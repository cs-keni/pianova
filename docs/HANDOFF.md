# Handoff

## What changed

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

- Backend: Ruff passed; Ruff formatting check passed; strict mypy passed across 37 source files;
  pytest passed 116 tests. The original 77 tests pass unmodified with the new helper tests excluded.
- Database: Alembic upgraded through `20260718_0007`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. The primary flow runs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM quantization, hand/staff interpretation, and notation-voice separation.
- Repository: `git diff --check` passed before delivery review.

## Remaining work

Voice separation is complete and verified through T1-T7 in `docs/VOICE_SEPARATION_PLAN.md`.
The next ordered milestone is a reviewed key-detection and enharmonic-spelling boundary over the
persisted voices. Cleaned MIDI, MusicXML,
rendering, correction tools, broad accuracy benchmarks, and Synthesia work remain deferred in
that order.

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
T3 `8066270`, T4 `d6c2c30`, T5 `ee269f7`, and T6 `2a938fc`. T7 completes the shared-context sweep
and final verification in this delivery.
