from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, get_settings
from app.core.capabilities import build_capabilities
from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.core.errors import PianovaError
from app.models.entities import Project
from app.schemas import (
    ConfigResponse,
    DependencyResponse,
    HealthResponse,
    ProjectCreate,
    ProjectResponse,
    UploadResponse,
)
from app.services.projects import ProjectService
from app.services.storage import SUPPORTED_EXTENSIONS, UploadService

router = APIRouter(prefix="/api")
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[Session, Depends(get_session)]
UploadDependency = Annotated[UploadFile, File()]


@router.get("/health", response_model=HealthResponse)
def health(request: Request, settings: SettingsDependency) -> HealthResponse:
    dependencies: dict[str, DependencyStatus] = request.app.state.dependencies
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        dependencies=[
            DependencyResponse(
                name=item.name,
                available=item.available,
                path=item.path,
                version=item.version,
                error=item.error,
            )
            for item in dependencies.values()
        ],
        capabilities=build_capabilities(
            ffmpeg=dependencies["ffmpeg"].available,
            ffprobe=dependencies["ffprobe"].available,
            musescore=dependencies["musescore"].available,
        ),
    )


@router.get("/config", response_model=ConfigResponse)
def config(settings: SettingsDependency) -> ConfigResponse:
    return ConfigResponse(
        max_upload_mb=settings.max_upload_mb,
        supported_extensions=sorted(SUPPORTED_EXTENSIONS),
        workspace_dir=str(settings.workspace_dir),
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    payload: ProjectCreate,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Project:
    return ProjectService(session, settings).create(payload.title)


@router.post("/projects/{project_id}/upload", response_model=UploadResponse)
async def upload_media(
    project_id: str,
    file: UploadDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> UploadResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    artifact, stored_filename, detected_type = await UploadService(session, settings).store(
        project, file
    )
    return UploadResponse(
        project=ProjectResponse.model_validate(project),
        artifact_id=artifact.id,
        stored_filename=stored_filename,
        detected_type=detected_type,
    )
