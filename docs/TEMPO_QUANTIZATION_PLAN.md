# Tempo and Readable Quantization Plan

Status: implemented and verified on 2026-07-16.

## Goal

Turn persisted raw transcription notes into a deterministic, readable symbolic-timing baseline without changing raw performance evidence. The milestone produces one global tempo, an explicit measure origin, a default or user-selected simple meter, chord groups, quantized note onsets/durations, fit diagnostics, and provenance.

The baseline is intentionally replaceable. It is not a claim of reliable rubato tracking, automatic downbeat inference, or publication-ready notation.

## Approved decisions

- Estimate tempo from persisted note-onset evidence, not audio or the isolated TensorFlow/librosa worker.
- Persist current global timing on `Project`; retain algorithm/version/settings/diagnostics in `ProcessingRun.configuration_json`.
- Reuse only the current result when raw-note fingerprint, effective settings, and algorithm version match.
- Recompute only symbolic fields when tempo, meter, measure origin, algorithm version, or raw evidence changes.
- Use `fractions.Fraction` inside the algorithm and convert to floats only at persistence/API boundaries.
- Require absolute fit quality and candidate separation; reject weak or ambiguous automatic estimates with a recoverable BPM-override path.
- Generate tempo candidates from adjacent chord groups plus four groups of bounded look-ahead, never every onset pair.
- Persist and return typed tempo-fit diagnostics.
- Repair same-pitch onset collisions within a bounded adjustment; reject rhythms denser than the configured grid.
- Apply duration operations in one documented order.
- Treat measure origin as an explicit default or override, never inferred downbeat truth.
- Support only `2/4`, `3/4`, and `4/4`; compound-meter pulse semantics remain deferred.
- Point each project at the ProcessingRun that produced its current symbolic state.
- Keep ML-specific ProcessingRun columns transcription-only.
- Use the existing precommitted-running, transactional-success, separate-failure pattern.
- Add database checks for scalar timing invariants and optimistic concurrency for recomputation.
- Exercise automatic tempo estimation from real Basic Pitch output in the live browser test.
- Ship the full deterministic unit, API, rollback, component, and live-browser test matrix.

## What already exists

- `NoteEvent.raw_start_seconds` and `raw_end_seconds` preserve Basic Pitch evidence.
- `NoteEvent.symbolic_start_beats` and `symbolic_duration_beats` are reserved for this stage.
- `ProcessingRun` already records stage status, errors, and configuration JSON.
- The transcription response and frontend already expose a bounded raw-note preview.
- Existing service patterns cover prerequisite validation, idempotent reuse, rollback, structured errors, and API response assembly.

The implementation reuses these boundaries rather than introducing tempo-map, beat-event, cleaned-score, or audio-worker infrastructure.

## Data model

Alembic revision `20260716_0005` will add:

### Project

- `estimated_tempo_bpm`: nullable automatic estimate.
- `selected_tempo_bpm`: effective BPM used for quantization.
- `tempo_source`: `estimated` or `override`.
- `measure_origin_seconds`: timestamp treated as measure 1 beat 1 by default; an override may produce measure-zero pickup positions.
- `measure_origin_source`: `default` or `override`.
- `meter_numerator`, `meter_denominator`: effective simple time signature.
- `meter_source`: `default` or `override`.
- `current_quantization_run_id`: nullable pointer to the ProcessingRun that produced current project/note symbolic state.
- `quantization_revision`: non-negative optimistic-concurrency counter, default zero.

### NoteEvent

- `chord_group`: nullable positive project-local integer assigned chronologically.

Existing raw timing columns remain unchanged. Existing symbolic timing columns receive quarter-note-based values:

- `symbolic_start_beats`
- `symbolic_duration_beats`

Measure number and beat position are derived from symbolic onset plus meter in the response rather than persisted redundantly.

All timing metadata remains nullable for existing/unquantized projects. Database checks enforce:

