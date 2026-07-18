from dataclasses import dataclass
from fractions import Fraction
from statistics import median
from typing import Literal

AssignmentValue = Literal["left", "right", "treble", "bass", "unknown"]
AmbiguityReasonValue = Literal[
    "close_alternative",
    "middle_register",
    "wide_chord",
    "crossing",
    "insufficient_context",
]


class InterpretationError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class InterpretationNote:
    id: int
    pitch: int
    symbolic_start_beats: Fraction
    symbolic_duration_beats: Fraction
    chord_group: int


@dataclass(frozen=True, slots=True)
class InterpretationSettings:
    left_center_pitch: float = 48.0
    right_center_pitch: float = 72.0
    bass_center_pitch: float = 48.0
    treble_center_pitch: float = 72.0
    pitch_weight: float = 1.0
    span_weight: float = 0.25
    movement_weight: float = 0.35
    appearance_weight: float = 0.15
    split_movement_weight: float = 0.08
    crossing_weight: float = 0.5
    compact_split_weight: float = 0.1
    wide_single_partition_weight: float = 0.5
    comfortable_hand_span: int = 12
    compact_chord_span: int = 7
    middle_register_low: int = 55
    middle_register_high: int = 65
    ambiguity_margin: float = 0.25
    high_confidence_margin: float = 1.0
    maximum_transition_evaluations: int = 2_000_000


@dataclass(frozen=True, slots=True)
class InterpretedNote:
    note_id: int
    hand: Literal["left", "right", "unknown"]
    staff: Literal["treble", "bass", "unknown"]
    hand_confidence: float
    staff_confidence: float
    hand_ambiguity_reason: AmbiguityReasonValue | None
    staff_ambiguity_reason: AmbiguityReasonValue | None


@dataclass(frozen=True, slots=True)
class InterpretationDiagnostics:
    chord_group_count: int
    candidate_state_count: int
    transition_evaluations: int
    resolved_hand_count: int
    unknown_hand_count: int
    resolved_staff_count: int
    unknown_staff_count: int
    wide_chord_count: int
    crossing_pressure_count: int


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    notes: tuple[InterpretedNote, ...]
    diagnostics: InterpretationDiagnostics


@dataclass(frozen=True, slots=True)
class _Group:
    index: int
    notes: tuple[InterpretationNote, ...]
    span: int


@dataclass(frozen=True, slots=True)
class _State:
    split: int
    lower_center: float | None
    upper_center: float | None
    local_cost: float


@dataclass(frozen=True, slots=True)
class _PassResult:
    assignments: dict[int, AssignmentValue]
    confidences: dict[int, float]
    reasons: dict[int, AmbiguityReasonValue | None]
    candidate_state_count: int
    transition_evaluations: int
    crossing_groups: frozenset[int]


def interpret_notes(
    notes: tuple[InterpretationNote, ...],
    settings: InterpretationSettings,
) -> InterpretationResult:
    groups = _group_notes(notes)
    hand = _solve_partition_pass(
        groups,
        settings,
        lower_label="left",
        upper_label="right",
        lower_center=settings.left_center_pitch,
        upper_center=settings.right_center_pitch,
        penalize_span=True,
        evaluation_budget=settings.maximum_transition_evaluations,
    )
    remaining_budget = settings.maximum_transition_evaluations - hand.transition_evaluations
    staff = _solve_partition_pass(
        groups,
        settings,
        lower_label="bass",
        upper_label="treble",
        lower_center=settings.bass_center_pitch,
        upper_center=settings.treble_center_pitch,
        penalize_span=False,
        evaluation_budget=remaining_budget,
    )
    interpreted = tuple(
        InterpretedNote(
            note_id=note.id,
            hand=hand.assignments[note.id],  # type: ignore[arg-type]
            staff=staff.assignments[note.id],  # type: ignore[arg-type]
            hand_confidence=hand.confidences[note.id],
            staff_confidence=staff.confidences[note.id],
            hand_ambiguity_reason=hand.reasons[note.id],
            staff_ambiguity_reason=staff.reasons[note.id],
        )
        for note in sorted(notes, key=lambda item: (item.symbolic_start_beats, item.pitch, item.id))
    )
    return InterpretationResult(
        notes=interpreted,
        diagnostics=InterpretationDiagnostics(
            chord_group_count=len(groups),
            candidate_state_count=hand.candidate_state_count + staff.candidate_state_count,
            transition_evaluations=(hand.transition_evaluations + staff.transition_evaluations),
            resolved_hand_count=sum(note.hand != "unknown" for note in interpreted),
            unknown_hand_count=sum(note.hand == "unknown" for note in interpreted),
            resolved_staff_count=sum(note.staff != "unknown" for note in interpreted),
            unknown_staff_count=sum(note.staff == "unknown" for note in interpreted),
            wide_chord_count=sum(group.span > settings.comfortable_hand_span for group in groups),
            crossing_pressure_count=len(hand.crossing_groups | staff.crossing_groups),
        ),
    )


