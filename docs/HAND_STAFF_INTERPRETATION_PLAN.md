# Hand and Staff Interpretation Plan

Status: implemented and fully verified on 2026-07-17.

## Goal

Turn the current quantized note state into a deterministic first piano interpretation:
independent hand and notation-staff assignments, per-note confidence, explicit ambiguity reasons,
project/run ownership, and a bounded user-visible preview.

This slice is intentionally honest. It does not claim to solve polyphonic voice separation, global
key detection, enharmonic spelling, cleaned MIDI, MusicXML, or engraving.

## Approved scope

### In scope

- Left/right/unknown hand assignment.
- Treble/bass/unknown notation-staff assignment independent from hand.
- Passage-level continuity rather than isolated pitch thresholds.
- Per-note hand and staff confidence derived from competing interpretation paths.
- Typed primary ambiguity reasons.
- Atomic persistence, provenance, idempotent reuse, optimistic concurrency, and downstream
  invalidation when quantization changes.
- API and frontend preview with resolved/unknown counts.
- Deterministic pure, API, failure, component, and live-browser coverage.

### NOT in scope

- Voice separation: it is a distinct multi-trajectory interpretation problem and follows this
  stable hand/staff boundary.
- Key detection and enharmonic spelling: these need a tonal-analysis evaluation contract and will
  extend the interpreted-note model in the next slice.
- Cleaned MIDI: MIDI cannot faithfully carry staff or uncertainty, and track structure should wait
  for voice decisions.
- MusicXML or rendering: these remain downstream of voices, spelling, and an explicit complete
  score contract.
- Manual correction endpoints: this slice stores correction-friendly provenance but does not
  introduce editing behavior.
- Learned hand/staff models: deterministic heuristics establish the replaceable baseline first.

## What already exists

- `NoteEvent.hand` already stores `left`, `right`, or `unknown`.
- Quantized onset, duration, and chord group provide the typed input evidence.
- `Project.current_quantization_run_id` and `quantization_revision` identify the timing state that
  interpretation consumes.
- `ProcessingRun` provides stage auditing and versioned configuration/provenance.
- `QuantizationService` provides the proven precommit-running, transactional-success,
  compare-and-swap, separate-failure, and reuse pattern.
- The frontend already presents a bounded symbolic-note table after quantization.

The implementation extends these boundaries. It does not introduce a parallel project model,
notation library, file artifact, queue, or ML environment.

## Architecture decisions

- Hand and staff are independent facts. A right-hand note may be written on bass staff and a
  left-hand note may be written on treble staff.
- Unknown is a valid successful output, not a processing failure.
- A note below the configured path-margin threshold receives `unknown`, a numeric confidence, and
  one typed primary reason.
- Hand assignment uses bounded dynamic programming over contiguous chord splits.
- Staff assignment runs as a separate pass over the same evidence and may disagree with hand.
- Confidence compares the best complete passage cost under each alternative assignment.
- One pure `app.symbolic.interpretation` module owns analysis. One
  `app.services.interpretation` service owns persistence and API orchestration.
- Current assignments live on `NoteEvent`; project-level run ownership and revision make staleness
  explicit.
- Successful re-quantization clears interpretation fields, clears the current interpretation run,
  and increments the interpretation revision in the same transaction.
- The algorithm has a persisted version and settings. Changing scoring semantics requires a
  version bump.

## Data model

Alembic revision `20260716_0006` will add:

### Project

- `current_interpretation_run_id`: nullable pointer to the successful `interpretation` run that
  owns current note assignments.
- `interpretation_revision`: non-negative optimistic-concurrency counter, default zero.

### NoteEvent

- Existing `hand`: retained as `left`, `right`, or `unknown`.
- `staff`: non-null `treble`, `bass`, or `unknown`, default `unknown`.
- `hand_confidence`: nullable float in `[0, 1]`.
- `staff_confidence`: nullable float in `[0, 1]`.
- `hand_ambiguity_reason`: nullable typed reason.
- `staff_ambiguity_reason`: nullable typed reason.

Initial ambiguity reasons:

- `close_alternative`
- `middle_register`
- `wide_chord`
- `crossing`
- `insufficient_context`

Database checks enforce confidence bounds and non-negative revision. Service invariants enforce:

- a current interpretation run belongs to the project, has stage `interpretation`, and succeeded;
- processed notes have both confidence values;
- `unknown` assignments have a reason;
- resolved assignments have no ambiguity reason;
- current assignments were produced from the current quantization run and revision.

No foreign key is added from `Project.current_interpretation_run_id` to `ProcessingRun`, matching
the existing current-quantization pointer and avoiding a schema cycle. Ownership is a tested
service invariant.

