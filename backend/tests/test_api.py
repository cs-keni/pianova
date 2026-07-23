import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.entities import (
    Artifact,
    ArtifactKind,
    AssignmentAmbiguityReason,
    Hand,
    KeyAmbiguityReason,
    KeySource,
    NoteEvent,
    ProcessingRun,
    ProcessingStatus,
    Project,
    SpellingAmbiguityReason,
    Staff,
    VoiceAmbiguityReason,
    utc_now,
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


def create_voice_ready_project(client: TestClient) -> dict[str, object]:
    project = client.post("/api/projects", json={"title": "Voice ready"}).json()
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        run = ProcessingRun(
            project_id=stored.id,
            stage="interpretation",
            status=ProcessingStatus.SUCCEEDED,
            configuration_json="{}",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        session.add(run)
        session.flush()
        stored.current_interpretation_run_id = run.id
        stored.interpretation_revision = 1
        session.add_all(
            [
                _interpreted_note(stored.id, 72, 0, 3, Staff.TREBLE),
                _interpreted_note(stored.id, 60, 1, 1, Staff.TREBLE),
                _interpreted_note(stored.id, 48, 0, 1, Staff.BASS),
                _interpreted_note(stored.id, 64, 2, 1, Staff.UNKNOWN),
            ]
        )
        session.commit()
    return project


def create_spelling_ready_project(
    client: TestClient,
    notes: list[tuple[int, float]],
    *,
    title: str = "Spelling ready",
) -> dict[str, object]:
    project = client.post("/api/projects", json={"title": title}).json()
    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        run = ProcessingRun(
            project_id=stored.id,
            stage="voice_separation",
            status=ProcessingStatus.SUCCEEDED,
            configuration_json="{}",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        session.add(run)
        session.flush()
        stored.current_voice_run_id = run.id
        stored.voice_revision = 1
        session.add_all(
            NoteEvent(
                project_id=stored.id,
                pitch=pitch,
                velocity=90,
                raw_start_seconds=index / 2,
                raw_end_seconds=(index + duration) / 2,
                confidence=0.9,
                symbolic_start_beats=float(index),
                symbolic_duration_beats=duration,
                chord_group=index + 1,
                hand=Hand.RIGHT,
                staff=Staff.TREBLE,
                hand_confidence=1,
                staff_confidence=1,
                voice=1,
                voice_confidence=1,
            )
            for index, (pitch, duration) in enumerate(notes)
        )
        session.commit()
    return project


def create_pipeline_spelled_project(
    client: TestClient,
    *,
    title: str,
) -> tuple[dict[str, object], dict[str, object]]:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4), (50, 0.5, 0.9), (74, 0.5, 0.9)],
        title=title,
    )
    assert (
        client.post(
            f"/api/projects/{project['id']}/quantize",
            json={"tempo_bpm": 120},
        ).status_code
        == 200
    )
    assert client.post(f"/api/projects/{project['id']}/interpret").status_code == 200
    assert client.post(f"/api/projects/{project['id']}/separate-voices").status_code == 200
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


def _interpreted_note(
    project_id: str,
    pitch: int,
    start: float,
    duration: float,
    staff: Staff,
) -> NoteEvent:
    unknown_staff = staff is Staff.UNKNOWN
    return NoteEvent(
        project_id=project_id,
        pitch=pitch,
        velocity=90,
        raw_start_seconds=start / 2,
        raw_end_seconds=(start + duration) / 2,
        confidence=0.9,
        symbolic_start_beats=start,
        symbolic_duration_beats=duration,
        chord_group=int(start) + 1,
        hand=Hand.RIGHT,
        staff=staff,
        hand_confidence=0.9,
        staff_confidence=0.2 if unknown_staff else 0.9,
        staff_ambiguity_reason=(
            AssignmentAmbiguityReason.CLOSE_ALTERNATIVE if unknown_staff else None
        ),
    )


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
    assert capabilities["voice_separation"] == "available"
    assert capabilities["pitch_spelling"] == "available"
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
    voiced = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert voiced.status_code == 200
    previous_voice_revision = voiced.json()["project"]["voice_revision"]

    requantized = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )

    assert requantized.status_code == 200
    assert requantized.json()["reused"] is False
    assert requantized.json()["project"]["current_interpretation_run_id"] is None
    assert requantized.json()["project"]["interpretation_revision"] == 3
    assert requantized.json()["project"]["current_voice_run_id"] is None
    assert requantized.json()["project"]["voice_revision"] == previous_voice_revision + 1
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
        assert all(note.voice is None for note in notes)
        assert all(note.voice_confidence is None for note in notes)
        assert all(note.voice_ambiguity_reason is None for note in notes)


