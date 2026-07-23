# Handoff

## What changed

- 2026-07-23 (T4): extended the Next.js staged workflow through key detection and written pitch.
  Added typed API models, the explicit post-voice action, pending/error recovery, duplicate-submit
  prevention, all 30 standard-signature overrides, clearing back to automatic estimation, distinct
  estimated/unknown/user-chosen key cards, bounded spelling evidence, and truthful cleaned-MIDI /
  MusicXML / rendering deferrals. The existing five-test component suite now exercises the full
  flow including failure/retry, unknown-key recovery, override-after-result, and request payloads.
- 2026-07-23 (T3): added the `pitch_spelling` service/API boundary, typed request/response
  schemas, settings, and available capability. The service validates current voice ownership and
  tri-state evidence, fingerprints the stored float/chord/voice contract plus override/settings,
  persists through `StageRunner`, and distrusts malformed key, note, diagnostic, or MIDI
  round-trip state before reuse. One shared helper clears spelling and key state from genuine
  quantization, interpretation, and voice recomputation; reuse preserves it. Both commit orders
  against all three upstream stages are covered, along with rollback, failed-audit, invalid
  override, override-to-auto transitions, unknown-key success, and resolved automatic-key tests.
- 2026-07-23 (T2): added Alembic revision `20260719_0008` and matching ORM state for one
  project-level key, spelling run ownership/revision, and per-note written spelling. Named
  database checks enumerate exactly four project key states and three note spelling states,
  couple processed key state to `current_spelling_run_id`, and enforce step/alter/octave,
  confidence, and revision bounds. Added 27 migrated-SQLite persistence tests covering all valid
  states, invalid presence combinations, both illegal pointer couplings, and every bound.
- 2026-07-19 (T1): independently re-reviewed the locked key/spelling plan and closed two blocking
  scoring gaps before implementation. Key confidence now uses the full Pearson span; spelling
  confidence uses a fixed 12-unit scale instead of the collapsing observed two-candidate range.
  D4 now requires one shared unique above-margin winner across every plausible key, stores
  worst-case resolved support, and gives contested notes `unknown_key` at 0.0. Implemented
  `app.symbolic.spelling`, a pure deterministic O(24n) engine with canonical key names,
  finite/degenerate evidence gates, validated overrides, contextual spelling, typed unknowns,
  diagnostics, octave-safe MIDI round trips, and no persistence/frontend/dependency coupling.
  Added 32 focused fixtures with 100% module coverage, including non-degenerate C-major/A-minor ambiguity and two
  hand-authored public-domain excerpts.
- 2026-07-19 (planning only, no code): authored and locked `docs/KEY_SPELLING_PLAN.md`, the
  reviewed execution plan for key detection and enharmonic spelling. gstack plan-eng-review
  found two issues (canonical tonic naming was unstated and load-bearing; a stale
  no-music-library claim), and a Codex outside-voice pass produced 15 findings of which five
  were accepted into the plan: context-free D4 agreement with an explicit penalty formula,
  degenerate-evidence gates before correlation, a float + `chord_group` contract replacing the
  false exact-Fraction claim, a pointer-coupled four-state key check, and evaluation honesty
  additions (resolved-key e2e leg, public-domain ground-truth fixtures, fragmentation caveat).
  Strategic reordering and best-guess-unknown dissents were rejected per the settled D2/D4/D5
  decisions. The plan file ends with the GSTACK REVIEW REPORT, verdict ENG CLEARED, no
  unresolved decisions.
- Extracted the shared symbolic-stage transaction mechanics into `app.services.stage_runner`:
  durable RUNNING precommit, success compare-and-swap enforcement, and rollback-following failed
  audit updates. Quantization and interpretation now use it with no contract change.
- Added isolated stage-runner tests for precommit, CAS winner, CAS loser, and failure marking.
- Added `app.symbolic.voices`, a pure deterministic per-staff notation-voice engine. It collapses
  compatible chord notes, builds interval-conflict components, prunes proven third streams with a
  typed structural unknown, two-colors the remainder, orients voice 1 as the upper stream, and
  emits uncalibrated decision scores plus typed crossing/close unknowns.
- Added 13 deterministic voice fixtures covering both staves, monophony, uniform chords,
  sustained-over-moving lines, suspension chains, unequal-duration same-onset notes, capacity,
  unresolved staff, crossing, close separation, input-order invariance, and the voice invariant.
- Added Alembic revision `20260718_0007`, project voice run ownership/revision, nullable note voice,
  bounded decision score, typed ambiguity reason, `voice >= 1`, and the exact enumerated tri-state
  database check. Ten persistence tests prove the valid states and reject every invalid combination
  and bound.
- Added `VoiceService` on the shared stage runner with strict interpretation prerequisites,
  versioned/fingerprinted execution, hardened stored-result validation, rollback-safe failures,
  optimistic concurrency, and synchronous `POST /api/projects/{project_id}/separate-voices`.
