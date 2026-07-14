from pathlib import Path

from app.core.capabilities import CapabilityState, build_capabilities
from app.core.config import Settings


def test_settings_resolve_project_relative_paths() -> None:
    settings = Settings(workspace_dir="workspace", database_url="sqlite:///./workspace/test.db")

    assert settings.workspace_dir.is_absolute()
    assert settings.resolved_database_url.startswith("sqlite:///")
    assert settings.resolved_database_url.endswith("workspace/test.db")


def test_capabilities_require_both_ffmpeg_tools() -> None:
    capabilities = {
        item.key: item for item in build_capabilities(ffmpeg=True, ffprobe=False, musescore=True)
    }

    assert capabilities["media_normalization"].state is CapabilityState.NOT_IMPLEMENTED
    assert capabilities["transcription"].state is CapabilityState.NOT_IMPLEMENTED
    assert capabilities["score_rendering"].state is CapabilityState.NOT_IMPLEMENTED


def test_upload_limit_is_exposed_in_bytes(tmp_path: Path) -> None:
    settings = Settings(workspace_dir=tmp_path, max_upload_mb=7)

    assert settings.max_upload_bytes == 7 * 1024 * 1024


def test_local_frontend_origins_cover_hostname_and_loopback() -> None:
    settings = Settings()

    assert "http://localhost:3000" in settings.cors_origins
    assert "http://127.0.0.1:3000" in settings.cors_origins
