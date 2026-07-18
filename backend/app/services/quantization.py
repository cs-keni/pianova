import json
import logging
import platform
from dataclasses import dataclass
from fractions import Fraction

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import PianovaError
from app.models.entities import (
    Artifact,
    ArtifactKind,
    Hand,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    SettingSource,
    Staff,
    TempoSource,
    utc_now,
)
from app.schemas.api import QuantizationRequest
from app.services.stage_runner import StageRunner
from app.symbolic.timing import (
    QuantizedTimingNote,
    RawTimingNote,
    TempoDiagnostics,
    TimingAnalysisError,
    TimingSettings,
    diagnostics_to_dict,
    measure_position,
    quantize_timing,
    raw_notes_fingerprint,
)

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "quantization"
PROCESSOR_NAME = "pianova_symbolic_timing"
PROCESSOR_RUNTIME = "python"


@dataclass(frozen=True, slots=True)
class QuantizationResult:
    run: ProcessingRun
    notes: tuple[NoteEvent, ...]
    positions: dict[int, QuantizedTimingNote]
    diagnostics: TempoDiagnostics
    provenance: dict[str, object]
    reused: bool


class QuantizationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.stage_runner = StageRunner(session, stage=PROCESSING_STAGE, logger=logger)

    def quantize(
        self,
        project: Project,
        request: QuantizationRequest,
    ) -> QuantizationResult:
        if not self._has_transcription_artifact(project.id):
            raise PianovaError(
                "transcription_required",
                "Transcribe the prepared audio before quantization.",
                409,
            )
        notes = tuple(
            self.session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project.id)
                .order_by(NoteEvent.raw_start_seconds, NoteEvent.pitch, NoteEvent.id)
            ).all()
        )
        if not notes:
            raise PianovaError(
                "notes_required",
                "No detected notes are available for quantization.",
                422,
            )

        raw_notes = tuple(
            RawTimingNote(
                id=note.id,
                pitch=note.pitch,
                start_seconds=note.raw_start_seconds,
                end_seconds=note.raw_end_seconds,
                confidence=note.confidence,
            )
            for note in notes
        )
        fingerprint = raw_notes_fingerprint(raw_notes)
        meter_numerator = request.meter_numerator or 4
        meter_denominator = request.meter_denominator or 4
        request_configuration = self._request_configuration(
            request,
            fingerprint=fingerprint,
            meter_numerator=meter_numerator,
            meter_denominator=meter_denominator,
        )
        reused = self._reuse_current(
            project,
            notes,
            request_configuration,
        )
        if reused is not None:
            return reused

        expected_revision = project.quantization_revision
        expected_interpretation_revision = project.interpretation_revision
        run = self.stage_runner.precommit_run(
            project_id=project.id,
            configuration=request_configuration,
        )

        try:
            timing = quantize_timing(
                raw_notes,
                self._timing_settings(),
                tempo_bpm=request.tempo_bpm,
                meter_numerator=meter_numerator,
                meter_denominator=meter_denominator,
                measure_origin_seconds=request.measure_origin_seconds,
            )
            positions = {item.note_id: item for item in timing.notes}
            for note in notes:
                position = positions[note.id]
                note.symbolic_start_beats = float(position.symbolic_start_beats)
                note.symbolic_duration_beats = float(position.symbolic_duration_beats)
                note.chord_group = position.chord_group
                note.hand = Hand.UNKNOWN
                note.staff = Staff.UNKNOWN
                note.hand_confidence = None
                note.staff_confidence = None
                note.hand_ambiguity_reason = None
                note.staff_ambiguity_reason = None

            completed_configuration = {
                **request_configuration,
                "diagnostics": diagnostics_to_dict(timing.diagnostics),
                "selected_tempo_bpm": timing.selected_tempo_bpm,
                "estimated_tempo_bpm": timing.estimated_tempo_bpm,
                "tempo_source": timing.tempo_source,
                "measure_origin_seconds": timing.measure_origin_seconds,
                "measure_origin_source": timing.measure_origin_source,
                "meter_source": timing.meter_source,
            }
            self.stage_runner.commit_success(
                project=project,
                run=run,
                configuration=completed_configuration,
                project_update=update(Project)
                .where(
                    Project.id == project.id,
                    Project.quantization_revision == expected_revision,
                    Project.interpretation_revision == expected_interpretation_revision,
                )
                .values(
                    estimated_tempo_bpm=timing.estimated_tempo_bpm,
                    selected_tempo_bpm=timing.selected_tempo_bpm,
                    tempo_source=TempoSource(timing.tempo_source),
                    measure_origin_seconds=timing.measure_origin_seconds,
                    measure_origin_source=SettingSource(timing.measure_origin_source),
                    meter_numerator=timing.meter_numerator,
                    meter_denominator=timing.meter_denominator,
                    meter_source=SettingSource(timing.meter_source),
                    current_quantization_run_id=run.id,
                    quantization_revision=expected_revision + 1,
                    current_interpretation_run_id=None,
                    interpretation_revision=expected_interpretation_revision + 1,
                    updated_at=utc_now(),
                ),
                conflict_error=PianovaError(
                    "quantization_conflict",
                    "This project was quantized by another request. Retry with the latest result.",
                    409,
                ),
            )
            return QuantizationResult(
                run=run,
                notes=notes,
                positions=positions,
                diagnostics=timing.diagnostics,
                provenance=completed_configuration,
                reused=False,
            )
        except TimingAnalysisError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise PianovaError(error.code, error.message, 422, error.details) from error
        except PianovaError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise
        except Exception as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, "Quantization failed.")
            logger.exception("Quantization failed for project %s", project.id)
            raise PianovaError(
                "quantization_failed",
                "The raw note events could not be quantized.",
                500,
            ) from error

    def _reuse_current(
        self,
        project: Project,
        notes: tuple[NoteEvent, ...],
        request_configuration: dict[str, object],
    ) -> QuantizationResult | None:
        if project.current_quantization_run_id is None:
            return None
        run = self.session.get(ProcessingRun, project.current_quantization_run_id)
        if (
            run is None
            or run.project_id != project.id
            or run.stage != PROCESSING_STAGE
            or run.status is not ProcessingStatus.SUCCEEDED
        ):
            return None
        try:
            stored = json.loads(run.configuration_json or "{}")
        except json.JSONDecodeError:
            return None
        if any(stored.get(key) != value for key, value in request_configuration.items()):
            return None
        if (
            project.meter_numerator is None
            or project.meter_denominator is None
            or any(
                note.symbolic_start_beats is None
                or note.symbolic_duration_beats is None
                or note.chord_group is None
                for note in notes
            )
        ):
            return None
        diagnostics_payload = stored.get("diagnostics")
        if not isinstance(diagnostics_payload, dict):
            return None
        try:
            diagnostics = TempoDiagnostics(**diagnostics_payload)
        except TypeError:
            return None
        positions = {
            note.id: self._stored_position(
                note,
                meter_numerator=project.meter_numerator,
                meter_denominator=project.meter_denominator,
            )
            for note in notes
        }
        return QuantizationResult(
            run=run,
            notes=notes,
            positions=positions,
            diagnostics=diagnostics,
            provenance=stored,
            reused=True,
        )

    def _stored_position(
        self,
        note: NoteEvent,
        *,
        meter_numerator: int,
        meter_denominator: int,
    ) -> QuantizedTimingNote:
        if (
            note.symbolic_start_beats is None
            or note.symbolic_duration_beats is None
            or note.chord_group is None
        ):
            raise PianovaError(
                "incomplete_quantization",
                "Stored quantization is incomplete.",
                500,
            )
        start = Fraction(str(note.symbolic_start_beats))
        measure_number, beat_in_measure = measure_position(
            start, meter_numerator, meter_denominator
        )
        return QuantizedTimingNote(
            note_id=note.id,
            chord_group=note.chord_group,
            symbolic_start_beats=start,
            symbolic_duration_beats=Fraction(str(note.symbolic_duration_beats)),
            measure_number=measure_number,
            beat_in_measure=beat_in_measure,
        )

    def _request_configuration(
        self,
        request: QuantizationRequest,
        *,
        fingerprint: str,
        meter_numerator: int,
        meter_denominator: int,
    ) -> dict[str, object]:
        timing = self._timing_settings()
        return {
            "processor_name": PROCESSOR_NAME,
            "processor_version": self.settings.quantization_algorithm_version,
            "runtime": f"{PROCESSOR_RUNTIME} {platform.python_version()}",
            "input_fingerprint": fingerprint,
            "tempo_override_bpm": request.tempo_bpm,
            "meter_numerator": meter_numerator,
            "meter_denominator": meter_denominator,
            "measure_origin_override_seconds": request.measure_origin_seconds,
            "minimum_bpm": timing.minimum_bpm,
            "maximum_bpm": timing.maximum_bpm,
            "chord_tolerance_seconds": timing.chord_tolerance_seconds,
            "minimum_grid_beats": float(timing.minimum_grid),
            "minimum_tempo_groups": timing.minimum_tempo_groups,
            "minimum_tempo_span_seconds": timing.minimum_tempo_span_seconds,
            "maximum_residual": timing.maximum_residual,
            "minimum_inlier_coverage": timing.minimum_inlier_coverage,
            "inlier_residual": timing.inlier_residual,
            "distinct_tempo_ratio": timing.distinct_tempo_ratio,
            "ambiguity_margin": timing.ambiguity_margin,
            "octave_ambiguity_margin": timing.octave_ambiguity_margin,
            "rest_tolerance_beats": float(timing.rest_tolerance_beats),
            "same_pitch_repair_tolerance_beats": float(timing.same_pitch_repair_tolerance_beats),
        }

    def _timing_settings(self) -> TimingSettings:
        return TimingSettings(
            minimum_bpm=self.settings.quantization_minimum_bpm,
            maximum_bpm=self.settings.quantization_maximum_bpm,
            chord_tolerance_seconds=self.settings.quantization_chord_tolerance_ms / 1000,
            minimum_grid=Fraction(str(self.settings.quantization_minimum_grid_beats)),
            minimum_tempo_groups=self.settings.quantization_minimum_tempo_groups,
            minimum_tempo_span_seconds=(self.settings.quantization_minimum_tempo_span_seconds),
            maximum_residual=self.settings.quantization_maximum_residual,
            minimum_inlier_coverage=(self.settings.quantization_minimum_inlier_coverage),
            inlier_residual=self.settings.quantization_inlier_residual,
            distinct_tempo_ratio=self.settings.quantization_distinct_tempo_ratio,
            ambiguity_margin=self.settings.quantization_ambiguity_margin,
            octave_ambiguity_margin=(self.settings.quantization_octave_ambiguity_margin),
            rest_tolerance_beats=Fraction(str(self.settings.quantization_rest_tolerance_beats)),
            same_pitch_repair_tolerance_beats=Fraction(
                str(self.settings.quantization_same_pitch_repair_tolerance_beats)
            ),
        )

    def _has_transcription_artifact(self, project_id: str) -> bool:
        return (
            self.session.scalar(
                select(Artifact.id).where(
                    Artifact.project_id == project_id,
                    Artifact.kind == ArtifactKind.NOTE_EVENTS,
                )
            )
            is not None
        )
