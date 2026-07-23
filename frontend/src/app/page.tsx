"use client";

import { FormEvent, useEffect, useState } from "react";
import styles from "./page.module.css";
import {
  ApiError,
  api,
  type ConfigResponse,
  type HealthResponse,
  type InterpretationResponse,
  type KeyOverride,
  type Project,
  type QuantizationResponse,
  type SpellingResponse,
  type TranscriptionResponse,
  type VoiceSeparationResponse,
} from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const wholeSeconds = Math.round(seconds);
  const minutes = Math.floor(wholeSeconds / 60);
  const remainder = wholeSeconds % 60;
  return minutes > 0 ? `${minutes}:${remainder.toString().padStart(2, "0")}` : `${remainder}s`;
}

function formatPitch(pitch: number): string {
  const names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something unexpected went wrong.";
}

function formatAssignment(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatReason(reason: string | null): string {
  return reason ? reason.replaceAll("_", " ") : "Resolved";
}

function formatAccidental(alter: number): string {
  if (alter === -2) return "♭♭";
  if (alter === -1) return "♭";
  if (alter === 1) return "♯";
  if (alter === 2) return "♯♯";
  return "";
}

function formatSpelling(
  step: string | null,
  alter: number | null,
  octave: number | null,
): string {
  if (step == null || alter == null || octave == null) return "Unknown";
  return `${step}${formatAccidental(alter)}${octave}`;
}

const KEY_OPTIONS: { value: string; label: string; key: KeyOverride }[] = [
  ["Cb major", "C♭ major", "C", -1, "major"],
  ["Gb major", "G♭ major", "G", -1, "major"],
  ["Db major", "D♭ major", "D", -1, "major"],
  ["Ab major", "A♭ major", "A", -1, "major"],
  ["Eb major", "E♭ major", "E", -1, "major"],
  ["Bb major", "B♭ major", "B", -1, "major"],
  ["F major", "F major", "F", 0, "major"],
  ["C major", "C major", "C", 0, "major"],
  ["G major", "G major", "G", 0, "major"],
  ["D major", "D major", "D", 0, "major"],
  ["A major", "A major", "A", 0, "major"],
  ["E major", "E major", "E", 0, "major"],
  ["B major", "B major", "B", 0, "major"],
  ["F# major", "F♯ major", "F", 1, "major"],
  ["C# major", "C♯ major", "C", 1, "major"],
  ["Ab minor", "A♭ minor", "A", -1, "minor"],
  ["Eb minor", "E♭ minor", "E", -1, "minor"],
  ["Bb minor", "B♭ minor", "B", -1, "minor"],
  ["F minor", "F minor", "F", 0, "minor"],
  ["C minor", "C minor", "C", 0, "minor"],
  ["G minor", "G minor", "G", 0, "minor"],
  ["D minor", "D minor", "D", 0, "minor"],
  ["A minor", "A minor", "A", 0, "minor"],
  ["E minor", "E minor", "E", 0, "minor"],
  ["B minor", "B minor", "B", 0, "minor"],
  ["F# minor", "F♯ minor", "F", 1, "minor"],
  ["C# minor", "C♯ minor", "C", 1, "minor"],
  ["G# minor", "G♯ minor", "G", 1, "minor"],
  ["D# minor", "D♯ minor", "D", 1, "minor"],
  ["A# minor", "A♯ minor", "A", 1, "minor"],
].map(([value, label, tonic_step, tonic_alter, mode]) => ({
  value: String(value),
  label: String(label),
  key: {
    tonic_step: tonic_step as KeyOverride["tonic_step"],
    tonic_alter: tonic_alter as KeyOverride["tonic_alter"],
    mode: mode as KeyOverride["mode"],
  },
}));

interface SpellingControlsProps {
  selection: string;
  pending: boolean;
  emphasizeOverride: boolean;
  onSelectionChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function SpellingControls({
  selection,
  pending,
  emphasizeOverride,
  onSelectionChange,
  onSubmit,
}: SpellingControlsProps) {
  return (
    <form
      className={`${styles.spellingForm} ${emphasizeOverride ? styles.overrideNeeded : ""}`}
      onSubmit={onSubmit}
    >
      <div>
        <label htmlFor="key-override">Key signature</label>
        <select
          id="key-override"
          value={selection}
          onChange={(event) => onSelectionChange(event.target.value)}
        >
          <option value="">Auto-detect</option>
          <optgroup label="Major">
            {KEY_OPTIONS.filter((option) => option.key.mode === "major").map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="Minor">
            {KEY_OPTIONS.filter((option) => option.key.mode === "minor").map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </optgroup>
        </select>
      </div>
      <p className={styles.help}>
        Leave this on auto-detect, or choose a key to resolve uncertain or incorrect spellings.
        Clear the selection to estimate again.
      </p>
      <button className={styles.primaryButton} disabled={pending}>
        {pending ? "Detecting key and spelling notes…" : "Detect key & spell notes"}
      </button>
    </form>
  );
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [transcription, setTranscription] = useState<TranscriptionResponse | null>(null);
  const [quantizing, setQuantizing] = useState(false);
  const [quantization, setQuantization] = useState<QuantizationResponse | null>(null);
  const [interpreting, setInterpreting] = useState(false);
  const [interpretation, setInterpretation] = useState<InterpretationResponse | null>(null);
  const [separatingVoices, setSeparatingVoices] = useState(false);
  const [voiceSeparation, setVoiceSeparation] = useState<VoiceSeparationResponse | null>(null);
  const [spelling, setSpelling] = useState<SpellingResponse | null>(null);
  const [spellingNotes, setSpellingNotes] = useState(false);
  const [keySelection, setKeySelection] = useState("");
  const [tempoOverride, setTempoOverride] = useState("");
  const [meter, setMeter] = useState("4/4");
  const [measureOrigin, setMeasureOrigin] = useState("");

  async function loadStatus() {
    try {
      const [healthResponse, configResponse] = await Promise.all([api.health(), api.config()]);
      setHealth(healthResponse);
      setConfig(configResponse);
      setConnectionError(null);
    } catch (error) {
      setConnectionError(errorMessage(error));
    }
  }

  function retryStatus() {
    setConnectionError(null);
    void loadStatus();
  }

  useEffect(() => {
    let active = true;
    Promise.all([api.health(), api.config()])
      .then(([healthResponse, configResponse]) => {
        if (!active) return;
        setHealth(healthResponse);
        setConfig(configResponse);
      })
      .catch((error: unknown) => {
        if (active) setConnectionError(errorMessage(error));
      });
    return () => {
      active = false;
    };
  }, []);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || creating) return;
    setCreating(true);
    setFormError(null);
    try {
      setProject(await api.createProject(title.trim()));
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setCreating(false);
    }
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !file || uploading) return;
    setUploading(true);
    setFormError(null);
    try {
      const response = await api.upload(project.id, file);
      setProject(response.project);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setUploading(false);
    }
  }

  async function processMedia() {
    if (!project || processing) return;
    setProcessing(true);
    setFormError(null);
    try {
      const response = await api.processMedia(project.id);
      setProject(response.project);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setProcessing(false);
    }
  }

  async function transcribeProject() {
    if (!project || transcribing) return;
    setTranscribing(true);
    setFormError(null);
    try {
      const response = await api.transcribe(project.id);
      setProject(response.project);
      setTranscription(response);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setTranscribing(false);
    }
  }

  async function quantizeProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || quantizing) return;
    const [meterNumerator] = meter.split("/").map(Number);
    const tempo = tempoOverride.trim() ? Number(tempoOverride) : undefined;
    const origin = measureOrigin.trim() ? Number(measureOrigin) : undefined;
    setQuantizing(true);
    setFormError(null);
    try {
      const response = await api.quantize(project.id, {
        tempo_bpm: tempo,
        meter_numerator: meterNumerator as 2 | 3 | 4,
        meter_denominator: 4,
        measure_origin_seconds: origin,
      });
      setProject(response.project);
      setQuantization(response);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setQuantizing(false);
    }
  }

  async function interpretProject() {
    if (!project || interpreting) return;
    setInterpreting(true);
    setFormError(null);
    try {
      const response = await api.interpret(project.id);
      setProject(response.project);
      setInterpretation(response);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setInterpreting(false);
    }
  }

  async function separateVoices() {
    if (!project || !interpretation || separatingVoices) return;
    setSeparatingVoices(true);
    setFormError(null);
    try {
      const response = await api.separateVoices(project.id);
      setProject(response.project);
      setVoiceSeparation(response);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSeparatingVoices(false);
    }
  }

  async function spellProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !voiceSeparation || spellingNotes) return;
    setSpellingNotes(true);
    setFormError(null);
    try {
      const selectedKey = KEY_OPTIONS.find((option) => option.value === keySelection)?.key;
      const response = await api.spell(
        project.id,
        selectedKey ? { key_override: selectedKey } : {},
      );
      setProject(response.project);
      setSpelling(response);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSpellingNotes(false);
    }
  }

  const mediaCapability = health?.capabilities.find(
    (capability) => capability.key === "media_normalization",
  );
  const transcriptionCapability = health?.capabilities.find(
    (capability) => capability.key === "transcription",
  );
  const audioStream = project?.media_streams.find((stream) => stream.stream_type === "audio");
  const videoStream = project?.media_streams.find((stream) => stream.stream_type === "video");
  const mediaReady = project?.duration_seconds != null;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brandMark} aria-hidden="true">P</div>
        <div>
          <p className={styles.eyebrow}>Local piano transcription workspace</p>
          <h1>Pianova</h1>
        </div>
        <div className={`${styles.connection} ${health ? styles.online : ""}`}>
          <span aria-hidden="true" />
          {health ? "API connected" : connectionError ? "API offline" : "Connecting"}
        </div>
      </header>

      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Hear it. See it. Play it.</p>
          <h2>Turn a piano performance into music you can work with.</h2>
          <p className={styles.lede}>
            Start a local project and securely add a solo-piano recording. Pianova keeps every
            source file on this computer and tells you exactly which processing stages are ready.
          </p>
        </div>
        <div className={styles.scorePreview} aria-label="Decorative musical staff">
          <span>𝄞</span>
          <div>♩ ♪ ♫</div>
        </div>
      </section>

      {connectionError && (
        <section className={styles.alert} role="alert">
          <div>
            <strong>Backend connection needed</strong>
            <p>{connectionError}</p>
          </div>
          <button type="button" onClick={retryStatus}>Retry</button>
        </section>
      )}

      <div className={styles.grid}>
        <section className={styles.workflow} aria-labelledby="workflow-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.step}>
                Step{" "}
                {spelling
                  ? "8"
                  : voiceSeparation
                  ? "7"
                  : interpretation
                    ? "6"
                  : quantization
                    ? "5"
                    : transcription
                      ? "4"
                      : mediaReady
                        ? "3"
                        : project
                          ? "2"
                          : "1"}{" "}
                of 8
              </p>
              <h3 id="workflow-title">
                {spelling
                  ? "Key and pitch spelling ready"
                  : voiceSeparation
                  ? "Notation voices ready"
                  : interpretation
                    ? "Hands and staves assigned"
                  : quantization
                    ? "Readable timing ready"
                  : transcription
                  ? "Raw transcription ready"
                  : mediaReady
                  ? "Media ready"
                  : project?.status === "uploaded"
                    ? "Inspect and prepare audio"
                    : project
                      ? "Add the performance"
                      : "Create a project"}
              </h3>
            </div>
            {project && <span className={styles.projectId}>Project ready</span>}
          </div>

          {!project ? (
            <form onSubmit={createProject} className={styles.form}>
              <label htmlFor="project-title">Project name</label>
              <input
                id="project-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                maxLength={120}
                placeholder="e.g. Chopin nocturne study"
                autoComplete="off"
              />
              <p className={styles.help}>Use the piece title or a name you will recognize later.</p>
              <button className={styles.primaryButton} disabled={!title.trim() || creating}>
                {creating ? "Creating…" : "Create local project"}
              </button>
            </form>
          ) : spelling ? (
            <div className={styles.quantizationResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Key detection and pitch spelling ready</h4>
                  <p>
                    {spelling.diagnostics.resolved_count} resolved ·{" "}
                    {spelling.diagnostics.unknown_count} unknown
                  </p>
                  <p>
                    Unknown spellings remain evidence for review. Cleaned MIDI, MusicXML, and
                    score rendering have not started.
                  </p>
                </div>
              </div>
              <div
                className={`${styles.keyCard} ${
                  spelling.key.ambiguity_reason ? styles.keyUnknown : ""
                }`}
              >
                <p className={styles.eyebrow}>
                  {spelling.key.source === "override" ? "User-chosen key" : "Estimated key"}
                </p>
                <h4>
                  {spelling.key.tonic_step != null &&
                  spelling.key.tonic_alter != null &&
                  spelling.key.mode != null
                    ? `${spelling.key.tonic_step}${formatAccidental(
                        spelling.key.tonic_alter,
                      )} ${spelling.key.mode}`
                    : "Key uncertain"}
                </h4>
                <p>
                  {spelling.key.ambiguity_reason
                    ? `${formatReason(spelling.key.ambiguity_reason)}. Choose the intended key below to respell these notes.`
                    : spelling.key.confidence == null
                      ? "Applied as an explicit override."
                      : `${Math.round(spelling.key.confidence * 100)}% uncalibrated decision score · ${
                          spelling.key.key_signature_fifths
                        } fifths`}
                </p>
              </div>
              <dl className={styles.timingDiagnostics}>
                <div>
                  <dt>Spellings</dt>
                  <dd>
                    {spelling.diagnostics.resolved_count} resolved ·{" "}
                    {spelling.diagnostics.unknown_count} unknown
                  </dd>
                </div>
                <div>
                  <dt>Unknown-key notes</dt>
                  <dd>{spelling.diagnostics.unknown_key_count}</dd>
                </div>
                <div>
                  <dt>Close alternatives</dt>
                  <dd>{spelling.diagnostics.close_alternative_count}</dd>
                </div>
                <div>
                  <dt>Processor</dt>
                  <dd>{spelling.provenance.processor_version}</dd>
                </div>
              </dl>
              <div className={styles.notePreview}>
                <h4>Written pitch evidence</h4>
                <div className={styles.noteTableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>Detected pitch</th>
                        <th>Written pitch</th>
                        <th>Grid onset</th>
                        <th>Hand</th>
                        <th>Staff</th>
                        <th>Voice</th>
                        <th>Decision score</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {spelling.preview_notes.map((note) => (
                        <tr key={note.id}>
                          <td>
                            {formatPitch(note.pitch)} <small>MIDI {note.pitch}</small>
                          </td>
                          <td>
                            {formatSpelling(
                              note.spelled_step,
                              note.spelled_alter,
                              note.spelled_octave,
                            )}
                          </td>
                          <td>{note.symbolic_start_beats.toFixed(2)}</td>
                          <td>{formatAssignment(note.hand)}</td>
                          <td>{formatAssignment(note.staff)}</td>
                          <td>{note.voice == null ? "Unknown" : `Voice ${note.voice}`}</td>
                          <td>{Math.round(note.spelling_confidence * 100)}%</td>
                          <td>{formatReason(note.spelling_ambiguity_reason)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <SpellingControls
                selection={keySelection}
                pending={spellingNotes}
                emphasizeOverride={spelling.key.ambiguity_reason != null}
                onSelectionChange={setKeySelection}
                onSubmit={spellProject}
              />
            </div>
          ) : voiceSeparation ? (
            <div className={styles.quantizationResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Notation voice separation ready</h4>
                  <p>
                    {voiceSeparation.diagnostics.resolved_count} resolved ·{" "}
                    {voiceSeparation.diagnostics.unknown_count} unknown
                  </p>
                  <p>
                    Unknown voices remain evidence for review. Key detection, pitch spelling,
                    cleaned MIDI, and score generation have not started.
                  </p>
                </div>
              </div>
              <dl className={styles.timingDiagnostics}>
                <div>
                  <dt>Treble voices</dt>
                  <dd>
                    V1 {voiceSeparation.diagnostics.treble_voice_1_count} · V2{" "}
                    {voiceSeparation.diagnostics.treble_voice_2_count}
                  </dd>
                </div>
                <div>
                  <dt>Bass voices</dt>
                  <dd>
                    V1 {voiceSeparation.diagnostics.bass_voice_1_count} · V2{" "}
                    {voiceSeparation.diagnostics.bass_voice_2_count}
                  </dd>
                </div>
                <div>
                  <dt>Structural unknowns</dt>
                  <dd>
                    {voiceSeparation.diagnostics.capacity_exceeded_count} capacity ·{" "}
                    {voiceSeparation.diagnostics.crossing_component_count} crossing
                  </dd>
                </div>
                <div>
                  <dt>Processor</dt>
                  <dd>{voiceSeparation.provenance.processor_version}</dd>
                </div>
              </dl>
              <div className={styles.notePreview}>
                <h4>Notation voice evidence</h4>
                <div className={styles.noteTableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>Pitch</th>
                        <th>Grid onset</th>
                        <th>Hand</th>
                        <th>Staff</th>
                        <th>Voice</th>
                        <th>Decision score</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {voiceSeparation.preview_notes.map((note) => (
                        <tr key={note.id}>
                          <td>
                            {formatPitch(note.pitch)} <small>MIDI {note.pitch}</small>
                          </td>
                          <td>{note.symbolic_start_beats.toFixed(2)}</td>
                          <td>{formatAssignment(note.hand)}</td>
                          <td>{formatAssignment(note.staff)}</td>
                          <td>{note.voice == null ? "Unknown" : `Voice ${note.voice}`}</td>
                          <td>{Math.round(note.voice_confidence * 100)}%</td>
                          <td>{formatReason(note.voice_ambiguity_reason)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <SpellingControls
                selection={keySelection}
                pending={spellingNotes}
                emphasizeOverride={false}
                onSelectionChange={setKeySelection}
                onSubmit={spellProject}
              />
            </div>
          ) : interpretation ? (
            <div className={styles.quantizationResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Hand and staff interpretation ready</h4>
                  <p>
                    {interpretation.note_count} interpreted{" "}
                    {interpretation.note_count === 1 ? "note" : "notes"} · uncertainty remains
                    explicit
                  </p>
                  <p>
                    Voices, key and pitch spelling, cleaned MIDI, and score generation have not
                    started.
                  </p>
                </div>
              </div>
              <dl className={styles.timingDiagnostics}>
                <div>
                  <dt>Hands</dt>
                  <dd>
                    {interpretation.diagnostics.resolved_hand_count} resolved ·{" "}
                    {interpretation.diagnostics.unknown_hand_count} unknown
                  </dd>
                </div>
                <div>
                  <dt>Staves</dt>
                  <dd>
                    {interpretation.diagnostics.resolved_staff_count} resolved ·{" "}
                    {interpretation.diagnostics.unknown_staff_count} unknown
                  </dd>
                </div>
                <div>
                  <dt>Wide chords</dt>
                  <dd>{interpretation.diagnostics.wide_chord_count}</dd>
                </div>
                <div>
                  <dt>Processor</dt>
                  <dd>{interpretation.provenance.processor_version}</dd>
                </div>
              </dl>
              <div className={styles.notePreview}>
                <h4>Interpreted note preview</h4>
                <div className={styles.noteTableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>Pitch</th>
                        <th>Grid onset</th>
                        <th>Hand</th>
                        <th>Hand evidence</th>
                        <th>Staff</th>
                        <th>Staff evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {interpretation.preview_notes.map((note) => (
                        <tr key={note.id}>
                          <td>
                            {formatPitch(note.pitch)} <small>MIDI {note.pitch}</small>
                          </td>
                          <td>{note.symbolic_start_beats.toFixed(2)}</td>
                          <td>{formatAssignment(note.hand)}</td>
                          <td>
                            {Math.round(note.hand_confidence * 100)}% ·{" "}
                            {formatReason(note.hand_ambiguity_reason)}
                          </td>
                          <td>{formatAssignment(note.staff)}</td>
                          <td>
                            {Math.round(note.staff_confidence * 100)}% ·{" "}
                            {formatReason(note.staff_ambiguity_reason)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={separatingVoices}
                onClick={separateVoices}
              >
                {separatingVoices ? "Separating notation voices…" : "Separate voices"}
              </button>
            </div>
          ) : quantization ? (
            <div className={styles.quantizationResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Readable timing ready</h4>
                  <p>
                    {quantization.project.selected_tempo_bpm?.toFixed(1)} BPM ·{" "}
                    {quantization.project.meter_numerator}/
                    {quantization.project.meter_denominator} ·{" "}
                    {quantization.project.tempo_source === "estimated"
                      ? "estimated tempo"
                      : "tempo override"}
                  </p>
                  <p>
                    Raw timing is preserved. Hands, voices, and score generation have not started.
                  </p>
                </div>
              </div>
              <dl className={styles.timingDiagnostics}>
                <div>
                  <dt>Chord groups</dt>
                  <dd>{quantization.diagnostics.chord_group_count}</dd>
                </div>
                <div>
                  <dt>Fit coverage</dt>
                  <dd>
                    {quantization.diagnostics.inlier_coverage == null
                      ? "Override"
                      : `${Math.round(quantization.diagnostics.inlier_coverage * 100)}%`}
                  </dd>
                </div>
                <div>
                  <dt>Measure origin</dt>
                  <dd>
                    {quantization.project.measure_origin_seconds?.toFixed(2)}s ·{" "}
                    {quantization.project.measure_origin_source}
                  </dd>
                </div>
                <div>
                  <dt>Processor</dt>
                  <dd>{quantization.provenance.processor_version}</dd>
                </div>
              </dl>
              <div className={styles.notePreview}>
                <h4>Symbolic timing preview</h4>
                <div className={styles.noteTableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>Pitch</th>
                        <th>Raw onset</th>
                        <th>Measure / beat</th>
                        <th>Grid onset</th>
                        <th>Grid duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quantization.preview_notes.map((note) => (
                        <tr key={note.id}>
                          <td>
                            {formatPitch(note.pitch)} <small>MIDI {note.pitch}</small>
                          </td>
                          <td>{note.raw_start_seconds.toFixed(2)}s</td>
                          <td>
                            M{note.measure_number} · beat {note.beat_in_measure.toFixed(2)}
                          </td>
                          <td>{note.symbolic_start_beats.toFixed(2)}</td>
                          <td>{note.symbolic_duration_beats.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={interpreting}
                onClick={interpretProject}
              >
                {interpreting ? "Assigning hands and staves…" : "Assign hands and staves"}
              </button>
            </div>
          ) : transcription ? (
            <div className={styles.transcriptionResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Raw transcription complete</h4>
                  <p>
                    {transcription.note_count} detected{" "}
                    {transcription.note_count === 1 ? "note" : "notes"} ·{" "}
                    {transcription.provenance.model_name}{" "}
                    {transcription.provenance.model_version}
                  </p>
                  <p>Raw MIDI and note-event JSON are saved. Quantization has not started.</p>
                </div>
              </div>
              {transcription.preview_notes.length > 0 ? (
                <div className={styles.notePreview}>
                  <h4>Detected note preview</h4>
                  <div className={styles.noteTableWrap}>
                    <table>
                      <thead>
                        <tr>
                          <th>Pitch</th>
                          <th>Onset</th>
                          <th>Duration</th>
                          <th>Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {transcription.preview_notes.map((note) => (
                          <tr key={note.id}>
                            <td>
                              {formatPitch(note.pitch)} <small>MIDI {note.pitch}</small>
                            </td>
                            <td>{note.raw_start_seconds.toFixed(2)}s</td>
                            <td>
                              {(note.raw_end_seconds - note.raw_start_seconds).toFixed(2)}s
                            </td>
                            <td>
                              {note.confidence == null
                                ? "—"
                                : `${Math.round(note.confidence * 100)}%`}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <p className={styles.emptyNotes}>No notes were detected in this source.</p>
              )}
              <form className={styles.quantizationForm} onSubmit={quantizeProject}>
                <div>
                  <label htmlFor="tempo-override">Tempo override (BPM)</label>
                  <input
                    id="tempo-override"
                    type="number"
                    min="40"
                    max="200"
                    step="0.1"
                    value={tempoOverride}
                    onChange={(event) => setTempoOverride(event.target.value)}
                    placeholder="Auto estimate"
                  />
                </div>
                <div>
                  <label htmlFor="meter">Meter</label>
                  <select
                    id="meter"
                    value={meter}
                    onChange={(event) => setMeter(event.target.value)}
                  >
                    <option value="4/4">4/4</option>
                    <option value="3/4">3/4</option>
                    <option value="2/4">2/4</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="measure-origin">Measure origin (seconds)</label>
                  <input
                    id="measure-origin"
                    type="number"
                    min="0"
                    step="0.01"
                    value={measureOrigin}
                    onChange={(event) => setMeasureOrigin(event.target.value)}
                    placeholder="First detected attack"
                  />
                </div>
                <p className={styles.help}>
                  Leave tempo blank to estimate it. If the pulse is ambiguous, Pianova will ask
                  for BPM without changing the raw transcription.
                </p>
                <button className={styles.primaryButton} disabled={quantizing}>
                  {quantizing ? "Estimating and quantizing…" : "Estimate tempo and quantize"}
                </button>
              </form>
            </div>
          ) : mediaReady ? (
            <div className={styles.mediaResult} role="status">
              <div className={styles.success}>
                <span aria-hidden="true">✓</span>
                <div>
                  <h4>Media inspected and audio normalized</h4>
                  <p>
                    {project.original_filename} · {formatDuration(project.duration_seconds ?? 0)} ·{" "}
                    {formatBytes(project.source_size_bytes ?? 0)}
                  </p>
                  <p>The normalized WAV is ready. Transcription has not started.</p>
                </div>
              </div>
              <dl className={styles.metadata}>
                <div>
                  <dt>Container</dt>
                  <dd>{project.container_format ?? "Unknown"}</dd>
                </div>
                <div>
                  <dt>Audio</dt>
                  <dd>
                    {audioStream?.codec_name ?? "Unknown codec"}
                    {audioStream?.channels ? ` · ${audioStream.channels} ch` : ""}
                  </dd>
                </div>
                <div>
                  <dt>Sample rate</dt>
                  <dd>
                    {audioStream?.sample_rate
                      ? `${(audioStream.sample_rate / 1000).toFixed(1)} kHz`
                      : "Unknown"}
                  </dd>
                </div>
                <div>
                  <dt>Video</dt>
                  <dd>
                    {videoStream
                      ? `${videoStream.codec_name ?? "Unknown"} · ${videoStream.width ?? "?"}×${videoStream.height ?? "?"}`
                      : "No video stream"}
                  </dd>
                </div>
              </dl>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={transcribing || transcriptionCapability?.state !== "available"}
                onClick={transcribeProject}
              >
                {transcribing ? "Transcribing piano…" : "Transcribe piano"}
              </button>
              {transcriptionCapability?.state === "unavailable" && (
                <p className={styles.formError}>
                  Install the isolated Basic Pitch environment for transcription.
                </p>
              )}
            </div>
          ) : project.status === "uploaded" ? (
            <div className={styles.processStep}>
              <div className={styles.sourceSummary}>
                <strong>Source file secured</strong>
                <p>
                  {project.original_filename} · {formatBytes(project.source_size_bytes ?? 0)}
                </p>
              </div>
              <p className={styles.help}>
                FFprobe will verify the media and FFmpeg will create a private normalized WAV for
                transcription. Transcription has not started.
              </p>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={processing || mediaCapability?.state !== "available"}
                onClick={processMedia}
              >
                {processing ? "Inspecting and normalizing…" : "Inspect and prepare audio"}
              </button>
              {mediaCapability?.state === "unavailable" && (
                <p className={styles.formError}>FFmpeg and FFprobe are required for this step.</p>
              )}
            </div>
          ) : (
            <form onSubmit={uploadFile} className={styles.form}>
              <div className={styles.projectSummary}>
                <span>Project</span>
                <strong>{project.title}</strong>
              </div>
              <label htmlFor="performance-file">Piano audio or video</label>
              <input
                id="performance-file"
                className={styles.fileInput}
                type="file"
                accept={config?.supported_extensions.join(",")}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <p className={styles.help}>
                MP3, WAV, M4A, MP4, or MOV · up to {config?.max_upload_mb ?? 250} MB
              </p>
              <button className={styles.primaryButton} disabled={!file || uploading}>
                {uploading ? "Securing file…" : "Upload source file"}
              </button>
            </form>
          )}
          {formError && <p className={styles.formError} role="alert">{formError}</p>}
        </section>

        <aside className={styles.statusPanel} aria-labelledby="status-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.step}>System status</p>
              <h3 id="status-title">Pipeline capabilities</h3>
            </div>
          </div>
          {!health ? (
            <p className={styles.muted}>{connectionError ? "Status unavailable" : "Checking local tools…"}</p>
          ) : (
            <ul className={styles.capabilities}>
              {health.capabilities.map((capability) => (
                <li key={capability.key}>
                  <span className={`${styles.stateDot} ${styles[capability.state]}`} />
                  <div>
                    <strong>{capability.label}</strong>
                    <p>{capability.state.replace("_", " ")}</p>
                    {capability.reason && <small>{capability.reason}</small>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      <footer className={styles.footer}>
        <span>Private by default</span>
        <span>Files stay in your Pianova workspace</span>
        <span>No cloud account required</span>
      </footer>
    </main>
  );
}