## Typed pure contract

Create `app/symbolic/interpretation.py` with immutable typed inputs/results and no database,
filesystem, frontend, subprocess, or ML imports.

```text
InterpretationNote
  id
  pitch
  symbolic_start_beats
  symbolic_duration_beats
  chord_group

InterpretationSettings
  scoring weights
  comfortable pitch centers
  hand-span threshold
  ambiguity/high-confidence margins
  maximum transition evaluations

InterpretedNote
  note_id
  hand
  staff
  hand_confidence
  staff_confidence
  hand_ambiguity_reason
  staff_ambiguity_reason

InterpretationDiagnostics
  chord_group_count
  candidate_state_count
  transition_evaluations
  resolved/unknown hand counts
  resolved/unknown staff counts
  crossing/wide-chord counts
```

## Processing flow

```text
POST /api/projects/{id}/interpret
  |
  +-- require current successful quantization
  +-- load ordered notes once
  +-- validate complete symbolic timing/chord evidence
  +-- fingerprint current quantization run + ordered symbolic notes
  |
  +-- current successful interpretation matches fingerprint/settings/version?
  |       +-- yes: return persisted result
  |       +-- no: create RUNNING ProcessingRun and commit
  |
  +-- pure interpretation
  |       +-- group notes by chord_group
  |       +-- build contiguous lower/upper split candidates
  |       +-- solve hand path with bounded dynamic programming
  |       +-- calculate hand min-marginal alternatives/confidence
  |       +-- solve independent bass/treble staff path
  |       +-- calculate staff alternatives/confidence
  |       +-- assign typed primary ambiguity reasons
  |
  +-- success transaction
          +-- verify quantization run still matches
          +-- compare-and-swap interpretation_revision
          +-- write all NoteEvent assignment fields
          +-- set current_interpretation_run_id
          +-- increment interpretation_revision
          +-- mark run SUCCEEDED
          +-- commit

failure/conflict
  -> rollback all note/project changes
  -> mark precommitted run FAILED in a separate transaction
  -> preserve the prior complete interpretation
```

## Hand assignment engine

For each chord group, sort notes by pitch then ID. Candidate state `k` assigns the lowest `k`
notes to left hand and the remainder to right hand. Empty left or right partitions are allowed.
This baseline assumes simultaneous hand assignments are pitch-contiguous. Non-contiguous or
crossing alternatives surface as uncertainty rather than hidden guesses.

Candidate cost combines:

- distance from configurable left/right comfortable pitch centers;
- excess simultaneous span above the configured hand-span threshold;
- a weak penalty for using both hands on a compact chord;
- a weak penalty for placing an entire wide chord in one hand.

Transition cost combines:

- movement of each non-empty hand center between consecutive chord groups;
- hand disappearance/reappearance;
- abrupt split movement;
- ordering/crossing pressure.

The solver stores forward and backward minimum costs. For each note, the best complete path cost
among states assigning it left is compared with the best complete path cost among states assigning
it right. This min-marginal difference is the hand evidence margin.

```text
margin < ambiguity threshold
  -> hand=unknown
  -> confidence = margin / high-confidence margin
  -> primary ambiguity reason

margin >= ambiguity threshold
  -> hand = lower-cost alternative
  -> confidence = min(1, margin / high-confidence margin)
  -> ambiguity reason = null
```

## Staff assignment engine

Staff placement is a second lower/upper partition pass using bass/treble pitch comfort and
continuity weights. It does not copy hand. This permits cross-staff output:

```text
hand=right + staff=bass
hand=left  + staff=treble
```

The same min-marginal confidence rule applies independently. Middle-register notes with close
bass/treble alternatives remain `unknown`.

## Ambiguity reason priority

Only one actionable primary reason is persisted per dimension. Full component costs and thresholds
remain in ProcessingRun provenance.

Priority:

1. `insufficient_context`: too few surrounding groups to distinguish close alternatives.
2. `crossing`: the best local alternatives imply abrupt ordering or hand/staff crossing pressure.
3. `wide_chord`: the chord exceeds the configured comfortable single-hand span.
4. `middle_register`: pitch lies inside the configured central ambiguity band.
5. `close_alternative`: no more specific cause explains a sub-threshold margin.

## Configuration baseline

All values are typed `PIANOVA_` settings and persisted with the run:

- interpretation algorithm version;
- left/right and bass/treble comfortable pitch centers;
- pitch, span, movement, appearance, split, and crossing weights;
- comfortable hand span;
- middle-register lower/upper bounds;
- ambiguity and high-confidence margins;
- maximum transition evaluations;
- preview note limit.

