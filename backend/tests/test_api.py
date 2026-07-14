from fastapi.testclient import TestClient


def test_health_reports_real_and_unfinished_capabilities(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {item["name"]: item["available"] for item in body["dependencies"]} == {
        "ffmpeg": True,
        "ffprobe": True,
        "musescore": False,
    }
    capabilities = {item["key"]: item["state"] for item in body["capabilities"]}
    assert capabilities["media_normalization"] == "not_implemented"
    assert capabilities["transcription"] == "not_implemented"
    assert capabilities["musicxml"] == "not_implemented"
    assert capabilities["score_rendering"] == "not_implemented"


def test_config_reports_upload_contract(client: TestClient) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["max_upload_mb"] == 1
    assert response.json()["supported_extensions"] == [".m4a", ".mov", ".mp3", ".mp4", ".wav"]


def test_dependencies_are_available_as_a_standalone_contract(client: TestClient) -> None:
    response = client.get("/api/dependencies")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["ffmpeg", "ffprobe", "musescore"]


def test_create_project_persists_and_creates_storage(client: TestClient) -> None:
    response = client.post("/api/projects", json={"title": "Nocturne Study"})

    assert response.status_code == 201
    project = response.json()
    assert project["title"] == "Nocturne Study"
    assert project["status"] == "created"


def test_create_project_rejects_blank_title(client: TestClient) -> None:
    response = client.post("/api/projects", json={"title": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_title"


def test_create_project_validation_uses_structured_error(client: TestClient) -> None:
    response = client.post("/api/projects", json={"title": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_wav_updates_project(client: TestClient, wav_bytes: bytes) -> None:
    project = client.post("/api/projects", json={"title": "Upload test"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["status"] == "uploaded"
    assert body["project"]["original_filename"] == "performance.wav"
    assert body["detected_type"] == "wav"
    assert body["stored_filename"].startswith("source-")


def test_upload_uses_detected_mime_not_client_claim(client: TestClient, wav_bytes: bytes) -> None:
    project = client.post("/api/projects", json={"title": "MIME test"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "text/html")},
    )

    assert response.status_code == 200
    assert response.json()["project"]["media_type"] == "audio/x-wav"


def test_second_source_upload_is_rejected(client: TestClient, wav_bytes: bytes) -> None:
    project = client.post("/api/projects", json={"title": "One source"}).json()
    first = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("first.wav", wav_bytes, "audio/wav")},
    )

    second = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("second.wav", wav_bytes, "audio/wav")},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "source_already_uploaded"


def test_upload_rejects_disguised_file(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "Bad upload"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("not-audio.wav", b"plain text", "audio/wav")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "invalid_media_signature"


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "Bad extension"}).json()

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media"


def test_upload_rejects_missing_project(client: TestClient, wav_bytes: bytes) -> None:
    response = client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def test_upload_enforces_streaming_size_limit(client: TestClient, wav_bytes: bytes) -> None:
    project = client.post("/api/projects", json={"title": "Large upload"}).json()
    oversized = wav_bytes + (b"\x00" * (1024 * 1024))

    response = client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("large.wav", oversized, "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
