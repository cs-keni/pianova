# Current Task

## Active milestone

Hand and staff interpretation is complete. The next ordered milestone is voice separation followed
by key detection and enharmonic spelling over the verified interpreted-note boundary. A reviewed
execution plan must define that slice before implementation begins.

## Status

Pianova now reaches a persisted hand/staff interpretation boundary. Quantized notes receive
independent left/right hand and bass/treble notation-staff assignments, competing-path confidence,
and explicit typed reasons when the evidence remains unknown. Re-quantization invalidates this
downstream state atomically; matching timing and settings reuse the current successful result.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and formatting pass across the backend; strict mypy passes across 34 application source files.
- 77 pytest tests pass using temporary Alembic-migrated SQLite databases.
- Alembic upgrades through revision `20260716_0006`; `alembic check` reports no schema drift.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Three Playwright tests pass against live FastAPI and Next.js servers. The primary audio flow performs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM estimation, quantization, and hand/staff interpretation.

## Delivered interpretation boundary

- Hand and notation staff remain independent facts, including cross-staff possibilities.
- Bounded passage-level dynamic programming evaluates pitch-contiguous chord splits with separate hand and staff passes.
- Per-note confidence compares the best complete competing paths; sub-threshold evidence succeeds as `unknown` with one typed primary reason.
- Processor version, scoring settings, work bounds, quantization ownership, input fingerprint, and diagnostics are persisted on the ProcessingRun.
- Reuse validates run ownership/stage/status, JSON shape, diagnostics, note confidence, and ambiguity invariants before trusting stored state.
- Successful recomputation uses optimistic concurrency and preserves the prior complete result on failure or conflict.
- Genuine re-quantization clears downstream assignments, confidence, reasons, and current-run ownership in the same transaction; quantization reuse preserves them.
- `POST /api/projects/{project_id}/interpret` returns a bounded preview, resolved/unknown counts, work diagnostics, provenance, ownership/revision, and reuse state.
- The frontend exposes an explicit action, pending/error recovery, uncertainty preview, and truthful copy that voices, spelling, cleaned MIDI, and score generation have not started.

## Current implementation target

Shape and review the next interpretation slice before coding:

1. Define the typed voice-separation contract and evaluation evidence.
2. Decide how voices interact with independent hand/staff assignments and explicit unknown states.
3. Define key detection and enharmonic spelling as a subsequent boundary unless review proves they must be coupled.
4. Preserve current raw timing, quantization, assignment provenance, and invalidation semantics.

Do not begin MusicXML or rendering until voice and spelling boundaries are verified.

## Active blockers

None for the delivered hand/staff milestone. The next milestone needs a reviewed plan and measurable
musical fixtures before implementation.
