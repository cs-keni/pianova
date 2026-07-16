import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(enum.StrEnum):
    CREATED = "created"
    UPLOADED = "uploaded"
    FAILED = "failed"


class Hand(enum.StrEnum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


class DetectionSource(enum.StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    AUDIO_AND_VIDEO = "audio_and_video"
    MANUAL = "manual"


class TempoSource(enum.StrEnum):
    ESTIMATED = "estimated"
    OVERRIDE = "override"


class SettingSource(enum.StrEnum):
    DEFAULT = "default"
    OVERRIDE = "override"


class ArtifactKind(enum.StrEnum):
    SOURCE = "source"
    NORMALIZED_AUDIO = "normalized_audio"
    NOTE_EVENTS = "note_events"
    RAW_MIDI = "raw_midi"
    CLEAN_MIDI = "clean_midi"
    MUSICXML = "musicxml"
    PDF = "pdf"


class ProcessingStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MediaStreamType(enum.StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False), default=ProjectStatus.CREATED
    )
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    container_format: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_tempo_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected_tempo_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    tempo_source: Mapped[TempoSource | None] = mapped_column(
        Enum(TempoSource, native_enum=False), nullable=True
    )
    measure_origin_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    measure_origin_source: Mapped[SettingSource | None] = mapped_column(
        Enum(SettingSource, native_enum=False), nullable=True
    )
    meter_numerator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meter_denominator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meter_source: Mapped[SettingSource | None] = mapped_column(
        Enum(SettingSource, native_enum=False), nullable=True
    )
    current_quantization_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantization_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", passive_deletes=True
    )
    note_events: Mapped[list["NoteEvent"]] = relationship(
        back_populates="project", passive_deletes=True
    )
    processing_runs: Mapped[list["ProcessingRun"]] = relationship(
        back_populates="project", passive_deletes=True
    )
    media_streams: Mapped[list["MediaStream"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MediaStream.stream_index",
    )


class NoteEvent(Base):
    __tablename__ = "note_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    pitch: Mapped[int] = mapped_column(Integer)
    velocity: Mapped[int] = mapped_column(Integer)
    raw_start_seconds: Mapped[float] = mapped_column(Float)
    raw_end_seconds: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch_bends_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbolic_start_beats: Mapped[float | None] = mapped_column(Float, nullable=True)
    symbolic_duration_beats: Mapped[float | None] = mapped_column(Float, nullable=True)
    chord_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hand: Mapped[Hand] = mapped_column(Enum(Hand, native_enum=False), default=Hand.UNKNOWN)
    source: Mapped[DetectionSource] = mapped_column(
        Enum(DetectionSource, native_enum=False), default=DetectionSource.AUDIO
    )

    project: Mapped[Project] = relationship(back_populates="note_events")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "kind", name="uq_artifact_project_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind, native_enum=False))
    relative_path: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="artifacts")


class MediaStream(Base):
    __tablename__ = "media_streams"
    __table_args__ = (
        UniqueConstraint("project_id", "stream_index", name="uq_media_stream_project_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    stream_index: Mapped[int] = mapped_column(Integer)
    stream_type: Mapped[MediaStreamType] = mapped_column(Enum(MediaStreamType, native_enum=False))
    codec_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    codec_long_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_layout: Mapped[str | None] = mapped_column(String(100), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_rate: Mapped[str | None] = mapped_column(String(50), nullable=True)

    project: Mapped[Project] = relationship(back_populates="media_streams")


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(100))
    status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, native_enum=False))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_runtime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    configuration_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="processing_runs")