def test_voice_separation_requires_current_complete_interpretation(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "No interpretation"}).json()

    missing = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "interpretation_required"

    invalid_owner = create_voice_ready_project(client)
    with client.app.state.session_factory() as session:
        stored = session.get(Project, invalid_owner["id"])
        assert stored is not None
        stored.current_interpretation_run_id = 999_999
        session.commit()

    invalid = client.post(f"/api/projects/{invalid_owner['id']}/separate-voices")

    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "interpretation_required"

    ready = create_voice_ready_project(client)
    with client.app.state.session_factory() as session:
        note = session.scalar(select(NoteEvent).where(NoteEvent.project_id == ready["id"]))
        assert note is not None
        note.staff_confidence = None
        session.commit()

    incomplete = client.post(f"/api/projects/{ready['id']}/separate-voices")

    assert incomplete.status_code == 409
    assert incomplete.json()["error"]["code"] == "incomplete_interpretation"


def test_voice_separation_persists_counts_provenance_and_reuses(client: TestClient) -> None:
    project = create_voice_ready_project(client)

    first = client.post(f"/api/projects/{project['id']}/separate-voices")
    second = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["note_count"] == 4
    assert body["project"]["current_voice_run_id"] == body["provenance"]["run_id"]
    assert body["project"]["voice_revision"] == 1
    assert body["provenance"]["processor_name"] == "pianova_notation_voice_separation"
    assert body["diagnostics"]["resolved_count"] == 3
    assert body["diagnostics"]["unknown_count"] == 1
    assert body["diagnostics"]["treble_voice_1_count"] == 1
    assert body["diagnostics"]["treble_voice_2_count"] == 1
    assert body["diagnostics"]["bass_voice_1_count"] == 1
    assert body["diagnostics"]["unresolved_staff_count"] == 1
    unknown = next(note for note in body["preview_notes"] if note["staff"] == "unknown")
    assert unknown["voice"] is None
    assert unknown["voice_ambiguity_reason"] == "unresolved_staff"
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
        assert sum(note.voice == 1 for note in notes) == 2
        assert sum(note.voice == 2 for note in notes) == 1
        assert (
            sum(
                note.voice_ambiguity_reason is VoiceAmbiguityReason.UNRESOLVED_STAFF
                for note in notes
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(ProcessingRun.id)).where(
                    ProcessingRun.project_id == project["id"],
                    ProcessingRun.stage == "voice_separation",
                )
            )
            == 1
        )


def test_voice_separation_declines_malformed_reuse_and_recomputes(client: TestClient) -> None:
    project = create_voice_ready_project(client)
    first = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert first.status_code == 200

    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        run = session.get(ProcessingRun, stored.current_voice_run_id)
        assert run is not None
        run.configuration_json = "not-json"
        session.commit()

    repaired = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert repaired.status_code == 200
    assert repaired.json()["reused"] is False
    assert repaired.json()["project"]["voice_revision"] == 2

    with client.app.state.session_factory() as session:
        treble_notes = tuple(
            session.scalars(
                select(NoteEvent).where(
                    NoteEvent.project_id == project["id"],
                    NoteEvent.staff == Staff.TREBLE,
                )
            )
        )
        assert len(treble_notes) == 2
        for note in treble_notes:
            note.voice = 1
            note.voice_confidence = 1
            note.voice_ambiguity_reason = None
        session.commit()

    repaired_invariant = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert repaired_invariant.status_code == 200
    assert repaired_invariant.json()["reused"] is False
    assert repaired_invariant.json()["project"]["voice_revision"] == 3

    client.app.state.settings.voice_close_separation_semitones = 1.5
    recomputed_settings = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert recomputed_settings.status_code == 200
    assert recomputed_settings.json()["reused"] is False
    assert recomputed_settings.json()["project"]["voice_revision"] == 4


