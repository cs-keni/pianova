import hashlib
import json
import logging
import math
import platform
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import PianovaError
from app.models.entities import (
    KeyAmbiguityReason,
    KeyMode,
    KeySource,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    SpellingAmbiguityReason,
    Staff,
    VoiceAmbiguityReason,
    utc_now,
)
from app.schemas.api import SpellingRequest
from app.services.spelling_state import clear_spelling_note_state
from app.services.stage_runner import StageRunner
from app.symbolic.spelling import (
    KeyEstimate,
    KeyModeValue,
    KeyName,
    KeyOverride,
    KeySourceValue,
    SpelledNote,
    SpellingDiagnostics,
    SpellingError,
    SpellingNote,
    SpellingSettings,
    StepValue,
    key_signature_fifths,
    midi_pitch_for_spelling,
    spell_notes,
)

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "pitch_spelling"
VOICE_STAGE = "voice_separation"
PROCESSOR_NAME = "pianova_key_pitch_spelling"


@dataclass(frozen=True, slots=True)
class SpellingServiceResult:
    run: ProcessingRun
    notes: tuple[NoteEvent, ...]
    spellings: dict[int, SpelledNote]
    key: KeyEstimate
    diagnostics: SpellingDiagnostics
    provenance: dict[str, object]
    reused: bool


