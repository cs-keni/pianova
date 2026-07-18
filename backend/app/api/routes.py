import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, get_settings
from app.core.capabilities import build_capabilities
from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.core.errors import PianovaError
from app.models.entities import (
    AssignmentAmbiguityReason,
    Hand,
    Project,
    Staff,
    VoiceAmbiguityReason,
)
from app.schemas import (
    ArtifactResponse,
    ConfigResponse,
    DependencyResponse,
    HealthResponse,
    InterpretationDiagnosticsResponse,
    InterpretationProvenanceResponse,
    InterpretationResponse,
    InterpretedNoteResponse,
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
    VoiceDiagnosticsResponse,
    VoicedNoteResponse,
    VoiceProvenanceResponse,
    VoiceSeparationResponse,
)
from app.services.interpretation import InterpretationService
from app.services.media import MediaService
from app.services.projects import ProjectService
from app.services.quantization import QuantizationService
from app.services.storage import SUPPORTED_EXTENSIONS, UploadService
from app.services.transcription import PREVIEW_NOTE_LIMIT, TranscriptionService
from app.services.voices import VoiceService

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


@router.post("/projects/{project_id}/interpret", response_model=InterpretationResponse)
def interpret_project(
    project_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InterpretationResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    result = InterpretationService(session, settings).interpret(project)
    provenance = result.provenance
    quantization_run_id = provenance.get("quantization_run_id")
    if not isinstance(quantization_run_id, int) or isinstance(quantization_run_id, bool):
        raise PianovaError(
            "interpretation_provenance_invalid",
            "The successful interpretation has invalid provenance.",
            500,
        )
    preview_notes: list[InterpretedNoteResponse] = []
    for note in result.notes[: settings.interpretation_preview_note_limit]:
        assignment = result.assignments[note.id]
        if (
            note.symbolic_start_beats is None
            or note.symbolic_duration_beats is None
            or note.chord_group is None
        ):
            raise PianovaError(
                "interpretation_result_invalid",
                "The interpreted note preview has incomplete timing.",
                500,
            )
        preview_notes.append(
            InterpretedNoteResponse(
                id=note.id,
                pitch=note.pitch,
                symbolic_start_beats=note.symbolic_start_beats,
                symbolic_duration_beats=note.symbolic_duration_beats,
                chord_group=note.chord_group,
                hand=Hand(assignment.hand),
                staff=Staff(assignment.staff),
                hand_confidence=assignment.hand_confidence,
                staff_confidence=assignment.staff_confidence,
                hand_ambiguity_reason=(
                    AssignmentAmbiguityReason(assignment.hand_ambiguity_reason)
                    if assignment.hand_ambiguity_reason
                    else None
                ),
                staff_ambiguity_reason=(
                    AssignmentAmbiguityReason(assignment.staff_ambiguity_reason)
                    if assignment.staff_ambiguity_reason
                    else None
                ),
            )
        )
    diagnostics = result.diagnostics
    return InterpretationResponse(
        project=ProjectResponse.model_validate(project),
        note_count=len(result.notes),
        preview_notes=preview_notes,
        diagnostics=InterpretationDiagnosticsResponse(
            chord_group_count=diagnostics.chord_group_count,
            candidate_state_count=diagnostics.candidate_state_count,
            transition_evaluations=diagnostics.transition_evaluations,
            resolved_hand_count=diagnostics.resolved_hand_count,
            unknown_hand_count=diagnostics.unknown_hand_count,
            resolved_staff_count=diagnostics.resolved_staff_count,
            unknown_staff_count=diagnostics.unknown_staff_count,
            wide_chord_count=diagnostics.wide_chord_count,
            crossing_pressure_count=diagnostics.crossing_pressure_count,
        ),
        provenance=InterpretationProvenanceResponse(
            run_id=result.run.id,
            processor_name=str(provenance["processor_name"]),
            processor_version=str(provenance["processor_version"]),
            runtime=str(provenance["runtime"]),
            quantization_run_id=quantization_run_id,
            input_fingerprint=str(provenance["input_fingerprint"]),
            configuration=provenance,
        ),
        reused=result.reused,
    )


@router.post(
    "/projects/{project_id}/separate-voices",
    response_model=VoiceSeparationResponse,
)
def separate_project_voices(
    project_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
) -> VoiceSeparationResponse:
    project = session.get(Project, project_id)
    if project is None:
        raise PianovaError("project_not_found", "The requested project does not exist.", 404)
    result = VoiceService(session, settings).separate(project)
    provenance = result.provenance
    interpretation_run_id = provenance.get("interpretation_run_id")
    if not isinstance(interpretation_run_id, int) or isinstance(interpretation_run_id, bool):
        raise PianovaError(
            "voice_separation_provenance_invalid",
            "The successful voice separation has invalid provenance.",
            500,
        )
    preview_notes: list[VoicedNoteResponse] = []
    for note in result.notes[: settings.voice_preview_note_limit]:
        assignment = result.assignments[note.id]
        if (
            note.symbolic_start_beats is None
            or note.symbolic_duration_beats is None
            or note.chord_group is None
        ):
            raise PianovaError(
                "voice_separation_result_invalid",
                "The voice-separated note preview has incomplete timing.",
                500,
            )
        preview_notes.append(
            VoicedNoteResponse(
                id=note.id,
                pitch=note.pitch,
                symbolic_start_beats=note.symbolic_start_beats,
                symbolic_duration_beats=note.symbolic_duration_beats,
                chord_group=note.chord_group,
                hand=note.hand,
                staff=note.staff,
                voice=assignment.voice,
                voice_confidence=assignment.voice_confidence,
                voice_ambiguity_reason=(
                    VoiceAmbiguityReason(assignment.voice_ambiguity_reason)
                    if assignment.voice_ambiguity_reason
                    else None
                ),
            )
        )
    diagnostics = result.diagnostics

    def count(staff: Staff, voice: int) -> int:
        return sum(
            note.staff is staff and result.assignments[note.id].voice == voice
            for note in result.notes
        )

    return VoiceSeparationResponse(
        project=ProjectResponse.model_validate(project),
        note_count=len(result.notes),
        preview_notes=preview_notes,
        diagnostics=VoiceDiagnosticsResponse(
            treble_note_count=diagnostics.treble_note_count,
            bass_note_count=diagnostics.bass_note_count,
            chord_node_count=diagnostics.chord_node_count,
            conflict_component_count=diagnostics.conflict_component_count,
            two_voice_component_count=diagnostics.two_voice_component_count,
            crossing_component_count=diagnostics.crossing_component_count,
            capacity_exceeded_count=diagnostics.capacity_exceeded_count,
            unresolved_staff_count=diagnostics.unresolved_staff_count,
            resolved_count=diagnostics.resolved_count,
            unknown_count=diagnostics.unknown_count,
            treble_voice_1_count=count(Staff.TREBLE, 1),
            treble_voice_2_count=count(Staff.TREBLE, 2),
            bass_voice_1_count=count(Staff.BASS, 1),
            bass_voice_2_count=count(Staff.BASS, 2),
        ),
        provenance=VoiceProvenanceResponse(
            run_id=result.run.id,
            processor_name=str(provenance["processor_name"]),
            processor_version=str(provenance["processor_version"]),
            runtime=str(provenance["runtime"]),
            interpretation_run_id=interpretation_run_id,
            input_fingerprint=str(provenance["input_fingerprint"]),
            configuration=provenance,
        ),
        reused=result.reused,
    )
