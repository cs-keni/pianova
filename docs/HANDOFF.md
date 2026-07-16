# Handoff

## What changed

- Added an isolated `.venv-transcription` dependency boundary pinned to Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1.
- Added dependency probing and truthful transcription capability reporting without importing TensorFlow into FastAPI.
- Added Alembic revision `20260716_0004` for note confidence/pitch-bend evidence and ProcessingRun model/runtime/configuration provenance.
- Added synchronous `POST /api/projects/{project_id}/transcribe` orchestration with normalized-input and 0.05-second duration guards.
- Added a versioned worker contract, raw note-event JSON, raw MIDI, atomic two-artifact finalization, idempotent reuse, and cleanup/retry handling across timeout, inference, malformed-output, rename, and database failures.
- Extended the Next.js workflow with explicit transcription and a bounded raw-note preview that does not imply quantization has started.
- Updated setup, architecture, pipeline, data model, roadmap, research, evaluation, task, handoff, and engineering-log documentation.

## Checks run

- Compatibility: the isolated worker probe passed with the pinned stack, and real Basic Pitch inference emitted a note event and MIDI from generated audio.
- Backend: Ruff passed; strict mypy passed; pytest passed 43 tests.
- Database: Alembic upgraded through `20260716_0004`; `alembic check` found no drift.
- Frontend: ESLint and TypeScript passed; Vitest passed five tests; the Next.js production build passed.
- Browser: Playwright passed three live Chromium tests. The primary flow performed real FFprobe 8.0, FFmpeg 8.0, and Basic Pitch/TensorFlow inference.

## Remaining work

The next milestone is tempo/beat estimation and readable quantization while preserving raw timing. Hands/staves/voices, MusicXML, rendering, correction tools, musical-accuracy benchmarks, and Synthesia work remain deferred in that order.

## Known risks

- Media preparation and transcription are synchronous; long sources keep requests open.
- A fresh worker reloads TensorFlow per transcription. Cold startup is isolated and reliable but adds several seconds.
- The normalized format remains mono 22.05 kHz PCM16; change it only with measured transcription evidence.
- The 0.05-second duration floor prevents a verified Basic Pitch empty-analysis crash but is not a musical suitability threshold.
- FastAPI/Starlette's current TestClient emits one upstream warning about future `httpx2` migration.
- npm reports two moderate advisories; no breaking forced audit fix was applied.
- Windows excluded port ranges can change after Hyper-V/WSL restarts. Port 18080 is configurable for Playwright through `PIANOVA_E2E_API_PORT`.
- No project license has been selected.

## Delivery state

The transcription milestone is implemented, fully verified, and included in the current delivery.
