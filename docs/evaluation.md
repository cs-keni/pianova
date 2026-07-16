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

No musical-accuracy baseline exists yet because the repository has no license-reviewed reference corpus. The current vertical-slice baseline is operational: 43 backend tests, five frontend component tests, a production build, and three live Playwright flows. Native Windows FFprobe/FFmpeg inspect and normalize generated WAV and MP4 fixtures; the primary audio flow also runs real Basic Pitch 0.4.0/TensorFlow 2.15 inference and verifies raw note-event JSON plus MIDI. The rejection flow blocks mismatched contents.

## Known limitations

- The generated transcription fixture proves orchestration and artifact correctness, not musical accuracy.
- Public piano datasets may not represent phone recordings, room acoustics, rubato, or modern Synthesia videos.
- A single tolerance can hide musically different errors; publish thresholds with every score.
- Readability requires human judgment alongside automated metrics.

Related: [research notes](research-notes.md), [pipeline](pipeline.md), and [roadmap](roadmap.md).
