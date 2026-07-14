# Processing Pipeline

The current product implements project creation and secure source ingestion. Every later stage remains a separate typed boundary and must fail explicitly until implemented.

| Stage | Input | Output/artifact | Main failure modes | Status |
|---|---|---|---|---|
| Project creation | Valid title, 1-120 characters | Project row and UUID directory | Validation, database commit, directory creation | Implemented |
| Upload validation | Project ID and multipart source | Validated temporary file | Missing project, unsupported extension, empty file, byte limit, signature mismatch | Implemented |
| Upload finalization | Valid temporary file | `source-<UUID>.<ext>` and source Artifact row | Atomic rename or metadata commit failure | Implemented |
| Media inspection | Source artifact | Duration, streams, codec metadata | Missing FFprobe, undecodable input, timeout | Next milestone |
| Audio normalization | Valid media | Normalized WAV artifact | Missing FFmpeg, codec failure, disk exhaustion | Not implemented |
| Transcription | Normalized WAV | Raw typed note events | Model load/inference failure, unsupported environment | Not implemented |
| Raw MIDI | Raw note events | Raw MIDI artifact | Invalid pitch/timing, serialization failure | Not implemented |
| Symbolic cleanup | Raw timing and pitch | Tempo, beats, quantized notes, hands, voices | Ambiguous rhythm, meter, hand, or spelling | Not implemented |
| MusicXML | Clean symbolic score | Editable MusicXML | Invalid measures, voices, durations, spelling | Not implemented |
| Score rendering | MusicXML | PDF/SVG | MuseScore missing or render failure | Not implemented |
| User correction | Note events and score state | Revised symbolic score and artifacts | Invalid edits or regeneration failure | Not implemented |

## Implemented upload contract

Accepted extensions are `.mp3`, `.wav`, `.m4a`, `.mp4`, and `.mov`. The byte limit is `PIANOVA_MAX_UPLOAD_MB` and defaults to 250 MB. The service reads in 1 MiB chunks and retains up to 8 KiB for signature detection.

M4A, MP4, and MOV share ISO base media signatures, so those detected containers are compatible with each of those extensions. MP3 and WAV require their corresponding signatures.

On success, the project becomes `uploaded`, original display metadata is recorded, and a `source` Artifact points to the generated relative path. Transcription is not triggered.

## Generated artifacts

All artifact kinds are reserved in the schema: source, normalized audio, note-event JSON, raw MIDI, cleaned MIDI, MusicXML, and PDF. Only source artifacts are currently produced.

## Configuration

- `PIANOVA_WORKSPACE_DIR`: artifact root.
- `PIANOVA_MAX_UPLOAD_MB`: streaming upload limit.
- `PIANOVA_FFMPEG_PATH`, `PIANOVA_FFPROBE_PATH`, `PIANOVA_MUSESCORE_PATH`: executable overrides.
- `PIANOVA_DEPENDENCY_PROBE_TIMEOUT_SECONDS`: probe timeout, default 3 seconds.
- `PIANOVA_DATABASE_URL`: SQLite or another SQLAlchemy URL.

Related: [architecture](architecture.md), [data model](data-model.md), and the root [run guide](../README.md#run-pianova).