These values are evaluation baselines, not universal piano truths.

## API contract

```text
POST /api/projects/{project_id}/interpret

request:
  {}

response:
  project interpretation ownership/revision
  total note count
  bounded interpreted-note preview
  resolved/unknown hand counts
  resolved/unknown staff counts
  typed diagnostics
  processor/version/configuration provenance
  reused
```

Structured failures:

- `quantization_required` (409)
- `incomplete_quantization` (409)
- `interpretation_too_complex` (422)
- `interpretation_conflict` (409)
- `interpretation_failed` (500)

Ambiguity is not an error response.

## Quantization invalidation

A successful non-reused quantization result must clear downstream interpretation in the same
transaction:

```text
each NoteEvent:
  hand = unknown
  staff = unknown
  hand/staff confidence = null
  hand/staff ambiguity reason = null

Project:
  current_interpretation_run_id = null
  interpretation_revision += 1
```

A reused quantization result does not invalidate interpretation.

## Frontend

Extend the existing terminal quantization state:

- add an explicit `Assign hands and staves` action;
- show a pending state and recoverable API errors;
- show resolved versus unknown counts for both dimensions;
- display hand, staff, confidence, and reason in a bounded note table;
- state that voices, key/spelling, cleaned MIDI, and score generation have not started;
- never label unknown assignments as completed notation.

The page remains session-local. Project discovery/resume stays deferred.

## Test coverage diagram

```text
CODE PATHS                                             USER FLOWS
[+] symbolic/interpretation.py                         [+] Interpret quantized project
  +-- validate non-empty/complete notes                  +-- [PLAN ★★★] success preview
  +-- group/order deterministic                          +-- [PLAN ★★★] unknown counts/reasons
  +-- build chord split states                           +-- [PLAN ★★★] retry API failure
  +-- hand DP                                            +-- [PLAN ★★★] double-submit disabled
  |   +-- obvious two-hand passage
  |   +-- middle-register ambiguity
  |   +-- repeated-note continuity
  |   +-- wide chord
  |   +-- crossing pressure
  |   +-- all-one-hand passage
  +-- forward/backward min marginals
  |   +-- resolved confidence
  |   +-- sub-threshold unknown
  +-- independent staff pass
  |   +-- ordinary bass/treble
  |   +-- right hand on bass staff
  |   +-- left hand on treble staff
  +-- work-budget rejection
  +-- stable output under input reordering

[+] services/interpretation.py                         [+] Live vertical slice [->E2E]
  +-- missing quantization -> 409                        +-- create/upload/prepare
  +-- incomplete symbolic state -> 409                   +-- Basic Pitch transcription
  +-- matching current result -> reuse                   +-- automatic quantization
  +-- changed fingerprint/version -> recompute            +-- hand/staff interpretation
  +-- precommit RUNNING                                  +-- visible resolved/unknown result
  +-- success CAS + complete note write
  +-- quantization changed during run -> conflict
  +-- success commit failure -> prior state preserved
  +-- failure marking failure -> logged

[+] quantization invalidation
  +-- reused quantization preserves interpretation
  +-- recomputed quantization clears assignments/pointer
  +-- recomputation increments interpretation revision

[+] migration/schema/API
  +-- enum and confidence constraints
  +-- complete response/provenance
  +-- capability truthfulness
```

Legend: `★★★` behavior + edge + error coverage; `[->E2E]` live integration boundary.

## Test files

- `backend/tests/test_symbolic_interpretation.py`
  - deterministic pure fixtures for every engine branch in the diagram;
  - exact confidence/reason expectations;
  - input-order invariance and work-budget rejection.
- `backend/tests/test_api.py`
  - prerequisite, success, persistence, response, reuse, and recomputation.
- `backend/tests/test_failure_paths.py`
  - commit rollback, concurrency conflict, failed-run recording, and quantization invalidation.
- `frontend/src/app/page.test.tsx`
  - action, pending state, success preview, unknown reasons, API recovery, and disabled resubmit.
- `frontend/e2e/vertical-slice.spec.ts`
  - extend the real generated-phrase flow through interpretation.

No LLM evaluation suite applies.

## Failure modes

| Failure | Handling | Test | User result |
|---|---|---|---|
| No current quantization | Structured 409 | API | Quantize first |
| Partial symbolic note state | Structured 409 | API | Re-quantize |
| Ambiguous note | Successful `unknown` assignment | Pure + UI | Reason shown |
| Path work exceeds budget | Structured 422 | Pure + API | Source too complex for baseline |
| Quantization changes mid-run | CAS conflict + rollback | Failure path | Retry latest timing |
| Database success commit fails | Rollback | Failure path | Prior interpretation retained |
| Failure audit commit fails | Log after rollback | Failure path | Original error retained |
| Frontend request fails | Alert + enabled retry | Component | User can retry |

