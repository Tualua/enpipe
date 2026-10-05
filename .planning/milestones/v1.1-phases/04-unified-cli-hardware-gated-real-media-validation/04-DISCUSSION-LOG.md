# Phase 4: Unified CLI + Hardware-Gated Real-Media Validation - Discussion Log

> **Audit trail only.** Decisions in CONTEXT.md.

**Date:** 2026-07-08
**Mode:** discuss (--auto --no-auto; autonomous answering, auto-advance suppressed for the cross-AI review step)
**Areas analyzed:** CLI structure & run_detect, backward-compat/.scenes handoff, TEST-04 source coverage, TEST-04 invariant checks, DV RPU mechanism uncertainty

## Gray Areas & Auto-Selected Decisions

- **CLI** → `src/enpipe/cli/main.py` argparse dispatcher (`enpipe detect`/`enpipe encode`), `[project.scripts] enpipe`; migrate the legacy detect `__main__` `.scenes`-writer into `run_detect(args)` mirroring `run_encode(args)`.
- **Backward compat** → preserve the two-stage `.scenes` handoff; legacy scripts still runnable; thin dispatch, zero detect/encode behavior change; NOT a fused orchestrator (out of scope).
- **TEST-04 coverage** → generate + validate SDR and synthetic HDR10 end-to-end on real Arc; FIXTURE-gate HDR10+/DV (skip cleanly + document how to supply a real sample) since genuine DV RPU source can't be synthesized in-sandbox; honest, no coverage theater.
- **TEST-04 invariants** → per-chunk + total frame counts, keyframe-aligned boundaries, DV RPU survival (only with a DV fixture); hardware-marked; optional self-hosted-runner CI stub (deferred from Phase 3).
- **DV RPU mechanism** → flagged for research: extract-rpu is HEVC-only but output is AV1 (qsvencc --dolby-vision-rpu copy); determine the real AV1 RPU-survival verification or scope it honestly.

## Corrections Made
None — auto mode, single pass.

## Deferred
Streaming orchestrator (out of scope), v2 quality items, PyPI release, permanent HDR10+/DV sample library.

## Todos
No pending todos matched Phase 4.
