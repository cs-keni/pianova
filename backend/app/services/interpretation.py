import hashlib
import json
import logging
import math
import platform
from dataclasses import dataclass
from fractions import Fraction

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import PianovaError
from app.models.entities import (
    AssignmentAmbiguityReason,
    Hand,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    Staff,
    utc_now,
)
from app.services.spelling_state import (
    clear_spelling_note_state,
    spelling_project_clear_values,
)
from app.services.stage_runner import StageRunner
from app.symbolic.interpretation import (
    InterpretationDiagnostics,
    InterpretationError,
    InterpretationNote,
    InterpretationSettings,
    InterpretedNote,
    interpret_notes,
)

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "interpretation"
QUANTIZATION_STAGE = "quantization"
PROCESSOR_NAME = "pianova_hand_staff_interpretation"


@dataclass(frozen=True, slots=True)
class InterpretationServiceResult:
    run: ProcessingRun
    notes: tuple[NoteEvent, ...]
    assignments: dict[int, InterpretedNote]
    diagnostics: InterpretationDiagnostics
    provenance: dict[str, object]
    reused: bool


class InterpretationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.stage_runner = StageRunner(session, stage=PROCESSING_STAGE, logger=logger)

    def interpret(self, project: Project) -> InterpretationServiceResult:
        if project.current_quantization_run_id is None:
            raise PianovaError(
                "quantization_required",
                "Quantize the transcription before assigning hands and staves.",
                409,
            )
        quantization_run = self.session.get(
            ProcessingRun,
            project.current_quantization_run_id,
        )
        if (
            quantization_run is None
            or quantization_run.project_id != project.id
            or quantization_run.stage != QUANTIZATION_STAGE
            or quantization_run.status is not ProcessingStatus.SUCCEEDED
        ):
            raise PianovaError(
                "quantization_required",
                "Assign hands and staves only after a current successful quantization.",
                409,
            )
        notes = tuple(
            self.session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project.id)
                .order_by(
                    NoteEvent.symbolic_start_beats,
                    NoteEvent.pitch,
                    NoteEvent.id,
                )
            ).all()
        )
        symbolic_notes = self._symbolic_notes(notes)
        configuration = self._configuration(
            project.current_quantization_run_id,
            project.interpretation_revision,
            symbolic_notes,
        )
        reused = self._reuse(project, notes, configuration)
        if reused is not None:
            return reused

        expected_revision = project.interpretation_revision
        expected_quantization_run_id = project.current_quantization_run_id
        expected_voice_revision = project.voice_revision
        expected_spelling_revision = project.spelling_revision
        run = self.stage_runner.precommit_run(
            project_id=project.id,
            configuration=configuration,
        )
        try:
            interpreted = interpret_notes(symbolic_notes, self._settings())
            assignments = {item.note_id: item for item in interpreted.notes}
            self._validate_assignments(notes, assignments)
            for note in notes:
                assignment = assignments[note.id]
                note.hand = Hand(assignment.hand)
                note.staff = Staff(assignment.staff)
                note.hand_confidence = assignment.hand_confidence
                note.staff_confidence = assignment.staff_confidence
                note.hand_ambiguity_reason = (
                    AssignmentAmbiguityReason(assignment.hand_ambiguity_reason)
                    if assignment.hand_ambiguity_reason
                    else None
                )
                note.staff_ambiguity_reason = (
                    AssignmentAmbiguityReason(assignment.staff_ambiguity_reason)
                    if assignment.staff_ambiguity_reason
                    else None
                )
                note.voice = None
                note.voice_confidence = None
                note.voice_ambiguity_reason = None
            clear_spelling_note_state(self.session, project.id)
            completed = {
                **configuration,
                "diagnostics": _diagnostics_dict(interpreted.diagnostics),
            }
            self.stage_runner.commit_success(
                project=project,
                run=run,
                configuration=completed,
                project_update=update(Project)
                .where(
                    Project.id == project.id,
                    Project.interpretation_revision == expected_revision,
                    Project.current_quantization_run_id == expected_quantization_run_id,
                    Project.voice_revision == expected_voice_revision,
                    Project.spelling_revision == expected_spelling_revision,
                )
                .values(
                    current_interpretation_run_id=run.id,
                    interpretation_revision=expected_revision + 1,
                    current_voice_run_id=None,
                    voice_revision=Project.voice_revision + 1,
                    **spelling_project_clear_values(),
                    updated_at=utc_now(),
                ),
                conflict_error=PianovaError(
                    "interpretation_conflict",
                    "The project timing changed during interpretation. Retry the latest result.",
                    409,
                ),
            )
            return InterpretationServiceResult(
                run=run,
                notes=notes,
                assignments=assignments,
                diagnostics=interpreted.diagnostics,
                provenance=completed,
                reused=False,
            )
        except InterpretationError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise PianovaError(error.code, error.message, 422, error.details) from error
        except PianovaError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise
        except Exception as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, "Interpretation failed.")
            logger.exception("Interpretation failed for project %s", project.id)
            raise PianovaError(
                "interpretation_failed",
                "Hands and staves could not be assigned.",
                500,
            ) from error

    def _symbolic_notes(self, notes: tuple[NoteEvent, ...]) -> tuple[InterpretationNote, ...]:
        if not notes or any(
            note.symbolic_start_beats is None
            or note.symbolic_duration_beats is None
            or note.chord_group is None
            for note in notes
        ):
            raise PianovaError(
                "incomplete_quantization",
                "The current quantized note state is incomplete. Quantize again.",
                409,
            )
        return tuple(
            InterpretationNote(
                id=note.id,
                pitch=note.pitch,
                symbolic_start_beats=Fraction(str(note.symbolic_start_beats)),
                symbolic_duration_beats=Fraction(str(note.symbolic_duration_beats)),
                chord_group=note.chord_group,
            )
            for note in notes
            if note.chord_group is not None
        )

    def _configuration(
        self,
        quantization_run_id: int,
        interpretation_revision: int,
        notes: tuple[InterpretationNote, ...],
    ) -> dict[str, object]:
        timing = self._settings()
        payload = [
            [
                note.id,
                note.pitch,
                str(note.symbolic_start_beats),
                str(note.symbolic_duration_beats),
                note.chord_group,
            ]
            for note in notes
        ]
        fingerprint = hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "processor_name": PROCESSOR_NAME,
            "processor_version": self.settings.interpretation_algorithm_version,
            "runtime": f"python {platform.python_version()}",
            "quantization_run_id": quantization_run_id,
            "input_interpretation_revision": interpretation_revision,
            "input_fingerprint": fingerprint,
            "settings": {
                field: getattr(timing, field)
                for field in InterpretationSettings.__dataclass_fields__
            },
        }

    def _settings(self) -> InterpretationSettings:
        return InterpretationSettings(
            left_center_pitch=self.settings.interpretation_left_center_pitch,
            right_center_pitch=self.settings.interpretation_right_center_pitch,
            bass_center_pitch=self.settings.interpretation_bass_center_pitch,
            treble_center_pitch=self.settings.interpretation_treble_center_pitch,
            pitch_weight=self.settings.interpretation_pitch_weight,
            span_weight=self.settings.interpretation_span_weight,
            movement_weight=self.settings.interpretation_movement_weight,
            appearance_weight=self.settings.interpretation_appearance_weight,
            split_movement_weight=self.settings.interpretation_split_movement_weight,
            crossing_weight=self.settings.interpretation_crossing_weight,
            compact_split_weight=self.settings.interpretation_compact_split_weight,
            wide_single_partition_weight=(
                self.settings.interpretation_wide_single_partition_weight
            ),
            comfortable_hand_span=self.settings.interpretation_comfortable_hand_span,
            compact_chord_span=self.settings.interpretation_compact_chord_span,
            middle_register_low=self.settings.interpretation_middle_register_low,
            middle_register_high=self.settings.interpretation_middle_register_high,
            ambiguity_margin=self.settings.interpretation_ambiguity_margin,
            high_confidence_margin=self.settings.interpretation_high_confidence_margin,
            maximum_transition_evaluations=(
                self.settings.interpretation_maximum_transition_evaluations
            ),
        )

    def _reuse(
        self,
        project: Project,
        notes: tuple[NoteEvent, ...],
        configuration: dict[str, object],
    ) -> InterpretationServiceResult | None:
        if project.current_interpretation_run_id is None:
            return None
        run = self.session.get(ProcessingRun, project.current_interpretation_run_id)
        if (
            run is None
            or run.project_id != project.id
            or run.stage != PROCESSING_STAGE
            or run.status is not ProcessingStatus.SUCCEEDED
        ):
            return None
        try:
            stored = json.loads(run.configuration_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(stored, dict):
            return None
        expected_configuration = {
            **configuration,
            "input_interpretation_revision": project.interpretation_revision - 1,
        }
        if project.interpretation_revision <= 0 or any(
            stored.get(key) != value for key, value in expected_configuration.items()
        ):
            return None
        diagnostics_payload = stored.get("diagnostics")
        if not isinstance(diagnostics_payload, dict):
            return None
        try:
            diagnostics = InterpretationDiagnostics(**diagnostics_payload)
        except (TypeError, ValueError):
            return None
        if not self._valid_diagnostics(diagnostics, notes):
            return None
        assignments: dict[int, InterpretedNote] = {}
        for note in notes:
            if note.hand_confidence is None or note.staff_confidence is None:
                return None
            assignments[note.id] = InterpretedNote(
                note_id=note.id,
                hand=note.hand.value,
                staff=note.staff.value,
                hand_confidence=note.hand_confidence,
                staff_confidence=note.staff_confidence,
                hand_ambiguity_reason=(
                    note.hand_ambiguity_reason.value if note.hand_ambiguity_reason else None
                ),
                staff_ambiguity_reason=(
                    note.staff_ambiguity_reason.value if note.staff_ambiguity_reason else None
                ),
            )
        try:
            self._validate_assignments(notes, assignments)
        except PianovaError:
            return None
        if (
            diagnostics.resolved_hand_count
            != sum(assignment.hand != "unknown" for assignment in assignments.values())
            or diagnostics.unknown_hand_count
            != sum(assignment.hand == "unknown" for assignment in assignments.values())
            or diagnostics.resolved_staff_count
            != sum(assignment.staff != "unknown" for assignment in assignments.values())
            or diagnostics.unknown_staff_count
            != sum(assignment.staff == "unknown" for assignment in assignments.values())
        ):
            return None
        return InterpretationServiceResult(
            run=run,
            notes=notes,
            assignments=assignments,
            diagnostics=diagnostics,
            provenance=stored,
            reused=True,
        )

    def _validate_assignments(
        self,
        notes: tuple[NoteEvent, ...],
        assignments: dict[int, InterpretedNote],
    ) -> None:
        if set(assignments) != {note.id for note in notes}:
            raise PianovaError(
                "interpretation_result_invalid",
                "Interpretation returned an incomplete note assignment.",
                500,
            )
        for note in notes:
            assignment = assignments[note.id]
            if assignment.note_id != note.id:
                raise PianovaError(
                    "interpretation_result_invalid",
                    "Interpretation returned a mismatched note assignment.",
                    500,
                )
            if assignment.hand not in {"left", "right", "unknown"} or assignment.staff not in {
                "treble",
                "bass",
                "unknown",
            }:
                raise PianovaError(
                    "interpretation_result_invalid",
                    "Interpretation returned an unsupported assignment value.",
                    500,
                )
            self._validate_dimension(
                assignment.hand,
                assignment.hand_confidence,
                assignment.hand_ambiguity_reason,
            )
            self._validate_dimension(
                assignment.staff,
                assignment.staff_confidence,
                assignment.staff_ambiguity_reason,
            )

    @staticmethod
    def _validate_dimension(
        value: str,
        confidence: float,
        reason: str | None,
    ) -> None:
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise PianovaError(
                "interpretation_result_invalid",
                "Interpretation returned an invalid confidence value.",
                500,
            )
        if (value == "unknown") != (reason is not None):
            raise PianovaError(
                "interpretation_result_invalid",
                "Interpretation returned inconsistent ambiguity metadata.",
                500,
            )

    @staticmethod
    def _valid_diagnostics(
        diagnostics: InterpretationDiagnostics,
        notes: tuple[NoteEvent, ...],
    ) -> bool:
        values = [
            getattr(diagnostics, field) for field in InterpretationDiagnostics.__dataclass_fields__
        ]
        return (
            all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            )
            and diagnostics.chord_group_count == len({note.chord_group for note in notes})
            and diagnostics.wide_chord_count <= diagnostics.chord_group_count
            and diagnostics.crossing_pressure_count <= diagnostics.chord_group_count
            and diagnostics.resolved_hand_count + diagnostics.unknown_hand_count == len(notes)
            and diagnostics.resolved_staff_count + diagnostics.unknown_staff_count == len(notes)
        )


def _diagnostics_dict(diagnostics: InterpretationDiagnostics) -> dict[str, int]:
    return {
        field: int(getattr(diagnostics, field))
        for field in InterpretationDiagnostics.__dataclass_fields__
    }
