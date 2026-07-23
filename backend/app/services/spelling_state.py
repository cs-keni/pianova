from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.entities import NoteEvent, Project


def clear_spelling_note_state(session: Session, project_id: str) -> None:
    """Clear every persisted per-note spelling field in the current transaction."""
    session.execute(
        update(NoteEvent)
        .where(NoteEvent.project_id == project_id)
        .values(
            spelled_step=None,
            spelled_alter=None,
            spelled_octave=None,
            spelling_confidence=None,
            spelling_ambiguity_reason=None,
        )
    )


def spelling_project_clear_values() -> dict[str, object]:
    """Return the project-side spelling invalidation values for an upstream CAS."""
    return {
        "key_tonic_step": None,
        "key_tonic_alter": None,
        "key_mode": None,
        "key_confidence": None,
        "key_ambiguity_reason": None,
        "key_source": None,
        "current_spelling_run_id": None,
        "spelling_revision": Project.spelling_revision + 1,
    }
