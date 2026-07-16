# Current Task

## Active milestone

Hands, staves, voices, and pitch spelling are the next milestone. Tempo estimation and readable quantization are complete; see [the reviewed execution plan](TEMPO_QUANTIZATION_PLAN.md).

## Status

The product now reaches a persisted readable-timing boundary: raw Basic Pitch evidence remains unchanged while project-level BPM, simple meter, measure origin, chord groups, and symbolic note timing are stored with diagnostics and provenance. The next stage may consume symbolic timing but must not collapse hand, staff, voice, or spelling uncertainty into hidden guesses.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and strict mypy pass across the backend.
- 62 pytest tests pass using temporary Alembic-migrated SQLite databases.
- `alembic check` reports no schema drift after revision `20260716_0005`.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Three Playwright tests pass against live FastAPI and Next.js servers. The primary audio flow performs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM estimation, and quantization; the video flow verifies media preparation; the rejection flow blocks mismatched contents.

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
- Tempo estimation groups nearby onsets, generates bounded candidates, and rejects sparse, weak, close-runner, or half/double-tempo evidence with an explicit BPM recovery path.
- Quantization supports one global quarter-note BPM, `2/4`, `3/4`, or `4/4`, explicit measure origin, exact internal fractions, and a straight sixteenth-note minimum grid.
- Raw seconds remain unchanged; symbolic fields, chord groups, project timing, current-run ownership, revision, diagnostics, and processor identity are persisted together.
- Matching raw fingerprint/settings/version reuse the current result; changed settings recompute only symbolic state.
- Optimistic concurrency and transactional rollback preserve the previous complete symbolic result.

## Current implementation target

Design and implement the first hand/staff/voice/spelling boundary:

1. Preserve quantized note timing and surface uncertainty rather than forcing hidden assignments.
2. Define typed, independently testable heuristics for hand, staff, voice, and enharmonic spelling.
3. Establish deterministic fixtures for crossings, overlapping voices, chords, repeated notes, and ambiguous middle-register material.
4. Keep MusicXML serialization and rendering downstream of an explicit cleaned-score contract.
5. Add correction-friendly provenance and confidence before presenting assignments as complete.

Do not begin MusicXML or rendering until this interpretation boundary is reviewed and verified.

## Active blockers

None. Engineering review resolved the architecture and full test matrix.
