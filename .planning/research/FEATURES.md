# Feature Research

**Domain:** Productionization of an existing scene-aware AV1 transcode CLI (Python 3.12, Intel Arc QSV) — engineering maturity deliverables, not new transcode capabilities
**Researched:** 2026-07-08
**Confidence:** MEDIUM-HIGH (general Python packaging/testing practice is HIGH confidence and well-established; specifics of what applies to *this* codebase are grounded directly in `.planning/codebase/ARCHITECTURE.md`, `CONVENTIONS.md`, `TESTING.md`, and `PROJECT.md`, which is as authoritative a source as exists for this project)

**Framing note:** In a normal ecosystem-research context, "features" means user-facing capabilities. This milestone is explicitly the opposite: the transcode features already work and are frozen (per `PROJECT.md` "Out of Scope" — no algorithm rewrites, no new capabilities). The tables below therefore categorize **engineering deliverables** — the things that turn "two scripts a human runs by hand" into "a production-grade CLI tool" — using the same table-stakes / differentiator / anti-feature lens.

## Feature Landscape

### Table Stakes (Required for "Production-Grade")

These are non-negotiable per `PROJECT.md`'s Active requirements and the debt explicitly documented in `ARCHITECTURE.md`/`TESTING.md`. Skipping any of these means the milestone has not actually productionized the tool.

