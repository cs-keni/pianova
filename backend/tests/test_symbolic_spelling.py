import math

import pytest

from app.symbolic.spelling import (
    KeyOverride,
    SpellingError,
    SpellingNote,
    SpellingSettings,
    canonical_tonic,
    key_signature_fifths,
    midi_pitch_for_spelling,
    spell_notes,
)


def note(
    note_id: int,
    pitch: int,
    start: float,
    group: int,
    *,
    duration: float = 1.0,
    staff: str = "treble",
    voice: int | None = 1,
) -> SpellingNote:
    return SpellingNote(
        id=note_id,
        pitch=pitch,
        symbolic_start_beats=start,
        symbolic_duration_beats=duration,
        chord_group=group,
        staff=staff,  # type: ignore[arg-type]
        voice=voice,
    )


def override(step: str, alter: int, mode: str) -> KeyOverride:
    return KeyOverride(step, alter, mode)  # type: ignore[arg-type]


def test_requires_complete_finite_voiced_notes_and_valid_settings() -> None:
    with pytest.raises(SpellingError) as missing:
        spell_notes((), SpellingSettings())
    assert missing.value.code == "notes_required"

    invalid_notes = (
        note(1, 60, 0, 1, duration=0),
        note(2, 128, 1, 2),
        note(3, 62, math.nan, 3),
        note(4, 64, 3, 0),
        note(5, 65, 4, 5, voice=0),
    )
    for invalid_note in invalid_notes:
        with pytest.raises(SpellingError) as incomplete:
            spell_notes((invalid_note,), SpellingSettings())
        assert incomplete.value.code == "incomplete_voice_state"

    with pytest.raises(SpellingError) as duplicate:
        spell_notes((note(1, 60, 0, 1), note(1, 64, 1, 2)), SpellingSettings())
    assert duplicate.value.code == "incomplete_voice_state"

    with pytest.raises(SpellingError) as invalid_settings:
        spell_notes((note(1, 60, 0, 1),), SpellingSettings(spelling_close_margin=1.1))
    assert invalid_settings.value.code == "incomplete_voice_state"


@pytest.mark.parametrize(
    ("pitch_class", "mode", "step", "alter", "fifths"),
    [
        (1, "major", "D", -1, -5),
        (11, "major", "B", 0, 5),
        (6, "major", "G", -1, -6),
        (8, "minor", "G", 1, 5),
        (10, "minor", "B", -1, -5),
        (3, "minor", "E", -1, -6),
    ],
)
def test_canonical_tonic_uses_fewer_accidentals_and_flat_six_accidental_ties(
    pitch_class: int,
    mode: str,
    step: str,
    alter: int,
    fifths: int,
) -> None:
    key = canonical_tonic(pitch_class, mode)  # type: ignore[arg-type]

    assert (key.tonic_step, key.tonic_alter) == (step, alter)
    assert key_signature_fifths(key) == fifths


def test_canonical_tonic_table_locks_all_24_pitch_class_keys() -> None:
    expected = {
        "major": (
            ("C", 0),
            ("D", -1),
            ("D", 0),
            ("E", -1),
            ("E", 0),
            ("F", 0),
            ("G", -1),
            ("G", 0),
            ("A", -1),
            ("A", 0),
            ("B", -1),
            ("B", 0),
        ),
        "minor": (
            ("C", 0),
            ("C", 1),
            ("D", 0),
            ("E", -1),
            ("E", 0),
            ("F", 0),
            ("F", 1),
            ("G", 0),
            ("G", 1),
            ("A", 0),
            ("B", -1),
            ("B", 0),
        ),
    }

    for mode, names in expected.items():
        actual: list[tuple[str, int]] = []
        for pitch_class in range(12):
            key = canonical_tonic(pitch_class, mode)  # type: ignore[arg-type]
            actual.append((key.tonic_step, key.tonic_alter))
        assert tuple(actual) == names


def test_canonical_tonic_rejects_values_outside_the_pitch_class_contract() -> None:
    with pytest.raises(ValueError):
        canonical_tonic(12, "major")


def test_clear_major_and_minor_profiles_produce_normalized_pearson_margins() -> None:
    major_profile = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
    minor_profile = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
    c_major = tuple(
        note(
            pitch_class + 1,
            60 + pitch_class,
            pitch_class,
            pitch_class + 1,
            duration=duration,
        )
        for pitch_class, duration in enumerate(major_profile)
    )
    a_minor = tuple(
        note(
            index + 1,
            60 + pitch_class,
            index,
            index + 1,
            duration=minor_profile[(pitch_class - 9) % 12],
        )
        for index, pitch_class in enumerate(range(12))
    )

    major = spell_notes(c_major, SpellingSettings())
    minor = spell_notes(a_minor, SpellingSettings())

    assert (major.key.tonic_step, major.key.tonic_alter, major.key.mode) == ("C", 0, "major")
    assert (minor.key.tonic_step, minor.key.tonic_alter, minor.key.mode) == ("A", 0, "minor")
    assert major.diagnostics.best_key_correlation == pytest.approx(1)
    assert minor.diagnostics.best_key_correlation == pytest.approx(1)
    assert major.key.confidence == pytest.approx(
        (major.diagnostics.best_key_correlation - major.diagnostics.runner_up_key_correlation) / 2
    )
    assert 0 < major.key.confidence <= 1


