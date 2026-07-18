# Current Task

## Active milestone

Voice separation is complete. The next ordered milestone is key detection and enharmonic spelling
over the verified notation-voice boundary. The implemented and verified voice plan is
`docs/VOICE_SEPARATION_PLAN.md`; all T1-T7 tasks are complete.

## Status

Pianova's backend now reaches a persisted notation-voice boundary. Quantized notes receive
independent left/right hand and bass/treble notation-staff assignments, competing-path confidence,
and explicit typed reasons when the evidence remains unknown. Interpreted notes then receive
staff-scoped notation voices or typed successful unknowns. Genuine upstream recomputation
atomically invalidates downstream state; matching evidence and settings reuse current results.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and formatting pass across the backend; strict mypy passes across 37 application source files.
- 116 pytest tests pass using temporary Alembic-migrated SQLite databases. The 77 tests that
  predated the helper extraction also pass unmodified when the new helper test file is excluded.
- Alembic upgrades through revision `20260718_0007`; `alembic check` reports no schema drift.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Three Playwright tests pass against live FastAPI and Next.js servers. The primary audio flow performs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM estimation, quantization, hand/staff interpretation, and all-voice-1 notation separation.

## Delivered interpretation boundary

- Hand and notation staff remain independent facts, including cross-staff possibilities.
- Bounded passage-level dynamic programming evaluates pitch-contiguous chord splits with separate hand and staff passes.
- Per-note confidence compares the best complete competing paths; sub-threshold evidence succeeds as `unknown` with one typed primary reason.
- Processor version, scoring settings, work bounds, quantization ownership, input fingerprint, and diagnostics are persisted on the ProcessingRun.
- Reuse validates run ownership/stage/status, JSON shape, diagnostics, note confidence, and ambiguity invariants before trusting stored state.
- Successful recomputation uses optimistic concurrency and preserves the prior complete result on failure or conflict.
- Genuine re-quantization clears downstream assignments, confidence, reasons, and current-run ownership in the same transaction; quantization reuse preserves them.
- `POST /api/projects/{project_id}/interpret` returns a bounded preview, resolved/unknown counts, work diagnostics, provenance, ownership/revision, and reuse state.
- The frontend exposes interpretation and voice actions with pending/error recovery, uncertainty
  evidence, per-staff voice counts, and truthful downstream-stage copy.

## Delivered voice backend boundary

- Voice 1 is the upper staff-scoped notation stream; voice 2 exists only when overlap forces it.
- Unknown staff, third-stream capacity, crossing, and close alternatives succeed with typed reasons.
- Fingerprinted reuse validates ownership, provenance, diagnostics, tri-state fields, voice bounds,
  staff/reason consistency, and the overlap invariant before trusting stored state.
- Re-interpretation and re-quantization clear downstream voice state only on genuine recomputation;
  reuse preserves it.
- SQL-relative cascade increments plus stage compare-and-swap predicates preserve revisions under
  both commit orders against interpretation and quantization.
- `POST /api/projects/{project_id}/separate-voices` returns a bounded preview, per-staff voice
  counts, structural diagnostics, provenance, ownership/revision, and reuse state.

## Completed milestone contract

The voice milestone is closed with these locked decisions:

1. Voice separation is an independent fourth stage with its own endpoint, run ownership, and
   revision (D1).
2. A shared `stage_runner` orchestration helper is extracted first as a zero-behavior-change
   commit gated on the unmodified existing test suite (D2).
3. The engine is deterministic per-staff conflict-graph two-coloring of notation voices under a
   hard forced-only rule; no weighted DP (D3, adopted from the cross-model review).
4. Key detection and enharmonic spelling remain the subsequent boundary; no coupling was proven.

The next implementation target requires a reviewed key-detection and enharmonic-spelling plan.
Do not begin MusicXML or rendering until the spelling boundary is verified.

## Active blockers

None. The full generated-phrase flow reaches the persisted voice boundary with five resolved
voice-1 notes and zero unknowns.
