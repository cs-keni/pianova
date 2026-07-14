import shutil
import subprocess
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    name: str
    available: bool
    path: str | None
    version: str | None
    error: str | None = None


def _probe(name: str, configured_path: str | None, timeout: float) -> DependencyStatus:
    executable = configured_path or shutil.which(name)
    if not executable:
        return DependencyStatus(
            name=name, available=False, path=None, version=None, error="not found"
        )
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return DependencyStatus(
            name=name,
            available=False,
            path=executable,
            version=None,
            error=type(error).__name__,
        )
    output = (result.stdout or result.stderr).splitlines()
    return DependencyStatus(
        name=name,
        available=result.returncode == 0,
        path=executable,
        version=output[0] if output else None,
        error=None if result.returncode == 0 else f"exit code {result.returncode}",
    )


def probe_dependencies(settings: Settings) -> dict[str, DependencyStatus]:
    timeout = settings.dependency_probe_timeout_seconds
    musescore_path = (
        settings.musescore_path or shutil.which("musescore4") or shutil.which("musescore")
    )
    return {
        "ffmpeg": _probe("ffmpeg", settings.ffmpeg_path, timeout),
        "ffprobe": _probe("ffprobe", settings.ffprobe_path, timeout),
        "musescore": _probe("musescore", musescore_path, timeout),
    }
