import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

const health = {
  status: "ok",
  app_name: "Pianova",
  environment: "test",
  dependencies: [],
  capabilities: [
    {
      key: "media_normalization",
      label: "Media normalization",
      state: "available",
      reason: null,
    },
    {
      key: "transcription",
      label: "Piano transcription",
      state: "not_implemented",
      reason: "The transcription pipeline has not been implemented yet.",
    },
  ],
};

const config = {
  max_upload_mb: 250,
  supported_extensions: [".m4a", ".mov", ".mp3", ".mp4", ".wav"],
  workspace_dir: "workspace",
};

const project = {
  id: "project-1",
  title: "Moonlight study",
  status: "created",
  original_filename: null,
  media_type: null,
  source_size_bytes: null,
  created_at: "2026-07-14T00:00:00Z",
  updated_at: "2026-07-14T00:00:00Z",
};

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Pianova home", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = input.toString();
        if (url.endsWith("/api/health")) return Promise.resolve(jsonResponse(health));
        if (url.endsWith("/api/config")) return Promise.resolve(jsonResponse(config));
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      }),
    );
  });

  it("shows backend state and truthful unfinished capabilities", async () => {
    render(<Home />);

    expect(await screen.findByText("API connected")).toBeInTheDocument();
    expect(screen.getByText("Media normalization")).toBeInTheDocument();
    expect(screen.getByText("Piano transcription")).toBeInTheDocument();
    expect(screen.getByText("not implemented")).toBeInTheDocument();
  });

  it("creates a project once and advances to upload", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = input.toString();
      if (url.endsWith("/api/health")) return Promise.resolve(jsonResponse(health));
      if (url.endsWith("/api/config")) return Promise.resolve(jsonResponse(config));
      if (url.endsWith("/api/projects")) return Promise.resolve(jsonResponse(project, 201));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
    const user = userEvent.setup();
    render(<Home />);

    await screen.findByText("API connected");
    await user.type(screen.getByLabelText("Project name"), "Moonlight study");
    await user.click(screen.getByRole("button", { name: "Create local project" }));

    expect(await screen.findByText("Add the performance")).toBeInTheDocument();
    expect(screen.getByText("Moonlight study")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => input.toString().endsWith("/api/projects"))).toHaveLength(1);
  });

  it("shows clear connection recovery guidance", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("offline"));
    render(<Home />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Start the backend on port 8000");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("uploads a selected source file and stops before transcription", async () => {
    const uploadedProject = {
      ...project,
      status: "uploaded",
      original_filename: "performance.wav",
      source_size_bytes: 44,
    };
    vi.mocked(fetch).mockImplementation((input) => {
      const url = input.toString();
      if (url.endsWith("/api/health")) return Promise.resolve(jsonResponse(health));
      if (url.endsWith("/api/config")) return Promise.resolve(jsonResponse(config));
      if (url.endsWith("/api/projects")) return Promise.resolve(jsonResponse(project, 201));
      if (url.endsWith("/api/projects/project-1/upload")) {
        return Promise.resolve(
          jsonResponse({
            project: uploadedProject,
            artifact_id: 1,
            stored_filename: "source-test.wav",
            detected_type: "wav",
          }),
        );
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
    const user = userEvent.setup();
    render(<Home />);
    await screen.findByText("API connected");
    await user.type(screen.getByLabelText("Project name"), "Moonlight study");
    await user.click(screen.getByRole("button", { name: "Create local project" }));
    const input = await screen.findByLabelText("Piano audio or video");
    await user.upload(input, new File(["RIFF"], "performance.wav", { type: "audio/wav" }));
    await user.click(screen.getByRole("button", { name: "Upload source file" }));

    await waitFor(() => expect(screen.getByText("Source file secured")).toBeInTheDocument());
    expect(screen.getByText("Transcription is intentionally not started yet.")).toBeInTheDocument();
  });
});
