from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_prefix="PIANOVA_",
        extra="ignore",
    )

    app_name: str = "Pianova"
    environment: str = "development"
    database_url: str = "sqlite:///./workspace/pianova.db"
    workspace_dir: Path = REPOSITORY_ROOT / "workspace"
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    musescore_path: str | None = None
    max_upload_mb: int = Field(default=250, gt=0, le=4096)
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    dependency_probe_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    media_inspection_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    media_normalization_timeout_seconds: float = Field(default=300.0, gt=0, le=3600)
    normalized_sample_rate: int = Field(default=22050, ge=8000, le=192000)
    normalized_channels: int = Field(default=1, ge=1, le=2)

    @field_validator("workspace_dir", mode="before")
    @classmethod
    def resolve_workspace_dir(cls, value: object) -> Path:
        path = Path(str(value))
        return path if path.is_absolute() else REPOSITORY_ROOT / path

    @property
    def resolved_database_url(self) -> str:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return self.database_url
        database_path = Path(self.database_url.removeprefix(prefix))
        if database_path.is_absolute():
            return self.database_url
        return f"{prefix}{(REPOSITORY_ROOT / database_path).resolve().as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
