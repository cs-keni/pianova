# Roadmap

Pianova is built as verified vertical slices. A milestone is complete only when behavior, failure paths, tests, and documentation agree.

1. **Repository scaffold: complete.** Pinned runtime boundary, dependency manifests, shared docs, Next.js, FastAPI, and local workspace rules.
2. **Project and secure upload: complete.** Migrated SQLite models, capabilities, project creation, signature validation, atomic storage, component tests, and live browser coverage.
3. **Media inspection and normalized WAV: complete.** FFprobe metadata, duration and stream display, FFmpeg extraction/normalization, artifact records, retries, cleanup, and live browser coverage.
4. **Basic transcription.** Optional Basic Pitch integration behind a transcriber interface, typed note-event output, and raw MIDI.
5. **Tempo and readable quantization.** Beat grid, meter, chord grouping, simpler rhythm preference, and evaluation fixtures.
6. **Hands, staves, voices, and spelling.** Initial heuristics with user-visible uncertainty and deterministic tests.
7. **MusicXML and optional rendering.** Editable MusicXML first; MuseScore PDF/SVG degrades independently.
8. **Inspection and correction.** Note table, piano roll, synchronized playback, edits, and artifact regeneration.
9. **Evaluation.** Reproducible benchmark corpus, transcription metrics, notation-readability review, and regression reports.
10. **Synthesia extraction.** Visual note detection only after the audio pipeline is stable.
11. **Audio-video fusion.** Confidence-aware multimodal note evidence and conflict resolution.
12. **Model improvements.** Custom training or fine-tuning only when measured failure modes justify it.

Cloud deployment, authentication, payments, mobile apps, distributed queues, and collaborative editing remain outside the local-first MVP.

See the executable [implementation plan](IMPLEMENTATION_PLAN.md), [pipeline](pipeline.md), and [evaluation plan](evaluation.md).
