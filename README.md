# Pianova

> Hear it. See it. Play it.

Pianova is a local-first, AI-assisted piano transcription application. The current working slice creates a project, securely stores an MP3, WAV, M4A, MP4, or MOV source, inspects its streams with FFprobe, and creates a normalized WAV with FFmpeg. Transcription and score generation remain explicitly unfinished.

## What works now

- FastAPI health and configuration APIs with cached FFmpeg, FFprobe, and MuseScore probes.
- SQLite projects managed through SQLAlchemy and Alembic migrations.
- Streamed uploads with a configurable byte limit, generated filenames, media-signature validation, atomic finalization, and failure cleanup.
- Typed FFprobe persistence for duration, container, bit rate, codecs, audio channels/sample rate, and video dimensions.
- Retry-safe FFmpeg normalization to mono 22.05 kHz PCM WAV with temporary-file cleanup and atomic finalization.
- A responsive Next.js interface for API status, project creation, source upload, explicit media processing, and inspected metadata.
- Structured API errors and truthful `available`, `unavailable`, and `not_implemented` capability states.
- Ruff, strict mypy, pytest, ESLint, TypeScript, Vitest, production-build, and Playwright checks.

Not implemented: transcription, MIDI, MusicXML, PDF rendering, note editing, or Synthesia analysis. The interface never presents these stages as working.

## Screenshots

The current interface is available after starting both local servers. Add stable product screenshots here after the visual design milestone; generated test traces and screenshots are intentionally ignored.

## Architecture

```text
Browser (Next.js)
  |  GET /api/health, GET /api/config, GET /api/dependencies
  |  POST /api/projects, POST /api/projects/{id}/upload
  |  POST /api/projects/{id}/process-media
  v
FastAPI
  +-- typed settings, errors, capabilities, dependency probes
  +-- SQLAlchemy sessions --> SQLite (Alembic migrations)
  +-- upload service ------> workspace/projects/<UUID>/source-<UUID>.<ext>
  +-- media service -------> FFprobe metadata + normalized-<UUID>.wav
```

FastAPI owns persistence and local artifacts. The frontend consumes typed HTTP contracts and never imports backend code. Later processing stages will consume typed musical models without depending on the UI. See [architecture](docs/architecture.md), [pipeline](docs/pipeline.md), and [data model](docs/data-model.md).

## Technology

- Next.js 16 and TypeScript 5
- React 19
- FastAPI and Pydantic 2
- SQLAlchemy 2 and Alembic
- SQLite and project-scoped filesystem storage
- FFmpeg/FFprobe for the next media milestone
- pytest, Vitest, and Playwright

## Requirements

- Python 3.11.x. Python 3.12+ is intentionally outside the initial Basic Pitch-compatible environment.
- Node.js 20.9 or newer; Node 20 LTS is recommended.
- FFmpeg and FFprobe on `PATH`, or explicit paths in `.env`.
- MuseScore 4 is optional and only needed when PDF/SVG rendering is implemented.

The verified Windows environment uses Python 3.11 through `py -3.11`. The WSL default Python may still be 3.13; do not use it for this project environment.

## Install local executables

Install FFmpeg with `winget install Gyan.FFmpeg` on Windows, `brew install ffmpeg` on macOS, or your Linux distribution package. Confirm both tools:

```bash
ffmpeg -version
ffprobe -version
```

