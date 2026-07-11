I want you to help me design and implement a local-first application called **Pianova**.

Pianova is an AI-assisted piano transcription platform that transforms piano audio and video performances into readable, editable sheet music.

The user uploads a piano-only audio or video file, such as MP3, WAV, M4A, MP4, or MOV. The application analyzes the piano performance, identifies the notes being played, and generates musically readable sheet music.

The input will primarily contain solo piano. Some videos may also contain Synthesia-style falling notes, an on-screen keyboard, illuminated keys, or other visual representations of the notes being played.

The application should eventually support both ordinary piano recordings and videos containing visual note information.

## Core product goal

The complete long-term workflow is:

1. Accept a piano audio or video file.
2. Extract and normalize its audio.
3. Transcribe the piano performance into note events.
4. Convert the raw transcription into clean MIDI.
5. Infer tempo, beats, measures, meter, key signature, rhythms, hand assignments, voices, and pitch spelling.
6. Generate editable MusicXML.
7. Render printable sheet music as PDF.
8. Allow the user to inspect and correct the transcription.
9. Regenerate the sheet music after corrections.
10. Eventually use both audio analysis and computer vision when Synthesia-style visuals are available.

This should be treated as a serious software engineering and AI/ML portfolio project, not as a shallow wrapper around an existing model or API.

## Product description

**Pianova turns piano performances into readable sheet music.**

Suggested tagline:

> Hear it. See it. Play it.

An alternative technical description:

> Pianova is an AI-assisted piano transcription platform that converts piano audio and video into editable MIDI, MusicXML, and sheet music.

## Product philosophy

Existing audio-to-MIDI tools may identify many of the correct pitches but frequently generate poor sheet music.

A literal transcription of a human performance can produce:

- Extremely short rests
- Excessive ties
- Incorrect tuplets
- Awkward note durations
- Misaligned chords
- Poor hand assignments
- Incorrect enharmonic spelling
- Unreadable voice separation
- Measures that do not reflect the intended musical rhythm

Pianova should distinguish between:

1. The exact timing of the recorded performance
2. The likely musical notation intended by the pianist

Expressive timing, rubato, and slight human timing differences should not automatically produce unnecessarily complicated notation.

When multiple symbolic interpretations are possible, Pianova should generally prefer the simpler, more musically readable interpretation.

The initial version does not need to be flawless. A human-in-the-loop correction workflow is expected and encouraged.

A major product goal is to reduce how much time a pianist must spend manually transcribing or correcting a performance.

## Initial MVP

Build the first version as a local-first web application.

Use the following initial architecture unless there is a strong technical reason to change it:

- Frontend: Next.js with TypeScript
- Backend: Python with FastAPI
- Database: SQLite
- ORM: SQLAlchemy or SQLModel
- Validation: Pydantic
- Audio and video processing: FFmpeg
- MIDI processing: pretty_midi and/or mido
- Music notation processing: music21
- Initial transcription model: Spotify Basic Pitch or another practical pretrained transcription model
- Score format: MusicXML
- Score rendering: MuseScore CLI when available
- Local filesystem storage for uploads and generated artifacts
- Testing: pytest for Python and an appropriate frontend testing tool
- Package management: choose stable, commonly used tools and document the choice

The application should run locally on the user's computer.

Do not require:

- Cloud hosting
- User accounts
- Authentication
- Payments
- External databases
- Paid APIs
- Proprietary cloud services

Do not train a neural network from scratch for the MVP.

Use an existing pretrained transcription model first. The original engineering work should focus on the complete processing pipeline, musical cleanup, notation reconstruction, editing workflow, testing, and evaluation.

## Target environment

Assume the primary development environment is:

- Windows
- VS Code or Codex
- Python 3
- Node.js
- Git
- GitHub
- A local browser

Avoid unnecessary operating-system-specific code.

Use configuration values for executable locations such as:

- FFmpeg
- FFprobe
- MuseScore

Support automatic executable discovery when practical, but allow users to configure explicit paths.

## MVP workflow

The first working application should support this flow:

1. The user opens the local Pianova web application.
2. The user creates a project.
3. The user uploads an MP3, WAV, M4A, MP4, or MOV file.
4. The application validates the file.
5. The application displays the file name, media type, file size, and duration.
6. FFmpeg extracts audio from video files.
7. FFmpeg converts the input into a normalized WAV format.
8. A pretrained piano transcription model processes the WAV file.
9. The model output is converted into structured note events.
10. The application generates a raw MIDI file.
11. Basic tempo and beat estimation are performed.
12. Basic rhythm quantization is applied.
13. Notes are assigned to left or right hand using initial heuristics.
14. Notes are placed onto treble and bass staves.
15. MusicXML is generated.
16. The score is rendered or previewed.
17. The user can download the raw MIDI, cleaned MIDI, MusicXML, note-event JSON, and PDF.
18. The user can inspect detected notes.
19. The user can make basic corrections.
20. The user can regenerate the score after corrections.

