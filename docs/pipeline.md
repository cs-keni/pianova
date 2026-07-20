# Processing Pipeline

The current backend implements secure ingestion, typed media preparation, raw Basic Pitch transcription, conservative readable timing, independent hand/staff interpretation, and staff-scoped notation voices. Every later score stage remains a separate typed boundary and must fail explicitly until implemented.

| Stage | Input | Output/artifact | Main failure modes | Status |
|---|---|---|---|---|
| Project creation | Valid title, 1-120 characters | Project row and UUID directory | Validation, database commit, directory creation | Implemented |
| Upload validation | Project ID and multipart source | Validated temporary file | Missing project, unsupported extension, empty file, byte limit, signature mismatch | Implemented |
| Upload finalization | Valid temporary file | `source-<UUID>.<ext>` and source Artifact row | Atomic rename or metadata commit failure | Implemented |
| Media inspection | Source artifact | Duration, container, bit rate, typed stream rows | Missing FFprobe, undecodable input, missing audio/duration, timeout | Implemented |
| Audio normalization | Valid inspected media | Mono 22.05 kHz PCM WAV artifact | Missing FFmpeg, codec failure, timeout, disk or commit failure | Implemented |
| Transcription | Normalized WAV | Raw typed note events | Missing worker, model load/inference failure, timeout, malformed output | Implemented |
| Raw MIDI | Raw note events | Raw MIDI artifact | Invalid pitch/timing, serialization or finalization failure | Implemented |
| Tempo and quantization | Raw timing, pitch, confidence | Global BPM, simple meter, chord groups, symbolic onsets/durations, diagnostics | Sparse/ambiguous tempo, unsupported meter, dense same-pitch rhythm, concurrent update | Implemented |
| Hands and notation staves | Quantized notes | Persisted assignments, confidence, reasons, diagnostics | Missing/stale timing, work bound, concurrent update | Implemented |
| Voice separation | Interpreted notes | Staff-scoped notation voices, decision scores, typed unknowns | Missing/stale interpretation, concurrent update | Implemented |
| Key and pitch spelling | Voiced notes | Tonal context and spelled score events | Missing/stale voice state, ambiguous key or spelling, concurrent update | Pure engine only; persistence/API not implemented |
| MusicXML | Clean symbolic score | Editable MusicXML | Invalid measures, voices, durations, spelling | Not implemented |
| Score rendering | MusicXML | PDF/SVG | MuseScore missing or render failure | Not implemented |
| User correction | Note events and score state | Revised symbolic score and artifacts | Invalid edits or regeneration failure | Not implemented |

## Implemented upload contract

Accepted extensions are `.mp3`, `.wav`, `.m4a`, `.mp4`, and `.mov`. The byte limit is `PIANOVA_MAX_UPLOAD_MB` and defaults to 250 MB. The service reads in 1 MiB chunks and retains up to 8 KiB for signature detection.

M4A, MP4, and MOV share ISO base media signatures, so those detected containers are compatible with each of those extensions. MP3 and WAV require their corresponding signatures.

On success, the project becomes `uploaded`, original display metadata is recorded, and a `source` Artifact points to the generated relative path. Transcription is not triggered.

## Implemented media-processing contract

`POST /api/projects/{project_id}/process-media` is explicit and synchronous. FFprobe runs with safe arguments, JSON output, and the configured inspection timeout. Pianova persists project duration/container/bit rate and one typed `MediaStream` row per reported stream. Sources without audio or a positive duration are rejected.

FFmpeg maps the first audio stream, removes video, and writes mono 22.05 kHz 16-bit PCM WAV to a hidden temporary path. The service atomically finalizes the generated filename and commits the normalized Artifact, metadata, and successful ProcessingRun together. Timeouts and failures remove partial output and leave the source retryable. Repeated successful requests reuse the existing normalized Artifact.

## Implemented transcription contract

`POST /api/projects/{project_id}/transcribe` is explicit and synchronous. It requires a normalized WAV and rejects sources shorter than the configured 0.05-second minimum before inference. The ordinary FastAPI environment launches an isolated `.venv-transcription` worker, which loads Basic Pitch 0.4.0 and TensorFlow 2.15 without importing the ML stack into the API process.

The worker writes versioned note-event JSON and raw MIDI to temporary paths. Pianova validates the schema and Basic Pitch provenance, atomically finalizes both artifacts, persists raw `NoteEvent` rows plus model/runtime/configuration metadata, and completes the ProcessingRun in one database transaction. Timeouts, inference failures, malformed output, finalization failures, and commit failures clean up generated files and remain retryable. Repeated successful requests reuse the existing note-event JSON and raw MIDI.

## Implemented quantization contract

`POST /api/projects/{project_id}/quantize` requires persisted note events. It groups attacks within
60 ms, estimates one quarter-note BPM from bounded onset intervals, and accepts automatic tempo
only when group count, span, residual, inlier coverage, winner separation, and half/double-tempo
gates all pass. An explicit BPM bypasses automatic fit acceptance while retaining diagnostics.