def test_duration_weighting_is_decisive_when_attack_counts_are_uniform() -> None:
    profile = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
    notes = tuple(
        note(index + 1, 60 + index, index, index + 1, duration=profile[index])
        for index in range(12)
    )

    result = spell_notes(notes, SpellingSettings())

    assert result.key.ambiguity_reason is None
    assert (result.key.tonic_step, result.key.mode) == ("C", "major")


def test_minimum_evidence_gates_run_before_correlation_and_boundaries_are_inclusive() -> None:
    too_few_notes = tuple(note(index + 1, 60 + index % 4, index, index + 1) for index in range(7))
    too_few_classes = tuple(note(index + 1, 60 + index % 2, index, index + 1) for index in range(8))
    at_boundaries = tuple(
        note(index + 1, (60, 64, 67)[index % 3], index, index + 1) for index in range(8)
    )

    for gated in (too_few_notes, too_few_classes):
        result = spell_notes(gated, SpellingSettings())
        assert result.key.ambiguity_reason == "insufficient_notes"
        assert result.key.confidence == 0
        assert result.diagnostics.best_key is None
        assert len(result.diagnostics.plausible_keys) == 24

    boundary = spell_notes(at_boundaries, SpellingSettings())
    assert boundary.key.ambiguity_reason != "insufficient_notes"
    assert boundary.diagnostics.best_key is not None


@pytest.mark.parametrize(
    "durations",
    [
        (1.0,) * 12,
        (1.0000001,) + (1.0,) * 11,
    ],
)
def test_uniform_and_near_uniform_histograms_are_typed_ambiguous_without_correlation(
    durations: tuple[float, ...],
) -> None:
    notes = tuple(
        note(index + 1, 60 + index, index, index + 1, duration=duration)
        for index, duration in enumerate(durations)
    )

    result = spell_notes(notes, SpellingSettings())

    assert result.key.ambiguity_reason == "ambiguous_key"
    assert result.key.confidence == 0
    assert result.diagnostics.best_key is None
    assert len(result.diagnostics.plausible_keys) == 24


def test_override_bypasses_key_evidence_gates_and_invalid_names_are_typed_errors() -> None:
    result = spell_notes(
        (note(1, 66, 0, 1),),
        SpellingSettings(),
        key_override=override("D", 0, "major"),
    )

    assert (result.key.tonic_step, result.key.tonic_alter, result.key.mode) == ("D", 0, "major")
    assert result.key.source == "override"
    assert result.key.confidence is None

    with pytest.raises(SpellingError) as invalid:
        spell_notes(
            (note(1, 60, 0, 1),),
            SpellingSettings(),
            key_override=override("D", 1, "major"),
        )
    assert invalid.value.code == "invalid_key_override"


@pytest.mark.parametrize(
    ("key", "pitch", "expected"),
    [
        (override("C", 0, "major"), 60, ("C", 0, 4)),
        (override("D", 0, "major"), 66, ("F", 1, 4)),
        (override("G", 0, "major"), 66, ("F", 1, 4)),
        (override("F", 0, "major"), 70, ("B", -1, 4)),
    ],
)
def test_diatonic_and_spec_case_spellings_follow_the_key(
    key: KeyOverride,
    pitch: int,
    expected: tuple[str, int, int],
) -> None:
    result = spell_notes((note(1, pitch, 0, 1),), SpellingSettings(), key_override=key)
    spelled = result.notes[0]

    assert (spelled.step, spelled.alter, spelled.octave) == expected
    assert spelled.spelling_ambiguity_reason is None


def test_chord_third_stacking_breaks_a_key_proximity_tie() -> None:
    result = spell_notes(
        (
            note(1, 62, 0, 1),
            note(2, 66, 0, 1),
        ),
        SpellingSettings(),
        key_override=override("C", 0, "major"),
    )
    second = result.notes[1]

    assert (second.step, second.alter) == ("F", 1)
    assert second.spelling_confidence == pytest.approx(2 / 12)
    assert result.diagnostics.chord_consistency_application_count == 1


