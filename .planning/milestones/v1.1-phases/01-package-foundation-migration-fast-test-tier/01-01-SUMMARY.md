---
phase: 01-package-foundation-migration-fast-test-tier
plan: 01
subsystem: packaging
tags: [uv, uv_build, pyproject, pytest, pytest-subprocess, subprocess-seam, logging]

# Dependency graph
requires: []
provides:
  - "Installable src/-layout `enpipe` package (uv/uv_build) with committed uv.lock"
  - "enpipe.shared.proc.{run,popen} — the sole subprocess call-through seam (D-08)"
  - "enpipe.shared.logging.{die,log,step} — relocated leaf logging module (Pattern 3)"
  - "uv-based devcontainer provisioning (`uv sync --locked`)"
  - "`hardware` pytest marker registered and excluded by default (D-10 groundwork)"
affects: [01-02-detection-migration, 01-03-encoding-migration-and-tests]

# Tech tracking
tech-stack:
  added: ["uv 0.11.28", "uv_build>=0.11.28,<0.12", "pytest 9.1.1", "pytest-subprocess 1.6.0", "pytest-mock 3.15.1", "scenedetect[opencv-headless]==0.7", "numpy==2.5.1"]
  patterns: ["shared.proc subprocess seam (single choke point, no runner param)", "die() relocated to shared/logging.py to avoid keyframes.py<->pipeline.py circular import", "module docstring warns against bare `import logging` shadowing enpipe.shared.logging"]

key-files:
  created: ["pyproject.toml", "uv.lock", "src/enpipe/__init__.py", "src/enpipe/detection/__init__.py", "src/enpipe/encoding/__init__.py", "src/enpipe/shared/__init__.py", "src/enpipe/shared/proc.py", "src/enpipe/shared/logging.py"]
  modified: [".gitignore", ".devcontainer/post-create.sh"]

key-decisions:
  - "Pinned scenedetect[opencv-headless]==0.7 verbatim per RESEARCH/D-02 — confirmed the installed version string is exactly \"0.7\" (PEP 440 == matches 0.7.0 exactly), no other 0.7.x exists on PyPI for this package"
  - "Ran `uv lock` immediately after writing [project.dependencies]/[dependency-groups], before scaffolding any source files, per the plan's fail-fast lock instruction"
  - "uv 0.11.28 self-installed via the official astral.sh installer matches the uv_build pin exactly"

patterns-established:
  - "shared.proc.run/popen: zero-signature-change subprocess seam, stateless (pickle-safe for ProcessPoolExecutor workers), no shell=True, no CommandRunner injection"
  - "shared.logging: die()/log()/step()/_START leaf module with no in-package dependencies; die() prefix 'encode_scenes: ' preserved verbatim as part of the D-14 byte-identical parity surface"

requirements-completed: [PKG-02]

# Metrics
duration: ~20min
completed: 2026-07-08
---

# Phase 1 Plan 1: Package Foundation Scaffold Summary

**uv/uv_build src-layout `enpipe` package with a committed uv.lock, exact-pinned scenedetect==0.7/numpy==2.5.1, and the shared.proc/shared.logging seam modules that all migration stages will route through.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-08T11:56:00Z (approx.)
- **Completed:** 2026-07-08T12:01:16Z
- **Tasks:** 2/2 completed
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments
- `enpipe` installs from a committed `uv.lock` via `uv sync --locked`; `import enpipe` resolves from `.venv/`, not system site-packages (verified `scenedetect.__file__` path contains `/workspaces/enpipe/.venv/`)
- `enpipe.shared.proc.{run,popen}` established as the sole subprocess call-through seam — stateless, no `shell=True`, no `runner`/`CommandRunner` parameter, ready for waves 2/3 migration call sites
- `enpipe.shared.logging.{die,log,step}` relocated with the exact `"encode_scenes: "` die-message prefix preserved (D-14/D-15 parity surface)
- `.devcontainer/post-create.sh` provisioning now self-bootstraps `uv` and runs `uv sync --locked` instead of an unpinned `pip install`; GPU/npm/claude-plugin/self-check sections (1, 2, 2b, 4) left byte-unchanged
- `.gitignore` gained scratch-media ignore rules (`scratch/*.mkv`, `scratch/*.scenes`, `scratch/*.obu`) without disturbing existing entries

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold package, pin+lock deps (fail-fast), gitignore scratch media, rewrite provisioning** - `c86169b` (feat)
2. **Task 2: Create shared subprocess seam and logging leaf module** - `2cdf91f` (feat)

