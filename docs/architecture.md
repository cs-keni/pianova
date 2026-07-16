# Architecture

Pianova is one local web application with two runtime processes. Next.js owns interaction and presentation. FastAPI owns validation, persistence, files, executable discovery, and every processing stage.

## Boundaries

```text
Next.js browser UI
  | typed JSON and multipart HTTP
  v
FastAPI routes
  |-- services: project lifecycle, storage, media preparation, transcription, symbolic timing
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

Media preparation is an explicit synchronous action after upload:

```text
source Artifact
  -> FFprobe JSON with a bounded timeout
  -> validate audio stream and positive duration
  -> FFmpeg mono 22.05 kHz PCM WAV in a temporary path
  -> atomic rename
  -> commit Project metadata, MediaStream rows, normalized Artifact, ProcessingRun
  -> remove temporary/final output and record a failed run on error
```

Completed normalized artifacts are idempotent: repeated requests return the existing file. Failed attempts do not create an Artifact and may be retried.

Transcription runs across a process boundary:

```text
FastAPI lightweight environment
  -> validate normalized Artifact and source duration
  -> create running ProcessingRun
  -> launch .venv-transcription Python with safe argument list
  -> Basic Pitch 0.4.0 / TensorFlow 2.15 inference
  -> validate versioned note-event JSON
  -> atomically finalize note-event JSON and raw MIDI
  -> commit NoteEvent rows, Artifacts, and model/config provenance
```

The worker is separately probed at startup and remains optional. A missing worker makes only
transcription unavailable; project creation, uploads, and media preparation continue working.
Successful repeat calls reuse both raw artifacts. Failed calls remove all partial/final output and
remain retryable.

Quantization stays inside the lightweight FastAPI process and consumes only persisted note evidence:

```text
ordered raw NoteEvent rows
  -> non-chaining onset/chord grouping
  -> bounded global-tempo candidate generation and fit gates, or explicit BPM override
  -> exact Fraction-based onset and duration quantization
  -> optimistic Project revision compare-and-swap
  -> commit Project timing, NoteEvent symbolic fields, and successful ProcessingRun
```

The pure `app.symbolic.timing` module has no database, filesystem, frontend, subprocess, or ML
dependencies. Raw seconds remain immutable evidence. Project timing and note symbolic fields are
recomputed together, and the project points at the run that produced its current result. A failed or
concurrent recomputation rolls back without damaging the prior symbolic state.

## External executables

FFmpeg, FFprobe, and MuseScore are configured by optional explicit paths or normal executable discovery. Startup probes use argument lists and bounded timeouts; the cached paths feed the capability registry and media service. Media subprocesses use separate configurable inspection and normalization timeouts.

## Capability truth

Capabilities have three states:

- `available`: the required dependency is present and the capability may be used.
- `unavailable`: a required local dependency is missing.
- `not_implemented`: Pianova does not have that stage yet, even if dependencies exist.

This contract prevents the interface from confusing a detected executable with an implemented product feature.

## Transcription boundary

`TranscriptionService` is the application-facing boundary. It does not import Basic Pitch,
TensorFlow, NumPy, librosa, or pretty_midi. `app.transcription.worker` owns those imports inside
`.venv-transcription`, converts Basic Pitch tuples into a versioned typed contract, and writes MIDI.
This isolates TensorFlow's large pinned dependency set and prevents model imports from affecting
ordinary API tests and startup when the optional environment is absent.

## Trade-offs

- One FastAPI process is simpler than a local queue, but long processing will eventually require a small worker boundary.
- SQLite and local files match the single-user product, but do not provide distributed coordination.
- Signature validation is fast and safe for upload acceptance; FFprobe separately proves decodability and extracts typed metadata.
- Cached dependency states avoid repeated subprocess cost, but executable changes require an application restart.
- Synchronous normalization is simple and visible but holds one API request open; a local worker remains deferred until real file durations justify it.
- A fresh transcription process isolates failures but reloads TensorFlow for each project. A persistent local worker is deferred until measured throughput justifies its lifecycle complexity.
- One global tempo and straight sixteenth-note grid provide a testable baseline, but rubato maps, swing, tuplets, compound meter, and inferred downbeats require later evidence and UX.

Related: [pipeline](pipeline.md), [data model](data-model.md), and [roadmap](roadmap.md).
