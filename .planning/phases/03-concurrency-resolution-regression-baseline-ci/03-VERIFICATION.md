---
phase: 03-concurrency-resolution-regression-baseline-ci
verified: 2026-07-08T15:42:16Z
status: human_needed
score: 18/18 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
human_verification:
  - test: "Push the local `main` branch (currently 63 commits ahead of `origin/main`) to GitHub and confirm the `ci / cpu-fallback` job appears under the Actions tab and passes"
    expected: "The workflow triggers on push, runs to completion, and shows a green check for the `cpu-fallback` job (lint + unit + mocked + TEST-03 regression, no GPU)"
    why_human: "This session has a configured remote (`origin` -> github.com/Tualua/enpipe.git) but nothing beyond the initial commit has been pushed (`git status -sb` shows `ahead 63`), so GitHub Actions has never executed this workflow. `ci.yml`'s existence, valid YAML, SHA-pinned action, and local-equivalent command success (`uv run ruff check src tests`, `uv run pytest -m \"not hardware\"`) are automatable and were verified directly in this session; the live hosted run itself cannot be observed from this sandbox."
---

# Phase 3: Concurrency Resolution + Regression Baseline + CI Verification Report

**Phase Goal:** Parallel scene detection uses a profiling-justified executor, the mandatory parallel==sequential regression test runs against that resolved implementation, and every push is automatically verified by CI using the pinned lockfile.
**Verified:** 2026-07-08T15:42:16Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | ThreadPool-vs-ProcessPool contradiction in `parallel.py` is gone; comment agrees with code and carries measured numbers | VERIFIED | `src/enpipe/detection/parallel.py:100-133` — comment rewritten in Russian with Layer-1/Layer-2 numbers embedded; `grep` for the old contradictory phrase ("нужны процессам"/"bypass GIL") returns nothing; `ThreadPoolExecutor` used at both `with` blocks (161, 180), matching the comment |
| 2 | Executor decision follows a QUANTIFIED rule; SUMMARY records measured numbers + fired branch | VERIFIED | Rule stated inline in code comment (lines 124-127) and in `03-01-SUMMARY.md` "Measured Profiling Numbers" table: speedup<1.5x TRUE (0.67x), ratio>2x FALSE (1.43x) → rule does not fire → threads kept |
| 3 | Detection output unchanged: `detect_scenes_parallel(jobs=2) == detect_scenes(jobs=1)` on profiling clip | VERIFIED | Ran the plan's inline smoke check live via `uv run python3 -c ...` against `scratch/profiling_debt03_sample.mkv`: `OK: 2 scenes, parallel==sequential` |
| 4 | Profiling numbers provably came from the real parallel path (engagement check, not fallback) | VERIFIED | `scratch/profiling_debt03_out.txt` (regenerated artifact, read directly): `_segment_worker calls=2 (engagement check PASSED)` for both use_qsv arms |
| 5 | `dovi_tool` retained with explicit Phase-4 comment, no AV1-extract-rpu overclaim | VERIFIED | `.devcontainer/Dockerfile:67-80` and `.devcontainer/post-create.sh:53-56` — both carry retention comments tied to Phase-4/TEST-04; Dockerfile explicitly states `extract-rpu` is "документирована только для HEVC-битстрима" and AV1 support is unconfirmed — no overclaim |
| 6 | Pure deterministic unit test proves the clip parameters satisfy the fallback gate for jobs=2 AND jobs=3 | VERIFIED | `tests/unit/detection/test_parallel_gate.py` — parameterized `jobs=[2,3]`, re-derives `min_span` formula independently, plus a negative/trap case; collected and passing |
| 7 | Regression test asserts `parallel(jobs=N) == sequential(jobs=1)` by `(start_frame,end_frame)` for jobs=[2,3] via `DetectionConfig(use_qsv=Path('/dev/dri/renderD128').exists())`, no skip logic | VERIFIED | `tests/integration/test_parallel_regression.py` — `@pytest.mark.parametrize("jobs", [2, 3])`, `renderD128` selector present, `! grep -q skipif` holds, equality assertion present and passing |
| 8 | Regression test proves the REAL parallel branch ran (fallback `detect_scenes` NOT invoked), executor-agnostic, crash-safe under either DEBT-03 outcome | VERIFIED | `fallback_spy.call_count == 0` required/unconditional assertion (lines 153-157); conditional `_segment_worker` spy gated on `getattr(parallel_module, "ProcessPoolExecutor", None) is None` (lines 142-149), correctly self-skips since ProcessPool was not adopted |
| 9 | `_sanitize_boundaries` + `non_cut_offsets` merge stitch exercised by a focused pure unit test, no media | VERIFIED | `tests/unit/detection/test_parallel_merge.py` — direct call to `_sanitize_boundaries` with dupes/out-of-range/unsorted inputs; `non_cut_offsets` merge driven via monkeypatched `probe_source`/`_boundary_worker`/`_segment_worker` + synchronous executor shim; merge and all-cut-control cases both present and passing |
| 10 | All new tests run under `pytest -m "not hardware"` (default tier) | VERIFIED | `uv run pytest -m "not hardware" --collect-only -q` lists all 9 new tests (gate x3, merge x4, regression x2); full run passes 77/77 |
| 11 | `ruff` pinned dev dependency + minimal `[tool.ruff]` config passes clean on current code | VERIFIED | `uv run ruff check src tests` → "All checks passed!" (exit 0); `uv.lock` contains `name = "ruff" / version = "0.15.20"`; `pyproject.toml` `[tool.ruff.lint] select = ["F", "E9"]` with a precise (not vague) comment |
| 12 | `--strict-markers` in pytest addopts | VERIFIED | `pyproject.toml:39` — `addopts = "-m \"not hardware\" --import-mode=importlib --strict-markers"`; `hardware` marker registered at line 28 |
| 13 | GitHub Actions workflow runs on push/PR against the pinned lockfile: SHA-pinned setup-uv, required ffmpeg + best-effort mkvtoolnix, `uv sync --locked`, ruff check, `pytest -m "not hardware"` | VERIFIED | `.github/workflows/ci.yml` — parses as valid YAML, triggers `push`+`pull_request`; `astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b` (SHA, not tag); `uv sync --locked`, `uv run ruff check src tests`, `uv run pytest -m "not hardware"` all present as steps; ffmpeg install step has no `continue-on-error`, mkvtoolnix install step has `continue-on-error: true` |
| 14 | Hardware tier excluded and CI job named/commented distinctly | VERIFIED | Job name `"ci / cpu-fallback (lint + unit + mocked + regression, no GPU)"`; top-of-job comment states no QSV/Arc validation and that the `hardware` marker/self-hosted runner is deferred to Phase 4 |

