import json
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.models.entities import (
    Artifact,
    ArtifactKind,
    Hand,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    Staff,
)


def project_directory(settings: Settings, project_id: str) -> Path:
    return settings.workspace_dir / "projects" / project_id


def create_quantized_note_project(
    client: TestClient,
    *,
    title: str,
) -> dict[str, object]:
    project = client.post("/api/projects", json={"title": title}).json()
    with client.app.state.session_factory() as session:
        session.add(
            Artifact(
                project_id=project["id"],
                kind=ArtifactKind.NOTE_EVENTS,
                relative_path=f"projects/{project['id']}/note-events-test.json",
                size_bytes=1,
            )
        )
        session.add_all(
            NoteEvent(
                project_id=project["id"],
                pitch=pitch,
                velocity=90,
                raw_start_seconds=start,
                raw_end_seconds=start + 0.4,
                confidence=0.9,
            )
            for pitch, start in [(48, 0.0), (72, 0.0), (50, 0.5), (74, 0.5)]
        )
        session.commit()
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    assert response.status_code == 200
    return project


def create_voiced_project(
    client: TestClient,
    *,
    title: str,
) -> tuple[dict[str, object], dict[str, object]]:
    project = create_quantized_note_project(client, title=title)
    interpreted = client.post(f"/api/projects/{project['id']}/interpret")
    assert interpreted.status_code == 200
    voiced = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert voiced.status_code == 200
    return project, voiced.json()


def create_spelled_project(
    client: TestClient,
    *,
    title: str,
) -> tuple[dict[str, object], dict[str, object]]:
    project, _voiced = create_voiced_project(client, title=title)
    spelled = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "C",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )
    assert spelled.status_code == 200
    return project, spelled.json()


def create_normalized_project(
    client: TestClient,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    title: str,
    duration_seconds: float = 1.0,
) -> dict[str, object]:
    project = client.post("/api/projects", json={"title": title}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def successful_media_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "audio",
                                "duration": str(duration_seconds),
                            }
                        ],
                        "format": {
                            "format_name": "wav",
                            "duration": str(duration_seconds),
                        },
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.media.subprocess.run", successful_media_run)
    response = client.post(f"/api/projects/{project['id']}/process-media")
    assert response.status_code == 200
    return project


