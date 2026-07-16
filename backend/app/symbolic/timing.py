import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from statistics import fmean, median
from typing import Literal

BEAT_DISTANCE_HYPOTHESES = (
    Fraction(1, 4),
    Fraction(1, 2),
    Fraction(3, 4),
    Fraction(1),
    Fraction(3, 2),
    Fraction(2),
    Fraction(3),
    Fraction(4),
)
PREFERRED_DURATIONS = BEAT_DISTANCE_HYPOTHESES
TempoSourceValue = Literal["estimated", "override"]
SettingSourceValue = Literal["default", "override"]


class TimingAnalysisError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class RawTimingNote:
    id: int
    pitch: int
    start_seconds: float
    end_seconds: float
    confidence: float | None


@dataclass(frozen=True, slots=True)
class TimingSettings:
    minimum_bpm: float = 40.0
    maximum_bpm: float = 200.0
    chord_tolerance_seconds: float = 0.06
    minimum_grid: Fraction = Fraction(1, 4)
    minimum_tempo_groups: int = 4
    minimum_tempo_span_seconds: float = 1.0
    maximum_residual: float = 0.22
    minimum_inlier_coverage: float = 0.75
    inlier_residual: float = 0.35
    distinct_tempo_ratio: float = 0.02
    ambiguity_margin: float = 0.03
    octave_ambiguity_margin: float = 0.04
    rest_tolerance_beats: Fraction = Fraction(3, 25)
    same_pitch_repair_tolerance_beats: Fraction = Fraction(1, 2)


@dataclass(frozen=True, slots=True)
class ChordGroup:
    index: int
    onset_seconds: float
    confidence: float
    note_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TempoDiagnostics:
    candidate_bpm: float | None
    residual: float | None
    inlier_coverage: float | None
    winning_score: float | None
    runner_up_score: float | None
    score_margin: float | None
    chord_group_count: int
    onset_span_seconds: float
    octave_ambiguous: bool


@dataclass(frozen=True, slots=True)
class TempoEstimate:
    bpm: float
    diagnostics: TempoDiagnostics


@dataclass(frozen=True, slots=True)
class QuantizedTimingNote:
    note_id: int
    chord_group: int
    symbolic_start_beats: Fraction
    symbolic_duration_beats: Fraction
    measure_number: int
    beat_in_measure: Fraction


@dataclass(frozen=True, slots=True)
class TimingResult:
    estimated_tempo_bpm: float | None
    selected_tempo_bpm: float
    tempo_source: TempoSourceValue
    measure_origin_seconds: float
    measure_origin_source: SettingSourceValue
    meter_numerator: int
    meter_denominator: int
    meter_source: SettingSourceValue
    diagnostics: TempoDiagnostics
    chord_groups: tuple[ChordGroup, ...]
    notes: tuple[QuantizedTimingNote, ...]


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    bpm: float
    residual: float
    coverage: float
    score: float


