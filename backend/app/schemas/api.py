from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.capabilities import Capability
from app.models.entities import (
    ArtifactKind,
    AssignmentAmbiguityReason,
    DetectionSource,
    Hand,
    KeyAmbiguityReason,
    KeyMode,
    KeySource,
    MediaStreamType,
    ProjectStatus,
    SettingSource,
    SpellingAmbiguityReason,
    Staff,
    TempoSource,
    VoiceAmbiguityReason,
)


class DependencyResponse(BaseModel):
    name: str
    available: bool
    path: str | None
    version: str | None
    error: str | None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    dependencies: list[DependencyResponse]
    capabilities: list[Capability]


class ConfigResponse(BaseModel):
    max_upload_mb: int
    supported_extensions: list[str]
    workspace_dir: str


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MediaStreamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stream_index: int
    stream_type: MediaStreamType
    codec_name: str | None
    codec_long_name: str | None
    duration_seconds: float | None
    bit_rate: int | None
    sample_rate: int | None
    channels: int | None
    channel_layout: str | None
    width: int | None
    height: int | None
    frame_rate: str | None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: ProjectStatus
    original_filename: str | None
    media_type: str | None
    source_size_bytes: int | None
    duration_seconds: float | None
    container_format: str | None
    source_bit_rate: int | None
    estimated_tempo_bpm: float | None
    selected_tempo_bpm: float | None
    tempo_source: TempoSource | None
    measure_origin_seconds: float | None
    measure_origin_source: SettingSource | None
    meter_numerator: int | None
    meter_denominator: int | None
    meter_source: SettingSource | None
    current_quantization_run_id: int | None
    quantization_revision: int
    current_interpretation_run_id: int | None
    interpretation_revision: int
    current_voice_run_id: int | None
    voice_revision: int
    key_tonic_step: str | None
    key_tonic_alter: int | None
    key_mode: KeyMode | None
    key_confidence: float | None
    key_ambiguity_reason: KeyAmbiguityReason | None
    key_source: KeySource | None
    current_spelling_run_id: int | None
    spelling_revision: int
    media_streams: list[MediaStreamResponse]
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    project: ProjectResponse
    artifact_id: int
    stored_filename: str
    detected_type: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ArtifactKind
    relative_path: str
    size_bytes: int
    created_at: datetime


class MediaProcessResponse(BaseModel):
    project: ProjectResponse
    normalized_artifact: ArtifactResponse
    reused: bool


class NoteEventResponse(BaseModel):
    id: int
    pitch: int
    velocity: int
    raw_start_seconds: float
    raw_end_seconds: float
    confidence: float | None
    pitch_bends: list[int] | None
    source: DetectionSource


class TranscriptionProvenanceResponse(BaseModel):
    run_id: int
    model_name: str
    model_version: str
    model_runtime: str
    configuration: dict[str, object]


class TranscriptionResponse(BaseModel):
    project: ProjectResponse
    note_events_artifact: ArtifactResponse
    raw_midi_artifact: ArtifactResponse
    note_count: int
    preview_notes: list[NoteEventResponse]
    provenance: TranscriptionProvenanceResponse
    reused: bool


class QuantizationRequest(BaseModel):
    tempo_bpm: float | None = Field(default=None, gt=0, le=400)
    meter_numerator: int | None = Field(default=None)
    meter_denominator: int | None = Field(default=None)
    measure_origin_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_meter(self) -> "QuantizationRequest":
        if (self.meter_numerator is None) != (self.meter_denominator is None):
            raise ValueError("Meter numerator and denominator must be provided together.")
        if self.meter_numerator is not None and (
            self.meter_numerator,
            self.meter_denominator,
        ) not in {(2, 4), (3, 4), (4, 4)}:
            raise ValueError("Supported meters are 2/4, 3/4, and 4/4.")
        return self


class TempoEstimateDiagnosticsResponse(BaseModel):
    candidate_bpm: float | None
    residual: float | None
    inlier_coverage: float | None
    winning_score: float | None
    runner_up_score: float | None
    score_margin: float | None
    chord_group_count: int
    onset_span_seconds: float
    octave_ambiguous: bool


class QuantizedNoteResponse(BaseModel):
    id: int
    pitch: int
    velocity: int
    raw_start_seconds: float
    raw_end_seconds: float
    symbolic_start_beats: float
    symbolic_duration_beats: float
    chord_group: int
    measure_number: int
    beat_in_measure: float
    confidence: float | None
    source: DetectionSource


class QuantizationProvenanceResponse(BaseModel):
    run_id: int
    processor_name: str
    processor_version: str
    runtime: str
    input_fingerprint: str
    configuration: dict[str, object]


class QuantizationResponse(BaseModel):
    project: ProjectResponse
    note_count: int
    preview_notes: list[QuantizedNoteResponse]
    diagnostics: TempoEstimateDiagnosticsResponse
    provenance: QuantizationProvenanceResponse
    reused: bool


