import math
from dataclasses import dataclass
from fractions import Fraction
from statistics import fmean
from typing import Literal

StaffValue = Literal["treble", "bass", "unknown"]
VoiceValue = Literal[1, 2]
VoiceAmbiguityReasonValue = Literal[
    "unresolved_staff",
    "voice_capacity_exceeded",
    "crossing",
    "close_alternative",
]


class VoiceSeparationError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class VoiceNote:
    id: int
    pitch: int
    symbolic_start_beats: Fraction
    symbolic_duration_beats: Fraction
    staff: StaffValue


@dataclass(frozen=True, slots=True)
class VoiceSettings:
    close_separation_semitones: float = 2.0
    high_separation_semitones: float = 7.0


@dataclass(frozen=True, slots=True)
class VoicedNote:
    note_id: int
    voice: VoiceValue | None
    voice_confidence: float
    voice_ambiguity_reason: VoiceAmbiguityReasonValue | None


@dataclass(frozen=True, slots=True)
class VoiceDiagnostics:
    treble_note_count: int
    bass_note_count: int
    chord_node_count: int
    conflict_component_count: int
    two_voice_component_count: int
    crossing_component_count: int
    capacity_exceeded_count: int
    unresolved_staff_count: int
    resolved_count: int
    unknown_count: int


@dataclass(frozen=True, slots=True)
class VoiceSeparationResult:
    notes: tuple[VoicedNote, ...]
    diagnostics: VoiceDiagnostics


@dataclass(frozen=True, slots=True)
class _ChordNode:
    index: int
    notes: tuple[VoiceNote, ...]
    start: Fraction
    duration: Fraction
    end: Fraction
    mean_pitch: float


@dataclass(frozen=True, slots=True)
class _StaffResult:
    assignments: dict[int, VoicedNote]
    chord_node_count: int
    conflict_component_count: int
    two_voice_component_count: int
    crossing_component_count: int
    capacity_exceeded_count: int


def separate_voices(
    notes: tuple[VoiceNote, ...],
    settings: VoiceSettings,
) -> VoiceSeparationResult:
    """Assign forced notation voices independently within each resolved staff."""
    _validate_inputs(notes, settings)
    assignments: dict[int, VoicedNote] = {}
    unresolved_count = 0
    for note in notes:
        if note.staff == "unknown":
            assignments[note.id] = VoicedNote(
                note_id=note.id,
                voice=None,
                voice_confidence=0.0,
                voice_ambiguity_reason="unresolved_staff",
            )
            unresolved_count += 1

    resolved_staff_results = [
        _separate_staff(
            tuple(note for note in notes if note.staff == staff),
            settings,
        )
        for staff in ("treble", "bass")
    ]
    for staff_result in resolved_staff_results:
        assignments.update(staff_result.assignments)

    ordered = tuple(
        assignments[note.id]
        for note in sorted(
            notes,
            key=lambda item: (item.symbolic_start_beats, item.pitch, item.id),
        )
    )
    return VoiceSeparationResult(
        notes=ordered,
        diagnostics=VoiceDiagnostics(
            treble_note_count=sum(note.staff == "treble" for note in notes),
            bass_note_count=sum(note.staff == "bass" for note in notes),
            chord_node_count=sum(item.chord_node_count for item in resolved_staff_results),
            conflict_component_count=sum(
                item.conflict_component_count for item in resolved_staff_results
            ),
            two_voice_component_count=sum(
                item.two_voice_component_count for item in resolved_staff_results
            ),
            crossing_component_count=sum(
                item.crossing_component_count for item in resolved_staff_results
            ),
            capacity_exceeded_count=sum(
                item.capacity_exceeded_count for item in resolved_staff_results
            ),
            unresolved_staff_count=unresolved_count,
            resolved_count=sum(note.voice is not None for note in ordered),
            unknown_count=sum(note.voice is None for note in ordered),
        ),
    )


