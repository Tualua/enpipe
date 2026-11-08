---
phase: 10-frame-extraction-alignment
reviewed: 2026-11-08T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - scratch/analysis_pair_probe.py
  - src/enpipe/analysis/config.py
  - src/enpipe/analysis/frames.py
  - src/enpipe/analysis/model.py
  - src/enpipe/analysis/pair.py
  - src/enpipe/analysis/precheck.py
  - src/enpipe/analysis/report.py
  - src/enpipe/analysis/seek.py
  - tests/integration/test_frames_media.py
  - tests/integration/test_hardware_real_media.py
  - tests/unit/analysis/golden/report_v1.json
  - tests/unit/analysis/test_config_model.py
  - tests/unit/analysis/test_pair.py
  - tests/unit/analysis/test_precheck.py
  - tests/unit/analysis/test_report.py
  - tests/unit/analysis/test_seek.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
  necessity: 1
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-11-08
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Review of the plans 10-19, 10-20 and 10-21 changes: removal of PSNR alignment (D-24..D-28), `--offset` allowed only with `.scenes` (D-26), `seek.py` extraction, and the hardware K-flag test.

- **Dangling references:** none. `align.py` and `test_align.py` are gone. A grep of `src`, `tests` and `scratch` finds no remaining import or use of `analysis.align`, `OFFSET_MANUAL`, `ALIGN_*`, `FileAlignment`, `PointAlignment`, `align_*` config fields, `PairCheck.alignment` or the `jobs=` argument of `check_pair_files`. `ruff check` passes on `scratch`, `src` and `tests`.
- **Rules D-05/D-06/D-07/D-09/D-16..D-20, WR-10 and WR-11:** I traced `check_offset`, `keyframe_reasons`, `scenes_reasons` and `check_pair` and found no logic defect.
  - A partial window must start and end on scene boundaries, and both reasons are collected together.
  - The `.scenes`/keyframe check is skipped when an earlier root cause exists, and it fails closed when keyframe flags are missing.
  - `--offset` without `.scenes` (`None` or `[]`) is refused, and the offset-range reason comes first.
- **`grab_frame_pair`:** it is gated on `check.ok`, bounds-checks both frame indices, and fetches exactly one frame per side, as D-27 requires. Its "does not raise" contract holds.
- **Remaining defects:** only leftovers of the refactor, and one test-robustness risk. No correctness or security defects were found in the reviewed code.

## Warnings

### WR-01: `DEFAULT_JOBS` and its comment describe an API that no longer exists (necessity)

**File:** `src/enpipe/analysis/config.py:51-60`
**Category:** necessity
**Issue:** The comment says "Функции принимают jobs параметром с дефолтом DEFAULT_JOBS, поэтому флаг --jobs подключается без правок конфига". After plan 10-19 removed `jobs=` from `check_pair_files`, no function in `src/enpipe/analysis/` takes `jobs` or reads `DEFAULT_JOBS`.
- `grep -rn "DEFAULT_JOBS\|jobs" src/enpipe/analysis/*.py` finds only the definition, this comment and the `build_thresholds` docstring.
- The scratch script uses its own `--jobs` list.

The constant is generality without an instantiation, and the comment is now false. It misleads a reader about a seam that does not exist, and the measurement (4 jobs) is already recorded in the comment.

`MAX_GRAB_FRAMES = 18` (line 67) has the same shape. Its rationale is "18 кадров … W·H·3 байт на кадр", sized for a window of neighbouring frames. The production caller `grab_frame_pair` now always passes `count=1` (D-27), so the cap guards a state the pipeline cannot reach. It is still a harmless guard for direct callers of `grab_frames`, and `tests/subprocess` use counts of 2 and 3.
**Fix:** Either delete `DEFAULT_JOBS`, or reword the comment to say it is "reserved for phase 11, not read by any function yet". Update the `MAX_GRAB_FRAMES` comment so it no longer describes a neighbour-frame window, and update the `build_thresholds` docstring list to match.