- Registered `voice_separation` as an available backend capability. The typed response includes a
  bounded hand/staff/voice preview, per-staff voice 1/2 counts, structural diagnostics,
  provenance, ownership/revision, and reuse state.
- Genuine quantization and interpretation recomputation now cascade voice invalidation with
  SQL-relative revision increments. Four actual-service tests cover both commit orders against
  quantization and interpretation so stale writers lose without dropping an increment.
- Extended the Next.js workflow with `Separate voices`, post-interpretation gating, pending/error
  recovery, duplicate-submit prevention, resolved/unknown totals, per-staff voice counts, and a
  bounded hand/staff/voice evidence table with decision scores and typed reasons.
- Extended the live generated five-tone phrase through voice separation. Playwright verifies the
  final evidence view, seven-step terminal state, truthful downstream copy, and all five notes
  resolved as voice 1 with zero unknowns.
- Added independent passage-level hand and notation-staff interpretation with bounded dynamic programming, competing-path confidence, explicit unknown assignments, typed ambiguity reasons, and deterministic diagnostics.
- Added Alembic revision `20260716_0006` plus project ownership/revision and note assignment/confidence/reason fields with database checks.
- Added a hardened interpretation service with fingerprinted/versioned reuse, persisted configuration/diagnostics, ownership and assignment validation, optimistic concurrency, rollback-safe failed runs, and explicit structured errors.
- Re-quantization now atomically invalidates hand/staff state only on genuine recomputation; reuse preserves the current interpretation.
- Added synchronous `POST /api/projects/{project_id}/interpret` and an available capability state with bounded preview, resolved/unknown counts, provenance, and reuse state.
- Extended the Next.js workflow with `Assign hands and staves`, pending/error recovery, duplicate-submit prevention, uncertainty evidence, and truthful downstream-stage copy.
- Extended the live Basic Pitch flow through hand/staff interpretation and updated configuration, setup, architecture, pipeline, data model, roadmap, research, evaluation, task, plan, handoff, and engineering-log documentation.

## Checks run

- T4: ESLint and TypeScript passed; all five Vitest component tests passed.
- T3: Ruff and formatting passed across the backend; strict mypy passed across 40 application
  sources; all 194 backend tests passed. The 43-test failure-path suite includes nine spelling
  rollback/interleaving tests, and 42 API tests cover the complete spelling contract and cascades.
- T2: Ruff and formatting passed across the backend; strict mypy passed across 38 application
  sources; all 175 tests passed, including 27 focused persistence tests; a fresh SQLite database
  upgraded through `20260719_0008`; `alembic check` found no model drift.
- Backend: Ruff passed; Ruff formatting check passed; strict mypy passed across 38 source files;
  pytest passed 194 tests. The focused spelling engine suite passed all 32 tests with 100% module
  coverage, and all 27 spelling persistence tests passed.
- Database: Alembic upgraded through `20260719_0008`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. The primary flow runs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM quantization, hand/staff interpretation, and notation-voice separation.
- Repository: `git diff --check` passed before delivery review.

## Remaining work

Voice separation is complete and verified through T1-T7 in `docs/VOICE_SEPARATION_PLAN.md`.
The key-detection and enharmonic-spelling plan is now reviewed and locked at
`docs/KEY_SPELLING_PLAN.md`; T1-T4 are complete and the next step is T5 live browser verification,
followed by the T6 consistency sweep. Cleaned MIDI, MusicXML, rendering, correction tools,
broad accuracy benchmarks, and Synthesia work remain deferred in that order.

## Known risks

- Media preparation and transcription are synchronous; long sources keep requests open.
- A fresh worker reloads TensorFlow per transcription and adds cold-start latency.
- Automatic tempo remains one conservative global quarter-note BPM with straight sixteenth resolution.
- Hand/staff interpretation assumes pitch-contiguous splits within each chord and uses deterministic configured centers/costs; real fingering, cross-hand passages, and engraving choices need measured evaluation.
- Unknown assignments are intentional successful outputs, not errors; downstream stages must preserve them until evidence or user correction resolves them.
- The UI does not restore a project after page refresh.
- FastAPI/Starlette emits one upstream warning about future `httpx2` migration.
- npm reports two moderate advisories without a safe non-breaking forced fix.
- No project license has been selected.

## Delivery state

The hand and staff interpretation milestone is shipped to `origin/main` as `9464c01`, and its
reviewed voice plan is shipped as `b20fb17`. Voice delivery slices are T1 `14999b2`, T2 `9c59b24`,
T3 `8066270`, T4 `d6c2c30`, T5 `ee269f7`, and T6 `2a938fc`. T7 completed the shared-context sweep
and final verification as `3aecee2`. The key-spelling plan shipped as `c6e28ba`; this delivery adds
the corrected T1 pure engine and matching shared-context updates.
