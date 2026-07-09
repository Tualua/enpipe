---
phase: 05-single-command-pipeline-entry-point
plan: 01
subsystem: cli
tags: [argparse, cli, orchestration, av1, qsv, testing]

# Dependency graph
requires:
  - phase: 04-cli-and-hardware-validation
    provides: verified run_detect/run_encode Namespace-shaped pipeline functions and the enpipe detect/encode CLI dispatch (build_parser/main)
provides:
  - "enpipe run <video> single-command wrapper: run_detect -> run_encode strictly sequential, one invocation"
  - "additive fail-fast shutil.which preflight (qsvencc/ffprobe/ffmpeg/mkvmerge) before run_detect"
  - "--detect-jobs/--encode-jobs collision-free flags with legacy defaults preserved"
  - "fast mocked unit test (order, per-stage routing, preflight, Namespace non-contamination)"
  - "hardware-gated run-vs-two-step parity test, verified passing on real Arc"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin CLI orchestrator: build a per-stage argparse.Namespace by hand and call the existing verified stage function by its module-global name (monkeypatch seam), rather than adding pipeline logic to the composing layer."
    - "Additive fail-fast preflight ahead of a long-running first stage, without touching either stage's own preflight/behavior."

key-files:
  created:
    - tests/unit/cli/test_cli_run.py
  modified:
    - src/enpipe/cli/main.py
    - tests/integration/test_hardware_real_media.py

key-decisions:
  - "run_pipeline defined above build_parser() in cli/main.py, referencing run_detect/run_encode by module-global name so tests can monkeypatch enpipe.cli.main.run_detect/run_encode (same seam as existing dispatch tests)."
  - "Preflight checks encode-stage tools (qsvencc/ffprobe/ffmpeg/mkvmerge) via shutil.which BEFORE run_detect; run_encode keeps its own identical preflight unchanged -- purely additive UX, zero behavior change to either stage (D-02)."
  - "--scenes PATH override implemented (Claude's discretion per D-04) to relocate the intermediate; when omitted, the default <video>.scenes path is used and kept on disk."
  - "No bare --jobs flag on `run` (D-03) -- --detect-jobs (default 4) and --encode-jobs (default ENCODE_JOBS) are separate, unambiguous flags; bare --jobs raises SystemExit via argparse's own unrecognized-argument handling."

requirements-completed: [RUN-01, RUN-02, RUN-03, RUN-04]

# Metrics
duration: 9min
completed: 2026-07-09
---

# Phase 5 Plan 1: Single-Command Pipeline Entry Point Summary

**Added `enpipe run <video>` as a thin sequential orchestrator composing the verified `run_detect`/`run_encode` with an additive fail-fast tool preflight; verified byte/frame-identical to the manual two-step on real Arc hardware.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-09T01:41:00Z
- **Completed:** 2026-07-09T01:50:15Z
- **Tasks:** 3
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `enpipe run <video>` runs `run_detect` then `run_encode` strictly sequentially in one process invocation, writing `<video>.scenes` and the final `.mkv`, with zero behavior change to either stage.
- Added a fail-fast `shutil.which` preflight over the encode-stage tools (`qsvencc`/`ffprobe`/`ffmpeg`/`mkvmerge`) at the start of `run_pipeline`, before `run_detect` — dies early instead of wasting a (potentially long) detect pass when an encode tool is missing.
- Resolved the `--jobs` collision between the two stages with `--detect-jobs` (default 4) / `--encode-jobs` (default `ENCODE_JOBS`); no bare `--jobs` exists on `run`.
- Fast mocked unit test (`tests/unit/cli/test_cli_run.py`, 10 tests) proves order, per-stage argument routing, the collision split, bare-`--jobs` rejection, preflight-before-`run_detect`, Namespace non-contamination, `--from`/`--to` routing, and `--scenes` override routing.
- Hardware-gated parity test (`test_run_parity_vs_two_step`) added to the existing Phase-4 harness and **verified passing on real Arc hardware in this session**: final-`.mkv` frame-count parity, pre-mux `movie.obu` byte-identical, run-side `.scenes` kept and byte-identical to the two-step `.scenes` despite distinct paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `run` subparser + thin sequential orchestrator (with fail-fast preflight) to cli/main.py** - `76171ab` (feat)
2. **Task 2: Fast mocked unit test — order + per-stage routing + preflight** - `c898af3` (test)
3. **Task 3: Hardware-gated run-vs-two-step parity test** - `6518e0b` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `src/enpipe/cli/main.py` - added `import shutil`, `from enpipe.shared.logging import die`, `run_pipeline(args)` (defined above `build_parser()`), and the `run` subparser (positional `video`, `-o/--out`, optional `--scenes`, full detect + encode option forwarding with `--detect-jobs`/`--encode-jobs`); `detect`/`encode` subparsers and `main()` untouched.
- `tests/unit/cli/test_cli_run.py` - new file, 10 tests covering order, detect/encode routing, jobs collision + defaults, bare-`--jobs` rejection, preflight-before-`run_detect`, Namespace non-contamination, `--from`/`--to` routing, `--scenes` override.
- `tests/integration/test_hardware_real_media.py` - appended `test_run_parity_vs_two_step` (existing tests/helpers untouched); reuses `_run_cli`, `_make_multiscene_clip`, `count_frames`, `read_scenes` (imported but only `read_scenes`/`count_frames` newly used by the new test — both already imported at module top).

