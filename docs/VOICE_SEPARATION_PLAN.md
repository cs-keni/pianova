# Voice Separation Plan

Status: reviewed execution plan, approved 2026-07-18. T1-T2 are complete; T3-T7 remain.

## Goal

Turn the current interpreted note state into per-staff **notation voices** (engraving layers, the
fact MusicXML consumes): a deterministic assignment of each staff-resolved note to voice 1 or
voice 2, a per-note decision score, explicit typed unknowns, project/run ownership, cascade
invalidation, and a bounded user-visible preview.

This slice is intentionally honest. It does not claim contrapuntal voice analysis, key detection,
enharmonic spelling, cleaned MIDI, MusicXML, or rendering. "Voice" in this boundary means the
notation stream a note is engraved in, not a musicological voice identity.

## Approved scope

### In scope

- One shared stage-orchestration helper extracted from the proven quantization/interpretation
  mechanics, landed as its own zero-behavior-change refactor commit (decision D2).
- A new independent voice-separation stage with its own endpoint, ProcessingRun stage, project
  ownership pointer, and optimistic revision (decision D1).
- Staff-scoped notation-voice assignment via deterministic conflict-graph two-coloring
  (decision D3, adopted from the outside-voice review): voice 1 is the upper stream, voice 2 the
  lower, and a second voice exists only where the voice invariant forces it. Hard rule, not a
  penalty.
- Structurally sound capacity detection: three mutually overlapping incompatible streams form a
  3-clique, which proves a genuine third stream; those notes become typed unknowns.
- A per-note normalized decision score (documented as such — not calibrated probability) derived
  from stream pitch separation, plus typed primary ambiguity reasons.
- Cascade invalidation with SQL-relative revision increments and concurrency interleaving tests.
- API and frontend preview with resolved/unknown and per-staff voice counts.
- Deterministic pure, service, failure-path, component, and live-browser coverage, plus the
  regression guarantee that the helper extraction leaves the existing 77 tests passing unmodified.
- Documentation updated inside each task's definition of done, per repository process.

### NOT in scope

- Key detection and enharmonic spelling: voice separation consumes pitch, symbolic timing, and
  staff only; no coupling was proven during review, so tonal analysis remains the next boundary.
- Cleaned MIDI: track/channel structure should reflect voice decisions, so it follows this slice.
- MusicXML or rendering: downstream of voices and spelling. The consumption contract for unknown
  assignments (voice, hand, or staff) is defined at that boundary, which is one reason it stays
  deferred (outside-voice finding 12, rejected for this slice with this rationale).
- Voluntary (taste-driven) second voices: the forced-only rule is hard in this version; relaxing
  it requires a new algorithm version.
- Tie-based single-voice renotation: same-onset unequal-duration notes force a second voice here
  even where notation reconstruction could instead tie shorter values in one voice. Known,
  documented limitation with a dedicated fixture (outside-voice finding 7).
- More than two voices per staff: the engine reports overflow instead of guessing; the schema
  check (`voice >= 1`) already admits higher numbers if a future version supports them.
- Contrapuntal voice separation, melody extraction, learned models: the deterministic baseline is
  the replaceable Layer-1 contract; link-prediction and GNN approaches stay documented research.
- Manual correction endpoints: provenance stays correction-friendly; editing is a later slice.
- Sustain-pedal-aware voice merging: raw pedal evidence is not yet modeled; noted in research.

## What already exists

- `NoteEvent` carries quantized `symbolic_start_beats`, `symbolic_duration_beats`, `chord_group`,
  independent `hand`/`staff`, confidences, and typed ambiguity reasons. It has no voice fields.
- `Project.current_interpretation_run_id` / `interpretation_revision` identify the assignment
  state voices consume; `current_quantization_run_id` anchors the timing chain above it.
- `QuantizationService` and `InterpretationService` both implement precommit-RUNNING,
  fingerprinted reuse, compare-and-swap success, rollback-safe failure, and separate failed-run
  audit. The voice stage reuses these mechanics through the extracted helper instead of copying
  them a third time.
