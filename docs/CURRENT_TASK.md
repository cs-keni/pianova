# Current Task

## Active milestone

The locked key-detection and enharmonic-spelling milestone is complete through T1-T6. Its
execution and absorbed independent review are recorded in `docs/KEY_SPELLING_PLAN.md`; the final
verdict is MILESTONE COMPLETE with no unresolved decisions. The next ordered product boundary is
cleaned MIDI, but no cleaned-MIDI planning or implementation has started. Editable MusicXML
follows it. The prior voice plan
`docs/VOICE_SEPARATION_PLAN.md` remains complete through T1-T7.

## Status

Pianova's backend now reaches a persisted notation-voice boundary. Quantized notes receive
independent left/right hand and bass/treble notation-staff assignments, competing-path confidence,
and explicit typed reasons when the evidence remains unknown. Interpreted notes then receive
staff-scoped notation voices or typed successful unknowns. Genuine upstream recomputation
atomically invalidates downstream state; matching evidence and settings reuse current results.
The pure tonal engine can estimate one global key or return a typed successful unknown, then
spell notes deterministically with key, chord-group, and melodic context. Its exact four-state
project key and tri-state note spelling contracts now persist through Alembic. The service/API
boundary is available with hardened reuse, override recovery, and concurrency-safe upstream
invalidation. The browser UI exposes the same contract with an automatic/override selector, typed
key card, bounded spelling evidence, and truthful downstream deferrals. Both its
insufficient-evidence recovery path and resolved automatic-key path are live-verified.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- The isolated worker resolves Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Ruff and formatting pass across the backend; strict mypy passes across 40 application source files.
- 194 pytest tests pass using temporary Alembic-migrated SQLite databases. The 77 tests that
  predated the helper extraction also pass unmodified when the new helper test file is excluded.
- Alembic upgrades through revision `20260719_0008`; `alembic check` reports no schema drift.
- Twenty-seven focused persistence tests prove every valid key/spelling state, invalid
  presence combination, pointer coupling, numeric bound, and the non-negative revision.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Four Playwright tests pass against live FastAPI and Next.js servers. The primary five-note
  flow performs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM estimation,
  quantization, hand/staff interpretation, notation-voice separation, typed insufficient-key
  recovery, and explicit C-major respelling. A separate twelve-note flow proves automatic
  C-major estimation and zero-unknown spelling over real transcription output.

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

The reviewed key-detection and enharmonic-spelling plan now exists at
`docs/KEY_SPELLING_PLAN.md`. Its load-bearing review outcomes: one combined `pitch_spelling`
stage, global key only with canonical tonic naming (fewer accidentals; the six-accidental tie
breaks flat), context-free D4 agreement under unknown keys, a float + `chord_group` engine
contract (symbolic beats persist as floats, never Fractions), degenerate-evidence gates before
correlation, and a pointer-coupled four-state key check. The prerequisite for cleaned MIDI is now
satisfied; cleaned MIDI, MusicXML, and rendering remain unstarted.

## Delivered pure key/spelling engine (T1)

- Duration-weighted global key correlation covers all 24 pitch-class major/minor profiles, with
  canonical tonic naming, note/distinct-class/near-uniform gates, explicit overrides, and typed
  successful unknowns.
- Stored float timing remains the contract; positive `chord_group` is the only simultaneity fact.
- Resolved-key spelling combines line-of-fifths proximity, chord-third consistency, and
  chromatic-neighbor stream context in one deterministic total order.
- Fixed-scale decision margins preserve meaningful close alternatives; D4 requires the same unique
  above-margin winner across every plausible key and stores worst-case support.
- Thirty-two focused fixtures with 100% module coverage exercise scoring attainability, every canonical enharmonic key pair,
  degenerate evidence, D4 agreement, public-domain ground truth, octave edges, MIDI round trips,
  and input-order invariance.

## Delivered key/spelling persistence (T2)

- Project key state has exactly four database-valid forms: unprocessed, estimated,
  estimated-unknown, and override. Every processed form requires an owning spelling run, and an
  owning spelling run cannot coexist with an unprocessed key.
- Note spellings have exactly three database-valid forms: unprocessed, resolved, and unknown.
- Written step, alter, octave, confidence, and revision bounds are enforced independently of the
  service layer.
- Migration `20260719_0008` upgrades cleanly from the full historical chain and matches ORM
  metadata with no drift.

## Delivered key/spelling backend boundary (T3)

- `POST /api/projects/{project_id}/spell` estimates one global key or adopts a validated
  standard-signature override, persists all spellings, and returns a bounded typed preview,
  diagnostics, provenance, ownership/revision, and reuse state.
- Matching results are reused only after validating run ownership, complete configuration,
  project key state, note tri-state and MIDI round trips, diagnostics, and all counts.
- One shared invalidation helper clears note spellings and project key state from genuine
  quantization, interpretation, or voice recomputation. Reuse preserves spelling.
- Both commit orders against all three upstream stages are tested. SQL-relative increments and
  compare-and-swap predicates preserve every revision; the stale request fails cleanly.
- Unknown key and spelling evidence remains a successful typed result. Invalid overrides are 422;
  missing/stale voices and conflicts are structured 409s.

## Delivered key/spelling frontend boundary (T4)

- `Detect key & spell notes` appears only after successful voice separation and prevents duplicate
  submission while pending.
- The 30 standard major/minor signatures are available as an optional override. Blank requests
  estimate; selecting a key respells; clearing it returns to estimation.
- Estimated, estimated-unknown, and user-chosen keys are labeled distinctly. Unknown-key results
  emphasize the recovery selector instead of presenting a guessed key.
- The result separates written pitch, uncalibrated score, and typed reason, and explicitly states
  that cleaned MIDI, MusicXML, and rendering have not started.
- The component suite covers failure/retry, pending state, unknown recovery, override after a
  result, clearing back to automatic, and request payloads.

## Delivered live key/spelling boundary (T5)

- The five-note 120 BPM fixture reaches the eighth workflow step, reports `insufficient_notes`,
  preserves the two D/G stable spellings, exposes three unknowns, and recovers all five names
  after an explicit C-major override.
- A twelve-note C-major fixture independently traverses the real worker and automatically
  estimates C major with every written pitch resolved.
- The production build and four live Playwright flows pass.

## Delivered milestone consistency boundary (T6)

- Configuration, both READMEs, architecture, pipeline, data model, research, evaluation, roadmap,
  current task, handoff, engineering log, and the locked plan were checked against the delivered
  implementation.
- The isolated worker's `pretty-midi` dependency is intentionally retained at 0.2.11: Basic Pitch
  imports it and returns the `PrettyMIDI` object used for raw-MIDI serialization even though the
  Pianova API has no direct import.
- Key-aware spelling is now marked complete; the next ordered boundary from `first.md` is cleaned
  MIDI, followed by MusicXML.

## Active blockers

None. Future work should begin by planning the cleaned-MIDI boundary rather than treating cleaned
MIDI, MusicXML, or rendering as already implemented.
