# Pianova Initial Scaffold Implementation Plan

Status: initial scaffold complete and verified as of 2026-07-14. The follow-on FFprobe inspection and FFmpeg normalized-WAV milestone was completed on 2026-07-16; see `docs/CURRENT_TASK.md` for the active boundary.

## Implementation progress

```text
Checkpoint 1  COMPLETE
  [x] Repository configuration and ignore rules
  [x] Python 3.11 backend dependency manifest
  [x] Workspace and sample directory boundaries
  [x] Root setup/architecture README
  [x] Next.js TypeScript source scaffold
  [x] Frontend lockfile and dependency tree produced (clean-install/build verification pending)
  [x] Python 3.11 virtual environment
  [x] Backend dependency verification and frontend clean dependency install

Checkpoint 2  COMPLETE
  [x] Settings, structured errors, and capability/dependency registry
  [x] SQLAlchemy models and initial Alembic migration
  [x] Project creation and secure upload APIs
  [x] Ruff, strict mypy, and 24 migrated-database pytest tests

Checkpoint 3  COMPLETE
  [x] Typed frontend API client and responsive health/create/upload interface
  [x] Explicit loading, error, unavailable, and not-implemented states
  [x] Four Vitest component tests
  [x] ESLint, TypeScript, and optimized production build
  [x] Live Playwright valid-WAV acceptance and mismatched-content rejection
```

Active blockers and recovery commands are maintained in `docs/CURRENT_TASK.md`; investigation evidence is in `docs/ENGINEERING_LOG.md`.

## Goal

Deliver every item in the `first.md` "First task" as a stable local scaffold. This milestone proves that the frontend, API, SQLite database, and project-scoped file storage work together. It does not claim transcription, media inspection, audio normalization, MIDI, MusicXML, or score rendering are implemented.

## Environment and compatibility baseline

- Python: 3.11. Basic Pitch 0.4.0 officially supports through Python 3.11; the installed Python 3.13.12 is not the project runtime.
- Node.js: 20 LTS. The installed Node.js 20.19.5 satisfies the current Next.js minimum of 20.9.
- FFmpeg and FFprobe: native Windows version 8.0 is verified for media inspection and normalization. WSL also has version 6.1.1.
- MuseScore: not detected. MusicXML must remain downloadable when implemented; PDF rendering will be an optional capability.
- Basic Pitch: optional backend dependency group. Do not load or install the ML stack for ordinary scaffold development.

The backend will keep a `PianoTranscriber`-style boundary when transcription begins. A separate Python process is deferred unless real dependency conflicts justify it.

## Approved architecture

- FastAPI with typed Pydantic request/response schemas.
- SQLAlchemy 2.0 persistence models kept separate from API schemas.
- Alembic owns schema creation and migrations, including test databases.
- SQLite uses a project-local configurable URL.
- Local artifacts live under generated UUID project directories.
- A typed capability registry is the sole backend source of truth for available, unavailable, and not-implemented features.
- API failures use one structured error envelope with centralized domain-exception mapping.
- Dependency executables are probed once at startup with safe argument arrays and bounded timeouts, then exposed as a cached snapshot.
- Uploads stream to a project-scoped temporary file, enforce the configured byte limit while streaming, validate extension and detected media signature, atomically move to the final generated path, and only then commit upload metadata. Failures remove temporary files and leave the project in an explicit recoverable state.

## Data flow

```text
Browser
  |
  +-- GET /api/health ----------------------> cached health/capability snapshot
  |
  +-- POST /api/projects -------------------> validate request
  |                                             |
  |                                             +--> SQLAlchemy transaction --> SQLite
  |
  +-- POST /api/projects/{id}/upload -------> find project
                                                |
                                                +--> stream + byte limit
                                                +--> extension/signature checks
                                                +--> temporary project file
                                                +--> atomic rename
                                                +--> metadata transaction
                                                +--> structured success/error
```