- positive estimated/selected BPM when present;
- supported meter pairs only;
- positive chord-group numbers;
- non-negative quantization revision;
- all-or-none current timing metadata, except estimated BPM remains nullable for override-only results.

Cross-row note completeness, current-run ownership, and supported symbolic values remain service invariants covered by integration tests.

## API contract

```text
POST /api/projects/{project_id}/quantize

request:
  tempo_bpm?: float
  meter_numerator?: 2 | 3 | 4
  meter_denominator?: 4
  measure_origin_seconds?: float

response:
  project timing metadata
  total quantized note count
  bounded symbolic-note preview
  estimated and selected tempo
  tempo/meter/measure-origin source
  meter
  typed fit diagnostics
  processor/version/configuration provenance
  reused
```

Supported meter pairs are `2/4`, `3/4`, and `4/4`. BPM always means quarter notes per minute. Omitted meter values default to `4/4`. Supplying only one meter component or an unsupported pair returns a structured validation error.

Automatic tempo requires at least four distinct chord-onset groups, a minimum onset span, acceptable normalized residual, sufficient inlier coverage, and a winning candidate separated from the runner-up. Otherwise the API returns `tempo_ambiguous` and explains that the user can provide BPM.

`TempoEstimateDiagnostics` returns:

- candidate/selected BPM;
- normalized residual;
- weighted inlier coverage;
- winning and runner-up scores;
- score margin;
- analyzed chord-group count and onset span;
- whether a near-octave candidate contributed to ambiguity.

## Processing flow

```text
POST /quantize
  |
  +-- load Project and ordered NoteEvent rows once
  +-- validate transcription exists and notes are non-empty
  +-- validate optional BPM, simple meter, and measure-origin override
  +-- fingerprint ordered raw-note evidence
  +-- cluster near-simultaneous raw onsets into chord groups
  |
  +-- BPM override? ---------------------------+
  |       yes                                  | no
  |       use selected BPM                     +-- build bounded candidates
  |                                            +-- score timing + complexity
  |                                            +-- apply absolute fit gates
  |                                            +-- reject weak/ambiguous winner
  |
  +-- choose measure origin
  |       +-- request override, or
  |       +-- earliest chord attack with source=default
  |
  +-- quantize chord onsets and note durations with exact Fractions
  |       +-- allowed straight/dotted values through a whole note
  |       +-- longer values stay grid-aligned for later measure splitting
  |       +-- bounded same-pitch onset repair
  |       +-- fixed duration simplification/capping order
  |       +-- preserve note count and chronological ordering
  |
  +-- same fingerprint/settings/version as current successful run?
  |       +-- yes: return persisted result
  |       +-- no: continue
  |
  +-- compare-and-swap expected Project quantization revision
  +-- commit Project + NoteEvent + current-run pointer + ProcessingRun
          +-- rollback leaves prior symbolic result intact
          +-- failed run retains a useful error message
```

ProcessingRun state transitions:

```text
create RUNNING + commit
  -> calculate pure result
  -> success transaction:
       compare quantization revision
       write Project timing
       write NoteEvent symbolic fields
       set current_quantization_run_id
       increment revision
       mark run SUCCEEDED
       commit
  -> on any error:
       rollback result changes
       mark precommitted run FAILED in a separate transaction
       if failure recording fails, log without changing prior symbolic state
```

Quantizer identity uses typed configuration keys such as `processor_name`, `processor_version`, and `runtime`. Existing `model_name`, `model_version`, and `model_runtime` columns remain transcription-only.

## Pure symbolic-timing module

Create `app/symbolic/timing.py` with typed immutable inputs/results and no database, filesystem, frontend, or ML imports.

### Chord grouping

- Sort notes by raw onset then pitch.
- Start a new group when an onset falls outside the configured tolerance from the first onset in the current group; do not allow tolerance chaining.
- Use the median onset as the group evidence time.
- Group confidence is the mean of present note confidences; a group without model confidence receives weight 1.0.
- Assign chronological group numbers beginning at one.

### Tempo candidate generation and scoring