## Decisions Made
- **Preflight placement and scope (review item, plan Task 1):** the additive `shutil.which` check lives entirely inside `run_pipeline`, runs before `run_detect`, and duplicates (does not replace) `run_encode`'s own preflight. This keeps D-02's "reuse verbatim, zero behavior change" invariant intact while giving `enpipe run` fail-fast UX.
- **`--scenes` override implemented:** since it was Claude's discretion (D-04) and cheap to add/test, implemented `--scenes PATH` routing to both the detect Namespace's `output` and the encode Namespace's `scenes`, with the corresponding test case in Task 2.
- **Hardware test iteration order:** in `test_run_parity_vs_two_step`, `enpipe run` runs first (writing `<video>.scenes` next to `src`), then the two-step side copies `src` into a distinct subdirectory before deriving its own `.scenes` path — this is the plan's specified collision-avoidance strategy, confirmed by an explicit `run_scenes != scenes2` assertion.

## Deviations from Plan

None — plan executed exactly as written, including the two Claude-discretion items (preflight placement covered by the plan's Task 1 spec itself; `--scenes` override implemented as specified in Task 1/Task 2/D-04).

## Cosmetic Note (per plan's `<output>` requirement)

The encode stage's `ГОТОВО за {t}с` log line (`encoding/pipeline.py:258`) reports **detect+encode combined wall time** when run under `enpipe run`, because `_START` (`enpipe/shared/logging.py:31`) is captured at module-import time, which now happens once for the whole `enpipe run` process rather than once per manually-invoked stage. This is purely cosmetic log text — already explicitly outside the parity surface per `logging.py:16-18` ("текст лога не входит в parity-поверхность") — and was **not** "fixed"; recording it here so a future reader does not mistake it for a bug.

## Issues Encountered

None. Real Intel Arc hardware (`/dev/dri/renderD128` + `qsvencc` 8.20) was available in this devcontainer session, so the hardware-gated test in Task 3 was run for real (not just self-skip-verified): `uv run pytest -m hardware -v` → `test_run_parity_vs_two_step PASSED` (4 passed, 2 skipped — the 2 skips are the pre-existing fixture-gated HDR10+/DV tests, unrelated to this plan).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `enpipe run` is the milestone v1.1 capstone deliverable (RUN-01..RUN-04); all four requirements are satisfied and verified (fast tier + real-hardware run in this session).
- `enpipe detect`/`enpipe encode` remain independently runnable and byte-identical to their pre-phase-5 behavior; `legacy/` untouched.
- No blockers. This closes the only planned plan (05-01) in Phase 5, which closes milestone v1.1.

---
*Phase: 05-single-command-pipeline-entry-point*
*Completed: 2026-07-09*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 3 task commit hashes (`76171ab`, `c898af3`, `6518e0b`) confirmed present in `git log`.
