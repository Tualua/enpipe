---
phase: 01-package-foundation-migration-fast-test-tier
reviewed: 2026-07-08T00:00:00Z
depth: deep
files_reviewed: 27
files_reviewed_list:
  - src/enpipe/shared/proc.py
  - src/enpipe/shared/logging.py
  - src/enpipe/detection/config.py
  - src/enpipe/detection/stream.py
  - src/enpipe/detection/detect.py
  - src/enpipe/detection/parallel.py
  - src/enpipe/encoding/scenes_io.py
  - src/enpipe/encoding/keyframes.py
  - src/enpipe/encoding/hdr.py
  - src/enpipe/encoding/chunk.py
  - src/enpipe/encoding/audio.py
  - src/enpipe/encoding/metrics.py
  - src/enpipe/encoding/pipeline.py
  - src/enpipe/__init__.py
  - src/enpipe/detection/__init__.py
  - src/enpipe/encoding/__init__.py
  - src/enpipe/shared/__init__.py
  - tests/unit/detection/test_detect.py
  - tests/unit/encoding/test_chunk.py
  - tests/unit/encoding/test_keyframes.py
  - tests/unit/encoding/test_scenes_io.py
  - tests/subprocess/detection/test_stream.py
  - tests/subprocess/encoding/test_audio.py
  - tests/subprocess/encoding/test_chunk.py
  - tests/subprocess/encoding/test_hdr.py
  - tests/subprocess/encoding/test_keyframes.py
  - pyproject.toml
  - .devcontainer/post-create.sh
  - .gitignore
  - scratch/parity_detect.py
  - scratch/parity_encode.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-07-08
**Depth:** deep (cross-file, byte-level diff against `legacy/`, live test execution)
**Files Reviewed:** 27 (+4 empty `__init__.py`)
**Status:** issues_found (no HIGH/blocker findings; one MEDIUM completeness gap, two LOW nits)

## Summary

This phase mechanically migrates `legacy/scene_detection.py` and `legacy/encode_scenes.py` into `src/enpipe/{detection,encoding,shared}` behind a single `enpipe.shared.proc` subprocess seam, and adds a fast hardware-free test tier. The review methodology went beyond reading the new files in isolation: every top-level function/class name was diffed against its legacy counterpart via `ast`-based extraction, and the full body of `run_encode` (the highest-risk file — the former `main()`) was diffed line-for-line against legacy `main()`.

**Verdict: the migration is faithful.** Every function/class defined in `legacy/scene_detection.py` has an exact byte-for-byte counterpart (docstrings, comments, code) in `src/enpipe/detection/*.py`, with the sole substitution of `subprocess.run`/`subprocess.Popen` → `proc.run`/`proc.popen` at the documented call sites. Every function/class in `legacy/encode_scenes.py` has an exact counterpart in `src/enpipe/encoding/*.py` (`main()` → `run_encode(args)`, `run()`/`log()`/`step()`/`die()`/`_START` relocated to `enpipe.shared.logging`/`enpipe.shared.proc`), and the entire post-argparse body of `run_encode` is line-identical to legacy `main()` except for the same seam substitution. No argv construction, no conditional, no numeric constant, and no ordering of operations differs from legacy anywhere in the reviewed diff.

The two cross-AI review HIGH fixes were independently verified in the code (not just trusted from planning docs):
1. `run_encode` (`src/enpipe/encoding/pipeline.py:58-62`) retains the `shutil.which` preflight loop and `args.video.is_file()` check as the first statements, exactly as legacy `main()` did (`legacy/encode_scenes.py:532-536`).
2. `scratch/parity_encode.py` is hardware-gated (`_hardware_available()` checked first, prints `SKIP` and exits 0 if absent), runs the legacy encoder twice to pre-check qsvencc determinism, and its PRIMARY GATE compares the pre-mux `movie.obu` (byte-identical when deterministic, falling back to frame-count + SSIM/PSNR epsilon otherwise) rather than the final muxed `.mkv`.

The detect.py↔parallel.py circular import is broken correctly: the deferred `from .parallel import detect_scenes_parallel` / `from .detect import detect_scenes` imports sit exactly at the two call sites that cross the new module boundary, matching legacy's control flow exactly; both import orders succeed with no `ImportError` (verified live).

All 40 tests pass (`pytest -m "not hardware"`); zero hardware tests collected; no hardcoded secrets, `eval`, empty `except`, or debug artifacts found via pattern scan.

The only substantive gap found is a test-coverage completeness issue (not a behavior bug): `enpipe.encoding.metrics.write_metrics_csv` — explicitly documented in its own module docstring as "чистый файловый вывод, subprocess-шов не задействован" (pure file output, no subprocess seam) and therefore squarely inside this phase's own stated TEST-01 pure-logic charter — has no test anywhere in `tests/unit/` or `tests/subprocess/`, and is not listed in either Plan 01-02's or Plan 01-03's D-11 TEST-01 target enumeration. Two additional LOW-severity nits are noted below.

## Warnings

### WR-01: `write_metrics_csv` (pure logic, in-scope for this phase's own TEST-01 charter) has zero test coverage

