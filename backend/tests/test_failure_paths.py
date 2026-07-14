from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.config import Settings
from app.models.entities import Artifact, Project


def project_directory(settings: Settings, project_id: str) -> Path:
    return settings.workspace_dir / "projects" / project_id


def test_signature_failure_removes_temporary_files(client: TestClient, settings: Settings) -> None:
    project = client.post("/api/projects", json={"title": "Cleanup"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("fake.wav", b"not wave data", "audio/wav")},
    )

    assert response.status_code == 415
    assert list(project_directory(settings, project["id"]).iterdir()) == []


def test_atomic_rename_failure_cleans_temporary_file(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Rename failure"}).json()

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("app.services.storage.os.replace", fail_replace)
    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "upload_failed"
    assert list(project_directory(settings, project["id"]).iterdir()) == []


def test_database_commit_failure_removes_finalized_file_and_artifact(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Commit failure"}).json()
    original_commit = Session.commit

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "upload_failed"
    assert list(project_directory(settings, project["id"]).iterdir()) == []
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(Artifact.id))) == 0
        stored_project = session.get(Project, project["id"])
        assert stored_project is not None
        assert stored_project.status.value == "created"


def test_existing_project_directory_is_not_deleted_when_creation_fails(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_id = UUID("12345678-1234-5678-1234-567812345678")
    existing = project_directory(settings, str(fixed_id))
    existing.mkdir(parents=True)
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    monkeypatch.setattr("app.models.entities.uuid.uuid4", lambda: fixed_id)

    response = client.post("/api/projects", json={"title": "Collision"})

    assert response.status_code == 500
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_sqlite_foreign_keys_cascade_artifacts(client: TestClient, wav_bytes: bytes) -> None:
    project = client.post("/api/projects", json={"title": "Cascade"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    with client.app.state.session_factory() as session:
        stored_project = session.get(Project, project["id"])
        assert stored_project is not None
        session.delete(stored_project)
        session.commit()
        assert session.scalar(select(func.count(Artifact.id))) == 0


def test_unexpected_dependency_error_uses_structured_envelope(client: TestClient) -> None:
    def broken_session() -> None:
        raise RuntimeError("simulated dependency error")

    client.app.dependency_overrides[get_session] = broken_session
    with TestClient(client.app, raise_server_exceptions=False) as error_client:
        response = error_client.post("/api/projects", json={"title": "Failure"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_request_body_limit_rejects_before_multipart_parsing(
    client: TestClient, settings: Settings
) -> None:
    project = client.post("/api/projects", json={"title": "Request limit"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/upload",
        headers={"Content-Length": str(settings.max_upload_bytes + (2 * 1024 * 1024))},
        content=b"oversized",
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
