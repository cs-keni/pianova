# Pianova frontend

The Next.js interface displays live backend capabilities and drives the local workflow from
project creation and source upload through media preparation, transcription, readable timing,
hand/staff assignment, notation voices, and key-aware written pitch. It consumes the typed HTTP
contracts in `src/lib/api.ts`; it does not import backend code.

```powershell
npm ci
npm run dev
```

Checks:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`npm run test:e2e` requires the repository-root Python 3.11 `.venv` plus the isolated
`.venv-transcription` worker. Its platform-aware launcher starts FastAPI on Windows or POSIX,
starts Next.js, migrates SQLite, and verifies real FFprobe/FFmpeg/Basic Pitch flows through key
spelling, typed insufficient-key recovery, a resolved automatic key, video inspection, and
mismatched-content rejection.

Copy `.env.example` to `.env.local` only when overriding the default API URL.
