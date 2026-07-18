import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

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


def create_note_project(
    client: TestClient,
    notes: list[tuple[int, float, float]],
    *,
    title: str = "Quantization",
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


def test_health_reports_media_capability_and_unfinished_stages(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {item["name"]: item["available"] for item in body["dependencies"]} == {
        "ffmpeg": True,
        "ffprobe": True,
        "musescore": False,
        "basic_pitch": True,
    }
    capabilities = {item["key"]: item["state"] for item in body["capabilities"]}
    assert capabilities["media_normalization"] == "available"
    assert capabilities["transcription"] == "available"
    assert capabilities["interpretation"] == "available"
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
    assert [item["name"] for item in response.json()] == [
        "ffmpeg",
        "ffprobe",
        "musescore",
        "basic_pitch",
    ]


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


def test_process_media_persists_probe_metadata_and_normalized_artifact(
    client: TestClient,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Media processing"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
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
                                "codec_name": "pcm_s16le",
                                "codec_long_name": "PCM signed 16-bit little-endian",
                                "duration": "1.25",
                                "bit_rate": "352800",
                                "sample_rate": "22050",
                                "channels": 2,
                                "channel_layout": "stereo",
                            }
                        ],
                        "format": {
                            "format_name": "wav",
                            "duration": "1.25",
                            "bit_rate": "353000",
                        },
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"RIFF-normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.media.subprocess.run", fake_run)

    first = client.post(f"/api/projects/{project['id']}/process-media")
    second = client.post(f"/api/projects/{project['id']}/process-media")

    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["project"]["duration_seconds"] == 1.25
    assert body["project"]["container_format"] == "wav"
    assert body["project"]["source_bit_rate"] == 353000
    assert body["project"]["media_streams"] == [
        {
            "stream_index": 0,
            "stream_type": "audio",
            "codec_name": "pcm_s16le",
            "codec_long_name": "PCM signed 16-bit little-endian",
            "duration_seconds": 1.25,
            "bit_rate": 352800,
            "sample_rate": 22050,
            "channels": 2,
            "channel_layout": "stereo",
            "width": None,
            "height": None,
            "frame_rate": None,
        }
    ]
    assert body["normalized_artifact"]["kind"] == "normalized_audio"
    assert body["normalized_artifact"]["relative_path"].endswith(".wav")
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert len(commands) == 2


def test_process_media_requires_an_uploaded_source(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "No source"}).json()

    response = client.post(f"/api/projects/{project['id']}/process-media")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_not_uploaded"


def test_transcribe_persists_raw_notes_midi_and_provenance(
    client: TestClient,
    wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = client.post("/api/projects", json={"title": "Transcription"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    def fake_media_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
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
                                "duration": "1.0",
                                "sample_rate": "22050",
                                "channels": 1,
                            }
                        ],
                        "format": {"format_name": "wav", "duration": "1.0"},
                    }
                ),
                "",
            )
        Path(command[-1]).write_bytes(b"RIFF-normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.media.subprocess.run", fake_media_run)
    processed = client.post(f"/api/projects/{project['id']}/process-media")
    assert processed.status_code == 200

    commands: list[list[str]] = []

    def fake_worker_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
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
                            "inference_seconds": 0.25,
                        },
                    },
                    "notes": [
                        {
                            "pitch": 60,
                            "start_seconds": 0.1,
                            "end_seconds": 0.5,
                            "velocity": 96,
                            "confidence": 0.75,
                            "pitch_bends": [0, 1],
                        },
                        {
                            "pitch": 64,
                            "start_seconds": 0.5,
                            "end_seconds": 0.9,
                            "velocity": 80,
                            "confidence": 0.63,
                            "pitch_bends": None,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        midi_path.write_bytes(b"MThd\x00\x00\x00\x06")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.transcription.subprocess.run", fake_worker_run)
    first = client.post(f"/api/projects/{project['id']}/transcribe")
    second = client.post(f"/api/projects/{project['id']}/transcribe")

    assert first.status_code == 200
    body = first.json()
    assert body["note_count"] == 2
    assert body["preview_notes"][0] == {
        "id": body["preview_notes"][0]["id"],
        "pitch": 60,
        "velocity": 96,
        "raw_start_seconds": 0.1,
        "raw_end_seconds": 0.5,
        "confidence": 0.75,
        "pitch_bends": [0, 1],
        "source": "audio",
    }
    assert body["note_events_artifact"]["kind"] == "note_events"
    assert body["raw_midi_artifact"]["kind"] == "raw_midi"
    assert body["provenance"]["model_name"] == "basic_pitch"
    assert body["provenance"]["model_version"] == "0.4.0"
    assert body["provenance"]["model_runtime"] == "tensorflow"
    assert body["provenance"]["configuration"]["runtime_version"] == "2.15.0"
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert len(commands) == 1

    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(NoteEvent.id))) == 2
        assert (
            session.scalar(
                select(func.count(Artifact.id)).where(
                    Artifact.kind.in_([ArtifactKind.NOTE_EVENTS, ArtifactKind.RAW_MIDI])
                )
            )
            == 2
        )
        run = session.scalar(select(ProcessingRun).where(ProcessingRun.stage == "transcription"))
        assert run is not None
        assert run.model_name == "basic_pitch"


