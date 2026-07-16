export type CapabilityState = "available" | "unavailable" | "not_implemented";

export interface DependencyStatus {
  name: string;
  available: boolean;
  path: string | null;
  version: string | null;
  error: string | null;
}

export interface Capability {
  key: string;
  label: string;
  state: CapabilityState;
  reason: string | null;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  environment: string;
  dependencies: DependencyStatus[];
  capabilities: Capability[];
}

export interface ConfigResponse {
  max_upload_mb: number;
  supported_extensions: string[];
  workspace_dir: string;
}

export interface Project {
  id: string;
  title: string;
  status: "created" | "uploaded" | "failed";
  original_filename: string | null;
  media_type: string | null;
  source_size_bytes: number | null;
  duration_seconds: number | null;
  container_format: string | null;
  source_bit_rate: number | null;
  media_streams: MediaStream[];
  created_at: string;
  updated_at: string;
}

export interface MediaStream {
  stream_index: number;
  stream_type: "audio" | "video" | "other";
  codec_name: string | null;
  codec_long_name: string | null;
  duration_seconds: number | null;
  bit_rate: number | null;
  sample_rate: number | null;
  channels: number | null;
  channel_layout: string | null;
  width: number | null;
  height: number | null;
  frame_rate: string | null;
}

export interface UploadResponse {
  project: Project;
  artifact_id: number;
  stored_filename: string;
  detected_type: string;
}

export interface Artifact {
  id: number;
  kind:
    | "source"
    | "normalized_audio"
    | "note_events"
    | "raw_midi"
    | "clean_midi"
    | "musicxml"
    | "pdf";
  relative_path: string;
  size_bytes: number;
  created_at: string;
}

export interface MediaProcessResponse {
  project: Project;
  normalized_artifact: Artifact;
  reused: boolean;
}

export interface NoteEvent {
  id: number;
  pitch: number;
  velocity: number;
  raw_start_seconds: number;
  raw_end_seconds: number;
  confidence: number | null;
  pitch_bends: number[] | null;
  source: "audio" | "video" | "audio_and_video" | "manual";
}

export interface TranscriptionProvenance {
  run_id: number;
  model_name: string;
  model_version: string;
  model_runtime: string;
  configuration: Record<string, unknown>;
}

export interface TranscriptionResponse {
  project: Project;
  note_events_artifact: Artifact;
  raw_midi_artifact: Artifact;
  note_count: number;
  preview_notes: NoteEvent[];
  provenance: TranscriptionProvenance;
  reused: boolean;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
  };
}

const API_URL = process.env.NEXT_PUBLIC_PIANOVA_API_URL ?? "http://127.0.0.1:18080";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "Pianova could not reach the local API. Start the backend on port 18080 and try again.",
      "backend_unreachable",
      0,
    );
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new ApiError(
      body.error?.message ?? "The request failed.",
      body.error?.code ?? "request_failed",
      response.status,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  config: () => request<ConfigResponse>("/api/config"),
  createProject: (title: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  upload: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<UploadResponse>(`/api/projects/${projectId}/upload`, {
      method: "POST",
      body,
    });
  },
  processMedia: (projectId: string) =>
    request<MediaProcessResponse>(`/api/projects/${projectId}/process-media`, {
      method: "POST",
    }),
  transcribe: (projectId: string) =>
    request<TranscriptionResponse>(`/api/projects/${projectId}/transcribe`, {
      method: "POST",
    }),
};
