# Current Task

## Active milestone

Initial local scaffold and vertical-slice foundation from the `first.md` "First task" section.

## Status

Engineering plan reviewed and cleared. Checkpoint 1 is in progress: repository configuration, backend manifest, root README, workspace boundaries, and the Next.js source scaffold exist. Python 3.11 is still missing. A frontend lockfile and dependency tree now exist, TypeScript checking passes, and dependency inspection succeeds, but ESLint did not complete within 45 seconds on the WSL-mounted Windows filesystem.

## Approved decisions

- Complete all 18 first-task deliverables in three verified checkpoints.
- Use Python 3.11; keep Basic Pitch in an optional dependency group.
- Use SQLAlchemy 2.0, Pydantic, and Alembic.
- Use streamed, size-limited, signature-checked, atomic uploads with cleanup and compensation.
- Centralize capability states and structured API errors.
- Test with pytest, migrated temporary SQLite databases, frontend unit tests, and Playwright.
- Cache dependency probes performed at application startup with bounded subprocess timeouts.

## Next action

Preserve the scaffold in Git, resolve the Python 3.11 and frontend lint/build blockers, finish Checkpoint 1 checks, then begin the backend implementation.

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

- Python 3.11 is not installed; the system default is Python 3.13.12.
- Linux npm previously failed while renaming package directories under `/mnt/c/.../frontend/node_modules` (`EACCES`/`ENOTEMPTY`). A lockfile and dependency tree were later produced, but ESLint still stalls on this filesystem and the install has not passed a clean build verification.

## Worktree state

- All scaffold and documentation files are currently uncommitted.
- `frontend/package-lock.json` and `frontend/node_modules` were produced after the previous handoff; `node_modules` remains ignored.
- `npm ls --depth=0` succeeds with one extraneous package (`@emnapi/runtime`).
- `npx tsc --noEmit --incremental false` passes; `npx eslint src --no-cache` timed out after 45 seconds without reporting a code error.
- No commit or push was made because runtime checks could not complete.
