# Key Detection and Enharmonic Spelling Plan

Status: locked after independent Codex review 2026-07-19. T1 pure engine, T2 checked
persistence, and T3 backend integration are complete and verified; T4 frontend is next.

## Goal

Turn the current persisted notation-voice state into a **tonal boundary**: one estimated or
user-overridden global key on the project, plus a deterministic enharmonic spelling
(step, alter, octave) for every note, with per-note decision scores, explicit typed unknowns,
project/run ownership, cascade invalidation, and a bounded user-visible preview.

This slice is intentionally honest. It does not claim modulation detection, harmonic analysis,
cleaned MIDI, MusicXML, rendering, or correction tooling beyond the single key override this
boundary strictly needs. "Key" in this boundary means one global tonal center for the piece;
"spelling" means the written pitch name, never a mutation of the underlying MIDI pitch.

## Approved scope

### In scope

- One new independent pitch-spelling stage (decision D2): one endpoint, one ProcessingRun stage
  (`pitch_spelling`), one project ownership pointer, one optimistic revision, one cascade hop
  below voice separation. The pure engine keeps key estimation and spelling as separate internal
  functions so a future stage split needs no schema rework.
- Global key detection only (decision D3): duration-weighted pitch-class correlation against the
  24 major/minor Krumhansl-Kessler profiles, with acceptance gates (minimum note count,
  runner-up margin) and typed unknown reasons. Local keys/modulation are a documented deferred
  boundary.
- Truthful ambiguity semantics (decision D4): an unknown key is a successful output with a typed
  reason (`insufficient_notes`, `ambiguous_key`). Spelling still runs: notes whose candidate
  spellings agree across every plausible key resolve normally; notes whose spelling depends on
  the contested key succeed as unknown with reason `unknown_key`.
- Explicit key override (decision D5): an optional request field mirroring the shipped BPM
  override. Validated against the 15 standard signatures per mode, bypasses acceptance gates,
  persists as `key_source = override`, participates in the input fingerprint.
- Deterministic contextual spelling (decision D6): per-note decisions in a fixed stream order
  (staff, voice, onset, pitch, id), scored by line-of-fifths proximity to the key with a
  chord-consistency preference within the persisted `chord_group` and a chromatic-neighbor
  melodic-step preference.
  Close margins succeed as typed `close_alternative` unknowns.
- Persistence with enumerated valid states, migration `20260719_0008`, SQL-relative cascade
  invalidation from every upstream stage, and both-order concurrency interleaving tests.
- API and frontend preview with the key result, resolved/unknown spelling counts, an
  unknown-key recovery selector, and truthful downstream copy.
- Deterministic pure, service, failure-path, component, and live-browser coverage.
- Documentation updated inside each task's definition of done, per repository process.

### NOT in scope

- Local keys and modulation: profile methods degrade at key changes; segmentation with change
  penalties is a tuning-heavy boundary deferred until labeled evaluation data exists. The
  deferred contract is per-segment key rows; the v1 schema stores one project-level key.
- Double accidentals in engine v1: the candidate set is the 21 single-accidental names. The
  schema check admits `alter` in [-2, 2] so a future engine version can add double accidentals
  without a migration (same pattern as the voice-cap decision).
- Key signature rendering, courtesy accidentals, and measure-level accidental state: those are
  MusicXML-boundary facts computed from this stage's output, not persisted here.
- Harmonic analysis (chord labels, Roman numerals): not needed by spelling's bounded
  chord-consistency rule, which only prefers third-stacking among simultaneous notes.
- Cleaned MIDI, MusicXML, rendering: downstream boundaries, unchanged order.
- Correction tooling beyond the single key override: per-note spelling edits belong to the
  correction milestone; provenance stays correction-friendly.
- Learned or corpus-tuned models (full ps13 windowing, HMM key tracking): documented research
  references; the deterministic baseline is the replaceable Layer-1 contract.
- Synthesia, cloud deployment, authentication, model training: unchanged deferrals.

## What already exists