def _validate_inputs(notes: tuple[VoiceNote, ...], settings: VoiceSettings) -> None:
    if not notes:
        raise VoiceSeparationError(
            "notes_required",
            "No interpreted notes are available for voice separation.",
        )
    if (
        not math.isfinite(settings.close_separation_semitones)
        or not math.isfinite(settings.high_separation_semitones)
        or settings.close_separation_semitones < 0
        or settings.high_separation_semitones <= 0
        or settings.high_separation_semitones < settings.close_separation_semitones
    ):
        raise VoiceSeparationError(
            "incomplete_interpretation",
            "Voice-separation settings are invalid.",
        )
    if len({note.id for note in notes}) != len(notes) or any(
        note.symbolic_duration_beats <= 0 or note.staff not in {"treble", "bass", "unknown"}
        for note in notes
    ):
        raise VoiceSeparationError(
            "incomplete_interpretation",
            "Interpreted notes are incomplete or invalid.",
        )


def _separate_staff(
    notes: tuple[VoiceNote, ...],
    settings: VoiceSettings,
) -> _StaffResult:
    if not notes:
        return _StaffResult({}, 0, 0, 0, 0, 0)
    nodes = _build_nodes(notes)
    adjacency = _build_conflicts(nodes)
    assignments: dict[int, VoicedNote] = {}
    conflict_components = _connected_components(
        {node.index for node in nodes if adjacency[node.index]},
        adjacency,
    )
    two_voice_count = 0
    crossing_count = 0
    capacity_note_count = 0

    conflicted_indexes = {index for component in conflict_components for index in component}
    for node in nodes:
        if node.index not in conflicted_indexes:
            _assign_node(assignments, node, voice=1, confidence=1.0, reason=None)

    by_index = {node.index: node for node in nodes}
    for component in conflict_components:
        remaining, capacity_indexes = _remove_capacity_excess(component, by_index)
        for index in capacity_indexes:
            node = by_index[index]
            capacity_note_count += len(node.notes)
            _assign_node(
                assignments,
                node,
                voice=None,
                confidence=0.0,
                reason="voice_capacity_exceeded",
            )

        remaining_adjacency = {index: adjacency[index] & remaining for index in remaining}
        colored_components = _connected_components(remaining, remaining_adjacency)
        for colored_component in colored_components:
            if not any(remaining_adjacency[index] for index in colored_component):
                for index in colored_component:
                    _assign_node(
                        assignments,
                        by_index[index],
                        voice=1,
                        confidence=1.0,
                        reason=None,
                    )
                continue
            two_voice_count += 1
            crossed = _assign_two_voice_component(
                colored_component,
                remaining_adjacency,
                by_index,
                settings,
                assignments,
            )
            crossing_count += crossed

    return _StaffResult(
        assignments=assignments,
        chord_node_count=len(nodes),
        conflict_component_count=len(conflict_components),
        two_voice_component_count=two_voice_count,
        crossing_component_count=crossing_count,
        capacity_exceeded_count=capacity_note_count,
    )


def _build_nodes(notes: tuple[VoiceNote, ...]) -> tuple[_ChordNode, ...]:
    grouped: dict[tuple[Fraction, Fraction], list[VoiceNote]] = {}
    for note in notes:
        grouped.setdefault((note.symbolic_start_beats, note.symbolic_duration_beats), []).append(
            note
        )
    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            tuple(sorted((note.pitch, note.id) for note in item[1])),
        ),
    )
    return tuple(
        _ChordNode(
            index=index,
            notes=tuple(sorted(group_notes, key=lambda item: (item.pitch, item.id))),
            start=key[0],
            duration=key[1],
            end=key[0] + key[1],
            mean_pitch=fmean(note.pitch for note in group_notes),
        )
        for index, (key, group_notes) in enumerate(ordered_groups)
    )


