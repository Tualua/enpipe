---
phase: 03-concurrency-resolution-regression-baseline-ci
plan: 03
subsystem: infra
tags: [ci, github-actions, ruff, lint, pytest, uv]

# Dependency graph
requires:
  - phase: 03-concurrency-resolution-regression-baseline-ci (plan 01)
    provides: resolved ThreadPoolExecutor decision (DEBT-03) and dovi_tool documentation (DEBT-04)
  - phase: 03-concurrency-resolution-regression-baseline-ci (plan 02)
    provides: TEST-03 parallel==sequential regression test (default, non-hardware tier)
provides:
  - ruff dev dependency + minimal [tool.ruff] lint config (select = ["F", "E9"])
  - --strict-markers in pytest addopts
  - .github/workflows/ci.yml running lint + non-hardware tests on push/PR against the pinned lockfile
affects: [phase-4-ci-hardware-tier, phase-4-cli-packaging]

# Tech tracking
tech-stack:
  added: [ruff==0.15.20 (dev dependency), astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b (GitHub Action, SHA-pinned)]
  patterns: [SHA-pinned third-party GitHub Actions, comment-only hardware-tier exclusion in CI, separate required-vs-best-effort apt install steps]

key-files:
  created: [.github/workflows/ci.yml]
  modified: [pyproject.toml, uv.lock]

key-decisions:
  - "ruff select = [\"F\", \"E9\"] only (pyflakes + syntax errors) — verified clean on current src/tests/legacy/scratch; the fuller E/W pycodestyle set fires 15x E702 on the deliberately dense src/enpipe/mkv/ebml.py binary parser"
  - "ruff pinned exactly (==0.15.20) to match the project's existing exact-pin convention (pytest==9.1.1 etc.), rather than uv add's default >= constraint"
  - "mkvtoolnix install is a separate continue-on-error step (not combined with the required ffmpeg step) so an unavailable-in-repo mkvmerge package cannot block the ffmpeg-only TEST-03 regression test"
  - "Hardware-tier exclusion is comment-only in ci.yml (RESEARCH Open Question 3 discretion) — no stub self-hosted job; Phase 4/TEST-04 introduces the first actual hardware test and its own runner wiring"

requirements-completed: [CI-01]

# Metrics
duration: 6min
completed: 2026-07-08
---

# Phase 3 Plan 3: CI Pipeline (lint + non-hardware tests) Summary

**GitHub Actions `ci.yml` running ruff lint + `pytest -m "not hardware"` on every push/PR from the pinned `uv.lock`, with a SHA-pinned setup-uv, required ffmpeg, best-effort mkvtoolnix, and the hardware tier named-out distinctly**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-08T15:30:00Z (approx, continuation from Wave 2 completion)
- **Completed:** 2026-07-08T15:36:10Z
- **Tasks:** 2 completed
- **Files modified:** 3 (pyproject.toml, uv.lock, .github/workflows/ci.yml)

## Accomplishments
- Added `ruff==0.15.20` as a locked dev dependency with a minimal, legacy-style-safe `[tool.ruff]` config (`select = ["F", "E9"]`) — verified `uv run ruff check src tests` passes clean ("All checks passed!")
- Added `--strict-markers` to pytest `addopts` so a future marker-name typo fails loudly instead of silently selecting zero tests
- Created `.github/workflows/ci.yml`: a single `cpu-fallback` job on `ubuntu-latest`, triggered on `push` and `pull_request`, with SHA-pinned `astral-sh/setup-uv`, `uv sync --locked`, required `ffmpeg`, best-effort `mkvtoolnix`, `uv run ruff check src tests`, and `uv run pytest -m "not hardware"`
- Job name and top-of-job comment distinctly mark this as the no-GPU / software-fallback tier, deferring the hardware-gated tier to a Phase-4 self-hosted Arc runner (satisfies D-08 / T-03-07)
- Full local verification: `uv run ruff check src tests` clean; `uv run pytest -m "not hardware"` → 77 passed; `ci.yml` parses as valid YAML with all required markers present

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ruff dev dependency + minimal [tool.ruff] config + --strict-markers** - `2f28d93` (feat)
2. **Task 2: Create .github/workflows/ci.yml** - `dc0403a` (feat)

**Plan metadata:** (this commit) `docs(03-03): complete CI pipeline plan`

