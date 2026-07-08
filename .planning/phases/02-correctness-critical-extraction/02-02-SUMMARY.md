---
phase: 02-correctness-critical-extraction
plan: 02
subsystem: encoding
tags: [pipeline, keyframes, seek-trim, high-water-mark, pytest, mocked-integration]

# Dependency graph
requires:
  - phase: 02-correctness-critical-extraction
    plan: 01
    provides: enpipe.mkv.ebml (pure EBML/Cues parser), keyframe_table_cues as a thin I/O shell, the fast test tier at 53 passing tests
provides:
  - "enpipe.encoding.keyframes.compute_chunk_seek_trim(table, s, e) -> (seek, trim): pure per-scene seek/trim math, co-located with kf_before/fmt_seek"
  - "enpipe.encoding.pipeline.contiguous_run(next_append, ready) -> List[int]: pure high-water-mark flush-ordering decision, module-level"
  - "flush_appends() as a thin I/O shell consuming contiguous_run's result"
  - "Direct unit tests over synthetic edge cases for both pure functions (frame-0/on/off-keyframe boundaries; gap/all-consumed/dict-vs-set/no-mutation contiguous_run cases)"
  - "A non-hardware mocked run_encode wiring test proving movie.obu == scene-ordered concatenation AND chunk_command seek/trim == compute_chunk_seek_trim"
affects: [phase-3-threadpool-processpool-resolution]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-arithmetic extraction behind a thin orchestration shell: compute_chunk_seek_trim/contiguous_run take only in-memory values, do no I/O; pipeline.py's run_encode/flush_appends stay the sole owners of file I/O and ThreadPoolExecutor orchestration"
    - "Mocked run_encode wiring test: patch every external boundary (shutil.which, probe_fps, keyframe_table, detect_hdr, read_scenes, write_metrics_csv, count_frames, encode_chunk, chunk_command, _proc.run) on the pipeline module object, then assert on the real output artifact (movie.obu bytes) and recorded call arguments — proves wiring correctness without any subprocess or hardware dependency"

key-files:
  created:
    - tests/unit/encoding/test_pipeline_ordering.py
    - tests/unit/encoding/test_pipeline_wiring.py
  modified:
    - src/enpipe/encoding/keyframes.py
    - src/enpipe/encoding/pipeline.py
    - tests/unit/encoding/test_keyframes.py

key-decisions:
  - "Used the 2-tuple (seek, trim) return for compute_chunk_seek_trim per D-04's explicit minimal-diff allowance, since the pre-extraction call site never used kf_frame after computing trim"
  - "contiguous_run annotated Union[Dict[int, int], Set[int]] using typing generics (D-11), not PEP 604 `|`, matching the rest of the codebase's typing style"
  - "chunk_command was wrapped with unittest.mock.Mock(side_effect=real_chunk_command) rather than replaced outright, so the wiring test exercises the real command-building logic while still recording the (seek, trim) arguments it received"

requirements-completed: [DEBT-02]

# Metrics
duration: 5min
completed: 2026-07-08
---

# Phase 2 Plan 2: Seek/Trim and Flush-Ordering Extraction Summary