**File:** `src/enpipe/encoding/metrics.py:12-40` (no corresponding test file anywhere under `tests/`)
**Severity:** MEDIUM
**Issue:** `write_metrics_csv` does no subprocess I/O — its own docstring says so explicitly ("чистый файловый вывод, subprocess-шов не задействован"), which places it squarely in the "pure-logic unit tests" bucket this phase's charter defines ("add a fast, hardware-free test tier (pure-logic unit tests + mocked subprocess-boundary tests)", `01-CONTEXT.md:9`). Yet:
- `tests/unit/encoding/` has no `test_metrics.py`.
- Neither `01-02-PLAN.md`'s nor `01-03-PLAN.md`'s D-11 TEST-01 target list mentions `write_metrics_csv` (they list `kf_before`, `fmt_seek`, `read_scenes`, the EBML helpers, and `parse_metrics` — but not `write_metrics_csv`, a distinct function in a distinct module).
- `grep -rn "write_metrics_csv" tests/ scratch/*.py` returns nothing; the hardware-gated `scratch/parity_encode.py` runs with `no_metrics=True` on both sides, so it never exercises the CSV-writing path either.

Untested logic includes the frame-weighted `wmean()` averaging (division-by-zero guard `if fr else None`, weighting by `r["frames"]`), the CSV field ordering (`fields` list), and the "ИТОГО" totals-row construction — all pure, deterministic, and cheap to test with `tmp_path`.

**Fix:** Add `tests/unit/encoding/test_metrics.py` covering at minimum: (a) a normal multi-scene CSV with correct per-row + frame-weighted total; (b) a scene with `None` metric fields excluded correctly from `wmean()`; (c) the `ssim_all`/`psnr_avg` keys landing in the same row identified by `scene == "ИТОГО"`. Example:
```python
from pathlib import Path
from enpipe.encoding.metrics import write_metrics_csv

def test_write_metrics_csv_frame_weighted_total(tmp_path):
    rows = {
        0: {"scene": 0, "start_frame": 0, "end_frame": 48, "frames": 48,
            "seek": "00:00:00.000", "trim": "0:47", "encode_sec": 1.0, "fps": 48.0,
            "size_mb": 1.0, "ssim_all": 0.99, "ssim_db": 20.0,
            "psnr_avg": 40.0, "ssim_y": 0.99, "psnr_y": 40.0},
        1: {"scene": 1, "start_frame": 48, "end_frame": 96, "frames": 48,
            "seek": "00:00:02.000", "trim": "0:47", "encode_sec": 1.0, "fps": 48.0,
            "size_mb": 1.0, "ssim_all": 0.98, "ssim_db": 19.0,
            "psnr_avg": 39.0, "ssim_y": 0.98, "psnr_y": 39.0},
    }
    total = write_metrics_csv(tmp_path / "out.csv", rows)
    assert total["frames"] == 96
    assert total["ssim_all"] == 0.985  # equal-weight frame average
    assert (tmp_path / "out.csv").exists()
```

## Info

### IN-01: Unused module-level constant `JOBS` in `pipeline.py`

**File:** `src/enpipe/encoding/pipeline.py:39`
**Severity:** LOW
**Issue:** `JOBS = int(os.environ.get("JOBS", "3"))` is defined but never referenced anywhere else in `pipeline.py` (or any other module). In legacy, `JOBS` fed `ap.add_argument("--jobs", type=int, default=JOBS)` — that argparse block was correctly and deliberately stripped from `run_encode` per this phase's own scope note (CLI glue deferred to Phase 4), but the constant itself was left behind with nothing consuming it. It's harmless today (all actual job-count reads go through `args.jobs`), but it is dead code that a linter (ruff/pyflakes `F401`/unused-variable-equivalent for module scope) would flag, and a future reader may wonder whether it's actually wired to anything.
**Fix:** Either remove it now (nothing consumes it) and let Phase 4's CLI module define its own `JOBS` default read from `os.environ`, or add a one-line comment noting it's intentionally retained as the Phase-4 CLI's future `--jobs` default so its current lack of use is not read as an oversight:
```python
# Reserved for Phase 4 CLI's `--jobs` default (ap.add_argument("--jobs", ..., default=JOBS));
# not referenced by run_encode itself, which reads args.jobs directly.
JOBS = int(os.environ.get("JOBS", "3"))
```

### IN-02: Monkeypatch in `test_detect_hdr_dolby_vision_side_data_adds_rpu_flags` sets `DV_PROFILE` to its own default value

**File:** `tests/subprocess/encoding/test_hdr.py:29-30`
**Severity:** LOW
**Issue:** `monkeypatch.setattr(hdr, "DV_PROFILE", "10.1")` sets `DV_PROFILE` to `"10.1"`, which is already the module's default (`hdr.py:13`: `os.environ.get("DV_PROFILE", "10.1")`). The test therefore does not actually prove that a non-default `DV_PROFILE` value propagates into the emitted `--dolby-vision-profile` flag — it would pass identically with the `monkeypatch.setattr` line deleted. The assertion on flag *selection* (that DV side-data triggers `--dolby-vision-rpu`/`--dolby-vision-profile`) is still valid and useful; only the "profile value is read from the module constant, not hardcoded" claim implied by using `monkeypatch` here is unverified.
**Fix:** Use a distinct value to actually exercise the override path:
```python
def test_detect_hdr_dolby_vision_side_data_adds_rpu_flags(fp, monkeypatch):
    monkeypatch.setattr(hdr, "DV_PROFILE", "05")
    ...
    flags = hdr.detect_hdr(Path("dv.mkv"))
    assert flags == ["--dolby-vision-rpu", "copy", "--dolby-vision-profile", "05"]
```

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
