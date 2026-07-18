# Handoff

## What changed

- Extracted the shared symbolic-stage transaction mechanics into `app.services.stage_runner`:
  durable RUNNING precommit, success compare-and-swap enforcement, and rollback-following failed
  audit updates. Quantization and interpretation now use it with no contract change.
- Added isolated stage-runner tests for precommit, CAS winner, CAS loser, and failure marking.
- Added independent passage-level hand and notation-staff interpretation with bounded dynamic programming, competing-path confidence, explicit unknown assignments, typed ambiguity reasons, and deterministic diagnostics.
- Added Alembic revision `20260716_0006` plus project ownership/revision and note assignment/confidence/reason fields with database checks.
- Added a hardened interpretation service with fingerprinted/versioned reuse, persisted configuration/diagnostics, ownership and assignment validation, optimistic concurrency, rollback-safe failed runs, and explicit structured errors.
- Re-quantization now atomically invalidates hand/staff state only on genuine recomputation; reuse preserves the current interpretation.
- Added synchronous `POST /api/projects/{project_id}/interpret` and an available capability state with bounded preview, resolved/unknown counts, provenance, and reuse state.
- Extended the Next.js workflow with `Assign hands and staves`, pending/error recovery, duplicate-submit prevention, uncertainty evidence, and truthful downstream-stage copy.
- Extended the live Basic Pitch flow through hand/staff interpretation and updated configuration, setup, architecture, pipeline, data model, roadmap, research, evaluation, task, plan, handoff, and engineering-log documentation.

## Checks run

- Backend: Ruff passed; Ruff formatting check passed; strict mypy passed across 35 source files;
  pytest passed 80 tests. The original 77 tests pass unmodified with the new helper tests excluded.
- Database: Alembic upgraded through `20260716_0006`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. The primary flow runs real FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM quantization, and hand/staff interpretation.
- Repository: `git diff --check` passed before delivery review.

## Remaining work

The voice-separation milestone now has a reviewed and approved execution plan in
`docs/VOICE_SEPARATION_PLAN.md` (2026-07-18): typed contract, two-coloring engine, cascade
invalidation semantics, musical fixtures, and verification matrix are defined. T1's stage-runner
extraction is complete. Begin at T2 (pure engine), then continue through T3-T7 in plan order. Key
detection and enharmonic spelling follow voices. Cleaned MIDI, MusicXML,
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
reviewed voice plan is shipped as `b20fb17`. Voice implementation has started: T1 is complete and
T2 is the next reviewable slice.
