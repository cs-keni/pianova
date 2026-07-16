# Engineering Log

## 2026-07-11 — Initial environment and architecture review

- The default Python is 3.13.12. Basic Pitch 0.4.0 officially supports Python through 3.11, so Pianova will target Python 3.11 and keep ML dependencies optional.
- Node 20.19.5 satisfies the current Next.js minimum of Node 20.9.
- FFmpeg and FFprobe 6.1.1 are available. MuseScore is not detected.
- Approved SQLAlchemy 2.0 models separate from Pydantic API schemas, with Alembic migrations from the first database revision.
- Approved upload ordering: stream to a project temporary file, enforce size during streaming, validate extension and media signature, atomically finalize, then commit metadata. Compensate filesystem changes if the database commit fails.
- Capability truthfulness is a backend-owned typed contract. Unfinished pipeline stages must report `not_implemented`, never simulated success.
- The initial user-visible vertical slice requires Playwright coverage in addition to backend and frontend unit/integration tests.

## 2026-07-11 — WSL frontend installation blocker

- `create-next-app` generated the source tree but its dependency installation did not finish.
- Subsequent `npm install` attempts failed with `EACCES` renaming `node_modules/typescript`, then `ENOTEMPTY` removing Next.js directories, and after a clean `node_modules` deletion, `EACCES` renaming `node_modules/next`.
- `node_modules` and affected packages were owned by `keni:keni` with mode `777`; no npm, Node, or create-next-app process remained. A direct rename succeeded after npm exited.
- Root cause: package-directory rename/cleanup races on the Windows-mounted `/mnt/c` filesystem, not Unix ownership or one corrupt package.
- Next attempt should use native Windows npm for this Windows-hosted repository, or a repository clone on WSL's ext4 filesystem. Do not keep retrying Linux npm against the same partial tree.

## 2026-07-14 — Context recovery and frontend state correction

- A frontend lockfile and dependency tree were produced at 12:30 on July 11, after the 12:17 handoff claimed they were absent. The shared task documents were corrected before implementation resumed.
- `npm ls --depth=0` succeeds but reports extraneous `@emnapi/runtime`.
- `npx tsc --noEmit --incremental false` passes. A bounded `npx eslint src --no-cache` run timed out after 45 seconds without reporting a code error, consistent with the existing `/mnt/c` tooling-performance concern.

## 2026-07-14 — Native Windows toolchain and backend foundation

- The Windows Python launcher already provided Python 3.11. A project `.venv` was created and the ordinary `backend[dev]` dependencies installed successfully; the optional Basic Pitch group remains deferred.
- Native Windows `npm ci` completed successfully against the repository lockfile. This is the supported dependency-install path while the checkout remains under `/mnt/c`.
- Implemented the initial FastAPI/SQLite vertical-slice backend with Alembic-owned schema creation, SQLAlchemy models, structured errors, cached dependency states, explicit unfinished capability states, project creation, and secure upload storage.
- Backend verification passed: Ruff, strict mypy across 22 source files, and 13 pytest tests using temporary migrated SQLite databases. FastAPI's test client emits one upstream Starlette deprecation warning about future `httpx2` migration.

## 2026-07-14 — Connected frontend and vertical-slice completion

- Replaced the starter interface with a typed Next.js health, capability, project, and upload workflow. The page reports backend connection errors and never implies that transcription begins after upload.
- The first Playwright run exposed a real CORS gap: the backend allowed `localhost:3000` but not the equivalent `127.0.0.1:3000` origin used by the test server. Both local origins are now defaults and covered by pytest.
- Final verification passed: Ruff; strict mypy across 24 backend source files; 24 pytest tests; Alembic upgrade and drift check; ESLint; TypeScript; four Vitest tests; Next.js production build; and two live Chromium upload flows.
- Native npm reports two moderate advisories. No forced audit fix was applied because npm labels it as a breaking change.
- Pre-landing review found that the broad `models/` ignore rule also matched `backend/app/models/`, which would have broken a fresh clone despite local tests passing. The rule is now root-scoped as `/models/`; always audit ignored source paths before delivery.
- The same review corrected capability truthfulness, enabled SQLite foreign-key cascades, enforced a one-source database invariant, stored detected rather than claimed MIME, added raw multipart limits and generic structured errors, and hardened filesystem/database compensation paths.
- Review-driven coverage raised the baseline to 24 backend tests and two live Playwright flows. The browser launcher is now platform-aware, and frontend environment overrides live in `frontend/.env.local` where Next.js loads them.
- The one-source invariant uses follow-up Alembic revision `20260714_0002` instead of rewriting the already-applied initial migration, preserving upgrades for existing local databases.

## 2026-07-16 — FFprobe inspection and FFmpeg normalization

- Native Windows Python 3.11.9 sees FFprobe and FFmpeg 8.0 from the WinGet Gyan build, so the media milestone uses the same runtime that launches FastAPI.
- Alembic revision `20260716_0003` adds project duration/container/bit-rate fields and a typed `media_streams` table. Stream metadata is queryable and preserves audio, video, and unknown stream evidence rather than storing opaque probe JSON.
- `POST /api/projects/{project_id}/process-media` runs bounded FFprobe inspection, requires an audio stream and positive duration, and generates mono 22.05 kHz PCM16 WAV without loudness filtering.
- Normalization writes a hidden temporary WAV, checks non-empty output, atomically finalizes, then commits metadata, the normalized Artifact, and the successful ProcessingRun. Failure paths remove output, record failure when possible, and remain retryable; successful repeats reuse the existing artifact.
- The frontend now makes processing explicit and displays duration, container, audio codec/channels/sample rate, and optional video dimensions while continuing to state that transcription has not started.
- Windows rejected Uvicorn port 8000 with permission error 13 even though no process was listening. `netsh interface ipv4 show excludedportrange protocol=tcp` showed Hyper-V/WSL had reserved `7919-8818`. Local and Playwright defaults now use port 18080, with `PIANOVA_E2E_API_PORT` available for test overrides.
- Verification baseline is now 32 backend tests, five component tests, a clean production build, and three live Chromium flows including real WAV and MP4 FFprobe/FFmpeg processing.
