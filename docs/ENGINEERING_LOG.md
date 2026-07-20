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

## 2026-07-16 — Basic Pitch transcription and raw MIDI

- Basic Pitch 0.4.0 resolves on Windows Python 3.11 with TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1. A real generated WAV completed inference and produced both a note event and MIDI.
- TensorFlow remains isolated in `.venv-transcription`. FastAPI probes and launches `app.transcription.worker` as a subprocess, so ordinary API startup, tests, and media preparation remain usable without the optional ML environment.
- Alembic revision `20260716_0004` adds note confidence/pitch-bend evidence and ProcessingRun model/runtime/configuration provenance. Raw performance timing remains separate from future symbolic timing.
- `POST /api/projects/{project_id}/transcribe` requires normalized input, validates versioned worker JSON, atomically finalizes note-event JSON and raw MIDI, persists notes/provenance, reuses successful output, and cleans partial/final files across failure paths.
- Basic Pitch 0.4.0 crashes on a 0.01-second WAV because its analysis array is empty. A loaded-model experiment showed 0.05 seconds returns a valid empty result, so Pianova rejects inputs below 0.05 seconds before worker startup and covers the boundary with a regression test.
- The frontend exposes explicit transcription and a bounded raw-note preview while stating that quantization has not started.
- Verification baseline is now 43 backend tests, five component tests, a clean production build, and three live Chromium flows. The primary browser flow performs real FFprobe, FFmpeg, and Basic Pitch/TensorFlow processing.

## 2026-07-16 — Tempo estimation and readable quantization

- Alembic revision `20260716_0005` adds nullable complete project timing metadata, simple-meter checks, positive chord groups, a current quantization-run pointer, and a non-negative optimistic revision.
- The pure symbolic module groups attacks without tolerance chaining, builds candidates from at most four following groups, scores sixteenth-grid fit/readability/tempo prior, and rejects insufficient, weak, close-runner, or half/double-tempo evidence.
- Exact 120 BPM initially failed because the half-beat complexity penalty (0.03) equaled the winner-separation margin. Raising it to 0.04 made the acceptance contract internally attainable while retaining the octave ambiguity gate; a regression test locks this relationship.
- The real Basic Pitch fixture then exposed that 0.1-BPM candidate buckets can produce several near-identical winners from frame-level onset jitter. Runner-up ambiguity now ignores candidates within a persisted 2% tempo neighborhood; distinct and half/double candidates still face the original score gates.
- Onsets and durations use `Fraction` internally. Raw seconds are immutable; durations follow one fixed simplify/snap/cap/minimum order, and same-pitch collision repair is bounded.
- Quantization precommits a running audit row, fingerprints ordered raw evidence, reuses only the current matching result, and atomically compare-and-swaps project timing plus all note symbolic fields. Failure and concurrent-loser paths preserve the prior complete state.
- The frontend exposes automatic tempo, BPM recovery, `2/4`/`3/4`/`4/4`, explicit measure origin, fit diagnostics, and symbolic preview while clearly deferring hands, voices, and score generation.
- The live fixture uses five distinct piano tones whose attacks are adjusted for Basic Pitch analysis-frame rounding. The real worker must emit a pulse accepted within 119.5-120.5 BPM; this is an integration contract, not a musical benchmark.
- Verification baseline is now 62 backend tests, five component tests, a clean production build, and three live Chromium flows.

## 2026-07-18 — Voice separation plan review

- The voice-separation milestone was shaped and reviewed via gstack plan-eng-review; the approved plan is `docs/VOICE_SEPARATION_PLAN.md`. Three user decisions were locked: independent fourth stage (D1), preparatory `stage_runner` helper extraction with the unmodified existing suite as its regression gate (D2), and a deterministic two-coloring voice engine (D3).
- The originally drafted weighted-DP voice engine was found unsound during the Codex outside-voice pass: its per-onset split state could not legally track which sustained notes belonged to which voice. Because `first.md` makes the second voice strictly overlap-forced, the problem reduces to interval-conflict two-coloring per staff, where a 3-clique structurally proves `voice_capacity_exceeded`. Fourteen of sixteen outside-voice findings were folded; the unknowns-as-success doctrine and the voice-before-cleaned-MIDI ordering were kept with recorded rationale.
- Durable contract points: voice is a staff-scoped notation fact (nullable integer, checked `voice >= 1`, cap in the engine); the tri-state voice/score/reason database check enumerates its three valid states exactly; cascaded revision increments must be SQL-relative to avoid lost updates, with interleaving tests planned.
- Voice separation needs no key or spelling evidence, so key detection and enharmonic spelling remain the next boundary after voices.

