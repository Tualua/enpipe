---
phase: 05-single-command-pipeline-entry-point
reviewed: 2026-07-09T01:57:15Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/enpipe/cli/main.py
  - tests/unit/cli/test_cli_run.py
  - tests/integration/test_hardware_real_media.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-09T01:57:15Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** clean

## Summary

Reviewed the `enpipe run` single-command wrapper (`run_pipeline` + `run` subparser) added to `src/enpipe/cli/main.py`, its fast mocked unit tests (`tests/unit/cli/test_cli_run.py`), and the new hardware-gated parity test (`tests/integration/test_hardware_real_media.py::test_run_parity_vs_two_step`). This was verified as a genuinely additive, zero-behavior-change change:

- **Diff scope confirmed minimal:** `git diff ae4bee4..3f798ca -- src/enpipe/cli/main.py` shows the entire change is additive (new imports, new `run_pipeline` function, new `run` subparser block, one new docstring paragraph). The existing `detect_p`/`encode_p` subparser blocks and `main()` are byte-for-byte unchanged. `legacy/` is confirmed untracked/untouched (not part of the phase-5 commit range).
- **Namespace attribute routing traced end-to-end against the callees:** every attribute `run_detect` reads (`input, output, width, threshold, min_scene_len_frames, min_scene_len, no_qsv, qsv_device, jobs`) and every attribute `run_encode` reads (`video, scenes, out, frm, to, workdir, keep, jobs, no_audio, no_metrics, csv`) is present, correctly named, and populated from the correct `run` CLI flag in `run_pipeline`'s two hand-built `argparse.Namespace` objects. No misrouting found (in particular: `-o/--out` on `run` maps only to `encode_args.out`, never to the `.scenes` path — matches the requirement that final-`.mkv` output not be confused with the scenes-file path).
- **`.scenes` derivation verified identical to `run_detect`'s own default:** `run_pipeline` computes `scenes_path = args.scenes or Path(str(args.video) + ".scenes")` (main.py:50), which is the same formula as `detection/pipeline.py:42`'s `args.output or Path(str(args.input) + ".scenes")`. Since `detect_args.output` is always set to this pre-computed `scenes_path` (never `None`), `run_detect`'s own `or` branch is a no-op passthrough — the two derivations can never diverge by construction.
- **Strict sequencing confirmed:** no `threading`/`queue.Queue`/`asyncio`/`multiprocessing` symbols appear anywhere in `main.py`; `run_encode(encode_args)` is a plain top-level statement following `run_detect(detect_args)`'s return, guaranteeing no overlap between stages.
- **`--jobs` collision genuinely resolved:** the `run` subparser defines only `--detect-jobs` (default 4, matches legacy detect default) and `--encode-jobs` (default `ENCODE_JOBS`, matches legacy encode env-derived default) — no bare `--jobs` flag exists on `run` at all, so `enpipe run ... --jobs N` fails argparse's own unrecognized-argument handling (`SystemExit`) rather than silently routing to one stage. Verified by `test_bare_jobs_flag_rejected` and confirmed by direct pytest execution (below).
- **Additive-only preflight confirmed:** the new `shutil.which` loop in `run_pipeline` (main.py:44-46) checks the same 4 tools, in the same order, as `run_encode`'s own untouched preflight (`encoding/pipeline.py:72-74`) — it is a pure fail-fast duplicate that runs before the (potentially long) detect stage; `run_detect`/`run_encode` themselves were not modified (confirmed via diff) so their own preflight/no-preflight behavior (per D-09, `run_detect` deliberately has none) is unchanged.
- **Unit test seam is non-vacuous:** `run_pipeline` calls `run_detect(...)`/`run_encode(...)` by bare module-global name, so `monkeypatch.setattr(cli_main, "run_detect", ...)` genuinely intercepts the call at runtime (Python resolves the name from the module's global namespace at call time, not by reference captured at `def` time). Ran the suite directly to confirm the seam and assertions are real, not tautological:
  - `uv run pytest tests/unit/cli/test_cli_run.py -q` → **10 passed**
  - `uv run pytest tests/unit -q` → **83 passed** (no cross-file regressions)

  The 10 tests exercise real, falsifiable conditions: call order (`test_order_detect_before_encode`), full per-stage attribute routing including the `--scenes` override reaching both stages, the `--detect-jobs`/`--encode-jobs` split, bare-`--jobs` rejection, preflight-before-`run_detect` (with `calls == []` asserted after the expected `SystemExit`, proving neither stage ran), Namespace non-contamination (`hasattr` negative assertions), and legacy default asymmetry (`detect.jobs == 4` vs `encode.jobs == ENCODE_JOBS`).
- **Hardware parity test genuinely compares run-vs-two-step:** `test_run_parity_vs_two_step` runs `enpipe run` on one temp copy and manual `enpipe detect` + `enpipe encode` on a second, path-distinct copy (with an explicit `run_scenes != scenes2` collision-avoidance assertion), then checks final-`.mkv` frame-count parity, pre-mux `movie.obu` byte-identity (falling back to frame-count parity only if QSV hardware non-determinism is detected), and `.scenes` byte-identity across the two differently-pathed intermediates. `--no-metrics` is present on every `enpipe encode`/`enpipe run` invocation in the file, consistent with the documented OpenCL-unavailable constraint. Per `05-01-SUMMARY.md`, this test was executed for real against Arc hardware in the implementation session (not just self-skip-verified), which corroborates non-vacuousness, though this reviewer could not re-execute it here (no `/dev/dri/renderD128` in this environment — the test correctly self-skips via `pytestmark = pytest.mark.hardware` / `_hardware_available()`).

No divergence between `enpipe run` and the manual two-step was found. No behavior change to `run_detect`/`run_encode` was found. No concurrency/overlap between stages was found. No BLOCKER or WARNING-level issues were found.

## Info

### IN-01: Preflight duplication is intentional but worth a single follow-up note

**File:** `src/enpipe/cli/main.py:44-46` (vs. `src/enpipe/encoding/pipeline.py:72-74`)
**Issue:** `run_pipeline`'s fail-fast preflight and `run_encode`'s own preflight check the identical 4 tools in the identical order. This is explicitly documented as intentional (additive UX, not a behavior change) in both the module docstring and `05-01-SUMMARY.md`, and is correct as designed — flagging only as a documentation/maintainability note, not a defect: if the tool list in `run_encode`'s preflight ever changes, `run_pipeline`'s copy must be updated in lockstep or the fail-fast guarantee silently degrades (it would still work, just later, since `run_encode` would still catch it — no correctness risk, only a UX regression).
**Fix:** Optional — extract the tuple `("qsvencc", "ffprobe", "ffmpeg", "mkvmerge")` to a shared module-level constant (e.g. in `enpipe.shared`) that both `run_pipeline` and `run_encode` import, so the two preflight lists cannot drift. Not required before shipping; the current duplication is safe and already called out in the plan/summary as a conscious tradeoff (D-02 "reuse verbatim" precluded touching `run_encode` itself).

---

_Reviewed: 2026-07-09T01:57:15Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