- Use differences from each chord group to the next four groups.
- Beat-distance hypotheses are `1/4`, `1/2`, `3/4`, `1`, `3/2`, `2`, `3`, and `4`.
- Candidate BPM is `60 * beat_distance / interval_seconds`.
- Retain candidates inside 40-200 BPM.
- Deduplicate in 0.1-BPM buckets. The representative is the confidence-weighted mean of exact candidates in the bucket.
- Treat candidates within 2% of the winner as one tempo neighborhood when selecting the runner-up; analysis-frame jitter must not manufacture a musically distinct alternative.

For candidate BPM `t`, group onset `s_i`, analysis origin `s_0`, group weight `w_i`, and sixteenth grid `g=1/4`:

```text
b_i = (s_i - s_0) * t / 60
q_i = nearest multiple of g, ties toward the earlier grid point
r_i = abs(b_i - q_i) / g

complexity(q_i) =
  0.00  integer beat
  0.04  eighth-note position
  0.08  remaining sixteenth position

residual(t)   = weighted_mean(r_i)
complexity(t) = weighted_mean(complexity(q_i))
prior(t)      = 0.03 * abs(log2(t / 120))
score(t)      = residual(t) + complexity(t) + prior(t)
coverage(t)   = weighted_share(r_i <= 0.35)
```

The estimate is accepted only when:

- at least four chord groups span at least 1.0 second;
- `residual <= 0.22`;
- `coverage >= 0.75`;
- the runner-up comes from outside the 2% winner neighborhood;
- `runner_up_score - winning_score >= 0.03`;
- no candidate near half/double the winning BPM is within 0.04 score.

All constants are typed settings and persisted with diagnostics. They are baseline values, not universal musical truths; changing them requires an algorithm-version bump.

### Quantization

- Quarter note equals one symbolic beat.
- Minimum grid is one sixteenth note (`1/4` beat).
- Preferred durations through a whole note are `1/4`, `1/2`, `3/4`, `1`, `3/2`, `2`, `3`, and `4`.
- Durations longer than four beats remain positive minimum-grid multiples and are split/tied only during later notation generation.
- Notes inside one chord group receive the same symbolic onset.
- Distinct same-pitch notes must have monotonically increasing symbolic onsets. Move a colliding later onset forward by one minimum grid step only when the adjustment stays within the configured repair tolerance; otherwise return `rhythm_too_dense`.
- Duration processing order is fixed:
  1. Convert the raw end to beat space relative to the selected measure origin.
  2. If it is within rest-simplification tolerance of the next chord onset, use that onset as the target end.
  3. Choose the nearest preferred duration through four beats; longer durations snap to the minimum grid.
  4. Cap the result at the next same-pitch symbolic onset.
  5. Enforce positive minimum duration or return `rhythm_too_dense`.
- A note must never have zero/negative symbolic duration or overlap the next same-pitch attack.

## Configuration

Add typed settings with conservative defaults:

- minimum/maximum automatic BPM;
- chord onset tolerance;
- minimum symbolic note value;
- minimum automatic-tempo group count and onset span;
- residual and inlier-coverage thresholds;
- tempo and octave-candidate ambiguity margins;
- rest simplification tolerance;
- same-pitch repair tolerance;
- preview-note limit;
- algorithm version constant.

The first implementation uses full snapping. Partial quantization strength is deferred until an editing workflow can explain and preview it.

## Failure modes