## 2026-07-17 — Independent hand and staff interpretation

- Alembic revision `20260716_0006` adds current interpretation ownership/revision plus independent staff, bounded confidence, and typed ambiguity fields on note events.
- The pure interpretation engine uses separate bounded dynamic-programming passes for hand and notation staff over pitch-contiguous chord splits. Per-note confidence compares the best complete paths under competing assignments; close evidence persists as `unknown` with one primary reason.
- The orchestration service fingerprints the current quantization run and ordered symbolic evidence, persists all settings and diagnostics, and validates run ownership, stored JSON, diagnostic totals, confidence bounds, and unknown/reason consistency before reuse.
- A genuine re-quantization resets downstream assignments and current-run ownership and increments the interpretation revision in the same optimistic transaction. Quantization reuse preserves interpretation; commit failures and concurrency losers preserve the previous complete state.
- `POST /api/projects/{project_id}/interpret` and the capability registry expose the implemented boundary. The frontend adds an explicit action, disables duplicate submission, recovers after API failure, and displays resolved/unknown hand and staff evidence without claiming voices, spelling, cleaned MIDI, or score generation.
- The real generated five-note phrase now crosses FFprobe, FFmpeg, Basic Pitch/TensorFlow, automatic 120 BPM quantization, persistence, and hand/staff interpretation in Playwright.
- Verification baseline is now Ruff plus formatting, strict mypy across 34 backend application sources, 77 pytest tests, Alembic through `20260716_0006` with no drift, five component tests, a clean production build, and three live Chromium flows.

## 2026-07-18 — Shared symbolic-stage transaction runner

- Extracted `app.services.stage_runner.StageRunner` before voice implementation. It owns the
  durable RUNNING precommit, success-run completion plus project compare-and-swap row-count gate,
  and rollback-following failed-run audit update.
- Stage policy remains explicit: quantization and interpretation still own fingerprints, reuse
  validation, note mutations, CAS predicates and values, conflict errors, and result contracts.
  The extraction therefore changes no endpoint or persistence behavior.
- The original 77 backend tests pass unmodified when the new helper test file is excluded. Three
  isolated helper tests raise the baseline to 80 and cover precommit, CAS winner/loser, and failure
  marking.

## 2026-07-18 — Pure notation-voice engine

- Added the independent `app.symbolic.voices` contract with immutable inputs/results and no
  persistence, frontend, subprocess, notation-library, or ML dependency.
- The forced-only baseline collapses exact-onset/exact-duration chord nodes, constructs per-staff
  half-open interval conflicts, removes deterministic excess nodes when a 3-clique proves a third
  stream, and two-colors the remainder. Voice 1 is the upper-mean-pitch stream; unknown staff,
  capacity, crossing, and close alternatives are successful typed outputs.
- `voice_confidence` is explicitly an uncalibrated normalized separation margin. Thirteen focused
  fixtures cover all planned engine branches, input-order stability, and the resolved voice
  invariant, raising the backend baseline to 93 tests and 36 strict-mypy application sources.

## 2026-07-18 — Checked notation-voice persistence

- Alembic revision `20260718_0007` adds `current_voice_run_id`, non-negative `voice_revision`,
  nullable note voice with `voice >= 1`, bounded decision score, and typed ambiguity reason.
- The named voice-state check enumerates exactly unprocessed `(NULL, NULL, NULL)`, resolved
  `(voice, score, NULL)`, and unknown `(NULL, score, reason)`. The two-voice cap stays in engine
  version 1 rather than the schema so later versions can add voices without another migration.
- Ten migrated-SQLite tests prove all allowed states, all other presence combinations, numeric
  bounds, and the revision bound. Alembic upgrades through `20260718_0007` with no model drift;
  the backend baseline is 103 tests.

## 2026-07-18 — Voice-separation backend boundary

