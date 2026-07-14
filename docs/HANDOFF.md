# Handoff

## What changed

- Recovered and checkpointed the previously untracked scaffold.
- Resolved toolchains with Windows Python 3.11 and native Windows npm.
- Implemented typed settings, logging, structured errors, cached executable probes, and truthful capability states.
- Added SQLAlchemy Project, Artifact, NoteEvent, and ProcessingRun models plus the initial Alembic migration.
- Added health, config, dependencies, project-creation, and secure-upload APIs.
- Implemented raw-request and streamed byte limits, extension/signature checks, detected MIME storage, generated project-local filenames, one-source invariants, atomic finalization, and compensation cleanup.
- Replaced the generated Next.js page with a responsive Pianova status/create/upload workflow and a typed API client.
- Added backend, component, and live Playwright tests.
- Added the root run guide and the six architecture/pipeline/data/roadmap/research/evaluation documents required by `first.md`.

## Checks run

- Backend: Ruff passed; strict mypy passed across 24 source files; pytest passed 24 tests; `alembic check` found no drift.
- Frontend: ESLint passed; TypeScript passed; Vitest passed four tests; the Next.js production build passed.
- Browser: Playwright passed two live Chromium tests against migrated FastAPI and Next.js servers, covering accepted and rejected uploads.
- Documentation links and staged diff are checked before delivery.

## Remaining work

The next milestone is FFprobe inspection and FFmpeg normalized-WAV generation. Basic Pitch, MIDI, symbolic reconstruction, MusicXML, rendering, correction tools, evaluation benchmarks, and Synthesia work remain intentionally deferred in that order.

## Known risks

- FastAPI/Starlette's current TestClient emits one upstream warning about a future `httpx2` migration.
- npm reports two moderate advisories; `npm audit fix --force` was not run because it requests breaking upgrades.
- FFmpeg is available in WSL but may not be on the native Windows backend `PATH`; configure or install it in the runtime used for the next milestone.
- Basic Pitch 0.4.0 and its older transitive ML stack still require an isolated compatibility test before integration.
- No project license has been selected.

## Delivery state

The reviewed milestone implementation is verified on `main`; two earlier WIP commits preserve its scaffold and backend checkpoints.