The baseline supports `2/4`, `3/4`, and `4/4`; omitted meter defaults to `4/4`. Measure origin
defaults to the first chord attack and can be overridden explicitly. Onsets and durations use exact
fractions internally, snap to a straight sixteenth-note grid, favor readable straight/dotted values,
and never alter raw timing. Same-pitch overlap repair is bounded and otherwise returns
`rhythm_too_dense`.

Processing uses a raw-note fingerprint, effective configuration, and algorithm version for
idempotent reuse. A running audit row is precommitted; success atomically updates project timing,
note symbolic fields, the current-run pointer, and an optimistic revision. Failures and concurrent
losers preserve the prior complete symbolic result. The transaction shell is provided by the
shared `StageRunner`; timing-specific fingerprinting, reuse, note writes, and CAS conditions remain
owned by `QuantizationService`.

## Implemented hand/staff interpretation contract

`POST /api/projects/{project_id}/interpret` requires a current complete quantization. Hand and
notation staff are independent assignments: a right-hand note may use bass staff and a left-hand
note may use treble staff. Each pass evaluates contiguous lower/upper chord splits across the full
passage using pitch comfort, span, movement, appearance, split movement, and crossing costs.

Per-note confidence is the normalized cost margin between the best complete passage paths under
the two competing assignments. A sub-threshold result succeeds as `unknown` with one typed reason:
`insufficient_context`, `crossing`, `wide_chord`, `middle_register`, or `close_alternative`.
Transition evaluation is counted before solving and rejected when it exceeds the configured work
bound.

The service fingerprints the current quantization run and ordered symbolic notes with the complete
settings/version identity. Matching successful state is reused only after run ownership, stage,
diagnostics, confidence, and ambiguity invariants pass. Success atomically writes all note fields,
the current interpretation run, and an optimistic revision. Re-quantization invalidates this state
only when timing is genuinely recomputed. `InterpretationService` uses the same `StageRunner`
transaction shell while retaining all interpretation-specific validation and persistence policy.

## Implemented voice-separation contract

`app.symbolic.voices.separate_voices` consumes immutable notes with exact symbolic onset/duration
and independent staff evidence. Staff-unknown notes succeed as `unresolved_staff` unknowns.
Resolved notes are collapsed into compatible chord nodes; incompatible half-open interval overlaps
form conflict components. Components requiring at most two streams are deterministically
two-colored, with voice 1 assigned to the higher-mean-pitch stream. A proven third concurrent
stream is removed by latest-onset, highest-pitch, then ID priority and reported as
`voice_capacity_exceeded`; remaining notes are still colored.

Crossing and sub-threshold separation remain successful typed unknowns. `voice_confidence` is an
uncalibrated normalized stream-separation decision score, not a probability. Revision
`20260718_0007` supplies nullable current-run ownership, a non-negative optimistic revision,
`voice >= 1`, a bounded score, typed reasons, and exactly three valid field combinations.

`POST /api/projects/{project_id}/separate-voices` requires current, complete interpretation
evidence. The service fingerprints the owning interpretation run/revision, ordered note evidence,
settings, runtime, and algorithm version. Reuse validates run ownership, JSON/provenance,
diagnostics, tri-state fields, staff/reason rules, the version-1 voice cap, and the per-staff
overlap invariant. Success returns a bounded note preview, per-staff voice 1/2 counts, structural
diagnostics, provenance, ownership/revision, and reuse state.

Genuine re-interpretation clears voices and advances `voice_revision`; genuine re-quantization
clears both interpretation and voice state and advances both downstream revisions. The cascade
increments are SQL-relative within the upstream transaction. Voice, interpretation, and
quantization compare-and-swap predicates make either interleaving deterministic: the first valid
commit wins and the stale stage returns a conflict without losing an increment.

The frontend enables `Separate voices` only after interpretation succeeds, prevents duplicate
submissions while pending, and preserves recoverable errors for retry. Success shows resolved and
unknown totals, treble/bass voice 1/2 counts, and bounded hand/staff/voice evidence with the
uncalibrated decision score and typed reason in separate columns.

## Pure key/spelling contract (not yet API-visible)

`app.symbolic.spelling.spell_notes` consumes immutable voiced notes with persisted float timing and
positive `chord_group` evidence. It validates finite symbolic values, estimates one global major or
minor key from a duration-weighted pitch-class histogram and 24 fixed Krumhansl-Kessler profiles,
or adopts a validated key override. Weak, degenerate, or split evidence succeeds with a typed
unknown key rather than manufacturing a winner.

Resolved-key spelling uses line-of-fifths proximity, third-stacking within `chord_group`, and a
chromatic-neighbor stream preference. Decision margins use a fixed 12-unit scale; singleton pitch
classes score 1.0. Under an unknown key, a spelling resolves only when every plausible key has the
same unique above-margin winner; otherwise it succeeds as `unknown_key`. The engine is deterministic,
input-order invariant, O(24n), dependency-free, and covered by 32 focused tests. No project or note
fields are written until T2 persistence and T3 service integration land.

## Generated artifacts