def test_interpretation_reuse_preserves_current_voices(client: TestClient) -> None:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4), (50, 0.5, 0.9), (74, 0.5, 0.9)],
        title="Preserve voices",
    )
    quantized = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )
    assert quantized.status_code == 200
    interpreted = client.post(f"/api/projects/{project['id']}/interpret")
    assert interpreted.status_code == 200
    voiced = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert voiced.status_code == 200

    reused_interpretation = client.post(f"/api/projects/{project['id']}/interpret")
    reused_quantization = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )

    assert reused_interpretation.status_code == 200
    assert reused_interpretation.json()["reused"] is True
    assert (
        reused_interpretation.json()["project"]["current_voice_run_id"]
        == voiced.json()["provenance"]["run_id"]
    )
    assert reused_quantization.status_code == 200
    assert reused_quantization.json()["reused"] is True
    assert (
        reused_quantization.json()["project"]["current_voice_run_id"]
        == voiced.json()["provenance"]["run_id"]
    )


def test_reinterpretation_invalidates_current_voices(client: TestClient) -> None:
    project = create_note_project(
        client,
        [(48, 0.0, 0.4), (72, 0.0, 0.4), (50, 0.5, 0.9), (74, 0.5, 0.9)],
        title="Reinterpret voices",
    )
    client.post(f"/api/projects/{project['id']}/quantize", json={"tempo_bpm": 120})
    client.post(f"/api/projects/{project['id']}/interpret")
    voiced = client.post(f"/api/projects/{project['id']}/separate-voices")
    assert voiced.status_code == 200
    previous_revision = voiced.json()["project"]["voice_revision"]
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"

    reinterpreted = client.post(f"/api/projects/{project['id']}/interpret")

    assert reinterpreted.status_code == 200
    assert reinterpreted.json()["reused"] is False
    assert reinterpreted.json()["project"]["current_voice_run_id"] is None
    assert reinterpreted.json()["project"]["voice_revision"] == previous_revision + 1
    with client.app.state.session_factory() as session:
        notes = session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        assert all(note.voice is None for note in notes)
        assert all(note.voice_confidence is None for note in notes)
        assert all(note.voice_ambiguity_reason is None for note in notes)


def test_spelling_requires_current_complete_voice_state(client: TestClient) -> None:
    project = client.post("/api/projects", json={"title": "No voices"}).json()

    missing = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "voice_separation_required"

    invalid_owner = create_spelling_ready_project(client, [(60, 1.0)])
    with client.app.state.session_factory() as session:
        stored = session.get(Project, invalid_owner["id"])
        assert stored is not None
        stored.current_voice_run_id = 999_999
        session.commit()

    invalid = client.post(f"/api/projects/{invalid_owner['id']}/spell", json={})

    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "voice_separation_required"

    incomplete = create_spelling_ready_project(client, [(60, 1.0)])
    with client.app.state.session_factory() as session:
        note = session.scalar(select(NoteEvent).where(NoteEvent.project_id == incomplete["id"]))
        assert note is not None
        note.chord_group = None
        session.commit()

    invalid_note = client.post(f"/api/projects/{incomplete['id']}/spell", json={})

    assert invalid_note.status_code == 409
    assert invalid_note.json()["error"]["code"] == "incomplete_voice_state"


