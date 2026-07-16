# Current Task

## Active milestone

The FFprobe inspection and FFmpeg normalized-WAV milestone is implemented.

## Status

Pianova can now create a project, securely store a supported source, explicitly inspect it, persist typed container and stream metadata, and generate a retry-safe mono 22.05 kHz PCM WAV artifact. The Next.js interface displays duration, codec, channel/sample-rate, and optional video metadata. Transcription remains explicit and unstarted.

## Verified behavior

- Native Windows Python 3.11.9, FFprobe 8.0, and FFmpeg 8.0 are available in the runtime used by FastAPI.
- Ruff and strict mypy pass across 25 backend source files.
- 32 pytest tests pass using temporary Alembic-migrated SQLite databases.
- `alembic check` reports no schema drift after revision `20260716_0003`.
- ESLint and TypeScript pass.
- Five Vitest component tests pass.
- The optimized Next.js production build passes.
- Three Playwright tests pass against live FastAPI and Next.js servers. The audio and video success flows perform real FFprobe inspection and FFmpeg normalization; the rejection flow blocks mismatched contents.

## Approved decisions preserved

- FFprobe output is parsed into typed project fields and `MediaStream` rows rather than stored as an opaque JSON blob.
- Normalized audio is mono, 22.05 kHz, 16-bit PCM WAV. No loudness filter is applied, preserving dynamics for later velocity work.
- Media processing is explicit and synchronous with separate bounded FFprobe/FFmpeg timeouts.
- Generated output uses a hidden temporary file, validates non-empty output, atomically finalizes, then commits metadata and the Artifact.
- Failed attempts remove partial/finalized output, record a failed ProcessingRun when possible, and remain retryable.
- Successful repeat requests return the existing normalized Artifact instead of duplicating work.
- Basic Pitch remains an optional Python 3.11 dependency boundary and has not been installed or represented as working.

## Next milestone

Implement basic transcription and raw MIDI:

1. Run an isolated Basic Pitch 0.4.0 compatibility spike against Windows Python 3.11, TensorFlow, NumPy, and librosa.
2. Define a typed transcriber interface that consumes the normalized WAV Artifact.
3. Persist raw note events without overwriting performed timing.
4. Generate raw MIDI and retain model/version/config provenance.
5. Add model-unavailable, inference-failure, malformed-output, cleanup, retry, and live workflow coverage.

Do not begin quantization, hand assignment, MusicXML, or score rendering until the raw transcription boundary is measured and verified.

## Active blockers

None for the completed media milestone. The next milestone must resolve the optional Basic Pitch dependency stack before implementation.