## Milestone checkpoints

### Checkpoint 1: repository and documented environment

1. Create the monorepo directories, `.gitignore`, `.env.example`, workspace placeholders, and shared context documents.
2. Add the root README with exact Python 3.11, Node 20, FFmpeg, optional MuseScore, backend, frontend, migration, test, and verification commands.
3. Record dependency choices and compatibility risks without installing or claiming unfinished ML capabilities.

Verification: review documented commands against the actual repository layout and configuration names.

### Checkpoint 2: backend, database, and secure storage

1. Scaffold the FastAPI application, typed settings, logging, capability registry, dependency snapshot, and structured errors.
2. Add SQLAlchemy models for Project, NoteEvent, Artifact, and ProcessingRun with explicit enums and raw-versus-symbolic note timing fields.
3. Add Alembic and the initial migration.
4. Implement health/config/dependency endpoints and project creation.
5. Implement streamed, size-limited, signature-checked, atomic uploads.
6. Add unit and API integration tests using temporary migrated SQLite databases and temporary workspaces.

Verification: formatting, type checks, migration upgrade/check, and pytest with success and error branches.

### Checkpoint 3: frontend and vertical-slice verification

1. Scaffold Next.js with TypeScript and a small API client.
2. Build the desktop-first Pianova page with health/dependency state, project creation, upload controls, clear loading/error states, and explicit unfinished-capability messaging.
3. Add frontend component tests.
4. Add Playwright tests for backend health display, project creation, valid upload, and rejected upload.
5. Run backend and frontend checks, repair failures, and update README and shared context.

Verification: lint, type check, unit tests, production build, and Playwright against real local servers.

## Failure matrix

| Codepath | Realistic failure | Planned test | Handling | User-visible result |
|---|---|---|---|---|
| Health/config | Dependency executable missing or hangs | Startup probe missing/timeout cases | Timeout and unavailable capability | Clear unavailable status |
| Project creation | Invalid title | API validation test | Structured 422 error | Field-level message |
| Project creation | SQLite commit failure | Transaction failure test | Rollback and structured 500 error | Recoverable error message |
| Upload lookup | Project ID missing | API integration test | Structured 404 error | Project-not-found message |
| Upload streaming | Limit exceeded mid-stream | Boundary and over-limit tests | Abort, close, delete temporary file | File-too-large message |
| Upload validation | Extension, MIME claim, and signature disagree | Parameterized validation tests | Reject before finalization | Unsupported/invalid media message |
| Upload finalization | Atomic rename fails | Storage failure test | Cleanup and unchanged metadata | Upload-failed message |
| Upload metadata | Database commit fails after rename | Compensation test | Remove finalized file and rollback | Upload-failed message |
| Frontend health | Backend unreachable or slow | Component and Playwright tests | Loading timeout and retry state | Connection guidance |
| Frontend forms | Duplicate submission | Component/browser test | Disable while pending | One request and progress state |

No planned path has a silent failure without both handling and a test.

## Test plan

```text
pytest unit
  +-- settings and capability states
  +-- dependency probe success/missing/timeout
  +-- filename and media-signature validation
  +-- streaming byte limits and cleanup
  +-- structured exception mapping

pytest integration (temporary SQLite + Alembic)
  +-- health/config/dependencies
  +-- project create validation/persistence/failure
  +-- upload success, missing project, invalid media, oversize, compensation

frontend unit
  +-- health loading/success/unavailable/error
  +-- create-project form validation/success/error/double-submit
  +-- upload validation/progress/success/error

Playwright
  +-- homepage reaches real backend
  +-- create project persists through real API
  +-- upload a tiny synthetic WAV fixture
  +-- reject a disguised or unsupported fixture clearly
```

## Initial repository structure

```text
pianova/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── database/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── tests/
│   └── package.json
├── docs/
├── samples/
├── workspace/projects/
├── .env.example
├── .gitignore
└── README.md
```