**Extracted the two correctness-critical arithmetic pieces flagged by PITFALLS.md as the highest silent-corruption risk — per-scene seek/trim computation and high-water-mark flush ordering — out of `pipeline.py`'s inline code into pure, directly unit-tested functions (`compute_chunk_seek_trim` in `keyframes.py`, `contiguous_run` in `pipeline.py`), with zero behavior change proven by 14 new unit tests, a fully-mocked `run_encode` wiring test, and a byte-identical re-run of the hardware `scratch/parity_encode.py` gate.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-08T13:49:17Z
- **Completed:** 2026-07-08T13:54:23Z
- **Tasks:** 3 completed
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `compute_chunk_seek_trim(table, s, e) -> (seek, trim)` added to `encoding/keyframes.py` next to `kf_before`/`fmt_seek` (D-04), extracted verbatim from `pipeline.py`'s inline three-line seek/trim math — `kf_before`/`fmt_seek` themselves untouched (D-06)
- `contiguous_run(next_append, ready)` added module-level in `encoding/pipeline.py` (D-05): a pure function returning a concrete `List[int]` (not a generator, per Pitfall 3), annotated `Union[Dict[int, int], Set[int]]` with `typing` generics (D-11, no PEP 604 `|`); does not mutate `ready` or advance `next_append`
- Both `pipeline.py` call sites rewired with no behavior change: the chunk-task build loop now calls `compute_chunk_seek_trim(table, s, e)`; `flush_appends()` is now a thin I/O shell iterating `contiguous_run(next_append, ready)` and preserving the exact `copyfileobj`/`unlink`/`next_append` advance semantics
- `tests/unit/encoding/test_keyframes.py` gained 3 `compute_chunk_seek_trim` tests covering frame-0/on/off-keyframe boundaries with exact `(seek, trim)` string assertions
- `tests/unit/encoding/test_pipeline_ordering.py` (new) covers all 8 `contiguous_run` edge-case rows from RESEARCH.md's table plus dict-input, all-consumed, and no-mutation (both dict and set) guarantees — 10 tests
- `tests/unit/encoding/test_pipeline_wiring.py` (new) drives a fully-mocked `run_encode(args)` (every external boundary patched: tool preflight, `probe_fps`, `keyframe_table`, `detect_hdr`, `read_scenes`, `write_metrics_csv`, `count_frames`, `encode_chunk`, `chunk_command`, `_proc.run`) and asserts `movie.obu` equals the scene-ordered concatenation of canned per-chunk bytes AND that every `chunk_command` call's `(seek, trim)` matches `compute_chunk_seek_trim(table, s, e)` — the hardware-independent backstop for DEBT-02
- Full fast test tier: 67 tests pass (53 from 02-01 + 14 new), zero collection errors
- Re-ran the UNCHANGED Phase-1 hardware parity gate `scratch/parity_encode.py`: Arc hardware was present in this devcontainer, `qsvencc` proved deterministic, and the migrated `run_encode` (now routing through `compute_chunk_seek_trim`/`contiguous_run`) produced a **byte-identical** pre-mux `movie.obu` vs the `legacy/` oracle — the primary gate — plus matching final `.mkv` frame counts (240 = 240) on the secondary gate. `PARITY OK`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract compute_chunk_seek_trim and contiguous_run, rewire the two pipeline call sites** - `384f3e0` (refactor)
2. **Task 2: Unit-test both pure functions, add the non-hardware mocked run_encode wiring proof, and confirm the full regression backstop** - `675833f` (test)
3. **Task 3: Re-run the Phase-1 encode-parity gate to prove byte-identical movie.obu** - no commit (verification-only; `scratch/parity_encode.py` re-run unchanged, confirmed zero diff via `git status`/`git diff --stat`)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `src/enpipe/encoding/keyframes.py` - added `compute_chunk_seek_trim` co-located with `kf_before`/`fmt_seek`
- `src/enpipe/encoding/pipeline.py` - added module-level `contiguous_run`; rewired the chunk-task build loop and `flush_appends()` to use the two extracted pure functions; import list updated (`compute_chunk_seek_trim` replaces direct `fmt_seek`/`kf_before` imports; `Set`/`Union` added to the `typing` import)
- `tests/unit/encoding/test_keyframes.py` - added 3 `compute_chunk_seek_trim` tests, import line extended
- `tests/unit/encoding/test_pipeline_ordering.py` - new, 10 `contiguous_run` edge-case tests
- `tests/unit/encoding/test_pipeline_wiring.py` - new, 1 fully-mocked `run_encode` wiring test

## Decisions Made
- 2-tuple `(seek, trim)` return for `compute_chunk_seek_trim`, matching D-04's stated minimal-diff allowance (the pre-extraction call site didn't retain `kf_frame` after computing `trim`)
- `contiguous_run`'s `ready` parameter typed `Union[Dict[int, int], Set[int]]` using `typing` generics, matching CONVENTIONS.md/D-11 style rather than PEP 604 `|`
- `chunk_command` in the wiring test is wrapped (`Mock(side_effect=real_chunk_command)`), not stubbed out, so the real command-building logic still runs while the mock still records the exact `(seek, trim)` arguments passed to it

## Deviations from Plan

None - plan executed exactly as written. All three tasks completed with no auto-fixes, no architectural questions, no checkpoints.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DEBT-02 fully satisfied: seek/trim math and high-water-mark flush ordering are now pure, directly unit-tested functions; `pipeline.py` calls them; `flush_appends` is a thin I/O shell
- `kf_before`/`fmt_seek` untouched; `scratch/parity_encode.py` re-run unchanged (zero diff); `legacy/` remains the untouched parity oracle
- Phase 2 (Correctness-Critical Extraction) is now complete: both DEBT-01 (02-01) and DEBT-02 (this plan) are done, with the hardware parity gate confirming byte-identical output end-to-end
- Ready for Phase 3 (ThreadPool/ProcessPool resolution, DEBT-03) — `contiguous_run`'s pure index-arithmetic shape is explicitly noted (PIPELINE_DESIGN.md, CONVENTIONS.md) as reusable unchanged by a future streaming consumer

---
*Phase: 02-correctness-critical-extraction*
*Completed: 2026-07-08*

## Self-Check: PASSED

All created/modified files verified present on disk; both task commits (`384f3e0`, `675833f`) verified present in git log. Task 3 was a verification-only re-run of the unchanged `scratch/parity_encode.py` (confirmed zero diff), so it has no commit of its own.
