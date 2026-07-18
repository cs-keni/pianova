# Evaluation Plan

Pianova needs two kinds of evidence: signal-level transcription accuracy and score-level usefulness. A model can score well on note timing while producing unreadable notation.

## Ground truth

Each evaluation item should retain:

- authorized source audio;
- aligned reference MIDI or note-event JSON;
- reference tempo, meter, key, beats, hands, voices, and MusicXML when available;
- provenance, license, split, instrument/rendering conditions, and expected limitations.

Infrastructure tests use generated fixtures. Model benchmarks and musical-quality studies must remain separate so fast CI does not download weights or datasets.

## Metrics

### Raw transcription

- note onset precision, recall, and F1 at documented tolerances;
- onset-plus-offset metrics;
- frame-level precision, recall, and F1 when the model exposes frames;
- velocity error and pitch-class/confusion summaries;
- inference time and peak memory.

### Symbolic reconstruction

- beat/tempo and downbeat accuracy;
- duration and onset error on the inferred beat grid;
- meter, key, hand, staff, voice, and spelling accuracy;
- invalid or incomplete measure count;
- counts of short rests, ties, tuplets, and voice collisions.

### Product outcome

- minutes of human correction per minute of source;
- number and type of edits before an acceptable score;
- blinded readability ratings from pianists;
- artifact-generation success rate and end-to-end latency.

## Benchmark procedure

1. Pin the code revision, model version, dependency environment, and configuration.
2. Select a fixed, license-reviewed dataset split that excludes training material.
3. Run each independent pipeline stage and retain intermediate artifacts.
4. Compute raw and symbolic metrics with fixed tolerances.
5. Record failures instead of silently dropping difficult files.
6. Compare with the previous accepted baseline and investigate regressions.
7. For notation changes, perform a blinded musical-readability review on a stable sample.

## Current baseline

No broad musical-accuracy baseline exists yet because the repository has no license-reviewed
reference corpus. The current quantization baseline is deterministic and operational: pure tests
cover chord grouping, exact 120 BPM acceptance, ambiguity, overrides, pickups, duration ordering,
same-pitch repair, and dense-rhythm rejection; API tests cover persistence, reuse/recompute,
validation, rollback, and optimistic-concurrency failure.

The hand/staff baseline has deterministic fixtures for obvious two-hand passages, ambiguity,
wide chords, crossing pressure, independent cross-staff placement, input-order stability, and the
transition-work bound. API and failure tests cover ownership, provenance, reuse repair, atomic
re-quantization invalidation, commit rollback, and concurrency conflicts. No broad hand/staff
accuracy score is reported until a license-reviewed corpus includes trustworthy assignment labels.

The pure voice baseline has deterministic fixtures for monophonic and uniform-chord one-voice
behavior, sustained notes over moving lines in both staves, suspension chains, forced voices from
unequal durations, three-stream capacity, unresolved staff, crossing, close separation, and input
reordering. Every resolved fixture checks the invariant that overlapping notes in one
`(staff, voice)` share exact onset and duration. Tracked fixture counts are unknown notes,
two-voice components, capacity-exceeded notes, and crossing components. These fixtures prove the
contract, not note-level musical voice accuracy; decision scores remain uncalibrated.

The live generated phrase contains five distinct tones at 120 BPM. Native Windows FFprobe/FFmpeg
normalize it, Basic Pitch 0.4.0/TensorFlow 2.15 emits real note events, and the onset estimator must
accept an automatic tempo within 119.5-120.5 BPM before the UI displays symbolic timing and runs
hand/staff interpretation. This proves the real transcription-to-interpretation boundary, not
general piano accuracy.

## Known limitations

- The generated transcription fixture proves orchestration and artifact correctness, not musical accuracy.
- One global straight-grid fixture does not evaluate rubato, swing, tuplets, ornamentation, compound meter, or downbeat inference.
- The deterministic hand/staff fixture proves bounded orchestration and uncertainty display, not real-world assignment accuracy or voice structure.
- The deterministic voice fixtures prove conflict handling and stable uncertainty, not contrapuntal identity or engraver preference.
- Public piano datasets may not represent phone recordings, room acoustics, rubato, or modern Synthesia videos.
- A single tolerance can hide musically different errors; publish thresholds with every score.
- Readability requires human judgment alongside automated metrics.

Related: [research notes](research-notes.md), [pipeline](pipeline.md), and [roadmap](roadmap.md).