## What already exists

- `first.md` is the product, architecture, scope-order, and milestone source of truth. This plan narrows it into executable checkpoints rather than duplicating the long-term roadmap.
- `AGENTS.md` defines delivery and shared-context rules. The implementation follows those rules.
- Git is initialized on `main` and tracks `origin/main`.
- Windows Python 3.11 and native Windows Node/npm are the verified runtime for this `/mnt/c` checkout. Native Windows FFmpeg/FFprobe 8.0 now process media; WSL also has FFmpeg/FFprobe 6.1.1. MuseScore is not currently detected.
- The scaffold, migrated backend, connected frontend, secure-upload flow, tests, and documentation described by this plan are implemented. Media inspection/normalization was delivered as the next vertical slice.

## NOT in scope

- FFprobe media inspection and FFmpeg normalization were outside this original scaffold plan and are now implemented in the follow-on milestone.
- Basic Pitch installation and real transcription: deferred until the upload/media foundation is verified under Python 3.11.
- MIDI, MusicXML, MuseScore rendering, note editing, and piano-roll UI: later ordered milestones.
- Project listing, editing, deletion, and reprocessing beyond what the initial page needs: later project-management work.
- Background workers or queues: synchronous request handling is sufficient for this scaffold; long processing will get a simple local worker only when needed.
- Synthesia computer vision and audio-video fusion: deferred until the audio pipeline is stable.
- Authentication, cloud deployment, payments, mobile applications, and distributed infrastructure: explicitly outside the local-first MVP.
- CI/CD and artifact publishing: this milestone creates a source-run local application, not a distributable binary or hosted service.

## Parallelization

The work has three lanes after shared contracts are established:

| Lane | Modules | Depends on |
|---|---|---|
| A: backend foundation and API | `backend/app`, `backend/alembic`, `backend/tests` | Approved plan |
| B: frontend scaffold and components | `frontend/app`, `frontend/components`, `frontend/lib`, `frontend/tests` | API response contracts |
| C: documentation and shared context | root docs, `docs/`, configuration examples | Final commands and behavior |
| D: browser verification | `frontend/e2e` | A and B |

Execution order: begin A and the non-command portions of C; begin B after API contracts exist; finish A and B; run D; then finalize C. Because this repository is greenfield and shared manifests/contracts change early, implementation will remain in one worktree to avoid coordination overhead.

## Implementation tasks

- [x] **T1** — Environment and dependency boundaries.
- [x] **T2** — SQLAlchemy models, Alembic migration, and migrated SQLite test fixtures.
- [x] **T3** — Streamed, validated, atomic uploads with cleanup tests.
- [x] **T4** — Capabilities, cached dependency probes, structured errors, health, config, dependencies, and project APIs.
- [x] **T5** — Frontend health, project creation, upload, and truthful capability states.
- [x] **T6** — Backend, component, production-build, and Playwright verification.
- [x] **T7** — Setup, architecture, pipeline, data model, roadmap, research, evaluation, capability, and limitation documentation.

## Inline diagram guidance

Add an ASCII state-transition comment beside the Project processing-status enum only if its legal transitions are enforced in code during this milestone. Add a short upload finalization/compensation diagram beside the storage service because its filesystem/database ordering is non-obvious. Do not add diagrams to trivial route handlers or schema classes.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---:|---|---|
| CEO Review | `/plan-ceo-review` | Scope and strategy | 0 | Not run | Product direction inherited from `first.md` |
| Outside Voice | `/claude` | Independent second opinion | 1 | Unavailable | Claude CLI returned no substantive review after one retry |
| Eng Review | `/plan-eng-review` | Architecture and tests | 1 | Clear | 8 issues resolved, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | Not run | Initial functional UI only |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | Not run | Exact setup instructions included in scope |

**VERDICT:** ENG CLEARED. The optional outside voice was attempted but unavailable.

NO UNRESOLVED DECISIONS