| Failure | Handling | Test | User result |
|---|---|---|---|
| Project missing | Structured 404 | API | Project-not-found message |
| Raw transcription missing | Structured 409 | API | Transcribe first |
| Zero notes | Structured 422 | API | No detected notes to quantize |
| Invalid BPM/meter/origin | Pydantic/domain validation | API | Correctable field message |
| Sparse onset evidence | `tempo_ambiguous` | Unit + API + UI | Enter BPM override |
| Weak absolute fit | Residual/coverage gates | Unit + API | Enter BPM override |
| Half/double-tempo tie | Explicit octave-candidate gate | Unit | No silent arbitrary choice |
| Rounding drift | Fractions internally | Unit | Exact grid values |
| Same-pitch collision | Bounded repair or `rhythm_too_dense` | Unit + API | Ordered repeats or recoverable error |
| Zero/negative duration | Minimum duration guard | Unit | Always valid symbolic note |
| Matching repeat request | Current-run fingerprint/config reuse | API | No duplicate work |
| Changed input/override | Recompute symbolic fields only | API | Raw evidence preserved |
| Database commit failure | Rollback and failed ProcessingRun | Failure-path test | Prior symbolic result remains |
| Concurrent recomputation | Revision compare-and-swap | Failure-path test | Retryable conflict |
| Rapid UI submission | Disable while pending | Component | One request |

No failure is silent.

## Test coverage

```text
CODE PATHS                                             USER FLOWS
[+] symbolic/timing.py                                 [+] Quantize after transcription
  +-- chord clustering                                   +-- [PLAN ★★★] automatic tempo success
  |   +-- within tolerance                               +-- [PLAN ★★★] BPM override success
  |   +-- outside tolerance                              +-- [PLAN ★★★] pending/double-submit
  |   +-- no tolerance chaining                          +-- [PLAN ★★★] symbolic preview
  +-- tempo estimation                                 [+] Recover from ambiguity
  |   +-- straight rhythm                                +-- [PLAN ★★★] clear diagnostics/error
  |   +-- half/double candidates                         +-- [PLAN ★★★] retain entered values
  |   +-- insufficient groups                            +-- [PLAN ★★★] enter BPM and retry
  |   +-- weak absolute fit                            [+] Full local workflow [-> E2E]
  |   +-- ambiguous score                                +-- upload
  +-- quantization                                       +-- prepare audio
      +-- straight/dotted values                         +-- real Basic Pitch transcription
      +-- chord-aligned onset                            +-- automatic tempo estimation
      +-- positive minimum duration                      +-- quantization
      +-- tiny-rest simplification                       +-- verify symbolic result/diagnostics
      +-- same-pitch collision repair/error
      +-- raw timing unchanged

[+] QuantizationService
  +-- prerequisites and validation
  +-- current fingerprint/config reuse
  +-- changed-input/settings recompute
  +-- optimistic-concurrency conflict
  +-- successful transaction/provenance
  +-- rollback preserves previous result

PLANNED COVERAGE: all listed branches
QUALITY TARGET: ★★★ behavior + boundaries + failure paths
```

Test files:

- `backend/tests/test_symbolic_timing.py`: pure deterministic musical fixtures and exact diagnostics.
- `backend/tests/test_api.py`: success, persistence, response, current-result reuse, input/override recomputation.
- `backend/tests/test_failure_paths.py`: prerequisites, ambiguity, dense rhythm, validation, conflict, rollback.
- `frontend/src/app/page.test.tsx`: pending, success, diagnostics, preview, ambiguity recovery.
- `frontend/e2e/vertical-slice.spec.ts`: generated distinct tones at 120 BPM through real Basic Pitch and automatic tempo estimation.

The E2E rhythm must produce at least four distinct Basic Pitch chord groups and an accepted tempo within a documented tolerance of 120 BPM. It proves the real transcription-to-estimator boundary but is not a broad musical-accuracy benchmark.

## Performance

- Load all project notes in one ordered query.
- Sort/cluster once: O(n log n).
- Candidate generation uses a four-group look-ahead: O(n).
- Candidate scoring is O(n × candidate_count), with candidates deduplicated and bounded.
- Response previews remain capped; total note count is separate.
- Reuse compares only the current run and includes algorithm version, effective settings, and a SHA-256 fingerprint of ordered raw-note evidence.
- No audio decode, ML import, subprocess, or generated artifact is required by the quantization stage.

## NOT in scope