def test_transcribe_requires_normalized_audio(
    client: TestClient,
    wav_bytes: bytes,
) -> None:
    project = client.post("/api/projects", json={"title": "Needs normalization"}).json()
    client.post(
        f"/api/projects/{project['id']}/upload",
        files={"file": ("performance.wav", wav_bytes, "audio/wav")},
    )

    response = client.post(f"/api/projects/{project['id']}/transcribe")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "normalized_audio_required"


def test_quantize_estimates_tempo_persists_symbolic_notes_and_reuses(
    client: TestClient,
) -> None:
    project = create_note_project(
        client,
        [
            (60, 0.0, 0.4),
            (62, 0.5, 0.9),
            (64, 1.0, 1.4),
            (65, 1.5, 1.9),
            (67, 2.0, 2.4),
        ],
    )

    first = client.post(f"/api/projects/{project['id']}/quantize", json={})
    second = client.post(f"/api/projects/{project['id']}/quantize", json={})

    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["note_count"] == 5
    assert body["project"]["selected_tempo_bpm"] == pytest.approx(120, abs=0.1)
    assert body["project"]["tempo_source"] == "estimated"
    assert body["project"]["meter_numerator"] == 4
    assert body["project"]["meter_denominator"] == 4
    assert body["project"]["quantization_revision"] == 1
    assert body["diagnostics"]["residual"] == pytest.approx(0)
    assert body["diagnostics"]["inlier_coverage"] == pytest.approx(1)
    assert body["preview_notes"][0]["symbolic_start_beats"] == 0
    assert body["preview_notes"][1]["symbolic_start_beats"] == 1
    assert body["provenance"]["processor_name"] == "pianova_symbolic_timing"
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["provenance"]["run_id"] == body["provenance"]["run_id"]

    with client.app.state.session_factory() as session:
        stored_notes = tuple(
            session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project["id"])
                .order_by(NoteEvent.id)
            )
        )
        assert [note.raw_start_seconds for note in stored_notes] == [0.0, 0.5, 1.0, 1.5, 2.0]
        assert [note.symbolic_start_beats for note in stored_notes] == [0.0, 1.0, 2.0, 3.0, 4.0]
        assert all(note.chord_group is not None for note in stored_notes)
        assert (
            session.scalar(
                select(func.count(ProcessingRun.id)).where(ProcessingRun.stage == "quantization")
            )
            == 1
        )