| Deliverable | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Installable package + unified entry point | Two standalone `argparse` scripts connected only by a text-file handoff is not a CLI tool; `PROJECT.md` Active explicitly requires "a proper installable module structure with a shared library layer and a unified entry point." | MEDIUM | Move `legacy/scene_detection.py` + `legacy/encode_scenes.py` into a `src/`-layout package (`src/enpipe/detection.py`, `encoding.py`, `cli.py`, ...) with `pyproject.toml` `[project.scripts]` giving one `enpipe` command (`enpipe detect`, `enpipe encode`, or equivalent subcommands). Must preserve the existing two-stage `<video>.scenes` file handoff as a supported mode — do not force fusion into one command (that's the streaming orchestrator, explicitly out of scope). |
| Pinned/locked dependencies | Deps (`scenedetect[opencv-headless]`, `numpy`) are installed via unpinned ad hoc `pip install` in `post-create.sh`; a transitive PySceneDetect bump can silently change scene-cut output with zero warning. | LOW-MEDIUM | `pyproject.toml` `[project.dependencies]` + a lockfile (see STACK.md for tool choice); `post-create.sh` should install from the lockfile instead of `pip install "scenedetect[opencv-headless]" numpy`. |
| Unit tests for pure-logic functions | These functions have zero subprocess/GPU dependency and are testable **today with no refactor** — `TESTING.md` names them explicitly as the highest-value, currently-zero-coverage targets: `kf_before`, `fmt_seek`, `_min_scene_len`, `_sanitize_boundaries`, `parse_metrics`, `write_metrics_csv`, `read_scenes`, `_ebml_num`/`_eid`/`_esz`. | MEDIUM | ~10-15 functions; no media fixtures needed, only synthetic tuples/byte strings. This is the cheapest, highest-ROI testing work and should be first. |
| Subprocess-boundary tests (mocking) | Functions that shell out — `probe_source`, `detect_hdr`, `chunk_command`, `encode_chunk`, `encode_audio`, `keyframe_table_ffprobe` — have no dependency-injection seam and zero coverage today (`TESTING.md`). | MEDIUM-HIGH | Patch at the `subprocess.run`/`Popen` boundary (stdlib `unittest.mock.patch` or `pytest-subprocess`); assert exact argv construction (flags, seek/trim math, HDR flag selection) and error-path behavior (`die()` vs. `SceneDetectionError`), not real media output. This validates command-building logic without needing hardware. |
| Mandatory regression test: parallel detection == sequential detection | `PIPELINE_DESIGN.md` marks this `(обязателен)` — mandatory — and `ARCHITECTURE.md` independently calls it out as the prerequisite before trusting `detect_scenes_parallel` in an automated pipeline. `PROJECT.md` Active lists it verbatim. | MEDIUM | Assert `[(s.start_frame, s.end_frame) for s in detect_scenes_parallel(f, jobs=N)] == [(s.start_frame, s.end_frame) for s in detect_scenes(f, jobs=1)]` on a real or fixture clip. **Can run with `--no-qsv` (software decode fallback), so it does NOT require Arc GPU hardware** — this should run in ordinary CI, not gated behind the hardware runner. Distinct from, and cheaper than, the full hardware-gated integration test below. |
| Hardware-gated integration test against real media | `scene_detection.py`'s own docstring admits it has never run against real video; the `qsvencc` encode path (the actual correctness-critical GPU work) has zero automated verification anywhere. | HIGH | Full detect → encode → mux pipeline against a real (or checked-in small) sample, asserting the existing invariants: per-chunk and total frame-count match, keyframe alignment, DV RPU survives concatenation where applicable. Requires a self-hosted runner with Arc GPU + `qsvencc`, or a `pytest.mark.hardware` marker excluded from default CI and run manually/on the devcontainer host. This is the single highest-cost, highest-value deliverable — it is the only thing that actually validates the "never run on real media" gap. |
| Isolate the hand-rolled EBML/Cues parser behind a tested module boundary | `ARCHITECTURE.md` names this the top anti-pattern: 130+ lines of manual byte-offset arithmetic embedded in the orchestration script, untested, with a "silently returns a wrong-but-parseable table" failure mode the ffprobe fallback only catches for *detected* anomalies. `PROJECT.md` Active requires it explicitly. | MEDIUM | Move `_ebml_num`/`_eid`/`_esz`/`keyframe_table_cues` into their own module. Enables golden-file fixture testing (see Differentiators) with a small corpus of real mkv Cues byte fixtures — not full videos, just the relevant header bytes. |
| CI pipeline | Zero CI exists today (`TESTING.md`: no `.github/workflows/`, no test runner config anywhere). Tests that no one runs automatically are not production-grade. | MEDIUM | Runs lint + unit tests + subprocess-mocked tests + the software-fallback regression test on every push, using the pinned lockfile. The hardware-gated test is explicitly **excluded** from the default hosted-runner matrix (no GPU available there) — separate job/marker, run on a self-hosted runner or manually. |
| Regression-test the existing runtime invariant checks in isolation | Frame-count verification and keyframe-alignment guards (`count_frames`, `total_expect` arithmetic, `flush_appends()` high-water-mark ordering, `kf_before` binary search) are the *actual* correctness mechanism today per `TESTING.md`'s "de facto verification strategy." Productionizing must not weaken them while adding proper tests around them. | LOW | Mostly folds into the pure-logic unit test item above — the deliverable is turning inline `die()` assertions into isolated, independently-testable functions with unit tests, not rewriting the invariants themselves. |
| Resolve or explicitly document the ThreadPool-vs-ProcessPool inconsistency | `PROJECT.md` Active requirement; `ARCHITECTURE.md` documents a latent mismatch: worker functions in `detect_scenes_parallel` are structured process-pool-compatible (no closures) per a comment saying real parallelism needs processes, but the code actually uses `ThreadPoolExecutor` for both boundary-finding and segment workers. | LOW-MEDIUM | Either switch to `ProcessPoolExecutor` (behavior-changing — do this *before* finalizing the mandatory regression test's expected baseline, see Dependencies) or fix the stale comment to match reality and document why threads are acceptable here. Do not leave the contradiction in place. |
| Remove orphaned/vestigial references | `PROJECT.md` Active requirement; `dovi_tool` is installed in the devcontainer but unused by any script. | LOW | Small cleanup; verify nothing depends on it before removing, or add a one-line comment explaining why it's kept for future use. |

### Differentiators (Quality Investments Beyond the Minimum)

Not required by `PROJECT.md`, but each directly strengthens the table-stakes deliverables above and is low-risk to add during the same milestone.

| Deliverable | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Replace `print`-based `log()`/`step()` with stdlib `logging` | Adds real log levels (DEBUG/INFO/WARNING), optional log-to-file for unattended NAS runs, `--verbose`/`--quiet` flags — while keeping the existing human-readable, elapsed-time-prefixed, unbuffered output style. Also gives `scene_detection.py` a logging story it currently lacks entirely (only `encode_scenes.py` has `log()`/`step()`). | LOW-MEDIUM | Not the same as a full observability stack (see Anti-Features) — stdlib `logging` with a custom formatter can reproduce the exact current `[{elapsed:8.1f}s] {msg}` format. |
| Typed config layer (single Settings object layering CLI args > env vars > defaults) | Replaces "env vars read as module-global constants at import time" with something introspectable and unit-testable, reducing risk of a typo'd env var silently no-op'ing. Documents the full tunable surface in one place. | MEDIUM | Must preserve exact existing env var names (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY`) and argparse flag names for backward compatibility with any external shell scripts already calling these tools. `CONVENTIONS.md` explicitly accepts the current dual convention (explicit config object in the detector, env-derived globals in the encoder) as intentional — this deliverable formalizes it, it does not have to unify the two files into one config style. |
| Golden-file fixture tests for the EBML/Cues parser | Catches "wrong but parseable" silent corruption — the actual risk `ARCHITECTURE.md` flags, not just crashes. | MEDIUM | Depends on the table-stakes EBML isolation deliverable existing first. Small corpus of real mkv Cues byte fixtures covering normal, multi-SeekHead, and malformed-structure cases. |
| Static typing enforcement (mypy or pyright) in CI | Type hints exist throughout but are "documentation-grade, never checked" (`CONVENTIONS.md`). Given the `typing.List`/`Optional`/`Union` style used consistently, promoting to enforced is low-friction and will surface real latent bugs. | MEDIUM | Expect some initial cleanup churn; start in permissive mode and tighten. |
| Linting/formatting via `ruff` (+ pre-commit hooks) | Fast, locks in the existing manual style without fighting it (88-100 col soft wrap, Russian-language banner comments are just comments to a linter) and catches dead-code/unused-import issues (e.g. would have flagged the orphaned `dovi_tool` reference). | LOW | Natural companion to the mypy deliverable; both plug into the same CI job. |
| Coverage reporting (`pytest-cov`) with a directional target, not 100% | Visibility into which invariant-bearing code paths remain untested, without chasing coverage of `main()` CLI glue that has no independent risk. | LOW | Pair with a threshold on the specific modules (pure-logic helpers, EBML parser) rather than the whole repo. |
| Property-based tests (Hypothesis) for numeric edge functions | `kf_before` (binary search), `fmt_seek` (ms rounding), `_min_scene_len` are exactly the "non-obvious numeric/ordering logic" `TESTING.md` flags as highest-value/lowest-coverage; example-based tests alone tend to miss boundary cases in binary search and rounding. | MEDIUM | Optional beyond the table-stakes example-based unit tests, but well-suited to this specific class of function. |
| CI/devcontainer parity (CI job runs inside the same pinned base image as `.devcontainer/Dockerfile`) | Eliminates "works in devcontainer, fails in CI" drift, especially given `qsvencc` requires glibc ≥ 2.39 (Debian 13 trixie specifically). | MEDIUM | Applies to the non-hardware CI jobs (unit/mocked tests); the hardware-gated job runs on the actual devcontainer/host by definition. |
| Dependency-update automation (Renovate/Dependabot) against the new lockfile | Prevents the "unpinned deps drift silently" problem from simply recurring six months after the lockfile lands. | LOW | Depends on the table-stakes pinned-dependency deliverable existing first — nothing to automate updates against otherwise. |
| Developer convenience tooling (`Makefile`/`justfile` with `test`, `lint`, `fmt`, `hardware-test` targets) | Lowers friction for a single/small-team NAS tool where there's no larger platform team enforcing conventions. | LOW | Purely optional ergonomics; zero risk. |

### Anti-Features (Deliberately Do NOT Build)

Each of these is a plausible-sounding "while we're productionizing, let's also..." instinct that either violates `PROJECT.md`'s explicit Out of Scope boundaries or is disproportionate effort/risk for a single-operator local/NAS CLI tool.

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Streaming/pipelined orchestrator (in-process `queue.Queue` producer/consumer) | "We're touching this code anyway, let's finish the design doc's proposal" | `PROJECT.md` Out of Scope, verbatim: `PIPELINE_DESIGN.md`'s own verdict is "do not build" on current spinning-disk ZFS + Arc A380 hardware — Amdahl ceiling ~10-18%, erased by disk seek contention. | Keep sequential `detect jobs=4 → encode jobs=4`; revisit only if source storage moves to SSD/NVMe. |
| Rewriting core detect/encode/seek-trim algorithms "while in there" | Refactoring naturally invites "and let's clean up the logic too" | `PROJECT.md` Out of Scope: keyframe-alignment and DV RPU-survives-`cat` are load-bearing correctness-by-construction invariants; re-deriving them risks silent output corruption, which `PROJECT.md` names as the primary risk of this whole milestone. | Productionization work is refactor-preserving only, verified by the regression/integration tests. Any algorithm change is a separate, future, deliberately-scoped milestone. |
| Swapping the hand-rolled EBML parser for a third-party MKV/Matroska library | "Stop hand-rolling binary parsing" is a reasonable-sounding first instinct | Introduces a new dependency with its own compatibility surface and risks silently changing the exact fallback-on-anomaly semantics the code currently relies on (`keyframe_table_ffprobe` fallback). Not requested — `PROJECT.md` Active asks to isolate + test the existing parser, not replace it. | Isolate + test as-is (table stakes). Reconsider a library swap only if the parser proves an ongoing maintenance burden after real usage data. |
| Full observability stack (structured JSON logs, metrics/tracing export, log shipping) | "Production-grade" often triggers a reflexive reach for OpenTelemetry/ELK-style tooling | This is a local/NAS batch CLI with no persistent process and no multi-user/service concern — `PROJECT.md` Out of Scope explicitly excludes "any network service, auth, or multi-user layer." An observability stack has no consumer. | stdlib `logging` with levels + optional file output (see Differentiators) is sufficient. |
| Async/asyncio rewrite of subprocess orchestration | "Modernize" concurrency while touching the encode loop | `ThreadPoolExecutor` is already correct for this workload — GIL is not the bottleneck, subprocess wall time is (`ARCHITECTURE.md`'s own analysis). An asyncio rewrite is exactly the kind of algorithm rewrite `PROJECT.md` excludes, with high regression risk to the ordered "high-water mark" append logic. | Keep `ThreadPoolExecutor`; only fix the flagged ThreadPool-vs-ProcessPool naming/comment inconsistency (table stakes). |
| Mocking `qsvencc`/GPU entirely so "everything passes in CI without hardware" | Wanting 100% CI coverage without provisioning a GPU runner | Gives false confidence exactly where `PROJECT.md` says correctness is non-negotiable (bit-exact chunk output, HDR/DV metadata survival) — a mocked `qsvencc` test cannot catch a real seek/keyframe-alignment regression, which is the actual risk. | Accept that the hardware-gated integration test genuinely requires real Arc hardware and lives outside the default hosted-CI matrix. Mock only at the subprocess-argv-construction boundary (table stakes item), never claim that substitutes for real validation. |
| Public PyPI packaging / SemVer-guaranteed public release process | "Installable package" sounds like it implies publishing | `PROJECT.md`: this is explicitly a local/NAS toolchain, not a distributed product. PyPI publishing, changelog automation, and public compatibility guarantees are effort spent on an audience that doesn't exist. | `pip install -e .` (or equivalent) from the repo path is the only installation target that matters. |
| Config-file-driven multi-profile system (YAML/TOML presets, config discovery/merge hierarchy) | "Config handling" naturally suggests a fuller config system beyond env vars + argparse | Not in `PROJECT.md` Active scope; adds a new file format, validation, and precedence surface for a tool with roughly ten tunables that already have a working (if inelegant) env-var convention. | The typed Settings layer (differentiator) formalizes but does not replace the existing env-var/argparse split. |
| 100%-coverage mandate / exhaustive testing of every `main()` CLI glue line | "We're finally adding tests, let's cover everything" | `main()` orchestration functions are intentionally long linear glue (per `CONVENTIONS.md`); real risk is concentrated in the numeric/ordering helper functions, not argparse wiring and print statements. Chasing glue coverage competes for time with the hardware integration test, which is the actually load-bearing deliverable. | Prioritize invariant-bearing pure functions and the mandated regression test; treat incidental CLI-glue coverage as a byproduct of the hardware integration test, not a target. |

## Feature Dependencies

```
Installable package + unified entry point (table stakes)
    ├──enables──> Pinned/locked dependencies (same pyproject.toml)
    ├──requires──> EBML parser isolation (needs a module to move it into)
    ├──requires──> Unit tests, pure-logic (needs stable import paths)
    ├──requires──> Subprocess-boundary tests (needs stable import paths)
    ├──requires──> CI pipeline (needs an installable, importable target)
    └──enhances──> Typed config layer, Logging upgrade (natural home during reorg)

EBML parser isolation (table stakes)
    └──requires──> Golden-file fixture tests for EBML parser (differentiator)

Unit tests (pure-logic + subprocess-mocked)
    └──requires──> CI pipeline (nothing to run automatically otherwise)

Resolve ThreadPool-vs-ProcessPool inconsistency
    └──must-precede──> Mandatory parallel==sequential regression test
        (if the executor changes, the parallel path's output may change;
         fix the executor first, THEN capture the regression baseline —
         otherwise the "mandatory" test locks in behavior that's about to change)

Mandatory parallel==sequential regression test (table stakes, software-fallback only)
    ≠ Hardware-gated integration test (table stakes, real GPU only)
    — these are NOT the same deliverable and do not block each other;
      the regression test runs in ordinary CI, the hardware test does not.

Pinned/locked dependencies (table stakes)
    └──requires──> Dependency-update automation (differentiator)
                       (nothing to automate updates against without a lockfile)

CI pipeline (table stakes)
    └──excludes by design──> Hardware-gated integration test
        (no GPU on default hosted runners; separate self-hosted/manual job)
```

### Dependency Notes

- **Package restructure is the true first deliverable.** Nearly everything else (dependency pinning, both classes of unit tests, EBML isolation, CI) either directly requires it or is far cheaper once it exists. Sequencing anything else first risks doing throwaway work against the current flat `legacy/` scripts.
- **The ThreadPool/ProcessPool fix must land before the mandatory regression test is finalized**, not after. If `detect_scenes_parallel`'s executor changes from thread- to process-based, its output could change (even if it shouldn't, per the "designed to be process-pool-compatible" comment) — capturing the parallel==sequential baseline before that fix risks needing to immediately re-baseline it.
- **The mandatory regression test and the hardware-gated integration test are easy to conflate but are different deliverables with different costs.** The regression test can run with `--no-qsv` (software decode) and belongs in ordinary CI. The hardware-gated test requires real Arc GPU + `qsvencc` and cannot run on default hosted CI runners at all. Treat them as two separate line items in the roadmap, not one.
- **EBML isolation unlocks, but does not require, golden-file fixture testing.** The isolation itself (moving code into a tested module) is table stakes; building out a fixture corpus of real mkv byte sequences is the differentiator layer on top.
- **Dependency-update automation is inert without the lockfile.** Don't schedule it before pinning lands.

## MVP Definition — Adapted to a Productionization Milestone

There is no "launch" in the product sense; the equivalent framing is "what must ship for this milestone to satisfy `PROJECT.md`'s Active requirements," vs. what strengthens the result further, vs. what should be explicitly deferred.

### Required This Milestone (satisfies PROJECT.md Active)

- [ ] Installable package + unified entry point — the structural prerequisite for nearly everything else
- [ ] Pinned/locked dependencies (manifest + lockfile), replacing ad hoc `pip install`
- [ ] Unit tests for pure-logic functions (no subprocess/GPU dependency)
- [ ] Subprocess-boundary tests (mocked) for the ffmpeg/ffprobe/qsvencc/mkvmerge call sites
- [ ] Mandatory regression test: parallel detection == sequential detection by `(start_frame, end_frame)` pairs
- [ ] Hardware-gated integration test against real media (the never-run-on-real-video gap)
- [ ] EBML/Cues parser isolated behind a tested module boundary
- [ ] CI established (lint + unit/mocked tests + software-fallback regression test on every push)
- [ ] ThreadPool-vs-ProcessPool inconsistency resolved or explicitly documented
- [ ] Orphaned references (`dovi_tool`) removed or justified

### Add If Time Allows Within the Milestone (strengthens the above, low risk)

- [ ] stdlib `logging` replacing `print`-based `log()`/`step()`, extended to `scene_detection.py`
- [ ] Typed config layer over the existing env-var/argparse convention (names preserved)
- [ ] `ruff` linting + `mypy`/`pyright` type checking wired into CI
- [ ] Golden-file fixture tests for the isolated EBML parser

### Explicitly Deferred (not this milestone, possibly never)

- [ ] Streaming/pipelined orchestrator — deferred pending SSD/NVMe storage migration, per `PIPELINE_DESIGN.md` verdict
- [ ] Any algorithm/seek-trim-math rewrite — out of scope by design, correctness invariants are load-bearing
- [ ] Alternative/non-QSV encoder path — explicitly not a goal
- [ ] Any network service, auth, or multi-user layer — explicitly not a goal
- [ ] Full observability stack, async rewrite, public PyPI release, config-file-preset system — see Anti-Features

## Feature Prioritization Matrix

| Deliverable | Engineering Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Installable package + entry point | HIGH | MEDIUM | P1 |
| Pinned/locked dependencies | HIGH | LOW-MEDIUM | P1 |
| Unit tests, pure-logic functions | HIGH | MEDIUM | P1 |
| Subprocess-boundary tests (mocked) | HIGH | MEDIUM-HIGH | P1 |
| Mandatory parallel==sequential regression test | HIGH | MEDIUM | P1 |
| Hardware-gated integration test | HIGH | HIGH | P1 |
| EBML parser isolation | HIGH | MEDIUM | P1 |
| CI pipeline | HIGH | MEDIUM | P1 |
| Resolve ThreadPool/ProcessPool inconsistency | MEDIUM | LOW-MEDIUM | P1 |
| Remove orphaned references | LOW | LOW | P1 |
| Logging upgrade (stdlib `logging`) | MEDIUM | LOW-MEDIUM | P2 |
| Typed config layer | MEDIUM | MEDIUM | P2 |
| `ruff` + `mypy`/`pyright` in CI | MEDIUM | LOW-MEDIUM | P2 |
| Golden-file EBML fixture tests | MEDIUM | MEDIUM | P2 |
| Coverage reporting | LOW | LOW | P3 |
| Property-based tests (Hypothesis) | LOW-MEDIUM | MEDIUM | P3 |
| CI/devcontainer image parity | MEDIUM | MEDIUM | P3 |
| Dependency-update automation | LOW | LOW | P3 |
| Developer convenience tooling (Makefile/justfile) | LOW | LOW | P3 |

**Priority key:**
- P1: Required this milestone — directly satisfies a `PROJECT.md` Active requirement
- P2: Should have, meaningfully strengthens a P1 deliverable, low risk to include
- P3: Nice to have, defer without regret if the milestone is time-constrained

## Reference Practices from Comparable Tools

No direct "competitors" exist for a local/NAS-only encoding CLI, so this section substitutes general patterns from comparable single-operator Python CLI tools that wrap external binaries (ffmpeg, media tools) and gate hardware/network-dependent tests, as grounding rather than direct comparison.

| Practice | How Comparable Tools Handle It | Our Approach |
|---------|--------------|--------------|
| Gating tests that need unavailable resources (network, hardware, external services) | Standard pytest pattern: custom `pytest.mark` (e.g. `@pytest.mark.hardware`) combined with `pytest.ini`/`pyproject.toml` marker registration and either `-m "not hardware"` as the default CI invocation or a `skipif` keyed off an environment variable/device check (HIGH confidence — this is documented pytest behavior, not project-specific: https://docs.pytest.org/en/stable/how-to/skipping.html) | Register a `hardware` marker; default CI command excludes it (`pytest -m "not hardware"`); a separate self-hosted-runner or manual job runs `pytest -m hardware` on the Arc devcontainer host |
| Mocking subprocess-heavy CLI wrappers (ffmpeg-style tools) | Libraries like `pytest-subprocess` (hooks `subprocess.Popen` so `run`/`call`/`check_output` all work) or plain `unittest.mock.patch("subprocess.run")` are the two dominant approaches in the Python ecosystem for this exact shape of problem (MEDIUM confidence, WebSearch-verified via PyPI/community sources: https://pypi.org/project/pytest-subprocess/, https://til.simonwillison.net/pytest/pytest-subprocess) | Either is viable for this codebase's `subprocess.run`/`Popen` call sites; final tool choice belongs in STACK.md, not here — the deliverable (subprocess-boundary tests) is table stakes regardless of which mocking library backs it |
| Packaging small internal/local CLI tools | `pyproject.toml`-based builds with `[project.scripts]` entry points and a lockfile are now the default expectation for any actively maintained Python CLI project, whether or not it is ever published (HIGH confidence, current Python Packaging User Guide: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) | Adopt this even though `enpipe` will never be published to PyPI — the deliverable is a locally-installable package, not a public one |

## Sources

- `.planning/PROJECT.md` — Active/Out of Scope requirements (primary source of truth for this milestone's boundaries)
- `.planning/codebase/ARCHITECTURE.md` — anti-patterns (EBML parser, untested-against-real-media), ThreadPool/ProcessPool inconsistency, correctness invariants
- `.planning/codebase/CONVENTIONS.md` — existing config/logging/error-handling conventions to preserve
- `.planning/codebase/TESTING.md` — current zero-test state, the mandated regression test, de facto verification strategy, recommended test targets
- `PIPELINE_DESIGN.md` (in-repo) — streaming orchestrator verdict ("do not build"), mandatory regression test specification
- [Writing your pyproject.toml — Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) (HIGH confidence, official docs)
- [pytest-subprocess · PyPI](https://pypi.org/project/pytest-subprocess/) (MEDIUM confidence, WebSearch-verified)
- [Mocking subprocess with pytest-subprocess — Simon Willison TILs](https://til.simonwillison.net/pytest/pytest-subprocess) (MEDIUM confidence)
- [pytest: How to use skip and xfail](https://docs.pytest.org/en/stable/how-to/skipping.html) (HIGH confidence, official docs)
- [GitHub Actions self-hosted runners — GitHub Docs](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners) (HIGH confidence, official docs)
- [GitHub Actions GPU Testing: Self-Hosted Solutions](https://devactivity.com/insights/testing-gpu-code-on-github-actions-overcoming-performance-hurdles-with-self-hosted-runners/) (MEDIUM confidence, WebSearch-verified pattern)
- Best Python Package Managers in 2026 (uv/Poetry/pip landscape) — MEDIUM confidence, multiple WebSearch sources agree uv has become the default for new application projects while Poetry remains common for library publishing; detailed tool recommendation deferred to STACK.md

---
*Feature research for: productionization of an existing Python 3.12 AV1 transcode CLI*
*Researched: 2026-07-08*
