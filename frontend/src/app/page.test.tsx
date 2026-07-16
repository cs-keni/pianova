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
      state: "available",
      reason: "Basic Pitch transcription and raw MIDI generation are ready.",
    },
    {
      key: "quantization",
      label: "Tempo and rhythm quantization",
      state: "available",
      reason: "Global tempo estimation and readable straight-note quantization are ready.",
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
  duration_seconds: null,
  container_format: null,
  source_bit_rate: null,
  estimated_tempo_bpm: null,
  selected_tempo_bpm: null,
  tempo_source: null,
  measure_origin_seconds: null,
  measure_origin_source: null,
  meter_numerator: null,
  meter_denominator: null,
  meter_source: null,
  current_quantization_run_id: null,
  quantization_revision: 0,
  media_streams: [],
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
    expect(screen.getByText("Tempo and rhythm quantization")).toBeInTheDocument();
    expect(screen.getAllByText("available")).toHaveLength(3);
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

    expect(await screen.findByRole("alert")).toHaveTextContent("Start the backend on port 18080");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("uploads a selected source file and offers explicit media processing", async () => {
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
    expect(screen.getByText(/Transcription has not started/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect and prepare audio" })).toBeInTheDocument();
  });

  it("shows inspected metadata and runs explicit raw transcription", async () => {
    const uploadedProject = {
      ...project,
      status: "uploaded",
      original_filename: "performance.wav",
      source_size_bytes: 44144,
    };
    const processedProject = {
      ...uploadedProject,
      duration_seconds: 75.2,
      container_format: "wav",
      source_bit_rate: 705600,
      media_streams: [
        {
          stream_index: 0,
          stream_type: "audio",
          codec_name: "pcm_s16le",
          codec_long_name: "PCM signed 16-bit little-endian",
          duration_seconds: 75.2,
          bit_rate: 705600,
          sample_rate: 44100,
          channels: 1,
          channel_layout: "mono",
          width: null,
          height: null,
          frame_rate: null,
        },
      ],
    };
    const quantizedProject = {
      ...processedProject,
      estimated_tempo_bpm: null,
      selected_tempo_bpm: 120,
      tempo_source: "override",
      measure_origin_seconds: 0.02,
      measure_origin_source: "default",
      meter_numerator: 3,
      meter_denominator: 4,
      meter_source: "override",
      current_quantization_run_id: 3,
      quantization_revision: 1,
    };
    let quantizationAttempts = 0;
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
      if (url.endsWith("/api/projects/project-1/process-media")) {
        return Promise.resolve(
          jsonResponse({
            project: processedProject,
            normalized_artifact: {
              id: 2,
              kind: "normalized_audio",
              relative_path: "projects/project-1/normalized-test.wav",
              size_bytes: 3316320,
              created_at: "2026-07-16T00:00:00Z",
            },
            reused: false,
          }),
        );
      }
      if (url.endsWith("/api/projects/project-1/transcribe")) {
        return Promise.resolve(
          jsonResponse({
            project: processedProject,
            note_events_artifact: {
              id: 3,
              kind: "note_events",
              relative_path: "projects/project-1/note-events-test.json",
              size_bytes: 1200,
              created_at: "2026-07-16T00:00:01Z",
            },
            raw_midi_artifact: {
              id: 4,
              kind: "raw_midi",
              relative_path: "projects/project-1/raw-midi-test.mid",
              size_bytes: 240,
              created_at: "2026-07-16T00:00:01Z",
            },
            note_count: 1,
            preview_notes: [
              {
                id: 1,
                pitch: 69,
                velocity: 74,
                raw_start_seconds: 0.02,
                raw_end_seconds: 0.23,
                confidence: 0.58,
                pitch_bends: [1, 1],
                source: "audio",
              },
            ],
            provenance: {
              run_id: 2,
              model_name: "basic_pitch",
              model_version: "0.4.0",
              model_runtime: "tensorflow",
              configuration: {
                runtime_version: "2.15.0",
              },
            },
            reused: false,
          }),
        );
      }
      if (url.endsWith("/api/projects/project-1/quantize")) {
        quantizationAttempts += 1;
        if (quantizationAttempts === 1) {
          return Promise.resolve(
            jsonResponse(
              {
                error: {
                  code: "tempo_ambiguous",
                  message: "Automatic tempo is uncertain. Enter a BPM to continue.",
                  details: {},
                },
              },
              422,
            ),
          );
        }
        return Promise.resolve(
          jsonResponse({
            project: quantizedProject,
            note_count: 1,
            preview_notes: [
              {
                id: 1,
                pitch: 69,
                velocity: 74,
                raw_start_seconds: 0.02,
                raw_end_seconds: 0.23,
                symbolic_start_beats: 0,
                symbolic_duration_beats: 0.5,
                chord_group: 1,
                measure_number: 1,
                beat_in_measure: 1,
                confidence: 0.58,
                source: "audio",
              },
            ],
            diagnostics: {
              candidate_bpm: null,
              residual: null,
              inlier_coverage: null,
              winning_score: null,
              runner_up_score: null,
              score_margin: null,
              chord_group_count: 1,
              onset_span_seconds: 0,
              octave_ambiguous: false,
            },
            provenance: {
              run_id: 3,
              processor_name: "pianova_symbolic_timing",
              processor_version: "1.0.0",
              runtime: "python 3.11.9",
              input_fingerprint: "abc123",
              configuration: {},
            },
            reused: false,
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
    await user.upload(
      await screen.findByLabelText("Piano audio or video"),
      new File(["RIFF"], "performance.wav", { type: "audio/wav" }),
    );
    await user.click(screen.getByRole("button", { name: "Upload source file" }));
    await user.click(await screen.findByRole("button", { name: "Inspect and prepare audio" }));

    expect(await screen.findByText("Media inspected and audio normalized")).toBeInTheDocument();
    expect(screen.getByText(/performance\.wav · 1:15/)).toBeInTheDocument();
    expect(screen.getByText("pcm_s16le · 1 ch")).toBeInTheDocument();
    expect(screen.getByText("44.1 kHz")).toBeInTheDocument();
    expect(
      screen.getByText("The normalized WAV is ready. Transcription has not started."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Transcribe piano" }));

    expect(await screen.findByText("Raw transcription complete")).toBeInTheDocument();
    expect(screen.getByText("1 detected note · basic_pitch 0.4.0")).toBeInTheDocument();
    expect(screen.getByText("A4")).toBeInTheDocument();
    expect(screen.getByText("58%")).toBeInTheDocument();
    expect(
      screen.getByText("Raw MIDI and note-event JSON are saved. Quantization has not started."),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Meter"), "3/4");
    await user.click(screen.getByRole("button", { name: "Estimate tempo and quantize" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Automatic tempo is uncertain. Enter a BPM to continue.",
    );
    expect(screen.getByLabelText("Meter")).toHaveValue("3/4");
    await user.type(screen.getByLabelText("Tempo override (BPM)"), "120");
    await user.click(screen.getByRole("button", { name: "Estimate tempo and quantize" }));

    expect(
      await screen.findByRole("heading", { name: "Readable timing ready", level: 4 }),
    ).toBeInTheDocument();
    expect(screen.getByText("120.0 BPM · 3/4 · tempo override")).toBeInTheDocument();
    expect(screen.getByText("M1 · beat 1.00")).toBeInTheDocument();
    expect(screen.getByText("Override")).toBeInTheDocument();
    expect(quantizationAttempts).toBe(2);
  });
});
