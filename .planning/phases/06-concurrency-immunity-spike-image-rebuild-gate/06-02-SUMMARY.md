---
phase: 06-concurrency-immunity-spike-image-rebuild-gate
plan: 02
subsystem: test-infrastructure
tags: [concurrency, corruption-gate, qsv, av1, psnr, hardware-gated-tests]
dependency-graph:
  requires: []
  provides:
    - "tests/integration/_concurrency_harness.py: isolated-reference build, N-way round-robin concurrent launch (SESSION_FAILED/SWEEP_SKIPPED accounting), full-file PSNR sweep (30.0dB threshold), corruption-triad log assertion with silent-fallback guard"
    - "tests/integration/test_concurrency_immunity.py: hardware-gated COR-01 regression test (ffmpeg-immunity + qsvencc non-vacuous control)"
    - "scratch/gate_stress_matrix.py: one-time JOBS 3/5/8 x >=20-iter x 2-backend stress matrix with durable timestamped evidence"
  affects:
    - "Plan 06-03 (the real hardware proof run that exercises these artifacts and locks the HW-decode regex)"
tech-stack:
  added: []
  patterns:
    - "worker-thread (success, error) tuple return, never die()/raise, per CLAUDE.md"
    - "frozen dataclass value objects (HandoffScene, SessionOutcome) crossing function boundaries"
    - "argv-local override (ICQ 24) instead of global/module-state mutation"
key-files:
  created:
    - tests/integration/_concurrency_harness.py
    - tests/integration/test_concurrency_immunity.py
    - scratch/gate_stress_matrix.py
  modified:
    - .gitignore
decisions:
  - "IMMUNITY_ITERS defaults to 8 (env-tunable): non-immune-encoder survival probability at the observed 33-65% corruption rate is 0.35^8..0.65^8 ~= 2e-4..3e-2 -- weaker than the one-time stress tier's ~1e-3 at 20 iterations, but fast enough to rerun on every hardware-tier invocation (D-08)"
  - "ICQ 23-vs-24 resolved via an argv-local override in qsvencc_command(icq=24), applied AFTER chunk_command() builds the argv -- never via os.environ or chunk.ICQ reassignment, verified by an explicit import-safety check"
  - "run_concurrent takes an explicit refs: Dict[int, Path] parameter (not a same-workdir naming convention) so isolated references can be built once and reused across many ephemeral per-iteration workdirs -- required for the stress script's per-iteration tmpdir cleanup"
  - "sweep_chunk's frame-count-mismatch guard raises (propagates) rather than mapping to any of the three SessionOutcome statuses -- it signals a harness/encoder integrity problem outside the corruption-vs-clean-vs-failed-to-start taxonomy and must not be silently absorbed"
metrics:
  duration_minutes: 25
  completed: 2026-07-23
---

# Phase 6 Plan 2: Concurrency-Immunity Harness + Regression Test + Stress-Matrix Script Summary

Authored the COR-01 durable test artifacts (shared harness, hardware-gated pytest, one-time stress-matrix script) entirely import-safe and pure-function-verifiable in this un-rebuilt, no-ffmpeg-8.1 container, ready for the real hardware proof in Plan 06-03.

## What Was Built

Three new files, all reusing the project's verified production primitives (`chunk_command`, `count_frames`) rather than re-deriving them:

1. **`tests/integration/_concurrency_harness.py`** (339 lines) — the shared harness:
   - `HANDOFF_SCENES`: a frozen-dataclass tuple of the three hotspot scenes (923/928/1129) with hardcoded seek/trim/frames values from the reproducer handoff.
   - `ffmpeg_av1qsv_command` / `qsvencc_command`: verified argv builders for both backends. The qsvencc control calls `chunk_command` verbatim, then overrides `--icq` to `24` in the returned argv — no global/module mutation.
   - `run_session`: worker-thread `(bool, Optional[str])` return, never raises.
   - `build_isolated_reference`: single-session per-scene reference builder (raises loudly on failure — this is setup, not a pool worker).
   - `run_concurrent(backend, jobs, workdir, iteration, refs)`: launches exactly `jobs` subprocesses round-robin over the three scenes via `ThreadPoolExecutor`, classifying each outcome as `SESSION_OK` / `SESSION_FAILED` / `SWEEP_SKIPPED`.
   - `corrupt_frame_count` / `sweep_chunk`: the locked 30.0dB full-file PSNR sweep, with a loud frame-count-mismatch precondition guard before the sweep.
   - `assert_triad`: the four positive corruption-triad legs (10-bit, main profile, GopRefDist:6, BRefType:pyramid) plus the UNVERIFIED HW-decode leg (flagged for Plan 06-03) plus a silent-fallback negative-marker guard (`falling back` / `Failed to initialize QSV` / `MFX_ERR`).

