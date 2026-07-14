# Current Task

## Active milestone

Initial local scaffold and vertical-slice foundation from the `first.md` "First task" section.

## Status

Checkpoints 1 and 2 are implemented. Windows Python 3.11 and native npm resolved the local toolchain blockers. The backend now has migrated SQLite models, cached dependency/capability reporting, structured errors, project creation, and streamed signature-checked atomic uploads. Ruff, strict mypy, and 13 pytest tests pass. Checkpoint 3 frontend implementation and end-to-end verification are next.

## Approved decisions

- Complete all 18 first-task deliverables in three verified checkpoints.
- Use Python 3.11; keep Basic Pitch in an optional dependency group.
- Use SQLAlchemy 2.0, Pydantic, and Alembic.
- Use streamed, size-limited, signature-checked, atomic uploads with cleanup and compensation.
- Centralize capability states and structured API errors.
- Test with pytest, migrated temporary SQLite databases, frontend unit tests, and Playwright.
- Cache dependency probes performed at application startup with bounded subprocess timeouts.

## Next action

Replace the generated frontend with the Pianova health, project-creation, and upload flow; add frontend tests; then run the complete vertical slice.

### Recommended recovery path

From Windows PowerShell, run:

```powershell
cd C:\dev\pianova\frontend
npm install
npm run lint
npm run build
```

Then install Python 3.11, return to the repository root, and follow the backend virtual-environment commands in `README.md`. If native Windows npm is not desired, clone or move the repository into the WSL ext4 filesystem and run Linux npm there.

## Active blockers

- No implementation blocker is active. Use the Windows Python 3.11 virtual environment and native Windows npm for this `/mnt/c` checkout.

## Worktree state

- The recovered scaffold is preserved in Git as WIP commit `080069a`.
- Windows Python 3.11 virtual environment and backend development dependencies are installed under ignored `.venv/`.
- Native Windows `npm ci` completed successfully; `node_modules` remains ignored.
- Backend verification: Ruff passed, strict mypy passed, and pytest passed 13 tests with one upstream test-client deprecation warning.
- Backend implementation changes are ready for a logical checkpoint commit.
