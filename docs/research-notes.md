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
- voice separation using continuity and minimum-complexity objectives;
- key-aware enharmonic spelling with melodic and harmonic context.

The primary product rule is to prefer readable intent over mechanically preserving every expressive deviation.

## Datasets and evaluation sources

Candidate public research corpora include MAESTRO for aligned piano audio/MIDI and MAPS for piano transcription evaluation. Licensing, permitted redistribution, splits, and format conversion must be documented before any fixture is committed. Small synthetic WAV and symbolic fixtures are sufficient for infrastructure tests.

## Synthesia computer vision

Visual work is deferred. Later research should compare falling-note segmentation, keyboard calibration, illuminated-key detection, temporal tracking, and confidence fusion with audio evidence. Visual detections must retain their source so disagreement with audio is inspectable.

## Copyright and ethics

Pianova processes user-supplied media and does not scrape platforms. Benchmark and demo material must be owned, licensed, public domain, or otherwise authorized. Generated scores do not erase rights in the source performance or composition.

Related: [evaluation](evaluation.md), [pipeline](pipeline.md), and [architecture](architecture.md).