All artifact kinds are reserved in the schema: source, normalized audio, note-event JSON, raw MIDI, cleaned MIDI, MusicXML, and PDF. Source, normalized-audio, note-event JSON, and raw-MIDI artifacts are currently produced.

## Configuration

- `PIANOVA_WORKSPACE_DIR`: artifact root.
- `PIANOVA_MAX_UPLOAD_MB`: streaming upload limit.
- `PIANOVA_FFMPEG_PATH`, `PIANOVA_FFPROBE_PATH`, `PIANOVA_MUSESCORE_PATH`: executable overrides.
- `PIANOVA_DEPENDENCY_PROBE_TIMEOUT_SECONDS`: probe timeout, default 3 seconds.
- `PIANOVA_MEDIA_INSPECTION_TIMEOUT_SECONDS`: FFprobe processing timeout, default 30 seconds.
- `PIANOVA_MEDIA_NORMALIZATION_TIMEOUT_SECONDS`: FFmpeg processing timeout, default 300 seconds.
- `PIANOVA_NORMALIZED_SAMPLE_RATE`: output rate, default 22050 Hz.
- `PIANOVA_NORMALIZED_CHANNELS`: output channels, default mono.
- `PIANOVA_TRANSCRIPTION_PYTHON_PATH`: optional isolated-worker Python override.
- `PIANOVA_TRANSCRIPTION_PROBE_TIMEOUT_SECONDS`: worker dependency-probe timeout, default 30 seconds.
- `PIANOVA_TRANSCRIPTION_TIMEOUT_SECONDS`: inference timeout, default 1800 seconds.
- `PIANOVA_TRANSCRIPTION_MINIMUM_DURATION_SECONDS`: pre-inference duration floor, default 0.05 seconds.
- `PIANOVA_TRANSCRIPTION_ONSET_THRESHOLD`, `PIANOVA_TRANSCRIPTION_FRAME_THRESHOLD`: Basic Pitch detection thresholds.
- `PIANOVA_TRANSCRIPTION_MINIMUM_NOTE_LENGTH_MS`: minimum emitted note length, default 127.7 ms.
- `PIANOVA_TRANSCRIPTION_MINIMUM_FREQUENCY_HZ`, `PIANOVA_TRANSCRIPTION_MAXIMUM_FREQUENCY_HZ`: piano-range frequency bounds.
- `PIANOVA_QUANTIZATION_MINIMUM_BPM`, `PIANOVA_QUANTIZATION_MAXIMUM_BPM`: automatic/override BPM range.
- `PIANOVA_QUANTIZATION_CHORD_TOLERANCE_MS`, `PIANOVA_QUANTIZATION_MINIMUM_GRID_BEATS`: grouping and straight-grid resolution.
- `PIANOVA_QUANTIZATION_MINIMUM_TEMPO_GROUPS`, `PIANOVA_QUANTIZATION_MINIMUM_TEMPO_SPAN_SECONDS`: absolute evidence gates.
- `PIANOVA_QUANTIZATION_MAXIMUM_RESIDUAL`, `PIANOVA_QUANTIZATION_MINIMUM_INLIER_COVERAGE`, `PIANOVA_QUANTIZATION_INLIER_RESIDUAL`: fit-quality gates.
- `PIANOVA_QUANTIZATION_DISTINCT_TEMPO_RATIO`: same-pulse candidate neighborhood, default 2%.
- `PIANOVA_QUANTIZATION_AMBIGUITY_MARGIN`, `PIANOVA_QUANTIZATION_OCTAVE_AMBIGUITY_MARGIN`: distinct-winner and half/double-tempo separation.
- `PIANOVA_QUANTIZATION_REST_TOLERANCE_BEATS`, `PIANOVA_QUANTIZATION_SAME_PITCH_REPAIR_TOLERANCE_BEATS`: readable-duration and collision bounds.
- `PIANOVA_QUANTIZATION_PREVIEW_NOTE_LIMIT`, `PIANOVA_QUANTIZATION_ALGORITHM_VERSION`: response bound and reuse identity.
- `PIANOVA_INTERPRETATION_*_CENTER_PITCH`, scoring weights, span/register thresholds, and confidence margins: deterministic hand/staff baseline.
- `PIANOVA_INTERPRETATION_MAXIMUM_TRANSITION_EVALUATIONS`: hard dynamic-programming work bound.
- `PIANOVA_INTERPRETATION_PREVIEW_NOTE_LIMIT`, `PIANOVA_INTERPRETATION_ALGORITHM_VERSION`: response bound and reuse identity.
- `PIANOVA_VOICE_CLOSE_SEPARATION_SEMITONES`, `PIANOVA_VOICE_HIGH_SEPARATION_SEMITONES`: typed-unknown and high-confidence separation thresholds.
- `PIANOVA_VOICE_PREVIEW_NOTE_LIMIT`, `PIANOVA_VOICE_ALGORITHM_VERSION`: response bound and reuse identity.
- `PIANOVA_DATABASE_URL`: SQLite or another SQLAlchemy URL.

Related: [architecture](architecture.md), [data model](data-model.md), and the root [run guide](../README.md#run-pianova).
