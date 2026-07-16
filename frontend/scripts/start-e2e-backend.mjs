import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDirectory = resolve(frontendDirectory, "../backend");
const apiPort = process.env.PIANOVA_E2E_API_PORT ?? "18080";
const python =
  process.platform === "win32"
    ? resolve(frontendDirectory, "../.venv/Scripts/python.exe")
    : resolve(frontendDirectory, "../.venv/bin/python");

const migration = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: backendDirectory,
  stdio: "inherit",
});

if (migration.status !== 0) {
  process.exit(migration.status ?? 1);
}

const backend = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", apiPort],
  { cwd: backendDirectory, stdio: "inherit" },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => backend.kill(signal));
}

backend.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 1);
  }
});
