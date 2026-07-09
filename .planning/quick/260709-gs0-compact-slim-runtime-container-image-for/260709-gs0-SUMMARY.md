---
phase: quick-260709-gs0
plan: 01
subsystem: infra
tags: [docker, uv, qsvencc, intel-arc, qsv, av1, packaging]

requires:
  - phase: 04-01 (unified CLI entry point)
    provides: console_script `enpipe` (pyproject.toml `[project.scripts]`), commands detect/encode/run
provides:
  - Root multi-stage `Dockerfile` (builder: `uv sync --frozen --no-dev --no-editable`; runtime: media stack + venv copy)
  - `.dockerignore` minimizing build context to pyproject.toml/uv.lock/src
  - `docker/README.md` build/run instructions with GPU passthrough and metrics caveat
affects: [deployment, packaging]

tech-stack:
  added: []
  patterns:
    - "Slim production image separate from `.devcontainer/Dockerfile` (dev vs runtime image split)"
    - "Builder ships non-editable venv via `uv sync --frozen --no-dev --no-editable` into `/opt/venv`, copied whole into runtime stage"

key-files:
  created:
    - Dockerfile
    - .dockerignore
    - docker/README.md
  modified: []

key-decisions:
  - "Media recipes (apt block, qsvencc dpkg-repack trick, dovi_tool musl binary) copied verbatim from .devcontainer/Dockerfile, only dropping tmux and the podman apt-sandbox fix (devcontainer-feature-only concern)"
  - "dovi_tool kept installed per user's earlier DEBT-04 decision, same rationale note carried over in condensed form"
  - "uv binary pulled from ghcr.io/astral-sh/uv:latest with an explicit in-Dockerfile comment recommending digest-pinning for production"

requirements-completed: [QUICK-260709-gs0]

duration: 6min
completed: 2026-07-09
---

# Quick Task 260709-gs0: Compact slim runtime container image Summary

**Root multi-stage `Dockerfile` (builder: `uv sync --frozen --no-dev --no-editable` into `/opt/venv`; runtime: python:3.12-slim-trixie + iHD/oneVPL/ffmpeg/mkvtoolnix/qsvencc/dovi_tool, verbatim from `.devcontainer/Dockerfile` minus dev tooling) plus `.dockerignore` and `docker/README.md`.**

## Performance

- **Duration:** ~6 min (commits at 12:11:29Z and 12:12:03Z; Task 3 verification-only, no commit)
- **Started:** 2026-07-09T12:05:00Z (approx)
- **Completed:** 2026-07-09T12:12:03Z
- **Tasks:** 3 (2 committed, 1 verification-only)
- **Files modified:** 3 (Dockerfile, .dockerignore, docker/README.md)

## Accomplishments

- Root `Dockerfile`: two-stage build. Builder stage (`FROM python:3.12-slim-trixie AS builder`) installs enpipe as a real non-editable wheel into `/opt/venv` via `uv sync --frozen --no-dev --no-editable`, using the pinned `uv.lock`. Runtime stage (second `FROM python:3.12-slim-trixie`, no `AS`) carries the Intel Arc media stack (contrib/non-free apt sources, `intel-media-va-driver-non-free`/`libva2`/`libva-drm2`/`vainfo`/`libvpl2`/`ocl-icd-libopencl1`/`ffmpeg`/`mkvtoolnix`, `libmfx-gen1.2`/`libmfxgen1`/`libmfx-gen1` fallback loop, `qsvencc` via the dpkg-repack Depends-strip trick, `dovi_tool` musl binary) and copies the venv in, without any dev tooling (no node/tmux/git/build-essential/AI-CLI/GSD).
- `.dockerignore` keeps the build context to `pyproject.toml`/`uv.lock`/`src/`, excluding `.git`, `.planning`, `tests`, `legacy`, `.devcontainer`, `scratch`, `docker`, caches, and doc files.
- `docker/README.md` documents `docker build`/`podman build`, an example `docker run --device /dev/dri --group-add $(stat -c '%g' /dev/dri/renderD128) ...` invocation with per-flag rationale, the `--no-metrics` caveat (OpenCL VPP filters — `intel-opencl-icd` absent on trixie), the trixie base rationale, and an explicit note that the image was not built in this environment.
- Verified (without Docker, which is unavailable in this environment): reproduced the exact builder command `uv sync --frozen --no-dev --no-editable` into a throwaway `/tmp` venv outside the repo; `enpipe --help` and `enpipe run --help` both exit 0 and show the `detect`/`encode`/`run` subcommands and `--no-metrics` flag; confirmed the install is non-editable (no `__editable__.enpipe*.pth` in site-packages — `enpipe` is a real installed package directory); temp venv removed. Regression suite `uv run pytest -m "not hardware" -q` passes: 153 passed, 6 deselected.