def _build_conflicts(nodes: tuple[_ChordNode, ...]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {node.index: set() for node in nodes}
    active: list[_ChordNode] = []
    for node in nodes:
        active = [candidate for candidate in active if candidate.end > node.start]
        for candidate in active:
            adjacency[node.index].add(candidate.index)
            adjacency[candidate.index].add(node.index)
        active.append(node)
    return adjacency


def _connected_components(
    indexes: set[int],
    adjacency: dict[int, set[int]],
) -> tuple[frozenset[int], ...]:
    remaining = set(indexes)
    components: list[frozenset[int]] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(sorted(adjacency[current] & remaining, reverse=True))
        remaining.difference_update(component)
        components.append(frozenset(component))
    return tuple(components)


def _remove_capacity_excess(
    component: frozenset[int],
    nodes: dict[int, _ChordNode],
) -> tuple[set[int], frozenset[int]]:
    kept: set[int] = set()
    capacity: set[int] = set()
    active: list[int] = []
    for index in sorted(component, key=lambda item: _node_order(nodes[item])):
        node = nodes[index]
        active = [candidate for candidate in active if nodes[candidate].end > node.start]
        candidates = [*active, index]
        if len(candidates) > 2:
            excess = max(candidates, key=lambda item: _capacity_priority(nodes[item]))
            capacity.add(excess)
            kept.discard(excess)
            active = [candidate for candidate in candidates if candidate != excess]
        else:
            active = candidates
        if index not in capacity:
            kept.add(index)
    return kept, frozenset(capacity)


def _node_order(node: _ChordNode) -> tuple[Fraction, Fraction, tuple[tuple[int, int], ...]]:
    return (
        node.start,
        node.duration,
        tuple((note.pitch, note.id) for note in node.notes),
    )


def _capacity_priority(
    node: _ChordNode,
) -> tuple[Fraction, int, int]:
    return (
        node.start,
        max(note.pitch for note in node.notes),
        max(note.id for note in node.notes),
    )


def _assign_two_voice_component(
    component: frozenset[int],
    adjacency: dict[int, set[int]],
    nodes: dict[int, _ChordNode],
    settings: VoiceSettings,
    assignments: dict[int, VoicedNote],
) -> int:
    colors: dict[int, int] = {}
    for start in sorted(component, key=lambda item: _node_order(nodes[item])):
        if start in colors:
            continue
        colors[start] = 0
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in sorted(adjacency[current] & component):
                expected = 1 - colors[current]
                existing = colors.get(neighbor)
                if existing is None:
                    colors[neighbor] = expected
                    stack.append(neighbor)
                elif existing != expected:
                    raise VoiceSeparationError(
                        "incomplete_interpretation",
                        "Voice conflicts could not be represented by two notation voices.",
                    )

    upper_color = _upper_color(component, colors, nodes)
    voice_by_index: dict[int, VoiceValue] = {
        index: 1 if color == upper_color else 2 for index, color in colors.items()
    }
    component_crossed = False
    for index in sorted(component, key=lambda item: _node_order(nodes[item])):
        node = nodes[index]
        neighbors = adjacency[index] & component
        opposite_pitch = fmean(nodes[neighbor].mean_pitch for neighbor in neighbors)
        voice = voice_by_index[index]
        signed_separation = (
            node.mean_pitch - opposite_pitch if voice == 1 else opposite_pitch - node.mean_pitch
        )
        separation = abs(signed_separation)
        confidence = min(1.0, separation / settings.high_separation_semitones)
        reason: VoiceAmbiguityReasonValue | None = None
        resolved_voice: VoiceValue | None = voice
        if signed_separation < 0:
            resolved_voice = None
            reason = "crossing"
            component_crossed = True
        elif separation < settings.close_separation_semitones:
            resolved_voice = None
            reason = "close_alternative"
        _assign_node(
            assignments,
            node,
            voice=resolved_voice,
            confidence=confidence,
            reason=reason,
        )
    return int(component_crossed)


def _upper_color(
    component: frozenset[int],
    colors: dict[int, int],
    nodes: dict[int, _ChordNode],
) -> int:
    grouped = {
        color: tuple(index for index in component if colors[index] == color) for color in (0, 1)
    }

    def rank(indexes: tuple[int, ...]) -> tuple[float, tuple[tuple[float, int], ...]]:
        pitches = [note.pitch for index in indexes for note in nodes[index].notes]
        signature = tuple(
            sorted(
                (nodes[index].mean_pitch, min(note.id for note in nodes[index].notes))
                for index in indexes
            )
        )
        return fmean(pitches), signature

    return max((0, 1), key=lambda color: rank(grouped[color]))


def _assign_node(
    assignments: dict[int, VoicedNote],
    node: _ChordNode,
    *,
    voice: VoiceValue | None,
    confidence: float,
    reason: VoiceAmbiguityReasonValue | None,
) -> None:
    for note in node.notes:
        assignments[note.id] = VoicedNote(
            note_id=note.id,
            voice=voice,
            voice_confidence=confidence,
            voice_ambiguity_reason=reason,
        )
