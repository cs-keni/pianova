# Data Model Reference

Alembic revision `20260714_0001` creates the initial tables; revision `20260714_0002` adds the per-project artifact-kind invariant; revision `20260716_0003` adds inspected project metadata and typed media streams; revision `20260716_0004` adds transcription evidence and ProcessingRun provenance. SQLAlchemy persistence models are separate from Pydantic API schemas.

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
- `hand`: left, right, or unknown.
- `source`: audio, video, audio-and-video, or manual.

This split lets Pianova simplify rubato into readable rhythm without destroying the model's original evidence.

## ProcessingRun

Each row records a `stage`, status, optional error message, and nullable start/completion timestamps. Status values are pending, running, succeeded, and failed. Media preparation and transcription create running and terminal audit rows.

Transcription runs additionally retain `model_name`, `model_version`, `model_runtime`, and `configuration_json`. This records the Basic Pitch/TensorFlow dependency versions and thresholds used to produce the raw evidence.

## API schemas

- `ProjectCreate`: `title`, 1-120 characters; whitespace-only titles are rejected by the service.
- `ProjectResponse`: project identity, status, source metadata, and timestamps.
- `HealthResponse`: application state, dependency probes, and capability registry.
- `DependencyResponse`: executable name, availability, resolved path, version line, and error.
- `ConfigResponse`: upload limit, extensions, and workspace location.
- `UploadResponse`: updated project, artifact ID, generated filename, and detected type.
- `MediaProcessResponse`: inspected project and streams, normalized Artifact, and whether an existing result was reused.
- `TranscriptionResponse`: note-event and raw-MIDI Artifacts, total note count, a bounded note preview, model provenance, and whether existing output was reused.

API failures use `{ "error": { "code", "message", "details" } }`. Validation failures use the same envelope.

Related: [architecture](architecture.md) and [pipeline](pipeline.md).