- `NoteEvent` carries pitch, symbolic timing persisted as floats (converted from the
  quantizer's exact Fractions at `services/quantization.py`), `chord_group` (the persisted
  same-onset truth), independent `hand`/`staff`, and tri-state notation-voice fields. It has
  no spelling fields. Spelling consumes the floats and `chord_group` as stored — it never
  reconstructs Fractions or compares float onsets for equality (review: Codex #12).
- `Project.current_voice_run_id` / `voice_revision` identify the voice state spelling consumes;
  the quantization and interpretation pointers anchor the chain above it.
- `app.services.stage_runner` owns the precommit-RUNNING/CAS-success/mark-failed transaction
  shell proven by three stages. The spelling service is its fourth consumer and copies the
  voice service's shape for fingerprinting, hardened reuse, and cascade invalidation.
- The frontend staged-action pattern (gate, pending, error recovery, evidence table, truthful
  deferred-stage copy) is established; this milestone extends it with one action and one card.
- The quantization stage ships the override precedent this plan mirrors: explicit BPM with
  `tempo_source = override`, gates bypassed, provenance recorded.
- No notation or key-analysis library is in use in the core backend (`pretty-midi` is declared
  in `backend/pyproject.toml` but imported nowhere — T6 audits whether to remove or document
  it). music21 key analysis was considered and rejected on the voice-boundary precedent: no
  typed unknowns, no provenance, heavyweight runtime for two ~100-line deterministic kernels.
  No new dependency is added.

## Architecture decisions

- D2 (user-approved): key detection and enharmonic spelling are one combined independently owned
  stage. Rationale: spelling needs the key; no consumer needs a keyed-but-unspelled state; the
  engine's internal split keeps a future stage split cheap.
- D3 (user-approved): global key only. Weak or split evidence succeeds as a typed unknown key.
  Matches the global-BPM precedent; modulation is deferred with a crisp boundary.
- Canonical tonic naming (review finding 1, user-approved): correlation runs over the 24
  pitch-class keys; a deterministic canonical-naming step (fewer accidentals; the 6-accidental
  tie breaks flat) maps the winner and every D4 plausible key to one named tonic before
  spelling. Keeps line-of-fifths scoring deterministic and stops enharmonic duplicates from
  inflating D4 contested sets.
- D4 (user-approved): selective resolve under an unknown key. Cross-key agreement is
  computed key-proximity-only (context-free): a note's best spelling per plausible key uses
  the line-of-fifths term alone — chord-consistency and melodic bonuses apply only under a
  resolved or overridden key. This keeps the unknown-key path O(24n) and deterministic
  without per-key context branching (review: Codex #5). Plausible-key semantics:
  - `ambiguous_key`: plausible keys are those within the ambiguity margin of the best
    correlation; a note is contested when those keys disagree on its best spelling.
  - `insufficient_notes`: no reliable ranking exists, so plausible keys are all 24 pitch-class
    keys, each under its canonical name (see Engine details); a note is
    contested exactly when its pitch class has more than one single-accidental candidate, and
    resolves only when it has exactly one — the single-name classes D, G, and A. The other
    naturals (C, E, F, B) are contested: B#, Fb, E#, and Cb are the genuine line-of-fifths
    best spellings in extreme plausible keys (e.g. B# in C# minor), so they succeed as
    `unknown_key`.
  - A per-key winner is stable only when it is the sole candidate or its normalized
    best-vs-runner-up margin meets `spelling_close_margin`. Cross-key agreement resolves a
    note only when every plausible key has the same stable winner. A close/tied winner in any
    plausible key or different stable winners across keys succeeds as `unknown_key`. A
    cross-key resolved note stores the minimum per-key confidence (worst-case support);
    `unknown_key` stores confidence 0.0. This prevents deterministic tie-breaking from
    manufacturing false agreement while retaining O(24n) work (independent review finding 2).
- D5 (user-approved): optional `key_override` request field, validated, gate-bypassing,
  persisted as `key_source = override`, fingerprint-participating.
- D6 (user-approved): spelling context is key proximity + chord consistency within the same
  `chord_group` + chromatic-neighbor melodic steps, evaluated in deterministic stream order
  with fixed candidate tie-breaking (smaller absolute alter, then flat before sharp — `id`
  orders the stream, never candidates of one note). Close margins are typed unknowns.
- Spelling is a written-notation fact: `spelled_step`/`spelled_alter`/`spelled_octave` on
  `NoteEvent`; MIDI pitch is never mutated (per `first.md`). Octave is stored explicitly so
  downstream consumers never re-derive the B#/Cb boundary arithmetic.
- Unknown is a successful output. Tri-state spelling persistence enumerated exactly, mirroring
  the shipped voice check; four-state key persistence on the project (unprocessed, estimated,
  estimated-unknown, override) enumerated in a named check.
- `spelling_confidence` and `key_confidence` are normalized decision margins, documented as
  uncalibrated everywhere they surface, matching the hand/staff/voice fields.
- Cascaded revision increments are SQL-relative inside the owning transaction; the stage CAS
  predicates make either commit order deterministic (prior-learning:
  symbolic-current-run-ownership).
- The algorithm has a persisted version and settings. Changing semantics requires a version
  bump (initial `1.0.0`).

## Data model

Alembic revision `20260719_0008` will add:

### Project

- `key_tonic_step`: nullable string, one of A-G.
- `key_tonic_alter`: nullable integer in [-1, 1].
- `key_mode`: nullable enum `major` | `minor`.
- `key_confidence`: nullable float in [0, 1] (normalized correlation margin).
- `key_ambiguity_reason`: nullable enum `insufficient_notes` | `ambiguous_key`.
- `key_source`: nullable enum `estimated` | `override`.
- `current_spelling_run_id`: nullable pointer, no foreign key, matching existing stage pointers.
- `spelling_revision`: non-negative optimistic-concurrency counter, default zero, checked.
- Named check `ck_projects_key_state` enumerating exactly four valid states, each coupled to
  the ownership pointer (review: Codex #14) — the key state is `unprocessed` if and only if
  `current_spelling_run_id` IS NULL:

```text
(unprocessed)      step NULL, alter NULL, mode NULL, confidence NULL, reason NULL, source NULL, run_id NULL
(estimated)        step SET,  alter SET,  mode SET,  confidence SET,  reason NULL, source 'estimated', run_id SET
(estimated-unknown) step NULL, alter NULL, mode NULL, confidence SET,  reason SET,  source 'estimated', run_id SET
(override)         step SET,  alter SET,  mode SET,  confidence NULL, reason NULL, source 'override',  run_id SET
```

  Persistence tests prove both illegal couplings (pointer set + key unprocessed; key set +
  pointer null) are rejected by the database.

- The tonic must belong to the 15 standard signatures per mode (line-of-fifths -7..+7);
  enforced by the service and engine, not the schema, so a future extended-key version needs
  no migration.

### NoteEvent

- `spelled_step`: nullable string A-G.
- `spelled_alter`: nullable integer, checked in [-2, 2] (engine v1 emits only [-1, 1]).
- `spelled_octave`: nullable integer, checked in [-2, 9] — the exact reachable range for
  `alter` in [-2, 2] over MIDI 0-127 (B#-2 = MIDI 0 at the low edge; G9 = MIDI 127 at the top;
  octave 10 is unreachable).
- `spelling_confidence`: nullable float, checked in [0, 1].
- `spelling_ambiguity_reason`: nullable enum `unknown_key` | `close_alternative`.
- Named check `ck_note_events_spelling_state` enumerating exactly three valid states:

```text
(unprocessed) step NULL,  alter NULL,  octave NULL,  confidence NULL, reason NULL
(resolved)    step SET,   alter SET,   octave SET,   confidence SET,  reason NULL
(unknown)     step NULL,  alter NULL,  octave NULL,  confidence SET,  reason SET
```

### New enums

`KeyMode` (`major`, `minor`), `KeySource` (`estimated`, `override`),
`KeyAmbiguityReason` (`insufficient_notes`, `ambiguous_key`),
`SpellingAmbiguityReason` (`unknown_key`, `close_alternative`) — separate enums, keeping
per-dimension validity typed, matching the voice-reason precedent.

Service invariants enforce: the current spelling run belongs to the project with stage
`pitch_spelling` and status succeeded; processed notes obey the enumerated tri-state; the
project key obeys the four-state check and matches the run's recorded key result; and current
spellings were produced from the current voice run and revision.

## Typed pure contract

Create `app/symbolic/spelling.py` with immutable typed inputs/results and no database,
filesystem, frontend, subprocess, notation-library, or ML imports.

```text
SpellingNote
  id
  pitch
  symbolic_start_beats (float, as persisted)
  symbolic_duration_beats (float, as persisted)
  chord_group (positive int)         (persisted same-onset truth; never float equality)
  staff ("treble" | "bass" | "unknown")
  voice (int | None)

KeyOverride
  tonic_step, tonic_alter, mode      (validated against the 15-signature set)

SpellingSettings
  key_minimum_notes                  (below this -> insufficient_notes)
  key_minimum_distinct_pitch_classes (below this -> insufficient_notes, before correlation)
  key_ambiguity_margin               (best-vs-runner-up margin; below -> ambiguous_key)
  spelling_close_margin              (normalized candidate margin; below -> close_alternative)

KeyEstimate
  tonic_step, tonic_alter, mode      (None when unknown)
  confidence                         (normalized margin; None for override)
  ambiguity_reason                   (None when resolved or overridden)
  source                             ("estimated" | "override")

SpelledNote
  note_id
  step, alter, octave                (None when unknown)
  spelling_confidence
  spelling_ambiguity_reason          (None when resolved)

SpellingDiagnostics
  duration-weighted pitch-class histogram
  best/runner-up key identities and correlation margin
  candidate-set sizes; chord-consistency and melodic-rule application counts
  resolved_count / unknown_count and per-reason counts

SpellingResult
  key (KeyEstimate)
  notes
  diagnostics
```

Errors: `notes_required`, `incomplete_voice_state`, and `invalid_key_override`, each a typed
`SpellingError`. There is no
work-budget error: the histogram is O(n); spelling under a resolved key evaluates at most
two candidates per note in one ordered pass; the unknown-key agreement check is
key-proximity-only over at most 24 canonical plausible keys — O(24n), no context branching
(review: Codex #5). No input can trigger combinatorial blowup.

## Processing flow

```text
POST /api/projects/{id}/spell
  |
  +-- require current successful voice run
  +-- load ordered notes once
  +-- validate complete symbolic + processed voice tri-state evidence
  +-- validate key_override against the supported signature set (422 on failure)
  +-- fingerprint voice run/revision + ordered (id, pitch, start, duration, chord_group,
  |     staff, voice) over stored float values + settings + algorithm version + key_override
  |
  +-- current successful spelling run matches fingerprint/settings/version?
  |       +-- yes: validate key state, tri-state, diagnostics -> return persisted result
  |       +-- no: precommit RUNNING ProcessingRun via stage_runner
  |
  +-- pure spelling (app.symbolic.spelling)
  |       +-- key: override? adopt it : duration-weighted histogram -> 24-profile
  |       |     correlation -> gates -> KeyEstimate or typed unknown
  |       +-- spelling: fixed stream order (staff, voice, onset, pitch, id)
  |       |     +-- candidate set per pitch class (21 single-accidental names)
  |       |     +-- score: line-of-fifths proximity to key (or context-free
  |       |     |     plausible-key agreement under unknown key, per D4)
  |       |     +-- chord_group chord-consistency preference (third stacking)
  |       |     +-- chromatic-neighbor melodic-step preference within the stream
  |       |     +-- margin below spelling_close_margin -> close_alternative unknown
  |       +-- diagnostics
  |
  +-- success transaction (stage_runner CAS)
          +-- verify current_voice_run_id unchanged
          +-- compare-and-swap spelling_revision
          +-- write all NoteEvent spelling fields + Project key fields
          +-- set current_spelling_run_id; increment spelling_revision (SQL-relative)
          +-- mark run SUCCEEDED, persist diagnostics provenance
          +-- commit

failure/conflict
  -> rollback all note/project changes
  -> mark precommitted run FAILED in a separate transaction
  -> preserve the prior complete spelling state
```

## Engine details

Key detection:

1. Build the duration-weighted pitch-class histogram from `symbolic_duration_beats`.
2. Correlate against the 24 fixed major/minor profiles (Krumhansl-Kessler values recorded as
   constants with their source; deterministic fixed iteration order).
3. Canonical tonic naming: correlation operates over pitch-class keys; the winner — and every
   plausible key in a D4 set — maps to exactly one named tonic before spelling. The rule:
   the enharmonic spelling with fewer accidentals wins (Db major over C# major, B major over
   Cb major); the only tie, six accidentals (F#/Gb major, D#/Eb minor), breaks flat (Gb major,
   Eb minor), mirroring the engine's flat-before-sharp spelling tie-break so one convention
   holds engine-wide. Fixtures lock every enharmonic pair and both tie cases.
4. Degenerate-evidence gates run before correlation (review: Codex #9): inputs must have
   finite starts and positive finite durations. Fewer than
   `key_minimum_notes` notes OR fewer than `key_minimum_distinct_pitch_classes` distinct
   pitch classes (default 3 — eight repeats of one pitch carry evidence of one class)
   -> `insufficient_notes` without correlating. The histogram is normalized by total duration
   before its centered norm is tested. A zero or near-zero centered norm (perfectly or
   numerically near-uniform weights) makes Pearson correlation undefined or evidentially
   unstable -> typed `ambiguous_key`, all 24 keys become plausible, and correlation never
   runs. Fixtures cover single-pitch, uniform, near-uniform, and exactly-at-boundary
   histograms.
5. When the histogram is non-degenerate, the 24-profile correlation always runs (O(n), and
   diagnostics require it); the remaining gate classifies the result: best-vs-runner-up
   margin below `key_ambiguity_margin` -> `ambiguous_key`. Relative-key ties (C major vs
   A minor share a signature) count as distinct candidates; the margin decides, and the
   fixed profile order breaks exact ties.
6. `key_confidence` is the normalized margin in every estimated state — resolved and both
   unknown reasons — so the four-state persistence check (`confidence SET` for
   estimated-unknown) is always satisfiable by real engine output. When the degenerate
   gates fire before correlation, the confidence is 0.0 (no ranking evidence exists).
   For correlated evidence, `key_confidence = clamp((best_r - runner_up_r) / 2, 0, 1)`;
   Pearson's full -1..1 span therefore maps to 0..1, and `key_ambiguity_margin` is compared
   in that same normalized domain. Documented as uncalibrated.
7. An override adopts the requested key with `source = override`, `confidence = None`.

Enharmonic spelling:

1. Candidate names per pitch class come from the fixed 21-name single-accidental table.
2. Notes are processed in deterministic stream order. The order is total: staff sorts
   `treble < bass < unknown`; voice sorts known voices ascending, then `None` last; then
   onset (stored float, ordering only — equality semantics live in `chord_group`), pitch,
   id. Unknown-staff and `None`-voice notes therefore hold a defined, deterministic
   decision slot but join no (staff, voice) melodic stream. A fixture asserts this total
   order. Under a resolved or overridden key, each decision minimizes an explicit penalty
   (review: Codex #8):

   ```text
   penalty(candidate) = |lof(candidate) - lof(tonic)|
                        - W_chord * stacks_as_third(candidate, decided notes in the same
                                                    chord_group)
                        - W_step  * forms_chromatic_neighbor_step(candidate, previous
                                                    decided note in the same (staff, voice)
                                                    stream; no bonus when the predecessor
                                                    is unknown or absent)
   ```

   `lof` is the line-of-fifths index; `W_chord` and `W_step` are named engine constants
   (initial values 2.0 and 1.0 line-of-fifths units) persisted with the run.
   `spelling_confidence` is the non-negative best-vs-runner-up raw penalty gap divided by the
   fixed, versioned `SPELLING_GAP_FULL_SCALE = 12.0` line-of-fifths units and clamped to
   [0, 1]. A single-candidate pitch class has confidence 1.0. The denominator is not the
   observed candidate range: engine v1 has at most two candidates per pitch class, so that
   denominator would collapse every non-tie to 1.0 (independent review finding 1).
   `spelling_close_margin` compares against the fixed-scale normalized gap. The
   margin-attainability fixtures gate these exact values before they freeze.
   Under an unknown key, the D4 agreement check is key-proximity-only: the penalty is the
   `lof` term alone, per canonical plausible key — no chord or melodic bonuses. Agreement
   uses the stable-winner and worst-case-confidence rule in D4 above.
3. Candidate ties break deterministically: smaller absolute alter, then flat before sharp.
   (`id` participates in stream ordering only — it cannot distinguish two candidate
   spellings of one note.)
4. `spelled_octave` is computed so that (step, alter, octave) maps exactly back to the MIDI
   pitch, with B#/Cb boundary fixtures locking the arithmetic.
5. Margins below `spelling_close_margin` succeed as `close_alternative`; contested notes under
   an unknown key succeed as `unknown_key` (D4 semantics above).
6. Staff- or voice-unknown notes are still spelled: context rules simply have less evidence
   (no stream neighbor), and the decision remains truthful because the score reflects it.

Deterministic by construction; input-order invariance is a tested property.

The margin-versus-scoring-term interaction must be proven internally attainable by fixtures
(prior-learning: tempo-margin-penalty-conflict): a clear C-major fixture must pass both key
gates, and a chromatic fixture must trip `close_alternative` without tripping `ambiguous_key`,
before thresholds are frozen.

## Ambiguity reason priority

Key reasons are mutually exclusive by construction: the evidence gates (note count, distinct
pitch classes) are evaluated first, so `insufficient_notes` takes precedence over
`ambiguous_key`; the zero-variance case classifies as `ambiguous_key` (per Engine details).
Spelling reasons, in precedence order:

1. `unknown_key` — the spelling depends on a contested key (D4).
2. `close_alternative` — candidate margin below threshold under a resolved key.

## Configuration baseline

Typed `PIANOVA_` settings, persisted with every run:

- `spelling_algorithm_version` (initial `1.0.0`);
- `key_minimum_notes` (default 8);
- `key_minimum_distinct_pitch_classes` (default 3);
- `key_ambiguity_margin` (default 0.05);
- `spelling_close_margin` (default 0.10, compared against the normalized penalty gap);
- `spelling_preview_note_limit` (default 50).

Engine constants (not settings; bumping them bumps `spelling_algorithm_version`):
`W_chord` (2.0), `W_step` (1.0), the Krumhansl-Kessler profile values, and the canonical
tonic-naming table, plus `SPELLING_GAP_FULL_SCALE` (12.0) and the normalized-histogram
degeneracy tolerance.

These values are evaluation baselines, not universal musical truths; fixtures prove the
defaults are internally attainable before they are frozen.

## API contract

```text
POST /api/projects/{project_id}/spell

request:
  {}                                     (estimate the key)
  { "key_override": { "tonic_step": "E", "tonic_alter": -1, "mode": "major" } }

response:
  key: source, tonic/mode (or null), confidence, ambiguity reason,
       derived key_signature_fifths for display
  spelling ownership/revision
  total note count
  bounded spelled-note preview (hand/staff/voice/spelling columns)
  resolved/unknown spelling counts and per-reason counts
  histogram/margin diagnostics
  processor/version/configuration provenance
  reused
```

Structured failures:

- `voice_separation_required` (409)
- `incomplete_voice_state` (409)
- `invalid_key_override` (422)
- `spelling_conflict` (409)
- `spelling_failed` (500)

Ambiguity is not an error response. The capability registry gains a new `pitch_spelling`
capability registered as available; cleaned MIDI, MusicXML, and score generation remain
truthfully unimplemented.

## Invalidation cascade

```text
genuine re-quantization (existing transaction, extended):
  existing interpretation + voice clears
  clear spelling fields + project key fields              (new)
  current_spelling_run_id = null,
  spelling_revision = spelling_revision + 1               (new, SQL-relative)

genuine re-interpretation (same CAS transaction):
  existing voice clears
  clear spelling fields + project key fields              (new)
  current_spelling_run_id = null,
  spelling_revision = spelling_revision + 1               (new, SQL-relative)

genuine re-voice-separation (same CAS transaction):
  clear spelling fields + project key fields              (new)
  current_spelling_run_id = null,
  spelling_revision = spelling_revision + 1               (new, SQL-relative)

quantization/interpretation/voice reuse: preserves spelling.
spelling recomputation: never touches voice, hand/staff, or timing state.
An override key is a request-time input: upstream invalidation clears it like any other
stage output, and the frontend re-offers the selector on the next unknown-key result.
```

All cascaded increments are SQL-relative inside the owning transaction; interleaving tests
cover both commit orders for spelling against each upstream stage.

The spelling-clear fragment (note spelling fields, project key fields, pointer null, and the
SQL-relative revision bump) is defined once in a shared helper alongside `stage_runner` and
consumed by all three upstream cascade sites and the spelling service itself — never
hand-copied per service, so a future column cannot drift out of one cascade site.

## Frontend

Extend the voiced terminal state:

- explicit `Detect key & spell notes` action, enabled only after successful voice separation;
- pending state, recoverable API errors, duplicate-submit prevention;
- an always-visible optional key selector (15 signatures x 2 modes, blank default =
  auto-detect) beside the action, mirroring the shipped tempo-override input: blank submits
  `{}`, a selection submits `key_override`, and clearing it back to blank re-estimates on the
  next run — so a confidently wrong estimate or stale override is always correctable;
- a key card: estimated key with confidence, or the typed unknown reason with the selector
  emphasized for recovery; override results labeled as user-chosen, never as estimated;
- resolved versus unknown spelling counts and per-reason counts;
- spelled name (e.g. `F#4`), decision score, and reason columns in the bounded note preview;
- truthful copy that cleaned MIDI, MusicXML, and score rendering have not started;
- unknown spellings presented as evidence, never as completed notation.

The page remains session-local; project resume stays deferred.

## Test coverage diagram

```text
CODE PATHS                                              USER FLOWS
[+] symbolic/spelling.py                                [+] Spell on voiced project
  +-- key detection                                       +-- [PLAN ***] gated until voices done
  |   +-- clear major / clear minor                       +-- [PLAN ***] success key card + counts
  |   +-- duration-weighting decides                      +-- [PLAN ***] unknown key -> reason +
  |   +-- insufficient_notes unknown                            selector emphasized
  |   +-- ambiguous_key (C vs Am) unknown                 +-- [PLAN ***] override resubmit ->
  |   +-- canonical naming (Db/C#, tie->flat)                   override-labeled key, respelled
  |   +-- degenerate gates: single pitch,
  |   |     uniform (zero-variance), boundary
  |   +-- margin-attainability regression
  |   +-- ground-truth public-domain excerpts
  |                                                       +-- [PLAN ***] override after resolved
  |                                                       +-- [PLAN ***] clear selector -> re-estimate
  |   +-- deterministic tie-break                         +-- [PLAN ***] API failure -> retry
  |   +-- override adopt / invalid -> 422                 +-- [PLAN ***] double-submit disabled
  +-- spelling                                            +-- [PLAN ***] truthful downstream copy
  |   +-- naturals in C; F# in G; Bb in F
  |   +-- F#-not-Gb in D major (spec case)              [+] Live vertical slice [->E2E]
  |   +-- chromatic asc/desc melodic rule                 +-- [PLAN ***] real phrase -> truthful
  |   +-- chord third-stacking preference                       insufficient_notes unknown key,
  |   +-- close margin -> close_alternative                     D/G/A resolved; C/E/F/B unknown,
  |   +-- unknown-key selective resolve (D4)                    then C-major override re-spells
  |   +-- staff/voice-unknown note still spelled                with key_source=override
  |   +-- octave boundary B#/Cb arithmetic                      (locked assertion contract)
  |   +-- MIDI round-trip property (all fixtures)         +-- [PLAN ***] resolved-key leg:
  |                                                             >=8-note clear-key phrase ->
  |                                                             estimated key card + resolved
  |                                                             spellings (review: Codex #11)
  |   +-- stream total order incl. unknown slots
  |   +-- input-order invariance / determinism
  +-- errors: notes_required, incomplete_voice_state

[+] services/spelling.py
  +-- missing/failed voice run -> 409
  +-- incomplete voice tri-state -> 409
  +-- matching fingerprint -> validated reuse
  +-- malformed stored JSON / broken invariants -> recompute
  +-- override participates in fingerprint (per-override reuse)
  +-- blank request after override -> recompute, key_source back to estimated
  +-- voice run changes mid-run -> CAS conflict
  +-- success commit failure -> prior state preserved
  +-- failure audit commit failure -> logged

[+] invalidation cascade + concurrency
  +-- re-voices clears spelling + key; voice reuse preserves
  +-- re-interpretation cascades voices AND spelling atomically
  +-- re-quantization cascades interpretation, voices, AND spelling
  +-- interleaving: spelling commit vs upstream commit, both orders,
        against voice, interpretation, and quantization; no lost increments

[+] migration/schema/API
  +-- four-state key check incl. pointer coupling; tri-state spelling check
  +-- step/alter/octave/score bounds; revision bound
  +-- complete response/provenance shape
  +-- new pitch_spelling capability registration truthfulness
```

Legend: `***` behavior + edge + error coverage planned; `[->E2E]` live integration boundary.

## Test files

- `backend/tests/test_symbolic_spelling.py`
  - deterministic key fixtures: clear major, clear minor, duration-weighting decisive,
    insufficient notes, C-vs-Am ambiguity, margin attainability, tie-break stability,
    canonical tonic naming (Db-over-C#, B-over-Cb, G#-over-Ab minor, Bb-over-A# minor, and
    the flat-breaking six-accidental ties Gb major and Eb minor), degenerate-evidence gates
    (single repeated pitch, uniform and near-uniform histograms, exactly-at-boundary note and
    distinct-class counts), explicit Pearson-span confidence, override adoption and validation;
  - deterministic spelling fixtures: diatonic keys, the D-major F# spec case, ascending and
    descending chromatic lines, chord third-stacking, close margins, singleton confidence,
    unknown-key selective resolve, D4 per-key close/tie rejection and worst-case confidence,
    unresolved staff/voice notes, B#/Cb octave boundaries including the MIDI 0
    (B#-2) and MIDI 127 (G9) extremes, the stream total-order
    fixture (unknown staff/voice slots), input-order invariance, and the universal round-trip
    property: every spelled note in every fixture maps (step, alter, octave) back to exactly
    its input MIDI pitch;
  - hand-authored public-domain ground-truth excerpts (review: Codex #10): short real-music
    phrases with known keys and known correct spellings, asserting both the estimated key
    and the full spelling — non-circular musical evidence, independent of the
    threshold-attainability fixtures.
- `backend/tests/test_spelling_persistence.py`
  - migrated-SQLite proofs of all allowed key/spelling states, every invalid combination
    including both illegal pointer/key couplings (run pointer set + key unprocessed; key
    set + pointer null), numeric bounds, and the revision bound.
- `backend/tests/test_api.py`
  - prerequisite 409s, invalid override 422, success persistence and response shape, reuse,
    per-override reuse, blank request after an override recomputes with estimation
    (`key_source` flips back to `estimated`, no reuse), recomputation after re-voice,
    new-capability registration.
- `backend/tests/test_failure_paths.py`
  - commit rollback, concurrency conflict, failed-run recording, all three cascade
    directions, and the revision-increment interleaving tests.
- `frontend/src/app/page.test.tsx`
  - action gating, pending state, success key card, unknown-key selector emphasis, override
    submit, override-after-resolved-estimate, clearing the selector back to auto-detect,
    API recovery, disabled resubmit.
- `frontend/e2e/vertical-slice.spec.ts`
  - extend the real generated-phrase flow through spelling with the locked unknown-key +
    override assertion contract, plus a resolved-key leg (review: Codex #11): a >=8-note
    clear-key phrase that asserts an automatically estimated key card and resolved
    spellings — live proof of the primary feature, not only the recovery path.

No LLM evaluation suite applies.

## Evaluation

`docs/evaluation.md` gains a key/spelling section: tracked fixture counts (unknown-key rate,
spelling unknown rate per reason, chord/melodic rule application counts) over the
deterministic corpus, plus the hand-authored ground-truth excerpt results. Note-level
spelling-accuracy benchmarks at corpus scale are deferred until a license-reviewed corpus
with trustworthy spellings exists; confidences are documented as uncalibrated until then.
Documented input-quality caveat (review: Codex #4): this stage consumes raw transcription
output, and Basic Pitch fragmentation or duplicate notes can distort the duration-weighted
histogram and the evidence gates; the effect is tracked in evaluation and revisited when
the cleaned-MIDI boundary exists upstream. Research references recorded in `docs/research-notes.md`:
Krumhansl-Schmuckler profiles and Temperley's reconsideration ("What's Key for Key?"),
Meredith's ps13 and the comparative pitch-spelling studies, and the engraving-oriented joint
key/spelling estimation line of work as the future modulation-aware reference. Recorded as
operational contracts, not musical-accuracy claims.

## Failure modes

| Failure | Handling | Test | User result |
|---|---|---|---|
| No current voice run | Structured 409 | API | Separate voices first |
| Partially processed voice state | Structured 409 | API | Re-run voices |
| Invalid key override | Structured 422 | API | Corrected selector input |
| Too few notes for key | Successful `insufficient_notes` unknown | Pure + UI | Reason + selector shown |
| Too few distinct pitch classes | Successful `insufficient_notes` unknown, no correlation | Pure + UI | Reason + selector shown |
| Uniform (zero-variance) histogram | Successful `ambiguous_key` unknown, never a math error | Pure | Reason + selector shown |
| Split key evidence | Successful `ambiguous_key` unknown | Pure + UI | Reason + selector shown |
| Spelling depends on contested key | Successful `unknown_key` unknown | Pure + UI | Reason shown |
| Candidates within margin | Successful `close_alternative` unknown | Pure + UI | Reason shown |
| Voice state changes mid-run | CAS conflict + rollback | Failure path | Retry latest result |
| Concurrent spelling/upstream commits | SQL-relative increments + CAS; loser conflicts | Interleaving | Retry latest result |
| Success commit fails | Rollback | Failure path | Prior spelling state retained |
| Failure audit commit fails | Log after rollback | Failure path | Original error retained |
| Frontend request fails | Alert + enabled retry | Component | User can retry |

No planned path has a silent failure without both handling and a test.

## Performance

- One ordered note query; one success transaction; no N+1 access.
- The histogram is O(n); spelling is one ordered pass with at most two candidates per note.
  No combinatorial search exists, so no work-budget rejection is needed.
- Only the histogram, stream cursors, and decided spellings are held in memory.
- No file, ML, subprocess, or notation-library work occurs in this stage.

## Implementation Tasks

Documentation is part of every task's definition of done: each task updates the docs its
change invalidates in the same commit, per repository process. T6 is a final consistency
sweep, not the documentation step.

- [x] **T1 (P1)** — pure engine — implement key detection, contextual spelling, D4 selective
  resolve, diagnostics, and the full deterministic fixture suite, including the
  margin-attainability regressions. The module docstring carries the processing-flow ASCII
  diagram (histogram -> correlation -> gates -> stream-ordered spelling), per repository
  diagram practice.
  - Files: `backend/app/symbolic/`, `backend/tests/test_symbolic_spelling.py`
  - Verified: 32 focused tests pass with 100% module coverage; the full backend suite passes 148 tests.
- [x] **T2 (P1)** — persistence — add key/spelling fields, ownership/revision, and checked
  migration `20260719_0008` with the enumerated four-state key and tri-state spelling checks.
  - Files: `backend/app/models/`, `backend/alembic/versions/`,
    `backend/tests/test_spelling_persistence.py`
  - Verified: fresh `alembic upgrade head` and `alembic check`; 27 focused persistence tests;
    full backend gate at 175 tests.
- [x] **T3 (P1)** — backend boundary — spelling service on stage_runner, key-override
  validation, a single shared spelling-clear helper consumed by the cascade extensions in
  quantization/interpretation/voice services, interleaving tests, schemas, route, capability
  registration, full API/failure coverage.
  - Files: `backend/app/services/`, `backend/app/api/`, `backend/app/schemas/`, `backend/tests/`
  - Verified: Ruff, formatting, strict mypy across 40 application sources, and all 194 backend
    tests.
- [ ] **T4 (P2)** — frontend — spell action, key card, unknown-key selector with override
  resubmit, spelling preview columns, truthful copy, and component tests.
  - Files: `frontend/src/`
  - Verify: `npm run lint && npm run typecheck && npm test`
- [ ] **T5 (P1)** — live verification — extend the real browser flow through spelling with the
  locked unknown-key + override assertion contract.
  - Files: `frontend/e2e/`
  - Verify: `npm run build && npm run test:e2e`
- [ ] **T6 (P2)** — shared context sweep — final consistency pass over configuration, READMEs,
  architecture, pipeline, data model, research, evaluation, roadmap, current task, handoff,
  and engineering log. Includes the pretty-midi audit (review finding 2): confirm it is
  genuinely unused and remove it, or document why it stays declared.
  - Files: `.env.example`, `README.md`, `backend/README.md`, `docs/`
  - Verify: `git diff --check` and stale-claim search

### Parallelization

| Step | Modules touched | Depends on |
|------|-----------------|------------|
| T1 pure engine | `backend/app/symbolic/` | — |
| T2 persistence | `backend/app/models/`, `backend/alembic/` | T1 contract |
| T3 backend boundary | `backend/app/services/`, `api/`, `schemas/` | T1, T2 |
| T4 frontend | `frontend/src/` | T3 |
| T5 e2e | `frontend/e2e/` | T4 |
| T6 docs sweep | `docs/`, READMEs | all |

Lane A: T1 → T2 (contract determines schema). Then T3 → T4 → T5 → T6 sequentially. No
independent parallel lane exists this milestone: every later task consumes the engine
contract, and T3 touches the three upstream service files for the cascade extensions.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 2 | ABSORBED | Earlier 15-finding pass absorbed; final independent pass found and closed 2 scoring blockers |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 9 issues, 0 critical gaps (2 review findings + 7 cross-model tension points, all resolved) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** Outside voice found 15 issues; accepted: context-free D4 agreement + explicit
scoring formula (#5/#8), degenerate-evidence gates (#9), float/chord_group contract (#12,
confirmed against `entities.py:190`), pointer-coupled key check (#14), evaluation honesty —
resolved-key e2e leg, ground-truth fixtures, fragmentation caveat (#11/#10/#4). Rejected by
user decision: milestone reordering / stage merge / voice-prerequisite removal (#1/#2/#3,
re-litigated settled D2 and milestone order), best-guess-with-flag unknowns (#6/#7,
re-litigated D4/D6 truthful-unknown doctrine), override durability (#13, session-local page
is documented deferred scope). Absorbed without change: O(n) workload bound (#15, consistent
with all shipped stages; input bounded at the media boundary). The final independent pass found
that observed-range normalization collapses two-candidate spelling confidence and that D4 lacked
stable-winner/confidence semantics. Both were locked before T1 as the fixed 12-unit scale plus
unique above-margin cross-key agreement with worst-case support.

**CROSS-MODEL:** Both models agree the stage pattern, cascade design, and typed-unknown
persistence are sound. Disagreement was strategic (build order, unknown semantics) and was
resolved by the user in favor of the settled decisions.

**VERDICT:** ENG CLEARED — T1-T3 complete; ready to implement (T4 → T6). Canonical tonic naming, D4
context-free agreement, chord_group/float contract, degenerate gates, and the pointer-coupled
check are locked into the plan above.

NO UNRESOLVED DECISIONS
