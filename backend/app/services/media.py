import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.dependencies import DependencyStatus
from app.core.errors import PianovaError
from app.models.entities import (
    Artifact,
    ArtifactKind,
    MediaStream,
    MediaStreamType,
    ProcessingRun,
    ProcessingStatus,
    Project,
    ProjectStatus,
    utc_now,
)

logger = logging.getLogger(__name__)
PROCESSING_STAGE = "media_normalization"


class FFprobeStream(BaseModel):
    index: int
    codec_type: str = "other"
    codec_name: str | None = None
    codec_long_name: str | None = None
    duration: str | float | int | None = None
    bit_rate: str | int | None = None
    sample_rate: str | int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    width: int | None = None
    height: int | None = None
    avg_frame_rate: str | None = None


class FFprobeFormat(BaseModel):
    format_name: str | None = None
    duration: str | float | int | None = None
    bit_rate: str | int | None = None


class FFprobePayload(BaseModel):
    streams: list[FFprobeStream]
    format: FFprobeFormat


@dataclass(frozen=True, slots=True)
class MediaInspection:
    duration_seconds: float
    container_format: str | None
    bit_rate: int | None
    streams: tuple[MediaStream, ...]


@dataclass(frozen=True, slots=True)
class MediaProcessResult:
    artifact: Artifact
    reused: bool


