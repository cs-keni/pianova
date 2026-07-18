# Current Task

## Active milestone

Hand and staff interpretation is complete. The next ordered milestone is voice separation followed
by key detection and enharmonic spelling over the verified interpreted-note boundary. The reviewed
execution plan for the voice slice is `docs/VOICE_SEPARATION_PLAN.md` (approved 2026-07-18);
implementation is underway. T1's shared stage-runner extraction is complete; T2's pure voice
engine is the current target.

## Status

Pianova now reaches a persisted hand/staff interpretation boundary. Quantized notes receive
independent left/right hand and bass/treble notation-staff assignments, competing-path confidence,
and explicit typed reasons when the evidence remains unknown. Re-quantization invalidates this
downstream state atomically; matching timing and settings reuse the current successful result.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and formatting pass across the backend; strict mypy passes across 35 application source files.
- 80 pytest tests pass using temporary Alembic-migrated SQLite databases. The 77 tests that
  predated the helper extraction also pass unmodified when the new helper test file is excluded.
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

Implement T2 in `docs/VOICE_SEPARATION_PLAN.md`: the pure deterministic voice engine and its
fixture suite. T3-T7 then follow sequentially. Locked review decisions:

1. Voice separation is an independent fourth stage with its own endpoint, run ownership, and
   revision (D1).
2. A shared `stage_runner` orchestration helper is extracted first as a zero-behavior-change
   commit gated on the unmodified existing test suite (D2).
3. The engine is deterministic per-staff conflict-graph two-coloring of notation voices under a
   hard forced-only rule; no weighted DP (D3, adopted from the cross-model review).
4. Key detection and enharmonic spelling remain the subsequent boundary; no coupling was proven.

Do not begin MusicXML or rendering until voice and spelling boundaries are verified.

## Active blockers

None. The shared stage runner is proven against the unchanged 77-test regression baseline; the
pure voice engine can proceed without a service-layer dependency.
