from fractions import Fraction

import pytest

from app.symbolic.voices import (
    VoiceNote,
    VoiceSeparationError,
    VoiceSeparationResult,
    VoiceSettings,
    separate_voices,
)


def note(
    note_id: int,
    pitch: int,
    start: int | Fraction,
    duration: int | Fraction = 1,
    staff: str = "treble",
) -> VoiceNote:
    return VoiceNote(
        id=note_id,
        pitch=pitch,
        symbolic_start_beats=Fraction(start),
        symbolic_duration_beats=Fraction(duration),
        staff=staff,  # type: ignore[arg-type]
    )


def assert_voice_invariant(
    inputs: tuple[VoiceNote, ...],
    result: VoiceSeparationResult,
) -> None:
    by_id = {note.note_id: note for note in result.notes}
    for first_index, first in enumerate(inputs):
        first_voice = by_id[first.id].voice
        if first_voice is None or first.staff == "unknown":
            continue
        for second in inputs[first_index + 1 :]:
            if by_id[second.id].voice != first_voice or second.staff != first.staff:
                continue
            overlap = (
                first.symbolic_start_beats
                < second.symbolic_start_beats + second.symbolic_duration_beats
                and second.symbolic_start_beats
                < first.symbolic_start_beats + first.symbolic_duration_beats
            )
            same_chord_node = (
                first.symbolic_start_beats == second.symbolic_start_beats
                and first.symbolic_duration_beats == second.symbolic_duration_beats
            )
            assert not overlap or same_chord_node


def test_requires_notes_and_complete_interpretation() -> None:
    with pytest.raises(VoiceSeparationError) as missing:
        separate_voices((), VoiceSettings())
    assert missing.value.code == "notes_required"

    with pytest.raises(VoiceSeparationError) as incomplete:
        separate_voices((note(1, 60, 0, duration=0),), VoiceSettings())
    assert incomplete.value.code == "incomplete_interpretation"

    with pytest.raises(VoiceSeparationError) as duplicate:
        separate_voices((note(1, 60, 0), note(1, 64, 1)), VoiceSettings())
    assert duplicate.value.code == "incomplete_interpretation"


def test_rejects_invalid_settings() -> None:
    with pytest.raises(VoiceSeparationError) as invalid:
        separate_voices(
            (note(1, 60, 0),),
            VoiceSettings(close_separation_semitones=8, high_separation_semitones=7),
        )
    assert invalid.value.code == "incomplete_interpretation"


def test_monophonic_lines_and_uniform_chords_stay_in_voice_one() -> None:
    notes = (
        note(1, 72, 0),
        note(2, 74, 1),
        note(3, 48, 0, staff="bass"),
        note(4, 52, 1, staff="bass"),
        note(5, 60, 2),
        note(6, 64, 2),
        note(7, 67, 2),
    )
    result = separate_voices(notes, VoiceSettings())

    assert all(item.voice == 1 for item in result.notes)
    assert all(item.voice_confidence == 1 for item in result.notes)
    assert result.diagnostics.chord_node_count == 5
    assert result.diagnostics.conflict_component_count == 0
    assert result.diagnostics.treble_note_count == 5
    assert result.diagnostics.bass_note_count == 2
    assert_voice_invariant(notes, result)


