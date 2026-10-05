---
phase: 03-concurrency-resolution-regression-baseline-ci
plan: 01
subsystem: detection
tags: [concurrency, gil, threadpool, processpool, profiling, devcontainer, dovi_tool]

# Dependency graph
requires:
  - phase: 01-package-scaffold
    provides: src/enpipe/detection/{config,detect,parallel,stream}.py (mechanically migrated from legacy/scene_detection.py)
provides:
  - Resolved (internally consistent, evidence-backed) ThreadPoolExecutor decision in detect_scenes_parallel
  - Reproducible profiling script (scratch/profiling_debt03.py) with raw measured numbers backing the decision
  - dovi_tool devcontainer retention documented against DEBT-04, without overclaiming AV1 support
affects: [03-02-regression-baseline-ci (TEST-03, depends on this resolution landing first per D-03)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Quantified profile-then-decide gate for concurrency primitive choice (Layer-1 real-path wall-clock A/B + Layer-2 CPU-isolated microbenchmark, engagement check proving non-fallback provenance)"

key-files:
  created:
    - scratch/profiling_debt03.py
    - scratch/profiling_debt03_out.txt
  modified:
    - src/enpipe/detection/parallel.py
    - .devcontainer/Dockerfile
    - .devcontainer/post-create.sh

key-decisions:
  - "DEBT-03: measured Layer-1 (real-path, 156s clip, jobs=1 vs jobs=2, use_qsv True/False) shows jobs=2 is SLOWER than jobs=1 in both arms (0.80x, 0.67x speedup) -- fixed subprocess/boundary-finding overhead dominates at this scale"
  - "DEBT-03: measured Layer-2 (CPU-isolated microbench, pure AdaptiveDetector.process_frame, no I/O) shows ProcessPool/ThreadPool speedup ratio of 1.43x (below the 2x quantified threshold)"
  - "DEBT-03: quantified rule (switch iff Layer-1 use_qsv=False speedup <1.5x AND Layer-2 ratio >2x) evaluated: first condition true (0.67x<1.5x), second false (1.43x<2x) -> rule does not fire -> KEEP ThreadPoolExecutor, comment rewritten with measured rationale"
  - "DEBT-04: dovi_tool kept installed (not removed); documented in both Dockerfile and post-create.sh as retained for planned Phase-4 TEST-04 DV RPU-fidelity work, explicitly NOT claiming extract-rpu works on this pipeline's AV1 output (documented HEVC-only per legacy/encode_scenes.py:15-16)"

patterns-established:
  - "Engagement-check pattern: wrap a module-level worker function with a call-counter before timing a code path that has a silent fallback, assert count>1, to prove decision-backing numbers came from the real path and not a fallback"

requirements-completed: [DEBT-03, DEBT-04]

# Metrics
duration: 6min
completed: 2026-07-08
---

# Phase 3 Plan 1: Concurrency Resolution + dovi_tool Documentation Summary

**Measured (not guessed) that ThreadPoolExecutor should stay in `detect_scenes_parallel`: real-path jobs=2 is net slower than jobs=1 at this workload scale, and the CPU-isolated ProcessPool/ThreadPool speedup ratio (1.43x) falls short of the quantified 2x switch threshold — the contradictory comment is now evidence-backed and consistent with the code; `dovi_tool` stays installed with a Phase-4-scoped, non-overclaiming retention comment.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-08T15:11:48Z
- **Completed:** 2026-07-08T15:17:36Z
- **Tasks:** 3/3 completed
- **Files modified:** 5 (1 new script + 1 output artifact + 1 source file + 2 devcontainer files)

## Accomplishments

- Ran the full two-layer profiling protocol (Layer 1 real-path A/B, Layer 2 CPU-isolated microbenchmark) from RESEARCH.md on a real 156s synthetic clip, with an engagement check proving the jobs=2 numbers came from the real parallel path (not a silent fallback)
- Applied the QUANTIFIED D-02 decision rule to the measured numbers: rule does not fire, so `ThreadPoolExecutor` is kept, and the previously-contradictory comment at `parallel.py:97-99` is rewritten with the measured rationale (raw seconds + ratios embedded inline)
- Confirmed detection OUTPUT is byte-for-byte unchanged: `detect_scenes_parallel(clip, cfg, jobs=2) == detect_scenes(clip, cfg, jobs=1)` by `(start_frame, end_frame)` pairs on the profiling clip (2 real scenes, non-trivial)
- Documented `dovi_tool`'s retained purpose (planned Phase-4 TEST-04 DV RPU verification) in both `.devcontainer/Dockerfile` and `.devcontainer/post-create.sh`, explicitly avoiding the AV1-vs-HEVC overclaim flagged by RESEARCH.md Pitfall 3
- All 68 fast-tier tests continue to pass (`uv run pytest -m "not hardware"`)

## Measured Profiling Numbers (DEBT-03 decision evidence)

Reproducible via `scratch/profiling_debt03.py` (raw output captured in `scratch/profiling_debt03_out.txt`).

**Layer 1 — real-path wall-clock A/B** (156s synthetic clip, 24fps, `jobs=1` vs `jobs=2`):

| use_qsv | jobs=1 | jobs=2 | speedup | `_segment_worker` calls (engagement check) |
|---|---|---|---|---|
| True  | 10.88s | 13.57s | 0.80x | 2 (PASSED, >1) |
| False |  6.53s |  9.81s | 0.67x | 2 (PASSED, >1) |

Both arms: `jobs=2` is net SLOWER than `jobs=1` — the fixed cost of boundary-finding (extra `ffmpeg` subprocess spawns per mark) and per-segment decoder restart dominates total wall time at this clip scale, before any parallelism gain can offset it.

**Layer 2 — CPU-isolated microbenchmark** (pure `AdaptiveDetector.process_frame`, no subprocess/pipe I/O, 300 frames, 2-way split vs single-worker baseline):

| Executor | baseline (1 worker) | 2-way split | internal speedup |
|---|---|---|---|
| ThreadPoolExecutor  | 0.707s | 0.678s | 1.04x (near-zero — GIL-serialized) |
| ProcessPoolExecutor | 1.075s | 0.473s | 2.27x (real parallelism) |

**ProcessPool/ThreadPool ratio: 1.43x**

**Decision rule fired:** SWITCH iff `(Layer-1 use_qsv=False speedup < 1.5x)` AND `(Layer-2 ratio > 2x)`.
- Condition 1: `0.67x < 1.5x` → **TRUE**
- Condition 2: `1.43x < 2x` → **FALSE** (ratio does not exceed 2x)
- AND → **FALSE** → rule does not fire → **KEEP `ThreadPoolExecutor`**

Layer-1.5 real-path ProcessPool re-measurement and the second-clip pickling smoke-check (Task 2's gated pre-commit guards for a SWITCH branch) are **moot** in this run — the rule did not fire, so no swap was attempted and those guards were not exercised.

## Task Commits

Each task was committed atomically:

1. **Task 1: Profile the executor (Layer 1 wall-clock A/B + Layer 2 CPU-isolated microbenchmark)** - `d4521db` (feat)
2. **Task 2: Resolve parallel.py per the QUANTIFIED decision rule** - `dfa1f81` (fix)
3. **Task 3: Document retained dovi_tool in the devcontainer (DEBT-04)** - `9e8dcf9` (docs)

_Note: no plan-metadata commit is separate — SUMMARY/STATE/ROADMAP updates land in the final commit below._

## Files Created/Modified

- `scratch/profiling_debt03.py` - throwaway, reproducible Layer-1/Layer-2 profiling script backing the DEBT-03 decision (215 lines)
- `scratch/profiling_debt03_out.txt` - captured raw stdout from the profiling run (decision provenance artifact)
- `src/enpipe/detection/parallel.py` - rewrote the contradictory `lines 97-99` comment with the measured rationale; `ThreadPoolExecutor` unchanged (both `with` blocks); no algorithm/output change
- `.devcontainer/Dockerfile` - added DEBT-04 retained-purpose comment above the `dovi_tool` install `RUN` block (also newly tracked in git — was previously untracked in this repo, pre-existing condition unrelated to this plan)
- `.devcontainer/post-create.sh` - added a matching short comment at the `dovi_tool` self-check line

## Decisions Made

- Kept `ThreadPoolExecutor` in `detect_scenes_parallel` per the quantified D-02 rule evaluated against real measured numbers (see table above) — not a guess, not a default.
- Kept `dovi_tool` installed (not removed) per D-04's lower-churn option, with an explicit doc comment scoping its retention to planned Phase-4 work and avoiding the AV1/HEVC mechanism overclaim (Pitfall 3).
- `.devcontainer/Dockerfile` was found untracked in git prior to this plan (pre-existing repo state, not caused by this plan); since the plan required editing it, this commit brings it under version control alongside the edit rather than leaving it untracked.

## Deviations from Plan

None - plan executed exactly as written. The profiling data led to the "keep threads" branch of the decision rule, which the plan explicitly anticipated as one of two possible outcomes; the Layer-1.5/pickling-smoke-check guards for the "switch" branch were correctly skipped as moot (documented above) rather than run unnecessarily.

## Known Stubs

None. No stub/placeholder data introduced.

## Threat Flags

None. No new network endpoints, auth paths, or trust-boundary-relevant surface introduced — this plan only reworded an internal comment (evidence-backed, not functionally changed) and added documentation comments to devcontainer files. The threat register items (T-03-01, T-03-02, T-03-09, T-03-03) from the plan's `<threat_model>` were all addressed as specified: T-03-01/T-03-09 via the inline smoke check + profiling engagement check; T-03-02 via the measured numbers embedded in the comment and this SUMMARY; T-03-03 accepted as doc-only per plan.

## Self-Check

- FOUND: scratch/profiling_debt03.py
- FOUND: scratch/profiling_debt03_out.txt
- FOUND: src/enpipe/detection/parallel.py (ThreadPoolExecutor retained, comment rewritten)
- FOUND: .devcontainer/Dockerfile (dovi_tool comment present)
- FOUND: .devcontainer/post-create.sh (dovi_tool comment present)
- Commit d4521db: FOUND in git log
- Commit dfa1f81: FOUND in git log
- Commit 9e8dcf9: FOUND in git log
- `uv run pytest -m "not hardware"`: 68 passed

## Self-Check: PASSED
