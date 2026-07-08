---
phase: 03-concurrency-resolution-regression-baseline-ci
reviewed: 2026-07-08T15:43:25Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - src/enpipe/detection/parallel.py
  - .devcontainer/Dockerfile
  - .devcontainer/post-create.sh
  - tests/integration/test_parallel_regression.py
  - tests/unit/detection/test_parallel_gate.py
  - tests/unit/detection/test_parallel_merge.py
  - pyproject.toml
  - uv.lock
  - .github/workflows/ci.yml
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-08T15:43:25Z
**Depth:** deep
**Files Reviewed:** 9 (scratch/profiling_debt03.py additionally inspected as supporting evidence, not a shipped source file)
**Status:** clean

## Summary

Phase 3 closes DEBT-03 (concurrency contradiction), DEBT-04 (dovi_tool documentation), TEST-03 (parallel==sequential regression baseline), and CI-01 (GitHub Actions wiring). I reviewed every file in scope with an adversarial stance, specifically probing the areas flagged as highest-risk in the task brief: whether the regression tests can pass vacuously, whether `parallel.py`'s executor/behavior actually changed, whether the ffprobe gate is genuinely clip-derived, whether the ThreadPool-only `_segment_worker` spy is safely gated against a hypothetical future `ProcessPoolExecutor` switch, whether `ci.yml` has supply-chain or blocking-step defects, whether the ruff config fires on the current codebase, and whether the profiling script's decision numbers could have come from a silent fallback run.

Concretely verified (not just read):
- `git diff` between the pre-Phase-3 commit and the DEBT-03 fix commit confirms **only the comment block changed** in `parallel.py` (lines 97-133) — no executor, algorithm, or gate-arithmetic edits. `detect_scenes_parallel` is byte-for-byte behaviorally identical.
- Traced `_sanitize_boundaries` + the `non_cut_offsets` merge arithmetic in `test_parallel_merge.py` by hand against `parallel.py`'s actual offset/merge logic (lines 186-209) — the synthetic `is_cut=False` interior-boundary test genuinely exercises the merge branch (`merged[-1][1] == s and s in non_cut_offsets`) and the all-cut control genuinely exercises the no-merge path. Confirmed by running the suite.
- Confirmed the regression test's "un-fakeable" engagement guard is sound: `detect_scenes_parallel`'s two silent-fallback sites (`total < jobs*min_span` gate, `len(bnds) < 3` collapse) both resolve `detect_scenes` via the exact same deferred `from .detect import detect_scenes` against the `enpipe.detection.detect` module, in the parent process, before any executor/pickling — so `mocker.spy(detect_module, "detect_scenes")` + `call_count == 0` after the parallel call is a valid, executor-agnostic proof that *neither* fallback fired. This closes the vacuous-pass hole (a bare `>=2 scenes` check would pass under either fallback too).
- Confirmed the `_segment_worker` spy is correctly gated: `is_thread_pool_executor = getattr(parallel_module, "ProcessPoolExecutor", None) is None`. Since `parallel.py` only imports `ThreadPoolExecutor`, the attribute is genuinely absent today, so the spy runs; if a future DEBT-03 revision switches to `ProcessPoolExecutor` (imported by that name, per the documented convention), `hasattr` flips and the spy — which pytest-mock autospecs and which cannot be pickled through `ProcessPoolExecutor.map` — is skipped, avoiding the documented `PicklingError` hard-crash.
- Confirmed the ffprobe engagement gate is genuinely clip-derived, not assumed: `_probe_actual_frame_count` runs real `ffprobe -count_frames` against the just-generated clip and the gate assertion uses the *probed* fps/frame-count, not the constants used to size the clip.
- Ran `uv run ruff check src tests` → "All checks passed!" (clean on current code, confirming the minimal `select = ["F", "E9"]` config does not fight the preserved legacy style).
- Ran `uv run pytest -m "not hardware" -q` → 77 passed, including both new Phase-3 regression parametrizations (`jobs=2`, `jobs=3`) against real ffmpeg-generated media.
- Ran `uv sync --locked` → succeeds; `uv.lock` contains a resolved `ruff==0.15.20` entry.
- Reviewed `ci.yml`: `astral-sh/setup-uv` is SHA-pinned (not a floating tag); `uv sync --locked` is used (fails closed on lockfile drift); ffmpeg install is a required step; mkvtoolnix install is isolated in its own step with `continue-on-error: true` (belt-and-suspenders redundant with its own `|| echo` fallback — informational only, see IN-01) and cannot block the ffmpeg-only tests; `pytest -m "not hardware"` excludes the hardware tier; the job is named/commented distinctly as the no-GPU software-fallback tier so a green run cannot be mistaken for real-Arc validation.
- Reviewed `scratch/profiling_debt03.py`: Layer-1 timing installs an in-process call-counting wrapper around `_segment_worker` and asserts `> 1` invocations *before* printing/using the jobs=2 numbers, for both `use_qsv` arms — so the decision numbers provably came from the real parallel path, not a fallback. The numbers printed in `scratch/profiling_debt03_out.txt` (jobs=1 6.53s / jobs=2 9.81s / speedup 0.67x at use_qsv=False; Layer-2 ratio 1.43x) match exactly what's embedded in the `parallel.py` resolution comment, and the stated decision rule (switch only if speedup<1.5x AND ratio>2x) is applied correctly (first condition true, second false → keep threads).
- Reviewed `.devcontainer/Dockerfile` and `post-create.sh`: `dovi_tool` install block is unchanged (still installs), with an added comment correctly scoping retention to planned Phase-4 TEST-04 work and explicitly *not* claiming `extract-rpu` works on the pipeline's AV1 output (cites the HEVC-only limitation in `legacy/encode_scenes.py`).

No BLOCKER or WARNING findings. One INFO-level, purely stylistic observation below.

## Info

### IN-01: Redundant double error-suppression on the mkvtoolnix CI step

**File:** `.github/workflows/ci.yml:35-38`
**Issue:** The mkvtoolnix install step sets `continue-on-error: true` at the step level *and* appends `|| echo "..."` inside the shell script itself. Either alone is sufficient to prevent this step from blocking the job (the plan's acceptance criteria only required "non-fatal"); having both is not a defect — the step already can't fail — but it is unnecessary belt-and-suspenders that could confuse a future reader into thinking one of the two mechanisms is load-bearing when it isn't.
**Fix:** Optional simplification — drop one of the two guards, e.g. keep only `continue-on-error: true` and let `apt-get install` fail loudly in the log (still non-blocking to the job) rather than swallowing the error into an echo:
```yaml
      - name: Install mkvtoolnix (best-effort — not required by any test wired this phase)
        continue-on-error: true
        run: sudo apt-get install -y --no-install-recommends mkvtoolnix
```

---

_Reviewed: 2026-07-08T15:43:25Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
