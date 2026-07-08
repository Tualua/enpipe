# Phase 3: Concurrency Resolution + Regression Baseline + CI - Discussion Log

> **Audit trail only.** Decisions in CONTEXT.md.

**Date:** 2026-07-08
**Mode:** discuss (--auto --no-auto; autonomous answering, auto-advance suppressed for the cross-AI review step)
**Areas analyzed:** DEBT-03 executor resolution, DEBT-04 dovi_tool disposition, TEST-03 regression design, CI-01 pipeline shape, profiling methodology

## Gray Areas & Auto-Selected Decisions

- **DEBT-03** → profile ThreadPool vs ProcessPool on a real CPU-bound detection run; switch `detect_scenes_parallel`'s two executors to `ProcessPoolExecutor` if the GIL genuinely serializes (workers already module-level/pickle-safe), else keep threads + fix the misleading comment with the measured rationale. Lands before TEST-03.
- **DEBT-04** → keep `dovi_tool` in the devcontainer but document its retained purpose (planned Phase-4 DV RPU-fidelity verification) — lower churn than remove-then-re-add.
- **TEST-03** → pure regression asserting `detect_scenes_parallel(jobs=N) == detect_scenes(jobs=1)` by `(start_frame,end_frame)`; `DetectionConfig(use_qsv=/dev/dri present)`; multi-scene synthetic clip; default non-hardware tier; after DEBT-03.
- **CI-01** → `.github/workflows/ci.yml`, ubuntu-latest, setup-uv + `uv sync --locked`, apt ffmpeg+mkvtoolnix, `ruff check` (lint) + `pytest -m "not hardware"`; hardware tier excluded + documented as self-hosted-Arc. Minimal conservative `[tool.ruff]` (lint only; pyright deferred to v2).
- **Profiling methodology** → Claude's discretion (time-based comparison + CPU-bound micro-benchmark to isolate GIL signal).

## Corrections Made
None — auto mode, single pass.

## Deferred
Unified CLI (Phase 4), hardware HDR/DV + dovi_tool RPU check (Phase 4), pyright/coverage/Hypothesis/dep-update automation (v2).

## Todos
No pending todos matched Phase 3.