- The frontend already renders staged actions, pending/error recovery, uncertainty previews, and
  truthful deferred-stage copy.
- music21 `makeVoices()` was considered and rejected: music21 is not yet a dependency, and its
  naive overlap partitioning cannot carry decision scores, typed unknowns, or provenance.

## Architecture decisions

- D1 (user-approved): voice separation is an independent fourth stage. Re-quantization clears
  interpretation and voices; re-interpretation clears voices; voice recomputation never touches
  hand/staff state.
- D2 (user-approved): extract `app/services/stage_runner.py` first — precommit-run creation,
  failure marking, and the CAS project update — as a separate commit with zero behavior change,
  verified by the unmodified existing test suite. Stage-specific fingerprinting, validation, and
  reuse logic stay in each service.
- D3 (user-approved, from outside-voice review): the engine is deterministic conflict-graph
  two-coloring, not weighted dynamic programming. The originally drafted DP had an unsound state
  (it could not legally track which sustained notes belonged to which voice), and the hard
  forced-only rule makes weighted search unnecessary.
- Voice is a staff-scoped notation fact. `voice` is a nullable small integer on `NoteEvent`:
  1 is the upper stream, 2 the lower, mapping directly to MusicXML per-staff voice numbers.
- Voice invariant: within one `(staff, voice)` pair, two notes may overlap in time only if they
  share both symbolic onset and duration (a chord within that voice). The engine enforces it by
  construction; the service enforces it on reuse; tests property-check it on every fixture.
- Unknown is a successful output. Tri-state persistence, enumerated exactly:
  - unprocessed: `voice` NULL, `voice_confidence` NULL, `voice_ambiguity_reason` NULL;
  - resolved: `voice` set, `voice_confidence` set, reason NULL;
  - unknown: `voice` NULL, `voice_confidence` set, reason set.
  No other combination is representable (database check lists these three states verbatim).
- A note with `staff = unknown` receives voice unknown with structural reason `unresolved_staff`
  without entering the engine. Voices are staff-scoped facts; an unresolved staff makes the voice
  undecidable by construction.
- `voice_confidence` is a normalized decision score (stream separation margin), documented as
  such everywhere it surfaces. It is not calibrated probability; calibration waits for labeled
  correction data. The field name stays consistent with the shipped hand/staff boundary.
- The engine derives per-staff onset groups from `symbolic_start_beats`. `chord_group` spans both
  staves and is not reused for voice grouping.
- Cascaded revision increments are SQL-relative (`voice_revision = voice_revision + 1`), never
  computed in Python from a possibly stale read, so concurrent upstream/voice commits cannot lose
  increments.
- The algorithm has a persisted version and settings. Changing semantics requires a version bump.

## Data model

Alembic revision `20260718_0007` will add:

### Project

- `current_voice_run_id`: nullable pointer to the successful `voice_separation` run owning the
  current note voices. No foreign key, matching the existing stage pointers.
- `voice_revision`: non-negative optimistic-concurrency counter, default zero, checked.

### NoteEvent

- `voice`: nullable integer, checked `voice >= 1` when present. The two-voice cap lives in the
  engine version, not the schema, so a future version raising the cap needs no migration.
- `voice_confidence`: nullable float, checked within `[0, 1]`.
- `voice_ambiguity_reason`: nullable typed reason.
- Tri-state check enumerating exactly the three valid states:

```text
(voice IS NULL     AND voice_confidence IS NULL     AND voice_ambiguity_reason IS NULL) OR
(voice IS NOT NULL AND voice_confidence IS NOT NULL AND voice_ambiguity_reason IS NULL) OR
(voice IS NULL     AND voice_confidence IS NOT NULL AND voice_ambiguity_reason IS NOT NULL)
```

### New enum

