---
phase: quick-260722-2rq
verified: 2026-07-22T00:00:00Z
status: passed
score: 6/6 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Quick Task 260722-2rq: `--out-dir` (encode into folder) Verification Report

**Task Goal:** A user can pass `--out-dir DIR` to `enpipe encode`, `enpipe run`,
and directory-input (batch) mode; the folder is created if it does not exist
(`mkdir -p`); the output is placed inside as `<video-stem>.Encoded<video-suffix>`.
`--out` remains a strict file path (unchanged, byte-identical behavior). `--out`
and `--out-dir` are mutually exclusive.

**Verified:** 2026-07-22
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `enpipe encode <video> --out-dir DIR` creates DIR (mkdir -p) if missing and writes `<stem>.Encoded<suffix>` inside it | VERIFIED | `pipeline.py:158-159`: `out_base = _ensure_out_dir(args); out = resolve_output_path(args.video, out_base)`. `_ensure_out_dir` (`pipeline.py:72-88`) calls `out_dir.mkdir(parents=True, exist_ok=True)`. Test `test_out_dir_creates_missing_folder_for_single_file` (`test_batch_dispatch.py:182`) passes. |
| 2 | `enpipe run <video> --out-dir DIR` does the same end-to-end (out_dir threaded through _pipeline_one) | VERIFIED | `cli/main.py:63`: `out_dir=args.out_dir,` in the hand-built `encode_args` Namespace inside `_pipeline_one`. Test `test_out_dir_routes_to_encode` (`test_cli_run.py:166`) asserts `e.out_dir == Path("X")`. |
| 3 | Passing both `-o/--out` and `--out-dir` exits via die() with a clear Russian message (manual guard, not argparse group) | VERIFIED | Guard present in both `run_encode` (`pipeline.py:111-112`) and `run_pipeline` (`main.py:92-93`): `if args.out is not None and getattr(args, "out_dir", None) is not None: die("-o/--out и --out-dir взаимоисключающи: задайте только один")`. Tests `test_out_and_out_dir_together_dies` (`test_batch_dispatch.py:223`), `test_out_and_out_dir_together_dies_on_encode`/`_on_run` (`test_cli_dispatch.py:123,130`) all pass. |
| 4 | `--out` semantics and all 4 resolve_output_path tests remain byte-identical (function stays pure/unchanged) | VERIFIED | `git diff c5545db~1 c5545db -- src/enpipe/encoding/pipeline.py` shows zero diff lines inside `resolve_output_path` (lines 58-69) — only additions of `_ensure_out_dir` after it. `pytest tests/unit/encoding/test_resolve_output_path.py -q` → 4 passed. |
| 5 | Batch (encode + run) accepts `--out-dir`: folder created on demand, skip-if-exists points inside the folder | VERIFIED | encode-batch: `pipeline.py:132,145` (`out_base = _ensure_out_dir(args)`, `resolve_output_path(v, out_base)`). run-batch: `main.py:112,122` (same pattern). Tests `test_encode_directory_out_dir_creates_folder_and_skip_resolves_inside` (`test_batch_dispatch.py:232`) and `test_run_on_directory_with_out_dir_creates_folder_and_skips_into_it` (`test_batch_run.py:158`) both pass. |
| 6 | mkdir failure (path is an existing file / no write perms on /data mount) exits via die(), never a raw traceback | VERIFIED | `_ensure_out_dir` wraps `mkdir` in `try/except OSError as ex: die(...)` (`pipeline.py:84-87`), covering both `FileExistsError` and `PermissionError`. Tests `test_out_dir_existing_file_dies` and `test_out_dir_permission_error_dies_cleanly` (`test_batch_dispatch.py:199,209`) both pass. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/enpipe/encoding/pipeline.py` | `_ensure_out_dir` helper + mutual-exclusion guard + mkdir wiring in single & encode-batch paths | VERIFIED | `_ensure_out_dir` defined at line 72; guard at line 111; wiring at 132/145 (batch), 158-159 (single). |
| `src/enpipe/cli/main.py` | `--out-dir` argparse on encode_p & run_p, guard in run_pipeline, out_dir threaded into `_pipeline_one` | VERIFIED | `--out-dir` added at lines 165-167 (encode_p) and 190-192 (run_p); guard at line 92; `out_dir=args.out_dir` at line 63. |
| `tests/unit/encoding/test_batch_dispatch.py` | `out_dir=None` in `_base_args` + new `--out-dir` folder-creation/skip tests | VERIFIED | `out_dir=None` default at line 36; 5 new tests (lines 182-245+) covering creation, existing-file die, permission-error die, mutual-exclusion die, batch skip-into-folder. |
| `tests/unit/cli/test_cli_dispatch.py` | `--out-dir` parse tests + mutual-exclusion die test | VERIFIED | 5 new tests at lines 101-133 covering parse-on-encode, parse-on-run, default-is-none, mutual-exclusion die (encode + run). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `pipeline.py::run_encode` (single path) | `resolve_output_path` | `out_base = _ensure_out_dir(args)` | WIRED | `pipeline.py:158-159` confirmed. |
| `cli/main.py::_pipeline_one` | `run_encode` encode_args | `out_dir=args.out_dir` field | WIRED | `main.py:63` confirmed. |
| `should_skip` closures (both batch branches) | `resolve_output_path` | `out_base` from `_ensure_out_dir` | WIRED | encode-batch `pipeline.py:145`, run-batch `main.py:122` both confirmed. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `--out-dir` parses on encode/run | Full pytest run (includes `test_cli_dispatch.py`) | 165 passed | PASS |
| `_ensure_out_dir` mkdir + die-on-OSError | `test_batch_dispatch.py` `test_out_dir_*` tests | 5/5 passed (within full run) | PASS |
| `resolve_output_path` byte-identical | `pytest tests/unit/encoding/test_resolve_output_path.py -q` | 4 passed | PASS |
| Full fast suite | `uv run pytest -m "not hardware" -q` | 165 passed, 6 deselected (hardware-tier, expected) | PASS |
| Lint clean | `uv run ruff check src tests` | All checks passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| OUTDIR-01 | 01 | `--out-dir` flag for encode/run/batch with mkdir-on-demand | SATISFIED | All 6 truths verified above; full test suite green. |

### Anti-Patterns Found

None. `grep -n -iE "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|placeholder|not implemented"` against both modified source files returned zero matches.

### Human Verification Required

None. This task is pure CLI-argument-parsing and filesystem behavior, fully covered by automated unit tests (mkdir creation, mutual-exclusion die, OSError handling, batch skip-resolution) — no UI, visual, real-time, or external-service surface requiring human judgment.

### Gaps Summary

No gaps. All 6 must-have truths, all 4 required artifacts, and all 3 key links
verified directly against the codebase (not SUMMARY.md claims): `_ensure_out_dir`
exists and is wired into all 4 call sites (encode single, encode batch, run
single via `_pipeline_one`, run batch); the mutual-exclusion guard fires in both
`run_encode` and `run_pipeline`; `resolve_output_path` has a git-confirmed empty
diff (still pure/unchanged) with its 4 tests green; the full fast test suite
(165 tests) and ruff both pass clean; no debt markers in modified files.

---

_Verified: 2026-07-22_
_Verifier: Claude (gsd-verifier)_
