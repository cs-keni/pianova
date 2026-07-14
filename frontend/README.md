# Pianova frontend

The Next.js interface displays live backend capabilities, creates a local project, and uploads its piano source. It consumes the typed HTTP contracts in `src/lib/api.ts`; it does not import backend code.

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

`npm run test:e2e` requires the repository-root Python 3.11 `.venv`. Its platform-aware launcher starts FastAPI on Windows or POSIX, starts Next.js, migrates SQLite, and verifies both valid WAV upload and mismatched-content rejection.

Copy `.env.example` to `.env.local` only when overriding the default API URL.
