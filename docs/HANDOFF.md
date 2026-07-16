# Handoff

## What changed

- Added Alembic revision `20260716_0003` with project duration/container/bit-rate fields and typed `media_streams`.
- Added a synchronous `POST /api/projects/{project_id}/process-media` boundary.
- Implemented bounded FFprobe JSON inspection, audio/duration validation, and typed stream persistence.
- Implemented mono 22.05 kHz PCM WAV generation with safe FFmpeg arguments, temporary output, atomic finalization, cleanup, ProcessingRun auditing, and idempotent repeat calls.
- Changed media normalization capability reporting from `not_implemented` to dependency-backed `available`/`unavailable`.
- Extended the Next.js workflow to explicitly process uploaded media and display container, duration, audio codec/channels/sample rate, and video dimensions.
- Moved the local/test API default to port 18080 because Windows Hyper-V/WSL currently reserves the range containing port 8000.
- Updated root, backend, architecture, pipeline, data-model, roadmap, research, evaluation, task, handoff, and engineering-log documentation.

## Checks run

- Backend: Ruff passed; strict mypy passed across 25 source files; pytest passed 32 tests.
- Database: Alembic upgraded through `20260716_0003`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. Native Windows FFprobe 8.0 and FFmpeg 8.0 inspected and normalized real generated WAV and MP4 fixtures.

## Remaining work

The next milestone is Basic Pitch compatibility, typed raw note-event transcription, and raw MIDI generation. Quantization, hands/staves/voices, MusicXML, rendering, correction tools, evaluation benchmarks, and Synthesia work remain deferred in that order.

## Known risks

- Media processing is synchronous; long sources may eventually justify a local worker boundary.
- The normalized format is intentionally fixed at mono 22.05 kHz PCM16 and should be re-evaluated only with measured transcription evidence.
- FastAPI/Starlette's current TestClient emits one upstream warning about future `httpx2` migration.
- npm reports two moderate advisories; no breaking forced audit fix was applied.
- Basic Pitch 0.4.0 and its older transitive ML stack still require an isolated Windows Python 3.11 compatibility test.
- Windows excluded port ranges can change after Hyper-V/WSL restarts. Port 18080 is configurable for Playwright through `PIANOVA_E2E_API_PORT`.
- No project license has been selected.

## Delivery state

The media milestone is implemented and fully verified on `main`.
