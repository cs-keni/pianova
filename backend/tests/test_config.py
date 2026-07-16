import json
import subprocess
from pathlib import Path

import pytest

from app.core.capabilities import CapabilityState, build_capabilities
from app.core.config import Settings
from app.core.dependencies import _probe_transcription


def test_settings_resolve_project_relative_paths() -> None:
    settings = Settings(
        workspace_dir="workspace",
        database_url="sqlite:///./workspace/test.db",
        transcription_python_path=".venv-transcription/Scripts/python.exe",
    )

    assert settings.workspace_dir.is_absolute()
    assert settings.resolved_database_url.startswith("sqlite:///")
    assert settings.resolved_database_url.endswith("workspace/test.db")
    assert settings.resolved_transcription_python_path.is_absolute()


def test_capabilities_require_both_ffmpeg_tools() -> None:
    capabilities = {
        item.key: item
        for item in build_capabilities(
            ffmpeg=True,
            ffprobe=False,
            musescore=True,
            transcription=False,
        )
    }

    assert capabilities["media_normalization"].state is CapabilityState.UNAVAILABLE
    assert capabilities["transcription"].state is CapabilityState.UNAVAILABLE
    assert capabilities["score_rendering"].state is CapabilityState.NOT_IMPLEMENTED


def test_upload_limit_is_exposed_in_bytes(tmp_path: Path) -> None:
    settings = Settings(workspace_dir=tmp_path, max_upload_mb=7)

    assert settings.max_upload_bytes == 7 * 1024 * 1024


def test_local_frontend_origins_cover_hostname_and_loopback() -> None:
    settings = Settings()

    assert "http://localhost:3000" in settings.cors_origins
    assert "http://127.0.0.1:3000" in settings.cors_origins


def test_transcription_probe_reports_model_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python_path = tmp_path / "python.exe"
    python_path.touch()
    settings = Settings(transcription_python_path=python_path)

    def successful_probe(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "model_name": "basic_pitch",
                    "model_version": "0.4.0",
                    "runtime": "tensorflow",
                    "runtime_version": "2.15.0",
                    "model_serialization": "icassp_2022/nmp",
                }
            ),
            "",
        )

    monkeypatch.setattr("app.core.dependencies.subprocess.run", successful_probe)
    status = _probe_transcription(settings)

    assert status.available is True
    assert status.version == "Basic Pitch 0.4.0 / tensorflow 2.15.0"


def test_transcription_probe_reports_missing_environment(tmp_path: Path) -> None:
    settings = Settings(transcription_python_path=tmp_path / "missing-python.exe")

    status = _probe_transcription(settings)

    assert status.available is False
    assert status.error == "transcription environment not found"
