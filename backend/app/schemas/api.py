from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.capabilities import Capability
from app.models.entities import ArtifactKind, DetectionSource, MediaStreamType, ProjectStatus


class DependencyResponse(BaseModel):
    name: str
    available: bool
    path: str | None
    version: str | None
    error: str | None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    dependencies: list[DependencyResponse]
    capabilities: list[Capability]


class ConfigResponse(BaseModel):
    max_upload_mb: int
    supported_extensions: list[str]
    workspace_dir: str


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MediaStreamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stream_index: int
    stream_type: MediaStreamType
    codec_name: str | None
    codec_long_name: str | None
    duration_seconds: float | None
    bit_rate: int | None
    sample_rate: int | None
    channels: int | None
    channel_layout: str | None
    width: int | None
    height: int | None
    frame_rate: str | None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: ProjectStatus
    original_filename: str | None
    media_type: str | None
    source_size_bytes: int | None
    duration_seconds: float | None
    container_format: str | None
    source_bit_rate: int | None
    media_streams: list[MediaStreamResponse]
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    project: ProjectResponse
    artifact_id: int
    stored_filename: str
    detected_type: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ArtifactKind
    relative_path: str
    size_bytes: int
    created_at: datetime


class MediaProcessResponse(BaseModel):
    project: ProjectResponse
    normalized_artifact: ArtifactResponse
    reused: bool


class NoteEventResponse(BaseModel):
    id: int
    pitch: int
    velocity: int
    raw_start_seconds: float
    raw_end_seconds: float
    confidence: float | None
    pitch_bends: list[int] | None
    source: DetectionSource


class TranscriptionProvenanceResponse(BaseModel):
    run_id: int
    model_name: str
    model_version: str
    model_runtime: str
    configuration: dict[str, object]


class TranscriptionResponse(BaseModel):
    project: ProjectResponse
    note_events_artifact: ArtifactResponse
    raw_midi_artifact: ArtifactResponse
    note_count: int
    preview_notes: list[NoteEventResponse]
    provenance: TranscriptionProvenanceResponse
    reused: bool