def _group_notes(notes: tuple[InterpretationNote, ...]) -> tuple[_Group, ...]:
    if not notes:
        raise InterpretationError(
            "notes_required",
            "No quantized notes are available for hand and staff interpretation.",
        )
    grouped: dict[int, list[InterpretationNote]] = {}
    for note in notes:
        if note.chord_group <= 0 or note.symbolic_duration_beats <= 0:
            raise InterpretationError(
                "incomplete_quantization",
                "Quantized notes are incomplete or invalid.",
            )
        grouped.setdefault(note.chord_group, []).append(note)
    result: list[_Group] = []
    previous_start: Fraction | None = None
    for index, group_notes in sorted(grouped.items()):
        starts = {note.symbolic_start_beats for note in group_notes}
        if len(starts) != 1:
            raise InterpretationError(
                "incomplete_quantization",
                "Notes in one chord group must share a symbolic onset.",
                {"chord_group": index},
            )
        start = next(iter(starts))
        if previous_start is not None and start < previous_start:
            raise InterpretationError(
                "incomplete_quantization",
                "Chord groups must be chronologically ordered.",
            )
        ordered = tuple(sorted(group_notes, key=lambda item: (item.pitch, item.id)))
        result.append(
            _Group(
                index=index,
                notes=ordered,
                span=ordered[-1].pitch - ordered[0].pitch,
            )
        )
        previous_start = start
    return tuple(result)


def _solve_partition_pass(
    groups: tuple[_Group, ...],
    settings: InterpretationSettings,
    *,
    lower_label: AssignmentValue,
    upper_label: AssignmentValue,
    lower_center: float,
    upper_center: float,
    penalize_span: bool,
    evaluation_budget: int,
) -> _PassResult:
    states = tuple(
        _build_states(
            group,
            settings,
            lower_center=lower_center,
            upper_center=upper_center,
            penalize_span=penalize_span,
        )
        for group in groups
    )
    evaluations = sum(
        len(previous) * len(current) for previous, current in zip(states, states[1:], strict=False)
    )
    if evaluations > evaluation_budget:
        raise InterpretationError(
            "interpretation_too_complex",
            "The quantized passage exceeds the interpretation work budget.",
            {"transition_evaluations": evaluations, "budget": evaluation_budget},
        )

    forward: list[list[float]] = [[state.local_cost for state in states[0]]]
    backpointers: list[list[int]] = [[-1] * len(states[0])]
    for group_index in range(1, len(groups)):
        costs: list[float] = []
        pointers: list[int] = []
        for current in states[group_index]:
            options = [
                (
                    forward[group_index - 1][previous_index]
                    + _transition_cost(previous, current, settings),
                    previous_index,
                )
                for previous_index, previous in enumerate(states[group_index - 1])
            ]
            best_cost, best_index = min(options, key=lambda item: (item[0], item[1]))
            costs.append(current.local_cost + best_cost)
            pointers.append(best_index)
        forward.append(costs)
        backpointers.append(pointers)

    backward: list[list[float]] = [[0.0] * len(group_states) for group_states in states]
    for group_index in range(len(groups) - 2, -1, -1):
        for state_index, state in enumerate(states[group_index]):
            backward[group_index][state_index] = min(
                _transition_cost(state, following, settings)
                + following.local_cost
                + backward[group_index + 1][following_index]
                for following_index, following in enumerate(states[group_index + 1])
            )

    best_last = min(
        range(len(states[-1])),
        key=lambda index: (forward[-1][index], index),
    )
    best_path = [best_last]
    for group_index in range(len(groups) - 1, 0, -1):
        best_path.append(backpointers[group_index][best_path[-1]])
    best_path.reverse()

    crossing_groups: set[int] = set()
    for group_index in range(1, len(groups)):
        if (
            _crossing_pressure(
                states[group_index - 1][best_path[group_index - 1]],
                states[group_index][best_path[group_index]],
            )
            > 0
        ):
            crossing_groups.update((group_index - 1, group_index))

    assignments: dict[int, AssignmentValue] = {}
    confidences: dict[int, float] = {}
    reasons: dict[int, AmbiguityReasonValue | None] = {}
    for group_index, group in enumerate(groups):
        total_costs = [
            forward[group_index][state_index] + backward[group_index][state_index]
            for state_index in range(len(states[group_index]))
        ]
        for note_index, note in enumerate(group.notes):
            lower_cost = min(
                total_costs[state_index]
                for state_index, state in enumerate(states[group_index])
                if note_index < state.split
            )
            upper_cost = min(
                total_costs[state_index]
                for state_index, state in enumerate(states[group_index])
                if note_index >= state.split
            )
            margin = abs(lower_cost - upper_cost)
            confidence = min(1.0, margin / settings.high_confidence_margin)
            confidences[note.id] = confidence
            if margin < settings.ambiguity_margin:
                assignments[note.id] = "unknown"
                reasons[note.id] = _ambiguity_reason(
                    group,
                    note,
                    group_index=group_index,
                    group_count=len(groups),
                    crossing_groups=crossing_groups,
                    settings=settings,
                )
            else:
                assignments[note.id] = lower_label if lower_cost < upper_cost else upper_label
                reasons[note.id] = None
    return _PassResult(
        assignments=assignments,
        confidences=confidences,
        reasons=reasons,
        candidate_state_count=sum(len(group_states) for group_states in states),
        transition_evaluations=evaluations,
        crossing_groups=frozenset(crossing_groups),
    )