## Scope priority

Prioritize this exact pipeline first:

```text
Upload piano audio or video
→ validate input
→ extract normalized WAV
→ transcribe audio into note events
→ create raw MIDI
→ estimate tempo and beats
→ perform basic quantization
→ assign hands and staves
→ create cleaned MIDI
→ generate MusicXML
→ render or export sheet music
```

Do not begin with the following:

- Training a custom neural network
- Full Synthesia computer vision
- Cloud deployment
- Authentication
- Social features
- Mobile applications
- Collaborative score editing
- Advanced score engraving
- Automatic fingering
- Automatic dynamics and articulation generation
- Microservice architecture
- Kubernetes
- Distributed task queues
- Premature optimization

Build a vertical slice that works from upload to generated MusicXML before adding advanced features.

## Architecture requirements

Separate the processing pipeline into independent, testable stages.

Suggested stages:

- File validation
- Media inspection
- Audio extraction
- Audio normalization
- Audio transcription
- Note-event parsing
- Note-event normalization
- MIDI generation
- Tempo estimation
- Beat-grid generation
- Meter inference
- Rhythm quantization
- Chord grouping
- Hand separation
- Staff assignment
- Voice separation
- Key detection
- Enharmonic spelling
- MusicXML generation
- Score rendering
- Evaluation
- User correction
- Artifact management

Each stage should:

- Accept a documented input structure
- Produce a documented output structure
- Log its start and completion
- Report meaningful errors
- Be independently testable
- Avoid directly depending on frontend code
- Avoid hidden global state

Do not create one large function that performs the entire pipeline.

Use typed schemas or domain models for data passed between stages.

## Domain models

Create clear domain models for musical data.

A note-event model may resemble:

```python
from dataclasses import dataclass
from enum import Enum


class Hand(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


class DetectionSource(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    AUDIO_AND_VIDEO = "audio_and_video"
    MANUAL = "manual"


@dataclass
class NoteEvent:
    pitch: int
    onset_seconds: float
    offset_seconds: float
    velocity: int
    confidence: float | None = None
    hand: Hand = Hand.UNKNOWN
    voice: int | None = None
    source: DetectionSource = DetectionSource.AUDIO
```

This is an example rather than a mandatory implementation.

The final model should eventually support:

- Unique note ID
- MIDI pitch
- Pitch name
- Onset in seconds
- Offset in seconds
- Duration in seconds
- Velocity
- Overall confidence
- Audio confidence
- Visual confidence
- Detection source
- Hand assignment
- Staff assignment
- Voice assignment
- Measure number
- Beat position
- Quantized onset
- Quantized duration
- Tie information
- Chord group
- Manually edited flag
- Deleted flag
- Conflict status
- Creation timestamp
- Update timestamp

Keep raw performance timing separate from quantized symbolic timing.

Do not overwrite the original transcription when quantization is performed.

## Data persistence

Use SQLite for the local application.

At minimum, support the following entities.

### Project

Fields should include:

- ID
- Title
- Original filename
- Sanitized filename
- Input file path
- Input media type
- File size
- Duration
- Processing status
- Current pipeline stage
- Progress percentage if available
- Error message
- Detected tempo
- Time signature
- Key signature
- Created timestamp
- Updated timestamp

### NoteEvent

Fields should include:

- ID
- Project ID
- MIDI pitch
- Raw onset time
- Raw offset time
- Velocity
- Confidence
- Audio confidence
- Visual confidence
- Detection source
- Assigned hand
- Assigned staff
- Assigned voice
- Measure number
- Beat position
- Quantized onset
- Quantized duration
- Manually edited flag
- Deleted flag

### Artifact

Fields should include:

- ID
- Project ID
- Artifact type
- File path
- File size
- Created timestamp

Artifact types may include:

- Original upload
- Extracted audio
- Normalized WAV
- Raw note-event JSON
- Raw MIDI
- Cleaned note-event JSON
- Cleaned MIDI
- MusicXML
- PDF
- SVG score preview
- Processing log

### ProcessingRun

Consider creating a ProcessingRun entity containing:

- ID
- Project ID
- Start timestamp
- End timestamp
- Status
- Current stage
- Pipeline version
- Configuration JSON
- Error details

This will allow the same project to be reprocessed using different settings later.

## Processing states

Use explicit processing states.

Possible states include:

```text
created
uploaded
validating
inspecting_media
extracting_audio
normalizing_audio
transcribing
parsing_notes
estimating_tempo
quantizing
separating_hands
generating_midi
generating_musicxml
rendering_score
completed
failed
cancelled
```

Persist the current state in SQLite.

Every failed job should include a useful error message rather than silently failing.

## Suggested repository structure

Use a clean monorepo structure similar to:

```text
pianova/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   │   ├── projects/
│   │   ├── upload/
│   │   ├── processing/
│   │   ├── piano-roll/
│   │   └── score/
│   ├── lib/
│   ├── hooks/
│   ├── types/
│   ├── public/
│   ├── tests/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── dependencies/
│   │   ├── core/
│   │   ├── database/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   └── pipeline/
│   │       ├── audio/
│   │       ├── transcription/
│   │       ├── midi/
│   │       ├── tempo/
│   │       ├── quantization/
│   │       ├── hand_separation/
│   │       ├── voice_separation/
│   │       ├── harmony/
│   │       ├── notation/
│   │       ├── rendering/
│   │       └── evaluation/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   ├── scripts/
│   ├── pyproject.toml
│   └── README.md
├── workspace/
│   ├── projects/
│   └── .gitkeep
├── docs/
│   ├── architecture.md
│   ├── pipeline.md
│   ├── roadmap.md
│   ├── research-notes.md
│   ├── data-model.md
│   └── evaluation.md
├── scripts/
├── samples/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── LICENSE
└── README.md
```

Adjust the exact structure if needed, but keep the following clearly separated:

- Frontend
- Backend
- Pipeline stages
- Domain models
- Database access
- Generated workspace files
- Tests
- Documentation
- Sample files

Do not commit uploaded media, generated music, large model files, database files, temporary files, or private user data.

## Backend API

Design a REST API similar to the following.

### Health and configuration

```text
GET /api/health
GET /api/config
GET /api/dependencies
```

The dependency endpoint should report whether required local executables are available, including:

- FFmpeg
- FFprobe
- MuseScore
- Transcription model dependencies

Do not expose private environment variables.

### Projects

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
```

### Upload and processing

```text
POST /api/projects/{project_id}/upload
POST /api/projects/{project_id}/process
POST /api/projects/{project_id}/reprocess
GET  /api/projects/{project_id}/status
```

### Notes

```text
GET    /api/projects/{project_id}/notes
PATCH  /api/projects/{project_id}/notes/{note_id}
POST   /api/projects/{project_id}/notes
DELETE /api/projects/{project_id}/notes/{note_id}
POST   /api/projects/{project_id}/notes/batch
```

### Artifacts

```text
GET /api/projects/{project_id}/artifacts
GET /api/projects/{project_id}/artifacts/{artifact_id}
```

### Score generation

```text
POST /api/projects/{project_id}/generate-midi
POST /api/projects/{project_id}/generate-score
```

The exact endpoint design may be adjusted if a cleaner API is justified.

Use structured error responses.

## File handling and security

Even though Pianova is local-first, handle files safely.

Requirements:

- Validate file extensions and MIME types.
- Set a configurable maximum upload size.
- Sanitize uploaded filenames.
- Store files under generated project IDs.
- Prevent directory traversal.
- Never use user-provided text directly in shell commands.
- Invoke subprocesses using argument arrays.
- Do not use `shell=True`.
- Capture stdout and stderr.
- Add subprocess timeouts where appropriate.
- Return useful errors when FFmpeg or MuseScore is missing.
- Do not overwrite unrelated files.
- Use generated filenames for internal artifacts.
- Keep original uploads unchanged.
- Avoid loading entire large media files into memory.
- Clean up abandoned temporary files.
- Do not trust metadata supplied by the client.

## Audio preprocessing

Use FFprobe to inspect input files.

Extract useful metadata:

- Duration
- Codec
- Sample rate
- Channel count
- Bit rate
- Container type

Normalize inputs to a consistent WAV format suitable for the selected transcription model.

Choose reasonable defaults based on the model requirements.

Potential normalization operations include:

- Extracting audio from video
- Converting to WAV
- Resampling
- Converting to mono if required
- Normalizing amplitude carefully
- Avoiding destructive clipping

Document the exact FFmpeg command and why the chosen settings are appropriate.

Preserve the original media file.

## Audio transcription

Begin with a practical pretrained model such as Basic Pitch.

Wrap the model behind a transcription interface.

Example:

```python
from typing import Protocol