def write_valid_worker_outputs(command: list[str]) -> None:
    events_path = Path(command[command.index("--events-output") + 1])
    midi_path = Path(command[command.index("--midi-output") + 1])
    events_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provenance": {
                    "model_name": "basic_pitch",
                    "model_version": "0.4.0",
                    "model_runtime": "tensorflow",
                    "runtime_version": "2.15.0",
                    "model_serialization": "icassp_2022/nmp",
                    "configuration": {
                        "onset_threshold": 0.5,
                        "frame_threshold": 0.3,
                        "minimum_note_length_ms": 127.7,
                        "minimum_frequency_hz": 27.5,
                        "maximum_frequency_hz": 4186.01,
                        "multiple_pitch_bends": False,
                        "melodia_trick": True,
                        "midi_tempo": 120.0,
                    },
                },
                "notes": [
                    {
                        "pitch": 60,
                        "start_seconds": 0.1,
                        "end_seconds": 0.5,
                        "velocity": 90,
                        "confidence": 0.7,
                        "pitch_bends": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    midi_path.write_bytes(b"MThd\x00\x00\x00\x06")


def create_note_project(
    client: TestClient,
    notes: list[tuple[int, float, float]],
    *,
    title: str,
) -> dict[str, object]:
    project = client.post("/api/projects", json={"title": title}).json()
    with client.app.state.session_factory() as session:
        session.add(
            Artifact(
                project_id=project["id"],
                kind=ArtifactKind.NOTE_EVENTS,
                relative_path=f"projects/{project['id']}/note-events-test.json",
                size_bytes=1,
            )
        )
        session.add_all(
            NoteEvent(
                project_id=project["id"],
                pitch=pitch,
                velocity=90,
                raw_start_seconds=start,
                raw_end_seconds=end,
                confidence=0.9,
            )
            for pitch, start, end in notes
        )
        session.commit()
    return project


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


@pytest.mark.parametrize(
    ("tool", "error_code"),
    [
        ("ffprobe", "ffprobe_unavailable"),
        ("ffmpeg", "ffmpeg_unavailable"),
    ],
)
def test_media_processing_reports_missing_tool(
    client: TestClient,
    wav_bytes: bytes,
    tool: str,
    error_code: str,
) -> None:
    project = client.post("/api/projects", json={"title": "Missing media tool"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )
    client.app.state.dependencies[tool] = DependencyStatus(tool, False, None, None, "not found")

    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == error_code


def test_media_inspection_failure_is_retryable_and_records_failed_run(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Undecodable"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def fail_probe(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "invalid data")

    monkeypatch.setattr("app.services.media.subprocess.run", fail_probe)
    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "media_inspection_failed"
    names = [path.name for path in project_directory(settings, project["id"]).iterdir()]
    assert len(names) == 1
    assert names[0].startswith("source-")
    with client.app.state.session_factory() as session:
        run = session.scalar(select(ProcessingRun))
        assert run is not None
        assert run.status is ProcessingStatus.FAILED
        assert (
            session.scalar(
                select(func.count(Artifact.id)).where(
                    Artifact.project_id == project["id"],
                    Artifact.kind == ArtifactKind.NORMALIZED_AUDIO,
                )
            )
            == 0
        )


def test_media_normalization_timeout_removes_partial_output(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Timeout"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def timed_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "audio",
                                "duration": "0.01",
                            }
                        ],
                        "format": {"format_name": "wav", "duration": "0.01"},
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr("app.services.media.subprocess.run", timed_run)
    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "media_normalization_timeout"
    names = [path.name for path in project_directory(settings, project["id"]).iterdir()]
    assert len(names) == 1
    assert names[0].startswith("source-")


def test_media_normalization_rename_failure_removes_partial_output(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Rename failure"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def successful_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "audio",
                                "duration": "0.01",
                            }
                        ],
                        "format": {"format_name": "wav", "duration": "0.01"},
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated media rename failure")

    monkeypatch.setattr("app.services.media.subprocess.run", successful_run)
    monkeypatch.setattr("app.services.media.os.replace", fail_replace)
    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "media_processing_failed"
    names = [path.name for path in project_directory(settings, project["id"]).iterdir()]
    assert len(names) == 1
    assert names[0].startswith("source-")


def test_media_metadata_commit_failure_removes_finalized_output(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Media commit failure"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def successful_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "audio",
                                "duration": "0.01",
                            }
                        ],
                        "format": {"format_name": "wav", "duration": "0.01"},
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    original_commit = Session.commit

    def fail_normalized_commit(session: Session) -> None:
        if any(
            isinstance(item, Artifact) and item.kind is ArtifactKind.NORMALIZED_AUDIO
            for item in session.new
        ):
            raise RuntimeError("simulated media metadata failure")
        original_commit(session)

    monkeypatch.setattr("app.services.media.subprocess.run", successful_run)
    monkeypatch.setattr(Session, "commit", fail_normalized_commit)
    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "media_processing_failed"
    names = [path.name for path in project_directory(settings, project["id"]).iterdir()]
    assert len(names) == 1
    assert names[0].startswith("source-")
    with client.app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count(Artifact.id)).where(Artifact.project_id == project["id"])
            )
            == 1
        )