def test_quantize_changed_override_recomputes_only_symbolic_state(
    client: TestClient,
) -> None:
    project = create_note_project(
        client,
        [
            (60, 0.0, 0.4),
            (62, 0.5, 0.9),
            (64, 1.0, 1.4),
            (65, 1.5, 1.9),
        ],
        title="Requantize",
    )
    first = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120, "meter_numerator": 3, "meter_denominator": 4},
    )
    second = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={
            "tempo_bpm": 90,
            "meter_numerator": 3,
            "meter_denominator": 4,
            "measure_origin_seconds": 0.5,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["reused"] is False
    assert second.json()["project"]["selected_tempo_bpm"] == 90
    assert second.json()["project"]["tempo_source"] == "override"
    assert second.json()["project"]["measure_origin_source"] == "override"
    assert second.json()["project"]["quantization_revision"] == 2
    assert second.json()["preview_notes"][0]["measure_number"] == 0

    with client.app.state.session_factory() as session:
        stored_notes = tuple(
            session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project["id"])
                .order_by(NoteEvent.id)
            )
        )
        assert [note.raw_start_seconds for note in stored_notes] == [0.0, 0.5, 1.0, 1.5]
        assert (
            session.scalar(
                select(func.count(ProcessingRun.id)).where(ProcessingRun.stage == "quantization")
            )
            == 2
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"meter_numerator": 3},
        {"meter_denominator": 4},
        {"meter_numerator": 6, "meter_denominator": 8},
    ],
)
def test_quantize_rejects_invalid_meter_payloads(
    client: TestClient,
    payload: dict[str, int],
) -> None:
    project = create_note_project(client, [(60, 0.0, 0.4)])

    response = client.post(f"/api/projects/{project['id']}/quantize", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_interpret_assigns_hands_and_staves_persists_and_reuses(
    client: TestClient,
) -> None:
    project = create_note_project(
        client,
        [
            (48, 0.0, 0.4),
            (72, 0.0, 0.4),
            (50, 0.5, 0.9),
            (74, 0.5, 0.9),
        ],
        title="Interpretation",
    )
    quantized = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    assert quantized.status_code == 200

    first = client.post(f"/api/projects/{project['id']}/interpret")
    second = client.post(f"/api/projects/{project['id']}/interpret")

    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["note_count"] == 4
    assert body["project"]["current_interpretation_run_id"] == body["provenance"]["run_id"]
    assert body["project"]["interpretation_revision"] == 2
    assert body["provenance"]["processor_name"] == "pianova_hand_staff_interpretation"
    assert body["provenance"]["quantization_run_id"] == quantized.json()["provenance"]["run_id"]
    assert body["diagnostics"]["resolved_hand_count"] == 4
    assert body["diagnostics"]["unknown_hand_count"] == 0
    assert {note["hand"] for note in body["preview_notes"]} == {"left", "right"}
    assert {note["staff"] for note in body["preview_notes"]} == {"bass", "treble"}
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["provenance"]["run_id"] == body["provenance"]["run_id"]

    with client.app.state.session_factory() as session:
        notes = tuple(
            session.scalars(
                select(NoteEvent)
                .where(NoteEvent.project_id == project["id"])
                .order_by(NoteEvent.pitch)
            )
        )
        assert [note.hand for note in notes] == [Hand.LEFT, Hand.LEFT, Hand.RIGHT, Hand.RIGHT]
        assert [note.staff for note in notes] == [
            Staff.BASS,
            Staff.BASS,
            Staff.TREBLE,
            Staff.TREBLE,
        ]
        assert all(note.hand_confidence is not None for note in notes)
        assert all(note.staff_confidence is not None for note in notes)
        assert (
            session.scalar(
                select(func.count(ProcessingRun.id)).where(
                    ProcessingRun.project_id == project["id"],
                    ProcessingRun.stage == "interpretation",
                )
            )
            == 1
        )


def test_interpret_requires_current_quantization(client: TestClient) -> None:
    project = create_note_project(client, [(60, 0.0, 0.4)], title="Not quantized")

    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quantization_required"


def test_interpret_rejects_invalid_current_quantization_owner(client: TestClient) -> None:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4)],
        title="Invalid quantization owner",
    )
    quantized = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    assert quantized.status_code == 200
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        stored.current_quantization_run_id = 999_999
        session.commit()

    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quantization_required"


def test_interpret_declines_malformed_reuse_state(client: TestClient) -> None:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4), (50, 0.5, 0.9), (74, 0.5, 0.9)],
        title="Repair reuse",
    )
    client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    first = client.post(f"/api/projects/{project['id']}/interpret")
    assert first.status_code == 200

    with client.app.state.session_factory() as session:
        stored_project = session.get(Project, project["id"])
        assert stored_project is not None
        run = session.get(ProcessingRun, stored_project.current_interpretation_run_id)
        assert run is not None
        run.configuration_json = "not-json"
        session.commit()

    repaired_provenance = client.post(f"/api/projects/{project['id']}/interpret")
    assert repaired_provenance.status_code == 200
    assert repaired_provenance.json()["reused"] is False

    with client.app.state.session_factory() as session:
        note = session.scalar(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        assert note is not None
        note.hand_confidence = None
        session.commit()

    repaired_assignment = client.post(f"/api/projects/{project['id']}/interpret")
    assert repaired_assignment.status_code == 200
    assert repaired_assignment.json()["reused"] is False
    with client.app.state.session_factory() as session:
        runs = tuple(
            session.scalars(
                select(ProcessingRun).where(
                    ProcessingRun.project_id == project["id"],
                    ProcessingRun.stage == "interpretation",
                    ProcessingRun.status == ProcessingStatus.SUCCEEDED,
                )
            )
        )
        assert len(runs) == 3


def test_requantization_invalidates_current_interpretation(client: TestClient) -> None:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4), (50, 0.5, 0.9), (74, 0.5, 0.9)],
        title="Invalidate interpretation",
    )
    client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    interpreted = client.post(f"/api/projects/{project['id']}/interpret")
    assert interpreted.status_code == 200

    requantized = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )

    assert requantized.status_code == 200
    assert requantized.json()["reused"] is False
    assert requantized.json()["project"]["current_interpretation_run_id"] is None
    assert requantized.json()["project"]["interpretation_revision"] == 3
    with client.app.state.session_factory() as session:
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.hand is Hand.UNKNOWN for note in notes)
        assert all(note.staff is Staff.UNKNOWN for note in notes)
        assert all(note.hand_confidence is None for note in notes)
        assert all(note.staff_confidence is None for note in notes)
        assert all(note.hand_ambiguity_reason is None for note in notes)
        assert all(note.staff_ambiguity_reason is None for note in notes)