@pytest.mark.parametrize(
    ("pitches", "expected_middle"),
    [
        ((60, 61, 62), ("C", 1)),
        ((62, 61, 60), ("D", -1)),
    ],
)
def test_chromatic_neighbor_rule_respects_ascending_and_descending_motion(
    pitches: tuple[int, int, int], expected_middle: tuple[str, int]
) -> None:
    notes = tuple(note(index + 1, pitch, index, index + 1) for index, pitch in enumerate(pitches))

    result = spell_notes(
        notes,
        SpellingSettings(spelling_close_margin=0.05),
        key_override=override("G", 0, "major"),
    )

    assert (result.notes[1].step, result.notes[1].alter) == expected_middle
    assert result.notes[1].spelling_confidence == pytest.approx(1 / 12)
    assert result.diagnostics.melodic_rule_application_count == 1


def test_fixed_gap_scale_distinguishes_tie_narrow_and_decisive_wins() -> None:
    tied = spell_notes(
        (note(1, 66, 0, 1),),
        SpellingSettings(),
        key_override=override("C", 0, "major"),
    ).notes[0]
    narrow = spell_notes(
        (note(1, 60, 0, 1), note(2, 61, 1, 2)),
        SpellingSettings(),
        key_override=override("G", 0, "major"),
    ).notes[1]
    decisive = spell_notes(
        (note(1, 66, 0, 1),),
        SpellingSettings(),
        key_override=override("F", 1, "major"),
    ).notes[0]
    singleton = spell_notes(
        (note(1, 62, 0, 1),),
        SpellingSettings(),
        key_override=override("C", 0, "major"),
    ).notes[0]

    assert (tied.spelling_confidence, tied.spelling_ambiguity_reason) == (0, "close_alternative")
    assert narrow.spelling_confidence == pytest.approx(1 / 12)
    assert narrow.spelling_ambiguity_reason == "close_alternative"
    assert decisive.spelling_confidence == 1
    assert decisive.spelling_ambiguity_reason is None
    assert singleton.spelling_confidence == 1
    assert singleton.spelling_ambiguity_reason is None


def test_candidate_tie_break_is_flat_before_sharp_when_close_rejection_is_disabled() -> None:
    result = spell_notes(
        (note(1, 66, 0, 1),),
        SpellingSettings(spelling_close_margin=0),
        key_override=override("C", 0, "major"),
    )

    assert (result.notes[0].step, result.notes[0].alter) == ("G", -1)
    assert result.notes[0].spelling_confidence == 0


def test_insufficient_key_resolves_only_single_name_pitch_classes() -> None:
    pitches = (62, 67, 69, 60, 64, 65, 71)
    result = spell_notes(
        tuple(note(index + 1, pitch, index, index + 1) for index, pitch in enumerate(pitches)),
        SpellingSettings(),
    )
    spelled = {item.note_id: item for item in result.notes}

    assert result.key.ambiguity_reason == "insufficient_notes"
    assert [(spelled[index].step, spelled[index].spelling_confidence) for index in (1, 2, 3)] == [
        ("D", 1),
        ("G", 1),
        ("A", 1),
    ]
    assert all(spelled[index].spelling_ambiguity_reason == "unknown_key" for index in (4, 5, 6, 7))
    assert all(spelled[index].spelling_confidence == 0 for index in (4, 5, 6, 7))


def test_correlated_c_major_a_minor_ambiguity_uses_stable_cross_key_agreement() -> None:
    pitch_classes = (0, 2, 4, 5, 7, 9, 11)
    counts = (1, 1, 1, 2, 2, 2, 1)
    pitches = tuple(
        60 + pitch_class
        for pitch_class, count in zip(pitch_classes, counts, strict=True)
        for _ in range(count)
    )
    notes = tuple(note(index + 1, pitch, index, index + 1) for index, pitch in enumerate(pitches))

    result = spell_notes(notes, SpellingSettings())
    spelled = {item.note_id: item for item in result.notes}

    assert result.key.ambiguity_reason == "ambiguous_key"
    assert result.diagnostics.best_key == "C major"
    assert result.diagnostics.runner_up_key == "A minor"
    assert result.diagnostics.plausible_keys == ("C major", "A minor", "F major")
    assert (spelled[1].step, spelled[1].spelling_confidence) == ("C", 0.5)
    assert spelled[10].spelling_ambiguity_reason == "unknown_key"
    assert spelled[10].spelling_confidence == 0


def test_unknown_key_rejects_different_stable_winners_across_plausible_keys() -> None:
    pitches = (65, 66, 66, 66, 67, 67, 67, 71)
    notes = tuple(note(index + 1, pitch, index, index + 1) for index, pitch in enumerate(pitches))

    result = spell_notes(notes, SpellingSettings())

    assert result.key.ambiguity_reason == "ambiguous_key"
    assert result.diagnostics.plausible_keys == (
        "G major",
        "B minor",
        "G minor",
        "E minor",
        "Gb major",
    )
    assert result.notes[1].spelling_ambiguity_reason == "unknown_key"
    assert result.notes[1].spelling_confidence == 0


