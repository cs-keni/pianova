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
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  project: Project;
  artifact_id: number;
  stored_filename: string;
  detected_type: string;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
  };
}

const API_URL = process.env.NEXT_PUBLIC_PIANOVA_API_URL ?? "http://127.0.0.1:8000";

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
      "Pianova could not reach the local API. Start the backend on port 8000 and try again.",
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
};
