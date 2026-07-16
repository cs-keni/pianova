from pydantic import BaseModel, Field, model_validator


class RawTranscriptionNote(BaseModel):
    pitch: int = Field(ge=0, le=127)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    velocity: int = Field(ge=1, le=127)
    confidence: float = Field(ge=0, le=1)
    pitch_bends: list[int] | None = None

    @model_validator(mode="after")
    def validate_timing(self) -> "RawTranscriptionNote":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Note end time must be after its start time.")
        return self


class TranscriptionProvenance(BaseModel):
    model_name: str
    model_version: str
    model_runtime: str
    runtime_version: str
    model_serialization: str
    configuration: dict[str, float | bool]


class WorkerTranscriptionOutput(BaseModel):
    schema_version: int = 1
    provenance: TranscriptionProvenance
    notes: list[RawTranscriptionNote]
