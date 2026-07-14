import { expect, test } from "@playwright/test";

function tinyWav(): Buffer {
  const buffer = Buffer.alloc(46);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(38, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(8000, 24);
  buffer.writeUInt32LE(16000, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(2, 40);
  buffer.writeInt16LE(0, 44);
  return buffer;
}

test("creates a project and securely uploads a piano source", async ({ page }) => {
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
  await expect(page.getByText("Transcription is intentionally not started yet.")).toBeVisible();
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