No planned path has a silent failure without both handling and a test.

## Performance

- Sort once by chord group, symbolic onset, pitch, and ID.
- Candidate count per chord is `notes_in_chord + 1`.
- Dynamic-programming work is proportional to transitions between adjacent candidate sets.
- Count transition evaluations before execution and reject above the configured bound.
- Store only candidate costs/backpointers plus forward/backward tables; do not construct every
  full path.
- Load project notes once and write them in one transaction.
- No file, ML, subprocess, or notation-library work occurs.

## Implementation order

1. Add pure interpretation contracts, bounded solver, diagnostics, and deterministic tests.
2. Add migration/models/configuration and database invariants.
3. Add service orchestration, quantization invalidation, schemas, route, and backend tests.
4. Add frontend action/result/error states and component tests.
5. Extend the live browser flow.
6. Update all shared documentation and run the complete verification matrix.

Sequential implementation, no parallelization opportunity. The pure output contract determines the
schema, service, API, and frontend fields; splitting these across worktrees would create avoidable
contract conflicts.

## Review completion

- Step 0 scope challenge: scope reduced from hand/staff/voice/spelling to the first honest
  hand/staff slice.
- Architecture review: five issues resolved.
- Code-quality review: three issues resolved.
- Test review: complete code-path and user-flow diagram produced; no uncovered planned branch.
- Performance review: forward/backward min-marginals and a hard transition-work budget adopted.
- Failure modes: zero silent unhandled gaps.
- Outside voice: Claude read-only consult attempted twice but returned no review after an
  authenticated streaming failure; no outside recommendation was incorporated.
- Parallelization: one sequential lane.
- Lake score: 9/9 recommendations chose the complete or right-sized option.

## Deferred-work disposition

No `TODOS.md` is created because the repository roadmap and this plan already track the deferred
work with ordering and rationale:

- Voice separation: retain in roadmap milestone 6 after hand/staff.
- Key detection and enharmonic spelling: retain in roadmap milestone 6 after voice structure.
- Cleaned MIDI: retain in the pipeline after voice assignment.
- Manual correction: retain in roadmap milestone 8.
- Learned hand/staff model: retain as evaluation-driven model improvement, not an unmeasured TODO.

## Implementation Tasks

- [x] **T1 (P1)** — interpretation engine — implement bounded hand/staff partition solvers,
  min-marginal confidence, ambiguity reasons, diagnostics, and pure tests.
  - Files: `backend/app/symbolic/`, `backend/tests/test_symbolic_interpretation.py`
  - Verify: `pytest tests/test_symbolic_interpretation.py -q`
- [x] **T2 (P1)** — persistence — add interpretation ownership/revision and note assignment fields
  with checked migration.
  - Files: `backend/app/models/`, `backend/alembic/versions/`
  - Verify: `alembic upgrade head && alembic check`
- [x] **T3 (P1)** — backend boundary — add interpretation service, quantization invalidation,
  schemas, route, provenance, reuse, concurrency, and rollback coverage.
  - Files: `backend/app/services/`, `backend/app/api/`, `backend/app/schemas/`, `backend/tests/`
  - Verify: `ruff check . && mypy app && pytest`
- [x] **T4 (P2)** — frontend — add interpretation action, status, diagnostics, uncertainty, and
  preview.
  - Files: `frontend/src/`
  - Verify: `npm run lint && npm run typecheck && npm test`
- [x] **T5 (P1)** — live verification — extend the real browser flow through hand/staff
  interpretation.
  - Files: `frontend/e2e/`
  - Verify: `npm run build && npm run test:e2e`
- [x] **T6 (P2)** — shared context — update configuration, architecture, pipeline, data model,
  research, evaluation, roadmap, current task, handoff, and engineering log.
  - Files: `.env.example`, `README.md`, `backend/README.md`, `docs/`
  - Verify: `git diff --check` and stale-claim search

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---:|---|---|
| CEO Review | `/plan-ceo-review` | Scope and strategy | 0 | Not run | Scope reduced during engineering review |
| Outside Voice | Claude consult | Independent plan challenge | 1 | Unavailable | Authenticated read-only run ended without review output |
| Eng Review | `/plan-eng-review` | Architecture and tests | 1 | Clear | 9 decisions folded in, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | Not run | Functional status and uncertainty preview only |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | Not run | No new developer-facing workflow |

**VERDICT:** ENG CLEARED — ready to implement the reduced hand/staff slice.

NO UNRESOLVED DECISIONS
