from fractions import Fraction

import pytest

from app.symbolic.timing import (
    RawTimingNote,
    TimingAnalysisError,
    TimingSettings,
    group_chords,
    quantize_timing,
    raw_notes_fingerprint,
)


def note(
    note_id: int,
    pitch: int,
    start: float,
    end: float,
    confidence: float | None = 0.9,
) -> RawTimingNote:
    return RawTimingNote(note_id, pitch, start, end, confidence)


def test_chord_grouping_does_not_chain_tolerance() -> None:
    groups = group_chords(
        (
            note(1, 60, 0.0, 0.4),
            note(2, 64, 0.05, 0.4),
            note(3, 67, 0.10, 0.4),
        ),
        tolerance_seconds=0.06,
    )

    assert [group.note_ids for group in groups] == [(1, 2), (3,)]
    assert groups[0].onset_seconds == pytest.approx(0.025)


def test_raw_note_fingerprint_is_order_independent_but_evidence_sensitive() -> None:
    first = note(1, 60, 0.0, 0.5)
    second = note(2, 64, 0.5, 1.0)

    assert raw_notes_fingerprint((first, second)) == raw_notes_fingerprint((second, first))
    assert raw_notes_fingerprint((first, second)) != raw_notes_fingerprint(
        (first, note(2, 64, 0.51, 1.0))
    )


def test_quantization_with_override_aligns_chords_and_dotted_durations() -> None:
    result = quantize_timing(
        (
            note(1, 60, 0.0, 0.74),
            note(2, 64, 0.03, 0.75),
            note(3, 67, 0.5, 1.0),
        ),
        TimingSettings(),
        tempo_bpm=120,
    )

    by_id = {item.note_id: item for item in result.notes}
    assert by_id[1].symbolic_start_beats == Fraction(0)
    assert by_id[2].symbolic_start_beats == Fraction(0)
    assert by_id[1].symbolic_duration_beats == Fraction(3, 2)
    assert by_id[3].symbolic_start_beats == Fraction(1)
    assert result.tempo_source == "override"
    assert result.measure_origin_source == "default"


def test_automatic_tempo_accepts_clear_120_bpm_quarter_notes() -> None:
    result = quantize_timing(
        (
            note(1, 60, 0.0, 0.4),
            note(2, 62, 0.5, 0.9),
            note(3, 64, 1.0, 1.4),
            note(4, 65, 1.5, 1.9),
            note(5, 67, 2.0, 2.4),
        ),
        TimingSettings(),
    )

    assert result.selected_tempo_bpm == pytest.approx(120, abs=0.1)
    assert result.tempo_source == "estimated"
    assert result.diagnostics.residual == pytest.approx(0)
    assert result.diagnostics.inlier_coverage == pytest.approx(1)


def test_automatic_tempo_treats_worker_frame_jitter_as_one_tempo_neighborhood() -> None:
    result = quantize_timing(
        (
            note(1, 60, 0.25541950113378686, 0.603718820861678),
            note(2, 62, 0.7546485260770975, 1.1029478458049886),
            note(3, 64, 1.253877551020408, 1.5905668934240362),
            note(4, 65, 1.7531065759637188, 2.079455782312925),
            note(5, 67, 2.253619501133787, 2.6019188208616777),
        ),
        TimingSettings(),
    )

    assert result.selected_tempo_bpm == pytest.approx(120.19, abs=0.1)
    assert result.diagnostics.score_margin is not None
    assert result.diagnostics.score_margin >= 0.03


def test_automatic_tempo_rejects_sparse_evidence() -> None:
    with pytest.raises(TimingAnalysisError, match="enough pulse evidence") as error:
        quantize_timing(
            (
                note(1, 60, 0.0, 0.4),
                note(2, 64, 0.5, 0.9),
                note(3, 67, 1.0, 1.4),
            ),
            TimingSettings(),
        )

    assert error.value.code == "tempo_ambiguous"


def test_same_pitch_collision_repairs_the_whole_later_chord() -> None:
    result = quantize_timing(
        (
            note(1, 60, 0.0, 0.12),
            note(2, 60, 0.13, 0.3),
            note(3, 64, 0.14, 0.3),
        ),
        TimingSettings(chord_tolerance_seconds=0.01),
        tempo_bpm=120,
    )
    by_id = {item.note_id: item for item in result.notes}

    assert by_id[2].symbolic_start_beats == Fraction(1, 4)
    assert by_id[3].symbolic_start_beats == Fraction(1, 4)
    assert by_id[1].symbolic_duration_beats == Fraction(1, 4)


def test_dense_same_pitch_repetition_fails_when_repair_exceeds_limit() -> None:
    with pytest.raises(TimingAnalysisError) as error:
        quantize_timing(
            (
                note(1, 60, 0.0, 0.02),
                note(2, 60, 0.03, 0.05),
                note(3, 60, 0.06, 0.08),
            ),
            TimingSettings(
                chord_tolerance_seconds=0.0,
                same_pitch_repair_tolerance_beats=Fraction(0),
            ),
            tempo_bpm=120,
        )

    assert error.value.code == "rhythm_too_dense"


def test_measure_origin_override_can_create_measure_zero_pickup_position() -> None:
    result = quantize_timing(
        (note(1, 60, 0.0, 0.4),),
        TimingSettings(),
        tempo_bpm=120,
        meter_numerator=4,
        meter_denominator=4,
        measure_origin_seconds=0.5,
    )

    assert result.notes[0].symbolic_start_beats == Fraction(-1)
    assert result.notes[0].measure_number == 0
    assert result.notes[0].beat_in_measure == Fraction(4)
    assert result.measure_origin_source == "override"


def test_invalid_meter_and_tempo_are_rejected() -> None:
    with pytest.raises(TimingAnalysisError) as meter_error:
        quantize_timing(
            (note(1, 60, 0.0, 0.4),),
            TimingSettings(),
            tempo_bpm=120,
            meter_numerator=6,
            meter_denominator=8,
        )
    with pytest.raises(TimingAnalysisError) as tempo_error:
        quantize_timing(
            (note(1, 60, 0.0, 0.4),),
            TimingSettings(),
            tempo_bpm=300,
        )

    assert meter_error.value.code == "unsupported_meter"
    assert tempo_error.value.code == "invalid_tempo"
