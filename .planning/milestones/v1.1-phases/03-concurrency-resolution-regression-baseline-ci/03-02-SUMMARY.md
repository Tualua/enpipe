---
phase: 03-concurrency-resolution-regression-baseline-ci
plan: 02
subsystem: detection
tags: [testing, regression, concurrency, ffmpeg, pytest-mock]

# Dependency graph
requires:
  - phase: 03-concurrency-resolution-regression-baseline-ci
    plan: 01
    provides: Resolved (evidence-backed) ThreadPoolExecutor in detect_scenes_parallel; profiling-derived engagement-check pattern
provides:
  - Un-fakeable parallel==sequential regression baseline (TEST-03) for detect_scenes_parallel, jobs=[2,3]
  - Pure gate-arithmetic and non_cut_offsets-merge unit coverage independent of any real media
affects: [03-03-ci-workflow (the new tests must be green in the CI workflow this plan sets up)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Executor-agnostic engagement proof: spy the deferred sequential-fallback function (not the executor/worker) to prove a silent-fallback code path did NOT fire, since the fallback always runs in the parent process before any executor/pickling -- crash-free under either concurrency primitive"
    - "Conditional worker-spy refinement, gated on the active executor class, to avoid PicklingError when an autospec'd mock would otherwise be dispatched through ProcessPoolExecutor.map"
    - "Monkeypatched media-dependent inputs (probe_source/worker functions/executor) + a synchronous in-process executor shim, to exercise real internal stitching logic deterministically with zero media/threads/processes"

key-files:
  created:
    - tests/unit/detection/test_parallel_gate.py
    - tests/integration/test_parallel_regression.py
    - tests/unit/detection/test_parallel_merge.py

key-decisions:
  - "TEST-03 clip recipe: four ~55s alternating color=red/smptebars/color=blue/smptebars segments at 24fps (~220s/5280 frames total) -- empirically verified via ffprobe to satisfy the jobs*min_span gate for both jobs=2 (2880 frames) and jobs=3 (4320 frames) with margin"
  - "Primary engagement proof is spying enpipe.detection.detect.detect_scenes (the deferred fallback target both fallback sites resolve at call time), asserting call_count==0 during the parallel run -- proven executor-agnostic and crash-free by actually running it against the real ThreadPoolExecutor-backed implementation"
  - "_segment_worker call-count spy is gated on getattr(parallel_module, 'ProcessPoolExecutor', None) is None, so it activates only under the current ThreadPoolExecutor resolution and would self-skip if 03-01 had chosen ProcessPoolExecutor instead"
  - "Empirically, on the real 220s clip, jobs=3's second interior mark (1/3 of total, ~73s) falls outside find_boundary's fixed 30s-ahead search window from the nearest real cut (~110s), so only one of the two nominal interior boundaries is actually found for jobs=3 on this specific clip -- the test still passes (parallel==sequential, no-fallback, segment_worker call_count=2>1) since none of the required invariants depend on exactly two boundaries being found, just real parallel engagement across a real jobs=[2,3] parameterization"

patterns-established: []

requirements-completed: [TEST-03]

# Metrics
duration: ~14min
completed: 2026-07-08
---

# Phase 3 Plan 2: Regression Baseline (TEST-03) Summary

**Captured the parallel==sequential regression baseline against the DEBT-03-resolved (ThreadPoolExecutor) implementation with a REQUIRED, executor-agnostic engagement proof (the deferred sequential fallback was never invoked) so the test cannot pass vacuously via either of `detect_scenes_parallel`'s two silent fallback paths, plus a pure gate-arithmetic guard and a focused unit test of the previously-unexercised `non_cut_offsets` boundary-merge logic.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-07-08T15:15:00Z (approx.)
- **Completed:** 2026-07-08T15:29:58Z
- **Tasks:** 3/3 completed
- **Files modified:** 3 (all new test files)

## Accomplishments

- Task 1: `tests/unit/detection/test_parallel_gate.py` -- pure, no-media unit test that independently re-derives `min_span = max(2*_min_scene_len(cfg, fps), round(60*fps))` and proves the TEST-03 regression clip's parameters (220s @ 24fps) clear the fallback gate for both `jobs=2` and `jobs=3`, plus a negative case documenting the trap (a 30s clip fails the gate).
- Task 2: `tests/integration/test_parallel_regression.py` -- generates a real ~220s four-segment synthetic clip via `ffmpeg`, asserts `detect_scenes_parallel(clip, jobs) == detect_scenes(clip, jobs=1)` by `(start_frame, end_frame)` pairs for `jobs=[2, 3]`, with:
  - a RUNTIME `ffprobe`-derived frame-count guard (`actual_total_frames >= jobs*min_span`) run *before* the equality assertion, so a real ffmpeg output shorter than intended fails loudly;
  - a REQUIRED, executor-agnostic engagement proof: `mocker.spy(enpipe.detection.detect, "detect_scenes")` asserting `call_count == 0` during the parallel call (both fallback sites resolve this deferred import at call time, always in the parent process, so this proves neither fallback fired, under either concurrency primitive);
  - a CONDITIONAL, ThreadPool-only refinement: `_segment_worker` spy asserting `call_count > 1`, gated on `getattr(parallel_module, "ProcessPoolExecutor", None) is None` to avoid a PicklingError if a future DEBT-03 resolution switches executors;
  - `DetectionConfig(use_qsv=Path("/dev/dri/renderD128").exists())` and no GPU-absence skip marker of any kind.
- Task 3: `tests/unit/detection/test_parallel_merge.py` -- direct pure-function coverage of `_sanitize_boundaries` (sort/dedup/clamp/is_cut-preservation), plus the `non_cut_offsets` stitch (parallel.py:149-176) driven for real via monkeypatched `probe_source`/`_boundary_worker`/`_segment_worker` and a synchronous in-process executor shim (no media, no real threads/processes/pickling) -- one test proving the merge fires and stitches across a non-cut boundary, one control proving it does NOT fire when every interior boundary is a real cut.
- Verified empirically (not assumed) end-to-end against the real hardware in this devcontainer (`/dev/dri/renderD128` present, `use_qsv=True`): `detect_scenes(clip, jobs=1)` and `detect_scenes_parallel(clip, jobs=2/3)` both detect the same 4 scenes at the exact segment boundaries (0, 1320, 2640, 3960, 5280).
- Full default (`not hardware`) tier: 77 passed (68 pre-existing + 3 gate + 2 regression + 4 merge).

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure gate-arithmetic unit test** - `e12ed59` (test)
2. **Task 2: Real-clip parallel==sequential regression test with direct engagement assertion** - `76f8525` (test)
3. **Task 3: Pure unit test for `_sanitize_boundaries` + the `non_cut_offsets` merge** - `1e81582` (test)

_Note: no plan-metadata commit is separate -- SUMMARY/STATE/ROADMAP updates land in the final commit below._

## Files Created/Modified

- `tests/unit/detection/test_parallel_gate.py` (55 lines) -- pure gate-arithmetic unit test, `jobs=[2,3]` parameterized, plus a negative/trap-documenting case.
- `tests/integration/test_parallel_regression.py` (169 lines) -- real-clip parallel==sequential regression test with runtime ffprobe guard and dual (required + conditional) engagement assertions.
- `tests/unit/detection/test_parallel_merge.py` (156 lines) -- pure unit coverage of `_sanitize_boundaries` and the `non_cut_offsets` merge, using monkeypatching + a synchronous executor shim.

## Decisions Made

- Used the four-segment (`color=red`/`smptebars`/`color=blue`/`smptebars`) `~55s` clip recipe from the plan verbatim; empirically confirmed via `ffprobe -count_frames` that it produces exactly 5280 frames (220s @ 24fps), clearing both `jobs=2` (2880-frame requirement) and `jobs=3` (4320-frame requirement) gates with margin.
- Chose `ffprobe -of json` (not `-of default=...`) for the runtime frame-count probe after discovering empirically that `ffprobe`'s `default` writer does not guarantee field-name-to-output-position ordering matches the `-show_entries` argument order -- JSON output is unambiguous and matches the existing `probe_source` pattern in `src/enpipe/detection/stream.py`.
- Removed all mention of the word "skipif" from `test_parallel_regression.py`, including in prose/comments (not just as an actual marker), per the plan's literal `! grep -q "skipif"` acceptance check -- ffmpeg is treated as an always-present core dependency in this environment (consistent with the rest of the codebase), so no skip logic of any kind gates this test.
- Did not add a `pytest.mark.skipif` on `ffmpeg`/`libx264` absence (unlike the pattern in `tests/integration/test_ebml_cross_validation.py`) specifically because this plan's acceptance criteria forbid any "skipif" occurrence in the file -- ffmpeg absence would surface as a loud `CalledProcessError` instead, which matches the plan's "fail loudly, not silently" philosophy for this test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect `smptebars` lavfi filter-string syntax**
- **Found during:** Task 2, first test run
- **Issue:** Initial draft used `smptebars:duration=...` (colon after filter name), which ffmpeg rejected (exit 234) -- `smptebars` has no positional first argument, so its parameter list must be introduced with `=` (`smptebars=duration=...`), matching `scratch/parity_detect.py`'s existing pattern.
- **Fix:** Changed the two `smptebars` segment strings in `_SEGMENTS` from `smptebars:duration=...` to `smptebars=duration=...`.
- **Files modified:** `tests/integration/test_parallel_regression.py`
- **Commit:** `76f8525` (fixed before the task's single commit; no separate commit needed)

**2. [Rule 1 - Bug] Removed docstring occurrence of "skipif" tripping the literal acceptance grep**
- **Found during:** Task 2, acceptance-criteria verification
- **Issue:** The module docstring's prose ("no pytest.mark.skipif on GPU/ffmpeg absence") contained the literal substring `skipif`, which the plan's `! grep -q "skipif"` acceptance check treats as present regardless of context (code vs. prose).
- **Fix:** Reworded the docstring to "no GPU-absence skip marker of any kind" (no `skipif` substring), preserving the same meaning.
- **Files modified:** `tests/integration/test_parallel_regression.py`
- **Commit:** `76f8525` (fixed before the task's single commit; no separate commit needed)

No architectural deviations (Rule 4). No auth gates encountered.

## Known Stubs

None. All three test files exercise real code paths (either the real `detect_scenes_parallel`/`detect_scenes` against real generated media, or the real `_sanitize_boundaries`/merge logic against monkeypatched-but-real function calls). No hardcoded empty/placeholder outputs.

## Threat Flags

None. This plan adds test-only files; no new network endpoints, auth paths, file-access patterns, or schema changes at a trust boundary were introduced. The threat register items from the plan's `<threat_model>` (T-03-04, T-03-05, T-03-06) were addressed as specified: T-03-04 via the pure gate test (Task 1) plus the runtime ffprobe guard and dual engagement assertions (Task 2); T-03-05 via the pure merge test (Task 3) and the `jobs=[2,3]` parameterization in Task 2; T-03-06 via `DetectionConfig(use_qsv=Path(...).exists())` with no skip logic.

## Self-Check

- FOUND: tests/unit/detection/test_parallel_gate.py
- FOUND: tests/integration/test_parallel_regression.py
- FOUND: tests/unit/detection/test_parallel_merge.py
- Commit e12ed59: FOUND in git log
- Commit 76f8525: FOUND in git log
- Commit 1e81582: FOUND in git log
- `uv run pytest -m "not hardware"`: 77 passed
- No unexpected file deletions across the three task commits (`git diff --diff-filter=D`: empty)

## Self-Check: PASSED
