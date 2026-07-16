import io
import wave
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'pianova-test.db').as_posix()}",
        workspace_dir=tmp_path / "workspace",
        max_upload_mb=1,
    )


@pytest.fixture
def client(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("PIANOVA_DATABASE_URL", settings.database_url)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    dependencies = {
        "ffmpeg": DependencyStatus("ffmpeg", True, "ffmpeg", "ffmpeg test"),
        "ffprobe": DependencyStatus("ffprobe", True, "ffprobe", "ffprobe test"),
        "musescore": DependencyStatus("musescore", False, None, None, "not found"),
        "basic_pitch": DependencyStatus(
            "basic_pitch",
            True,
            "python",
            "Basic Pitch 0.4.0 / TensorFlow 2.15.0",
        ),
    }
    app = create_app(settings=settings, dependencies=dependencies)
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


@pytest.fixture
def wav_bytes() -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 80)
    return target.getvalue()
