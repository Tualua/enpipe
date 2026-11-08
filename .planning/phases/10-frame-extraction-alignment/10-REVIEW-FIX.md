---
phase: 10-frame-extraction-alignment
fixed_at: 2026-11-08T09:21:19Z
review_path: .planning/phases/10-frame-extraction-alignment/10-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-11-08T09:21:19Z
**Source review:** .planning/phases/10-frame-extraction-alignment/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (WR-01, WR-02; the orchestrator put them in scope explicitly. WR-01 carries `Category: necessity`, which `critical_warning` would normally exclude.)
- Fixed: 2
- Skipped: 0
- Out of scope, left untouched: IN-01, IN-02, IN-03, IN-04

## Fixed Issues

### WR-01: `DEFAULT_JOBS` and its comment describe an API that no longer exists (necessity)

**Status:** fixed: requires human verification (necessity finding; the resolution is a scope decision)
**Files modified:** `src/enpipe/analysis/config.py`
**Commit:** 9633450
**Applied fix:** Only the comments changed, so behaviour is the same. `DEFAULT_JOBS` was kept because `tests/unit/analysis/test_config_model.py::test_perf_constants_not_thresholds` still reads it. Its comment no longer claims that functions take `jobs=` with this default. It now says the constant is reserved for phase 11, that no `enpipe.analysis` function reads it since plan 10-19, and why the measured value is kept. The `MAX_GRAB_FRAMES` comment now describes the constant as the upper bound of `count` for direct `grab_frames` callers. It records the memory figures (about 0.45 GB for 18 frames at 3840x2160) and notes that `grab_frame_pair` always takes one frame per side (D-27). The constants still exist, so the list in the `build_thresholds` docstring stays correct and was not changed. The golden report and the threshold-count tests are not affected.

### WR-02: K-flag hardware test has an upper bound that can fail on a correct pipeline

**Status:** fixed
**Files modified:** `tests/integration/test_hardware_real_media.py`
**Commit:** 60e189c
**Applied fix:**
- `_keyframe_bounds` now returns an upper bound of `2 * Σ ceil(len/gop)`. A Russian docstring explains why: nothing in the repo guarantees that the encoder adds no extra I/IDR frames inside `--gop-len`, the hardware changed from A380 to B50 (backlog 999.7), and the WR-10 invariant is carried by the lower bound together with `keyframe_reasons`.
- `_assert_keyframe_flags` now checks the lower and upper bounds as two separate asserts, each with its own diagnosis.
- Both failure messages print the bounds, the scene starts inside the window and the full list of K indices.
- `len(keys) < n_enc` and `keyframe_reasons == []` are unchanged.
- The `test_keyframe_flags_after_mkvmerge` docstring now describes the new bound.

## Verification

All gates ran in the main checkout (`workflow.use_worktrees: false`), so no worktree was created.

- `uv run pytest -q`: 808 passed, 18 deselected.
- `uv run ruff check src tests`: all checks passed.
- `uv run pytest --collect-only -q -o addopts="" tests/integration/test_hardware_real_media.py`: 14 tests collected, including `test_keyframe_flags_after_mkvmerge`.
- The hardware test was not run, because it needs the GPU and `/data`. The new upper bound and failure message must be confirmed on the B50 in a UAT re-run.

---

_Fixed: 2026-11-08T09:21:19Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