`VoiceAmbiguityReason` (separate from `AssignmentAmbiguityReason`, keeping per-dimension validity
typed; every reason has a defined structural or margin trigger):

- `unresolved_staff` — the note has no resolved staff.
- `voice_capacity_exceeded` — a conflict clique larger than two proves a third stream.
- `crossing` — the two streams invert pitch order inside the component at this note.
- `close_alternative` — stream pitch separation below the close-separation threshold.

Service invariants enforce: current run belongs to the project with stage `voice_separation` and
status succeeded; processed notes obey the enumerated tri-state; the voice invariant holds within
every `(staff, voice)`; and current voices were produced from the current interpretation run and
revision.

## Typed pure contract

Create `app/symbolic/voices.py` with immutable typed inputs/results and no database, filesystem,
frontend, subprocess, or ML imports.

```text
VoiceNote
  id
  pitch
  symbolic_start_beats (Fraction)
  symbolic_duration_beats (Fraction)
  staff ("treble" | "bass" | "unknown")

VoiceSettings
  close_separation_semitones   (below this mean stream separation -> unknown)
  high_separation_semitones    (at or above this -> score 1.0; validated >= close)

VoicedNote
  note_id
  voice (1 | 2 | None)
  voice_confidence (normalized decision score)
  voice_ambiguity_reason (None when resolved)

VoiceDiagnostics
  treble/bass note counts
  chord_node_count, conflict_component_count
  two_voice_component_count, crossing_component_count
  capacity_exceeded_count, unresolved_staff_count
  resolved_count / unknown_count

VoiceSeparationResult
  notes
  diagnostics
```

Errors: `notes_required`, `incomplete_interpretation`, each a typed `VoiceSeparationError`.
There is no work-budget error: two-coloring over interval conflicts is near-linear after the
onset sort, so no input can trigger combinatorial blowup (the DP's `too_complex` rejection is
gone with the DP).

## Processing flow

```text
POST /api/projects/{id}/separate-voices
  |
  +-- require current successful interpretation run
  +-- load ordered notes once
  +-- validate complete symbolic + processed hand/staff evidence
  +-- fingerprint interpretation run + ordered (id, pitch, start, duration, staff) + settings
  |
  +-- current successful voice run matches fingerprint/settings/version?
  |       +-- yes: validate tri-state, diagnostics, voice invariant -> return persisted result
  |       +-- no: precommit RUNNING ProcessingRun via stage_runner
  |
  +-- pure voice separation (per staff: treble pass, bass pass)
  |       +-- staff=unknown notes -> unknown + unresolved_staff (no engine entry)
  |       +-- collapse same-onset+duration notes into chord nodes
  |       +-- build interval-overlap conflict edges between incompatible nodes
  |       +-- connected components; cliques > 2 -> capacity_exceeded unknowns,
  |       |     remaining component notes still colored
  |       +-- two-color each component; upper stream by pitch = voice 1
  |       +-- unconflicted notes -> voice 1, score 1.0
  |       +-- separation-based decision score; crossing/close typed reasons
  |
  +-- success transaction (stage_runner CAS)
          +-- verify current_interpretation_run_id unchanged
          +-- compare-and-swap voice_revision
          +-- write all NoteEvent voice fields
          +-- set current_voice_run_id; increment voice_revision (SQL-relative)
          +-- mark run SUCCEEDED, persist diagnostics provenance
          +-- commit

failure/conflict
  -> rollback all note/project changes
  -> mark precommitted run FAILED in a separate transaction
  -> preserve the prior complete voice state
```

## Voice engine (two-coloring)

Per staff:

1. Collapse notes sharing exact symbolic onset and duration into chord nodes.
2. Add a conflict edge between two nodes whose intervals overlap in time (the voice invariant
   forbids them sharing a voice). Interval sweep after one onset sort: O(n log n + edges).
3. Take connected components of the conflict graph. Nodes outside any component are voice 1 with
   score 1.0 (no competing alternative exists under the forced-only rule).
