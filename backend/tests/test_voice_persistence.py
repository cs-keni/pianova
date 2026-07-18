import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.models.entities import NoteEvent, Project, VoiceAmbiguityReason


def test_voice_persistence_accepts_exactly_the_three_valid_states(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Valid voice states")
        session.add(project)
        session.flush()
        session.add_all(
            [
                _note(project.id, pitch=60),
                _note(project.id, pitch=64, voice=1, confidence=0.75),
                _note(
                    project.id,
                    pitch=67,
                    confidence=0.25,
                    reason=VoiceAmbiguityReason.CLOSE_ALTERNATIVE,
                ),
            ]
        )
        session.commit()

        assert project.current_voice_run_id is None
        assert project.voice_revision == 0


@pytest.mark.parametrize(
    ("voice", "confidence", "reason"),
    [
        (1, None, None),
        (None, 0.5, None),
        (None, None, VoiceAmbiguityReason.CLOSE_ALTERNATIVE),
        (1, 0.5, VoiceAmbiguityReason.CROSSING),
        (1, None, VoiceAmbiguityReason.CROSSING),
    ],
)
def test_voice_persistence_rejects_every_other_state_combination(
    client: TestClient,
    voice: int | None,
    confidence: float | None,
    reason: VoiceAmbiguityReason | None,
) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Invalid voice state")
        session.add(project)
        session.flush()
        session.add(
            _note(
                project.id,
                pitch=60,
                voice=voice,
                confidence=confidence,
                reason=reason,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("voice", "confidence"),
    [(0, 0.5), (1, -0.01), (1, 1.01)],
)
def test_voice_persistence_rejects_value_and_score_bounds(
    client: TestClient,
    voice: int,
    confidence: float,
) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Invalid voice bounds")
        session.add(project)
        session.flush()
        session.add(_note(project.id, pitch=60, voice=voice, confidence=confidence))

        with pytest.raises(IntegrityError):
            session.commit()


def test_voice_revision_must_be_nonnegative(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        session.add(Project(title="Invalid voice revision", voice_revision=-1))

        with pytest.raises(IntegrityError):
            session.commit()


def _note(
    project_id: str,
    *,
    pitch: int,
    voice: int | None = None,
    confidence: float | None = None,
    reason: VoiceAmbiguityReason | None = None,
) -> NoteEvent:
    return NoteEvent(
        project_id=project_id,
        pitch=pitch,
        velocity=80,
        raw_start_seconds=0.0,
        raw_end_seconds=0.5,
        voice=voice,
        voice_confidence=confidence,
        voice_ambiguity_reason=reason,
    )