class SpellingService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.stage_runner = StageRunner(session, stage=PROCESSING_STAGE, logger=logger)

    def spell(self, project: Project, request: SpellingRequest) -> SpellingServiceResult:
        voice_run_id = project.current_voice_run_id
        if voice_run_id is None:
            raise PianovaError(
                "voice_separation_required",
                "Separate notation voices before detecting the key and spelling notes.",
                409,
            )
        voice_run = self.session.get(ProcessingRun, voice_run_id)
        if (
            voice_run is None
            or voice_run.project_id != project.id
            or voice_run.stage != VOICE_STAGE
            or voice_run.status is not ProcessingStatus.SUCCEEDED
        ):
            raise PianovaError(
                "voice_separation_required",
                "Spell notes only after a current successful notation-voice separation.",
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
        spelling_notes = self._spelling_notes(notes)
        key_override = self._key_override(request)
        configuration = self._configuration(
            voice_run_id=voice_run_id,
            voice_revision=project.voice_revision,
            spelling_revision=project.spelling_revision,
            notes=spelling_notes,
            key_override=key_override,
        )
        reused = self._reuse(project, notes, configuration)
        if reused is not None:
            return reused

        expected_voice_run_id = voice_run_id
        expected_voice_revision = project.voice_revision
        expected_spelling_revision = project.spelling_revision
        run = self.stage_runner.precommit_run(
            project_id=project.id,
            configuration=configuration,
        )
        try:
            result = spell_notes(
                spelling_notes,
                self._settings(),
                key_override=key_override,
            )
            spellings = {item.note_id: item for item in result.notes}
            self._validate_result(notes, result.key, spellings, result.diagnostics)
            clear_spelling_note_state(self.session, project.id)
            for note in notes:
                spelling = spellings[note.id]
                note.spelled_step = spelling.step
                note.spelled_alter = spelling.alter
                note.spelled_octave = spelling.octave
                note.spelling_confidence = spelling.spelling_confidence
                note.spelling_ambiguity_reason = (
                    SpellingAmbiguityReason(spelling.spelling_ambiguity_reason)
                    if spelling.spelling_ambiguity_reason
                    else None
                )

            completed = {
                **configuration,
                "key": _key_dict(result.key),
                "diagnostics": _diagnostics_dict(result.diagnostics),
            }
            project_values = self._project_key_values(result.key)
            self.stage_runner.commit_success(
                project=project,
                run=run,
                configuration=completed,
                project_update=update(Project)
                .where(
                    Project.id == project.id,
                    Project.current_voice_run_id == expected_voice_run_id,
                    Project.voice_revision == expected_voice_revision,
                    Project.spelling_revision == expected_spelling_revision,
                )
                .values(
                    **project_values,
                    current_spelling_run_id=run.id,
                    spelling_revision=Project.spelling_revision + 1,
                    updated_at=utc_now(),
                ),
                conflict_error=PianovaError(
                    "spelling_conflict",
                    "The notation voices changed during pitch spelling. Retry the latest result.",
                    409,
                ),
            )
            return SpellingServiceResult(
                run=run,
                notes=notes,
                spellings=spellings,
                key=result.key,
                diagnostics=result.diagnostics,
                provenance=completed,
                reused=False,
            )
        except SpellingError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            status_code = 422 if error.code == "invalid_key_override" else 409
            raise PianovaError(error.code, error.message, status_code, error.details) from error
        except PianovaError as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, error.message)
            raise
        except Exception as error:
            self.session.rollback()
            self.stage_runner.mark_failed(run.id, "Pitch spelling failed.")
            logger.exception("Pitch spelling failed for project %s", project.id)
            raise PianovaError(
                "spelling_failed",
                "The project key and written pitches could not be produced.",
                500,
            ) from error

    def _spelling_notes(self, notes: tuple[NoteEvent, ...]) -> tuple[SpellingNote, ...]:
        if not notes:
            raise PianovaError(
                "incomplete_voice_state",
                "The current notation-voice result has no notes. Separate voices again.",
                409,
            )
        result: list[SpellingNote] = []
        for note in notes:
            confidence = note.voice_confidence
            reason = note.voice_ambiguity_reason
            has_resolved_voice = note.voice is not None
            if (
                note.symbolic_start_beats is None
                or not math.isfinite(note.symbolic_start_beats)
                or note.symbolic_duration_beats is None
                or not math.isfinite(note.symbolic_duration_beats)
                or note.symbolic_duration_beats <= 0
                or note.chord_group is None
                or note.chord_group <= 0
                or confidence is None
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
                or has_resolved_voice == (reason is not None)
                or has_resolved_voice
                and note.voice not in {1, 2}
                or note.staff is Staff.UNKNOWN
                and (note.voice is not None or reason is not VoiceAmbiguityReason.UNRESOLVED_STAFF)
                or note.staff is not Staff.UNKNOWN
                and reason is VoiceAmbiguityReason.UNRESOLVED_STAFF
            ):
                raise PianovaError(
                    "incomplete_voice_state",
                    "The current notation-voice state is incomplete. Separate voices again.",
                    409,
                )
            result.append(
                SpellingNote(
                    id=note.id,
                    pitch=note.pitch,
                    symbolic_start_beats=note.symbolic_start_beats,
                    symbolic_duration_beats=note.symbolic_duration_beats,
                    chord_group=note.chord_group,
                    staff=note.staff.value,
                    voice=note.voice,
                )
            )
        return tuple(result)

    @staticmethod
    def _key_override(request: SpellingRequest) -> KeyOverride | None:
        payload = request.key_override
        if payload is None:
            return None
        return KeyOverride(
            tonic_step=payload.tonic_step,
            tonic_alter=payload.tonic_alter,
            mode=payload.mode.value,
        )

    def _configuration(
        self,
        *,
        voice_run_id: int,
        voice_revision: int,
        spelling_revision: int,
        notes: tuple[SpellingNote, ...],
        key_override: KeyOverride | None,
    ) -> dict[str, object]:
        payload = [
            [
                note.id,
                note.pitch,
                note.symbolic_start_beats,
                note.symbolic_duration_beats,
                note.chord_group,
                note.staff,
                note.voice,
            ]
            for note in notes
        ]
        fingerprint = hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        spelling_settings = self._settings()
        return {
            "processor_name": PROCESSOR_NAME,
            "processor_version": self.settings.spelling_algorithm_version,
            "runtime": f"python {platform.python_version()}",
            "voice_run_id": voice_run_id,
            "input_voice_revision": voice_revision,
            "input_spelling_revision": spelling_revision,
            "input_fingerprint": fingerprint,
            "key_override": (
                {
                    "tonic_step": key_override.tonic_step,
                    "tonic_alter": key_override.tonic_alter,
                    "mode": key_override.mode,
                }
                if key_override
                else None
            ),
            "settings": {
                field: getattr(spelling_settings, field)
                for field in SpellingSettings.__dataclass_fields__
            },
        }

    def _settings(self) -> SpellingSettings:
        return SpellingSettings(
            key_minimum_notes=self.settings.spelling_key_minimum_notes,
            key_minimum_distinct_pitch_classes=(
                self.settings.spelling_key_minimum_distinct_pitch_classes
            ),
            key_ambiguity_margin=self.settings.spelling_key_ambiguity_margin,
            spelling_close_margin=self.settings.spelling_close_margin,
        )

    def _reuse(
        self,
        project: Project,
        notes: tuple[NoteEvent, ...],
        configuration: dict[str, object],
    ) -> SpellingServiceResult | None:
        run_id = project.current_spelling_run_id
        if run_id is None:
            return None
        run = self.session.get(ProcessingRun, run_id)
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
        if not isinstance(stored, dict) or project.spelling_revision <= 0:
            return None
        expected_configuration = {
            **configuration,
            "input_spelling_revision": project.spelling_revision - 1,
        }
        if any(stored.get(key) != value for key, value in expected_configuration.items()):
            return None
        key = self._stored_key(project)
        if key is None or stored.get("key") != _key_dict(key):
            return None
        diagnostics_payload = stored.get("diagnostics")
        diagnostics = _diagnostics_from_payload(diagnostics_payload)
        if diagnostics is None:
            return None
        spellings = self._stored_spellings(notes)
        if spellings is None:
            return None
        try:
            self._validate_result(notes, key, spellings, diagnostics)
        except PianovaError:
            return None
        return SpellingServiceResult(
            run=run,
            notes=notes,
            spellings=spellings,
            key=key,
            diagnostics=diagnostics,
            provenance=stored,
            reused=True,
        )

    @staticmethod
    def _stored_key(project: Project) -> KeyEstimate | None:
        source = project.key_source
        if source is None:
            return None
        confidence = project.key_confidence
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            return None
        if project.key_tonic_step is None:
            if (
                source is not KeySource.ESTIMATED
                or project.key_tonic_alter is not None
                or project.key_mode is not None
                or confidence is None
                or project.key_ambiguity_reason is None
            ):
                return None
            return KeyEstimate(
                None,
                None,
                None,
                confidence,
                project.key_ambiguity_reason.value,
                cast(KeySourceValue, source.value),
            )
        if (
            project.key_tonic_alter is None
            or project.key_mode is None
            or project.key_ambiguity_reason is not None
            or source is KeySource.ESTIMATED
            and confidence is None
            or source is KeySource.OVERRIDE
            and confidence is not None
        ):
            return None
        step = cast(StepValue, project.key_tonic_step)
        mode: KeyModeValue = project.key_mode.value
        try:
            key_signature_fifths(KeyName(step, project.key_tonic_alter, mode))
        except ValueError:
            return None
        return KeyEstimate(
            step,
            project.key_tonic_alter,
            mode,
            confidence,
            None,
            source.value,
        )

    @staticmethod
    def _stored_spellings(
        notes: tuple[NoteEvent, ...],
    ) -> dict[int, SpelledNote] | None:
        spellings: dict[int, SpelledNote] = {}
        for note in notes:
            confidence = note.spelling_confidence
            if confidence is None:
                return None
            reason = note.spelling_ambiguity_reason
            step = cast(StepValue | None, note.spelled_step)
            spelling = SpelledNote(
                note_id=note.id,
                step=step,
                alter=note.spelled_alter,
                octave=note.spelled_octave,
                spelling_confidence=confidence,
                spelling_ambiguity_reason=reason.value if reason else None,
            )
            spellings[note.id] = spelling
        return spellings

    def _validate_result(
        self,
        notes: tuple[NoteEvent, ...],
        key: KeyEstimate,
        spellings: dict[int, SpelledNote],
        diagnostics: SpellingDiagnostics,
    ) -> None:
        if set(spellings) != {note.id for note in notes}:
            raise PianovaError(
                "spelling_result_invalid",
                "Pitch spelling returned an incomplete note result.",
                500,
            )
        self._validate_key(key)
        notes_by_id = {note.id: note for note in notes}
        for note_id, spelling in spellings.items():
            note = notes_by_id[note_id]
            confidence = spelling.spelling_confidence
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise PianovaError(
                    "spelling_result_invalid",
                    "Pitch spelling returned an invalid decision score.",
                    500,
                )
            if spelling.step is None:
                if (
                    spelling.alter is not None
                    or spelling.octave is not None
                    or spelling.spelling_ambiguity_reason
                    not in {"unknown_key", "close_alternative"}
                ):
                    raise PianovaError(
                        "spelling_result_invalid",
                        "Pitch spelling returned inconsistent ambiguity metadata.",
                        500,
                    )
            elif (
                spelling.step not in {"A", "B", "C", "D", "E", "F", "G"}
                or spelling.alter is None
                or spelling.octave is None
                or spelling.spelling_ambiguity_reason is not None
                or not -2 <= spelling.alter <= 2
                or not -2 <= spelling.octave <= 9
                or midi_pitch_for_spelling(
                    spelling.step,
                    spelling.alter,
                    spelling.octave,
                )
                != note.pitch
            ):
                raise PianovaError(
                    "spelling_result_invalid",
                    "A written spelling does not map back to its unchanged MIDI pitch.",
                    500,
                )
        if not self._valid_diagnostics(diagnostics, notes, spellings):
            raise PianovaError(
                "spelling_result_invalid",
                "Pitch spelling returned inconsistent diagnostics.",
                500,
            )

    @staticmethod
    def _validate_key(key: KeyEstimate) -> None:
        confidence = key.confidence
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise PianovaError(
                "spelling_result_invalid",
                "Key detection returned an invalid decision score.",
                500,
            )
        if key.tonic_step is None:
            valid = (
                key.source == "estimated"
                and key.tonic_alter is None
                and key.mode is None
                and confidence is not None
                and key.ambiguity_reason in {"insufficient_notes", "ambiguous_key"}
            )
        else:
            valid = (
                key.tonic_alter is not None
                and key.mode is not None
                and key.ambiguity_reason is None
                and (
                    key.source == "estimated"
                    and confidence is not None
                    or key.source == "override"
                    and confidence is None
                )
            )
            if valid:
                try:
                    key_signature_fifths(
                        KeyName(key.tonic_step, key.tonic_alter, key.mode)  # type: ignore[arg-type]
                    )
                except ValueError:
                    valid = False
        if not valid:
            raise PianovaError(
                "spelling_result_invalid",
                "Key detection returned inconsistent key metadata.",
                500,
            )

    @staticmethod
    def _valid_diagnostics(
        diagnostics: SpellingDiagnostics,
        notes: tuple[NoteEvent, ...],
        spellings: dict[int, SpelledNote],
    ) -> bool:
        integer_fields = (
            diagnostics.chord_consistency_application_count,
            diagnostics.melodic_rule_application_count,
            diagnostics.resolved_count,
            diagnostics.unknown_count,
            diagnostics.unknown_key_count,
            diagnostics.close_alternative_count,
        )
        correlations = (
            diagnostics.best_key_correlation,
            diagnostics.runner_up_key_correlation,
        )
        return (
            len(diagnostics.pitch_class_histogram) == 12
            and all(
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
                for value in diagnostics.pitch_class_histogram
            )
            and len(diagnostics.candidate_set_sizes) == len(notes)
            and all(
                isinstance(value, int) and not isinstance(value, bool) and value in {1, 2}
                for value in diagnostics.candidate_set_sizes
            )
            and all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in integer_fields
            )
            and math.isfinite(diagnostics.key_correlation_margin)
            and 0 <= diagnostics.key_correlation_margin <= 1
            and all(
                value is None or isinstance(value, float) and math.isfinite(value)
                for value in correlations
            )
            and (diagnostics.best_key is None) == (diagnostics.best_key_correlation is None)
            and (diagnostics.runner_up_key is None)
            == (diagnostics.runner_up_key_correlation is None)
            and all(isinstance(value, str) and value for value in diagnostics.plausible_keys)
            and diagnostics.resolved_count
            == sum(spelling.step is not None for spelling in spellings.values())
            and diagnostics.unknown_count
            == sum(spelling.step is None for spelling in spellings.values())
            and diagnostics.unknown_key_count
            == sum(
                spelling.spelling_ambiguity_reason == "unknown_key"
                for spelling in spellings.values()
            )
            and diagnostics.close_alternative_count
            == sum(
                spelling.spelling_ambiguity_reason == "close_alternative"
                for spelling in spellings.values()
            )
            and diagnostics.resolved_count + diagnostics.unknown_count == len(notes)
            and diagnostics.unknown_key_count + diagnostics.close_alternative_count
            == diagnostics.unknown_count
            and diagnostics.chord_consistency_application_count <= len(notes)
            and diagnostics.melodic_rule_application_count <= len(notes)
        )

    @staticmethod
    def _project_key_values(key: KeyEstimate) -> dict[str, object]:
        return {
            "key_tonic_step": key.tonic_step,
            "key_tonic_alter": key.tonic_alter,
            "key_mode": KeyMode(key.mode) if key.mode else None,
            "key_confidence": key.confidence,
            "key_ambiguity_reason": (
                KeyAmbiguityReason(key.ambiguity_reason) if key.ambiguity_reason else None
            ),
            "key_source": KeySource(key.source),
        }