## Files Created/Modified
- `pyproject.toml` - added `ruff==0.15.20` to `[dependency-groups] dev`, added `[tool.ruff]`/`[tool.ruff.lint]` (line-length 100, target-version py312, select F+E9 with a precise rule-scope comment), added `--strict-markers` to pytest addopts
- `uv.lock` - re-locked to include the `ruff` resolution (installs via `uv sync --locked` in CI)
- `.github/workflows/ci.yml` - new CI workflow: checkout, SHA-pinned setup-uv, required ffmpeg install, best-effort mkvtoolnix install, `uv sync --locked`, ruff lint, `pytest -m "not hardware"`

## Decisions Made
- Pinned `ruff` exactly (`==0.15.20`) rather than leaving `uv add --dev ruff`'s default `>=0.15.20` constraint, to match this project's existing exact-pin convention for all other dependencies (`pytest==9.1.1`, `pytest-subprocess==1.6.0`, `pytest-mock==3.15.1`) — re-ran `uv lock` after the manual edit to keep `uv.lock` consistent.
- Wrote the ruff `select` comment to precisely name the rule families caught (F401 unused imports, F811 redefinition, F841 unused locals, F821 undefined names, E999/E902 syntax/IO errors) rather than a vague "catches dead code" claim, and deliberately did NOT repeat the RESEARCH-flagged-inaccurate "would have caught the JOBS finding" justification (Pitfall 1) anywhere in code or this summary.
- mkvtoolnix install kept as its own `continue-on-error: true` step, separate from the required ffmpeg step, so a repo-unavailable mkvmerge package can never block the ffmpeg-only TEST-03 regression test — matches D-07/T-03-08 exactly.
- Comment-only hardware-tier exclusion (no stub `workflow_dispatch`/self-hosted job) per RESEARCH Open Question 3's resolved discretion — lowest-effort option that still satisfies "visibly named, never confused with hardware validation."

## Deviations from Plan

None - plan executed exactly as written. The only adjustment (pinning `ruff==` instead of the `uv add` default `>=`) is a convention-consistency choice within Claude's discretion for exact ruff/dependency specification, not a deviation from any locked plan requirement — it does not change ruff's behavior or the config's substance.

## Issues Encountered
None. `yaml` module was not installed in the base Python for local YAML-parse verification of `ci.yml`; installed `pyyaml` via `pip install --user` (not added to the project's `uv.lock`/`pyproject.toml` — a one-time local verification aid only, matching the ephemeral-tool precedent set by `py-spy` in Plan 03-01).

## User Setup Required

**External service requires manual observation.** GitHub Actions runs automatically once `ci.yml` is pushed to the remote — no dashboard configuration is needed, but per the plan's `user_setup` block:
- Confirm the CI workflow appears and passes under the Actions tab after this branch/commit is pushed to GitHub (location: GitHub repo → Actions).

This cannot be verified from within this local execution session (no push to a remote occurred as part of this plan) — flagged for the user to check after pushing.

## Next Phase Readiness
- CI-01 satisfied: every future push/PR now runs lint (`ruff check src tests`) + the full non-hardware test tier (77 tests: pure-logic unit, subprocess-mocked, and the TEST-03 parallel==sequential regression) against the pinned lockfile.
- Phase 3 (Concurrency Resolution + Regression Baseline + CI) is now fully complete: DEBT-03 (resolved, threads kept with corrected rationale), DEBT-04 (dovi_tool documented), TEST-03 (regression test wired and passing), CI-01 (this plan).
- Phase 4 will add the first `hardware`-marked test (TEST-04) and its self-hosted Arc-equipped runner wiring — `ci.yml`'s comment already anticipates this and the `hardware` marker/`-m "not hardware"` default are already in place to receive it.
- No blockers identified for Phase 4.

---
*Phase: 03-concurrency-resolution-regression-baseline-ci*
*Completed: 2026-07-08*

## Self-Check: PASSED

- FOUND: .github/workflows/ci.yml
- FOUND: [tool.ruff.lint] select = ["F", "E9"] in pyproject.toml
- FOUND: .planning/phases/03-concurrency-resolution-regression-baseline-ci/03-03-SUMMARY.md
- FOUND: commit 2f28d93 (Task 1)
- FOUND: commit dc0403a (Task 2)
