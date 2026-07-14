# Current Task

## Active milestone

The `first.md` initial local scaffold and secure-upload vertical slice is complete.

## Status

All 18 first-task deliverables now have implemented or documented coverage. Pianova can report local dependencies and capabilities, create a migrated SQLite project, securely store a supported piano source, and show the result in the Next.js interface. Unfinished media, transcription, MIDI, notation, rendering, and editing stages remain explicit.

## Verified behavior

- Windows Python 3.11 environment and native Windows npm installation.
- Ruff and strict mypy pass across 24 backend source files.
- 24 pytest tests pass using temporary Alembic-migrated SQLite databases.
- `alembic check` reports no schema drift.
- ESLint and TypeScript pass.
- Four Vitest component tests pass.
- The optimized Next.js production build passes.
- Two Playwright tests pass against live FastAPI and Next.js servers: one accepts a valid WAV and one rejects mismatched contents.

## Approved decisions preserved

- Basic Pitch remains an optional Python 3.11 dependency boundary.
- Alembic owns schema creation.
- Uploads stream to project-local temporary files, enforce size while reading, validate the media signature, atomically finalize, then commit metadata with compensation cleanup.
- Cached backend capability states are the source of truth; unfinished stages report `not_implemented`.
- MusicXML must remain independent from optional MuseScore rendering.

## Next milestone

Implement media inspection and normalized WAV generation:

1. Run FFprobe with safe arguments and a bounded timeout.
2. Persist stream, codec, duration, and media metadata.
3. Display inspected metadata in the frontend.
4. Extract/normalize audio with FFmpeg into a new Artifact.
5. Test audio and video success, invalid/undecodable media, missing tools, timeouts, cleanup, and repeat processing.

Do not begin Basic Pitch integration until this media boundary is verified.

## Active blockers

None. For the `/mnt/c` checkout, use Windows Python and native Windows npm. FFmpeg must also be installed or configured in the runtime environment that launches FastAPI before the next milestone can pass real media checks.
