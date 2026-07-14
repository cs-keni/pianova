# Data Model Reference

Alembic revision `20260714_0001` creates four tables; revision `20260714_0002` adds the per-project artifact-kind invariant. SQLAlchemy persistence models are separate from Pydantic API schemas.

## Project

| Field | Type | Constraint/purpose |
|---|---|---|
| `id` | string(36) | Generated UUID primary key |
| `title` | string(120) | Required project display name |
| `status` | enum | `created`, `uploaded`, or `failed` |
| `original_filename` | string(255), nullable | Display metadata only, never a storage path |
| `media_type` | string(100), nullable | Signature-detected source media type |
| `source_size_bytes` | integer, nullable | Stored source size |
| `created_at`, `updated_at` | timestamps | UTC lifecycle timestamps |

## Artifact

Artifacts belong to a Project through `project_id`. `relative_path` is limited to 500 characters and resolves beneath the configured workspace. `size_bytes` and `created_at` record storage metadata. A database uniqueness constraint permits only one artifact of each kind per project; the current API therefore accepts only one source upload.

Kinds: `source`, `normalized_audio`, `note_events`, `raw_midi`, `clean_midi`, `musicxml`, and `pdf`. Only `source` is produced today.

## NoteEvent

Note events preserve performed timing separately from later notation:

- `pitch` and `velocity`: MIDI integers.
- `raw_start_seconds`, `raw_end_seconds`: detected performance timing.
- `symbolic_start_beats`, `symbolic_duration_beats`: nullable quantized notation timing.
- `hand`: left, right, or unknown.
- `source`: audio, video, audio-and-video, or manual.

This split lets Pianova simplify rubato into readable rhythm without destroying the model's original evidence.

## ProcessingRun

Each row records a `stage`, status, optional error message, and nullable start/completion timestamps. Status values are pending, running, succeeded, and failed. Processing execution is not implemented yet; the table establishes its audit boundary.

## API schemas

- `ProjectCreate`: `title`, 1-120 characters; whitespace-only titles are rejected by the service.
- `ProjectResponse`: project identity, status, source metadata, and timestamps.
- `HealthResponse`: application state, dependency probes, and capability registry.
- `DependencyResponse`: executable name, availability, resolved path, version line, and error.
- `ConfigResponse`: upload limit, extensions, and workspace location.
- `UploadResponse`: updated project, artifact ID, generated filename, and detected type.

API failures use `{ "error": { "code", "message", "details" } }`. Validation failures use the same envelope.

Related: [architecture](architecture.md) and [pipeline](pipeline.md).
