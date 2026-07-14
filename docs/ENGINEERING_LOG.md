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
