# Phase 3: Concurrency Resolution + Regression Baseline + CI - Context

**Gathered:** 2026-07-08 (--auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

Resolve the parallel-detection concurrency inconsistency, capture the mandatory parallel==sequential regression baseline on top of the resolved implementation, clean up the orphaned `dovi_tool` reference, and wire it all into CI:
- **DEBT-03** — resolve the ThreadPool-vs-ProcessPool inconsistency in `src/enpipe/detection/parallel.py` (profiling-informed), BEFORE the regression baseline is captured.
- **DEBT-04** — remove or document the orphaned `dovi_tool` devcontainer reference.
- **TEST-03** — a regression test asserting parallel detection == sequential detection by `(start_frame, end_frame)` pairs, software-fallback (`use_qsv=False`) so it runs in ordinary CI without GPU.
- **CI-01** — a GitHub Actions pipeline running lint + pure-logic unit tests + subprocess-mocked tests + the software-fallback regression test on every push against the pinned lockfile, with the hardware-gated tier excluded and named distinctly.

**Explicitly NOT in this phase:** the unified `enpipe` CLI (Phase 4 / PKG-01), the hardware-gated real-media HDR/DV validation (Phase 4 / TEST-04). No change to detection OUTPUT is allowed — the regression test is the guard.
</domain>

<decisions>
## Implementation Decisions

### DEBT-03 — ThreadPool/ProcessPool resolution
- **D-01:** PROFILE first, decide second. `detection/parallel.py:97-99` documents "real parallelism bypassing the GIL needs processes" but lines 127/146 use `ThreadPoolExecutor` for both `_boundary_worker` and `_segment_worker`. Measure whether the ThreadPool path actually parallelizes the CPU-bound PySceneDetect detector or serializes on the GIL (wall-clock of `detect_scenes_parallel(jobs=N)` vs `detect_scenes(jobs=1)` on a real multi-scene clip, plus a CPU-bound micro-benchmark isolating the detector from GPU-decode I/O overlap). Record the numbers.
- **D-02:** If profiling shows the GIL genuinely serializes and `ProcessPoolExecutor` is materially faster: switch the two executors in `detect_scenes_parallel` to `ProcessPoolExecutor` — the workers `_boundary_worker`/`_segment_worker` are ALREADY module-level (pickle-safe), so this is low-risk. If profiling shows threads are fine (GPU-decode I/O overlap masks the GIL, or the workload is subprocess-bound): KEEP `ThreadPoolExecutor` and FIX the misleading comment to document, with the measured rationale, why threads are acceptable here. Either way the contradiction is gone and the decision is evidence-backed.
- **D-03:** This resolution MUST land before TEST-03's baseline is captured (locked ordering) — changing the executor could change the parallel path's behavior, so the regression baseline must be taken against the resolved implementation. Detection OUTPUT must be unchanged regardless (TEST-03 proves it).

### DEBT-04 — orphaned dovi_tool
- **D-04:** KEEP `dovi_tool` in the devcontainer (`.devcontainer/Dockerfile` install + `post-create.sh` self-check) but DOCUMENT its retained purpose with an explicit comment: it is held for the planned Phase-4 Dolby Vision RPU-fidelity verification (`TEST-04` — the research/PITFALLS flagged wiring `dovi_tool` into an RPU frame-count/profile check, since the pipeline currently only guards aggregate video frame count). This satisfies DEBT-04's "removed OR documented reason for keeping" with the lower-churn option (removing then re-adding in Phase 4 is wasteful). The current DV path (`qsvencc --dolby-vision-rpu copy`) is unchanged.

### TEST-03 — parallel==sequential regression
- **D-05:** A regression test asserting `[(s.start_frame, s.end_frame) for s in detect_scenes_parallel(f, jobs=N)] == [(s.start_frame, s.end_frame) for s in detect_scenes(f, jobs=1)]`, constructing `DetectionConfig(use_qsv=Path("/dev/dri/renderD128").exists())` — i.e. software decode when no GPU — so it runs in ordinary CI without hardware. Generate a synthetic multi-source clip (ffmpeg lavfi concat) long enough with enough real cuts that `jobs=N` actually exercises the segment-splitting path (not a trivial single-segment case).
- **D-06:** This test lives in a DEFAULT-run (non-`hardware`) location so CI runs it. It runs AFTER DEBT-03 is resolved (D-03).

### CI-01 — GitHub Actions
- **D-07:** Create `.github/workflows/ci.yml` running on `ubuntu-latest` (no GPU), triggered on push + PR. Steps: `astral-sh/setup-uv` (pinned), `uv sync --locked` (from the committed lockfile), `apt-get install ffmpeg mkvtoolnix` (real NON-QSV binaries — the software-decode regression + EBML cross-validation tests need real ffmpeg/mkvmerge; only `qsvencc` is truly hardware-gated), then `uv run ruff check` (lint) and `uv run pytest -m "not hardware"` (unit + mocked + regression tiers).
- **D-08:** The `hardware`-marked tier is EXCLUDED from this CI (`-m "not hardware"`) and named distinctly — document in the workflow (and/or a stub self-hosted job) that hardware tests require a self-hosted Intel Arc runner and are NOT run on hosted CI. Never let a green hosted-CI check be mistaken for hardware validation.
- **D-09:** Add a MINIMAL, CONSERVATIVE `[tool.ruff]` config to `pyproject.toml` for the lint step — essentials only (pyflakes `F` for unused imports / undefined names, critical `E` errors), a generous line length, and NO aggressive restyling/import-reordering that would fight the preserved legacy style (Russian comments, `typing.List`, banners). The goal is catching real defects (it would have caught the `JOBS` dead-code finding), not reformatting. `pyright` type-checking stays deferred to v2 (QUAL-01); this phase does lint only, as CI-01 requires.

### Conventions & scope
- **D-10:** Preserve conventions verbatim (Russian docstrings, typing generics, banners). `legacy/` untouched as the oracle. No detection output change.

### Claude's Discretion
- Exact profiling methodology/tooling for D-01 (time-based comparison, `py-spy`, or a targeted micro-benchmark) — pick what gives a clear GIL-vs-not signal.
- Exact ruff rule selection within the "conservative, lint-only, don't-fight-legacy-style" envelope (D-09).
- The synthetic-clip recipe for TEST-03 (reuse Phase-2's `-cues_to_front`/lavfi-concat approach; ensure enough scenes for `jobs>1`).
- Whether the hardware exclusion in CI is a comment, a separate never-triggered job, or a documented runbook line.
</decisions>

<specifics>
## Specific Ideas

- DEBT-03 is a MEASURE-then-decide item, not a guess — the research (PITFALLS.md Pitfall 5) explicitly says the current speedup may be GPU-decode I/O overlap masking GIL serialization, which only profiling can distinguish. Do not pre-decide the executor.
- The ordering DEBT-03 → TEST-03 is locked and load-bearing: baseline the regression test against the RESOLVED implementation, never before.
- CI-01's "lint" is satisfied by ruff; the fuller pyright type-checking is intentionally a later (v2) concern.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Concurrency + CI research
- `.planning/research/PITFALLS.md` — Pitfall 5 (GIL/ThreadPool trap; profiling before deciding), Pitfall 3 (green CI ≠ hardware-validated; name the tiers distinctly)
- `.planning/research/STACK.md` — CI strategy (ubuntu-latest, setup-uv, apt ffmpeg/mkvmerge, hardware-gating via `hardware` marker), ruff config, `pytest -m "not hardware"` default
- `.planning/research/SUMMARY.md` — Phase-3 ordering (DEBT-03 before regression baseline) and CI scope

### Current code
- `src/enpipe/detection/parallel.py` — the ThreadPool/ProcessPool inconsistency (comment lines 97-99 vs `ThreadPoolExecutor` at 127/146); module-level `_boundary_worker`/`_segment_worker` (pickle-safe)
- `src/enpipe/detection/detect.py` — `detect_scenes` (the sequential jobs=1 reference for TEST-03)
- `src/enpipe/detection/config.py` — `DetectionConfig(use_qsv=...)` (software-fallback selector)
- `.devcontainer/Dockerfile`, `.devcontainer/post-create.sh` — the `dovi_tool` install + self-check (DEBT-04)
- `pyproject.toml` — where `[tool.ruff]` + the `hardware` marker live; `uv.lock` is the CI install source
- `legacy/scene_detection.py` — parity oracle (untouched)

### Project scope
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md` — DEBT-03, DEBT-04, TEST-03, CI-01 acceptance language
- `.planning/codebase/CONVENTIONS.md` — conventions to preserve; the concurrency-pattern notes
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_boundary_worker`/`_segment_worker` are already module-level (no closures) — deliberately structured for ProcessPool compatibility, so a switch is a low-risk executor swap (D-02).
- `detect_scenes` (sequential) is the ready-made oracle for the TEST-03 comparison.
- Phase-2's synthetic-`.mkv` / lavfi-concat recipe (with `-cues_to_front 1`) is a starting point for the TEST-03 multi-scene clip.
- The `hardware` pytest marker + `pytest -m "not hardware"` default (Phase 1) already separate the tiers CI needs.

### Established Patterns
- `use_qsv` is selected by constructing `DetectionConfig(use_qsv=...)` (no `--no-qsv` library flag) — same as the Phase-2 parity script.
- Threaded pools are used because the heavy work is subprocess/GPU; the OPEN question DEBT-03 answers is whether the *detector* itself (Python CPU work) is the exception.

### Integration Points
- New `.github/workflows/ci.yml`; new `[tool.ruff]` block in `pyproject.toml`; the `dovi_tool` devcontainer lines get a doc comment.
- TEST-03 test lives under `tests/` in a non-hardware location so both `pytest -m "not hardware"` and CI pick it up.
</code_context>

<deferred>
## Deferred Ideas

- Unified `enpipe` CLI entry point — Phase 4 (PKG-01).
- Hardware-gated real-media HDR10/HDR10+/DV validation + `dovi_tool` RPU-fidelity check — Phase 4 (TEST-04); DEBT-04 keeps `dovi_tool` around precisely for this.
- `pyright` type-checking in CI, coverage reporting, Hypothesis property tests, CI/devcontainer image parity, dependency-update automation — v2 (QUAL-01/03, CI-02).
</deferred>

---

*Phase: 03-concurrency-resolution-regression-baseline-ci*
*Context gathered: 2026-07-08*
