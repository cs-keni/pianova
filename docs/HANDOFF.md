# Handoff

## What changed

- Read and reviewed the full `first.md` specification.
- Inspected the initial environment and found Python 3.13.12, Node 20.19.5, npm 11.14.1, FFmpeg/FFprobe 6.1.1, and no MuseScore executable.
- Completed an interactive gstack engineering-plan review and recorded approved architecture, testing, upload-safety, and performance decisions.
- Added `docs/IMPLEMENTATION_PLAN.md` and initialized shared task context.
- Attempted the default outside-voice review with Claude CLI. The first call returned no response and the retry never read the plan, so no external findings were incorporated.
- Began Checkpoint 1: added environment and Python-version contracts, backend dependency manifest, root README, ignore rules, workspace/sample placeholders, and generated the Next.js TypeScript source scaffold.
- Investigated failed frontend dependency installation. Directory ownership and mode are correct, no Node process remains, and direct renames succeed after npm exits. Clean installs still fail while npm renames `typescript` or `next` on the `/mnt/c` filesystem.
- Recovered context on 2026-07-14 and found that a later July 11 attempt produced `frontend/package-lock.json` and `node_modules` after this handoff was originally written. Dependency inspection succeeds and TypeScript checking passes, but ESLint times out on the mounted Windows filesystem.

## Checks run

- Repository status and file inventory.
- Local executable/version detection.
- Primary-source compatibility research for Basic Pitch, TensorFlow, librosa, and Next.js.
- `git diff --check` passed after scaffolding.
- Frontend dependency inspection succeeds and TypeScript checking passes. A bounded ESLint run started but did not complete within 45 seconds.
- Frontend installation attempts failed with the WSL/NTFS errors recorded below; the partial `node_modules` tree was removed afterward.
- Backend lint, typing, migrations, and tests were not run because Python 3.11 is unavailable and application code has not landed.

## Remaining work

1. Install Python 3.11 and create the project virtual environment.
2. Verify or regenerate frontend dependencies with native Windows tooling, or move/clone the repository to the WSL ext4 filesystem before relying on Linux npm.
3. Finish Checkpoint 1 verification and then implement Checkpoints 2 and 3.
4. Refresh this handoff with exact results and remaining risks.

## Worktree and delivery state

- Changes are uncommitted and unpushed.
- `frontend/package-lock.json` is intended for commit; generated dependency directories, uploads, databases, and media artifacts are not.
- Do not treat Checkpoint 1 as complete until frontend lint/build and the documented Python 3.11 setup have been verified.

## Known risks

- Python 3.11 is required for the chosen Basic Pitch-compatible baseline but is not the current default interpreter.
- Basic Pitch 0.4.0 is older than the surrounding audio ecosystem; its transitive pins must be tested in an optional environment before integration.
- MuseScore is absent, so later PDF rendering must degrade without failing MusicXML generation.
- Linux npm against this repository's `/mnt/c` path currently cannot complete package-directory renames reliably. Repeated blind retries are unsafe and have been stopped.