## Files Created/Modified
- `pyproject.toml` - `uv_build` backend, exact-pinned `scenedetect[opencv-headless]==0.7` + `numpy==2.5.1`, dev group (pytest/pytest-subprocess/pytest-mock), `hardware` pytest marker with `addopts = "-m \"not hardware\""`
- `uv.lock` - committed cross-platform lockfile pinning all 14 resolved packages (scenedetect==0.7, numpy==2.5.1, pytest==9.1.1, pytest-subprocess==1.6.0, pytest-mock==3.15.1, transitives)
- `src/enpipe/__init__.py` - `__version__ = "0.1.0"` only
- `src/enpipe/{detection,encoding,shared}/__init__.py` - empty package markers
- `src/enpipe/shared/proc.py` - `run()`/`popen()` subprocess seam, generalized from `legacy/encode_scenes.py`'s local `run()` wrapper
- `src/enpipe/shared/logging.py` - `die()`/`log()`/`step()`/`_START` relocated from `legacy/encode_scenes.py`, with a docstring warning about shadowing stdlib `logging`
- `.gitignore` - added `# enpipe scratch/parity artifacts` block (`scratch/*.mkv`, `scratch/*.scenes`, `scratch/*.obu`)
- `.devcontainer/post-create.sh` - section 3 replaced: `uv` self-bootstrap (curl installer, PATH export) + `uv sync --locked`, replacing the ad hoc `pip install "scenedetect[opencv-headless]" numpy` line

## Decisions Made
- **scenedetect pin intent:** the installed/working version string is exactly `"0.7"` (`pip show scenedetect` confirms `Version: 0.7`, i.e. PEP 440 `0.7.0`), and `pip index versions scenedetect` shows no other `0.7.x` release exists on PyPI (next-newest is `0.6.7.1`). The plain `==0.7` pin is therefore correct as written — no ambiguity to resolve.
- **Fail-fast lock ordering:** ran `uv lock` immediately after writing `pyproject.toml`'s `[project.dependencies]`/`[dependency-groups]`, before creating any `src/` files, per the plan's explicit fail-fast instruction. It resolved cleanly in <1s (15 packages), confirming all five version pins (`scenedetect==0.7`, `numpy==2.5.1`, `pytest==9.1.1`, `pytest-subprocess==1.6.0`, `pytest-mock==3.15.1`) and the `uv_build>=0.11.28,<0.12` build-backend constraint are all resolvable.
- **uv version match:** the official installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`) installed `uv 0.11.28`, matching the `uv_build>=0.11.28,<0.12` pin in `pyproject.toml` exactly — no version drift to reconcile.

## Deviations from Plan

None — plan executed exactly as written. One non-blocking finding worth recording for future phases (not a deviation, since no plan-specified behavior changed and the environment already worked this way before this phase):

**`opencv-headless` extra does not exist on `scenedetect==0.7`.** `uv lock` printed: `warning: The package \`scenedetect==0.7\` does not have an extra named \`opencv-headless\``. Confirmed via `importlib.metadata`: `scenedetect==0.7`'s actual declared extras are `pyav`, `moviepy`, `dev`, `docs`, `website` — `opencv-python` is an unconditional (non-extra) dependency, and no headless variant extra is defined by this package version. This means the resulting `uv.lock`/`uv sync` installs the full GUI-capable `opencv-python` (currently `5.0.0.93`), not `opencv-python-headless`, identical to what the pre-existing (legacy) `pip install "scenedetect[opencv-headless]" numpy` line actually did (pip silently no-ops unknown extras too — confirmed the devcontainer's prior system install also has `opencv-python`, not headless, installed). `cv2` imports successfully in this devcontainer regardless (`libGL`/`libGLX` are present, likely pulled in by the Intel media/VA-API stack), so there is no functional break. Kept `scenedetect[opencv-headless]==0.7` verbatim per RESEARCH.md/D-02 (mechanical, "whatever currently works" — the extra spec matches the exact pre-existing working configuration byte-for-byte). Flagging for awareness in case a future phase wants to explicitly swap to `opencv-python-headless` as a real dependency rather than a no-op extra.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. `uv` was self-bootstrapped via the official installer during this session (no manual step needed); the same self-bootstrap logic is now baked into `.devcontainer/post-create.sh` for future container rebuilds.

## Next Phase Readiness
- `enpipe.shared.proc` and `enpipe.shared.logging` are ready for Plan 01-02 (detection migration) and Plan 01-03 (encoding migration) to import and route every subprocess call / `die()` call through.
- The `detection/` and `encoding/` package directories exist (empty `__init__.py` only) awaiting the mechanical module split per RESEARCH.md's Mechanical Migration Map.
- No `tests/` directory or test files were created this plan — that is Plan 01-02/01-03's responsibility per the phase's wave breakdown (TEST-01/TEST-02 land alongside each migrated module).
- No blockers.

---
*Phase: 01-package-foundation-migration-fast-test-tier*
*Completed: 2026-07-08*

## Self-Check: PASSED

All 11 claimed files verified present on disk (pyproject.toml, uv.lock, .gitignore, src/enpipe/__init__.py, src/enpipe/{detection,encoding,shared}/__init__.py, src/enpipe/shared/{proc,logging}.py, .devcontainer/post-create.sh, this SUMMARY.md). All 3 claimed commits (`c86169b`, `2cdf91f`, `03b3845`) verified present in `git log --oneline --all`.
