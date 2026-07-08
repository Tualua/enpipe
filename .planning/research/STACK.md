# Stack Research

**Domain:** Packaging, testing, linting, and CI for a subprocess-heavy Python CLI wrapping external media binaries (ffmpeg/qsvencc/mkvmerge) on Intel Arc QSV hardware
**Researched:** 2026-07-08
**Confidence:** HIGH (packaging/lint/CI tooling verified against PyPI/official docs) / MEDIUM (subprocess-testing strategy — verified via multiple sources but no single canonical "official" doc)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `uv` | ≥0.11 (0.11.28 current, 2026-07-07) | Project/dependency manager, venv, lockfile, task runner | Single Rust binary replaces pip + pip-tools + venv + pipx; `uv.lock` is a cross-platform lockfile (one file resolves for the devcontainer's Debian trixie image regardless of who edits it); 10-100x faster installs matter for devcontainer rebuild time; already the closest thing to a 2026 default for new Python projects, and the project's own `.devcontainer` is exactly the kind of pinned, reproducible environment `uv` is built for. Confidence: HIGH. |
| `uv_build` | pinned via `requires = ["uv_build>=0.11,<0.12"]` | PEP 517 build backend | Declared production-stable as of June 2026 (uv-build 0.11.19). Zero-config, 10-35x faster builds than hatchling/flit/setuptools for a project with no compiled extensions, no dynamic versioning-from-VCS need, and no plan to publish to PyPI (this is a local CLI tool, `pip install -e .` / `uv tool install` from the repo is the only "distribution" needed). Confidence: HIGH. |
| `pyproject.toml` (PEP 621) | — | Single manifest: metadata, dependencies, entry points, tool config | Standard since PEP 621; consolidates what is currently three untracked things (unpinned `pip install`, no entry point, no lint config) into one version-controlled file. Confidence: HIGH. |
| `pytest` | ≥9.1 (9.1.1 current, 2026-06-19) | Test framework | De facto standard; fixtures + `tmp_path` + `monkeypatch` are the right primitives for a subprocess-orchestration codebase (temp workdirs, fake binaries on `PATH`, env-var config overrides). `unittest`/`nose` are not competitive choices in 2026. Confidence: HIGH. |
| `ruff` | ≥0.15 (0.15.20 current, 2026-06-25) | Linter + formatter (replaces flake8/isort/pydocstyle/pyupgrade + black) | One Rust binary, one config block in `pyproject.toml`, no plugin-version-matrix to maintain. This matters specifically here because the codebase has *no* current lint config (`CONCERNS.md` notes a stray `.ruff_cache` gitignore entry with no actual config) — ruff lets one dependency+config replace what would otherwise be 4-5 separate tools. Confidence: HIGH. |
| `pyright` (via `basedpyright` or plain `pyright`) | latest | Static type checker | For a **new** codebase being packaged from scratch (not one with years of mypy-plugin investment), Pyright is the stronger 2026 default: ~98% typing-spec conformance vs mypy, checks unannotated code by default (useful here — `legacy/*.py` has essentially no type hints yet), and gives immediate editor feedback in VS Code (the project already standardizes on a VS Code devcontainer). mypy remains fine if there's a reason to prefer it, but don't pick it by default. `ty` (Astral's new checker) is NOT recommended yet — still 0.0.x, no stable API, breaking diagnostic changes between versions as of July 2026; revisit at its 1.0 release. Confidence: MEDIUM (comparative claims sourced from third-party 2026 comparison articles, not a single official benchmark). |
| `pytest-subprocess` | latest (2.x) | Fake/register subprocess calls without touching real ffmpeg/qsvencc/mkvmerge | Purpose-built for exactly this codebase's shape: it hooks `subprocess.Popen` (the base of `run`/`call`/`check_output`, all of which `legacy/*.py` uses), so tests register expected argv patterns and canned stdout/stderr/returncodes without real binaries or GPU access. This is the correct default over hand-rolled `unittest.mock.patch("subprocess.run")` because it exercises the *actual* call surface (positional vs keyword args, `Popen` vs `run`) instead of asserting against a specific call signature that breaks on refactor. Confidence: MEDIUM (no single official doc naming it "the standard"; corroborated by multiple independent sources and its own maturity/adoption). |
| `hypothesis` | ≥6.150 | Property-based testing for frame/seek arithmetic | Directly targets the exact fragile code flagged in `CONCERNS.md`: `kf_before`, `fmt_seek`, `_sanitize_boundaries`, the millisecond-rounding-to-keyframe math in `encode_scenes.py`. Property tests ("for all frame counts / fps / offsets, `fmt_seek` output is monotonic and never lands before the requested keyframe") catch off-by-one regressions that example-based tests would miss, and specifically address the CONCERNS.md line "An off-by-one here would corrupt every chunk boundary silently." Confidence: HIGH for the tool itself; MEDIUM that it's "standard" (it is widely used but genuinely optional — flag as recommended-not-mandatory). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-cov` + `coverage[toml]` | pytest-cov ≥6.x, coverage ≥7.15 | Coverage measurement/reporting in CI | Add once the test suite exists; `[tool.coverage.run]` in `pyproject.toml`, gate CI on a coverage floor once baseline is established (do not gate at 100% — subprocess-heavy code has legitimate hardware-only branches that can't run in CI). |
| `pytest-mock` | latest | Thin `mocker` fixture wrapper over `unittest.mock` | For mocking non-subprocess collaborators (e.g., `os.environ`, filesystem stat calls) where `pytest-subprocess` doesn't apply — keeps mock lifecycle (`mocker.patch` auto-undo) consistent with the rest of the suite instead of mixing raw `unittest.mock.patch` decorators. |
| `pytest-xdist` | latest | Parallel test execution | Optional; only worth adding once the suite is large enough that wall-clock matters. Not needed at initial productionization scope. |
| `syrupy` | latest | Snapshot testing | Useful specifically for the `.scenes` text-log format and any structured (CSV/JSON) replacement of it (`CONCERNS.md`'s "implicit unversioned text-file protocol" pitfall) — snapshot the parsed scene list against a committed fixture so format drift is caught by a diff instead of silently. Optional; only add if the roadmap decides to formalize the inter-script protocol. |
| `pip-audit` or `uv`'s built-in advisory checks | latest | Dependency vulnerability scanning | Run in CI on `uv.lock`; low-effort, catches known-CVE dependencies in `scenedetect`/`numpy` before they ship. |
| `pre-commit` | latest | Git hook runner for ruff/pyright on commit | Optional but recommended given there is currently zero enforcement; wires `ruff check --fix`, `ruff format`, and (optionally) `pyright` into a pre-commit hook so CI failures are caught locally first. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `astral-sh/setup-uv` (GitHub Action) | Installs a pinned `uv` version in CI, restores cache | Pin the action to a specific `uv` version (e.g. `version: "0.11.28"`) rather than "latest" — mirrors the exact pinning discipline `CONCERNS.md` flags as missing for `qsvencc`/`dovi_tool`. Use `enable-cache: true` for faster CI runs. |
| GitHub Actions (`ubuntu-latest` runner) | CI for lint/type-check/unit tests, no GPU needed | Standard hosted runner is sufficient for everything except real `qsvencc` encode tests — see CI Strategy below. |
| Self-hosted runner (optional, deferred) | GPU-gated integration tests against real Intel Arc hardware | Only needed if/when the project wants push-button integration testing against the actual NAS hardware; label-gate it (`runs-on: [self-hosted, qsv]`) and keep it a separate, manually-triggered or nightly workflow — do not block PR merges on hardware that isn't guaranteed available. Confidence: MEDIUM (pattern is well-established in the GPU/ML CI ecosystem generally; no enpipe-specific precedent to point to). |

## Installation

```bash
# Core: uv itself (one-time, or via devcontainer feature)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Project init (creates pyproject.toml + uv.lock)
uv init --package enpipe
cd enpipe

# Runtime dependencies (pin explicit versions once validated against real media)
uv add "scenedetect[opencv-headless]==0.7.*" numpy

# Dev dependencies
uv add --dev pytest pytest-subprocess pytest-mock pytest-cov hypothesis ruff pyright pre-commit

# Sync locked environment (CI + local use this identically)
uv sync --locked --all-extras --dev

# Run the test suite
uv run pytest

# Lint / format / type-check
uv run ruff check .
uv run ruff format .
uv run pyright
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `uv` | Poetry | If the team already has deep Poetry tooling/CI investment elsewhere and wants stack consistency across repos — Poetry is mature and fine, just slower and now the "legacy modern" choice rather than the 2026 default. |
| `uv` | PDM | PDM pioneered PEP 621-native workflows but has smaller ecosystem momentum than `uv` in 2026; only pick it if a specific PDM plugin is needed that has no `uv` equivalent. |
| `uv` | Hatch (the CLI, not hatchling) | If the project needs Hatch's environment-matrix features (multiple named test environments with different dependency sets) beyond what `uv`'s dependency groups + CI matrix already cover — not needed here (single Python 3.12 target, single environment). |
| `uv_build` | `hatchling` | If the project later needs VCS-based dynamic versioning (`uv-dynamic-versioning` plugin doesn't work with `uv_build`) or custom build-time file generation/hooks. Not a current need. |
| `pyright` | `mypy` | If a contributor strongly prefers mypy's plugin ecosystem, or if third-party stub quality for `scenedetect`/`numpy` turns out to be meaningfully better under mypy in practice — verify by trial before committing either way; both are reasonable, this is a soft recommendation. |
| `pytest-subprocess` | `unittest.mock.patch("subprocess.run")` | For a single, isolated call where full argv-pattern registration is overkill — plain `mocker.patch` is fine for a one-off. Don't use it as the *primary* strategy across the suite; it couples tests to exact call signatures and breaks on harmless refactors (e.g., switching `subprocess.run` to `Popen` internally). |
| GitHub-hosted `ubuntu-latest` for all CI | Self-hosted GPU runner for all CI | Only if the team wants every PR gated on real QSV hardware — not recommended as the default because it makes CI depend on a single physical NAS being online/available, contradicting the goal of fast, reliable PR feedback. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Unpinned `pip install` at container build time (current state) | `CONCERNS.md` already documents this as active risk: `scenedetect`/`numpy` version drift can silently break the `AdaptiveDetector.post_process()` assumption the code depends on. | `uv add` with pinned/range-constrained versions + committed `uv.lock`. |
| `setup.py` / `setup.cfg` | Legacy packaging format, no longer the recommended entry point for new projects; PEP 621 (`pyproject.toml`) has fully superseded it. | `pyproject.toml` with `uv_build`. |
| `flake8` + `isort` + `black` + `pyupgrade` as separate tools | Four separate configs/dependencies/versions to keep in sync for what `ruff` does in one binary with one config block — pure maintenance overhead with no upside for a project this size. | `ruff check` + `ruff format`. |
| `ty` (Astral's type checker) as the primary type checker today | Still 0.0.x versioning, explicitly no stable API yet, breaking diagnostic changes between releases as of July 2026 per Astral's own docs. | `pyright` (or `mypy`) now; revisit `ty` after its 1.0 stable release. |
| Mocking `qsvencc`/`ffmpeg` calls with hand-rolled `sys.argv`/subprocess monkeypatching sprinkled per-test | Duplicated, inconsistent fake-process logic across test files; easy to miss edge cases (stderr vs stdout, non-zero exit codes) that `pytest-subprocess`'s registration API handles uniformly. | `pytest-subprocess`'s `fp` fixture, centralized in `conftest.py` fixtures per external tool (`fake_ffmpeg`, `fake_qsvencc`, `fake_mkvmerge`). |
| Gating all CI (including plain lint/unit-test PR checks) on a self-hosted GPU runner | Makes ordinary PR feedback depend on a single NAS's uptime and availability — directly contradicts having fast, reliable CI for the 95% of code that has nothing to do with actual QSV hardware interaction. | Hosted `ubuntu-latest` for lint/type-check/unit tests (with fake binaries); a clearly separate, optionally-gated hardware workflow for real encode validation. |
| 100%-coverage CI gate from day one | This codebase has legitimate hardware-only code paths (`qsvencc` invocation, `/dev/dri` access, real QSV decode) that cannot execute in CI at all — chasing 100% either forces bad mocking-for-coverage's-sake or blocks merges on unreachable lines. | Track coverage, set a realistic floor (e.g. 70-80%) on the CPU-testable subset, and explicitly mark hardware-only branches with `# pragma: no cover` plus a comment pointing at the manual/self-hosted validation path. |

## Stack Patterns by Variant

**Given the existing constraints (Python 3.12, Debian trixie devcontainer, no PyPI publishing goal):**
- Use `uv_build` (not hatchling) as the build backend — no dynamic versioning or custom build steps are needed for a local CLI tool.
- Use `uv` as *both* the devcontainer's Python dependency manager (replacing the current bare `pip install` in `post-create.sh`) *and* the CI dependency manager — one tool, one lockfile, one source of truth across dev and CI. This directly fixes the `CONCERNS.md` "no packaging, dependency pinning" finding.

**For subprocess-heavy CLI code with hardware dependencies:**
- Split tests into two tiers via pytest markers: `@pytest.mark.unit` (pure logic — `fmt_seek`, `kf_before`, EBML parsing, scene-log parsing — no subprocess at all) and `@pytest.mark.subprocess` (uses `pytest-subprocess` to fake ffmpeg/qsvencc/mkvmerge argv/output without touching hardware). Neither tier needs a GPU or the real binaries, so both run identically in CI and locally.
- Reserve an explicit `@pytest.mark.hardware` tier (skipped by default via `pytest.ini`'s default marker deselection, or `pytest.mark.skipif(not qsv_available(), reason=...)`) for tests that require real `/dev/dri` + `qsvencc` + actual media — these run only on a self-hosted runner or manually on the NAS, never in the default `ubuntu-latest` CI job.
- For the "mandatory regression test" already required by the project (`detect_scenes_streaming(f) == detect_scenes(f, jobs=1)` and the parallel-vs-sequential detection equivalence check in `PROJECT.md`'s Active requirements): this needs a real (or realistic small synthetic) video fixture. Keep such fixtures tiny (a few seconds, low resolution) and committed via Git LFS or generated on-the-fly with `ffmpeg -f lavfi` synthetic test patterns so the regression test *can* run in plain CI without QSV hardware (software decode is fine for correctness-of-logic checks; only the *encode* step strictly needs QSV).

**For CI structure specifically:**
- One workflow, one job matrix entry (single Python 3.12 target — no need for a version matrix since the devcontainer pins exactly one Python/OS combination and that's the only supported target): `uv sync --locked` → `ruff check` → `ruff format --check` → `pyright` → `pytest -m "not hardware"` → coverage report.
- Install real `ffmpeg`/`ffprobe`/`mkvmerge` via `apt-get` in the CI job (they're software-only, no GPU needed, and Debian/Ubuntu package them) so that any integration test wanting a *real* (non-QSV) ffmpeg/mkvmerge invocation still can run in CI — only `qsvencc` genuinely requires hardware and should be the sole thing gated behind the hardware-only marker.
- Keep the hardware-gated workflow (if built at all) as a separate `.github/workflows/hardware-integration.yml`, triggered on manual `workflow_dispatch` or a schedule, not on every PR push.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `uv` ≥0.11 | Python 3.12 (devcontainer's pinned version) | `uv` manages/downloads its own Python interpreters if needed, but should be told to use the devcontainer's existing 3.12 (`uv python pin 3.12`) to avoid a second interpreter install inside the container. |
| `uv_build` ≥0.11,<0.12 | `uv` ≥0.11 | Pin the build-backend requirement range in `pyproject.toml`'s `[build-system]` to avoid an unrelated `uv_build` major bump silently changing build behavior — same discipline `CONCERNS.md` recommends for `qsvencc`/`dovi_tool` release pinning. |
| `pytest-subprocess` | `pytest` ≥7 | No known conflicts with pytest 9.x; actively maintained against current pytest releases. |
| `pyright` | VS Code Pylance | Since the project already standardizes on VS Code devcontainers, Pyright gives free editor integration via Pylance (which embeds Pyright) with zero extra config, reinforcing the recommendation. |
| `ruff format` | Existing code style | No existing style/formatter config to migrate away from (repo currently has none) — adopting `ruff format` from a blank slate avoids any black-vs-ruff-format reformatting churn debate. |

## Sources

- [uv Projects Guide](https://docs.astral.sh/uv/guides/projects/) — project/lockfile workflow, HIGH confidence
- [uv Build Backend docs](https://docs.astral.sh/uv/concepts/build-backend/) — `uv_build` stability and config, HIGH confidence
- PyPI `uv` project page — version 0.11.28, released 2026-07-07, HIGH confidence (fetched directly)
- PyPI `ruff` project page — version 0.15.20, released 2026-06-25, HIGH confidence (fetched directly)
- PyPI `pytest` project page — version 9.1.1, released 2026-06-19, HIGH confidence (fetched directly)
- [astral-sh/setup-uv GitHub Action](https://github.com/astral-sh/setup-uv) — CI integration pattern, MEDIUM confidence (community docs + official repo)
- [Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/) — official CI guide, HIGH confidence
- [pytest-subprocess docs](https://pytest-subprocess.readthedocs.io/) — subprocess faking API, HIGH confidence (official docs)
- [Simon Willison's pytest-subprocess TIL](https://til.simonwillison.net/pytest/pytest-subprocess) — real-world usage pattern, MEDIUM confidence
- [pyright vs mypy comparison, microsoft/pyright](https://github.com/microsoft/pyright/blob/main/docs/mypy-comparison.md) — official but vendor-authored, MEDIUM confidence (cross-checked against third-party 2026 comparison articles)
- [Astral `ty` GitHub releases](https://github.com/astral-sh/ty/releases) — confirms 0.0.x/beta status as of 2026-07-01, HIGH confidence
- [pytest.mark.skipif docs](https://docs.pytest.org/en/stable/how-to/skipping.html) — official pytest docs, HIGH confidence
- [devcontainers/ci GitHub Action](https://github.com/devcontainers/ci) — optional devcontainer-in-CI pattern, MEDIUM confidence
- Coverage.py docs (coverage.readthedocs.io) — version 7.15.0, MEDIUM confidence (search-result derived, not directly fetched)
- General GPU/self-hosted-runner CI pattern articles (devactivity.com, packagemain.tech, betatim.github.io) — MEDIUM/LOW confidence, corroborating pattern across multiple independent sources but no single authoritative source for "the" standard GPU CI pattern

---
*Stack research for: Python CLI packaging/testing/CI for subprocess-heavy media transcode tool*
*Researched: 2026-07-08*
