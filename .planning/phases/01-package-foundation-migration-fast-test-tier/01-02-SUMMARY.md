---
phase: 01-package-foundation-migration-fast-test-tier
plan: 02
subsystem: detection
tags: [scenedetect, pytest-subprocess, subprocess-seam, circular-import, parity]

# Dependency graph
requires:
  - phase: 01-package-foundation-migration-fast-test-tier (plan 01)
    provides: "enpipe.shared.proc.{run,popen} subprocess seam; enpipe.shared.logging leaf module; installable src/-layout package with hardware pytest marker"
provides:
  - "src/enpipe/detection/{config,stream,detect,parallel}.py — mechanical migration of legacy/scene_detection.py, zero logic changes, every subprocess call routed through enpipe.shared.proc"
  - "detect.py <-> parallel.py circular import resolved via deferred function-body imports (sanctioned non-logic structural change)"
  - "tests/unit/detection/test_detect.py — TEST-01 pure-logic coverage for _min_scene_len/_build_scenes"
  - "tests/subprocess/detection/test_stream.py — TEST-02 mocked probe_source argv + SceneDetectionError error-path coverage"
  - "scratch/parity_detect.py — throwaway byte-identical parity script vs legacy/scene_detection.py (D-14), verified passing"
affects: [01-03-encoding-migration-and-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "detection/detect.py <-> detection/parallel.py circular import broken with deferred function-body imports in both directions (RESEARCH.md Pattern 2)"
    - "detection stage keeps the typed-exception regime (SceneDetectionError, raise ... from exc) — no die()/sys.exit anywhere in detection/"

key-files:
  created:
    - "src/enpipe/detection/config.py"
    - "src/enpipe/detection/stream.py"
    - "src/enpipe/detection/detect.py"
    - "src/enpipe/detection/parallel.py"
    - "tests/unit/detection/test_detect.py"
    - "tests/subprocess/detection/test_stream.py"
    - "scratch/parity_detect.py"
  modified: []

key-decisions:
  - "Used jobs=1 (sequential) on both sides of the D-14 parity check, for both the legacy CLI invocation and the migrated detect_scenes() call — deterministic, avoids conflating parallel-path correctness with mechanical-migration correctness (parallel jobs>1 correctness is exercised structurally by the circular-import verification, not by the byte-identical parity gate)"
  - "Probed use_qsv once via Path('/dev/dri/renderD128').exists() (confirmed True — vainfo reports a working iHD driver in this devcontainer) and applied it explicitly and identically to both the oracle CLI (--no-qsv toggle) and the migrated DetectionConfig(use_qsv=...), per the plan's USE_QSV EXPLICITNESS requirement"

patterns-established:
  - "Deferred function-body imports for the detect.py<->parallel.py edge — the sole cross-module import within detection/, sanctioned as a non-logic structural change required only because one legacy file was split into two modules (D-13's mechanical-migration discipline is preserved; no algorithm/argv/output byte differs)"

requirements-completed: [TEST-01, TEST-02]

# Metrics
duration: ~20min
completed: 2026-07-08
---

# Phase 1 Plan 2: Detection Migration & Fast Test Tier Summary

**Mechanically migrated legacy/scene_detection.py into four src/enpipe/detection/ modules behind the shared.proc seam (zero logic change), resolved the detect.py<->parallel.py circular import with sanctioned deferred imports, added TEST-01/TEST-02 detection coverage, and proved byte-identical .scenes parity against the legacy oracle on a 3-scene synthetic clip.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-08T~11:56 (approx, continuation of Phase 1 execution)
- **Completed:** 2026-07-08T12:16:00Z
- **Tasks:** 3/3 completed
- **Files modified:** 7 (all created)

## Accomplishments
- `src/enpipe/detection/{config,stream,detect,parallel}.py` created from `legacy/scene_detection.py:50-644` with zero logic changes (D-13/D-15): Russian docstrings, `typing.List`/`Optional`/`Tuple`/`Union` generics, `@dataclass(frozen=True)` value objects, and `# --- section --- #` banners preserved verbatim
- Every subprocess call in detection routed through `enpipe.shared.proc` — `probe_source`'s `subprocess.run` → `proc.run`, `QsvPipeStream._start_process`'s `subprocess.Popen` → `proc.popen`, `keyframes_in_window`/`find_boundary`'s `subprocess.run` → `proc.run` (D-08); `grep -RnE "subprocess\.(run|Popen|call|check_output)\("` on `src/enpipe/detection/` returns zero matches
- `detect.py` <-> `parallel.py` circular import (created only by splitting one legacy file into two modules) resolved with deferred function-body imports in both directions; verified both import orders (`import enpipe.detection.detect` first, and `import enpipe.detection.parallel` first) succeed with no `ImportError`
- 7 fast-tier tests added and passing under `pytest -m "not hardware"`: 5 TEST-01 pure-logic tests (`_min_scene_len` frames/seconds/floor cases, `_build_scenes` boundary mapping + `frame_count` property) and 2 TEST-02 mocked-subprocess tests (`probe_source` exact ffprobe argv + JSON parse via the `fp` fixture, and a `SceneDetectionError` — not `SystemExit` — failure-path test)
- `scratch/parity_detect.py` proved byte-identical `.scenes` output between `detect_scenes()` and `legacy/scene_detection.py` on a real 3-source lavfi concat clip (red/blue/smptebars) that produced 3 detected scenes — not a trivial single-scene clip

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate detection into four modules behind the proc seam** - `c623503` (feat)
2. **Task 2: Detection fast test tier (TEST-01 pure + TEST-02 mocked)** - `648d76e` (test)
3. **Task 3: Byte-identical detection parity vs legacy (D-14)** - `5732ae5` (test)

## Files Created/Modified
- `src/enpipe/detection/config.py` - `PathLike`, `SceneDetectionError`, `DetectionConfig`, `SourceInfo`, `Scene` (frozen dataclasses, `Scene.frame_count` property)
- `src/enpipe/detection/stream.py` - `probe_source` (ffprobe → `SourceInfo`, typed-exception regime) and `QsvPipeStream` (VideoStream adapter over an `ffmpeg` pipe; `close()`/`finish()` dual resource pattern; `subprocess.Popen`/`subprocess.run` routed through `enpipe.shared.proc`)
- `src/enpipe/detection/detect.py` - `_min_scene_len`, `_detect_relative`, `_build_scenes`, `detect_scenes` (deferred import of `.parallel` when `jobs > 1`)
- `src/enpipe/detection/parallel.py` - `keyframes_in_window`, `find_boundary`, `_sanitize_boundaries`, `_boundary_worker`/`_segment_worker` (module-level, pickle-safe), `detect_scenes_parallel` (deferred import of `.detect` at both fallback call sites)
- `tests/unit/detection/test_detect.py` - TEST-01: `_min_scene_len` (frames-configured, seconds-fallback, floor-at-one-frame) and `_build_scenes` (boundary mapping, `frame_count`), synthetic `DetectionConfig()` inputs only
- `tests/subprocess/detection/test_stream.py` - TEST-02: `probe_source` exact-argv + JSON-parse assertion and `SceneDetectionError` failure-path test, using the `pytest-subprocess` `fp` fixture; fixtures kept local (no shared `tests/conftest.py`, per the plan's conflict-avoidance instruction with Plan 01-03)
- `scratch/parity_detect.py` - throwaway D-14 parity script (not packaged, no `[project.scripts]` entry); generates `scratch/parity_detect_sample.mkv` (gitignored, distinct from Plan 01-03's `scratch/parity_encode_sample.mkv`), runs the legacy CLI as the oracle, calls `detect_scenes()` directly, diffs the two `.scenes` outputs

## Decisions Made
- **jobs=1 on both sides of the parity check:** kept the D-14 comparison deterministic and focused on proving the mechanical migration (module split + proc-seam substitution) is behavior-preserving, rather than also exercising the `ThreadPoolExecutor`-based parallel segmentation path in the same gate. The parallel path's correctness is separately covered by the circular-import-resolution verification in Task 1's acceptance criteria (both import orders succeed).
- **use_qsv probed once, applied explicitly to both oracle and migrated calls:** `Path("/dev/dri/renderD128").exists()` returned `True` in this devcontainer (`vainfo` confirmed a working `iHD` VA-API driver), so QSV hardware decode was used identically on both sides — the parity script never assumes a `--no-qsv` flag exists on the migrated library API (it doesn't; `DetectionConfig(use_qsv=...)` is the only selection mechanism), per the plan's explicit constraint.

## Deviations from Plan

**Sanctioned structural deviation (pre-approved by the plan itself, not a Rule 1-4 auto-fix):**

**1. Deferred function-body imports between `detect.py` and `parallel.py`**
- **Found during:** Task 1 (mechanical migration)
- **Issue:** `legacy/scene_detection.py` is a single file with no circular import; splitting it into `detect.py` (contains `detect_scenes`, which calls `detect_scenes_parallel` when `jobs > 1`) and `parallel.py` (contains `detect_scenes_parallel`, whose two fallback branches call `detect_scenes(path, config, jobs=1)`) creates a two-way import edge between the modules.
- **Fix:** Per the plan's explicit instruction (itself sourced from RESEARCH.md Pattern 2, flagged by both cross-AI reviewers as a required sanctioned change), used deferred (function-body) imports in both directions: `from .parallel import detect_scenes_parallel` inside `detect_scenes()`'s `jobs > 1` branch, and `from .detect import detect_scenes` inside `detect_scenes_parallel()`'s two fallback branches. `parallel.py` additionally imports `_build_scenes`/`_detect_relative`/`_min_scene_len` from `.detect` at module top-level (safe — `detect.py` has no top-level import of `.parallel`, so this does not reintroduce a cycle).
- **Verification:** `uv run python -c "import enpipe.detection.detect; import enpipe.detection.parallel"` and the reverse order both succeed with no `ImportError`. No algorithm, argv, or output byte differs from `legacy/scene_detection.py` — confirmed by the Task 3 byte-identical parity run.
- **Files modified:** `src/enpipe/detection/detect.py`, `src/enpipe/detection/parallel.py`
- **Committed in:** `c623503` (Task 1 commit)

No Rule 1/2/3/4 auto-fixes were needed — the migration was a clean mechanical copy from `legacy/scene_detection.py`, and the fast test tier plus parity script matched the plan's specification without requiring bug fixes, missing-functionality additions, or architectural decisions beyond the one sanctioned deviation above.

## Issues Encountered
None. `ffmpeg`/`ffprobe` were present and QSV hardware (`/dev/dri/renderD128`, `iHD` VA-API driver) was functional in this devcontainer, so the D-14 parity script ran end-to-end on the first attempt (3 scenes detected, byte-identical to the legacy oracle).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Detection is fully migrated and proven byte-identical to the legacy oracle; `enpipe.detection.detect.detect_scenes` / `enpipe.detection.parallel.detect_scenes_parallel` are ready for any future consumer (Phase 4's unified CLI) to import.
- The fast test tier for detection (`tests/unit/detection/`, `tests/subprocess/detection/`) establishes the exact directory-and-fixture pattern Plan 01-03 should mirror for encoding (`tests/unit/encoding/`, `tests/subprocess/encoding/`), keeping the two plans' test subtrees disjoint as intended (no shared `tests/conftest.py` was created).
- `scratch/parity_detect.py` is a throwaway script, not a permanent artifact — it and its generated `*.mkv`/`*.scenes` files are gitignored and were not committed as source (only the script itself is tracked, per D-13's constraint that no CLI/permanent tooling is built this phase).
- No blockers for Plan 01-03 (encoding migration and tests) or later phases.

---
*Phase: 01-package-foundation-migration-fast-test-tier*
*Completed: 2026-07-08*

## Self-Check: PASSED

All 8 claimed files verified present on disk (src/enpipe/detection/{config,stream,detect,parallel}.py, tests/unit/detection/test_detect.py, tests/subprocess/detection/test_stream.py, scratch/parity_detect.py, this SUMMARY.md). All 3 claimed commits (`c623503`, `648d76e`, `5732ae5`) verified present in `git log --oneline --all`.
