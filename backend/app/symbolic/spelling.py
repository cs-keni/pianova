"""Detect one global key and spell MIDI pitches without changing their pitch.

Processing flow::

    validated voiced notes
      -> duration-weighted pitch-class histogram
      -> minimum-evidence / centered-norm gates
      -> 24 Krumhansl-Kessler correlations (unless overridden)
      -> resolved key or typed successful unknown
      -> deterministic staff/voice/onset/pitch/id spelling pass
      -> resolved spellings or typed successful unknowns

Stored symbolic beats remain floats at this boundary. ``chord_group`` is the
persisted same-onset fact; this module never reconstructs fractions or uses
float equality to infer chords.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

StepValue = Literal["A", "B", "C", "D", "E", "F", "G"]
StaffValue = Literal["treble", "bass", "unknown"]
KeyModeValue = Literal["major", "minor"]
KeySourceValue = Literal["estimated", "override"]
KeyAmbiguityReasonValue = Literal["insufficient_notes", "ambiguous_key"]
SpellingAmbiguityReasonValue = Literal["unknown_key", "close_alternative"]

W_CHORD = 2.0
W_STEP = 1.0
SPELLING_GAP_FULL_SCALE = 12.0
HISTOGRAM_CENTERED_NORM_EPSILON = 1e-12

# Krumhansl and Kessler probe-tone profiles, ordered from tonic through B.
_MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

_NATURAL_PITCH_CLASS: dict[StepValue, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}
_NATURAL_LOF: dict[StepValue, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": -1,
    "G": 1,
    "A": 3,
    "B": 5,
}
_STEP_INDEX: dict[StepValue, int] = {
    "C": 0,
    "D": 1,
    "E": 2,
    "F": 3,
    "G": 4,
    "A": 5,
    "B": 6,
}


class SpellingError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class SpellingNote:
    id: int
    pitch: int
    symbolic_start_beats: float
    symbolic_duration_beats: float
    chord_group: int
    staff: StaffValue
    voice: int | None


@dataclass(frozen=True, slots=True)
class KeyOverride:
    tonic_step: StepValue
    tonic_alter: int
    mode: KeyModeValue


@dataclass(frozen=True, slots=True)
class SpellingSettings:
    key_minimum_notes: int = 8
    key_minimum_distinct_pitch_classes: int = 3
    key_ambiguity_margin: float = 0.05
    spelling_close_margin: float = 0.10


@dataclass(frozen=True, slots=True)
class KeyName:
    tonic_step: StepValue
    tonic_alter: int
    mode: KeyModeValue


@dataclass(frozen=True, slots=True)
class KeyEstimate:
    tonic_step: StepValue | None
    tonic_alter: int | None
    mode: KeyModeValue | None
    confidence: float | None
    ambiguity_reason: KeyAmbiguityReasonValue | None
    source: KeySourceValue


@dataclass(frozen=True, slots=True)
class SpelledNote:
    note_id: int
    step: StepValue | None
    alter: int | None
    octave: int | None
    spelling_confidence: float
    spelling_ambiguity_reason: SpellingAmbiguityReasonValue | None


@dataclass(frozen=True, slots=True)
class SpellingDiagnostics:
    pitch_class_histogram: tuple[float, ...]
    best_key: str | None
    best_key_correlation: float | None
    runner_up_key: str | None
    runner_up_key_correlation: float | None
    key_correlation_margin: float
    plausible_keys: tuple[str, ...]
    candidate_set_sizes: tuple[int, ...]
    chord_consistency_application_count: int
    melodic_rule_application_count: int
    resolved_count: int
    unknown_count: int
    unknown_key_count: int
    close_alternative_count: int


@dataclass(frozen=True, slots=True)
class SpellingResult:
    key: KeyEstimate
    notes: tuple[SpelledNote, ...]
    diagnostics: SpellingDiagnostics


@dataclass(frozen=True, slots=True)
class _PitchName:
    step: StepValue
    alter: int

    @property
    def pitch_class(self) -> int:
        return (_NATURAL_PITCH_CLASS[self.step] + self.alter) % 12


@dataclass(frozen=True, slots=True)
class _Candidate:
    step: StepValue
    alter: int
    octave: int
    pitch: int

    @property
    def line_of_fifths(self) -> int:
        return _NATURAL_LOF[self.step] + 7 * self.alter


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    candidate: _Candidate
    penalty: float
    chord_bonus: bool
    step_bonus: bool


@dataclass(frozen=True, slots=True)
class _KeyCorrelation:
    name: KeyName
    correlation: float
    order: int


@dataclass(frozen=True, slots=True)
class _KeyDecision:
    estimate: KeyEstimate
    plausible_keys: tuple[KeyName, ...]
    histogram: tuple[float, ...]
    best: _KeyCorrelation | None
    runner_up: _KeyCorrelation | None


_PITCH_NAMES = (
    _PitchName("C", 0),
    _PitchName("C", 1),
    _PitchName("D", -1),
    _PitchName("D", 0),
    _PitchName("D", 1),
    _PitchName("E", -1),
    _PitchName("E", 0),
    _PitchName("F", -1),
    _PitchName("E", 1),
    _PitchName("F", 0),
    _PitchName("F", 1),
    _PitchName("G", -1),
    _PitchName("G", 0),
    _PitchName("G", 1),
    _PitchName("A", -1),
    _PitchName("A", 0),
    _PitchName("A", 1),
    _PitchName("B", -1),
    _PitchName("B", 0),
    _PitchName("C", -1),
    _PitchName("B", 1),
)
_PITCH_NAMES_BY_CLASS = tuple(
    tuple(name for name in _PITCH_NAMES if name.pitch_class == pitch_class)
    for pitch_class in range(12)
)

_CANONICAL_MAJOR = (
    _PitchName("C", 0),
    _PitchName("D", -1),
    _PitchName("D", 0),
    _PitchName("E", -1),
    _PitchName("E", 0),
    _PitchName("F", 0),
    _PitchName("G", -1),
    _PitchName("G", 0),
    _PitchName("A", -1),
    _PitchName("A", 0),
    _PitchName("B", -1),
    _PitchName("B", 0),
)
_CANONICAL_MINOR = (
    _PitchName("C", 0),
    _PitchName("C", 1),
    _PitchName("D", 0),
    _PitchName("E", -1),
    _PitchName("E", 0),
    _PitchName("F", 0),
    _PitchName("F", 1),
    _PitchName("G", 0),
    _PitchName("G", 1),
    _PitchName("A", 0),
    _PitchName("B", -1),
    _PitchName("B", 0),
)

_SUPPORTED_KEY_FIFTHS: dict[tuple[KeyModeValue, StepValue, int], int] = {
    ("major", "C", -1): -7,
    ("major", "G", -1): -6,
    ("major", "D", -1): -5,
    ("major", "A", -1): -4,
    ("major", "E", -1): -3,
    ("major", "B", -1): -2,
    ("major", "F", 0): -1,
    ("major", "C", 0): 0,
    ("major", "G", 0): 1,
    ("major", "D", 0): 2,
    ("major", "A", 0): 3,
    ("major", "E", 0): 4,
    ("major", "B", 0): 5,
    ("major", "F", 1): 6,
    ("major", "C", 1): 7,
    ("minor", "A", -1): -7,
    ("minor", "E", -1): -6,
    ("minor", "B", -1): -5,
    ("minor", "F", 0): -4,
    ("minor", "C", 0): -3,
    ("minor", "G", 0): -2,
    ("minor", "D", 0): -1,
    ("minor", "A", 0): 0,
    ("minor", "E", 0): 1,
    ("minor", "B", 0): 2,
    ("minor", "F", 1): 3,
    ("minor", "C", 1): 4,
    ("minor", "G", 1): 5,
    ("minor", "D", 1): 6,
    ("minor", "A", 1): 7,
}


def spell_notes(
    notes: tuple[SpellingNote, ...],
    settings: SpellingSettings,
    *,
    key_override: KeyOverride | None = None,
) -> SpellingResult:
    """Estimate or adopt a key and deterministically spell every input note."""
    _validate_inputs(notes, settings, key_override)
    ordered = tuple(sorted(notes, key=_note_order))
    key_decision = _detect_key(ordered, settings, key_override)
    spelled, chord_count, step_count = _spell_ordered_notes(
        ordered,
        key_decision,
        settings,
    )
    best = key_decision.best
    runner_up = key_decision.runner_up
    diagnostics = SpellingDiagnostics(
        pitch_class_histogram=key_decision.histogram,
        best_key=_format_key(best.name) if best else None,
        best_key_correlation=best.correlation if best else None,
        runner_up_key=_format_key(runner_up.name) if runner_up else None,
        runner_up_key_correlation=runner_up.correlation if runner_up else None,
        key_correlation_margin=(key_decision.estimate.confidence or 0.0),
        plausible_keys=tuple(_format_key(key) for key in key_decision.plausible_keys),
        candidate_set_sizes=tuple(len(_PITCH_NAMES_BY_CLASS[note.pitch % 12]) for note in ordered),
        chord_consistency_application_count=chord_count,
        melodic_rule_application_count=step_count,
        resolved_count=sum(note.step is not None for note in spelled),
        unknown_count=sum(note.step is None for note in spelled),
        unknown_key_count=sum(note.spelling_ambiguity_reason == "unknown_key" for note in spelled),
        close_alternative_count=sum(
            note.spelling_ambiguity_reason == "close_alternative" for note in spelled
        ),
    )
    return SpellingResult(key=key_decision.estimate, notes=spelled, diagnostics=diagnostics)


def canonical_tonic(pitch_class: int, mode: KeyModeValue) -> KeyName:
    """Return the deterministic standard-signature name for a pitch-class key."""
    if not 0 <= pitch_class < 12 or mode not in {"major", "minor"}:
        raise ValueError("Pitch class and mode must identify one of the 24 pitch-class keys.")
    name = (_CANONICAL_MAJOR if mode == "major" else _CANONICAL_MINOR)[pitch_class]
    return KeyName(name.step, name.alter, mode)


def key_signature_fifths(key: KeyName | KeyOverride) -> int:
    """Return -7..7 for a supported standard major or minor key name."""
    try:
        return _SUPPORTED_KEY_FIFTHS[(key.mode, key.tonic_step, key.tonic_alter)]
    except KeyError as error:
        raise ValueError("Key must belong to the 15 standard signatures for its mode.") from error


def midi_pitch_for_spelling(step: StepValue, alter: int, octave: int) -> int:
    """Map a written spelling back to its unchanged MIDI pitch."""
    return 12 * (octave + 1) + _NATURAL_PITCH_CLASS[step] + alter


def _validate_inputs(
    notes: tuple[SpellingNote, ...],
    settings: SpellingSettings,
    key_override: KeyOverride | None,
) -> None:
    if not notes:
        raise SpellingError("notes_required", "No voiced notes are available for pitch spelling.")
    if (
        settings.key_minimum_notes <= 0
        or not 1 <= settings.key_minimum_distinct_pitch_classes <= 12
        or not math.isfinite(settings.key_ambiguity_margin)
        or not 0 <= settings.key_ambiguity_margin <= 1
        or not math.isfinite(settings.spelling_close_margin)
        or not 0 <= settings.spelling_close_margin <= 1
    ):
        raise SpellingError("incomplete_voice_state", "Pitch-spelling settings are invalid.")
    if len({note.id for note in notes}) != len(notes):
        raise SpellingError("incomplete_voice_state", "Voiced note identifiers must be unique.")
    if any(
        not 0 <= note.pitch <= 127
        or not math.isfinite(note.symbolic_start_beats)
        or not math.isfinite(note.symbolic_duration_beats)
        or note.symbolic_duration_beats <= 0
        or note.chord_group <= 0
        or note.staff not in {"treble", "bass", "unknown"}
        or note.voice is not None
        and note.voice < 1
        for note in notes
    ):
        raise SpellingError(
            "incomplete_voice_state",
            "Voiced notes contain incomplete or invalid symbolic evidence.",
        )
    if key_override is not None:
        try:
            key_signature_fifths(key_override)
        except ValueError as error:
            raise SpellingError("invalid_key_override", str(error)) from error


def _detect_key(
    notes: tuple[SpellingNote, ...],
    settings: SpellingSettings,
    key_override: KeyOverride | None,
) -> _KeyDecision:
    buckets: list[list[float]] = [[] for _ in range(12)]
    for note in notes:
        buckets[note.pitch % 12].append(note.symbolic_duration_beats)
    histogram = tuple(math.fsum(bucket) for bucket in buckets)
    all_keys = _all_canonical_keys()

    if key_override is not None:
        adopted = KeyName(key_override.tonic_step, key_override.tonic_alter, key_override.mode)
        return _KeyDecision(
            estimate=KeyEstimate(
                tonic_step=adopted.tonic_step,
                tonic_alter=adopted.tonic_alter,
                mode=adopted.mode,
                confidence=None,
                ambiguity_reason=None,
                source="override",
            ),
            plausible_keys=(adopted,),
            histogram=histogram,
            best=None,
            runner_up=None,
        )

    if (
        len(notes) < settings.key_minimum_notes
        or sum(weight > 0 for weight in histogram) < settings.key_minimum_distinct_pitch_classes
    ):
        return _unknown_key_decision("insufficient_notes", histogram, all_keys)

    total_duration = math.fsum(histogram)
    normalized = tuple(weight / total_duration for weight in histogram)
    mean = math.fsum(normalized) / 12
    centered_norm = math.fsum((weight - mean) ** 2 for weight in normalized)
    if centered_norm <= HISTOGRAM_CENTERED_NORM_EPSILON:
        return _unknown_key_decision("ambiguous_key", histogram, all_keys)

    correlations = _key_correlations(normalized, centered_norm)
    best, runner_up = correlations[:2]
    confidence = _clamp((best.correlation - runner_up.correlation) / 2)
    if confidence < settings.key_ambiguity_margin:
        plausible = tuple(
            candidate.name
            for candidate in correlations
            if _clamp((best.correlation - candidate.correlation) / 2)
            <= settings.key_ambiguity_margin
        )
        return _KeyDecision(
            estimate=KeyEstimate(None, None, None, confidence, "ambiguous_key", "estimated"),
            plausible_keys=plausible,
            histogram=histogram,
            best=best,
            runner_up=runner_up,
        )

    return _KeyDecision(
        estimate=KeyEstimate(
            best.name.tonic_step,
            best.name.tonic_alter,
            best.name.mode,
            confidence,
            None,
            "estimated",
        ),
        plausible_keys=(best.name,),
        histogram=histogram,
        best=best,
        runner_up=runner_up,
    )


def _unknown_key_decision(
    reason: KeyAmbiguityReasonValue,
    histogram: tuple[float, ...],
    plausible_keys: tuple[KeyName, ...],
) -> _KeyDecision:
    return _KeyDecision(
        estimate=KeyEstimate(None, None, None, 0.0, reason, "estimated"),
        plausible_keys=plausible_keys,
        histogram=histogram,
        best=None,
        runner_up=None,
    )


def _key_correlations(
    normalized_histogram: tuple[float, ...], centered_histogram_norm: float
) -> tuple[_KeyCorrelation, ...]:
    correlations: list[_KeyCorrelation] = []
    histogram_mean = math.fsum(normalized_histogram) / 12
    order = 0
    for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
        for tonic_pitch_class in range(12):
            rotated = tuple(
                profile[(pitch_class - tonic_pitch_class) % 12] for pitch_class in range(12)
            )
            profile_mean = math.fsum(rotated) / 12
            centered_profile = tuple(value - profile_mean for value in rotated)
            numerator = math.fsum(
                (value - histogram_mean) * profile_value
                for value, profile_value in zip(
                    normalized_histogram,
                    centered_profile,
                    strict=True,
                )
            )
            denominator = math.sqrt(
                centered_histogram_norm
                * math.fsum(profile_value**2 for profile_value in centered_profile)
            )
            correlations.append(
                _KeyCorrelation(
                    name=canonical_tonic(tonic_pitch_class, mode),  # type: ignore[arg-type]
                    correlation=max(-1.0, min(1.0, numerator / denominator)),
                    order=order,
                )
            )
            order += 1
    return tuple(sorted(correlations, key=lambda item: (-item.correlation, item.order)))


def _spell_ordered_notes(
    notes: tuple[SpellingNote, ...],
    key_decision: _KeyDecision,
    settings: SpellingSettings,
) -> tuple[tuple[SpelledNote, ...], int, int]:
    if key_decision.estimate.ambiguity_reason is not None:
        unknown_key_spellings = tuple(
            _spell_under_unknown_key(note, key_decision.plausible_keys, settings) for note in notes
        )
        return unknown_key_spellings, 0, 0

    resolved_key = key_decision.plausible_keys[0]
    decided_by_group: dict[int, list[_Candidate]] = {}
    previous_by_stream: dict[tuple[StaffValue, int], _Candidate | None] = {}
    spelled: list[SpelledNote] = []
    chord_applications = 0
    step_applications = 0
    for note in notes:
        stream = (
            (note.staff, note.voice) if note.staff != "unknown" and note.voice is not None else None
        )
        previous = previous_by_stream.get(stream) if stream is not None else None
        ranked = _rank_candidates(
            note,
            resolved_key,
            decided_by_group.get(note.chord_group, []),
            previous,
        )
        winner = ranked[0]
        confidence = _candidate_confidence(ranked)
        if winner.chord_bonus:
            chord_applications += 1
        if winner.step_bonus:
            step_applications += 1
        if confidence < settings.spelling_close_margin:
            spelled.append(_unknown_spelling(note.id, confidence, "close_alternative"))
            if stream is not None:
                previous_by_stream[stream] = None
            continue

        candidate = winner.candidate
        spelled.append(_resolved_spelling(note.id, candidate, confidence))
        decided_by_group.setdefault(note.chord_group, []).append(candidate)
        if stream is not None:
            previous_by_stream[stream] = candidate
    return tuple(spelled), chord_applications, step_applications


def _spell_under_unknown_key(
    note: SpellingNote,
    plausible_keys: tuple[KeyName, ...],
    settings: SpellingSettings,
) -> SpelledNote:
    stable_winners: list[_Candidate] = []
    confidences: list[float] = []
    for key in plausible_keys:
        ranked = _rank_candidates(note, key, (), None)
        confidence = _candidate_confidence(ranked)
        if confidence < settings.spelling_close_margin:
            return _unknown_spelling(note.id, 0.0, "unknown_key")
        stable_winners.append(ranked[0].candidate)
        confidences.append(confidence)
    first = stable_winners[0]
    if any(
        (candidate.step, candidate.alter) != (first.step, first.alter)
        for candidate in stable_winners[1:]
    ):
        return _unknown_spelling(note.id, 0.0, "unknown_key")
    return _resolved_spelling(note.id, first, min(confidences))


def _rank_candidates(
    note: SpellingNote,
    key: KeyName,
    chord_candidates: Sequence[_Candidate],
    previous: _Candidate | None,
) -> tuple[_RankedCandidate, ...]:
    tonic_lof = _NATURAL_LOF[key.tonic_step] + 7 * key.tonic_alter
    ranked: list[_RankedCandidate] = []
    for candidate in _candidates(note.pitch):
        chord_bonus = any(_stacks_as_third(candidate, other) for other in chord_candidates)
        step_bonus = previous is not None and _forms_chromatic_neighbor(candidate, previous)
        penalty = (
            abs(candidate.line_of_fifths - tonic_lof) - W_CHORD * chord_bonus - W_STEP * step_bonus
        )
        ranked.append(_RankedCandidate(candidate, penalty, chord_bonus, step_bonus))
    return tuple(
        sorted(
            ranked,
            key=lambda item: (
                item.penalty,
                abs(item.candidate.alter),
                _alter_tie_order(item.candidate.alter),
            ),
        )
    )


def _candidates(pitch: int) -> tuple[_Candidate, ...]:
    return tuple(
        _Candidate(
            step=name.step,
            alter=name.alter,
            octave=(pitch - _NATURAL_PITCH_CLASS[name.step] - name.alter) // 12 - 1,
            pitch=pitch,
        )
        for name in _PITCH_NAMES_BY_CLASS[pitch % 12]
    )


def _candidate_confidence(ranked: tuple[_RankedCandidate, ...]) -> float:
    if len(ranked) == 1:
        return 1.0
    return _clamp((ranked[1].penalty - ranked[0].penalty) / SPELLING_GAP_FULL_SCALE)


def _stacks_as_third(first: _Candidate, second: _Candidate) -> bool:
    letter_distance = (_STEP_INDEX[first.step] - _STEP_INDEX[second.step]) % 7
    pitch_distance = abs(first.pitch - second.pitch) % 12
    return letter_distance in {2, 5} and pitch_distance in {3, 4}


def _forms_chromatic_neighbor(current: _Candidate, previous: _Candidate) -> bool:
    return abs(current.pitch - previous.pitch) == 1 and current.step == previous.step


def _resolved_spelling(note_id: int, candidate: _Candidate, confidence: float) -> SpelledNote:
    return SpelledNote(
        note_id,
        candidate.step,
        candidate.alter,
        candidate.octave,
        confidence,
        None,
    )


def _unknown_spelling(
    note_id: int,
    confidence: float,
    reason: SpellingAmbiguityReasonValue,
) -> SpelledNote:
    return SpelledNote(note_id, None, None, None, confidence, reason)


def _all_canonical_keys() -> tuple[KeyName, ...]:
    modes: tuple[KeyModeValue, ...] = ("major", "minor")
    return tuple(canonical_tonic(pitch_class, mode) for mode in modes for pitch_class in range(12))


def _note_order(note: SpellingNote) -> tuple[int, tuple[int, int], float, int, int]:
    staff_order = {"treble": 0, "bass": 1, "unknown": 2}[note.staff]
    voice_order = (0, note.voice) if note.voice is not None else (1, 0)
    return staff_order, voice_order, note.symbolic_start_beats, note.pitch, note.id


def _format_key(key: KeyName) -> str:
    accidental = "#" if key.tonic_alter == 1 else "b" if key.tonic_alter == -1 else ""
    return f"{key.tonic_step}{accidental} {key.mode}"


def _alter_tie_order(alter: int) -> int:
    if alter < 0:
        return 0
    if alter == 0:
        return 1
    return 2


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