class InterpretedNoteResponse(BaseModel):
    id: int
    pitch: int
    symbolic_start_beats: float
    symbolic_duration_beats: float
    chord_group: int
    hand: Hand
    staff: Staff
    hand_confidence: float = Field(ge=0, le=1)
    staff_confidence: float = Field(ge=0, le=1)
    hand_ambiguity_reason: AssignmentAmbiguityReason | None
    staff_ambiguity_reason: AssignmentAmbiguityReason | None


class InterpretationDiagnosticsResponse(BaseModel):
    chord_group_count: int
    candidate_state_count: int
    transition_evaluations: int
    resolved_hand_count: int
    unknown_hand_count: int
    resolved_staff_count: int
    unknown_staff_count: int
    wide_chord_count: int
    crossing_pressure_count: int


class InterpretationProvenanceResponse(BaseModel):
    run_id: int
    processor_name: str
    processor_version: str
    runtime: str
    quantization_run_id: int
    input_fingerprint: str
    configuration: dict[str, object]


class InterpretationResponse(BaseModel):
    project: ProjectResponse
    note_count: int
    preview_notes: list[InterpretedNoteResponse]
    diagnostics: InterpretationDiagnosticsResponse
    provenance: InterpretationProvenanceResponse
    reused: bool


class VoicedNoteResponse(BaseModel):
    id: int
    pitch: int
    symbolic_start_beats: float
    symbolic_duration_beats: float
    chord_group: int
    hand: Hand
    staff: Staff
    voice: int | None = Field(default=None, ge=1)
    voice_confidence: float = Field(ge=0, le=1)
    voice_ambiguity_reason: VoiceAmbiguityReason | None


class VoiceDiagnosticsResponse(BaseModel):
    treble_note_count: int
    bass_note_count: int
    chord_node_count: int
    conflict_component_count: int
    two_voice_component_count: int
    crossing_component_count: int
    capacity_exceeded_count: int
    unresolved_staff_count: int
    resolved_count: int
    unknown_count: int
    treble_voice_1_count: int
    treble_voice_2_count: int
    bass_voice_1_count: int
    bass_voice_2_count: int


class VoiceProvenanceResponse(BaseModel):
    run_id: int
    processor_name: str
    processor_version: str
    runtime: str
    interpretation_run_id: int
    input_fingerprint: str
    configuration: dict[str, object]


class VoiceSeparationResponse(BaseModel):
    project: ProjectResponse
    note_count: int
    preview_notes: list[VoicedNoteResponse]
    diagnostics: VoiceDiagnosticsResponse
    provenance: VoiceProvenanceResponse
    reused: bool


class KeyOverrideRequest(BaseModel):
    tonic_step: Literal["A", "B", "C", "D", "E", "F", "G"]
    tonic_alter: int = Field(ge=-1, le=1)
    mode: KeyMode


class SpellingRequest(BaseModel):
    key_override: KeyOverrideRequest | None = None


class KeyResultResponse(BaseModel):
    source: KeySource
    tonic_step: str | None
    tonic_alter: int | None
    mode: KeyMode | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    ambiguity_reason: KeyAmbiguityReason | None
    key_signature_fifths: int | None


class SpelledNoteResponse(BaseModel):
    id: int
    pitch: int
    symbolic_start_beats: float
    symbolic_duration_beats: float
    chord_group: int
    hand: Hand
    staff: Staff
    voice: int | None = Field(default=None, ge=1)
    spelled_step: str | None
    spelled_alter: int | None = Field(default=None, ge=-2, le=2)
    spelled_octave: int | None = Field(default=None, ge=-2, le=9)
    spelling_confidence: float = Field(ge=0, le=1)
    spelling_ambiguity_reason: SpellingAmbiguityReason | None


class SpellingDiagnosticsResponse(BaseModel):
    pitch_class_histogram: list[float]
    best_key: str | None
    best_key_correlation: float | None
    runner_up_key: str | None
    runner_up_key_correlation: float | None
    key_correlation_margin: float = Field(ge=0, le=1)
    plausible_keys: list[str]
    candidate_set_sizes: list[int]
    chord_consistency_application_count: int
    melodic_rule_application_count: int
    resolved_count: int
    unknown_count: int
    unknown_key_count: int
    close_alternative_count: int


class SpellingProvenanceResponse(BaseModel):
    run_id: int
    processor_name: str
    processor_version: str
    runtime: str
    voice_run_id: int
    input_fingerprint: str
    configuration: dict[str, object]


class SpellingResponse(BaseModel):
    project: ProjectResponse
    key: KeyResultResponse
    note_count: int
    preview_notes: list[SpelledNoteResponse]
    diagnostics: SpellingDiagnosticsResponse
    provenance: SpellingProvenanceResponse
    reused: bool
