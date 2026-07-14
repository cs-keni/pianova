from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.capabilities import Capability
from app.models.entities import ProjectStatus


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


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: ProjectStatus
    original_filename: str | None
    media_type: str | None
    source_size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    project: ProjectResponse
    artifact_id: int
    stored_filename: str
    detected_type: str
