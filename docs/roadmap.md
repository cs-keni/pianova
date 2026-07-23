# Roadmap

Pianova is built as verified vertical slices. A milestone is complete only when behavior, failure paths, tests, and documentation agree.

1. **Repository scaffold: complete.** Pinned runtime boundary, dependency manifests, shared docs, Next.js, FastAPI, and local workspace rules.
2. **Project and secure upload: complete.** Migrated SQLite models, capabilities, project creation, signature validation, atomic storage, component tests, and live browser coverage.
3. **Media inspection and normalized WAV: complete.** FFprobe metadata, duration and stream display, FFmpeg extraction/normalization, artifact records, retries, cleanup, and live browser coverage.
4. **Basic transcription: complete.** Isolated Basic Pitch/TensorFlow worker, dependency-backed capability, typed raw note events, model/config provenance, note-event JSON, raw MIDI, retry-safe cleanup, and live browser coverage.
5. **Tempo and readable quantization: complete.** Conservative global tempo estimation, BPM recovery, simple meter, explicit measure origin, chord grouping, exact-fraction straight-note quantization, diagnostics, concurrency-safe persistence, and live Basic Pitch coverage.
6. **Hands and staves: complete.** Independent passage-level assignment, competing-path confidence, explicit unknown reasons, concurrency-safe persistence/invalidation, bounded preview, and real browser coverage.
7. **Voice separation: complete.** Shared orchestration, the deterministic per-staff
   conflict-graph engine, checked persistence, API/service, hardened reuse, concurrency-safe
   cascade invalidation, UI, live browser coverage, and documentation are complete.
8. **Key-aware spelling: in progress (T3/6 complete).** The pure engine, checked persistence,
   service/API, hardened reuse, all upstream invalidation cascades, and both-order concurrency
   coverage are complete. Frontend and live verification remain T4-T6.
9. **MusicXML and optional rendering.** Editable MusicXML first; MuseScore PDF/SVG degrades independently.
10. **Inspection and correction.** Note table, piano roll, synchronized playback, edits, and artifact regeneration.
11. **Evaluation.** Reproducible benchmark corpus, transcription metrics, notation-readability review, and regression reports.
12. **Synthesia extraction.** Visual note detection only after the audio pipeline is stable.
13. **Audio-video fusion.** Confidence-aware multimodal note evidence and conflict resolution.
14. **Model improvements.** Custom training or fine-tuning only when measured failure modes justify it.

Cloud deployment, authentication, payments, mobile apps, distributed queues, and collaborative editing remain outside the local-first MVP.

See the executable [implementation plan](IMPLEMENTATION_PLAN.md), [pipeline](pipeline.md), and [evaluation plan](evaluation.md).
