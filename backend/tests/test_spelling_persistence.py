import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    KeyAmbiguityReason,
    KeyMode,
    KeySource,
    NoteEvent,
    Project,
    SpellingAmbiguityReason,
)


def test_key_persistence_accepts_exactly_the_four_valid_states(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        session.add_all(
            [
                Project(title="Unprocessed key"),
                Project(
                    title="Estimated key",
                    key_tonic_step="C",
                    key_tonic_alter=0,
                    key_mode=KeyMode.MAJOR,
                    key_confidence=0.75,
                    key_source=KeySource.ESTIMATED,
                    current_spelling_run_id=11,
                ),
                Project(
                    title="Unknown estimated key",
                    key_confidence=0.0,
                    key_ambiguity_reason=KeyAmbiguityReason.INSUFFICIENT_NOTES,
                    key_source=KeySource.ESTIMATED,
                    current_spelling_run_id=12,
                ),
                Project(
                    title="Overridden key",
                    key_tonic_step="E",
                    key_tonic_alter=-1,
                    key_mode=KeyMode.MINOR,
                    key_source=KeySource.OVERRIDE,
                    current_spelling_run_id=13,
                ),
            ]
        )
        session.commit()


@pytest.mark.parametrize(
    "values",
    [
        {"current_spelling_run_id": 1},
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 0.5,
            "key_source": KeySource.ESTIMATED,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 0.5,
            "key_ambiguity_reason": KeyAmbiguityReason.AMBIGUOUS_KEY,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_confidence": 0.0,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_confidence": 0.0,
            "key_ambiguity_reason": KeyAmbiguityReason.AMBIGUOUS_KEY,
            "key_source": KeySource.OVERRIDE,
            "current_spelling_run_id": 1,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 0.5,
            "key_source": KeySource.OVERRIDE,
            "current_spelling_run_id": 1,
        },
    ],
)
def test_key_persistence_rejects_every_other_state_combination(
    client: TestClient,
    values: dict[str, object],
) -> None:
    with client.app.state.session_factory() as session:
        session.add(Project(title="Invalid key state", **values))

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "values",
    [
        {
            "key_tonic_step": "H",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 0.5,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 2,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 0.5,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": -0.01,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {
            "key_tonic_step": "C",
            "key_tonic_alter": 0,
            "key_mode": KeyMode.MAJOR,
            "key_confidence": 1.01,
            "key_source": KeySource.ESTIMATED,
            "current_spelling_run_id": 1,
        },
        {"spelling_revision": -1},
    ],
)
def test_key_persistence_rejects_value_and_revision_bounds(
    client: TestClient,
    values: dict[str, object],
) -> None:
    with client.app.state.session_factory() as session:
        session.add(Project(title="Invalid key bounds", **values))

        with pytest.raises(IntegrityError):
            session.commit()


def test_spelling_persistence_accepts_exactly_the_three_valid_states(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Valid spelling states")
        session.add(project)
        session.flush()
        session.add_all(
            [
                _note(project.id, pitch=60),
                _note(
                    project.id,
                    pitch=61,
                    step="C",
                    alter=1,
                    octave=4,
                    confidence=0.75,
                ),
                _note(
                    project.id,
                    pitch=62,
                    confidence=0.0,
                    reason=SpellingAmbiguityReason.UNKNOWN_KEY,
                ),
            ]
        )
        session.commit()


@pytest.mark.parametrize(
    ("step", "alter", "octave", "confidence", "reason"),
    [
        ("C", 0, 4, None, None),
        (None, None, None, 0.5, None),
        (None, None, None, None, SpellingAmbiguityReason.UNKNOWN_KEY),
        ("C", 0, 4, 0.5, SpellingAmbiguityReason.CLOSE_ALTERNATIVE),
        ("C", None, 4, 0.5, None),
        (None, 0, None, 0.5, SpellingAmbiguityReason.UNKNOWN_KEY),
    ],
)
def test_spelling_persistence_rejects_every_other_state_combination(
    client: TestClient,
    step: str | None,
    alter: int | None,
    octave: int | None,
    confidence: float | None,
    reason: SpellingAmbiguityReason | None,
) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Invalid spelling state")
        session.add(project)
        session.flush()
        session.add(
            _note(
                project.id,
                pitch=60,
                step=step,
                alter=alter,
                octave=octave,
                confidence=confidence,
                reason=reason,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("step", "alter", "octave", "confidence"),
    [
        ("H", 0, 4, 0.5),
        ("C", -3, 4, 0.5),
        ("C", 3, 4, 0.5),
        ("C", 0, -3, 0.5),
        ("C", 0, 10, 0.5),
        ("C", 0, 4, -0.01),
        ("C", 0, 4, 1.01),
    ],
)
def test_spelling_persistence_rejects_value_and_score_bounds(
    client: TestClient,
    step: str,
    alter: int,
    octave: int,
    confidence: float,
) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Invalid spelling bounds")
        session.add(project)
        session.flush()
        session.add(
            _note(
                project.id,
                pitch=60,
                step=step,
                alter=alter,
                octave=octave,
                confidence=confidence,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def _note(
    project_id: str,
    *,
    pitch: int,
    step: str | None = None,
    alter: int | None = None,
    octave: int | None = None,
    confidence: float | None = None,
    reason: SpellingAmbiguityReason | None = None,
) -> NoteEvent:
    return NoteEvent(
        project_id=project_id,
        pitch=pitch,
        velocity=80,
        raw_start_seconds=0.0,
        raw_end_seconds=0.5,
        spelled_step=step,
        spelled_alter=alter,
        spelled_octave=octave,
        spelling_confidence=confidence,
        spelling_ambiguity_reason=reason,
    )
