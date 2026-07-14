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


class NoteEvent(Base):
    __tablename__ = "note_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    pitch: Mapped[int] = mapped_column(Integer)
    velocity: Mapped[int] = mapped_column(Integer)
    raw_start_seconds: Mapped[float] = mapped_column(Float)
    raw_end_seconds: Mapped[float] = mapped_column(Float)
    symbolic_start_beats: Mapped[float | None] = mapped_column(Float, nullable=True)
    symbolic_duration_beats: Mapped[float | None] = mapped_column(Float, nullable=True)
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


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(100))
    status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, native_enum=False))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="processing_runs")