def test_spelling_persists_unknown_key_counts_provenance_and_reuses(
    client: TestClient,
) -> None:
    project = create_spelling_ready_project(
        client,
        [(60, 1.0), (64, 1.0), (67, 1.0), (62, 1.0)],
    )

    first = client.post(f"/api/projects/{project['id']}/spell", json={})
    second = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert first.status_code == 200
    body = first.json()
    assert body["reused"] is False
    assert body["note_count"] == 4
    assert body["key"] == {
        "source": "estimated",
        "tonic_step": None,
        "tonic_alter": None,
        "mode": None,
        "confidence": 0.0,
        "ambiguity_reason": "insufficient_notes",
        "key_signature_fifths": None,
    }
    assert body["project"]["current_spelling_run_id"] == body["provenance"]["run_id"]
    assert body["project"]["spelling_revision"] == 1
    assert body["provenance"]["processor_name"] == "pianova_key_pitch_spelling"
    assert body["diagnostics"]["resolved_count"] + body["diagnostics"]["unknown_count"] == 4
    assert body["diagnostics"]["unknown_key_count"] == body["diagnostics"]["unknown_count"]
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["provenance"]["run_id"] == body["provenance"]["run_id"]

    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        assert stored.key_source is KeySource.ESTIMATED
        assert stored.key_ambiguity_reason is KeyAmbiguityReason.INSUFFICIENT_NOTES
        assert stored.key_confidence == 0
        notes = tuple(
            session.scalars(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        )
        assert all(note.spelling_confidence is not None for note in notes)
        assert (
            sum(
                note.spelling_ambiguity_reason is SpellingAmbiguityReason.UNKNOWN_KEY
                for note in notes
            )
            == body["diagnostics"]["unknown_count"]
        )


def test_spelling_override_reuse_and_blank_request_reestimates(client: TestClient) -> None:
    project = create_spelling_ready_project(
        client,
        [(60, 1.0), (64, 1.0), (67, 1.0), (62, 1.0)],
    )
    client.post(f"/api/projects/{project['id']}/spell", json={})
    override = {
        "key_override": {
            "tonic_step": "C",
            "tonic_alter": 0,
            "mode": "major",
        }
    }

    overridden = client.post(f"/api/projects/{project['id']}/spell", json=override)
    reused = client.post(f"/api/projects/{project['id']}/spell", json=override)
    estimated = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert overridden.status_code == 200
    assert overridden.json()["key"]["source"] == "override"
    assert overridden.json()["key"]["confidence"] is None
    assert overridden.json()["key"]["key_signature_fifths"] == 0
    assert overridden.json()["diagnostics"]["resolved_count"] == 4
    assert all(note["spelled_step"] is not None for note in overridden.json()["preview_notes"])
    assert reused.status_code == 200
    assert reused.json()["reused"] is True
    assert estimated.status_code == 200
    assert estimated.json()["reused"] is False
    assert estimated.json()["key"]["source"] == "estimated"
    assert estimated.json()["key"]["ambiguity_reason"] == "insufficient_notes"
    assert estimated.json()["project"]["spelling_revision"] == 3


def test_spelling_rejects_nonstandard_key_override(client: TestClient) -> None:
    project = create_spelling_ready_project(client, [(60, 1.0)])

    response = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "F",
                "tonic_alter": -1,
                "mode": "major",
            }
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_key_override"


def test_spelling_estimates_clear_major_key(client: TestClient) -> None:
    major_profile = (
        6.35,
        2.23,
        3.48,
        2.33,
        4.38,
        4.09,
        2.52,
        5.19,
        2.39,
        3.66,
        2.29,
        2.88,
    )
    project = create_spelling_ready_project(
        client,
        [(60 + pitch_class, duration) for pitch_class, duration in enumerate(major_profile)],
        title="Clear C major",
    )

    response = client.post(f"/api/projects/{project['id']}/spell", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["key"]["source"] == "estimated"
    assert body["key"]["tonic_step"] == "C"
    assert body["key"]["tonic_alter"] == 0
    assert body["key"]["mode"] == "major"
    assert body["key"]["key_signature_fifths"] == 0
    assert body["key"]["confidence"] > 0


def test_spelling_declines_malformed_reuse_and_recomputes(client: TestClient) -> None:
    project = create_spelling_ready_project(
        client,
        [(60, 1.0), (64, 1.0), (67, 1.0), (62, 1.0)],
    )
    first = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "C",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )
    assert first.status_code == 200

    with client.app.state.session_factory() as session:
        stored = session.get(Project, project["id"])
        assert stored is not None
        run = session.get(ProcessingRun, stored.current_spelling_run_id)
        assert run is not None
        run.configuration_json = "not-json"
        session.commit()

    repaired = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "C",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )

    assert repaired.status_code == 200
    assert repaired.json()["reused"] is False
    assert repaired.json()["project"]["spelling_revision"] == 2

    with client.app.state.session_factory() as session:
        note = session.scalar(select(NoteEvent).where(NoteEvent.project_id == project["id"]))
        assert note is not None
        note.spelled_step = None
        note.spelled_alter = None
        note.spelled_octave = None
        note.spelling_ambiguity_reason = SpellingAmbiguityReason.UNKNOWN_KEY
        session.commit()

    repaired_state = client.post(
        f"/api/projects/{project['id']}/spell",
        json={
            "key_override": {
                "tonic_step": "C",
                "tonic_alter": 0,
                "mode": "major",
            }
        },
    )
    assert repaired_state.status_code == 200
    assert repaired_state.json()["reused"] is False
    assert repaired_state.json()["project"]["spelling_revision"] == 3