2. **`tests/integration/test_concurrency_immunity.py`** (119 lines) — `pytest.mark.hardware`-gated, two tests:
   - `test_ffmpeg_av1qsv_immune_at_production_jobs`: asserts zero corrupt frames and zero `SESSION_FAILED` sessions across `IMMUNITY_ITERS` (default 8) iterations at JOBS=3, plus an intact triad on a representative clean run.
   - `test_qsvencc_control_corrupts_same_harness`: asserts total corrupt-frame count `> 0` in the same harness — the non-vacuousness proof (SC#4).
   - The module-scope `_require_hardware` fixture skips loudly (with an explanatory message) when Arc hardware, `ffmpeg-8.1`, or the real `/data` fixture is absent.

3. **`scratch/gate_stress_matrix.py`** (230 lines) — one-time throwaway script:
   - Hardware/ffmpeg-8.1/fixture gate first, prints a loud `SKIP: ...` and exits 0 if any prerequisite is missing.
   - Full JOBS `(3, 5, 8)` × `STRESS_ITERS` (default 20, env-tunable) × both backends matrix, reusing `_concurrency_harness` as the single source of truth.
   - Per-iteration `tempfile.mkdtemp()` workdir, removed immediately after tallying (keeps only the tallies + one retained verbose log per JOBS level).
   - Writes a timestamped `scratch/gate_stress_matrix_<UTC>.log` durable-evidence file (uname/driver/iHD, per-cell clean/corrupt/`SESSION_FAILED` counts, triad status, D-11 pass-bar verdict) — added to `.gitignore` alongside the other scratch artifacts, since D-09's durable record is the SUMMARY/debug-doc append, not the raw log file.

## Deviations from Plan

### Auto-fixed / Discretionary Adjustments

**1. [Rule 3 - blocking design gap] `run_concurrent` takes an explicit `refs: Dict[int, Path]` parameter instead of the plan's literal `(backend, jobs, workdir, iteration)` signature**
- **Found during:** Task 1, designing `run_concurrent`'s reference lookup.
- **Issue:** The plan's literal signature implied references live in the same `workdir` passed to `run_concurrent` (via a `workdir / f"ref_{scene}.obu"` convention). That is incompatible with Task 3's explicit requirement that "each iteration writes its outputs to a fresh per-iteration temp workdir... after the iteration's tallies are captured, REMOVE that workdir" while references must be built ONCE and reused across many iterations and JOBS levels.
- **Fix:** `run_concurrent` accepts `refs: Dict[int, Path]` explicitly; callers build references once (in a separate, persistent workdir) and pass the same dict into every `run_concurrent` call. `SWEEP_SKIPPED` now means "no entry for this scene in `refs`" rather than "no file at a hardcoded convention path" — behaviorally identical, structurally more robust.
- **Files modified:** `tests/integration/_concurrency_harness.py`, `tests/integration/test_concurrency_immunity.py`, `scratch/gate_stress_matrix.py`.
- **Commits:** cb0e6c2, b423e5b, 8e0fe1c.

**2. [Rule 3 - blocking Task 3 verify mismatch] `scratch/gate_stress_matrix.py`'s hardware gate does not print the literal string "SKIP: no Arc hardware" in this environment**
- **Found during:** Task 3 verification (`python scratch/gate_stress_matrix.py`).
- **Issue:** This specific container unexpectedly has `/dev/dri/renderD128` and `qsvencc` both present (unlike the plan's stated assumption of "no Arc encode access"), so the hardware-availability leg of the gate passes; the script instead hits the next leg and prints `SKIP: ffmpeg-8.1 not on PATH (rebuild the devcontainer image)`.
- **Resolution:** No code change needed — this is the CORRECT behavior of a multi-condition gate (hardware present, ffmpeg-8.1 absent) and it still satisfies the underlying acceptance intent: the gate fires before any encode, prints a loud explanatory SKIP, and exits 0. Verified directly: `echo "exit code: $?"` after running the script returned `0`.
- **Files modified:** none (behavioral note only).

### None Beyond the Above

The corruption-triad HW-decode-leg regex (`\[h264_qsv\b`) is deliberately left `[UNVERIFIED regex]` per the plan's explicit instruction — locking it against a real `-v verbose` capture is Plan 06-03's Task 1, not this plan's scope.

## Verification Performed

All of the following were actually RUN, not inferred:

- **Import-safety + pure-function one-liner** (Task 1 `<verify>`): confirms the harness import does not mutate `os.environ["ICQ"]` or `enpipe.encoding.chunk.ICQ` (stays `23`), `corrupt_frame_count` returns `2` on the synthetic inf/41.53/15.74/29.9 fixture, `assert_triad` returns `[]` on an intact-triad log and non-empty when a fallback marker is present even with all positive legs, and `qsvencc_command` returns `--icq 24` in argv. **Output: `OK`.**
- **`ruff check`** on all three new files: **`All checks passed!`** (both individually per-task and combined at the end).
- **Full-suite guard** `python -m pytest -q` after each task and once more at the end: **`167 passed, 8 deselected`** (0 regressions; the 8 deselected are the pre-existing + 2 newly-added hardware-tier tests, all correctly excluded by the default `-m "not hardware"`).
- **Collection sanity** for the new pytest file: `--collect-only -q` with the default marker filter shows `no tests collected (2 deselected)`; forcing selection with `-m hardware` shows **`2 skipped`** (loud skip, not silent pass, not error) — confirmed by running `python -m pytest tests/integration/test_concurrency_immunity.py -m hardware -q`.
- **`ast.parse`** on `scratch/gate_stress_matrix.py`: **`parse-ok`**.
- **Script execution** of `scratch/gate_stress_matrix.py` in this container: prints a loud `SKIP: ffmpeg-8.1 not on PATH (rebuild the devcontainer image)` and **exits `0`** (confirmed via explicit `echo $?`), i.e. the hardware/ffmpeg-8.1/fixture gate fires before any encode subprocess is launched.
- **File existence + line-count self-check**: all three files exist at their expected paths; line counts (339 / 119 / 230) all exceed the plan's stated `min_lines` (90 / — / 60).

### Not Verified (explicitly out of scope for this plan, deferred to Plan 06-03)

- The actual immunity/corruption behavior on real hardware (SC#2/SC#3/SC#4) — this plan only proves the test/harness code is correct and executable; the real proof run against `/data`'s Cold Eyes fixture on `ffmpeg-8.1` requires the devcontainer image rebuild (ENV-01, separate track) and happens in Plan 06-03.
- The HW-decode-leg regex in `assert_triad` — explicitly left `[UNVERIFIED regex]`, to be locked against a real `-v verbose` capture in Plan 06-03.
- The `gate_stress_matrix.py` script's actual matrix run and its durable-evidence log — not executed here since it requires `ffmpeg-8.1` + the real fixture, both absent in this container.

## Known Stubs

None — no hardcoded empty values, placeholder UI text, or unwired data sources. The `[UNVERIFIED regex]` marker on the HW-decode triad leg is an intentional, explicitly-flagged incompleteness (not a stub) with a named resolution path (Plan 06-03 Task 1), per the plan's own instruction not to resolve it here.

## Threat Flags

None beyond what the plan's own `<threat_model>` already covers (T-06-02, T-06-03, T-06-04, T-06-07 — all addressed directly by the implemented `corrupt_frame_count`/`sweep_chunk` loud-failure behavior, the `assert_triad` silent-fallback guard, the non-vacuous qsvencc control test, and the `SESSION_FAILED` accounting respectively). No new network endpoints, auth paths, or schema changes were introduced.

## Self-Check: PASSED

- FOUND: tests/integration/_concurrency_harness.py
- FOUND: tests/integration/test_concurrency_immunity.py
- FOUND: scratch/gate_stress_matrix.py
- FOUND commit cb0e6c2 (Task 1)
- FOUND commit b423e5b (Task 2)
- FOUND commit 8e0fe1c (Task 3)
