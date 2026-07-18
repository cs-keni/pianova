# Pianova backend

The FastAPI backend owns configuration, persistence, storage, dependency/capability reporting,
media preparation, typed transcription orchestration, deterministic symbolic timing, and bounded
hand/staff interpretation. Basic Pitch and
TensorFlow run from a separate Python 3.11 environment so ordinary API development remains light.

From `backend/` with the repository `.venv` active:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --port 18080
```

The implemented API surface is `GET /api/health`, `GET /api/config`,
`GET /api/dependencies`, `POST /api/projects`, `POST /api/projects/{project_id}/upload`,
`POST /api/projects/{project_id}/process-media`, `POST /api/projects/{project_id}/transcribe`,
`POST /api/projects/{project_id}/quantize`, and
`POST /api/projects/{project_id}/interpret`. Interactive OpenAPI documentation is available at
`http://127.0.0.1:18080/docs`.

From the repository root, install and verify the isolated worker:

```powershell
py -3.11 -m venv .venv-transcription
.\.venv-transcription\Scripts\python.exe -m pip install -e ".\backend[transcription]"
.\.venv-transcription\Scripts\python.exe -m app.transcription.worker --probe
```

```powershell
ruff check .
mypy app
pytest
alembic check
```

See the root [architecture](../docs/architecture.md), [pipeline](../docs/pipeline.md), and [data model](../docs/data-model.md) documentation.
