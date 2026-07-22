---
phase: quick-260722-2rq
reviewed: 2026-07-22T02:31:44Z
depth: quick
files_reviewed: 6
files_reviewed_list:
  - src/enpipe/encoding/pipeline.py
  - src/enpipe/cli/main.py
  - tests/unit/encoding/test_batch_dispatch.py
  - tests/unit/cli/test_cli_dispatch.py
  - tests/unit/cli/test_batch_run.py
  - tests/unit/cli/test_cli_run.py
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
---

# Quick Task 260722-2rq: Code Review Report

**Reviewed:** 2026-07-22T02:31:44Z
**Depth:** quick (grep-pattern pass + targeted read of both source files and all four test files against the locked CONTEXT.md decisions, plus live reproduction of one edge case)
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the `--out-dir` folder-encoding flag (commits c5545db, ff83f9d) against
the locked design intent in `260722-2rq-CONTEXT.md` and the review focus areas
supplied by the caller. The core correctness invariants hold:

- `resolve_output_path` is byte-identical (diff shows zero changes inside the
  function body; only `_ensure_out_dir` was appended after it).
- The `-o`/`--out-dir` mutual-exclusion guard is duplicated at the top of both
  `run_encode` (`pipeline.py:111-112`) and `run_pipeline` (`main.py:92-93`), so
  it fires for every entry path, including the hand-built `_pipeline_one`
  Namespace (which always routes through `run_encode`'s own guard) and both
  batch branches.
- `_ensure_out_dir`'s single `except OSError` correctly folds in both
  `FileExistsError` (leaf exists as a file) and `PermissionError`, converting
  either into a clean `die()` with no raw traceback — verified by reading
  `shared/logging.py::die()` (plain `sys.exit(str)`, no stack trace) and by the
  new `test_out_dir_existing_file_dies` / `test_out_dir_permission_error_dies_cleanly`
  tests.
- Batch skip-if-exists (`resolve_output_path(v, out_base).exists()`) correctly
  points into the `--out-dir` folder in both `pipeline.py` (encode batch,
  line 145) and `main.py` (run batch, line 122).
- Russian in-code prose, `typing`-generics style, and "die() only on the main
  thread" are all respected; ran `uv run pytest` (96 passed in the touched
  packages, 165 in the full fast suite per VERIFICATION.md) and
  `uv run ruff check src tests` (clean) to confirm no regressions.

One real, reproducible side-effect bug was found (WR-01) and one minor
encapsulation nit (IN-01). Neither blocks the encode/mux correctness
invariants (frame-count verification, keyframe alignment, HDR/DV metadata
are untouched by this diff), so nothing here rises to Critical.

## Warnings

### WR-01: `--out-dir` folder is created before validating there is any work to do, leaving an orphaned empty directory on a `die()`

**File:** `src/enpipe/encoding/pipeline.py:132-136` (encode batch), `src/enpipe/cli/main.py:112-116` (run batch); same ordering issue also applies to the single-file path at `pipeline.py:158-167` relative to the empty-scene-range `die()` at line 168.

**Issue:** `_ensure_out_dir(args)` (which performs the `mkdir(parents=True, exist_ok=True)` side effect) runs *before* the batch discovers whether there is anything to encode:

```python
out_base = _ensure_out_dir(args)          # <- folder created here

videos = iter_input_videos(args.video, getattr(args, "recursive", False))
if not videos:
    die("в папке нет видеофайлов")         # <- but we already created out_base
```

Reproduced live against the actual code (not just read):

```
$ python3 -c "
import shutil; from pathlib import Path; from argparse import Namespace
import enpipe.encoding.pipeline as p
shutil.which = lambda t: '/usr/bin/x'
empty = Path('/tmp/empty'); empty.mkdir(exist_ok=True)
out_dir = Path('/tmp/newout')
args = Namespace(video=empty, scenes=None, out=None, out_dir=out_dir, frm=0, to=None,
                  workdir=None, keep=False, jobs=3, no_audio=False, no_metrics=False,
                  csv=None, recursive=False)
try: p.run_encode(args)
except SystemExit as e: print('died:', e)
print('leftover dir?', out_dir.exists())
"
died: encode_scenes: в папке нет видеофайлов
leftover dir? True
```

The same reproduces through `enpipe run <empty-dir> --out-dir DIR` via
`cli/main.py::run_pipeline`. This is a real filesystem side effect on a path
that is supposed to fail validation with no effect — on a NAS/ZFS host this
silently litters stray directories every time a batch run is pointed at an
empty or all-video-missing folder (e.g. a typo'd `--recursive` omission), and
there is no test covering it (existing `test_encode_directory_empty_dies`
does not pass `out_dir`).

Not classified Critical because it does not corrupt encoded output, lose
data, or violate the frame-count/keyframe invariants — it is a leftover empty
directory, not incorrect media.

**Fix:** Move the `iter_input_videos`/`if not videos: die(...)` (and, for the
single-file path, the `read_scenes`/empty-scene-range checks) ahead of the
`_ensure_out_dir(args)` call, so the `mkdir` side effect only happens once
there is confirmed work to do:

```python
videos = iter_input_videos(args.video, getattr(args, "recursive", False))
if not videos:
    die("в папке нет видеофайлов")

out_base = _ensure_out_dir(args)
```

Apply the same reordering in `cli/main.py::run_pipeline`'s batch branch.
Add a regression test asserting `out_dir` does NOT exist after
`test_encode_directory_empty_dies`/the `run` equivalent dies.

## Info

### IN-01: Private (`_`-prefixed) helper `_ensure_out_dir` imported across the `cli` <-> `encoding` module boundary

**File:** `src/enpipe/cli/main.py:26`
**Issue:** `from enpipe.encoding.pipeline import _ensure_out_dir, resolve_output_path, run_encode` pulls a leading-underscore name into another module. CLAUDE.md's Naming Patterns convention states underscore-prefixed helpers are "private/internal" (`_detect_relative`, `_boundary_worker`, etc.), signalling module-local-only use; here `_ensure_out_dir` is now part of the cross-module contract between `encoding/pipeline.py` and `cli/main.py`, so a future rename/refactor of the encoding module has no naming signal that `cli/main.py` depends on it. There is a mild precedent for this already (`pipeline.py` imports `_START` from `shared.logging`), so this is not a novel pattern — it's a genuine but low-severity encapsulation nit, not a new anti-pattern.

**Fix:** Either drop the leading underscore now that it's a public cross-module symbol (e.g. `ensure_out_dir`), or keep it private and give `cli/main.py` its own thin wrapper/duplicate of the two-line `getattr`+`mkdir`+`die` logic instead of importing the internal name directly.

---

_Reviewed: 2026-07-22T02:31:44Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