MuseScore is optional. Install MuseScore 4 from [musescore.org](https://musescore.org/) or with `winget install MuseScore.MuseScore`. Set `PIANOVA_MUSESCORE_PATH` if it is not on `PATH`.

## Set up the project

Copy `.env.example` to `.env` from the repository root. To override the frontend API URL,
copy `frontend/.env.example` to `frontend/.env.local`. Defaults are suitable for local development.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\backend[dev]"

cd backend
alembic upgrade head
cd ..\frontend
npm ci
```

For a repository stored under `/mnt/c` in WSL, run npm through native Windows PowerShell. Linux npm previously hit Windows-filesystem package rename failures.

### macOS, Linux, or a WSL ext4 clone

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e './backend[dev]'

cd backend
alembic upgrade head
cd ../frontend
npm ci
```

The optional transcription stack is deliberately not installed by these commands.

## Run Pianova

Start the API in one terminal:

```powershell
cd C:\dev\pianova\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 18080
```

Start the frontend in another terminal:

```powershell
cd C:\dev\pianova\frontend
npm run dev
```

Open `http://localhost:3000`. API documentation is at `http://127.0.0.1:18080/docs`.

## Verify the implemented slice

Create a project in the browser, choose a supported piano file, upload it, then select **Inspect and prepare audio**. Success means the page displays duration and stream metadata and reports `Media inspected and audio normalized`. The source and generated PCM WAV are stored under `workspace/projects/<project-id>/`; transcription still does not start.

Run backend checks from `backend/`:

```powershell
..\.venv\Scripts\ruff.exe check .
..\.venv\Scripts\mypy.exe app
..\.venv\Scripts\pytest.exe
..\.venv\Scripts\alembic.exe check
```

Run frontend checks from `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Playwright starts both local servers through a platform-aware Python launcher on API port 18080,
creates real migrated projects, runs FFprobe and FFmpeg on a small WAV fixture, and rejects content
that only pretends to be WAV. Override the test API port with `PIANOVA_E2E_API_PORT`.

## Configuration

All backend variables use the `PIANOVA_` prefix. The main settings are database URL, workspace directory, FFmpeg/FFprobe/MuseScore executable paths, upload size, subprocess timeouts, normalized sample rate/channels, log level, and allowed local frontend origins. Backend defaults are in [.env.example](.env.example). `NEXT_PUBLIC_PIANOVA_API_URL` selects the frontend API base URL and belongs in `frontend/.env.local`; see [frontend/.env.example](frontend/.env.example).

## Supported source formats

MP3, WAV, M4A, MP4, and MOV are accepted. Pianova does not trust the extension alone: the upload service compares it with the detected file signature. FFprobe then proves decodability, records all streams, and requires an audio stream and positive duration before normalization.

## Limitations

- A successful upload proves safe local storage, not audio validity beyond its media signature.
- Media processing is synchronous; very long files may keep one API request open until a later worker milestone.
- MuseScore absence never blocks project creation or future MusicXML export.
- Projects cannot yet be listed, renamed, deleted, or reprocessed through the UI.
- Upload progress is represented as a pending state, not a byte-level progress bar.

## Troubleshooting

- `py -3.11` missing: install Python 3.11 and recreate `.venv`.
- Frontend shows `API offline`: confirm Uvicorn is listening on port 18080 and `NEXT_PUBLIC_PIANOVA_API_URL` matches it.
- Windows reports bind permission error 13: inspect `netsh interface ipv4 show excludedportrange protocol=tcp`; Hyper-V/WSL can reserve port 8000. Pianova uses 18080 by default to avoid the observed reserved range.
- Browser reports a CORS failure: use `localhost:3000` or `127.0.0.1:3000`, both included by default, or update `PIANOVA_CORS_ORIGINS`.
- npm rename errors under `/mnt/c`: use native Windows npm or move the clone to WSL's ext4 filesystem.
- Migration errors: run `alembic upgrade head` from `backend/` before starting the API.
- MuseScore unavailable: expected until score rendering is implemented.

## Documentation

- [Architecture](docs/architecture.md)
- [Pipeline](docs/pipeline.md)
- [Data model](docs/data-model.md)
- [Roadmap](docs/roadmap.md)
- [Research notes](docs/research-notes.md)
- [Evaluation plan](docs/evaluation.md)
- [Reviewed implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Responsible use

Only process recordings you possess or are authorized to transcribe. Pianova does not download or scrape third-party media. Respect copyright and platform terms.

## Roadmap

Secure upload and normalized media preparation are complete. Next: real transcription and raw MIDI, then readable quantization and hand separation, MusicXML, optional score rendering, correction tools, evaluation, and finally Synthesia analysis. See the [milestone roadmap](docs/roadmap.md).

## License

No project license has been selected. Do not assume redistribution rights until a license file is added.
