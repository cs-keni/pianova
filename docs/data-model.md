# Data Model Reference

Alembic revision `20260714_0001` creates the initial tables; revision `20260714_0002` adds the per-project artifact-kind invariant; revision `20260716_0003` adds inspected project metadata and typed media streams; revision `20260716_0004` adds transcription evidence and ProcessingRun provenance; revision `20260716_0005` adds symbolic timing metadata, chord groups, invariants, and optimistic revision state; revision `20260716_0006` adds hand/staff state, confidence, ambiguity, ownership, and revision constraints; revision `20260718_0007` adds the checked notation-voice state and project ownership/revision fields. SQLAlchemy persistence models are separate from Pydantic API schemas.

## Project

| Field | Type | Constraint/purpose |
|---|---|---|
| `id` | string(36) | Generated UUID primary key |
| `title` | string(120) | Required project display name |
| `status` | enum | `created`, `uploaded`, or `failed` |
| `original_filename` | string(255), nullable | Display metadata only, never a storage path |
| `media_type` | string(100), nullable | Signature-detected source media type |
| `source_size_bytes` | integer, nullable | Stored source size |
| `duration_seconds` | float, nullable | FFprobe container/stream duration |
| `container_format` | string(200), nullable | FFprobe format name |
| `source_bit_rate` | integer, nullable | FFprobe aggregate bit rate |
| `estimated_tempo_bpm` | float, nullable | Accepted automatic estimate; nullable for override-only results |
| `selected_tempo_bpm` | float, nullable | Effective positive quarter-note BPM |
| `tempo_source` | enum, nullable | `estimated` or `override` |
| `measure_origin_seconds` | float, nullable | Timestamp treated as measure 1 beat 1 |
| `measure_origin_source` | enum, nullable | `default` or `override` |
| `meter_numerator`, `meter_denominator` | integers, nullable | Complete supported pair: `2/4`, `3/4`, or `4/4` |
| `meter_source` | enum, nullable | `default` or `override` |
| `current_quantization_run_id` | integer, nullable | ProcessingRun that owns current symbolic state |
| `quantization_revision` | integer | Non-negative optimistic-concurrency counter |
| `current_interpretation_run_id` | integer, nullable | Successful ProcessingRun that owns current hand/staff state |
| `interpretation_revision` | integer | Non-negative optimistic-concurrency and invalidation counter |
| `current_voice_run_id` | integer, nullable | Successful ProcessingRun that owns current notation-voice state |
| `voice_revision` | integer | Non-negative optimistic-concurrency and invalidation counter |
| `created_at`, `updated_at` | timestamps | UTC lifecycle timestamps |

## Artifact

Artifacts belong to a Project through `project_id`. `relative_path` is limited to 500 characters and resolves beneath the configured workspace. `size_bytes` and `created_at` record storage metadata. A database uniqueness constraint permits only one artifact of each kind per project; the current API therefore accepts only one source upload.

Kinds: `source`, `normalized_audio`, `note_events`, `raw_midi`, `clean_midi`, `musicxml`, and `pdf`. Source, normalized-audio, note-event JSON, and raw-MIDI artifacts are produced today.

## MediaStream

Each FFprobe stream is stored with a unique `(project_id, stream_index)` pair. Common fields are stream type, codec names, duration, and bit rate. Audio fields include sample rate, channel count, and channel layout. Video fields include width, height, and frame rate. Unknown stream types remain recorded as `other` so inspection does not discard evidence needed by later video work.

## NoteEvent

Note events preserve performed timing separately from later notation:

- `pitch` and `velocity`: MIDI integers.
- `raw_start_seconds`, `raw_end_seconds`: detected performance timing.
- `confidence`: nullable model confidence from zero to one.
- `pitch_bends_json`: nullable raw Basic Pitch bend evidence.
- `symbolic_start_beats`, `symbolic_duration_beats`: nullable quantized notation timing.
- `chord_group`: nullable positive chronological group number.
- `hand`: left, right, or unknown.
- `staff`: treble, bass, or unknown; independent from hand.
- `hand_confidence`, `staff_confidence`: nullable bounded evidence margins in `[0, 1]`.
- `hand_ambiguity_reason`, `staff_ambiguity_reason`: nullable typed primary reason; required by service invariants for unknown assignments and absent for resolved assignments.
- `voice`: nullable staff-scoped notation voice, checked `>= 1` when present. Version 1 of the
  engine emits only voice 1 or 2; the schema admits future higher voice numbers without migration.
- `voice_confidence`: nullable normalized decision score in `[0, 1]`; it is not a calibrated
  probability.
- `voice_ambiguity_reason`: nullable typed reason: `unresolved_staff`,
  `voice_capacity_exceeded`, `crossing`, or `close_alternative`.
- `source`: audio, video, audio-and-video, or manual.

The three voice fields have exactly three valid database states:

- unprocessed: voice, score, and reason are all null;
- resolved: voice and score are present, reason is null;
- unknown: voice is null, score and reason are present.

All other combinations fail the named `ck_note_events_voice_state` constraint.

This split lets Pianova simplify rubato into readable rhythm without destroying the model's original evidence.

## ProcessingRun

Each row records a `stage`, status, optional error message, and nullable start/completion timestamps. Status values are pending, running, succeeded, and failed. Media preparation, transcription, quantization, interpretation, and voice separation create running and terminal audit rows.

Transcription runs additionally retain `model_name`, `model_version`, `model_runtime`, and `configuration_json`. This records the Basic Pitch/TensorFlow dependency versions and thresholds used to produce the raw evidence.

Quantization keeps the ML columns empty and stores processor identity, raw-note fingerprint,
effective settings, fit diagnostics, and result metadata in `configuration_json`. The project
current-run pointer plus revision identify which successful run owns the persisted symbolic fields.

Interpretation also keeps the ML columns empty. Its JSON records processor/runtime identity,
current quantization ownership, input fingerprint, scoring settings, work bounds, and diagnostics.
The project current-run pointer plus interpretation revision identify the owner of persisted
hand/staff state. Re-quantization clears that pointer and all assignments atomically.

Voice runs keep the ML columns empty. Their JSON records processor/runtime identity, current
interpretation ownership, input fingerprint, effective thresholds, algorithm version, and
diagnostics. The project current-run pointer plus voice revision identify the owner of persisted
voice state. Genuine upstream recomputation clears downstream pointers and fields atomically;
SQL-relative revision increments preserve invalidation under concurrent stage commits.

## API schemas

- `ProjectCreate`: `title`, 1-120 characters; whitespace-only titles are rejected by the service.
- `ProjectResponse`: project identity, source metadata, current stage ownership/revisions, and timestamps.
- `HealthResponse`: application state, dependency probes, and capability registry.
- `DependencyResponse`: executable name, availability, resolved path, version line, and error.
- `ConfigResponse`: upload limit, extensions, and workspace location.
- `UploadResponse`: updated project, artifact ID, generated filename, and detected type.
- `MediaProcessResponse`: inspected project and streams, normalized Artifact, and whether an existing result was reused.
- `TranscriptionResponse`: note-event and raw-MIDI Artifacts, total note count, a bounded note preview, model provenance, and whether existing output was reused.
- `QuantizationResponse`: updated project timing, bounded symbolic-note preview, typed fit diagnostics, processor provenance, and reuse state.
- `InterpretationResponse`: updated ownership/revision, bounded assignment preview, resolved/unknown and work diagnostics, processor provenance, and reuse state.
- `VoiceSeparationResponse`: updated ownership/revision, bounded voice preview, per-staff voice counts and structural diagnostics, processor provenance, and reuse state.

API failures use `{ "error": { "code", "message", "details" } }`. Validation failures use the same envelope.

Related: [architecture](architecture.md) and [pipeline](pipeline.md).