def _key_dict(key: KeyEstimate) -> dict[str, object]:
    return {
        "tonic_step": key.tonic_step,
        "tonic_alter": key.tonic_alter,
        "mode": key.mode,
        "confidence": key.confidence,
        "ambiguity_reason": key.ambiguity_reason,
        "source": key.source,
    }


def _diagnostics_dict(diagnostics: SpellingDiagnostics) -> dict[str, object]:
    return {
        "pitch_class_histogram": list(diagnostics.pitch_class_histogram),
        "best_key": diagnostics.best_key,
        "best_key_correlation": diagnostics.best_key_correlation,
        "runner_up_key": diagnostics.runner_up_key,
        "runner_up_key_correlation": diagnostics.runner_up_key_correlation,
        "key_correlation_margin": diagnostics.key_correlation_margin,
        "plausible_keys": list(diagnostics.plausible_keys),
        "candidate_set_sizes": list(diagnostics.candidate_set_sizes),
        "chord_consistency_application_count": (diagnostics.chord_consistency_application_count),
        "melodic_rule_application_count": diagnostics.melodic_rule_application_count,
        "resolved_count": diagnostics.resolved_count,
        "unknown_count": diagnostics.unknown_count,
        "unknown_key_count": diagnostics.unknown_key_count,
        "close_alternative_count": diagnostics.close_alternative_count,
    }


