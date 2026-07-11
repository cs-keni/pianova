# Pianova Engineering Instructions

## Source Of Truth

- Read `first.md` before planning or implementing work. It is the initial product specification and defines the product goals, architecture, scope order, and first milestone.
- Treat the "First task" section of `first.md` as the current implementation target until shared task documents say otherwise.
- The first milestone is a stable local scaffold and vertical-slice foundation. Do not attempt the complete transcription product in one pass.
- Preserve the core stack unless a documented compatibility problem requires a change: Next.js and TypeScript, FastAPI and Python, SQLite, FFmpeg/FFprobe, typed domain models, and local filesystem artifacts.

## Scope Discipline

- Build the audio workflow before Synthesia/computer-vision features.
- Do not add cloud deployment, authentication, payments, microservices, distributed queues, mobile apps, model training, or other deferred features unless explicitly requested.
- Never represent transcription, MusicXML generation, rendering, or another unfinished pipeline stage as working. Use explicit capability states and clear user-facing errors.
- Keep processing stages independent, typed, testable, and free of frontend dependencies or hidden global state.
- Prefer readable musical notation over mechanically preserving every expressive timing variation, as described in `first.md`.

## Delivery

- Before selecting ML and audio dependencies, inspect installed Python, Node.js, FFmpeg, FFprobe, and MuseScore versions. Check compatibility among Basic Pitch, TensorFlow, NumPy, librosa, and the chosen Python version.
- Make small, testable changes and run relevant backend and frontend checks after each milestone.
- Keep setup commands cross-platform where practical and document Windows-specific requirements explicitly.
- Use safe subprocess argument lists, `pathlib`, configurable executable paths, validated uploads, generated filenames, and project-scoped storage.
- Do not commit uploads, generated media, databases, model weights, secrets, or dependency/build output.

## Shared Context

- Keep `docs/CURRENT_TASK.md` current as milestone status changes.
- Update `docs/HANDOFF.md` after meaningful work with changes, checks, remaining work, and risks.
- Append durable decisions, compatibility findings, and recurring failures to `docs/ENGINEERING_LOG.md`.
- Update architecture, pipeline, roadmap, research, and evaluation documents whenever implementation changes their claims.

## Model And Tool Routing

- Follow the global model-and-effort routing rules. Recommend a different model or effort level only when it would materially improve cost, speed, design quality, or correctness.
- Treat Claude Code and Codex as peer engineering environments sharing repository context. Review prior work rather than assuming it is correct.
- gstack is not implicitly available merely because it is installed for Claude. In Codex, use a gstack capability only when its corresponding Codex skill/plugin is visible in the active skill list, and invoke it by that exposed skill name rather than by a Claude slash command.