def raw_notes_fingerprint(notes: tuple[RawTimingNote, ...]) -> str:
    payload = [
        {
            "id": note.id,
            "pitch": note.pitch,
            "start_seconds": note.start_seconds,
            "end_seconds": note.end_seconds,
            "confidence": note.confidence,
        }
        for note in sorted(notes, key=lambda item: (item.start_seconds, item.pitch, item.id))
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def group_chords(
    notes: tuple[RawTimingNote, ...],
    tolerance_seconds: float,
) -> tuple[ChordGroup, ...]:
    if not notes:
        return ()
    ordered = sorted(notes, key=lambda item: (item.start_seconds, item.pitch, item.id))
    grouped: list[list[RawTimingNote]] = []
    current: list[RawTimingNote] = []
    anchor = 0.0
    for note in ordered:
        if not current or note.start_seconds - anchor <= tolerance_seconds:
            if not current:
                anchor = note.start_seconds
            current.append(note)
            continue
        grouped.append(current)
        current = [note]
        anchor = note.start_seconds
    grouped.append(current)

    return tuple(
        ChordGroup(
            index=index,
            onset_seconds=float(median(note.start_seconds for note in group)),
            confidence=(
                fmean(note.confidence for note in group if note.confidence is not None)
                if any(note.confidence is not None for note in group)
                else 1.0
            ),
            note_ids=tuple(note.id for note in group),
        )
        for index, group in enumerate(grouped, start=1)
    )


def estimate_tempo(
    groups: tuple[ChordGroup, ...],
    settings: TimingSettings,
) -> TempoEstimate:
    span = groups[-1].onset_seconds - groups[0].onset_seconds if groups else 0.0
    if len(groups) < settings.minimum_tempo_groups or span < settings.minimum_tempo_span_seconds:
        raise TimingAnalysisError(
            "tempo_ambiguous",
            "The detected notes do not contain enough pulse evidence. Enter a BPM to continue.",
            {"chord_group_count": len(groups), "onset_span_seconds": span},
        )

    buckets: dict[int, list[tuple[float, float]]] = {}
    for index, group in enumerate(groups):
        for other in groups[index + 1 : index + 5]:
            interval = other.onset_seconds - group.onset_seconds
            if interval <= 0:
                continue
            pair_weight = (group.confidence + other.confidence) / 2
            for beat_distance in BEAT_DISTANCE_HYPOTHESES:
                bpm = 60 * float(beat_distance) / interval
                if settings.minimum_bpm <= bpm <= settings.maximum_bpm:
                    bucket = math.floor((bpm * 10) + 0.5)
                    buckets.setdefault(bucket, []).append((bpm, pair_weight))

    candidates = [
        sum(bpm * weight for bpm, weight in values) / sum(weight for _, weight in values)
        for values in buckets.values()
        if sum(weight for _, weight in values) > 0
    ]
    if len(candidates) < 2:
        raise TimingAnalysisError(
            "tempo_ambiguous",
            "The detected notes do not contain enough tempo candidates. Enter a BPM to continue.",
            {"candidate_count": len(candidates)},
        )

    scored = sorted(
        (_score_candidate(groups, bpm, settings) for bpm in candidates),
        key=lambda item: item.score,
    )
    winner = scored[0]
    runner_up = next(
        (
            candidate
            for candidate in scored[1:]
            if abs(math.log(candidate.bpm / winner.bpm))
            >= math.log1p(settings.distinct_tempo_ratio)
        ),
        None,
    )
    if runner_up is None:
        raise TimingAnalysisError(
            "tempo_ambiguous",
            "The detected notes do not contain distinct tempo candidates. Enter a BPM to continue.",
            {"candidate_count": len(candidates)},
        )
    margin = runner_up.score - winner.score
    octave_ambiguous = any(
        _is_near_octave(winner.bpm, candidate.bpm)
        and candidate.score - winner.score <= settings.octave_ambiguity_margin
        for candidate in scored[1:]
    )
    diagnostics = TempoDiagnostics(
        candidate_bpm=winner.bpm,
        residual=winner.residual,
        inlier_coverage=winner.coverage,
        winning_score=winner.score,
        runner_up_score=runner_up.score,
        score_margin=margin,
        chord_group_count=len(groups),
        onset_span_seconds=span,
        octave_ambiguous=octave_ambiguous,
    )
    if (
        winner.residual > settings.maximum_residual
        or winner.coverage < settings.minimum_inlier_coverage
        or margin < settings.ambiguity_margin
        or octave_ambiguous
    ):
        raise TimingAnalysisError(
            "tempo_ambiguous",
            "Automatic tempo is uncertain. Enter a BPM to continue.",
            {"diagnostics": diagnostics_to_dict(diagnostics)},
        )
    return TempoEstimate(bpm=winner.bpm, diagnostics=diagnostics)


def quantize_timing(
    notes: tuple[RawTimingNote, ...],
    settings: TimingSettings,
    *,
    tempo_bpm: float | None = None,
    meter_numerator: int = 4,
    meter_denominator: int = 4,
    measure_origin_seconds: float | None = None,
) -> TimingResult:
    if not notes:
        raise TimingAnalysisError(
            "notes_required",
            "No detected notes are available for quantization.",
        )
    if tempo_bpm is not None and not settings.minimum_bpm <= tempo_bpm <= settings.maximum_bpm:
        raise TimingAnalysisError(
            "invalid_tempo",
            (f"Tempo must be between {settings.minimum_bpm:g} and {settings.maximum_bpm:g} BPM."),
        )
    if (meter_numerator, meter_denominator) not in {(2, 4), (3, 4), (4, 4)}:
        raise TimingAnalysisError(
            "unsupported_meter",
            "This baseline supports 2/4, 3/4, and 4/4.",
        )
    if measure_origin_seconds is not None and measure_origin_seconds < 0:
        raise TimingAnalysisError(
            "invalid_measure_origin",
            "Measure origin must be zero or later.",
        )

    groups = group_chords(notes, settings.chord_tolerance_seconds)
    span = groups[-1].onset_seconds - groups[0].onset_seconds
    if tempo_bpm is None:
        estimate = estimate_tempo(groups, settings)
        selected_bpm = estimate.bpm
        estimated_bpm: float | None = estimate.bpm
        tempo_source: TempoSourceValue = "estimated"
        diagnostics = estimate.diagnostics
    else:
        selected_bpm = tempo_bpm
        estimated_bpm = None
        tempo_source = "override"
        diagnostics = TempoDiagnostics(
            candidate_bpm=None,
            residual=None,
            inlier_coverage=None,
            winning_score=None,
            runner_up_score=None,
            score_margin=None,
            chord_group_count=len(groups),
            onset_span_seconds=span,
            octave_ambiguous=False,
        )

    origin = (
        measure_origin_seconds if measure_origin_seconds is not None else groups[0].onset_seconds
    )
    origin_source: SettingSourceValue = (
        "override" if measure_origin_seconds is not None else "default"
    )
    meter_source: SettingSourceValue = (
        "override" if (meter_numerator, meter_denominator) != (4, 4) else "default"
    )
    bpm_fraction = _fraction(selected_bpm)
    origin_fraction = _fraction(origin)

    note_by_id = {note.id: note for note in notes}
    group_onsets: dict[int, Fraction] = {}
    last_pitch_onset: dict[int, Fraction] = {}
    for group in groups:
        raw_position = (_fraction(group.onset_seconds) - origin_fraction) * bpm_fraction / 60
        onset = _nearest_grid(raw_position, settings.minimum_grid)
        required = onset
        for note_id in group.note_ids:
            previous = last_pitch_onset.get(note_by_id[note_id].pitch)
            if previous is not None:
                required = max(required, previous + settings.minimum_grid)
        if required > onset:
            if required - onset > settings.same_pitch_repair_tolerance_beats:
                raise TimingAnalysisError(
                    "rhythm_too_dense",
                    "Repeated notes are too close for the selected tempo and minimum note value.",
                    {"chord_group": group.index},
                )
            onset = required
        group_onsets[group.index] = onset
        for note_id in group.note_ids:
            last_pitch_onset[note_by_id[note_id].pitch] = onset

    group_by_note = {note_id: group for group in groups for note_id in group.note_ids}
    later_same_pitch: dict[int, Fraction] = {}
    next_by_pitch: dict[int, Fraction] = {}
    for note in sorted(notes, key=lambda item: (item.start_seconds, item.id), reverse=True):
        later = next_by_pitch.get(note.pitch)
        if later is not None:
            later_same_pitch[note.id] = later
        next_by_pitch[note.pitch] = group_onsets[group_by_note[note.id].index]

    quantized: list[QuantizedTimingNote] = []
    for note in sorted(notes, key=lambda item: (item.start_seconds, item.pitch, item.id)):
        group = group_by_note[note.id]
        start = group_onsets[group.index]
        raw_end = (_fraction(note.end_seconds) - origin_fraction) * bpm_fraction / 60
        target_end = raw_end
        next_group = groups[group.index] if group.index < len(groups) else None
        if next_group is not None:
            next_raw_position = (
                (_fraction(next_group.onset_seconds) - origin_fraction) * bpm_fraction / 60
            )
            if abs(raw_end - next_raw_position) <= settings.rest_tolerance_beats:
                target_end = group_onsets[next_group.index]
        target_duration = target_end - start
        duration = _preferred_duration(target_duration, settings.minimum_grid)
        next_same_pitch = later_same_pitch.get(note.id)
        if next_same_pitch is not None:
            duration = min(duration, next_same_pitch - start)
        if duration < settings.minimum_grid:
            raise TimingAnalysisError(
                "rhythm_too_dense",
                "A detected note cannot fit the selected tempo and minimum note value.",
                {"note_id": note.id},
            )
        measure_number, beat_in_measure = measure_position(
            start, meter_numerator, meter_denominator
        )
        quantized.append(
            QuantizedTimingNote(
                note_id=note.id,
                chord_group=group.index,
                symbolic_start_beats=start,
                symbolic_duration_beats=duration,
                measure_number=measure_number,
                beat_in_measure=beat_in_measure,
            )
        )

    return TimingResult(
        estimated_tempo_bpm=estimated_bpm,
        selected_tempo_bpm=selected_bpm,
        tempo_source=tempo_source,
        measure_origin_seconds=origin,
        measure_origin_source=origin_source,
        meter_numerator=meter_numerator,
        meter_denominator=meter_denominator,
        meter_source=meter_source,
        diagnostics=diagnostics,
        chord_groups=groups,
        notes=tuple(quantized),
    )


def diagnostics_to_dict(diagnostics: TempoDiagnostics) -> dict[str, object]:
    return {
        "candidate_bpm": diagnostics.candidate_bpm,
        "residual": diagnostics.residual,
        "inlier_coverage": diagnostics.inlier_coverage,
        "winning_score": diagnostics.winning_score,
        "runner_up_score": diagnostics.runner_up_score,
        "score_margin": diagnostics.score_margin,
        "chord_group_count": diagnostics.chord_group_count,
        "onset_span_seconds": diagnostics.onset_span_seconds,
        "octave_ambiguous": diagnostics.octave_ambiguous,
    }


def _score_candidate(
    groups: tuple[ChordGroup, ...],
    bpm: float,
    settings: TimingSettings,
) -> _CandidateScore:
    origin = _fraction(groups[0].onset_seconds)
    bpm_fraction = _fraction(bpm)
    weighted_residual = 0.0
    weighted_complexity = 0.0
    inlier_weight = 0.0
    total_weight = 0.0
    for group in groups:
        position = (_fraction(group.onset_seconds) - origin) * bpm_fraction / 60
        snapped = _nearest_grid(position, settings.minimum_grid)
        residual = float(abs(position - snapped) / settings.minimum_grid)
        complexity = _complexity(snapped)
        weight = group.confidence
        weighted_residual += residual * weight
        weighted_complexity += complexity * weight
        if residual <= settings.inlier_residual:
            inlier_weight += weight
        total_weight += weight
    residual_score = weighted_residual / total_weight
    complexity_score = weighted_complexity / total_weight
    prior = 0.03 * abs(math.log2(bpm / 120))
    return _CandidateScore(
        bpm=bpm,
        residual=residual_score,
        coverage=inlier_weight / total_weight,
        score=residual_score + complexity_score + prior,
    )


def _complexity(position: Fraction) -> float:
    remainder = position % 1
    if remainder == 0:
        return 0.0
    if remainder == Fraction(1, 2):
        return 0.04
    return 0.08


def _is_near_octave(first: float, second: float) -> bool:
    ratio = max(first, second) / min(first, second)
    return 1.95 <= ratio <= 2.05


def _preferred_duration(target: Fraction, minimum_grid: Fraction) -> Fraction:
    if target <= 0:
        return minimum_grid
    if target > 4:
        return max(minimum_grid, _nearest_grid(target, minimum_grid))
    return min(
        PREFERRED_DURATIONS,
        key=lambda value: (abs(value - target), -value),
    )


def measure_position(
    symbolic_start: Fraction,
    meter_numerator: int,
    meter_denominator: int,
) -> tuple[int, Fraction]:
    measure_length = Fraction(meter_numerator * 4, meter_denominator)
    measure_index = symbolic_start // measure_length
    offset = symbolic_start - (measure_index * measure_length)
    beat_unit = Fraction(4, meter_denominator)
    return int(measure_index) + 1, (offset / beat_unit) + 1


def _nearest_grid(value: Fraction, grid: Fraction) -> Fraction:
    quotient = value / grid
    lower = quotient.numerator // quotient.denominator
    remainder = quotient - lower
    multiplier = lower + 1 if remainder > Fraction(1, 2) else lower
    return multiplier * grid


def _fraction(value: float) -> Fraction:
    return Fraction(str(value))