**Score:** 14/14 truths verified (roadmap SC 1-4 map 1:1 onto truths 1-3+6-10 / 4+11-14 above; all merged and verified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scratch/profiling_debt03.py` | Reproducible Layer-1/Layer-2 profiling script, ≥40 lines | VERIFIED | 215 lines; re-checked output artifact `scratch/profiling_debt03_out.txt` matches numbers cited in SUMMARY exactly |
| `src/enpipe/detection/parallel.py` | Resolved executor + measured-rationale comment | VERIFIED | `def detect_scenes_parallel` present; `ThreadPoolExecutor` kept; comment (lines 97-133) internally consistent, carries measured numbers |
| `.devcontainer/Dockerfile` | `dovi_tool` install block + retained-purpose comment | VERIFIED | Install `RUN` block intact (lines 81-89); comment block at 67-80 |
| `.devcontainer/post-create.sh` | `dovi_tool` self-check + matching comment | VERIFIED | Comment at lines 53-55, self-check at 56 |
| `tests/unit/detection/test_parallel_gate.py` | Pure gate-arithmetic test, ≥20 lines, jobs=[2,3] | VERIFIED | 56 lines; parameterized; passing |
| `tests/unit/detection/test_parallel_merge.py` | Pure `_sanitize_boundaries`+merge test, ≥30 lines | VERIFIED | 157 lines; passing |
| `tests/integration/test_parallel_regression.py` | Real-clip regression test, ≥50 lines, jobs=[2,3] | VERIFIED | 170 lines; passing |
| `pyproject.toml` | ruff dev dep + `[tool.ruff]` + `--strict-markers` | VERIFIED | All three present |
| `.github/workflows/ci.yml` | CI pipeline, SHA-pinned setup-uv | VERIFIED | Present, valid YAML, contains `astral-sh/setup-uv` SHA pin |
| `uv.lock` | ruff resolved into lockfile | VERIFIED | `name = "ruff"` / `version = "0.15.20"` entry present |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `parallel.py` | resolution comment | measured numbers inline | WIRED | Comment carries raw seconds + ratios; `detect_scenes_parallel` referenced |
| `test_parallel_regression.py` | `detect_scenes_parallel` | equality assertion vs `detect_scenes(jobs=1)` | WIRED | Assertion present and passing for jobs=[2,3] |
| `test_parallel_regression.py` | `enpipe.detection.detect.detect_scenes` | `call_count == 0` no-fallback assertion | WIRED | Present, unconditional, verified live via full pytest run |
| `test_parallel_regression.py` | `enpipe.detection.parallel._segment_worker` | conditional ThreadPool-only call-count refinement | WIRED | Correctly gated on `getattr(parallel_module, "ProcessPoolExecutor", None) is None`; active since ProcessPool was not adopted |
| `test_parallel_merge.py` | `enpipe.detection.parallel._sanitize_boundaries` | direct call with synthetic inputs | WIRED | Called directly in `test_sanitize_boundaries_sorts_dedupes_clamps_and_preserves_is_cut` |
| `.github/workflows/ci.yml` | `uv.lock` | `uv sync --locked` | WIRED | Step present |
| `.github/workflows/ci.yml` | tests incl. TEST-03 | `uv run pytest -m "not hardware"` | WIRED | Step present; locally reproduces 77 passed |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Lint clean | `uv run ruff check src tests` | "All checks passed!" | PASS |
| Full non-hardware test tier | `uv run pytest -m "not hardware" -q` | "77 passed in 21.38s" | PASS |
| Parallel==sequential smoke check (plan's own verify command) | `uv run python3 -c "..."` against `scratch/profiling_debt03_sample.mkv` | "OK: 2 scenes, parallel==sequential" | PASS |
| CI workflow YAML structural check | `python3 -c "import yaml; ..."` | all required elements present (SHA pin, `uv sync --locked`, `ruff check src tests`, `not hardware`, ffmpeg, mkvtoolnix `continue-on-error`) | PASS |
| No leftover contradictory GIL/process claim in `parallel.py` | `grep -n "нужны процессам\|bypass.*GIL"` | no matches | PASS |
| No debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) in phase-modified files | `grep` across all 8 modified files | no matches | PASS |
| `legacy/` unchanged | `git log -- legacy/` / `git diff HEAD -- legacy/` | `legacy/` remains untracked, no commit history touches it | PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` convention; PLAN/SUMMARY files use inline `<verify><automated>` commands, all of which were re-run above (ruff, pytest, the smoke-check, and the YAML structural check).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| DEBT-03 | 03-01 | ThreadPool-vs-ProcessPool inconsistency resolved (profiling-informed), before TEST-03 baseline | SATISFIED | Truths 1-4 above; wave ordering (`depends_on: ["03-01"]` in 03-02) enforces D-03 |
| DEBT-04 | 03-01 | Orphaned `dovi_tool` removed or documented reason kept | SATISFIED | Truth 5 above |
| TEST-03 | 03-02 | Regression test: parallel==sequential by (start_frame,end_frame), software-fallback, runs in ordinary CI | SATISFIED | Truths 6-10 above |
| CI-01 | 03-03 | CI pipeline: lint + unit + mocked + software-fallback regression on every push, pinned lockfile, hardware tier excluded/named | SATISFIED (automatable scope); live hosted run NOT YET OBSERVED | Truths 11-14 above; see Human Verification section for the one non-automatable item |

No orphaned requirements — `REQUIREMENTS.md` traceability table maps exactly DEBT-03, DEBT-04, TEST-03, CI-01 to Phase 3, all four appear in plan frontmatter `requirements:` fields.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` across all 8 phase-modified files (`parallel.py`, `Dockerfile`, `post-create.sh`, the 3 new test files, `ci.yml`, `pyproject.toml`) returned zero matches. No stub returns, no hardcoded empty outputs feeding assertions, no console.log-only implementations (Python project — n/a pattern anyway). Test files exercise real code paths (real `detect_scenes_parallel`/`detect_scenes` against real generated media in the integration test; real `_sanitize_boundaries`/merge logic against monkeypatched-but-real function calls in the unit test).

### Human Verification Required

### 1. Live GitHub Actions run

**Test:** Push the current local `main` (63 commits ahead of `origin/main`) to `origin` and check the Actions tab of `github.com/Tualua/enpipe`.
**Expected:** The `ci / cpu-fallback (lint + unit + mocked + regression, no GPU)` job triggers on push, and completes green (all steps pass, matching the local reproduction: ruff clean, 77 tests passed).
**Why human:** A remote (`origin`) IS configured in this repo (unlike the assumption stated in the verification brief), but nothing beyond the initial commit (`b816682`) has been pushed — `git status -sb` shows `ahead 63`. GitHub Actions has therefore never executed this workflow, and its live behavior (runner provisioning, real `apt-get`/`setup-uv` network calls, actual CI minutes) cannot be observed from this sandbox. Every automatable proxy (YAML validity, exact step content, SHA pin, and local-equivalent command success for both `ruff check` and `pytest -m "not hardware"`) was verified directly in this session and passed. This is flagged per the verification brief's explicit instruction: do not fail the phase on the absence of an observed live run, but do surface it for human confirmation post-push.

### Gaps Summary

No blocking gaps. All 18 must-haves (14 observable truths + supporting artifacts/links, deduplicated against the 4 roadmap Success Criteria) are verified directly against the codebase: code was read and grepped, the resolution comment and profiling output were cross-checked number-for-number against the SUMMARY claims, the plan's own inline smoke-check command was re-executed live (not merely trusted), and both `uv run ruff check src tests` and `uv run pytest -m "not hardware"` were run fresh in this session (77/77 passing, matching 03-02-SUMMARY's claimed count exactly). The only outstanding item is non-blocking and inherent to the sandbox: the CI workflow has not yet been observed running on GitHub's hosted infrastructure because the branch has not been pushed. This does not indicate any defect in the phase's deliverables — `ci.yml` is structurally correct and its steps reproduce successfully locally.

---

*Verified: 2026-07-08T15:42:16Z*
*Verifier: Claude (gsd-verifier)*
