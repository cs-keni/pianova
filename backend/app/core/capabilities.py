from enum import StrEnum

from pydantic import BaseModel


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_IMPLEMENTED = "not_implemented"


class Capability(BaseModel):
    key: str
    label: str
    state: CapabilityState
    reason: str | None = None


def build_capabilities(*, ffmpeg: bool, ffprobe: bool, musescore: bool) -> list[Capability]:
    media_ready = ffmpeg and ffprobe
    return [
        Capability(
            key="media_normalization",
            label="Media normalization",
            state=CapabilityState.AVAILABLE if media_ready else CapabilityState.UNAVAILABLE,
            reason=(
                "FFprobe inspection and FFmpeg WAV normalization are ready."
                if media_ready
                else "FFmpeg and FFprobe are required for media processing."
            ),
        ),
        Capability(
            key="transcription",
            label="Piano transcription",
            state=CapabilityState.NOT_IMPLEMENTED,
            reason="The transcription pipeline has not been implemented yet.",
        ),
        Capability(
            key="musicxml",
            label="MusicXML generation",
            state=CapabilityState.NOT_IMPLEMENTED,
            reason="Notation reconstruction has not been implemented yet.",
        ),
        Capability(
            key="score_rendering",
            label="Score rendering",
            state=CapabilityState.NOT_IMPLEMENTED,
            reason=(
                "Score rendering has not been implemented yet."
                if musescore
                else "MuseScore was not found; MusicXML export will remain independent."
            ),
        ),
    ]