def test_transcription_reports_missing_worker(
    client: TestClient,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Missing worker")
    client.app.state.dependencies["basic_pitch"] = DependencyStatus(
        "basic_pitch",
        False,
        None,
        None,
        "not found",
    )

    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "transcription_unavailable"


def test_transcription_rejects_audio_below_basic_pitch_minimum_duration(
    client: TestClient,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(
        client,
        wav_bytes,
        monkeypatch,
        "Too short",
        duration_seconds=0.01,
    )

    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_too_short_for_transcription"


def test_transcription_timeout_removes_partial_outputs_and_records_failure(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Transcription timeout")

    def timeout_worker(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        write_valid_worker_outputs(command)
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr("app.services.transcription.subprocess.run", timeout_worker)
    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "transcription_timeout"
    names = [path.name for path in project_directory(settings, str(project["id"])).iterdir()]
    assert len(names) == 2
    assert not any(
        name.startswith(("note-events-", "raw-midi-", ".transcription-")) for name in names
    )
    with client.app.state.session_factory() as session:
        run = session.scalar(select(ProcessingRun).where(ProcessingRun.stage == "transcription"))
        assert run is not None
        assert run.status is ProcessingStatus.FAILED

    def successful_worker(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        write_valid_worker_outputs(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.transcription.subprocess.run", successful_worker)
    retry = client.post(f"/api/projects/{project['id']}/transcribe")
    assert retry.status_code == 200
    assert retry.json()["reused"] is False


def test_transcription_reports_model_inference_failure(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Inference failure")

    def failed_worker(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "model inference failed")

    monkeypatch.setattr("app.services.transcription.subprocess.run", failed_worker)
    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "transcription_inference_failed"
    names = [path.name for path in project_directory(settings, str(project["id"])).iterdir()]
    assert len(names) == 2


def test_transcription_rejects_malformed_worker_output(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Malformed output")

    def malformed_worker(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        events_path = Path(command[command.index("--events-output") + 1])
        midi_path = Path(command[command.index("--midi-output") + 1])
        events_path.write_text('{"notes":[{"pitch":999}]}', encoding="utf-8")
        midi_path.write_bytes(b"MThd")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.transcription.subprocess.run", malformed_worker)
    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_transcription_output"
    names = [path.name for path in project_directory(settings, str(project["id"])).iterdir()]
    assert len(names) == 2


def test_transcription_second_rename_failure_cleans_both_outputs(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Rename outputs")

    def successful_worker(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        write_valid_worker_outputs(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    original_replace = Path.replace
    replace_count = 0

    def fail_second_replace(source: Path, destination: Path) -> Path:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("simulated second rename failure")
        return original_replace(source, destination)

    monkeypatch.setattr("app.services.transcription.subprocess.run", successful_worker)
    monkeypatch.setattr("app.services.transcription.os.replace", fail_second_replace)
    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "transcription_failed"
    names = [path.name for path in project_directory(settings, str(project["id"])).iterdir()]
    assert len(names) == 2


def test_transcription_commit_failure_removes_artifacts_and_notes(
    client: TestClient,
    settings: Settings,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_normalized_project(client, wav_bytes, monkeypatch, "Commit transcription")

    def successful_worker(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        write_valid_worker_outputs(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    original_commit = Session.commit

    def fail_transcription_commit(session: Session) -> None:
        if any(
            isinstance(item, Artifact)
            and item.kind in {ArtifactKind.NOTE_EVENTS, ArtifactKind.RAW_MIDI}
            for item in session.new
        ):
            raise RuntimeError("simulated transcription metadata failure")
        original_commit(session)

    monkeypatch.setattr("app.services.transcription.subprocess.run", successful_worker)
    monkeypatch.setattr(Session, "commit", fail_transcription_commit)
    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "transcription_failed"
    names = [path.name for path in project_directory(settings, str(project["id"])).iterdir()]
    assert len(names) == 2
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(NoteEvent.id))) == 0
        assert (
            session.scalar(
                select(func.count(Artifact.id)).where(
                    Artifact.kind.in_([ArtifactKind.NOTE_EVENTS, ArtifactKind.RAW_MIDI])
                )
            )
            == 0
        )


def test_quantization_requires_transcription(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "No transcription"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transcription_required"


def test_quantization_rejects_empty_and_ambiguous_note_evidence(client: TestClient) -> None:
    empty = create_note_project(client, [], title="Empty notes")
    sparse = create_note_project(
        client,
        [(60, 0.0, 0.4), (64, 0.5, 0.9), (67, 1.0, 1.4)],
        title="Sparse notes",
    )

    empty_response = client.post(f"/api/projects/{empty['id']}/quantize", json={})
    sparse_response = client.post(f"/api/projects/{sparse['id']}/quantize", json={})

    assert empty_response.status_code == 422
    assert empty_response.json()["error"]["code"] == "notes_required"
    assert sparse_response.status_code == 422
    assert sparse_response.json()["error"]["code"] == "tempo_ambiguous"
    with client.app.state.session_factory() as session:
        run = session.scalar(
            select(ProcessingRun).where(
                ProcessingRun.project_id == sparse["id"],
                ProcessingRun.stage == "quantization",
            )
        )
        assert run is not None
        assert run.status is ProcessingStatus.FAILED


def test_quantization_commit_failure_preserves_previous_symbolic_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_note_project(
        client,
        [
            (60, 0.0, 0.4),
            (62, 0.5, 0.9),
            (64, 1.0, 1.4),
            (65, 1.5, 1.9),
        ],
        title="Quantization rollback",
    )
    first = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    assert first.status_code == 200
    first_run_id = first.json()["provenance"]["run_id"]
    original_commit = Session.commit
    commit_count = 0

    def fail_success_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated quantization commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_success_commit)
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "quantization_failed"
    with client.app.state.session_factory() as session:
        stored_project = session.get(Project, project["id"])
        assert stored_project is not None
        assert stored_project.selected_tempo_bpm == 120
        assert stored_project.current_quantization_run_id == first_run_id
        assert stored_project.quantization_revision == 1
        notes = tuple(
            session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project["id"])
                .order_by(NoteEvent.id)
            )
        )
        assert [note.symbolic_start_beats for note in notes] == [0.0, 1.0, 2.0, 3.0]
        latest_run = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "quantization",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest_run is not None
        assert latest_run.status is ProcessingStatus.FAILED


def test_quantization_conflict_rolls_back_symbolic_changes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_note_project(
        client,
        [
            (60, 0.0, 0.4),
            (62, 0.5, 0.9),
            (64, 1.0, 1.4),
            (65, 1.5, 1.9),
        ],
        title="Quantization conflict",
    )
    from app.services import quantization as quantization_module

    original_quantize_timing = quantization_module.quantize_timing

    def concurrent_quantize(*args: object, **kwargs: object) -> object:
        result = original_quantize_timing(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            stored.quantization_revision += 1
            other_session.commit()
        return result

    monkeypatch.setattr(quantization_module, "quantize_timing", concurrent_quantize)
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quantization_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_quantization_run_id is None
        assert stored.selected_tempo_bpm is None
        assert all(
            note.symbolic_start_beats is None
            for note in session.scalars(
                select(NoteEvent).where(NoteEvent.project_id == project["id"])
            )
        )


def test_interpretation_commit_failure_preserves_previous_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_quantized_note_project(client, title="Interpretation rollback")
    first = client.post(f"/api/projects/{project['id']}/interpret")
    assert first.status_code == 200
    first_body = first.json()
    original_commit = Session.commit
    commit_count = 0

    client.app.state.settings.interpretation_algorithm_version = "2.0.0"

    def fail_success_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated interpretation commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_success_commit)
    response = client.post(f"/api/projects/{project['id']}/interpret")
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "interpretation_failed"
    with client.app.state.session_factory() as session:
        stored_project = session.get(Project, project["id"])
        assert stored_project is not None
        assert stored_project.current_interpretation_run_id == first_body["provenance"]["run_id"]
        assert stored_project.interpretation_revision == 2
        notes = tuple(
            session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project["id"])
                .order_by(NoteEvent.id)
            )
        )
        assert all(note.hand is not Hand.UNKNOWN for note in notes)
        assert all(note.staff is not Staff.UNKNOWN for note in notes)
        assert all(note.hand_confidence is not None for note in notes)
        latest_run = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "interpretation",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest_run is not None
        assert latest_run.status is ProcessingStatus.FAILED


def test_interpretation_conflict_rolls_back_assignments(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_quantized_note_project(client, title="Interpretation conflict")
    from app.services import interpretation as interpretation_module

    original_interpret_notes = interpretation_module.interpret_notes

    def concurrent_interpretation(*args: object, **kwargs: object) -> object:
        result = original_interpret_notes(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            stored.interpretation_revision += 1
            other_session.commit()
        return result

    monkeypatch.setattr(
        interpretation_module,
        "interpret_notes",
        concurrent_interpretation,
    )
    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interpretation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_interpretation_run_id is None
        assert stored.interpretation_revision == 2
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.hand is Hand.UNKNOWN for note in notes)
        assert all(note.staff is Staff.UNKNOWN for note in notes)
        assert all(note.hand_confidence is None for note in notes)
        latest_run = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "interpretation",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest_run is not None
        assert latest_run.status is ProcessingStatus.FAILED


def test_requantization_commit_failure_preserves_interpretation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_quantized_note_project(client, title="Invalidation rollback")
    interpreted = client.post(f"/api/projects/{project['id']}/interpret")
    assert interpreted.status_code == 200
    interpretation_run_id = interpreted.json()["provenance"]["run_id"]
    original_commit = Session.commit
    commit_count = 0

    def fail_success_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated requantization commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_success_commit)
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "quantization_failed"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_interpretation_run_id == interpretation_run_id
        assert stored.interpretation_revision == 2
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.hand is not Hand.UNKNOWN for note in notes)
        assert all(note.staff is not Staff.UNKNOWN for note in notes)
        assert all(note.hand_confidence is not None for note in notes)
        assert all(note.staff_confidence is not None for note in notes)


def test_voice_commit_failure_preserves_previous_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Voice rollback")
    original_commit = Session.commit
    commit_count = 0
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def fail_success_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated voice commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_success_commit)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "voice_separation_failed"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_voice_run_id == first_body["provenance"]["run_id"]
        assert stored.voice_revision == first_body["project"]["voice_revision"]
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.voice is not None for note in notes)
        assert all(note.voice_confidence is not None for note in notes)
        latest = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "voice_separation",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest is not None
        assert latest.status is ProcessingStatus.FAILED


def test_voice_conflict_rolls_back_new_assignments(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Voice conflict")
    from app.services import voices as voices_module

    original_separate = voices_module.separate_voices
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def concurrent_voice(*args: object, **kwargs: object) -> object:
        result = original_separate(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            stored.voice_revision += 1
            other_session.commit()
        return result

    monkeypatch.setattr(voices_module, "separate_voices", concurrent_voice)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_separation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_voice_run_id == first_body["provenance"]["run_id"]
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        latest = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "voice_separation",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest is not None
        assert latest.status is ProcessingStatus.FAILED


def test_voice_failure_audit_commit_failure_is_logged(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = create_quantized_note_project(client, title="Voice audit failure")
    interpreted = client.post(f"/api/projects/{project['id']}/interpret")
    assert interpreted.status_code == 200
    from app.services import voices as voices_module

    original_commit = Session.commit
    commit_count = 0
    logged: list[str] = []

    def fail_engine(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated voice engine failure")

    def fail_audit_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated audit commit failure")
        original_commit(session)

    def capture_exception(message: str, *args: object, **_kwargs: object) -> None:
        logged.append(message % args)

    monkeypatch.setattr(voices_module, "separate_voices", fail_engine)
    monkeypatch.setattr(voices_module.logger, "exception", capture_exception)
    monkeypatch.setattr(Session, "commit", fail_audit_commit)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "voice_separation_failed"
    assert any("Could not persist failed voice_separation run" in item for item in logged)
    with client.app.state.session_factory() as session:
        run = session.scalar(
            select(ProcessingRun).where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "voice_separation",
            )
        )
        assert run is not None
        assert run.status is ProcessingStatus.RUNNING


def test_reinterpretation_commit_first_makes_voice_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Interpretation wins")
    from app.services import voices as voices_module
    from app.services.interpretation import InterpretationService

    original_separate = voices_module.separate_voices
    client.app.state.settings.voice_algorithm_version = "2.0.0"
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"

    def interpretation_commits_first(*args: object, **kwargs: object) -> object:
        result = original_separate(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            InterpretationService(other_session, client.app.state.settings).interpret(stored)
        return result

    monkeypatch.setattr(voices_module, "separate_voices", interpretation_commits_first)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_separation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.interpretation_revision == (
            first_body["project"]["interpretation_revision"] + 1
        )
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        assert stored.current_voice_run_id is None


def test_voice_commit_first_makes_reinterpretation_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Voice beats interpretation")
    from app.services import interpretation as interpretation_module
    from app.services.voices import VoiceService

    original_interpret = interpretation_module.interpret_notes
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def voice_commits_first(*args: object, **kwargs: object) -> object:
        result = original_interpret(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            VoiceService(other_session, client.app.state.settings).separate(stored)
        return result

    monkeypatch.setattr(interpretation_module, "interpret_notes", voice_commits_first)
    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interpretation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.interpretation_revision == first_body["project"]["interpretation_revision"]
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        assert stored.current_voice_run_id != first_body["provenance"]["run_id"]


def test_requantization_commit_first_makes_voice_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Quantization wins")
    from app.schemas.api import QuantizationRequest
    from app.services import voices as voices_module
    from app.services.quantization import QuantizationService

    original_separate = voices_module.separate_voices
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def quantization_commits_first(*args: object, **kwargs: object) -> object:
        result = original_separate(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            QuantizationService(other_session, client.app.state.settings).quantize(
                stored,
                QuantizationRequest(tempo_bpm=90),
            )
        return result

    monkeypatch.setattr(voices_module, "separate_voices", quantization_commits_first)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_separation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.quantization_revision == first_body["project"]["quantization_revision"] + 1
        assert stored.interpretation_revision == (
            first_body["project"]["interpretation_revision"] + 1
        )
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        assert stored.current_interpretation_run_id is None
        assert stored.current_voice_run_id is None


def test_voice_commit_first_makes_requantization_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_voiced_project(client, title="Voice beats quantization")
    from app.services import quantization as quantization_module
    from app.services.voices import VoiceService

    original_quantize = quantization_module.quantize_timing
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def voice_commits_first(*args: object, **kwargs: object) -> object:
        result = original_quantize(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            VoiceService(other_session, client.app.state.settings).separate(stored)
        return result

    monkeypatch.setattr(quantization_module, "quantize_timing", voice_commits_first)
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quantization_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.quantization_revision == first_body["project"]["quantization_revision"]
        assert stored.interpretation_revision == first_body["project"]["interpretation_revision"]
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        assert stored.current_voice_run_id != first_body["provenance"]["run_id"]


def test_spelling_commit_failure_preserves_previous_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Spelling rollback")
    original_commit = Session.commit
    commit_count = 0
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def fail_success_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated spelling commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_success_commit)
    response = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "C",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "spelling_failed"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_spelling_run_id == first_body["provenance"]["run_id"]
        assert stored.spelling_revision == first_body["project"]["spelling_revision"]
        assert stored.key_source is not None
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.spelled_step is not None for note in notes)
        assert all(note.spelling_confidence is not None for note in notes)
        latest = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "pitch_spelling",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest is not None
        assert latest.status is ProcessingStatus.FAILED


def test_spelling_conflict_rolls_back_new_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Spelling conflict")
    from app.services import spelling as spelling_module

    original_spell = spelling_module.spell_notes
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def concurrent_spelling(*args: object, **kwargs: object) -> object:
        result = original_spell(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            stored.spelling_revision += 1
            other_session.commit()
        return result

    monkeypatch.setattr(spelling_module, "spell_notes", concurrent_spelling)
    response = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "G",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spelling_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.current_spelling_run_id == first_body["provenance"]["run_id"]
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        latest = session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "pitch_spelling",
            )
            .order_by(ProcessingRun.id.desc())
        )
        assert latest is not None
        assert latest.status is ProcessingStatus.FAILED


def test_spelling_failure_audit_commit_failure_is_logged(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _voiced = create_voiced_project(client, title="Spelling audit failure")
    from app.services import spelling as spelling_module

    original_commit = Session.commit
    commit_count = 0
    logged: list[str] = []

    def fail_engine(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated spelling engine failure")

    def fail_audit_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("simulated audit commit failure")
        original_commit(session)

    def capture_exception(message: str, *args: object, **_kwargs: object) -> None:
        logged.append(message % args)

    monkeypatch.setattr(spelling_module, "spell_notes", fail_engine)
    monkeypatch.setattr(spelling_module.logger, "exception", capture_exception)
    monkeypatch.setattr(Session, "commit", fail_audit_commit)
    response = client.post(f"/api/projects/{project['id']}/spell", json={})
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "spelling_failed"
    assert any("Could not persist failed pitch_spelling run" in item for item in logged)
    with client.app.state.session_factory() as session:
        run = session.scalar(
            select(ProcessingRun).where(
                ProcessingRun.project_id == project["id"],
                ProcessingRun.stage == "pitch_spelling",
            )
        )
        assert run is not None
        assert run.status is ProcessingStatus.RUNNING


def test_revoice_commit_first_makes_spelling_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Voice wins over spelling")
    from app.services import spelling as spelling_module
    from app.services.voices import VoiceService

    original_spell = spelling_module.spell_notes
    client.app.state.settings.spelling_algorithm_version = "2.0.0"
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    def voice_commits_first(*args: object, **kwargs: object) -> object:
        result = original_spell(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            VoiceService(other_session, client.app.state.settings).separate(stored)
        return result

    monkeypatch.setattr(spelling_module, "spell_notes", voice_commits_first)
    response = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spelling_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.voice_revision == first_body["project"]["voice_revision"] + 1
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_spelling_run_id is None


def test_spelling_commit_first_makes_revoice_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Spelling wins over voice")
    from app.schemas.api import SpellingRequest
    from app.services import voices as voices_module
    from app.services.spelling import SpellingService

    original_separate = voices_module.separate_voices
    client.app.state.settings.voice_algorithm_version = "2.0.0"
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def spelling_commits_first(*args: object, **kwargs: object) -> object:
        result = original_separate(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            SpellingService(other_session, client.app.state.settings).spell(
                stored,
                SpellingRequest(),
            )
        return result

    monkeypatch.setattr(voices_module, "separate_voices", spelling_commits_first)
    response = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_separation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.voice_revision == first_body["project"]["voice_revision"]
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_spelling_run_id != first_body["provenance"]["run_id"]


def test_reinterpretation_commit_first_makes_spelling_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Interpretation beats spelling")
    from app.services import spelling as spelling_module
    from app.services.interpretation import InterpretationService

    original_spell = spelling_module.spell_notes
    client.app.state.settings.spelling_algorithm_version = "2.0.0"
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"

    def interpretation_commits_first(*args: object, **kwargs: object) -> object:
        result = original_spell(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            InterpretationService(other_session, client.app.state.settings).interpret(stored)
        return result

    monkeypatch.setattr(spelling_module, "spell_notes", interpretation_commits_first)
    response = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spelling_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.interpretation_revision == (
            first_body["project"]["interpretation_revision"] + 1
        )
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_voice_run_id is None
        assert stored.current_spelling_run_id is None


def test_spelling_commit_first_makes_reinterpretation_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Spelling beats interpretation")
    from app.schemas.api import SpellingRequest
    from app.services import interpretation as interpretation_module
    from app.services.spelling import SpellingService

    original_interpret = interpretation_module.interpret_notes
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def spelling_commits_first(*args: object, **kwargs: object) -> object:
        result = original_interpret(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            SpellingService(other_session, client.app.state.settings).spell(
                stored,
                SpellingRequest(),
            )
        return result

    monkeypatch.setattr(interpretation_module, "interpret_notes", spelling_commits_first)
    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "interpretation_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.interpretation_revision == first_body["project"]["interpretation_revision"]
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_spelling_run_id != first_body["provenance"]["run_id"]


def test_requantization_commit_first_makes_spelling_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Quantization beats spelling")
    from app.schemas.api import QuantizationRequest
    from app.services import spelling as spelling_module
    from app.services.quantization import QuantizationService

    original_spell = spelling_module.spell_notes
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def quantization_commits_first(*args: object, **kwargs: object) -> object:
        result = original_spell(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            QuantizationService(other_session, client.app.state.settings).quantize(
                stored,
                QuantizationRequest(tempo_bpm=90),
            )
        return result

    monkeypatch.setattr(spelling_module, "spell_notes", quantization_commits_first)
    response = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spelling_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.quantization_revision == first_body["project"]["quantization_revision"] + 1
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_interpretation_run_id is None
        assert stored.current_voice_run_id is None
        assert stored.current_spelling_run_id is None


def test_spelling_commit_first_makes_requantization_commit_lose(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, first_body = create_spelled_project(client, title="Spelling beats quantization")
    from app.schemas.api import SpellingRequest
    from app.services import quantization as quantization_module
    from app.services.spelling import SpellingService

    original_quantize = quantization_module.quantize_timing
    client.app.state.settings.spelling_algorithm_version = "2.0.0"

    def spelling_commits_first(*args: object, **kwargs: object) -> object:
        result = original_quantize(*args, **kwargs)
        with client.app.state.session_factory() as other_session:
            stored = other_session.get(Project, project["id"])
            assert stored is not None
            SpellingService(other_session, client.app.state.settings).spell(
                stored,
                SpellingRequest(),
            )
        return result

    monkeypatch.setattr(quantization_module, "quantize_timing", spelling_commits_first)
    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quantization_conflict"
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.quantization_revision == first_body["project"]["quantization_revision"]
        assert stored.spelling_revision == first_body["project"]["spelling_revision"] + 1
        assert stored.current_spelling_run_id != first_body["provenance"]["run_id"]