def test_upstream_reuse_preserves_current_spelling(client: TestClient) -> None:
    project, spelled = create_pipeline_spelled_project(client, title="Preserve spelling")
    run_id = spelled["provenance"]["run_id"]

    reused_voice = client.post(f"/api/projects/{project['id']}/separate-voices")
    reused_interpretation = client.post(f"/api/projects/{project['id']}/interpret")
    reused_quantization = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 120},
    )

    assert reused_voice.status_code == 200
    assert reused_voice.json()["reused"] is True
    assert reused_voice.json()["project"]["current_spelling_run_id"] == run_id
    assert reused_interpretation.status_code == 200
    assert reused_interpretation.json()["reused"] is True
    assert reused_interpretation.json()["project"]["current_spelling_run_id"] == run_id
    assert reused_quantization.status_code == 200
    assert reused_quantization.json()["reused"] is True
    assert reused_quantization.json()["project"]["current_spelling_run_id"] == run_id


def test_revoice_clears_current_spelling(client: TestClient) -> None:
    project, spelled = create_pipeline_spelled_project(client, title="Revoice spelling")
    client.app.state.settings.voice_algorithm_version = "2.0.0"

    response = client.post(f"/api/projects/{project['id']}/separate-voices")

    assert response.status_code == 200
    assert response.json()["reused"] is False
    assert response.json()["project"]["current_spelling_run_id"] is None
    assert (
        response.json()["project"]["spelling_revision"]
        == spelled["project"]["spelling_revision"] + 1
    )
    _assert_spelling_cleared(client, str(project["id"]))


def test_reinterpretation_clears_current_spelling(client: TestClient) -> None:
    project, spelled = create_pipeline_spelled_project(client, title="Reinterpret spelling")
    client.app.state.settings.interpretation_algorithm_version = "2.0.0"

    response = client.post(f"/api/projects/{project['id']}/interpret")

    assert response.status_code == 200
    assert response.json()["reused"] is False
    assert response.json()["project"]["current_spelling_run_id"] is None
    assert (
        response.json()["project"]["spelling_revision"]
        == spelled["project"]["spelling_revision"] + 1
    )
    _assert_spelling_cleared(client, str(project["id"]))


def test_requantization_clears_current_spelling(client: TestClient) -> None:
    project, spelled = create_pipeline_spelled_project(client, title="Requantize spelling")

    response = client.post(
        f"/api/projects/{project['id']}/quantize",
        json={"tempo_bpm": 90},
    )

    assert response.status_code == 200
    assert response.json()["reused"] is False
    assert response.json()["project"]["current_spelling_run_id"] is None
    assert (
        response.json()["project"]["spelling_revision"]
        == spelled["project"]["spelling_revision"] + 1
    )
    _assert_spelling_cleared(client, str(project["id"]))


def _assert_spelling_cleared(client: TestClient, project_id: str) -> None:
    with client.app.state.session_factory() as session:
        project = session.get(Project, project_id)
        assert project is not None
        assert project.key_tonic_step is None
        assert project.key_tonic_alter is None
        assert project.key_mode is None
        assert project.key_confidence is None
        assert project.key_ambiguity_reason is None
        assert project.key_source is None
        notes = tuple(session.scalars(select(NoteEvent).where(NoteEvent.project_id == project_id)))
        assert all(note.spelled_step is None for note in notes)
        assert all(note.spelled_alter is None for note in notes)
        assert all(note.spelled_octave is None for note in notes)
        assert all(note.spelling_confidence is None for note in notes)
        assert all(note.spelling_ambiguity_reason is None for note in notes)