def _build_states(
    group: _Group,
    settings: InterpretationSettings,
    *,
    lower_center: float,
    upper_center: float,
    penalize_span: bool,
) -> tuple[_State, ...]:
    pitches = [note.pitch for note in group.notes]
    states: list[_State] = []
    for split in range(len(pitches) + 1):
        lower = pitches[:split]
        upper = pitches[split:]
        cost = sum(abs(pitch - lower_center) / 12 for pitch in lower)
        cost += sum(abs(pitch - upper_center) / 12 for pitch in upper)
        cost *= settings.pitch_weight
        if penalize_span:
            for partition in (lower, upper):
                if partition:
                    excess = max(
                        0,
                        partition[-1] - partition[0] - settings.comfortable_hand_span,
                    )
                    cost += excess * settings.span_weight
            if lower and upper and group.span <= settings.compact_chord_span:
                cost += settings.compact_split_weight
            if (not lower or not upper) and group.span > settings.comfortable_hand_span:
                cost += settings.wide_single_partition_weight
        states.append(
            _State(
                split=split,
                lower_center=float(median(lower)) if lower else None,
                upper_center=float(median(upper)) if upper else None,
                local_cost=cost,
            )
        )
    return tuple(states)


def _transition_cost(
    previous: _State,
    current: _State,
    settings: InterpretationSettings,
) -> float:
    cost = 0.0
    for before, after in (
        (previous.lower_center, current.lower_center),
        (previous.upper_center, current.upper_center),
    ):
        if before is None or after is None:
            if before != after:
                cost += settings.appearance_weight
        else:
            cost += abs(after - before) / 12 * settings.movement_weight
    cost += abs(current.split - previous.split) * settings.split_movement_weight
    cost += _crossing_pressure(previous, current) * settings.crossing_weight
    return cost


def _crossing_pressure(previous: _State, current: _State) -> float:
    pressure = 0.0
    if previous.lower_center is not None and current.upper_center is not None:
        pressure += max(0.0, previous.lower_center - current.upper_center) / 12
    if previous.upper_center is not None and current.lower_center is not None:
        pressure += max(0.0, current.lower_center - previous.upper_center) / 12
    return pressure


def _ambiguity_reason(
    group: _Group,
    note: InterpretationNote,
    *,
    group_index: int,
    group_count: int,
    crossing_groups: set[int],
    settings: InterpretationSettings,
) -> AmbiguityReasonValue:
    if group_count < 2:
        return "insufficient_context"
    if group_index in crossing_groups:
        return "crossing"
    if group.span > settings.comfortable_hand_span:
        return "wide_chord"
    if settings.middle_register_low <= note.pitch <= settings.middle_register_high:
        return "middle_register"
    return "close_alternative"