- Added the independent `voice_separation` service, endpoint, available capability, typed preview,
  per-staff voice counts, diagnostics, provenance, and fingerprinted reuse over the current
  successful interpretation run. Stored reuse is rejected unless ownership, JSON, diagnostics,
  tri-state fields, staff/reason rules, voice 1/2 bounds, scores, and overlap invariants all hold.
- Genuine re-interpretation invalidates voice state; genuine re-quantization invalidates both
  interpretation and voice state. Downstream revisions increment as SQL expressions inside the
  owning transaction instead of from stale Python reads.
- Four actual-service interleaving tests cover both commit orders for voice versus interpretation
  and voice versus quantization. In every order the first valid commit wins, the stale CAS fails,
  the prior complete result remains atomic, and no cascade revision increment is lost.
- Voice ambiguity remains a successful output with `unresolved_staff`,
  `voice_capacity_exceeded`, `crossing`, or `close_alternative`; there is no complexity error or
  weighted dynamic-programming path. `voice_confidence` remains an uncalibrated decision score.

## 2026-07-18 — Voice-separation frontend boundary

- Added the explicit post-interpretation `Separate voices` action with duplicate-submit locking,
  recoverable API errors, typed response state, and a seven-step terminal workflow state.
- The result view separates resolved from unknown counts, shows treble/bass voice 1/2 counts, and
  renders voice, uncalibrated decision score, and typed reason as distinct evidence columns.
  Unknown voices are labeled unknown rather than presented as completed notation.
- Component coverage exercises action gating, the pending label/disabled state, failure and retry,
  successful counts, unknown evidence, and truthful copy deferring key detection, pitch spelling,
  cleaned MIDI, and score generation.

## 2026-07-18 — Live transcription-to-voice boundary

- Extended the native Playwright vertical slice from hand/staff interpretation through the real
  voice service and final frontend evidence state.
- The generated monophonic five-tone phrase resolves all five notes to notation voice 1 with zero
  unknowns. The browser asserts the final seven-step state and downstream-stage truthfulness.
- This remains an orchestration contract over one synthetic phrase, not a musical voice-accuracy
  benchmark or evidence for contrapuntal identity.

## 2026-07-18 — Voice-separation milestone completion

- Completed the final consistency sweep across configuration, both READMEs, architecture,
  pipeline, data model, research, evaluation, roadmap, task state, handoff, and the approved plan.
- Research context now distinguishes forced notation layers from longer-lived contrapuntal stream
  separation and records why the deterministic engine does not adopt stochastic optimization,
  contig connection, or music21 runtime behavior.
- The final baseline remains 37 strict-mypy application sources, 116 pytest tests, five component
  tests, a production build, and three live Chromium flows through notation voices.

## 2026-07-19 — Key-spelling plan review locked (planning only)

- Resumed the plan-eng-review session that a terminal crash interrupted mid-review; the
  `docs/KEY_SPELLING_PLAN.md` draft and its approved decisions D2-D6 survived intact.
- Review finding 1: the enharmonic tonic naming rule was unstated and load-bearing (24
  pitch-class correlation vs 15-per-mode named signatures). Locked rule: fewer accidentals
  wins; the six-accidental tie (F#/Gb major, D#/Eb minor) breaks flat, matching the engine's
  flat-before-sharp spelling tie-break.
- Review finding 2: corrected the stale no-music-library claim; `pretty-midi` is declared in
  `backend/pyproject.toml` but imported nowhere, and T6 now audits it.
- Codex outside voice returned 15 findings. Accepted five: context-free D4 agreement with an
  explicit penalty formula and named weights; degenerate-evidence gates (distinct pitch
  classes, zero-variance histogram) before correlation; the engine contract now takes floats
  plus `chord_group` because symbolic beats persist as floats
  (`entities.py`/`quantization.py`), never Fractions; the four-state key check now couples to
  `current_spelling_run_id`; the live e2e gains a resolved-key leg and T1 gains hand-authored
  public-domain ground-truth fixtures, with a transcription-fragmentation caveat recorded in
  evaluation. Rejected per settled decisions: milestone reordering, stage merging, removing
  the voice prerequisite, and best-guess-with-flag unknowns.
- The plan file now ends with the GSTACK REVIEW REPORT: verdict ENG CLEARED, no unresolved
  decisions. No application code changed this session.
