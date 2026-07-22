---
phase: quick-260722-2rq
plan: 01
subsystem: cli/encoding-pipeline
tags: [cli, argparse, output-path, mkdir]
dependency-graph:
  requires: []
  provides: ["--out-dir CLI flag on enpipe encode/run", "_ensure_out_dir helper"]
  affects: [src/enpipe/encoding/pipeline.py, src/enpipe/cli/main.py]
tech-stack:
  added: []
  patterns: ["mkdir wrapped in try/except OSError -> die()", "manual mutual-exclusion die() guard (not argparse group)"]
key-files:
  created: []
  modified:
    - src/enpipe/encoding/pipeline.py
    - src/enpipe/cli/main.py
    - tests/unit/encoding/test_batch_dispatch.py
    - tests/unit/cli/test_cli_dispatch.py
    - tests/unit/cli/test_batch_run.py
    - tests/unit/cli/test_cli_run.py
decisions:
  - "Manual die() guard for -o/--out-dir mutual exclusion, not argparse add_mutually_exclusive_group (must also fire for the hand-built Namespace in _pipeline_one, and keep the project's single die() error-surface convention)"
  - "resolve_output_path stays pure/unchanged; mkdir side effect lives entirely in the new _ensure_out_dir(args) caller-side helper"
  - "Single except OSError clause in _ensure_out_dir covers both PermissionError (read-only /data mount) and FileExistsError (out-dir path is an existing file)"
metrics:
  duration: 25min
  completed: 2026-07-22
---

# Phase quick-260722-2rq Plan 01: `--out-dir` (encode into folder) Summary

Added a `--out-dir DIR` flag to `enpipe encode` and `enpipe run` (including
both directory-input batch branches) that creates `DIR` on demand
(`mkdir -p`, idempotent) and places the muxed output inside it as
`<video-stem>.Encoded<video-suffix>` — reusing the existing
`resolve_output_path` existing-directory formula unchanged.

## What Was Built

- `_ensure_out_dir(args)` in `src/enpipe/encoding/pipeline.py`: reads
  `args.out_dir` (defensive `getattr`, falls back to `args.out` when unset),
  runs `Path.mkdir(parents=True, exist_ok=True)` wrapped in
  `try/except OSError -> die()`. One clause catches both `PermissionError`
  (read-only/wrong-uid `/data` mount) and `FileExistsError` (path already
  exists as a non-directory file) and converts either into a clean fatal
  message instead of a raw traceback.
- Manual mutual-exclusion guard (`args.out is not None and args.out_dir is
  not None -> die(...)`) placed right after the `shutil.which` preflight
  loop in both `run_encode` (`pipeline.py`) and `run_pipeline`
  (`cli/main.py`) — this single check protects direct `encode`, `run`
  single-file, and both batch branches, and also fires for
  `_pipeline_one`'s hand-built `encode_args` Namespace (which argparse's
  own mutually-exclusive group could never do, since it never re-parses
  argv).
- `--out-dir` argparse option added to `encode_p` and `run_p`
  (`dest="out_dir"`, `type=Path`, `default=None`, Russian help text
  matching the existing `-o/--out` style).
- `out_dir=args.out_dir` threaded into `_pipeline_one`'s hand-built
  `encode_args` Namespace so `enpipe run --out-dir X` doesn't silently drop
  the flag before reaching `run_encode`.
- Single-file encode path: `out_base = _ensure_out_dir(args)` replaces the
  direct `args.out` argument to `resolve_output_path`; once the folder
  exists, `resolve_output_path`'s existing dir-branch returns
  `<dir>/<stem>.Encoded<suffix>` with zero changes to the function itself.
- Both batch branches (encode in `pipeline.py`, run in `cli/main.py`):
  existing `-o must be an existing dir` guard message extended to mention
  `--out-dir`; `out_base = _ensure_out_dir(args)` computed once before
  `run_batch`; `should_skip` closures changed from
  `resolve_output_path(v, args.out)` to `resolve_output_path(v, out_base)`
  so "already done" correctly resolves into the `--out-dir` folder.

## Deviations from Plan

None — plan executed exactly as written (both tasks, all 7 sub-points of
Task 1 and all 4 test groups of Task 2 implemented as specified in
PLAN.md/RESEARCH.md).

## Verification

- Task 1 automated verify (ast.parse + argparse round-trip for `--out-dir`
  on `encode`/`run` + `_ensure_out_dir` importable): ran, printed `ok`.
- Task 2 automated verify:
  `uv run python -m pytest tests/unit/encoding/test_resolve_output_path.py
  tests/unit/encoding/test_batch_dispatch.py tests/unit/cli/test_cli_dispatch.py
  tests/unit/cli/test_batch_run.py tests/unit/cli/test_cli_run.py -q`
  → **57 passed**.
- Full fast suite: `uv run pytest -m "not hardware" -q` → **165 passed, 6
  deselected** (hardware-tier tests, expected to be excluded — no hardware
  in this environment).
- `uv run ruff check src tests` → **All checks passed!**
- `resolve_output_path` diff: confirmed untouched (only new code added
  after it in `pipeline.py`); all 4 of its existing pure-function tests
  pass unchanged.

## Known Stubs

None. No placeholder/mock data paths introduced — `_ensure_out_dir` is
fully wired into all 4 real call sites (encode single, encode batch, run
single via `_pipeline_one`, run batch).

## Threat Flags

None. This closes out the plan's own `<threat_model>` register (T-2rq-01,
T-2rq-02, T-2rq-03) via the `_ensure_out_dir` try/except and the mutual-
exclusion guard — no new unmitigated surface introduced beyond what the
plan already registered.

## Self-Check: PASSED

All modified files confirmed present on disk:
- `src/enpipe/encoding/pipeline.py` — FOUND
- `src/enpipe/cli/main.py` — FOUND
- `tests/unit/encoding/test_batch_dispatch.py` — FOUND
- `tests/unit/cli/test_cli_dispatch.py` — FOUND
- `tests/unit/cli/test_batch_run.py` — FOUND
- `tests/unit/cli/test_cli_run.py` — FOUND

Both task commits confirmed in `git log`:
- `c5545db` — `feat(quick-260722-2rq): add --out-dir folder-creation flag to encode/run`
- `ff83f9d` — `test(quick-260722-2rq): cover --out-dir mkdir, mutual-exclusion, batch skip`
