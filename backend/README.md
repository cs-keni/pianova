# Pianova backend

The FastAPI backend owns configuration, SQLite persistence, project-scoped storage, dependency/capability reporting, and future processing stages. Use Python 3.11; the Basic Pitch transcription extra remains separate from ordinary development dependencies.

From `backend/` with the repository `.venv` active:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

The implemented API surface is `GET /api/health`, `GET /api/config`, `GET /api/dependencies`, `POST /api/projects`, and `POST /api/projects/{project_id}/upload`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

```powershell
ruff check .
mypy app
pytest
alembic check
```

See the root [architecture](../docs/architecture.md), [pipeline](../docs/pipeline.md), and [data model](../docs/data-model.md) documentation.
