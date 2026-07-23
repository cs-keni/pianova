import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

function melodyWav(noteStarts: number[], frequencies: number[]): Buffer {
  const sampleRate = 22050;
  const noteDuration = 0.34;
  const sampleCount = Math.ceil(
    sampleRate * (Math.max(...noteStarts) + noteDuration + 0.15),
  );
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

function quantizableWav(): Buffer {
  // Two attacks are offset by one analysis frame so Basic Pitch emits stable
  // 43-frame spacing across the real worker boundary.
  return melodyWav(
    [0.25, 0.75, 1.25, 1.74, 2.26],
    [261.63, 293.66, 329.63, 349.23, 392.0],
  );
}

function clearCMajorWav(): Buffer {
  const frequencies = [
    261.63, 329.63, 392.0, 523.25, 349.23, 392.0, 329.63, 261.63, 293.66, 349.23,
    440.0, 392.0,
  ];
  return melodyWav(
    frequencies.map((_, index) => 0.25 + index * 0.5),
    frequencies,
  );
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

test("separates notation voices for a real 120 BPM transcription", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();
  await expect(page.getByText("Piano transcription", { exact: true })).toBeVisible();
  await expect(page.getByText("Hand and staff assignment", { exact: true })).toBeVisible();
  await expect(page.getByText("Notation voice separation", { exact: true })).toBeVisible();
  await expect(page.getByText("Key detection and pitch spelling", { exact: true })).toBeVisible();
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
  await page.getByRole("button", { name: "Separate voices" }).click();
  await expect(page.getByText("Notation voice separation ready", { exact: true })).toBeVisible();
  await expect(page.getByText("5 resolved · 0 unknown", { exact: true })).toBeVisible();
  await expect(page.getByText("Notation voice evidence", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Voice 1", exact: true })).toHaveCount(5);
  await expect(page.getByText("Step 7 of 8", { exact: true })).toBeVisible();
  await expect(
    page.getByText(
      "Unknown voices remain evidence for review. Key detection, pitch spelling, cleaned MIDI, and score generation have not started.",
    ),
  ).toBeVisible();

  await page.getByRole("button", { name: "Detect key & spell notes" }).click();
  await expect(page.getByText("Key detection and pitch spelling ready")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Key uncertain" })).toBeVisible();
  await expect(
    page.getByText(
      "Insufficient notes. Choose the intended key below to respell these notes.",
    ),
  ).toBeVisible();
  await expect(page.getByText("2 resolved · 3 unknown", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "Unknown", exact: true })).toHaveCount(3);

  await page.getByLabel("Key signature").selectOption("C major");
  await page.getByRole("button", { name: "Detect key & spell notes" }).click();
  await expect(page.getByText("User-chosen key", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "C major", exact: true })).toBeVisible();
  await expect(page.getByText("Applied as an explicit override.", { exact: true })).toBeVisible();
  await expect(page.getByText("5 resolved · 0 unknown", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "C4", exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: "D4", exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: "E4", exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: "F4", exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: "G4", exact: true })).toHaveCount(1);
  await expect(page.getByText("Step 8 of 8", { exact: true })).toBeVisible();
  await expect(
    page.getByText(
      "Unknown spellings remain evidence for review. Cleaned MIDI, MusicXML, and score rendering have not started.",
    ),
  ).toBeVisible();
});

test("automatically estimates a clear key and spells a real transcription", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await expect(page.getByText("API connected")).toBeVisible();

  await page.getByLabel("Project name").fill(`C major study ${Date.now()}`);
  await page.getByRole("button", { name: "Create local project" }).click();
  await page.getByLabel("Piano audio or video").setInputFiles({
    name: "c-major-study.wav",
    mimeType: "audio/wav",
    buffer: clearCMajorWav(),
  });
  await page.getByRole("button", { name: "Upload source file" }).click();
  await page.getByRole("button", { name: "Inspect and prepare audio" }).click();
  await expect(page.getByText("Media inspected and audio normalized")).toBeVisible();
  await page.getByRole("button", { name: "Transcribe piano" }).click();
  await expect(page.getByText("Raw transcription complete")).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("Tempo override (BPM)").fill("120");
  await page.getByRole("button", { name: "Estimate tempo and quantize" }).click();
  await expect(page.getByText("Readable timing ready", { exact: true }).last()).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Assign hands and staves" }).click();
  await expect(page.getByText("Hand and staff interpretation ready")).toBeVisible();
  await page.getByRole("button", { name: "Separate voices" }).click();
  await expect(page.getByText("Notation voice separation ready", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Detect key & spell notes" }).click();

  await expect(page.getByText("Estimated key", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "C major", exact: true })).toBeVisible();
  await expect(page.getByText(/uncalibrated decision score · 0 fifths/)).toBeVisible();
  await expect(page.getByText(/resolved · 0 unknown/, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Step 8 of 8", { exact: true })).toBeVisible();
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
