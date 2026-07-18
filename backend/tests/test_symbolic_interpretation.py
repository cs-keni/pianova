from fractions import Fraction

import pytest

from app.symbolic.interpretation import (
    InterpretationError,
    InterpretationNote,
    InterpretationSettings,
    interpret_notes,
)


def note(
    note_id: int,
    pitch: int,
    start: int | Fraction,
    group: int,
    duration: Fraction = Fraction(1),
) -> InterpretationNote:
    return InterpretationNote(
        id=note_id,
        pitch=pitch,
        symbolic_start_beats=Fraction(start),
        symbolic_duration_beats=duration,
        chord_group=group,
    )


def test_assigns_obvious_two_hand_chords_and_independent_staves() -> None:
    result = interpret_notes(
        (
            note(1, 43, 0, 1),
            note(2, 67, 0, 1),
            note(3, 45, 1, 2),
            note(4, 69, 1, 2),
            note(5, 47, 2, 3),
            note(6, 71, 2, 3),
        ),
        InterpretationSettings(),
    )
    by_id = {item.note_id: item for item in result.notes}

    assert [by_id[index].hand for index in (1, 3, 5)] == ["left"] * 3
    assert [by_id[index].hand for index in (2, 4, 6)] == ["right"] * 3
    assert [by_id[index].staff for index in (1, 3, 5)] == ["bass"] * 3
    assert [by_id[index].staff for index in (2, 4, 6)] == ["treble"] * 3
    assert result.diagnostics.unknown_hand_count == 0


def test_middle_register_single_note_remains_explicitly_unknown() -> None:
    result = interpret_notes((note(1, 60, 0, 1),), InterpretationSettings())
    interpreted = result.notes[0]

    assert interpreted.hand == "unknown"
    assert interpreted.staff == "unknown"
    assert interpreted.hand_confidence == pytest.approx(0)
    assert interpreted.hand_ambiguity_reason == "insufficient_context"


def test_passage_continuity_keeps_a_descending_line_in_one_hand() -> None:
    result = interpret_notes(
        (
            note(1, 72, 0, 1),
            note(2, 69, 1, 2),
            note(3, 65, 2, 3),
            note(4, 62, 3, 4),
        ),
        InterpretationSettings(ambiguity_margin=0.1),
    )

    assert [item.hand for item in result.notes] == ["right"] * 4


def test_staff_is_not_derived_from_hand() -> None:
    result = interpret_notes(
        (
            note(1, 36, 0, 1),
            note(2, 60, 0, 1),
            note(3, 38, 1, 2),
            note(4, 57, 1, 2),
            note(5, 40, 2, 3),
            note(6, 53, 2, 3),
        ),
        InterpretationSettings(ambiguity_margin=0.05),
    )
    by_id = {item.note_id: item for item in result.notes}

    assert by_id[2].hand == "right"
    assert by_id[2].staff == "bass"


def test_wide_chord_uses_typed_ambiguity_reason_when_margin_is_close() -> None:
    result = interpret_notes(
        (
            note(1, 48, 0, 1),
            note(2, 60, 0, 1),
            note(3, 72, 0, 1),
            note(4, 50, 1, 2),
            note(5, 62, 1, 2),
            note(6, 74, 1, 2),
        ),
        InterpretationSettings(ambiguity_margin=10),
    )

    assert all(item.hand == "unknown" for item in result.notes)
    assert {item.hand_ambiguity_reason for item in result.notes} == {"wide_chord"}


def test_output_is_stable_under_input_reordering() -> None:
    notes = (
        note(1, 43, 0, 1),
        note(2, 67, 0, 1),
        note(3, 45, 1, 2),
        note(4, 69, 1, 2),
    )

    forward = interpret_notes(notes, InterpretationSettings())
    reverse = interpret_notes(tuple(reversed(notes)), InterpretationSettings())

    assert forward == reverse


def test_rejects_invalid_group_evidence_and_excess_work() -> None:
    with pytest.raises(InterpretationError) as invalid:
        interpret_notes(
            (note(1, 60, 0, 1), note(2, 64, 1, 1)),
            InterpretationSettings(),
        )
    assert invalid.value.code == "incomplete_quantization"

    dense = tuple(
        note(group * 3 + offset, 48 + offset * 12, group, group + 1)
        for group in range(3)
        for offset in range(3)
    )
    with pytest.raises(InterpretationError) as too_complex:
        interpret_notes(
            dense,
            InterpretationSettings(maximum_transition_evaluations=1),
        )
    assert too_complex.value.code == "interpretation_too_complex"
