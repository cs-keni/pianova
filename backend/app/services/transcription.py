import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.core.errors import PianovaError
from app.models.entities import (
    Artifact,
    ArtifactKind,
    DetectionSource,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    utc_now,
)
from app.transcription.contracts import WorkerTranscriptionOutput

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "transcription"
PREVIEW_NOTE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    events_artifact: Artifact
    midi_artifact: Artifact
    run: ProcessingRun
    notes: tuple[NoteEvent, ...]
    reused: bool


class TranscriptionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        dependency: DependencyStatus,
    ) -> None:
        self.session = session
        self.settings = settings
        self.dependency = dependency

    def transcribe(self, project: Project) -> TranscriptionResult:
        normalized = self._artifact(project.id, ArtifactKind.NORMALIZED_AUDIO)
        if normalized is None:
            raise PianovaError(
                "normalized_audio_required",
                "Inspect and prepare the source audio before transcription.",
                409,
            )
        if (
            project.duration_seconds is None
            or project.duration_seconds < self.settings.transcription_minimum_duration_seconds
        ):
            raise PianovaError(
                "audio_too_short_for_transcription",
                (
                    "The prepared audio must be at least "
                    f"{self.settings.transcription_minimum_duration_seconds:.2f} seconds long."
                ),
                422,
            )

        existing_events = self._artifact(project.id, ArtifactKind.NOTE_EVENTS)
        existing_midi = self._artifact(project.id, ArtifactKind.RAW_MIDI)
        if existing_events is not None or existing_midi is not None:
            if existing_events is None or existing_midi is None:
                raise PianovaError(
                    "incomplete_transcription_artifacts",
                    "Stored transcription artifacts are incomplete.",
                    500,
                )
            if not self._artifact_path(existing_events).is_file():
                raise PianovaError(
                    "note_events_artifact_missing",
                    "The note-event record exists, but its file is missing.",
                    500,
                )
            if not self._artifact_path(existing_midi).is_file():
                raise PianovaError(
                    "raw_midi_artifact_missing",
                    "The raw MIDI record exists, but its file is missing.",
                    500,
                )
            run = self.session.scalar(
                select(ProcessingRun)
                .where(
                    ProcessingRun.project_id == project.id,
                    ProcessingRun.stage == PROCESSING_STAGE,
                    ProcessingRun.status == ProcessingStatus.SUCCEEDED,
                )
                .order_by(ProcessingRun.id.desc())
            )
            if run is None:
                raise PianovaError(
                    "transcription_provenance_missing",
                    "The transcription artifacts have no successful provenance record.",
                    500,
                )
            notes = tuple(
                self.session.scalars(
                    select(NoteEvent)
                    .where(NoteEvent.project_id == project.id)
                    .order_by(NoteEvent.raw_start_seconds, NoteEvent.pitch)
                ).all()
            )
            return TranscriptionResult(
                events_artifact=existing_events,
                midi_artifact=existing_midi,
                run=run,
                notes=notes,
                reused=True,
            )

        if not self.dependency.available or not self.dependency.path:
            raise PianovaError(
                "transcription_unavailable",
                "Install the isolated Basic Pitch transcription environment.",
                503,
            )

        normalized_path = self._artifact_path(normalized)
        if not normalized_path.is_file():
            raise PianovaError(
                "normalized_audio_missing",
                "The normalized audio file is missing.",
                500,
            )

        configuration = self._configuration()
        run = ProcessingRun(
            project_id=project.id,
            stage=PROCESSING_STAGE,
            status=ProcessingStatus.RUNNING,
            configuration_json=json.dumps(configuration, sort_keys=True),
            started_at=utc_now(),
        )
        self.session.add(run)
        self.session.commit()

        token = uuid.uuid4().hex
        project_dir = normalized_path.parent
        temporary_events = project_dir / f".transcription-{token}.tmp.json"
        temporary_midi = project_dir / f".transcription-{token}.tmp.mid"
        final_events = project_dir / f"note-events-{token}.json"
        final_midi = project_dir / f"raw-midi-{token}.mid"
        finalized_paths: list[Path] = []

        try:
            self._run_worker(normalized_path, temporary_events, temporary_midi)
            output = self._load_output(temporary_events)
            if not temporary_midi.is_file() or temporary_midi.stat().st_size == 0:
                raise PianovaError(
                    "invalid_transcription_output",
                    "The transcription worker did not produce raw MIDI.",
                    502,
                )

            os.replace(temporary_events, final_events)
            finalized_paths.append(final_events)
            os.replace(temporary_midi, final_midi)
            finalized_paths.append(final_midi)

            notes = tuple(
                NoteEvent(
                    project_id=project.id,
                    pitch=note.pitch,
                    velocity=note.velocity,
                    raw_start_seconds=note.start_seconds,
                    raw_end_seconds=note.end_seconds,
                    confidence=note.confidence,
                    pitch_bends_json=(
                        json.dumps(note.pitch_bends, separators=(",", ":"))
                        if note.pitch_bends
                        else None
                    ),
                    source=DetectionSource.AUDIO,
                )
                for note in output.notes
            )
            events_artifact = Artifact(
                project_id=project.id,
                kind=ArtifactKind.NOTE_EVENTS,
                relative_path=str(final_events.relative_to(self.settings.workspace_dir)),
                size_bytes=final_events.stat().st_size,
            )
            midi_artifact = Artifact(
                project_id=project.id,
                kind=ArtifactKind.RAW_MIDI,
                relative_path=str(final_midi.relative_to(self.settings.workspace_dir)),
                size_bytes=final_midi.stat().st_size,
            )
            self.session.add_all([*notes, events_artifact, midi_artifact])

            provenance = output.provenance
            stored_configuration: dict[str, object] = {
                **provenance.configuration,
                "runtime_version": provenance.runtime_version,
                "model_serialization": provenance.model_serialization,
            }
            run.model_name = provenance.model_name
            run.model_version = provenance.model_version
            run.model_runtime = provenance.model_runtime
            run.configuration_json = json.dumps(stored_configuration, sort_keys=True)
            run.status = ProcessingStatus.SUCCEEDED
            run.completed_at = utc_now()
            self.session.commit()
            return TranscriptionResult(
                events_artifact=events_artifact,
                midi_artifact=midi_artifact,
                run=run,
                notes=notes,
                reused=False,
            )
        except PianovaError as error:
            self.session.rollback()
            self._cleanup(temporary_events, temporary_midi, *finalized_paths)
            self._mark_failed(run.id, error.message)
            raise
        except IntegrityError as error:
            self.session.rollback()
            self._cleanup(temporary_events, temporary_midi, *finalized_paths)
            self._mark_failed(run.id, "Transcription artifacts could not be committed.")
            raise PianovaError(
                "transcription_already_exists",
                "This project already has a raw transcription.",
                409,
            ) from error
        except Exception as error:
            self.session.rollback()
            self._cleanup(temporary_events, temporary_midi, *finalized_paths)
            self._mark_failed(run.id, "Transcription failed.")
            logger.exception("Transcription failed for project %s", project.id)
            raise PianovaError(
                "transcription_failed",
                "The normalized audio could not be transcribed.",
                500,
            ) from error

    def _run_worker(
        self,
        normalized_path: Path,
        events_output: Path,
        midi_output: Path,
    ) -> None:
        configuration = self._configuration()
        command = [
            self.dependency.path or str(self.settings.resolved_transcription_python_path),
            "-m",
            "app.transcription.worker",
            "--input",
            str(normalized_path),
            "--events-output",
            str(events_output),
            "--midi-output",
            str(midi_output),
            "--onset-threshold",
            str(configuration["onset_threshold"]),
            "--frame-threshold",
            str(configuration["frame_threshold"]),
            "--minimum-note-length-ms",
            str(configuration["minimum_note_length_ms"]),
            "--minimum-frequency-hz",
            str(configuration["minimum_frequency_hz"]),
            "--maximum-frequency-hz",
            str(configuration["maximum_frequency_hz"]),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.transcription_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise PianovaError(
                "transcription_timeout",
                "Piano transcription timed out.",
                504,
            ) from error
        except OSError as error:
            raise PianovaError(
                "transcription_unavailable",
                "The Basic Pitch transcription worker could not be started.",
                503,
            ) from error
        if result.returncode != 0:
            logger.error(
                "Transcription worker failed with exit code %s: %s",
                result.returncode,
                result.stderr[-2000:],
            )
            raise PianovaError(
                "transcription_inference_failed",
                "Basic Pitch could not transcribe the normalized audio.",
                422,
                {"exit_code": result.returncode},
            )

    def _load_output(self, path: Path) -> WorkerTranscriptionOutput:
        if not path.is_file() or path.stat().st_size == 0:
            raise PianovaError(
                "invalid_transcription_output",
                "The transcription worker did not produce note events.",
                502,
            )
        try:
            output = WorkerTranscriptionOutput.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise PianovaError(
                "invalid_transcription_output",
                "The transcription worker returned invalid note events.",
                502,
            ) from error
        if output.schema_version != 1 or output.provenance.model_name != "basic_pitch":
            raise PianovaError(
                "invalid_transcription_output",
                "The transcription worker returned unsupported provenance.",
                502,
            )
        return output

    def _configuration(self) -> dict[str, float]:
        return {
            "onset_threshold": self.settings.transcription_onset_threshold,
            "frame_threshold": self.settings.transcription_frame_threshold,
            "minimum_note_length_ms": self.settings.transcription_minimum_note_length_ms,
            "minimum_frequency_hz": self.settings.transcription_minimum_frequency_hz,
            "maximum_frequency_hz": self.settings.transcription_maximum_frequency_hz,
        }

    def _artifact(self, project_id: str, kind: ArtifactKind) -> Artifact | None:
        return self.session.scalar(
            select(Artifact).where(Artifact.project_id == project_id, Artifact.kind == kind)
        )

    def _artifact_path(self, artifact: Artifact) -> Path:
        workspace = self.settings.workspace_dir.resolve()
        candidate = (workspace / artifact.relative_path).resolve()
        if not candidate.is_relative_to(workspace):
            raise PianovaError("invalid_artifact_path", "Stored artifact metadata is invalid.", 500)
        return candidate

    def _mark_failed(self, run_id: int, message: str) -> None:
        try:
            run = self.session.get(ProcessingRun, run_id)
            if run is None:
                return
            run.status = ProcessingStatus.FAILED
            run.error_message = message
            run.completed_at = utc_now()
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Could not persist failed transcription run %s", run_id)

    @staticmethod
    def _cleanup(*paths: Path) -> None:
        for path in paths:
            path.unlink(missing_ok=True)