## Task Commits

Each task was committed atomically:

1. **Task 1: Multi-stage Dockerfile + .dockerignore** - `cf8ce1e` (feat)
2. **Task 2: docker/README.md build/run instructions** - `cbae949` (docs)
3. **Task 3: Local clean-install + regression verification** - no commit (verification-only, per plan instructions; temp `/tmp/enpipe-gs0-venv` created and removed, nothing in-repo changed)

**Plan metadata:** (this SUMMARY commit, made by orchestrator after this report)

## Files Created/Modified

- `Dockerfile` - Two-stage slim production image (builder: uv sync into /opt/venv; runtime: Intel Arc media stack + venv copy + ENTRYPOINT ["enpipe"])
- `.dockerignore` - Minimizes build context to pyproject.toml/uv.lock/src, excludes dev/planning/test artifacts
- `docker/README.md` - Build/run instructions, GPU device passthrough explanation, metrics caveat, base-image rationale, honest note that build was not exercised here

## Decisions Made

- Media-stack recipes (apt contrib/non-free enablement, media package list + libmfx fallback loop, qsvencc dpkg-repack Depends-strip, dovi_tool musl-binary install) copied verbatim from `.devcontainer/Dockerfile` per plan's explicit "reuse verbatim, do not rewrite" instruction — only `tmux` was dropped (interactive dev tool, unneeded in production) and the podman/buildah apt-sandbox fix was not carried over (it addresses a devcontainer-features-specific apt privilege-drop issue that doesn't apply here, since this Dockerfile has no devcontainer features).
- `dovi_tool` retained in the runtime image, mirroring the DEBT-04 decision already recorded in `.devcontainer/Dockerfile` and `STATE.md` — condensed rationale comment carried into the new Dockerfile rather than the full explanation, per plan instruction.
- `uv` binary is pulled from `ghcr.io/astral-sh/uv:latest` (not digest-pinned) with an explicit Dockerfile comment recommending digest-pinning for production use, per the plan's threat-model disposition (T-gs0-02, accepted risk).

## Deviations from Plan

None - plan executed exactly as written. All structural verification checks (Task 1's Python structural-marker script, Task 2's README grep checks, Task 3's builder-command reproduction + non-editable proof + pytest regression) passed on the first attempt with no fixes needed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. However, per the plan's explicit environment boundary: **the container image itself was NOT built in this environment** (no `docker`/`podman`/`buildah`/`hadolint` available here). The user must run `docker build -t enpipe:slim .` (or `podman build`) on a host with Docker/Podman and an Intel Arc GPU, then verify the GPU-accelerated run per `docker/README.md`'s example command. Static/structural validation of the Dockerfile and a clean-room reproduction of the `uv sync --frozen --no-dev --no-editable` builder step (both stages logically exercised as far as possible without a container runtime) were performed instead, as documented above.

## Next Phase Readiness

- `Dockerfile`, `.dockerignore`, and `docker/README.md` are ready for the user to build and run on a GPU-equipped host.
- `.devcontainer/Dockerfile`, `pyproject.toml`, `src/`, and `legacy/` were not touched by this task.
- No blockers for follow-up work; actual `docker build` + hardware GPU run remains a manual step for the user, as this environment has no container runtime and no `/dev/dri` device is exercised inside a container here.

---
*Phase: quick-260709-gs0*
*Completed: 2026-07-09*

## Self-Check: PASSED

- FOUND: /workspaces/enpipe/Dockerfile
- FOUND: /workspaces/enpipe/.dockerignore
- FOUND: /workspaces/enpipe/docker/README.md
- FOUND: /workspaces/enpipe/.planning/quick/260709-gs0-compact-slim-runtime-container-image-for/260709-gs0-SUMMARY.md
- FOUND commit: cf8ce1e
- FOUND commit: cbae949