@pytest.mark.parametrize("staff,pitches", [("treble", (76, 60, 62)), ("bass", (52, 36, 38))])
def test_sustained_note_over_moving_line_forces_two_voices(
    staff: str,
    pitches: tuple[int, int, int],
) -> None:
    notes = (
        note(1, pitches[0], 0, duration=3, staff=staff),
        note(2, pitches[1], 1, staff=staff),
        note(3, pitches[2], 2, staff=staff),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[1].voice == 1
    assert by_id[2].voice == 2
    assert by_id[3].voice == 2
    assert result.diagnostics.two_voice_component_count == 1
    assert_voice_invariant(notes, result)


def test_suspension_chain_alternates_conflicting_nodes() -> None:
    notes = (
        note(1, 72, 0, duration=2),
        note(2, 60, 1, duration=2),
        note(3, 74, 2, duration=2),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[1].voice == by_id[3].voice == 1
    assert by_id[2].voice == 2
    assert_voice_invariant(notes, result)


def test_same_onset_with_unequal_durations_forces_two_voices() -> None:
    notes = (
        note(1, 72, 0, duration=2),
        note(2, 60, 0, duration=1),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[1].voice == 1
    assert by_id[2].voice == 2
    assert by_id[1].voice_confidence == pytest.approx(1)
    assert by_id[2].voice_confidence == pytest.approx(1)
    assert result.diagnostics.chord_node_count == 2
    assert_voice_invariant(notes, result)


def test_three_stream_clique_marks_deterministic_excess_unknown_and_colors_rest() -> None:
    notes = (
        note(1, 72, 0, duration=4),
        note(2, 60, 1, duration=3),
        note(3, 84, 2, duration=1),
        note(4, 76, 4, duration=1),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[3].voice is None
    assert by_id[3].voice_confidence == 0
    assert by_id[3].voice_ambiguity_reason == "voice_capacity_exceeded"
    assert by_id[1].voice == 1
    assert by_id[2].voice == 2
    assert by_id[4].voice == 1
    assert result.diagnostics.capacity_exceeded_count == 1
    assert_voice_invariant(notes, result)


def test_capacity_priority_uses_latest_onset_then_highest_pitch_then_id() -> None:
    notes = (
        note(1, 60, 0, duration=4),
        note(3, 84, 0, duration=2),
        note(4, 84, 0, duration=3),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {item.note_id: item for item in result.notes}

    assert by_id[4].voice is None
    assert by_id[4].voice_ambiguity_reason == "voice_capacity_exceeded"
    assert by_id[1].voice is not None
    assert by_id[3].voice is not None
    assert_voice_invariant(notes, result)


def test_unresolved_staff_is_a_successful_typed_unknown() -> None:
    notes = (note(1, 60, 0, staff="unknown"), note(2, 72, 1))
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[1].voice is None
    assert by_id[1].voice_confidence == 0
    assert by_id[1].voice_ambiguity_reason == "unresolved_staff"
    assert by_id[2].voice == 1
    assert result.diagnostics.unresolved_staff_count == 1
    assert result.diagnostics.unknown_count == 1
    assert_voice_invariant(notes, result)


def test_close_streams_return_decision_scores_and_close_alternative() -> None:
    notes = (
        note(1, 64, 0, duration=3),
        note(2, 62, 1),
        note(3, 63, 2),
    )
    result = separate_voices(
        notes,
        VoiceSettings(close_separation_semitones=3, high_separation_semitones=8),
    )

    assert all(item.voice is None for item in result.notes)
    assert {item.voice_ambiguity_reason for item in result.notes} == {"close_alternative"}
    assert all(0 < item.voice_confidence < 1 for item in result.notes)
    assert_voice_invariant(notes, result)


def test_crossing_stream_returns_typed_crossing_unknown() -> None:
    notes = (
        note(1, 70, 0, duration=4),
        note(2, 50, 1),
        note(3, 60, 2),
        note(4, 80, 3),
    )
    result = separate_voices(notes, VoiceSettings())
    by_id = {note.note_id: note for note in result.notes}

    assert by_id[4].voice is None
    assert by_id[4].voice_ambiguity_reason == "crossing"
    assert by_id[4].voice_confidence == 1
    assert result.diagnostics.crossing_component_count == 1
    assert_voice_invariant(notes, result)


def test_output_and_diagnostics_are_stable_under_input_reordering() -> None:
    notes = (
        note(1, 76, 0, duration=3),
        note(2, 60, 1),
        note(3, 62, 2),
        note(4, 48, 0, staff="bass"),
        note(5, 52, 1, staff="bass"),
    )

    forward = separate_voices(notes, VoiceSettings())
    reverse = separate_voices(tuple(reversed(notes)), VoiceSettings())

    assert forward == reverse
    assert_voice_invariant(notes, forward)
