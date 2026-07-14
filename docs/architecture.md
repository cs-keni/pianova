# Architecture

Pianova is one local web application with two runtime processes. Next.js owns interaction and presentation. FastAPI owns validation, persistence, files, executable discovery, and every processing stage.

## Boundaries

```text
Next.js browser UI
  | typed JSON and multipart HTTP
  v
FastAPI routes
  |-- services: project lifecycle and safe storage
  |-- repositories: SQLAlchemy persistence access
  |-- core: settings, errors, capabilities, executable probes
  v
SQLite + workspace/projects/<UUID>/
```

The frontend depends only on API contracts. Processing services never depend on frontend modules or browser state. This keeps media, transcription, symbolic cleanup, and notation stages independently testable.

## Runtime composition

`app.main.create_app` constructs settings, a SQLAlchemy engine and session factory, a cached dependency snapshot, raw upload-size and CORS middleware, structured exception handlers, and the `/api` router. Tests inject temporary settings and deterministic dependency states.

Alembic owns database creation. Application startup does not silently create tables, so schema drift fails visibly and migrations remain reviewable.

## Persistence and files

SQLite stores metadata and processing state. Source media and later generated artifacts live under `workspace/projects/<project-id>/`. Database rows store project-relative paths rather than arbitrary absolute paths.

Upload finalization has an explicit order:

```text
stream to hidden temp file
  -> enforce byte limit while reading
  -> compare extension and detected signature
  -> os.replace to generated final name
  -> commit artifact and project metadata
  -> remove final file if the commit fails
```

The ASGI boundary rejects oversized multipart bodies before form parsing, while the storage service independently enforces the source-byte limit. This favors consistent database/filesystem state over raw upload throughput. It also prevents client filenames from becoming storage paths or client MIME claims from becoming trusted metadata.

## External executables

FFmpeg, FFprobe, and MuseScore are configured by optional explicit paths or normal executable discovery. Each probe uses an argument list, captures output, and has a bounded timeout. The cached result feeds the capability registry; request handlers do not repeatedly launch subprocesses.

## Capability truth

Capabilities have three states:

- `available`: the required dependency is present and the capability may be used.
- `unavailable`: a required local dependency is missing.
- `not_implemented`: Pianova does not have that stage yet, even if dependencies exist.

This contract prevents the interface from confusing a detected executable with an implemented product feature.

## Transcription boundary

Basic Pitch is an optional dependency group, not part of ordinary API development. When transcription begins, a `PianoTranscriber`-style interface will convert normalized WAV input into typed note events. A separate process is deferred until dependency conflicts or resource isolation make it necessary.

## Trade-offs

- One FastAPI process is simpler than a local queue, but long processing will eventually require a small worker boundary.
- SQLite and local files match the single-user product, but do not provide distributed coordination.
- Signature validation is fast and safe for upload acceptance, but FFprobe must still prove decodability in the next milestone.
- Cached dependency states avoid repeated subprocess cost, but executable changes require an application restart.

Related: [pipeline](pipeline.md), [data model](data-model.md), and [roadmap](roadmap.md).
