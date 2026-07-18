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
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    Staff,
    VoiceAmbiguityReason,
    utc_now,
)
from app.services.stage_runner import StageRunner
from app.symbolic.voices import (
    VoiceDiagnostics,
    VoicedNote,
    VoiceNote,
    VoiceSeparationError,
    VoiceSettings,
    VoiceValue,
    separate_voices,
)

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "voice_separation"
INTERPRETATION_STAGE = "interpretation"
PROCESSOR_NAME = "pianova_notation_voice_separation"


@dataclass(frozen=True, slots=True)
class VoiceServiceResult:
    run: ProcessingRun
    notes: tuple[NoteEvent, ...]
    assignments: dict[int, VoicedNote]
    diagnostics: VoiceDiagnostics
    provenance: dict[str, object]
    reused: bool


class VoiceService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.stage_runner = StageRunner(session, stage=PROCESSING_STAGE, logger=logger)

    def separate(self, project: Project) -> VoiceServiceResult:
        interpretation_run_id = project.current_interpretation_run_id
        if interpretation_run_id is None:
            raise PianovaError(
                "interpretation_required",
                "Assign hands and staves before separating notation voices.",
                409,
            )
        interpretation_run = self.session.get(ProcessingRun, interpretation_run_id)
        if (
            interpretation_run is None
            or interpretation_run.project_id != project.id
            or interpretation_run.stage != INTERPRETATION_STAGE
            or interpretation_run.status is not ProcessingStatus.SUCCEEDED
        ):
            raise PianovaError(
                "interpretation_required",
                "Separate voices only after a current successful hand/staff interpretation.",
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
        voice_notes = self._voice_notes(notes)
        configuration = self._configuration(
            interpretation_run_id=interpretation_run_id,
            interpretation_revision=project.interpretation_revision,
            voice_revision=project.voice_revision,
            notes=voice_notes,
        )
        reused = self._reuse(project, notes, configuration)
        if reused is not None:
            return reused

        expected_voice_revision = project.voice_revision
        expected_interpretation_revision = project.interpretation_revision
        expected_interpretation_run_id = interpretation_run_id
        run = self.stage_runner.precommit_run(
            project_id=project.id,
            configuration=configuration,
        )
        try:
            separated = separate_voices(voice_notes, self._settings())
            assignments = {item.note_id: item for item in separated.notes}
            self._validate_assignments(notes, assignments)
            for note in notes:
                assignment = assignments[note.id]
                note.voice = assignment.voice
                note.voice_confidence = assignment.voice_confidence
                note.voice_ambiguity_reason = (
                    VoiceAmbiguityReason(assignment.voice_ambiguity_reason)
                    if assignment.voice_ambiguity_reason
                    else None
                )
            completed = {
                **configuration,
                "diagnostics": _diagnostics_dict(separated.diagnostics),
            }
            self.stage_runner.commit_success(
                project=project,
                run=run,
                configuration=completed,
                project_update=update(Project)
                .where(
                    Project.id == project.id,
                    Project.voice_revision == expected_voice_revision,
                    Project.interpretation_revision == expected_interpretation_revision,
                    Project.current_interpretation_run_id == expected_interpretation_run_id,
                )
                .values(
                    current_voice_run_id=run.id,
                    voice_revision=Project.voice_revision + 1,
                    updated_at=utc_now(),
                ),
                conflict_error=PianovaError(
                    "voice_separation_conflict",
                    "The hand/staff interpretation changed during voice separation. "
                    "Retry the latest result.",
                    409,
                ),
            )
            return VoiceServiceResult(
                run=run,
                notes=notes,
                assignments=assignments,
                diagnostics=separated.diagnostics,
                provenance=completed,
                reused=False,
            )
        except VoiceSeparationError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            status_code = 409 if error.code == "incomplete_interpretation" else 422
            raise PianovaError(error.code, error.message, status_code, error.details) from error
        except PianovaError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise
        except Exception as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, "Voice separation failed.")
            logger.exception("Voice separation failed for project %s", project.id)
            raise PianovaError(
                "voice_separation_failed",
                "Notation voices could not be separated.",
                500,
            ) from error

    def _voice_notes(self, notes: tuple[NoteEvent, ...]) -> tuple[VoiceNote, ...]:
        if not notes:
            raise PianovaError(
                "incomplete_interpretation",
                "The current hand/staff interpretation has no notes. Interpret again.",
                409,
            )
        result: list[VoiceNote] = []
        for note in notes:
            if (
                note.symbolic_start_beats is None
                or note.symbolic_duration_beats is None
                or note.chord_group is None
                or note.hand_confidence is None
                or note.staff_confidence is None
                or not self._valid_interpretation_dimension(
                    note.hand.value,
                    note.hand_confidence,
                    note.hand_ambiguity_reason is not None,
                )
                or not self._valid_interpretation_dimension(
                    note.staff.value,
                    note.staff_confidence,
                    note.staff_ambiguity_reason is not None,
                )
            ):
                raise PianovaError(
                    "incomplete_interpretation",
                    "The current hand/staff interpretation is incomplete. Interpret again.",
                    409,
                )
            result.append(
                VoiceNote(
                    id=note.id,
                    pitch=note.pitch,
                    symbolic_start_beats=Fraction(str(note.symbolic_start_beats)),
                    symbolic_duration_beats=Fraction(str(note.symbolic_duration_beats)),
                    staff=note.staff.value,
                )
            )
        return tuple(result)

    @staticmethod
    def _valid_interpretation_dimension(
        value: str,
        confidence: float,
        has_reason: bool,
    ) -> bool:
        return (
            math.isfinite(confidence)
            and 0 <= confidence <= 1
            and ((value == "unknown") == has_reason)
        )

    def _configuration(
        self,
        *,
        interpretation_run_id: int,
        interpretation_revision: int,
        voice_revision: int,
        notes: tuple[VoiceNote, ...],
    ) -> dict[str, object]:
        payload = [
            [
                note.id,
                note.pitch,
                str(note.symbolic_start_beats),
                str(note.symbolic_duration_beats),
                note.staff,
            ]
            for note in notes
        ]
        fingerprint = hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode()
        ).hexdigest()
        voice_settings = self._settings()
        return {
            "processor_name": PROCESSOR_NAME,
            "processor_version": self.settings.voice_algorithm_version,
            "runtime": f"python {platform.python_version()}",
            "interpretation_run_id": interpretation_run_id,
            "input_interpretation_revision": interpretation_revision,
            "input_voice_revision": voice_revision,
            "input_fingerprint": fingerprint,
            "settings": {
                field: getattr(voice_settings, field)
                for field in VoiceSettings.__dataclass_fields__
            },
        }

    def _settings(self) -> VoiceSettings:
        return VoiceSettings(
            close_separation_semitones=self.settings.voice_close_separation_semitones,
            high_separation_semitones=self.settings.voice_high_separation_semitones,
        )

    def _reuse(
        self,
        project: Project,
        notes: tuple[NoteEvent, ...],
        configuration: dict[str, object],
    ) -> VoiceServiceResult | None:
        if project.current_voice_run_id is None:
            return None
        run = self.session.get(ProcessingRun, project.current_voice_run_id)
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
        if not isinstance(stored, dict) or project.voice_revision <= 0:
            return None
        expected_configuration = {
            **configuration,
            "input_voice_revision": project.voice_revision - 1,
        }
        if any(stored.get(key) != value for key, value in expected_configuration.items()):
            return None
        diagnostics_payload = stored.get("diagnostics")
        if not isinstance(diagnostics_payload, dict):
            return None
        try:
            diagnostics = VoiceDiagnostics(**diagnostics_payload)
        except (TypeError, ValueError):
            return None
        assignments = self._stored_assignments(notes)
        if assignments is None or not self._valid_diagnostics(diagnostics, notes, assignments):
            return None
        try:
            self._validate_assignments(notes, assignments)
        except PianovaError:
            return None
        return VoiceServiceResult(
            run=run,
            notes=notes,
            assignments=assignments,
            diagnostics=diagnostics,
            provenance=stored,
            reused=True,
        )

    @staticmethod
    def _stored_assignments(
        notes: tuple[NoteEvent, ...],
    ) -> dict[int, VoicedNote] | None:
        assignments: dict[int, VoicedNote] = {}
        for note in notes:
            confidence = note.voice_confidence
            reason = note.voice_ambiguity_reason
            if confidence is None:
                return None
            stored_voice: VoiceValue | None
            if note.voice == 1:
                stored_voice = 1
            elif note.voice == 2:
                stored_voice = 2
            elif note.voice is None:
                stored_voice = None
            else:
                return None
            assignments[note.id] = VoicedNote(
                note_id=note.id,
                voice=stored_voice,
                voice_confidence=confidence,
                voice_ambiguity_reason=reason.value if reason else None,
            )
        return assignments

    def _validate_assignments(
        self,
        notes: tuple[NoteEvent, ...],
        assignments: dict[int, VoicedNote],
    ) -> None:
        if set(assignments) != {note.id for note in notes}:
            raise PianovaError(
                "voice_separation_result_invalid",
                "Voice separation returned an incomplete note assignment.",
                500,
            )
        by_id = {note.id: note for note in notes}
        for note_id, assignment in assignments.items():
            note = by_id[note_id]
            if assignment.note_id != note_id or (assignment.voice is None) != (
                assignment.voice_ambiguity_reason is not None
            ):
                raise PianovaError(
                    "voice_separation_result_invalid",
                    "Voice separation returned inconsistent ambiguity metadata.",
                    500,
                )
            if assignment.voice not in {None, 1, 2} or not (
                math.isfinite(assignment.voice_confidence) and 0 <= assignment.voice_confidence <= 1
            ):
                raise PianovaError(
                    "voice_separation_result_invalid",
                    "Voice separation returned an invalid voice or decision score.",
                    500,
                )
            if note.staff is Staff.UNKNOWN:
                if assignment.voice_ambiguity_reason != "unresolved_staff":
                    raise PianovaError(
                        "voice_separation_result_invalid",
                        "An unresolved staff must produce an unresolved voice.",
                        500,
                    )
            elif assignment.voice_ambiguity_reason == "unresolved_staff":
                raise PianovaError(
                    "voice_separation_result_invalid",
                    "A resolved staff cannot produce an unresolved-staff voice reason.",
                    500,
                )
        self._validate_voice_invariant(notes, assignments)

    @staticmethod
    def _validate_voice_invariant(
        notes: tuple[NoteEvent, ...],
        assignments: dict[int, VoicedNote],
    ) -> None:
        for index, first in enumerate(notes):
            first_voice = assignments[first.id].voice
            if first_voice is None or first.symbolic_start_beats is None:
                continue
            for second in notes[index + 1 :]:
                if (
                    assignments[second.id].voice != first_voice
                    or second.staff is not first.staff
                    or second.symbolic_start_beats is None
                    or first.symbolic_duration_beats is None
                    or second.symbolic_duration_beats is None
                ):
                    continue
                first_start = Fraction(str(first.symbolic_start_beats))
                second_start = Fraction(str(second.symbolic_start_beats))
                first_duration = Fraction(str(first.symbolic_duration_beats))
                second_duration = Fraction(str(second.symbolic_duration_beats))
                overlaps = (
                    first_start < second_start + second_duration
                    and second_start < first_start + first_duration
                )
                same_chord = first_start == second_start and first_duration == second_duration
                if overlaps and not same_chord:
                    raise PianovaError(
                        "voice_separation_result_invalid",
                        "Stored notation voices violate the overlap invariant.",
                        500,
                    )

    @staticmethod
    def _valid_diagnostics(
        diagnostics: VoiceDiagnostics,
        notes: tuple[NoteEvent, ...],
        assignments: dict[int, VoicedNote],
    ) -> bool:
        values = [getattr(diagnostics, field) for field in VoiceDiagnostics.__dataclass_fields__]
        return (
            all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            )
            and diagnostics.treble_note_count == sum(note.staff is Staff.TREBLE for note in notes)
            and diagnostics.bass_note_count == sum(note.staff is Staff.BASS for note in notes)
            and diagnostics.unresolved_staff_count
            == sum(note.staff is Staff.UNKNOWN for note in notes)
            and diagnostics.resolved_count
            == sum(assignment.voice is not None for assignment in assignments.values())
            and diagnostics.unknown_count
            == sum(assignment.voice is None for assignment in assignments.values())
            and diagnostics.capacity_exceeded_count
            == sum(
                assignment.voice_ambiguity_reason == "voice_capacity_exceeded"
                for assignment in assignments.values()
            )
            and diagnostics.crossing_component_count <= diagnostics.two_voice_component_count
            and diagnostics.conflict_component_count <= diagnostics.chord_node_count
            and diagnostics.two_voice_component_count <= diagnostics.chord_node_count
            and diagnostics.resolved_count + diagnostics.unknown_count == len(notes)
        )


def _diagnostics_dict(diagnostics: VoiceDiagnostics) -> dict[str, int]:
    return {
        field: int(getattr(diagnostics, field)) for field in VoiceDiagnostics.__dataclass_fields__
    }