class PianoTranscriber(Protocol):
    def transcribe(self, audio_path: str) -> list[NoteEvent]:
        ...
```

The rest of the application should not depend directly on Basic Pitch-specific APIs.

This allows another model to be substituted later.

Possible future transcription implementations may include:

- Basic Pitch
- Onsets and Frames
- Piano-specific transformer models
- Custom fine-tuned models
- Ensemble transcription

Store model information with each processing run:

- Model name
- Model version
- Configuration
- Processing duration

Do not represent placeholder transcription as completed functionality.

When a real model is not yet connected, return an explicit “not implemented” error or provide a clearly labeled development fixture.

## MIDI generation

Generate at least two MIDI artifacts:

1. Raw MIDI representing the direct transcription
2. Cleaned MIDI representing quantized and corrected note events

Preserve:

- Pitch
- Onset
- Offset
- Velocity
- Tempo when known

Where possible, preserve sustain pedal events separately rather than converting all sustained audio into long note durations.

Keep MIDI generation isolated from notation generation.

## Tempo and beat estimation

Create a tempo and beat module.

The MVP may begin with:

- Model-provided tempo
- MIDI onset analysis
- Beat tracking from an audio library
- A user-specified tempo override

Store both:

- Raw estimated tempo
- User-confirmed tempo

Support an initial single-tempo assumption, but design the data model so later versions can support tempo changes and rubato.

Do not assume every note onset falls exactly on a metronomic beat.

The long-term system should create a flexible beat grid representing the intended musical pulse.

## Rhythm quantization

Implement a basic but isolated rhythm quantization system.

Initially support:

- Whole notes
- Half notes
- Quarter notes
- Eighth notes
- Sixteenth notes
- Dotted half notes
- Dotted quarter notes
- Dotted eighth notes
- Basic triplets when feasible

Use configurable quantization settings.

Possible settings:

- Minimum note value
- Triplets enabled
- Quantization strength
- Chord onset tolerance
- Rest simplification tolerance
- Tie simplification tolerance

Do not blindly round every note independently to the nearest grid position.

At minimum:

- Group nearly simultaneous notes into chords.
- Avoid creating tiny rests between notes that are likely connected.
- Avoid creating tiny differences between chord-note onsets.
- Preserve note ordering.
- Prevent negative or zero durations.
- Prefer simpler rhythms when timing differences are small.
- Avoid excessive tuplets.
- Avoid unnecessary ties.
- Respect measure boundaries.

Design the quantizer so it can later be replaced by:

- Dynamic programming
- Beam search
- Probabilistic sequence decoding
- A learned symbolic correction model

A future scoring function may include:

```text
quantization_score =
    timing_error
    + rhythm_complexity_penalty
    + tiny_rest_penalty
    + excessive_tie_penalty
    + chord_misalignment_penalty
    + unusual_tuplet_penalty
    + voice_crossing_penalty
