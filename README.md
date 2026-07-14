# Pianova

> Hear it. See it. Play it.

Pianova is a local-first, AI-assisted piano transcription application that will turn solo-piano audio and video into readable, editable MIDI and MusicXML. The current milestone is the application foundation: a typed FastAPI API, SQLite persistence, safe local uploads, and a Next.js interface. Transcription and score generation are not implemented yet.

## Current capabilities

- Engineering plan and compatibility baseline.
- Repository and dependency scaffold.
- Generated Next.js TypeScript source scaffold; dependency installation is currently blocked under Linux npm on the `/mnt/c` workspace.
- FFmpeg/FFprobe discovery, project creation, and secure uploads are planned but not yet implemented.

Not implemented: media normalization, transcription, MIDI, MusicXML, PDF rendering, note editing, or Synthesia analysis. Pianova must report these stages as unavailable rather than simulate success.

## Requirements

- Python 3.11.x. Python 3.12+ is intentionally unsupported for the initial Basic Pitch-compatible environment.
- Node.js 20.9 or newer; Node 20 LTS is recommended.
- FFmpeg and FFprobe on `PATH`, or configured through `.env`.
- MuseScore 4 is optional and will only be needed for later PDF/SVG rendering.

The checked environment currently has Node 20.19.5 and FFmpeg/FFprobe 6.1.1. Its default Python is 3.13.12, so install Python 3.11 before running the backend.

## Setup

Copy `.env.example` to `.env` from the repository root.

### Backend (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\backend[dev]"
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

### Backend (macOS, Linux, or WSL)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e './backend[dev]'
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

The API will run at `http://127.0.0.1:8000` and interactive documentation at `http://127.0.0.1:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Checks

```bash
cd backend
ruff check .
mypy app
pytest
alembic check
```

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

These commands become executable as their checkpoint lands. See [the reviewed implementation plan](docs/IMPLEMENTATION_PLAN.md) and [current task](docs/CURRENT_TASK.md) for exact status.

On the current WSL checkout, use native Windows npm or a WSL ext4 clone for frontend installation. Repeated Linux npm attempts under `/mnt/c` failed during package-directory renames; see [the engineering log](docs/ENGINEERING_LOG.md).

## Architecture

The browser talks to one local FastAPI process. FastAPI owns SQLite and files under `workspace/projects/<generated-project-id>/`. Processing stages will consume typed domain models and remain independent from the frontend. External programs are invoked with argument arrays, configured paths, captured output, and timeouts.

## Supported upload formats

The active milestone targets MP3, WAV, M4A, MP4, and MOV. An extension alone is never trusted; the upload service also checks a detected media signature and later FFprobe will validate decodability.

## Troubleshooting

- `python3.11: command not found`: install Python 3.11 and recreate the virtual environment.
- FFmpeg unavailable: install FFmpeg and ensure both `ffmpeg` and `ffprobe` are on `PATH`, or set explicit paths in `.env`.
- MuseScore unavailable: expected for the current milestone. Later MusicXML export will work without PDF rendering.
- Frontend cannot reach backend: confirm the API is on port 8000 and `NEXT_PUBLIC_PIANOVA_API_URL` matches it.

## Responsible use

Only process recordings you possess and are authorized to transcribe. Pianova does not download or scrape media from third-party platforms. Respect copyright and platform terms.

## Roadmap

Secure upload → media inspection → normalized WAV → real transcription → raw MIDI → quantization and hand separation → MusicXML → optional score rendering → correction tools → evaluation → Synthesia analysis.

## License

No project license has been selected yet. Do not assume redistribution rights until a license file is added.
