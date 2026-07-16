"use client";

import { FormEvent, useEffect, useState } from "react";
import styles from "./page.module.css";
import {
  ApiError,
  api,
  type ConfigResponse,
  type HealthResponse,
  type Project,
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

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something unexpected went wrong.";
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

  const mediaCapability = health?.capabilities.find(
    (capability) => capability.key === "media_normalization",
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
                Step {mediaReady ? "3" : project ? "2" : "1"} of 3
              </p>
              <h3 id="workflow-title">
                {mediaReady
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