```

Do not implement a fake advanced optimizer. Start with a tested, understandable baseline.

## Hand separation

For the MVP, create a modular heuristic hand-separation system.

Do not simply assign every note below middle C to the left hand and every note above middle C to the right hand.

Use a combination of:

- Pitch
- Register
- Distance from the previous note assigned to each hand
- Chord grouping
- Temporal continuity
- Typical piano hand spans
- Bass-line continuity
- Melody continuity
- Hand crossing penalties
- Large leap penalties
- Simultaneous-note distribution

Support an “unknown” assignment when confidence is low.

Expose hand assignments in the editor so the user can correct them.

Create an interface that can later be replaced by:

- Dynamic programming
- Graph optimization
- Sequence classification
- A custom machine-learning model

Add test fixtures covering:

- Simple melody and bass
- Broken chords
- Wide arpeggios
- Crossing hands
- Chords around middle C
- Notes spanning both staves

## Staff assignment

Hand assignment and staff assignment should be related but not treated as perfectly identical.

For the first version, they may be closely linked.

Later versions should support:

- Right-hand notes temporarily written on the bass staff
- Left-hand notes temporarily written on the treble staff
- Cross-staff notation
- Voice-specific staff placement

Avoid embedding the assumption that “right hand always means treble staff” too deeply in the domain model.

## Voice separation

Implement only a basic voice-separation baseline in the MVP.

Start with:

- One voice per staff by default
- Detection of overlapping notes that require an additional voice
- Sustained melody notes over moving accompaniment when practical

Keep the system modular.

Do not attempt perfect contrapuntal voice separation initially.

The data model should support multiple voices per staff later.

## Key detection and pitch spelling

Create a basic key-estimation module.

Possible inputs include:

- Pitch-class distribution
- Duration-weighted pitch classes
- Chord context
- Existing music21 key analysis

Keep the estimated key editable by the user.

Use the key and local harmonic context to improve enharmonic spelling.

Avoid obviously poor spellings, such as representing an F-sharp in a D-major chord as G-flat without a musical reason.

Do not mutate the underlying MIDI pitch when changing the written pitch spelling.

Store symbolic spelling separately where needed.

## Time-signature inference

For the MVP:

- Default to 4/4 when inference is uncertain.
- Allow the user to select a time signature.
- Support common meters such as 4/4, 3/4, 2/4, 6/8, and 12/8.
- Keep the meter logic isolated.

Do not claim automatic meter inference is reliable until it has been properly implemented and evaluated.

## MusicXML generation

Generate standards-compliant MusicXML.

The generated score should include, where available:

- Title
- Composer or source metadata
- Tempo
- Time signature
- Key signature
- Treble and bass staves
- Measures
- Notes
- Chords
- Rests
- Voices
- Ties
- Beams
- Accidentals
- Basic pedal markings when available

Use music21 or another appropriate library.

Do not build a custom score renderer.

Ensure the generated MusicXML can be opened in MuseScore.

Add an integration test using a small synthetic note sequence.

## Score rendering

Use MuseScore CLI when it is installed.

Support conversion from MusicXML to:

- PDF
- SVG or PNG preview if practical
- MuseScore-native format if useful

The application should still provide MusicXML if MuseScore is not installed.

A missing MuseScore executable should not cause the entire transcription pipeline to fail.

Instead:

- Mark MusicXML generation as successful.
- Mark PDF rendering as unavailable or failed.
- Provide installation and configuration guidance.

## Frontend requirements

Create a clean desktop-first interface.

The initial application should include:

- Pianova name and tagline
- Short product description
- Create-project button
- Project list
- Upload area
- Drag-and-drop support
- Supported file types
- File validation feedback
- Audio player
- Video player when the source is video
- Processing status
- Current pipeline stage
- Progress indicator
- Error display
- Project metadata
- Generated artifact links
- Download controls
- Detected tempo
- Time-signature selector
- Key-signature selector
- Detected-note table
- Basic piano-roll visualization
- Regenerate-score button

Prioritize clarity and functionality.

Do not spend excessive time on:

- Animations
- Complex branding
- Marketing pages
- Mobile design
- Custom design systems

Use a minimal, modern visual design.

## Piano-roll editor

After the upload-to-score pipeline works, build a basic piano-roll editor.

The editor should display:

- Time horizontally
- MIDI pitch vertically
- Piano-key labels
- Notes as rectangular blocks
- Different visual treatment for left-hand and right-hand notes
- Unknown-hand notes
- Playback cursor when practical
- Selected-note state

The editor should eventually support:

- Selecting a note
- Selecting multiple notes
- Moving a note
- Resizing note duration
- Changing pitch
- Changing hand assignment
- Changing voice assignment
- Deleting a note
- Restoring a deleted note
- Adding a note
- Snapping notes to the quantization grid
- Playing a selected section

For the initial editor, prioritize:

1. Viewing notes
2. Selecting notes
3. Editing values through a side panel or table
4. Deleting notes
5. Changing hand assignment
6. Regenerating the score

Do not attempt to build a complete DAW.

Keep the editor architecture modular because it may become one of Pianova’s most important features.

## Note table

Provide a table displaying:

- Pitch
- Pitch name
- Onset
- Offset
- Duration
- Velocity
- Confidence
- Hand
- Staff
- Voice
- Measure
- Beat
- Edited state

Allow sorting and filtering.

Useful filters may include:

- Low-confidence notes
- Left-hand notes
- Right-hand notes
- Unknown-hand notes
- Manually edited notes
- Deleted notes
- Notes within a time range

## Playback synchronization

When practical, synchronize:

- Original audio playback
- Piano-roll playback cursor
- Selected notes
- Score position

This does not need to be perfect in the first milestone.

Design APIs and frontend state so synchronization can be added without rewriting the whole application.

## Synthesia video mode

Do not implement the complete Synthesia computer-vision system until the audio pipeline is stable.

However, document and prepare the architecture for it.

The future video pipeline may include:

1. Extract video frames.
2. Detect or calibrate the keyboard region.
3. Identify white-key and black-key boundaries.
4. Locate the strike line.
5. Detect colored falling-note rectangles.
6. Track rectangles across frames.
7. Map horizontal positions to MIDI pitches.
8. Estimate note onsets.
9. Estimate note durations.
10. Infer left and right hand from note colors.
11. Assign confidence values.
12. Compare visual detections against audio detections.
13. Merge detections.
14. Flag disagreements for review.

For constrained Synthesia videos, traditional OpenCV techniques may be sufficient.

Potential techniques include:

- Perspective correction
- Color thresholding
- Edge detection
- Connected-component analysis
- Contour detection
- Frame differencing
- Optical flow
- Object tracking
- User-assisted calibration

Do not introduce a neural network for video analysis unless there is a demonstrated need.

A future calibration interface may ask the user to identify:

- Left edge of the keyboard
- Right edge of the keyboard
- Strike line
- Lowest visible key
- Highest visible key
- Left-hand note color
- Right-hand note color

## Multimodal detection

Design note events so they can eventually represent detections from multiple sources.

Possible sources:

```text
audio
video
audio_and_video
manual
```

Future confidence information should include:

- Audio confidence
- Visual confidence
- Combined confidence
- Timing agreement
- Pitch agreement
- Conflict status

Possible future fusion behavior:

```python
if audio_detection and visual_detection and detections_agree:
    accept_with_high_confidence()
