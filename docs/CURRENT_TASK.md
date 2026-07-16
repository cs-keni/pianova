# Current Task

## Active milestone

The Basic Pitch raw-transcription and raw-MIDI milestone is implemented.

## Status

Pianova can now create a project, securely store a supported source, inspect and normalize it, and explicitly run Basic Pitch in an isolated Python environment. The backend persists raw performed note timing, confidence and pitch-bend evidence, model/configuration provenance, versioned note-event JSON, and raw MIDI. The Next.js interface shows a bounded note preview while truthfully leaving quantization and score reconstruction unstarted.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and strict mypy pass across the backend.
- 43 pytest tests pass using temporary Alembic-migrated SQLite databases.
- `alembic check` reports no schema drift after revision `20260716_0004`.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Three Playwright tests pass against live FastAPI and Next.js servers. The primary audio flow performs real FFprobe, FFmpeg, and Basic Pitch/TensorFlow work; the video flow verifies media preparation; the rejection flow blocks mismatched contents.

## Approved decisions preserved

- FFprobe output is parsed into typed project fields and `MediaStream` rows rather than stored as an opaque JSON blob.
- Normalized audio is mono, 22.05 kHz, 16-bit PCM WAV. No loudness filter is applied, preserving dynamics for later velocity work.
- Media processing is explicit and synchronous with separate bounded FFprobe/FFmpeg timeouts.
- Generated output uses a hidden temporary file, validates non-empty output, atomically finalizes, then commits metadata and the Artifact.
- Failed attempts remove partial/finalized output, record a failed ProcessingRun when possible, and remain retryable.
- Successful repeat requests return the existing normalized Artifact instead of duplicating work.
- Basic Pitch runs only in `.venv-transcription`; the ordinary FastAPI process never imports TensorFlow.
- Missing transcription dependencies make only that capability unavailable.
- The worker returns versioned JSON plus MIDI, and the API validates provenance before persistence.
- Transcription requires normalized input, rejects duration below 0.05 seconds, has a bounded timeout, cleans all partial output on failure, and remains retryable.
- Successful repeat requests reuse both raw transcription artifacts.

## Next milestone

Implement tempo estimation and readable quantization:

1. Define typed tempo, beat-grid, meter, and quantized-note contracts without altering raw transcription evidence.
2. Establish deterministic synthetic fixtures and measurable rhythm/readability expectations.
3. Prefer simple readable durations, chord grouping, and limited rests/ties over preserving every expressive deviation.
4. Persist symbolic onset/duration separately from raw timing and retain algorithm/configuration provenance.
5. Add ambiguity, invalid-grid, cleanup, retry, and regression coverage before exposing the stage in the UI.

Do not begin hand assignment, MusicXML, or score rendering until the quantization boundary is measured and verified.

## Active blockers

None for the completed transcription milestone. The next milestone needs an approved quantization approach and evaluation fixtures before implementation.