4. Inside a component, find the maximum clique size cheaply via the interval sweep's concurrent-
   stream counter. If more than two incompatible nodes sound simultaneously, the deterministically
   identified excess notes (latest onset, then highest pitch, then id) become
   `voice_capacity_exceeded` unknowns and are removed from the coloring problem. This is sound:
   a 3-clique proves a genuine third stream, independent of any path choice.
5. Two-color the remaining component (interval graphs are perfect; greedy by onset is exact and
   deterministic). A component has exactly two colorings; pick the one whose higher-mean-pitch
   stream is voice 1.
6. Score each colored note by normalized stream separation at its onset span:
   `score = min(1, separation_semitones / high_separation_semitones)`. Below
   `close_separation_semitones`, the note is unknown with a typed reason: `crossing` when the two
   streams invert pitch order inside the component at that note, otherwise `close_alternative`.
   The score is a decision margin, not calibrated probability, and is documented as such.

Deterministic by construction; input-order invariance is a tested property. Sustained-note-over-
moving-accompaniment resolves because the sustained node conflicts with every moving attack,
forcing two streams, and pitch order labels them.

Known limitation (documented + fixture): same-onset nodes with unequal durations always force two
voices here, even where notation reconstruction could tie shorter values inside one voice. That
choice belongs to the future MusicXML boundary.

## Ambiguity reason priority

Structural reasons are determined, not margin-based, and take precedence:

1. `unresolved_staff`
2. `voice_capacity_exceeded`
3. `crossing`
4. `close_alternative`

Full component diagnostics persist in ProcessingRun provenance.

## Configuration baseline

Typed `PIANOVA_` settings, persisted with every run:

- `voice_algorithm_version` (initial `1.0.0`);
- `voice_close_separation_semitones` (default 2.0);
- `voice_high_separation_semitones` (default 7.0; validated >= close);
- `voice_preview_note_limit` (default 50).

These values are evaluation baselines, not universal musical truths. The two-coloring engine has
no scoring weights to tune — a deliberate simplification adopted in review.

## API contract

```text
POST /api/projects/{project_id}/separate-voices

request:
  {}

response:
  voice ownership/revision
  total note count
  bounded voiced-note preview
  resolved/unknown counts
  per-staff voice-1/voice-2 counts
  capacity/unresolved-staff/crossing diagnostics
  processor/version/configuration provenance
  reused
```

Structured failures:

- `interpretation_required` (409)
- `incomplete_interpretation` (409)
- `voice_separation_conflict` (409)
- `voice_separation_failed` (500)

Ambiguity is not an error response. The capability registry gains a **new** `voice_separation`
capability registered as available (no voice capability exists today); key detection, spelling,
cleaned MIDI, and score generation remain truthfully unimplemented.

## Invalidation cascade

```text
genuine re-quantization (existing transaction, extended):
  clear hand/staff fields                                   (existing)
  clear voice/confidence/reason                             (new)
  current_interpretation_run_id = null,
  interpretation_revision = interpretation_revision + 1     (existing)
  current_voice_run_id = null,
  voice_revision = voice_revision + 1                       (new, SQL-relative)

genuine re-interpretation (same CAS transaction):
  clear voice/confidence/reason
  current_voice_run_id = null
  voice_revision = voice_revision + 1                       (SQL-relative)

quantization reuse: preserves interpretation and voices.
interpretation reuse: preserves voices.
voice recomputation: never touches hand/staff state.
```

All cascaded counter increments execute as SQL expressions against the current row value inside
the owning CAS transaction, so a concurrent voice commit and upstream commit cannot lose an
increment; one of them loses its CAS and surfaces the structured conflict. Interleaving tests
cover both orderings.

## Frontend

Extend the interpreted terminal state:

- explicit `Separate voices` action, enabled only after successful interpretation;
- pending state, recoverable API errors, duplicate-submit prevention;
- resolved versus unknown voice counts and per-staff voice-1/voice-2 counts;
- voice, decision score, and reason columns in the bounded note preview;
- truthful copy that key detection, spelling, cleaned MIDI, and score generation have not started;
- unknown voices presented as evidence, never as completed notation.

The page remains session-local; project resume stays deferred.

## Test coverage diagram

```text
CODE PATHS                                              USER FLOWS
[+] symbolic/voices.py                                  [+] Separate voices on interpreted project
  +-- validate staff/symbolic evidence                    +-- [PLAN ***] success preview + counts
  +-- chord-node collapse (exact onset+duration)          +-- [PLAN ***] unknown voices show reasons
  +-- conflict edges via interval sweep                   +-- [PLAN ***] API failure -> retry
  |   +-- chord stays one node/voice                      +-- [PLAN ***] double-submit disabled
  |   +-- sustained-over-moving forces component          +-- [PLAN ***] truthful downstream copy
  |   +-- suspension chain alternation
  |   +-- same-onset unequal-duration limitation        [+] Live vertical slice [->E2E]
  |   +-- 3-clique -> capacity_exceeded, rest colored     +-- [PLAN ***] upload -> prepare -> Basic
  +-- two-coloring per component                               Pitch -> quantize -> interpret ->
  |   +-- monophonic -> all voice 1, score 1.0                 separate voices; five-tone fixture
  |   +-- upper-by-pitch = voice 1 (+ inverted variant)        resolves all voice 1
  |   +-- crossing streams -> crossing reason
  |   +-- close separation -> close_alternative          [+] Regression guard (IRON RULE)
  +-- staff=unknown -> unresolved_staff                    +-- [PLAN ***] existing 77 tests pass
  +-- separation-based decision score both branches            UNMODIFIED after stage_runner
  +-- voice invariant property check on every fixture          extraction (quantization +
  +-- input-order invariance / determinism                     interpretation behavior pinned)

[+] services/stage_runner.py
  +-- precommit RUNNING run
  +-- CAS success / conflict loser
  +-- mark-failed separate transaction

[+] services/voices.py
  +-- missing/failed interpretation -> 409
  +-- incomplete interpretation state -> 409
  +-- matching fingerprint -> validated reuse
  +-- changed fingerprint/settings/version -> recompute
  +-- interpretation changed mid-run -> CAS conflict
  +-- success commit failure -> prior state preserved
  +-- failure audit commit failure -> logged

[+] invalidation cascade + concurrency
  +-- re-interpretation clears voices + pointer + revision
  +-- interpretation reuse preserves voices
  +-- re-quantization cascades interpretation AND voices atomically
  +-- quantization reuse preserves both
  +-- interleaving: voice commit vs upstream commit, both orderings,
        no lost revision increments

[+] migration/schema/API
  +-- voice value / score bounds / enumerated tri-state checks
  +-- complete response/provenance shape
  +-- new capability registration truthfulness
```

Legend: `***` behavior + edge + error coverage planned; `[->E2E]` live integration boundary.

## Test files

- `backend/tests/test_symbolic_voices.py`
  - deterministic musical fixtures for every engine branch: monophonic lines, uniform chords,
    sustained-over-moving in both registers, suspension chains, the same-onset unequal-duration
    limitation, 3-clique overflow with remaining notes colored, unresolved staves, crossing and
    close-separation unknowns, order invariance, and the voice invariant property-checked on
    every output.
- `backend/tests/test_stage_runner.py`
  - helper mechanics in isolation: precommit, CAS winner/loser, failure marking.
- `backend/tests/test_api.py`
  - prerequisite 409s, success persistence and response shape, reuse, recomputation after
    re-interpretation, per-staff counts, new-capability registration.
- `backend/tests/test_failure_paths.py`
  - commit rollback, concurrency conflict, failed-run recording, both cascade directions, and
    the revision-increment interleaving tests.
- `frontend/src/app/page.test.tsx`
  - action gating, pending state, success preview, unknown reasons, API recovery, disabled
    resubmit.
