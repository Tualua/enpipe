# Phase 5: Single-Command Pipeline Entry Point - Discussion Log

> **Audit trail only.** Decisions in CONTEXT.md.

**Date:** 2026-07-09
**Mode:** discuss (--auto --no-auto; autonomous answering, auto-advance suppressed for the cross-AI review step)
**Areas analyzed:** command shape, --jobs collision, .scenes handling, output/option surface, testing

## Gray Areas & Auto-Selected Decisions

- **Command shape** → `run` subparser in cli/main.py; thin orchestrator builds detect-Namespace → run_detect → encode-Namespace(scenes=written path) → run_encode, strictly sequential; reuse verbatim, zero behavior change.
- **--jobs collision** → separate `--detect-jobs` (default 4) / `--encode-jobs` (default ENCODE_JOBS); no single `--jobs`.
- **.scenes handling** → write `<video>.scenes` at the same path `enpipe detect` uses and keep it (mirrors manual two-step → byte-identical parity trivially true); optional `--scenes PATH` = discretion.
- **Output/options** → `-o/--out` = final `.mkv` (encode semantics); scenes path auto-derived; forward detect opts + encode opts with unambiguous names; Russian help.
- **Testing** → fast unit (mock run_detect/run_encode: assert order + arg routing) + hardware-gated e2e byte-identical parity vs manual two-step (Phase-4 harness, `--no-metrics`).

## Corrections Made
None — auto mode, single pass.

## Deferred
Overlapped/streaming orchestrator (out of scope), v2 items, auto-clean of `.scenes`.

## Todos
No pending todos matched Phase 5.
