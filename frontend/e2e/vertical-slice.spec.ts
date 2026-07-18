import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

function quantizableWav(): Buffer {
  const sampleRate = 22050;
  // Two attacks are offset by one analysis frame so Basic Pitch emits stable
  // 43-frame spacing across the real worker boundary.
  const noteStarts = [0.25, 0.75, 1.25, 1.74, 2.26];
  const frequencies = [261.63, 293.66, 329.63, 349.23, 392.0];
  const noteDuration = 0.34;
  const sampleCount = Math.ceil(sampleRate * 2.75);
  const dataSize = sampleCount * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  for (let index = 0; index < sampleCount; index += 1) {
    const time = index / sampleRate;
    let value = 0;
    for (let noteIndex = 0; noteIndex < noteStarts.length; noteIndex += 1) {
      const noteTime = time - noteStarts[noteIndex];
      if (noteTime < 0 || noteTime >= noteDuration) continue;
      const attack = Math.min(1, noteTime / 0.015);
      const release = Math.min(1, (noteDuration - noteTime) / 0.04);
      const envelope = Math.min(attack, release);
      value +=
        Math.sin(2 * Math.PI * frequencies[noteIndex] * noteTime) * envelope * 0.65;
    }
    const sample = Math.round(Math.max(-1, Math.min(1, value)) * 16000);
    buffer.writeInt16LE(sample, 44 + index * 2);
  }
  return buffer;
}

function tinyMp4(): Buffer {
  const directory = mkdtempSync(join(tmpdir(), "pianova-video-"));
  const output = join(directory, "performance.mp4");
  try {
    const result = spawnSync(
      "ffmpeg",
      [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:d=0.25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=0.25",
        "-shortest",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        output,
      ],
      { encoding: "utf8" },
    );
    if (result.status !== 0) {
      throw new Error(`Could not generate MP4 fixture: ${result.stderr}`);
    }
    return readFileSync(output);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("interprets hands and staves for a real 120 BPM transcription", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();
  await expect(page.getByText("Piano transcription", { exact: true })).toBeVisible();
  await expect(page.getByText("Hand and staff assignment", { exact: true })).toBeVisible();
  await expect(page.getByText("not implemented").first()).toBeVisible();

  const title = `Playwright study ${Date.now()}`;
  await page.getByLabel("Project name").fill(title);
  await page.getByRole("button", { name: "Create local project" }).click();
  await expect(page.getByText("Add the performance")).toBeVisible();

  await page.getByLabel("Piano audio or video").setInputFiles({
    name: "performance.wav",
    mimeType: "audio/wav",
    buffer: quantizableWav(),
  });
  await page.getByRole("button", { name: "Upload source file" }).click();

  await expect(page.getByText("Source file secured")).toBeVisible();
  await expect(page.getByText("Transcription has not started.")).toBeVisible();
  await page.getByRole("button", { name: "Inspect and prepare audio" }).click();
  await expect(page.getByText("Media inspected and audio normalized")).toBeVisible();
  await expect(page.getByText("The normalized WAV is ready. Transcription has not started.")).toBeVisible();
  await page.getByRole("button", { name: "Transcribe piano" }).click();
  await expect(page.getByText("Raw transcription complete")).toBeVisible({ timeout: 60_000 });
  await expect(
    page.getByText("Raw MIDI and note-event JSON are saved. Quantization has not started."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Estimate tempo and quantize" }).click();
  await expect(page.getByText("Readable timing ready", { exact: true }).last()).toBeVisible({
    timeout: 60_000,
  });
  const timingSummary = await page
    .getByText(/BPM · 4\/4 · estimated tempo/)
    .textContent();
  const bpm = Number.parseFloat(timingSummary ?? "");
  expect(bpm).toBeGreaterThanOrEqual(119.5);
  expect(bpm).toBeLessThanOrEqual(120.5);
  await expect(page.getByText("Symbolic timing preview")).toBeVisible();
  await page.getByRole("button", { name: "Assign hands and staves" }).click();
  await expect(page.getByText("Hand and staff interpretation ready")).toBeVisible();
  await expect(page.getByText("Interpreted note preview")).toBeVisible();
  await expect(
    page.getByText(
      "Voices, key and pitch spelling, cleaned MIDI, and score generation have not started.",
    ),
  ).toBeVisible();
});

test("rejects a file whose contents do not match its audio extension", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();

  await page.getByLabel("Project name").fill(`Rejected upload ${Date.now()}`);
  await page.getByRole("button", { name: "Create local project" }).click();
  await expect(page.getByText("Add the performance")).toBeVisible();

  await page.getByLabel("Piano audio or video").setInputFiles({
    name: "not-really-audio.wav",
    mimeType: "audio/wav",
    buffer: Buffer.from("This is plain text, not a WAV file."),
  });
  await page.getByRole("button", { name: "Upload source file" }).click();

  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "The file contents do not match its supported media extension." }),
  ).toBeVisible();
  await expect(page.getByText("Source file secured")).not.toBeVisible();
});

test("inspects video and displays its audio and video streams", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();

  await page.getByLabel("Project name").fill(`Video study ${Date.now()}`);
  await page.getByRole("button", { name: "Create local project" }).click();
  await page.getByLabel("Piano audio or video").setInputFiles({
    name: "performance.mp4",
    mimeType: "video/mp4",
    buffer: tinyMp4(),
  });
  await page.getByRole("button", { name: "Upload source file" }).click();
  await page.getByRole("button", { name: "Inspect and prepare audio" }).click();

  await expect(page.getByText("Media inspected and audio normalized")).toBeVisible();
  await expect(page.getByText(/aac · 1 ch/)).toBeVisible();
  await expect(page.getByText(/mpeg4 · 64×64/)).toBeVisible();
});
