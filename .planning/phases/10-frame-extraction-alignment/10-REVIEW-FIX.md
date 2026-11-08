---
phase: 10-frame-extraction-alignment
fixed_at: 2026-11-08T12:00:00Z
review_path: .planning/phases/10-frame-extraction-alignment/10-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-11-08T12:00:00Z
**Source review:** .planning/phases/10-frame-extraction-alignment/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (fix_scope `all`: WR-01, WR-02, IN-01..IN-04)
- Fixed: 6
- Skipped: 0
- WR-01 and WR-02 were fixed in an earlier pass (commits 9633450, 60e189c) and were not touched again. This pass fixed IN-01..IN-04.

## Fixed Issues

### WR-01: `DEFAULT_JOBS` and its comment describe an API that no longer exists (necessity)

**Status:** fixed: requires human verification (necessity finding; the resolution is a scope decision)
**Files modified:** `src/enpipe/analysis/config.py`
**Commit:** 9633450
**Applied fix:** Only the comments changed, so behaviour is the same. `DEFAULT_JOBS` was kept because `tests/unit/analysis/test_config_model.py::test_perf_constants_not_thresholds` still reads it. Its comment now says the constant is reserved for phase 11 and that no `enpipe.analysis` function has read it since plan 10-19. The `MAX_GRAB_FRAMES` comment now describes the constant as the upper bound of `count` for direct `grab_frames` callers, and notes that `grab_frame_pair` always takes one frame per side (D-27). The `build_thresholds` docstring list is still correct and was not changed.

### WR-02: K-flag hardware test has an upper bound that can fail on a correct pipeline

**Status:** fixed
**Files modified:** `tests/integration/test_hardware_real_media.py`
**Commit:** 60e189c
**Applied fix:** `_keyframe_bounds` now returns an upper bound of `2 * Σ ceil(len/gop)`, and a Russian docstring explains why. The lower and upper bounds are now two separate asserts, each with its own diagnosis. Both failure messages print the bounds, the scene starts inside the window and the K indices. `len(keys) < n_enc` and `keyframe_reasons == []` are unchanged.

### IN-01: Over-long, stale module docstring paragraph

**Status:** fixed
**Files modified:** `src/enpipe/analysis/precheck.py`
**Commit:** b4c7fe7
**Applied fix:** The `--offset` rules paragraph is re-wrapped to under 90 columns. The final rule now reads "во всех случаях K + кадры_энкода <= кадры_источника", so it no longer looks like a separate sentence. No code changed.

### IN-02: `OFFSET_*` comments name a family that has a single member

**Status:** fixed
**Files modified:** `src/enpipe/analysis/model.py`
**Commit:** 7122e87
**Applied fix:** Both `offset_source` comments (lines 213 and 265) now read `# OFFSET_SCENES | None`. The `if/else` in `report._meta_lines` was left as it is, so the golden report stays byte-identical.

### IN-03: Scratch script gaps

**Status:** fixed
**Files modified:** `scratch/analysis_pair_probe.py`
**Commit:** 367d9cd
**Applied fix:**
- The long `.scenes` auto-detection line was split by adding a local `auto_scenes` variable.
- Passing `--no-scenes` together with `--scenes` now fails through `ap.error` ("--no-scenes и --scenes взаимоисключающие", exit 2).
- Step 5 (jobs timing) is now skipped when step 4 failed or the pair was refused. A Russian message explains the skip. The `args.offset or 0` fallback is gone, so an unvalidated offset can no longer reach `grab_frames`.
- The default `--cache` is now a per-user directory, `$XDG_CACHE_HOME/enpipe/pts-cache` (or `~/.cache/enpipe/pts-cache`). It is created with mode 0700, and the script refuses to use it if it is a symlink or belongs to another user. The module docstring and `--help` explain this.
- An explicit `--cache PATH` works as before. The UAT 10 commands (`--check-only`, `--offset`, `--no-scenes`) are unchanged.
- The UAT example command on docstring line 29 is still over 100 characters. It was left whole so it can be copied as is.

### IN-04: Unneeded `noqa` on the broad catch

**Status:** fixed
**Files modified:** `src/enpipe/analysis/pair.py`
**Commit:** a22bc9e
**Applied fix:** Removed `# noqa: BLE001`. The explanatory comment about the "does not raise" contract is kept.

## Verification

All gates ran in the main checkout (`workflow.use_worktrees: false`), so no worktree was created.

- `uv run pytest -q`: 808 passed, 18 deselected.
- `uv run ruff check src tests scratch/analysis_pair_probe.py`: all checks passed.
- `uv run python scratch/analysis_pair_probe.py --help`: works and shows the new `--cache` default.
- `--no-scenes --scenes x`: refused through `ap.error`, exit code 2.
- Smoke test with `XDG_CACHE_HOME` pointed at a scratchpad directory and inputs that do not exist: the cache directory was created with mode 700 and the step flow ran as expected. The script was not run on real media under `/data`.
- Not checked: the step-5 skip after a refused pair on real media. It should be confirmed during the UAT 10 re-run on the B50.

---

_Fixed: 2026-11-08T12:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