class MediaService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        ffmpeg: DependencyStatus,
        ffprobe: DependencyStatus,
    ) -> None:
        self.session = session
        self.settings = settings
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def process(self, project: Project) -> MediaProcessResult:
        source = self._artifact(project.id, ArtifactKind.SOURCE)
        if project.status is not ProjectStatus.UPLOADED or source is None:
            raise PianovaError(
                "source_not_uploaded",
                "Upload a source file before processing media.",
                409,
            )

        existing = self._artifact(project.id, ArtifactKind.NORMALIZED_AUDIO)
        if existing is not None:
            if not self._artifact_path(existing).is_file():
                raise PianovaError(
                    "normalized_artifact_missing",
                    "The normalized audio record exists, but its file is missing.",
                    500,
                )
            return MediaProcessResult(existing, reused=True)

        if not self.ffprobe.available or not self.ffprobe.path:
            raise PianovaError(
                "ffprobe_unavailable",
                "FFprobe is unavailable. Install it or configure PIANOVA_FFPROBE_PATH.",
                503,
            )
        if not self.ffmpeg.available or not self.ffmpeg.path:
            raise PianovaError(
                "ffmpeg_unavailable",
                "FFmpeg is unavailable. Install it or configure PIANOVA_FFMPEG_PATH.",
                503,
            )

        source_path = self._artifact_path(source)
        if not source_path.is_file():
            raise PianovaError("source_file_missing", "The uploaded source file is missing.", 500)

        run = ProcessingRun(
            project_id=project.id,
            stage=PROCESSING_STAGE,
            status=ProcessingStatus.RUNNING,
            started_at=utc_now(),
        )
        self.session.add(run)
        self.session.commit()

        token = uuid.uuid4().hex
        project_dir = source_path.parent
        temporary_path = project_dir / f".normalize-{token}.tmp.wav"
        final_path = project_dir / f"normalized-{token}.wav"
        finalized = False
        try:
            inspection = self._inspect(source_path, project.id)
            self._normalize(source_path, temporary_path)
            if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
                raise PianovaError(
                    "media_normalization_failed",
                    "FFmpeg did not produce a normalized audio file.",
                    422,
                )
            os.replace(temporary_path, final_path)
            finalized = True

            project.duration_seconds = inspection.duration_seconds
            project.container_format = inspection.container_format
            project.source_bit_rate = inspection.bit_rate
            project.media_streams.clear()
            project.media_streams.extend(inspection.streams)

            artifact = Artifact(
                project_id=project.id,
                kind=ArtifactKind.NORMALIZED_AUDIO,
                relative_path=str(final_path.relative_to(self.settings.workspace_dir)),
                size_bytes=final_path.stat().st_size,
            )
            self.session.add(artifact)
            run.status = ProcessingStatus.SUCCEEDED
            run.completed_at = utc_now()
            self.session.commit()
            return MediaProcessResult(artifact, reused=False)
        except PianovaError as error:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            if finalized:
                final_path.unlink(missing_ok=True)
            self._mark_failed(run.id, error.message)
            raise
        except IntegrityError as error:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            if finalized:
                final_path.unlink(missing_ok=True)
            self._mark_failed(run.id, "Media metadata could not be committed.")
            raise PianovaError(
                "media_already_processed",
                "This project already has normalized audio.",
                409,
            ) from error
        except Exception as error:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            if finalized:
                final_path.unlink(missing_ok=True)
            self._mark_failed(run.id, "Media processing failed.")
            logger.exception("Media processing failed for project %s", project.id)
            raise PianovaError(
                "media_processing_failed",
                "The source could not be inspected and normalized.",
                500,
            ) from error

    def _artifact(self, project_id: str, kind: ArtifactKind) -> Artifact | None:
        return self.session.scalar(
            select(Artifact).where(Artifact.project_id == project_id, Artifact.kind == kind)
        )

    def _artifact_path(self, artifact: Artifact) -> Path:
        workspace = self.settings.workspace_dir.resolve()
        candidate = (workspace / artifact.relative_path).resolve()
        if not candidate.is_relative_to(workspace):
            raise PianovaError("invalid_artifact_path", "Stored artifact metadata is invalid.", 500)
        return candidate

    def _inspect(self, source_path: Path, project_id: str) -> MediaInspection:
        try:
            result = subprocess.run(
                [
                    self.ffprobe.path or "ffprobe",
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(source_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.media_inspection_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise PianovaError(
                "media_inspection_timeout",
                "Media inspection timed out.",
                504,
            ) from error
        except OSError as error:
            raise PianovaError(
                "ffprobe_unavailable",
                "FFprobe could not be started.",
                503,
            ) from error

        if result.returncode != 0:
            raise PianovaError(
                "media_inspection_failed",
                "FFprobe could not decode the uploaded source.",
                422,
                {"exit_code": result.returncode},
            )
        try:
            payload = FFprobePayload.model_validate_json(result.stdout)
        except ValidationError as error:
            raise PianovaError(
                "invalid_ffprobe_output",
                "FFprobe returned invalid media metadata.",
                502,
            ) from error

        streams = tuple(self._stream_model(project_id, stream) for stream in payload.streams)
        if not any(stream.stream_type is MediaStreamType.AUDIO for stream in streams):
            raise PianovaError(
                "audio_stream_missing",
                "The uploaded media does not contain an audio stream.",
                422,
            )
        duration = _float_value(payload.format.duration)
        if duration is None:
            durations = [
                stream.duration_seconds for stream in streams if stream.duration_seconds is not None
            ]
            duration = max(durations, default=None)
        if duration is None or duration <= 0:
            raise PianovaError(
                "media_duration_missing",
                "The media duration could not be determined.",
                422,
            )
        return MediaInspection(
            duration_seconds=duration,
            container_format=payload.format.format_name,
            bit_rate=_int_value(payload.format.bit_rate),
            streams=streams,
        )

    def _normalize(self, source_path: Path, output_path: Path) -> None:
        try:
            result = subprocess.run(
                [
                    self.ffmpeg.path or "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source_path),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    str(self.settings.normalized_channels),
                    "-ar",
                    str(self.settings.normalized_sample_rate),
                    "-c:a",
                    "pcm_s16le",
                    str(output_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.media_normalization_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise PianovaError(
                "media_normalization_timeout",
                "Audio normalization timed out.",
                504,
            ) from error
        except OSError as error:
            raise PianovaError(
                "ffmpeg_unavailable",
                "FFmpeg could not be started.",
                503,
            ) from error
        if result.returncode != 0:
            raise PianovaError(
                "media_normalization_failed",
                "FFmpeg could not normalize the uploaded source.",
                422,
                {"exit_code": result.returncode},
            )

    def _stream_model(self, project_id: str, stream: FFprobeStream) -> MediaStream:
        stream_type = {
            "audio": MediaStreamType.AUDIO,
            "video": MediaStreamType.VIDEO,
        }.get(stream.codec_type, MediaStreamType.OTHER)
        return MediaStream(
            project_id=project_id,
            stream_index=stream.index,
            stream_type=stream_type,
            codec_name=stream.codec_name,
            codec_long_name=stream.codec_long_name,
            duration_seconds=_float_value(stream.duration),
            bit_rate=_int_value(stream.bit_rate),
            sample_rate=_int_value(stream.sample_rate),
            channels=stream.channels,
            channel_layout=stream.channel_layout,
            width=stream.width,
            height=stream.height,
            frame_rate=stream.avg_frame_rate,
        )

    def _mark_failed(self, run_id: int, message: str) -> None:
        try:
            run = self.session.get(ProcessingRun, run_id)
            if run is None:
                return
            run.status = ProcessingStatus.FAILED
            run.error_message = message
            run.completed_at = utc_now()
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Could not persist failed processing run %s", run_id)


def _float_value(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