elif visual_detection and not audio_detection:
    accept_if_visual_confidence_is_high()
elif audio_detection and not visual_detection:
    accept_if_audio_confidence_is_high()
else:
    flag_for_manual_review()
```

Do not implement placeholder fusion logic and claim it is complete.

## Human-in-the-loop corrections

Treat manual correction as a core feature rather than a failure of the AI.

Store both:

- Original model output
- Current edited state

Every manual edit should be traceable.

Possible edit history fields:

- Note ID
- Previous values
- New values
- Edit type
- Timestamp

This corrected data may eventually become training data for improved models.

Design the data model so future exports can contain:

```text
raw transcription → corrected transcription
```

## Evaluation

Create an evaluation module that compares generated note events against ground-truth MIDI.

Possible note-level metrics:

- Onset precision
- Onset recall
- Onset F1
- Pitch accuracy
- Offset accuracy
- Offset F1
- Velocity error
- Hand-assignment accuracy
- Note-duration error

Possible notation-quality metrics:

- Number of unnecessary ties
- Number of extremely short rests
- Number of unexpected tuplets
- Number of misaligned chord notes
- Number of measures requiring correction
- Number of low-confidence notes
- Number of manual edits required
- Time required to produce a usable score

Keep note-detection accuracy separate from score-readability quality.

A transcription may have accurate pitches while still producing poor notation.

## Testing requirements

Add automated tests for:

- File-extension validation
- MIME-type validation
- Filename sanitization
- Project-directory generation
- FFmpeg command construction
- FFprobe parsing
- Subprocess failure handling
- Note-event validation
- Note-event serialization
- MIDI generation
- Chord grouping
- Quantization
- Hand separation
- Staff assignment
- MusicXML generation
- Database operations
- API status transitions
- Artifact creation
- Error persistence
- Project deletion and file cleanup

Create small synthetic note-event and MIDI fixtures.

Do not require large audio files for ordinary unit tests.

Use integration tests selectively for:

- FFmpeg
- Basic Pitch
- MusicXML generation
- MuseScore rendering

Skip dependency-specific integration tests gracefully when the required executable is unavailable.

Do not make the whole test suite fail merely because MuseScore is not installed.

## Logging

Add structured logging around every pipeline stage.

Include:

- Project ID
- Processing-run ID
- Pipeline stage
- Start time
- End time
- Duration
- Artifact paths
- Error information

Do not log sensitive file contents.

Make logs useful for debugging failed transcriptions.

## Configuration

Create a typed configuration system.

Possible environment variables:

```text
PIANOVA_WORKSPACE_DIR
PIANOVA_DATABASE_URL
PIANOVA_FFMPEG_PATH
PIANOVA_FFPROBE_PATH
PIANOVA_MUSESCORE_PATH
PIANOVA_MAX_UPLOAD_MB
PIANOVA_LOG_LEVEL
PIANOVA_CORS_ORIGINS
```

Provide `.env.example`.

Choose safe local defaults.

Do not require the user to configure every value manually.

## Dependency management

Use stable dependency versions compatible with the selected Python and Node.js versions.

Before pinning versions:

- Check compatibility between Basic Pitch, TensorFlow, Python, NumPy, librosa, and other audio dependencies.
- Avoid selecting versions merely because they are newest.
- Document any Python-version constraints.
- Prefer a version of Python known to work with the transcription model.
- Keep ML dependencies isolated where useful.

If Basic Pitch causes major dependency conflicts, investigate alternatives or an isolated transcription environment.

Do not silently use incompatible packages.

Explain technical tradeoffs in the architecture documentation.

## Background processing

For the first implementation, processing may run:

- Synchronously for a minimal proof of concept
- In a simple local worker
- In a background thread or process with clear limitations

Avoid adding Celery, Redis, or a distributed queue for the MVP unless there is a concrete need.

The frontend must still be able to display processing states.

Ensure that long-running work does not unnecessarily block unrelated API requests.

Document the selected approach.

## Error handling

Return clear errors for cases such as:

- Unsupported file format
- File too large
- Corrupted media
- Missing FFmpeg
- Failed audio extraction
- Failed transcription
- Invalid model output
- Failed MIDI generation
- Failed MusicXML generation
- Missing MuseScore
- Failed PDF rendering
- Database error
- Missing project
- Missing artifact

Do not expose internal stack traces directly to the frontend in production-style responses.

Log detailed errors on the backend.

## Documentation

Create a high-quality root README containing:

- Pianova name
- Tagline
- Product description
- Current capabilities
- Screenshots section placeholder
- Architecture summary
- Technology stack
- Setup requirements
- Supported file formats
- How to install FFmpeg
- How to install MuseScore
- How to install Python dependencies
- How to install frontend dependencies
- How to run the backend
- How to run the frontend
- How to run tests
- How the processing pipeline works
- Current limitations
- Troubleshooting
- Project roadmap
- License information

Also create:

```text
docs/architecture.md
docs/pipeline.md
docs/roadmap.md
docs/research-notes.md
docs/data-model.md
docs/evaluation.md
```

### architecture.md

Explain:

- Frontend/backend boundaries
- Pipeline-stage boundaries
- Domain models
- Database
- Filesystem workspace
- External executables
- Transcription-model abstraction
- Major technical decisions

### pipeline.md

Explain each stage:

- Inputs
- Outputs
- Failure modes
- Generated artifacts
- Relevant configuration

### roadmap.md

Organize work into milestones.

Suggested milestones:

1. Repository scaffold
2. Upload and media validation
3. Audio extraction
4. Basic transcription
5. MIDI export
6. Tempo and quantization
7. Hand separation
8. MusicXML generation
9. PDF rendering
10. Note table
11. Piano-roll editor
12. Manual correction
13. Evaluation
14. Synthesia extraction
15. Audio-video fusion
16. Custom ML improvements

### research-notes.md

Track:

- Automatic music transcription research
- Candidate pretrained models
- Relevant datasets
- Quantization approaches
- Hand-separation approaches
- Voice-separation approaches
- Enharmonic spelling
- Synthesia computer vision
- Copyright and ethical considerations

### evaluation.md

Define:

- Ground-truth formats
- Metrics
- Test datasets
- Benchmark procedure
- Known limitations

## Copyright and responsible use

Pianova is a transcription tool.

Do not build automatic downloading or scraping from YouTube, TikTok, or other platforms into the MVP.

The initial application should accept files the user already possesses and is authorized to process.

Add a short notice explaining that users are responsible for respecting copyright and platform terms when processing recordings.

Do not include copyrighted audio test files in the repository.

Use:

- Original recordings
- Public-domain music
- Synthetic MIDI renders
- Properly licensed samples

## Development approach

Work incrementally.

Do not attempt to implement every long-term feature immediately.

Follow this order:

1. Analyze the repository and current environment.
2. Create an implementation plan.
3. Identify technical risks.
4. Select compatible dependency versions.
5. Scaffold the backend.
6. Scaffold the frontend.
7. Add a health-check endpoint.
8. Add dependency detection.
9. Add project creation.
10. Add file upload and validation.
11. Add FFprobe inspection.
12. Add FFmpeg audio extraction and normalization.
13. Add transcription-model abstraction.
14. Integrate a real pretrained transcription model.
15. Store note events.
16. Generate raw MIDI.
17. Add basic tempo estimation.
18. Add basic quantization.
19. Add hand separation.
20. Generate cleaned MIDI.
21. Generate MusicXML.
22. Add optional MuseScore rendering.
23. Add artifact downloads.
24. Add the detected-note table.
25. Add the piano-roll viewer.
26. Add manual corrections.
27. Add score regeneration.
28. Add evaluation tools.
29. Document Synthesia mode.
30. Implement Synthesia mode only after the audio workflow is stable.

After each milestone:

- Verify the application runs.
- Run relevant tests.
- Fix failures before moving forward.
- Update documentation.
- Clearly mark unfinished functionality.
- Document known limitations.
- Avoid adding unrelated complexity.

## Coding requirements

Use the following standards:

- Python type hints
- TypeScript types
- Focused functions
- Clear module boundaries
- Descriptive names
- Pydantic validation
- Database migrations if appropriate
- Dependency injection where useful
- Repository or service patterns only when they improve clarity
- Structured error handling
- Structured logging
- Automated tests
- Safe subprocess execution
- Cross-platform path handling with `pathlib`
- Comments for non-obvious musical logic
- Docstrings for public Python APIs
- No fake implementations
- No silent exception swallowing
- No hardcoded absolute paths
- No hardcoded user-specific directories
- No secrets committed to Git
- No generated media committed to Git
- No unnecessary abstraction layers

Prefer understandable code over clever code.

## Git practices

Create a thorough `.gitignore`.

Ignore at least:

```text
.env
*.db
*.sqlite
*.sqlite3
__pycache__/
.pytest_cache/
.mypy_cache/
.venv/
venv/
node_modules/
.next/
coverage/
dist/
build/
workspace/projects/*
models/
*.wav
*.mp3
*.m4a
*.mp4
*.mov
*.mid
*.midi
*.musicxml
*.mxl
*.pdf
```

Keep `.gitkeep` files where empty directories must be preserved.

Do not commit large ML model files.

Document how models are downloaded or installed.

## Initial visual direction

Use a clean, understated interface inspired by modern creative tools.

Possible visual motifs:

- Piano keys
- Musical staff lines
- Piano-roll blocks
- Waveforms
- Sheet-music pages

Do not overuse musical icons.

Use “Pianova” as the visible product name.

Suggested homepage copy:

> Turn piano performances into readable sheet music.

Supporting text:

> Upload a piano recording or video. Pianova detects the notes, reconstructs the musical structure, and generates editable MIDI and MusicXML.

Suggested upload text:

> Drop a piano recording here

Supported-formats text:

> MP3, WAV, M4A, MP4, and MOV

## Definition of the first successful vertical slice

The first vertical slice is successful when all of the following are true:

1. The backend starts locally.
2. The frontend starts locally.
3. The frontend can reach the backend health endpoint.
4. A user can create a project.
5. A user can upload a supported file.
6. The file is stored safely.
7. The media is inspected using FFprobe.
8. The audio is normalized using FFmpeg.
9. A real transcription model generates note events.
10. Raw note events are saved as JSON.
11. A raw MIDI file is generated.
12. Basic MusicXML is generated.
13. The frontend displays project status.
14. The user can download the generated artifacts.
15. Errors are shown clearly.
16. Automated tests cover the critical non-ML behavior.
17. The README explains how to run and verify everything.

The generated sheet music does not need to be polished at this stage.

The goal is to prove the complete flow before improving musical intelligence.

## First task

Begin by producing the following:

1. A concise implementation plan
2. A milestone breakdown
3. Key technical risks
4. Recommended Python and Node.js versions
5. Recommended dependency versions, with compatibility concerns noted
6. The initial repository structure
7. Backend scaffolding
8. Frontend scaffolding
9. A working backend health-check endpoint
10. A frontend page that calls and displays the health-check result
11. A basic project-creation endpoint
12. A secure basic upload endpoint
13. SQLite setup
14. Initial database models
15. Initial tests
16. `.env.example`
17. `.gitignore`
18. Root README with exact setup and run instructions

Before writing a large amount of code, inspect the environment and explain any dependency risks, especially around Python, TensorFlow, Basic Pitch, NumPy, librosa, FFmpeg, and MuseScore.

Do not create placeholder functions that pretend transcription or score generation works.

Clearly label all unfinished features.

After implementing the initial scaffold:

- Run the backend tests.
- Run frontend checks.
- Report any commands that fail.
- Fix failures that can be fixed.
- Explain exactly how I can run the application locally.
- Explain exactly how I can verify each implemented feature.
- Summarize the files created or changed.
- State the next recommended milestone.

Do not attempt the full project in a single uncontrolled pass. Establish a stable foundation first, then proceed milestone by milestone.
