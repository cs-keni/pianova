import os
import uuid
from pathlib import Path

import filetype  # type: ignore[import-untyped]
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import PianovaError
from app.models.entities import Artifact, ArtifactKind, Project, ProjectStatus

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".mov"}
COMPATIBLE_SIGNATURES = {
    ".mp3": {"mp3"},
    ".wav": {"wav"},
    ".m4a": {"m4a", "mp4", "mov"},
    ".mp4": {"m4a", "mp4", "mov"},
    ".mov": {"m4a", "mp4", "mov"},
}
CHUNK_SIZE = 1024 * 1024
SIGNATURE_BYTES = 8192


class UploadService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def store(self, project: Project, upload: UploadFile) -> tuple[Artifact, str, str]:
        original_name = Path(upload.filename or "").name
        extension = Path(original_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise PianovaError(
                "unsupported_media",
                "Supported file types are MP3, WAV, M4A, MP4, and MOV.",
                415,
            )

        project_dir = self.settings.workspace_dir / "projects" / project.id
        if not project_dir.is_dir():
            raise PianovaError("project_storage_missing", "Project storage is unavailable.", 500)

        token = uuid.uuid4().hex
        temporary_path = project_dir / f".upload-{token}.tmp"
        stored_filename = f"source-{token}{extension}"
        final_path = project_dir / stored_filename
        total_bytes = 0
        signature = bytearray()

        try:
            with temporary_path.open("xb") as target:
                while chunk := await upload.read(CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > self.settings.max_upload_bytes:
                        raise PianovaError(
                            "upload_too_large",
                            f"The upload exceeds the {self.settings.max_upload_mb} MB limit.",
                            413,
                        )
                    if len(signature) < SIGNATURE_BYTES:
                        remaining = SIGNATURE_BYTES - len(signature)
                        signature.extend(chunk[:remaining])
                    target.write(chunk)

            if total_bytes == 0:
                raise PianovaError("empty_upload", "The uploaded file is empty.", 422)

            detected = filetype.guess(bytes(signature))
            detected_extension = detected.extension.lower() if detected else "unknown"
            if detected_extension not in COMPATIBLE_SIGNATURES[extension]:
                raise PianovaError(
                    "invalid_media_signature",
                    "The file contents do not match its supported media extension.",
                    415,
                    {"extension": extension, "detected": detected_extension},
                )

            os.replace(temporary_path, final_path)
            artifact = Artifact(
                project_id=project.id,
                kind=ArtifactKind.SOURCE,
                relative_path=str(Path("projects") / project.id / stored_filename),
                size_bytes=total_bytes,
            )
            project.original_filename = original_name
            project.media_type = upload.content_type or detected.mime
            project.source_size_bytes = total_bytes
            project.status = ProjectStatus.UPLOADED
            self.session.add(artifact)
            self.session.commit()
            self.session.refresh(artifact)
            return artifact, stored_filename, detected_extension
        except PianovaError:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        except Exception as error:
            self.session.rollback()
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise PianovaError("upload_failed", "The upload could not be stored.", 500) from error
        finally:
            await upload.close()