def test_unknown_staff_and_voice_keep_deterministic_slots_without_melodic_context() -> None:
    notes = (
        note(4, 66, 0, 4, staff="unknown", voice=None),
        note(3, 62, 0, 3, staff="bass", voice=1),
        note(2, 67, 1, 2, staff="treble", voice=2),
        note(1, 60, 2, 1, staff="treble", voice=1),
    )

    result = spell_notes(notes, SpellingSettings(), key_override=override("D", 0, "major"))

    assert [item.note_id for item in result.notes] == [1, 2, 3, 4]
    assert (result.notes[-1].step, result.notes[-1].alter) == ("F", 1)


def test_octave_boundaries_and_round_trip_preserve_every_midi_pitch() -> None:
    low = spell_notes(
        (note(1, 0, 0, 1),),
        SpellingSettings(),
        key_override=override("C", 1, "minor"),
    ).notes[0]
    c_flat = spell_notes(
        (note(2, 11, 0, 1),),
        SpellingSettings(),
        key_override=override("C", -1, "major"),
    ).notes[0]
    high = spell_notes(
        (note(3, 127, 0, 1),),
        SpellingSettings(),
        key_override=override("C", 0, "major"),
    ).notes[0]

    assert (low.step, low.alter, low.octave) == ("B", 1, -2)
    assert (c_flat.step, c_flat.alter, c_flat.octave) == ("C", -1, 0)
    assert (high.step, high.alter, high.octave) == ("G", 0, 9)
    for source_pitch, spelled in ((0, low), (11, c_flat), (127, high)):
        assert spelled.step is not None
        assert spelled.alter is not None
        assert spelled.octave is not None
        assert midi_pitch_for_spelling(spelled.step, spelled.alter, spelled.octave) == source_pitch


def test_output_and_diagnostics_are_invariant_to_input_order() -> None:
    notes = (
        note(1, 62, 0, 1),
        note(2, 66, 0, 1),
        note(3, 67, 1, 2),
        note(4, 61, 2, 3, staff="bass"),
    )

    forward = spell_notes(notes, SpellingSettings(), key_override=override("C", 0, "major"))
    reverse = spell_notes(
        tuple(reversed(notes)),
        SpellingSettings(),
        key_override=override("C", 0, "major"),
    )

    assert forward == reverse


@pytest.mark.parametrize(
    ("pitches", "expected_key", "expected_spellings"),
    [
        (
            (48, 52, 55, 60, 64, 55, 60, 64, 48, 55, 60, 64, 67, 72),
            ("C", 0, "major"),
            (
                ("C", 0),
                ("E", 0),
                ("G", 0),
                ("C", 0),
                ("E", 0),
                ("G", 0),
                ("C", 0),
                ("E", 0),
                ("C", 0),
                ("G", 0),
                ("C", 0),
                ("E", 0),
                ("G", 0),
                ("C", 0),
            ),
        ),
        (
            (66, 66, 67, 69, 69, 67, 66, 64, 62, 62, 64, 66, 62, 66, 69, 74),
            ("D", 0, "major"),
            (
                ("F", 1),
                ("F", 1),
                ("G", 0),
                ("A", 0),
                ("A", 0),
                ("G", 0),
                ("F", 1),
                ("E", 0),
                ("D", 0),
                ("D", 0),
                ("E", 0),
                ("F", 1),
                ("D", 0),
                ("F", 1),
                ("A", 0),
                ("D", 0),
            ),
        ),
    ],
)
def test_public_domain_ground_truth_excerpts(
    pitches: tuple[int, ...],
    expected_key: tuple[str, int, str],
    expected_spellings: tuple[tuple[str, int], ...],
) -> None:
    notes = tuple(note(index + 1, pitch, index, index + 1) for index, pitch in enumerate(pitches))

    result = spell_notes(notes, SpellingSettings())

    assert (result.key.tonic_step, result.key.tonic_alter, result.key.mode) == expected_key, (
        result.key,
        result.diagnostics,
    )
    assert tuple((item.step, item.alter) for item in result.notes) == expected_spellings
    assert all(item.spelling_ambiguity_reason is None for item in result.notes)
    for source, spelled in zip(notes, result.notes, strict=True):
        assert spelled.step is not None
        assert spelled.alter is not None
        assert spelled.octave is not None
        assert midi_pitch_for_spelling(spelled.step, spelled.alter, spelled.octave) == source.pitch
