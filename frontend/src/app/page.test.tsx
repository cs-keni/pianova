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
    {
      key: "interpretation",
      label: "Hand and staff assignment",
      state: "available",
      reason: "Independent hand and notation-staff assignment with uncertainty is ready.",
    },
    {
      key: "voice_separation",
      label: "Notation voice separation",
      state: "available",
      reason: "Staff-scoped forced notation voices with explicit uncertainty are ready.",
    },
    {
      key: "pitch_spelling",
      label: "Key detection and pitch spelling",
      state: "available",
      reason: "Global key detection and contextual enharmonic spelling are ready.",
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
  current_interpretation_run_id: null,
  interpretation_revision: 0,
  current_voice_run_id: null,
  voice_revision: 0,
  key_tonic_step: null,
  key_tonic_alter: null,
  key_mode: null,
  key_confidence: null,
  key_ambiguity_reason: null,
  key_source: null,
  current_spelling_run_id: null,
  spelling_revision: 0,
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
    expect(screen.getByText("Hand and staff assignment")).toBeInTheDocument();
    expect(screen.getByText("Notation voice separation")).toBeInTheDocument();
    expect(screen.getByText("Key detection and pitch spelling")).toBeInTheDocument();
    expect(screen.getAllByText("available")).toHaveLength(6);
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
      interpretation_revision: 1,
      voice_revision: 1,
      spelling_revision: 1,
    };
    let quantizationAttempts = 0;
    let interpretationAttempts = 0;
    let voiceAttempts = 0;
    let spellingAttempts = 0;
    let resolveInterpretation!: (response: Response) => void;
    let resolveVoices!: (response: Response) => void;
    let resolveSpelling!: (response: Response) => void;
    const spellingBodies: unknown[] = [];
    vi.mocked(fetch).mockImplementation((input, init) => {
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
      if (url.endsWith("/api/projects/project-1/interpret")) {
        interpretationAttempts += 1;
        if (interpretationAttempts === 1) {
          return new Promise<Response>((resolve) => {
            resolveInterpretation = resolve;
          });
        }
        return Promise.resolve(
          jsonResponse({
            project: {
              ...quantizedProject,
              current_interpretation_run_id: 4,
              interpretation_revision: 2,
              voice_revision: 2,
            },
            note_count: 1,
            preview_notes: [
              {
                id: 1,
                pitch: 69,
                symbolic_start_beats: 0,
                symbolic_duration_beats: 0.5,
                chord_group: 1,
                hand: "unknown",
                staff: "treble",
                hand_confidence: 0.42,
                staff_confidence: 0.91,
                hand_ambiguity_reason: "middle_register",
                staff_ambiguity_reason: null,
              },
            ],
            diagnostics: {
              chord_group_count: 1,
              candidate_state_count: 4,
              transition_evaluations: 0,
              resolved_hand_count: 0,
              unknown_hand_count: 1,
              resolved_staff_count: 1,
              unknown_staff_count: 0,
              wide_chord_count: 0,
              crossing_pressure_count: 0,
            },
            provenance: {
              run_id: 4,
              processor_name: "pianova_hand_staff_interpretation",
              processor_version: "1.0.0",
              runtime: "python 3.11.9",
              quantization_run_id: 3,
              input_fingerprint: "def456",
              configuration: {},
            },
            reused: false,
          }),
        );
      }
      if (url.endsWith("/api/projects/project-1/separate-voices")) {
        voiceAttempts += 1;
        if (voiceAttempts === 1) {
          return new Promise<Response>((resolve) => {
            resolveVoices = resolve;
          });
        }
        return Promise.resolve(
          jsonResponse({
            project: {
              ...quantizedProject,
              current_interpretation_run_id: 4,
              interpretation_revision: 2,
              current_voice_run_id: 5,
              voice_revision: 3,
            },
            note_count: 1,
            preview_notes: [
              {
                id: 1,
                pitch: 69,
                symbolic_start_beats: 0,
                symbolic_duration_beats: 0.5,
                chord_group: 1,
                hand: "unknown",
                staff: "treble",
                voice: null,
                voice_confidence: 0.42,
                voice_ambiguity_reason: "close_alternative",
              },
            ],
            diagnostics: {
              treble_note_count: 1,
              bass_note_count: 0,
              chord_node_count: 1,
              conflict_component_count: 0,
              two_voice_component_count: 0,
              crossing_component_count: 0,
              capacity_exceeded_count: 0,
              unresolved_staff_count: 0,
              resolved_count: 0,
              unknown_count: 1,
              treble_voice_1_count: 0,
              treble_voice_2_count: 0,
              bass_voice_1_count: 0,
              bass_voice_2_count: 0,
            },
            provenance: {
              run_id: 5,
              processor_name: "pianova_notation_voice_separation",
              processor_version: "1.0.0",
              runtime: "python 3.11.9",
              interpretation_run_id: 4,
              input_fingerprint: "ghi789",
              configuration: {},
            },
            reused: false,
          }),
        );
      }
      if (url.endsWith("/api/projects/project-1/spell")) {
        spellingAttempts += 1;
        spellingBodies.push(JSON.parse(String(init?.body ?? "{}")));
        if (spellingAttempts === 1) {
          return new Promise<Response>((resolve) => {
            resolveSpelling = resolve;
          });
        }
        const overridden = spellingAttempts === 3;
        return Promise.resolve(
          jsonResponse({
            project: {
              ...quantizedProject,
              current_interpretation_run_id: 4,
              interpretation_revision: 2,
              current_voice_run_id: 5,
              voice_revision: 3,
              key_tonic_step: overridden ? "C" : null,
              key_tonic_alter: overridden ? 0 : null,
              key_mode: overridden ? "major" : null,
              key_confidence: overridden ? null : 0,
              key_ambiguity_reason: overridden ? null : "insufficient_notes",
              key_source: overridden ? "override" : "estimated",
              current_spelling_run_id: 5 + spellingAttempts,
              spelling_revision: 3 + spellingAttempts,
            },
            key: {
              source: overridden ? "override" : "estimated",
              tonic_step: overridden ? "C" : null,
              tonic_alter: overridden ? 0 : null,
              mode: overridden ? "major" : null,
              confidence: overridden ? null : 0,
              ambiguity_reason: overridden ? null : "insufficient_notes",
              key_signature_fifths: overridden ? 0 : null,
            },
            note_count: 1,
            preview_notes: [
              {
                id: 1,
                pitch: 69,
                symbolic_start_beats: 0,
                symbolic_duration_beats: 0.5,
                chord_group: 1,
                hand: "unknown",
                staff: "treble",
                voice: null,
                spelled_step: overridden ? "A" : null,
                spelled_alter: overridden ? 0 : null,
                spelled_octave: overridden ? 4 : null,
                spelling_confidence: overridden ? 0.83 : 0,
                spelling_ambiguity_reason: overridden ? null : "unknown_key",
              },
            ],
            diagnostics: {
              pitch_class_histogram: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.5, 0, 0],
              best_key: null,
              best_key_correlation: null,
              runner_up_key: null,
              runner_up_key_correlation: null,
              key_correlation_margin: 0,
              plausible_keys: [],
              candidate_set_sizes: [1],
              chord_consistency_application_count: 0,
              melodic_rule_application_count: 0,
              resolved_count: overridden ? 1 : 0,
              unknown_count: overridden ? 0 : 1,
              unknown_key_count: overridden ? 0 : 1,
              close_alternative_count: 0,
            },
            provenance: {
              run_id: 5 + spellingAttempts,
              processor_name: "pianova_key_pitch_spelling",
              processor_version: "1.0.0",
              runtime: "python 3.11.9",
              voice_run_id: 5,
              input_fingerprint: "spell123",
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
    expect(screen.queryByRole("button", { name: "Separate voices" })).not.toBeInTheDocument();

    const interpretButton = screen.getByRole("button", { name: "Assign hands and staves" });
    await user.click(interpretButton);
    expect(screen.getByRole("button", { name: "Assigning hands and staves…" })).toBeDisabled();
    expect(interpretationAttempts).toBe(1);
    resolveInterpretation(
      jsonResponse(
        {
          error: {
            code: "interpretation_failed",
            message: "Hands and staves could not be assigned.",
          },
        },
        500,
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Hands and staves could not be assigned.",
    );
    await user.click(screen.getByRole("button", { name: "Assign hands and staves" }));

    expect(
      await screen.findByRole("heading", {
        name: "Hand and staff interpretation ready",
        level: 4,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("0 resolved · 1 unknown")).toBeInTheDocument();
    expect(screen.getByText("1 resolved · 0 unknown")).toBeInTheDocument();
    expect(screen.getByText("42% · middle register")).toBeInTheDocument();
    expect(screen.getByText("91% · Resolved")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Voices, key and pitch spelling, cleaned MIDI, and score generation have not started.",
      ),
    ).toBeInTheDocument();
    expect(interpretationAttempts).toBe(2);

    const voiceButton = screen.getByRole("button", { name: "Separate voices" });
    await user.click(voiceButton);
    expect(screen.getByRole("button", { name: "Separating notation voices…" })).toBeDisabled();
    expect(voiceAttempts).toBe(1);
    resolveVoices(
      jsonResponse(
        {
          error: {
            code: "voice_separation_failed",
            message: "Notation voices could not be separated.",
          },
        },
        500,
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Notation voices could not be separated.",
    );
    await user.click(screen.getByRole("button", { name: "Separate voices" }));

    expect(
      await screen.findByRole("heading", { name: "Notation voice separation ready", level: 4 }),
    ).toBeInTheDocument();
    expect(screen.getByText("0 resolved · 1 unknown")).toBeInTheDocument();
    expect(screen.getAllByText("V1 0 · V2 0")).toHaveLength(2);
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("close alternative")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Unknown voices remain evidence for review. Key detection, pitch spelling, cleaned MIDI, and score generation have not started.",
      ),
    ).toBeInTheDocument();
    expect(voiceAttempts).toBe(2);

    const spellButton = screen.getByRole("button", { name: "Detect key & spell notes" });
    expect(screen.getByLabelText("Key signature")).toHaveValue("");
    await user.click(spellButton);
    expect(
      screen.getByRole("button", { name: "Detecting key and spelling notes…" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Detecting key and spelling notes…" }),
    );
    expect(spellingAttempts).toBe(1);
    resolveSpelling(
      jsonResponse(
        {
          error: {
            code: "spelling_failed",
            message: "The project key and written pitches could not be produced.",
          },
        },
        500,
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The project key and written pitches could not be produced.",
    );
    await user.click(screen.getByRole("button", { name: "Detect key & spell notes" }));

    expect(
      await screen.findByRole("heading", {
        name: "Key detection and pitch spelling ready",
        level: 4,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Key uncertain")).toBeInTheDocument();
    expect(
      screen.getByText(
        "insufficient notes. Choose the intended key below to respell these notes.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("unknown key")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Unknown spellings remain evidence for review. Cleaned MIDI, MusicXML, and score rendering have not started.",
      ),
    ).toBeInTheDocument();
    expect(spellingBodies[1]).toEqual({});

    await user.selectOptions(screen.getByLabelText("Key signature"), "C major");
    await user.click(screen.getByRole("button", { name: "Detect key & spell notes" }));

    expect(await screen.findByText("User-chosen key")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "C major", level: 4 })).toBeInTheDocument();
    expect(screen.getByText("Applied as an explicit override.")).toBeInTheDocument();
    expect(screen.getByText("83%")).toBeInTheDocument();
    expect(spellingBodies[2]).toEqual({
      key_override: {
        tonic_step: "C",
        tonic_alter: 0,
        mode: "major",
      },
    });

    await user.selectOptions(screen.getByLabelText("Key signature"), "");
    await user.click(screen.getByRole("button", { name: "Detect key & spell notes" }));
    expect(await screen.findByText("Key uncertain")).toBeInTheDocument();
    expect(spellingBodies[3]).toEqual({});
    expect(spellingAttempts).toBe(4);
  });
});