- `frontend/e2e/vertical-slice.spec.ts`
  - extend the real generated-phrase flow through voice separation.

The helper-extraction commit runs the complete existing suite unmodified as its regression gate.
No LLM evaluation suite applies.

## Evaluation

`docs/evaluation.md` gains a voice-separation section: tracked counts (unknown rate, two-voice
component rate, capacity-exceeded rate, crossing rate) over the deterministic fixture corpus.
Note-level ground-truth voice benchmarks are deferred until the correction workflow can produce
labeled data; the decision score is documented as uncalibrated until then. Recorded as a
limitation, not claimed capability.

## Failure modes

| Failure | Handling | Test | User result |
|---|---|---|---|
| No current interpretation | Structured 409 | API | Interpret first |
| Partially processed assignment state | Structured 409 | API | Re-interpret |
| Staff unknown on a note | Successful `unresolved_staff` unknown | Pure + UI | Reason shown |
| Genuine third stream (3-clique) | Successful `voice_capacity_exceeded` unknown | Pure + UI | Reason shown |
| Streams cross or barely separate | Successful `crossing`/`close_alternative` unknown | Pure + UI | Reason shown |
| Interpretation changes mid-run | CAS conflict + rollback | Failure path | Retry latest result |
| Concurrent voice/upstream commits | SQL-relative increments + CAS; loser gets conflict | Interleaving | Retry latest result |
| Success commit fails | Rollback | Failure path | Prior voice state retained |
| Failure audit commit fails | Log after rollback | Failure path | Original error retained |
| Helper refactor drifts behavior | Unmodified existing suite as regression gate | Regression | No visible change |
| Frontend request fails | Alert + enabled retry | Component | User can retry |

No planned path has a silent failure without both handling and a test.

## Performance

- One ordered note query; one success transaction; no N+1 access.
- Chord-node collapse and the interval conflict sweep are O(n log n); two-coloring is linear in
  component size. No combinatorial search exists, so no work-budget rejection is needed.
- Only component structures and stream labels are held in memory.
- No file, ML, subprocess, or notation-library work occurs in this stage.

## Implementation Tasks

Documentation is part of every task's definition of done: each task updates the docs its change
invalidates in the same commit, per repository process. T7 is a final consistency sweep, not the
documentation step.

- [x] **T1 (P1)** — stage-runner extraction — extract precommit/CAS/mark-failed mechanics into
  `app/services/stage_runner.py`; migrate quantization and interpretation services with zero
  behavior change; land as its own commit.
  - Files: `backend/app/services/`, `backend/tests/test_stage_runner.py`
  - Verify: `ruff check . && mypy app && pytest` with existing tests unmodified
- [x] **T2 (P1)** — voice engine — implement pure per-staff two-coloring, voice invariant,
  structural and margin reasons, diagnostics, and the full deterministic fixture suite.
  - Files: `backend/app/symbolic/`, `backend/tests/test_symbolic_voices.py`
  - Verify: `pytest tests/test_symbolic_voices.py -q`
- [ ] **T3 (P1)** — persistence — add voice fields, project ownership/revision, and checked
  migration `20260718_0007` with the enumerated tri-state check.
  - Files: `backend/app/models/`, `backend/alembic/versions/`
  - Verify: `alembic upgrade head && alembic check`
- [ ] **T4 (P1)** — backend boundary — voice service on stage_runner, cascade invalidation with
  SQL-relative increments in quantization and interpretation services, interleaving tests,
  schemas, route, new capability registration, and full API/failure coverage.
  - Files: `backend/app/services/`, `backend/app/api/`, `backend/app/schemas/`, `backend/tests/`
  - Verify: `ruff check . && mypy app && pytest`
- [ ] **T5 (P2)** — frontend — voice action, status, per-staff counts, uncertainty preview, and
  component tests.
  - Files: `frontend/src/`
  - Verify: `npm run lint && npm run typecheck && npm test`
