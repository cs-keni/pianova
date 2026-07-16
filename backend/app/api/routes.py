import json
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
    ArtifactResponse,
    ConfigResponse,
    DependencyResponse,
    HealthResponse,
    MediaProcessResponse,
    NoteEventResponse,
    ProjectCreate,
    ProjectResponse,
    QuantizationProvenanceResponse,
    QuantizationRequest,
    QuantizationResponse,
    QuantizedNoteResponse,
    TempoEstimateDiagnosticsResponse,
    TranscriptionProvenanceResponse,
    TranscriptionResponse,
    UploadResponse,
)
from app.services.media import MediaService
from app.services.projects import ProjectService
from app.services.quantization import QuantizationService
from app.services.storage import SUPPORTED_EXTENSIONS, UploadService
from app.services.transcription import PREVIEW_NOTE_LIMIT, TranscriptionService

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
            transcription=dependencies["basic_pitch"].available,
        ),
    )


@router.get("/config", response_model=ConfigResponse)
def config(settings: SettingsDependency) -> ConfigResponse:
    return ConfigResponse(
        max_upload_mb=settings.max_upload_mb,
        supported_extensions=sorted(SUPPORTED_EXTENSIONS),
        workspace_dir=str(settings.workspace_dir),
    )


@router.get("/dependencies", response_model=list[DependencyResponse])
def dependency_status(request: Request) -> list[DependencyResponse]:
    dependencies: dict[str, DependencyStatus] = request.app.state.dependencies
    return [
        DependencyResponse(
            name=item.name,
            available=item.available,
            path=item.path,
            version=item.version,
            error=item.error,
        )
        for item in dependencies.values()
    ]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    payload: ProjectCreate,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Project:
    return ProjectService(session, settings).create(payload.title)


@router.post("/projects/{project_id}/upload", response_model=UploadResponse)
def upload_media(
    project_id: str,
    file: UploadDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> UploadResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    artifact, stored_filename, detected_type = UploadService(session, settings).store(project, file)
    return UploadResponse(
        project=ProjectResponse.model_validate(project),
        artifact_id=artifact.id,
        stored_filename=stored_filename,
        detected_type=detected_type,
    )


@router.post("/projects/{project_id}/process-media", response_model=MediaProcessResponse)
def process_media(
    project_id: str,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> MediaProcessResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    dependencies: dict[str, DependencyStatus] = request.app.state.dependencies
    result = MediaService(
        session,
        settings,
        ffmpeg=dependencies["ffmpeg"],
        ffprobe=dependencies["ffprobe"],
    ).process(project)
    return MediaProcessResponse(
        project=ProjectResponse.model_validate(project),
        normalized_artifact=ArtifactResponse.model_validate(result.artifact),
        reused=result.reused,
    )


@router.post("/projects/{project_id}/transcribe", response_model=TranscriptionResponse)
def transcribe_project(
    project_id: str,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> TranscriptionResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    dependencies: dict[str, DependencyStatus] = request.app.state.dependencies
    result = TranscriptionService(
        session,
        settings,
        dependency=dependencies["basic_pitch"],
    ).transcribe(project)
    run = result.run
    if run.model_name is None or run.model_version is None or run.model_runtime is None:
        raise PianovaError(
            "transcription_provenance_missing",
            "The successful transcription has incomplete provenance.",
            500,
        )
    try:
        configuration = json.loads(run.configuration_json or "{}")
    except json.JSONDecodeError as error:
        raise PianovaError(
            "transcription_provenance_invalid",
            "The successful transcription has invalid provenance.",
            500,
        ) from error
    preview_notes = [
        NoteEventResponse(
            id=note.id,
            pitch=note.pitch,
            velocity=note.velocity,
            raw_start_seconds=note.raw_start_seconds,
            raw_end_seconds=note.raw_end_seconds,
            confidence=note.confidence,
            pitch_bends=json.loads(note.pitch_bends_json) if note.pitch_bends_json else None,
            source=note.source,
        )
        for note in result.notes[:PREVIEW_NOTE_LIMIT]
    ]
    return TranscriptionResponse(
        project=ProjectResponse.model_validate(project),
        note_events_artifact=ArtifactResponse.model_validate(result.events_artifact),
        raw_midi_artifact=ArtifactResponse.model_validate(result.midi_artifact),
        note_count=len(result.notes),
        preview_notes=preview_notes,
        provenance=TranscriptionProvenanceResponse(
            run_id=run.id,
            model_name=run.model_name,
            model_version=run.model_version,
            model_runtime=run.model_runtime,
            configuration=configuration,
        ),
        reused=result.reused,
    )


@router.post("/projects/{project_id}/quantize", response_model=QuantizationResponse)
def quantize_project(
    project_id: str,
    payload: QuantizationRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> QuantizationResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    result = QuantizationService(session, settings).quantize(project, payload)
    provenance = result.provenance
    preview_notes = []
    for note in result.notes[: settings.quantization_preview_note_limit]:
        position = result.positions[note.id]
        preview_notes.append(
            QuantizedNoteResponse(
                id=note.id,
                pitch=note.pitch,
                velocity=note.velocity,
                raw_start_seconds=note.raw_start_seconds,
                raw_end_seconds=note.raw_end_seconds,
                symbolic_start_beats=float(position.symbolic_start_beats),
                symbolic_duration_beats=float(position.symbolic_duration_beats),
                chord_group=position.chord_group,
                measure_number=position.measure_number,
                beat_in_measure=float(position.beat_in_measure),
                confidence=note.confidence,
                source=note.source,
            )
        )
    return QuantizationResponse(
        project=ProjectResponse.model_validate(project),
        note_count=len(result.notes),
        preview_notes=preview_notes,
        diagnostics=TempoEstimateDiagnosticsResponse(
            candidate_bpm=result.diagnostics.candidate_bpm,
            residual=result.diagnostics.residual,
            inlier_coverage=result.diagnostics.inlier_coverage,
            winning_score=result.diagnostics.winning_score,
            runner_up_score=result.diagnostics.runner_up_score,
            score_margin=result.diagnostics.score_margin,
            chord_group_count=result.diagnostics.chord_group_count,
            onset_span_seconds=result.diagnostics.onset_span_seconds,
            octave_ambiguous=result.diagnostics.octave_ambiguous,
        ),
        provenance=QuantizationProvenanceResponse(
            run_id=result.run.id,
            processor_name=str(provenance["processor_name"]),
            processor_version=str(provenance["processor_version"]),
            runtime=str(provenance["runtime"]),
            input_fingerprint=str(provenance["input_fingerprint"]),
            configuration=provenance,
        ),
        reused=result.reused,
    )