### WR-02: K-flag hardware test has an upper bound that can fail on a correct pipeline

**File:** `tests/integration/test_hardware_real_media.py:1189-1229`
**Issue:** `_keyframe_bounds` assumes the encode has at most one keyframe per `GOP_LEN` frames inside a scene: `hi = Σ ceil(len/gop)`. The bound is checked against `ffprobe` `K` flags of a real qsvencc plus mkvmerge output. Nothing in the repo shows that the Arc encoder cannot also emit an extra I/IDR frame within `--gop-len`, for example for scene-change handling, a forced IDR on a B-pyramid boundary, or a different frame type for an open-GOP `K` packet.
- The test is a hard fail with no skip (D-28), so a hardware or driver revision change (A380 to B50, backlog 999.7) could fail it even though WR-10 is fine.
- The failure message does not distinguish "assumption wrong" from "encoder emits extra keyframes".

The lower bound and the `keyframe_reasons == []` assertion are the real WR-10 invariant. The upper bound only guards against "every frame is a keyframe", which `len(keys) < n_enc` already catches.
**Fix:** Keep the lower bound and `len(keys) < n_enc`. Loosen the upper bound, for example `hi = 2 * Σ ceil(len/gop)`, or assert `len(keys) <= n_enc // 2`. Alternatively print the K indices and the bounds on failure, which the message already partly does.

## Info

### IN-01: Over-long, stale module docstring paragraph

**File:** `src/enpipe/analysis/precheck.py:17-21`
**Issue:** The `--offset` rules paragraph contains a single physical line of about 170 characters ("… K без .scenes — отказ (D-26, частичный энкод проверяется только по .scenes); всегда"). The wrapping is broken by an in-place edit, and "всегда K + кадры_энкода <= кадры_источника" now reads as a separate sentence.
**Fix:** Re-wrap the paragraph to the module's ~90 columns.

### IN-02: `OFFSET_*` comments name a family that has a single member

**File:** `src/enpipe/analysis/model.py:213`, `src/enpipe/analysis/model.py:265`
**Issue:** `offset_source: Optional[str]  # OFFSET_*` refers to a family, but only `OFFSET_SCENES` remains (`None` means no verified source). `report._meta_lines` keeps an `if/else` for a branch that has one non-trivial value.
**Fix:** Change the comments to `# OFFSET_SCENES | None`.

### IN-03: Scratch script gaps

**File:** `scratch/analysis_pair_probe.py:226-228`, `scratch/analysis_pair_probe.py:201`
**Issue:**
- The line is longer than 100 characters.
- `--no-scenes` is silently ignored when `--scenes PATH` is also given.
- With `--check-only` absent, step 5 (the jobs timing) still runs after a refused pair. It uses `chk.verdict.offset`, which on refusal can be an unvalidated user value, so `grab_frames` can fail on an out-of-range frame.
- The default `--cache /tmp/enpipe-pts-cache` is a predictable path in a world-writable directory. The file name, `<hash>.pts.json.tmp<pid>`, is also predictable, so another local user could pre-create a symlink there. This is low risk for a scratch tool.

**Fix:**
- Wrap the long line.
- Make `--no-scenes` and `--scenes` mutually exclusive via `ap.error`.
- Skip step 5 when `chk` is not ok.
- Use `tempfile.mkdtemp` or a path under the repo for the default cache.

### IN-04: Unneeded `noqa` on the broad catch

**File:** `src/enpipe/analysis/pair.py:178`
**Issue:** `except Exception:  # noqa: BLE001`. Ruff here selects only `F` and `E9`, so BLE001 is never active and the `noqa` is noise. The broad catch itself is justified by the "does not raise" contract and is documented.
**Fix:** Drop the `# noqa: BLE001` and keep the explanatory comment.

---

_Reviewed: 2026-11-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