- [ ] **T6 (P1)** — live verification — extend the real browser flow through voice separation.
  - Files: `frontend/e2e/`
  - Verify: `npm run build && npm run test:e2e`
- [ ] **T7 (P2)** — shared context sweep — final consistency pass over configuration, README,
  architecture, pipeline, data model, research (voice-separation literature), evaluation,
  roadmap, current task, handoff, and engineering log.
  - Files: `.env.example`, `README.md`, `backend/README.md`, `docs/`
  - Verify: `git diff --check` and stale-claim search

### Parallelization

| Step | Modules touched | Depends on |
|------|-----------------|------------|
| T1 helper extraction | `backend/app/services/` | — |
| T2 pure engine | `backend/app/symbolic/` | — |
| T3 persistence | `backend/app/models/`, `backend/alembic/` | T2 contract |
| T4 backend boundary | `backend/app/services/`, `api/`, `schemas/` | T1, T2, T3 |
| T5 frontend | `frontend/src/` | T4 |
| T6 e2e | `frontend/e2e/` | T5 |
| T7 docs sweep | `docs/`, READMEs | all |

Lane A: T1 (independent). Lane B: T2 → T3 (contract determines schema). Launch A and B in
parallel; merge both; then T4 → T5 → T6 → T7 sequentially. Conflict flag: T1 and T4 both touch
`backend/app/services/` — T4 must start from the merged result of both lanes.

## Review completion

- Step 0 scope challenge: complexity gate triggered (expected milestone shape); D1 resolved the
  stage-boundary fork; key detection confirmed decoupled; music21 `makeVoices()` considered and
  rejected; deterministic Layer-1 baseline confirmed against voice-separation literature.
- Architecture review: five decisions folded (staff-scoped notation voice, voice invariant,
  unknown interaction, cascade invalidation, engine shape); one user decision (D1).
- Code-quality review: one finding (orchestration duplication) resolved by user decision D2.
- Test review: complete code-path and user-flow diagram produced; regression rule applied to the
  helper extraction; no uncovered planned branch.
- Performance review: no issues found.
- Outside voice (Codex, high reasoning): 16 findings. Folded: 1/2/3/5/6 (engine reframed to
  two-coloring, user decision D3), 4 (notation-voice framing), 7 (documented limitation +
  fixture), 8 (decision-score language), 9 (enumerated tri-state check), 10 (`voice >= 1` check
  only), 11 (SQL-relative increments + interleaving tests), 13 (parallel lanes restored),
  15 (docs in each task's definition of done), 16 (new-capability wording). Rejected with
  rationale: 12 (unknowns-as-success is shipped repo doctrine; consumption contract defined at
  the MusicXML boundary), 14 (milestone ordering settled by the user's handoff and the prior
  plan's cleaned-MIDI-after-voices rationale).
- Failure modes: zero silent unhandled gaps.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | Not run | Scope fixed by handoff and CURRENT_TASK.md |
| Outside Voice | Codex `exec` (high) | Independent 2nd opinion | 1 | ISSUES FOUND | 16 findings: 14 folded (incl. engine reframe D3), 2 rejected with rationale |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 17 issues total, 0 critical gaps, 3 user decisions (D1-D3), 0 unresolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | Not run | Functional status/uncertainty preview only |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | Not run | No new developer-facing workflow |

**CODEX:** Outside voice caught a genuine defect (unsound DP state) and drove the simpler
two-coloring engine adopted as D3; concurrency, schema-check, sequencing, and process
corrections folded; unknowns-doctrine and milestone-ordering objections rejected per shipped
precedent and the user's handoff.

**CROSS-MODEL:** One substantive tension (engine algorithm) — resolved in Codex's favor by
user decision D3 after verification of the DP-state objection.

**VERDICT:** ENG CLEARED — ready to implement (T1/T2 parallel lanes first).

NO UNRESOLVED DECISIONS
