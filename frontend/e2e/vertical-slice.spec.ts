import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

function tinyWav(): Buffer {
  const sampleRate = 22050;
  const sampleCount = sampleRate;
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
    const sample = Math.round(Math.sin((2 * Math.PI * 440 * index) / sampleRate) * 10000);
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

test("creates a project, prepares audio, and runs raw transcription", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();
  await expect(page.getByText("Piano transcription", { exact: true })).toBeVisible();
  await expect(page.getByText("not implemented").first()).toBeVisible();

  const title = `Playwright study ${Date.now()}`;
  await page.getByLabel("Project name").fill(title);
  await page.getByRole("button", { name: "Create local project" }).click();
  await expect(page.getByText("Add the performance")).toBeVisible();

  await page.getByLabel("Piano audio or video").setInputFiles({
    name: "performance.wav",
    mimeType: "audio/wav",
    buffer: tinyWav(),
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
