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


def build_capabilities(
    *,
    ffmpeg: bool,
    ffprobe: bool,
    musescore: bool,
    transcription: bool,
) -> list[Capability]:
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
            state=CapabilityState.AVAILABLE if transcription else CapabilityState.UNAVAILABLE,
            reason=(
                "Basic Pitch transcription and raw MIDI generation are ready."
                if transcription
                else "Install the isolated Basic Pitch transcription environment."
            ),
        ),
        Capability(
            key="quantization",
            label="Tempo and rhythm quantization",
            state=CapabilityState.AVAILABLE,
            reason="Global tempo estimation and readable straight-note quantization are ready.",
        ),
        Capability(
            key="interpretation",
            label="Hand and staff assignment",
            state=CapabilityState.AVAILABLE,
            reason="Independent hand and notation-staff assignment with uncertainty is ready.",
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
