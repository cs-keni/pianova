# Handoff

## What changed

- Added a pure exact-fraction symbolic-timing module for chord grouping, bounded tempo candidates, deterministic fit scoring, conservative ambiguity gates, and readable onset/duration quantization.
- Added Alembic revision `20260716_0005` for project timing, simple meter, measure origin, chord groups, current-run ownership, revision state, and scalar invariants.
- Added synchronous `POST /api/projects/{project_id}/quantize` with BPM/meter/origin overrides, diagnostics, fingerprinted reuse, changed-setting recomputation, optimistic concurrency, and rollback-safe failure recording.
- Preserved raw Basic Pitch seconds and ML provenance; quantizer identity/settings/diagnostics live in ProcessingRun configuration.
- Extended the Next.js workflow with automatic-tempo recovery, simple-meter/origin controls, fit diagnostics, and a bounded symbolic timing preview.
- Replaced the sustained-tone browser fixture with a five-note 120 BPM phrase that crosses real FFprobe, FFmpeg, Basic Pitch/TensorFlow, tempo estimation, persistence, and UI rendering.
- Updated configuration, setup, architecture, pipeline, data model, roadmap, research, evaluation, task, handoff, and engineering-log documentation.

## Checks run

- Backend: Ruff passed; strict mypy passed across 32 source files; pytest passed 62 tests.
- Database: Alembic upgraded through `20260716_0005`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. The primary flow estimated the generated phrase within 119.5-120.5 BPM and produced symbolic timing.

## Remaining work

The next milestone is hands/staves/voices and pitch spelling over the verified quantized-note boundary. MusicXML, rendering, correction tools, broad musical-accuracy benchmarks, and Synthesia work remain deferred in that order.

## Known risks

- Media preparation and transcription are synchronous; long sources keep requests open.
- A fresh worker reloads TensorFlow per transcription. Cold startup is isolated and reliable but adds several seconds.
- The normalized format remains mono 22.05 kHz PCM16; change it only with measured transcription evidence.
- The 0.05-second duration floor prevents a verified Basic Pitch empty-analysis crash but is not a musical suitability threshold.
- Automatic tempo is deliberately conservative and may require a BPM override for sparse, rubato, swung, compound-meter, or half/double-tempo material.
- Current quantization is one global tempo with straight sixteenth resolution; it does not infer downbeats, tempo maps, swing, tuplets, or compound-meter pulse.
- The UI does not restore a project after page refresh; current timing remains persisted and accessible through the API/database.
- FastAPI/Starlette's current TestClient emits one upstream warning about future `httpx2` migration.
- npm reports two moderate advisories; no breaking forced audit fix was applied.
- Windows excluded port ranges can change after Hyper-V/WSL restarts. Port 18080 is configurable for Playwright through `PIANOVA_E2E_API_PORT`.
- No project license has been selected.

## Delivery state

The tempo and readable-quantization milestone is implemented, fully verified, and included in the current delivery.
