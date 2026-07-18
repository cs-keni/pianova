# Research Notes

This file records model and music-engineering questions that affect implementation. Claims must be updated when experiments replace assumptions.

## Automatic music transcription

Spotify Basic Pitch 0.4.0 is the implemented first transcriber because it produces polyphonic pitch events and MIDI without training a model. Its Python support stops at 3.11, so Pianova uses a separate `.venv-transcription` and keeps the ordinary API usable when the ML stack is absent.

The verified Windows Python 3.11 stack is Basic Pitch 0.4.0, TensorFlow 2.15.0, NumPy 1.26.4, librosa 0.11.0, pretty-midi 0.2.11, and SciPy 1.17.1. A real generated WAV completed prediction and emitted both a note event and MIDI. The API launches this environment as a subprocess and validates a versioned JSON contract, so a future transcriber can replace the worker without changing downstream raw-note persistence.

Basic Pitch 0.4.0 fails internally on extremely short audio because its analysis array is empty. Experiments showed 0.01 seconds fails while 0.05 seconds produces a valid empty result, so Pianova rejects sources shorter than 0.05 seconds before model startup. This is an operational guard, not a musical-quality claim.

The verified media input boundary now produces mono 22.05 kHz 16-bit PCM WAV. This standardizes model inputs without applying loudness normalization, preserving performance dynamics for later velocity and expression work. Revisit the sample rate only if Basic Pitch compatibility or measured accuracy requires it.

## Symbolic reconstruction

Pitch detection is not the same as readable notation. Evaluation must separate raw timing accuracy from musical interpretation. Candidate approaches include:

- beat-synchronous quantization with penalties for tiny rests, excessive ties, and unsupported tuplets;
- chord grouping within tempo-relative timing windows;
- hand assignment using pitch range, continuity, overlap, and crossing costs;
- staff-scoped notation-voice separation under explicit overlap and readability invariants;
- key-aware enharmonic spelling with melodic and harmonic context.

The primary product rule is to prefer readable intent over mechanically preserving every expressive deviation.

The implemented baseline estimates tempo from note-onset groups rather than re-reading audio. It
generates bounded candidates from nearby onset intervals, scores sixteenth-grid residual plus
rhythmic complexity and a weak 120 BPM prior, and requires absolute fit quality plus clear
separation from the runner-up and half/double-tempo alternatives. This follows the general
beat-tracking pattern of balancing local onset evidence against a tempo preference while keeping
Pianova's scoring deterministic and inspectable. Librosa's beat tracker and Ellis's dynamic
programming beat-tracking paper are reference designs, not runtime dependencies:
[librosa beat_track](https://librosa.org/doc/latest/generated/librosa.beat.beat_track.html) and
[Ellis 2007](https://www.ee.columbia.edu/~dpwe/pubs/Ellis07-beattrack.pdf).

Quantization uses exact fractions internally and a straight sixteenth grid. The current duration
vocabulary favors common straight and dotted values through a whole note; longer notes remain
grid-aligned for later measure splitting. music21's configurable stream quantizer is a useful
comparison for future tuplets and multi-divisor grids:
[music21 quantize](https://music21.org/music21docs/moduleReference/moduleStreamBase.html).

An exact 120 BPM synthetic fixture initially exposed a scoring-contract conflict: the 180 BPM
runner-up's half-beat complexity penalty equaled the required ambiguity margin. Raising that
penalty from 0.03 to 0.04 made the documented acceptance threshold attainable without weakening
ambiguity protection. The regression is locked by unit and live-boundary tests.

The first hand/staff baseline is also deterministic and operates only on quantized symbolic
evidence. For each chord group it considers every pitch-contiguous lower/upper split, then uses
bounded passage-level dynamic programming to balance pitch comfort, span, continuity, appearance,
split movement, and crossing pressure. Hand and notation staff run as independent passes. A note's
confidence comes from the cost difference between the best complete paths under its two competing
assignments; close alternatives remain explicitly unknown with one actionable reason. This is an
inspectable baseline for evaluation, not a claim that piano fingering or engraving always follows
pitch-contiguous partitions.

The first notation-voice engine is deterministic and forced-only. Exact-onset/exact-duration notes
collapse into chord nodes; incompatible interval overlaps form a per-staff conflict graph. A graph
with clique size at most two is two-colored, and the higher-mean-pitch color becomes voice 1. A
3-clique proves a third simultaneous stream without search, so a deterministic excess node becomes
`voice_capacity_exceeded` unknown while the remaining graph is colored. This replaces the reviewed
weighted-DP draft, whose state could not soundly retain sustained-note voice identity. Crossing and
small pitch separation also remain typed unknowns. The normalized separation value is an
uncalibrated decision margin until corrected voice labels exist.

## Datasets and evaluation sources

Candidate public research corpora include MAESTRO for aligned piano audio/MIDI and MAPS for piano transcription evaluation. Licensing, permitted redistribution, splits, and format conversion must be documented before any fixture is committed. Small synthetic WAV and symbolic fixtures are sufficient for infrastructure tests.

## Synthesia computer vision

Visual work is deferred. Later research should compare falling-note segmentation, keyboard calibration, illuminated-key detection, temporal tracking, and confidence fusion with audio evidence. Visual detections must retain their source so disagreement with audio is inspectable.

## Copyright and ethics

Pianova processes user-supplied media and does not scrape platforms. Benchmark and demo material must be owned, licensed, public domain, or otherwise authorized. Generated scores do not erase rights in the source performance or composition.

Related: [evaluation](evaluation.md), [pipeline](pipeline.md), and [architecture](architecture.md).
