import os
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    transcription_python_path: Path | None = None
    max_upload_mb: int = Field(default=250, gt=0, le=4096)
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    dependency_probe_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    media_inspection_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    media_normalization_timeout_seconds: float = Field(default=300.0, gt=0, le=3600)
    normalized_sample_rate: int = Field(default=22050, ge=8000, le=192000)
    normalized_channels: int = Field(default=1, ge=1, le=2)
    transcription_probe_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    transcription_timeout_seconds: float = Field(default=1800.0, gt=0, le=14400)
    transcription_minimum_duration_seconds: float = Field(default=0.05, gt=0, le=60)
    transcription_onset_threshold: float = Field(default=0.5, ge=0, le=1)
    transcription_frame_threshold: float = Field(default=0.3, ge=0, le=1)
    transcription_minimum_note_length_ms: float = Field(default=127.7, gt=0, le=10000)
    transcription_minimum_frequency_hz: float = Field(default=27.5, gt=0)
    transcription_maximum_frequency_hz: float = Field(default=4186.01, gt=0)
    quantization_minimum_bpm: float = Field(default=40.0, gt=0, le=400)
    quantization_maximum_bpm: float = Field(default=200.0, gt=0, le=400)
    quantization_chord_tolerance_ms: float = Field(default=60.0, ge=0, le=500)
    quantization_minimum_grid_beats: float = Field(default=0.25, gt=0, le=1)
    quantization_minimum_tempo_groups: int = Field(default=4, ge=3, le=32)
    quantization_minimum_tempo_span_seconds: float = Field(default=1.0, gt=0, le=60)
    quantization_maximum_residual: float = Field(default=0.22, ge=0, le=0.5)
    quantization_minimum_inlier_coverage: float = Field(default=0.75, ge=0, le=1)
    quantization_inlier_residual: float = Field(default=0.35, ge=0, le=0.5)
    quantization_distinct_tempo_ratio: float = Field(default=0.02, ge=0, le=0.25)
    quantization_ambiguity_margin: float = Field(default=0.03, ge=0, le=1)
    quantization_octave_ambiguity_margin: float = Field(default=0.04, ge=0, le=1)
    quantization_rest_tolerance_beats: float = Field(default=0.12, ge=0, le=1)
    quantization_same_pitch_repair_tolerance_beats: float = Field(default=0.5, ge=0, le=4)
    quantization_preview_note_limit: int = Field(default=50, ge=1, le=500)
    quantization_algorithm_version: str = "1.0.0"
    interpretation_left_center_pitch: float = Field(default=48.0, ge=0, le=127)
    interpretation_right_center_pitch: float = Field(default=72.0, ge=0, le=127)
    interpretation_bass_center_pitch: float = Field(default=48.0, ge=0, le=127)
    interpretation_treble_center_pitch: float = Field(default=72.0, ge=0, le=127)
    interpretation_pitch_weight: float = Field(default=1.0, ge=0, le=100)
    interpretation_span_weight: float = Field(default=0.25, ge=0, le=100)
    interpretation_movement_weight: float = Field(default=0.35, ge=0, le=100)
    interpretation_appearance_weight: float = Field(default=0.15, ge=0, le=100)
    interpretation_split_movement_weight: float = Field(default=0.08, ge=0, le=100)
    interpretation_crossing_weight: float = Field(default=0.5, ge=0, le=100)
    interpretation_compact_split_weight: float = Field(default=0.1, ge=0, le=100)
    interpretation_wide_single_partition_weight: float = Field(default=0.5, ge=0, le=100)
    interpretation_comfortable_hand_span: int = Field(default=12, ge=1, le=48)
    interpretation_compact_chord_span: int = Field(default=7, ge=0, le=48)
    interpretation_middle_register_low: int = Field(default=55, ge=0, le=127)
    interpretation_middle_register_high: int = Field(default=65, ge=0, le=127)
    interpretation_ambiguity_margin: float = Field(default=0.25, gt=0, le=100)
    interpretation_high_confidence_margin: float = Field(default=1.0, gt=0, le=100)
    interpretation_maximum_transition_evaluations: int = Field(
        default=2_000_000, ge=1, le=100_000_000
    )
    interpretation_preview_note_limit: int = Field(default=50, ge=1, le=500)
    interpretation_algorithm_version: str = "1.0.0"
    voice_close_separation_semitones: float = Field(default=2.0, ge=0, le=48)
    voice_high_separation_semitones: float = Field(default=7.0, gt=0, le=48)
    voice_preview_note_limit: int = Field(default=50, ge=1, le=500)
    voice_algorithm_version: str = "1.0.0"
    spelling_key_minimum_notes: int = Field(default=8, ge=1, le=10_000)
    spelling_key_minimum_distinct_pitch_classes: int = Field(default=3, ge=1, le=12)
    spelling_key_ambiguity_margin: float = Field(default=0.05, ge=0, le=1)
    spelling_close_margin: float = Field(default=0.10, ge=0, le=1)
    spelling_preview_note_limit: int = Field(default=50, ge=1, le=500)
    spelling_algorithm_version: str = "1.0.0"

    @field_validator("workspace_dir", mode="before")
    @classmethod
    def resolve_workspace_dir(cls, value: object) -> Path:
        path = Path(str(value))
        return path if path.is_absolute() else REPOSITORY_ROOT / path

    @field_validator("transcription_python_path", mode="before")
    @classmethod
    def resolve_transcription_python_path(cls, value: object) -> Path | None:
        if value is None or str(value).strip() == "":
            return None
        path = Path(str(value))
        return path if path.is_absolute() else REPOSITORY_ROOT / path

    @model_validator(mode="after")
    def validate_ranges(self) -> "Settings":
        if self.transcription_maximum_frequency_hz <= self.transcription_minimum_frequency_hz:
            raise ValueError("transcription_maximum_frequency_hz must exceed the minimum frequency")
        if self.quantization_maximum_bpm <= self.quantization_minimum_bpm:
            raise ValueError("quantization_maximum_bpm must exceed quantization_minimum_bpm")
        if self.interpretation_middle_register_high < self.interpretation_middle_register_low:
            raise ValueError("interpretation middle-register bounds are reversed")
        if self.interpretation_high_confidence_margin < self.interpretation_ambiguity_margin:
            raise ValueError(
                "interpretation_high_confidence_margin must meet or exceed ambiguity margin"
            )
        if self.voice_high_separation_semitones < self.voice_close_separation_semitones:
            raise ValueError("voice_high_separation_semitones must meet or exceed close separation")
        return self

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

    @property
    def resolved_transcription_python_path(self) -> Path:
        if self.transcription_python_path is not None:
            return self.transcription_python_path
        executable = "python.exe" if os.name == "nt" else "python"
        scripts_dir = "Scripts" if os.name == "nt" else "bin"
        return REPOSITORY_ROOT / ".venv-transcription" / scripts_dir / executable