- Audio beat tracking: retains the isolated worker boundary and is deferred until note-onset baselines are measured.
- Variable tempo, rubato maps, accelerando, and ritardando: require tempo-segment evidence and evaluation.
- Automatic downbeat or meter inference: meter and measure-origin sources are explicitly default or override.
- Compound meters: `6/8` and `12/8` require dotted-quarter pulse semantics.
- Pickup inference: a manual measure-origin override may produce measure-zero positions, but automatic pickup detection remains deferred.
- Triplets and tuplets: defer until straight/dotted scoring is measured; avoid fake advanced notation.
- Partial quantization strength: defer until the correction UI can preview the effect.
- Hand, staff, voice, key, and spelling analysis: next ordered milestones.
- Cleaned MIDI and cleaned note-event artifacts: follow hand/voice decisions.
- MusicXML, ties, and measure splitting: notation milestone.
- Project discovery/resume after page refresh: later inspection/correction milestone; document the page-session limitation.

Existing roadmap and research documents already track these deferred stages, so this review adds no separate `TODOS.md` items.

## Parallelization

Sequential implementation, no parallelization opportunity. Persistence, service, API, and frontend contracts depend on the same evolving symbolic schema; worktrees would add merge overhead without shortening the critical path.

## Implementation Tasks

- [x] **T1 (P1)** — symbolic timing — implement exact chord grouping, tempo scoring, absolute-fit/ambiguity detection, diagnostics, collision repair, and quantization.
  - Surfaced by: review decisions D3, D6, D7, D9-D16.
  - Files: `backend/app/symbolic/`, `backend/tests/test_symbolic_timing.py`
  - Verify: `pytest tests/test_symbolic_timing.py -q`
- [x] **T2 (P1)** — persistence — add global timing/chord fields, current-run pointer, revision, and checked migration.
  - Surfaced by: review decisions D4, D17, D20, D21.
  - Files: `backend/app/models/`, `backend/alembic/versions/`
  - Verify: `alembic upgrade head && alembic check`
- [x] **T3 (P1)** — backend boundary — add quantization service, schemas, route, fingerprinted reuse, recomputation, diagnostics, optimistic concurrency, provenance, and rollback.
  - Surfaced by: review decisions D5, D8, D12, D17-D21.
  - Files: `backend/app/services/`, `backend/app/api/`, `backend/app/schemas/`, `backend/tests/`
  - Verify: `ruff check . && mypy app && pytest`
- [x] **T4 (P2)** — frontend — add tempo/simple-meter/measure-origin controls, ambiguity recovery, diagnostics, and symbolic-note preview.
  - Surfaced by: review decisions D8, D12, D15, D16.
  - Files: `frontend/src/`
  - Verify: `npm run lint && npm run typecheck && npm test`
- [x] **T5 (P1)** — live verification — extend the real browser flow through automatic tempo estimation and quantization.
  - Surfaced by: review decision D22.
  - Files: `frontend/e2e/`
  - Verify: `npm run build && npm run test:e2e`
- [x] **T6 (P2)** — shared context — update architecture, pipeline, data model, research, evaluation, roadmap, current task, handoff, and engineering log.
  - Surfaced by: repository documentation-freshness requirements.
  - Files: `README.md`, `docs/`
  - Verify: `git diff --check` and stale-claim search

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---:|---|---|
| CEO Review | `/plan-ceo-review` | Scope and strategy | 0 | Not run | Product direction inherited from `first.md` |
| Outside Voice | automatic | Independent plan challenge | 1 | Clear | 15 findings reviewed; 14 folded into the plan and refresh/resume explicitly deferred |
| Eng Review | `/plan-eng-review` | Architecture and tests | 1 | Clear | 22 technical decisions resolved, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | Not run | Functional controls and result states only |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | Not run | No new developer-facing workflow |

**CROSS-MODEL:** Both reviews agree on the right-sized stage boundary; the outside voice tightened determinism, state ownership, concurrency, and live evidence.

**VERDICT:** ENG + OUTSIDE VOICE CLEARED — implemented and verified.

NO UNRESOLVED DECISIONS