def _diagnostics_from_payload(payload: object) -> SpellingDiagnostics | None:
    if not isinstance(payload, dict):
        return None
    try:
        histogram = payload["pitch_class_histogram"]
        plausible_keys = payload["plausible_keys"]
        candidate_sizes = payload["candidate_set_sizes"]
        if (
            not isinstance(histogram, list)
            or not isinstance(plausible_keys, list)
            or not isinstance(candidate_sizes, list)
        ):
            return None
        return SpellingDiagnostics(
            pitch_class_histogram=tuple(histogram),
            best_key=payload["best_key"],
            best_key_correlation=payload["best_key_correlation"],
            runner_up_key=payload["runner_up_key"],
            runner_up_key_correlation=payload["runner_up_key_correlation"],
            key_correlation_margin=payload["key_correlation_margin"],
            plausible_keys=tuple(plausible_keys),
            candidate_set_sizes=tuple(candidate_sizes),
            chord_consistency_application_count=payload["chord_consistency_application_count"],
            melodic_rule_application_count=payload["melodic_rule_application_count"],
            resolved_count=payload["resolved_count"],
            unknown_count=payload["unknown_count"],
            unknown_key_count=payload["unknown_key_count"],
            close_alternative_count=payload["close_alternative_count"],
        )
    except (KeyError, TypeError, ValueError):
        return None
