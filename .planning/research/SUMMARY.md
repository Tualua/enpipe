# Project Research Summary

**Project:** enpipe
**Domain:** Productionization of an existing, working-but-unverified scene-aware AV1 transcode CLI (Python 3.12, subprocess-orchestration, Intel Arc QSV hardware-coupled)
**Researched:** 2026-07-08
**Confidence:** HIGH

## Executive Summary

`enpipe` is not a greenfield build — it is two working, unpackaged, untested `argparse` scripts (`legacy/scene_detection.py`, `legacy/encode_scenes.py`) that have never been run against real media, connected only by a free-text `<video>.scenes` intermediate file. This milestone is explicitly engineering maturity — packaging, pinned dependencies, tests, CI, and targeted tech-debt cleanup — not new transcode features and not the streaming orchestrator sketched in `PIPELINE_DESIGN.md` (which its own Amdahl analysis says not to build on current spinning-disk hardware). All four research tracks (stack, features, architecture, pitfalls) converge independently on the same conclusion: **the correctness invariants in this code (keyframe-aligned seek/trim math, DV RPU survival through concatenation, frame-count guards) are "correct by construction" and currently unverified — the entire milestone's risk surface is in making that correctness checkable before anyone refactors around it, not in the refactor itself.**

The recommended approach is `uv` + `pyproject.toml` + `src/`-layout package with a `shared.proc` subprocess seam, `ruff`/`pyright` for lint/types, and a strict two-tier test strategy: fast mocked-subprocess unit tests (pure logic + argv construction, no hardware) gating every PR, and a separate hardware-gated golden-sample tier (real qsvencc/Arc GPU, real media covering SDR/HDR10/HDR10+/DV/VFR) that gates releases but never blocks ordinary CI. The single most load-bearing sequencing constraint across all four documents is: **package/restructure first (it is the prerequisite for nearly everything else), pin dependencies alongside it, then build the fast test tier, THEN touch anything correctness-sensitive** — the EBML parser isolation and the ThreadPool/ProcessPool fix must happen with tests wrapped around them, not before. The mandatory parallel==sequential regression test and the hardware-gated real-media validation are two distinct, differently-costed deliverables that must not be conflated.

Key risks, all converging in PITFALLS.md and echoed in FEATURES.md's anti-features: (1) a "cleanup" refactor of the seek/trim arithmetic silently shifting frame boundaries with no error anywhere in the chain; (2) a mocked-subprocess-only test suite creating false confidence while the actual QSV/EBML/RPU bug classes go completely unexercised; (3) green CI being mistaken for hardware-validated when GPU paths structurally cannot run on hosted runners; (4) unpinned `qsvencc`/`dovi_tool`/`scenedetect` drifting silently on every container rebuild; and (5) Dolby Vision RPU frame-count desync surviving chunk splice/mux undetected because the only existing guard checks aggregate video frame count, not RPU-per-frame fidelity. Mitigation is consistent across all four docs: build the safety net (tests + pinning) before refactoring correctness-critical code, keep the two test tiers explicitly separate in CI status/naming, and never let a green mocked-only suite substitute for real-media validation in release criteria.

## Key Findings

### Recommended Stack

`uv` (≥0.11) as the single project/dependency/lockfile manager, paired with `uv_build` as the PEP 621 build backend and `pyproject.toml` as the sole manifest — this directly retires the currently-unpinned `pip install` in `post-create.sh`, the single most-cited concrete risk in PITFALLS.md and FEATURES.md alike. `pytest` (≥9.1) is the test framework, with `pytest-subprocess` as the primary subprocess-faking library (hooks `Popen` itself, so it exercises the real call surface rather than a hand-asserted call signature) and plain `unittest.mock.patch`/`monkeypatch` reserved for one-off mocks. `ruff` (≥0.15) replaces the currently-nonexistent lint/format tooling in one binary/config block; `pyright` is the recommended type checker for this specific codebase (unannotated-by-default checking suits `legacy/*.py`'s currently-unenforced type hints) over `mypy`, though the choice is a soft recommendation. `hypothesis` is recommended (not mandatory) for property-testing the fragile numeric functions (`kf_before`, `fmt_seek`). CI runs on hosted `ubuntu-latest` for lint/type-check/mocked-subprocess tests only; a separate, manually-triggered or scheduled workflow (never gating ordinary PRs, never open to fork PRs) covers the hardware-gated tier on a self-hosted Arc-equipped runner.

**Core technologies:**
- `uv` + `uv_build`: dependency/lockfile/build management — single tool, single lockfile, fixes the unpinned-deps risk CONCERNS.md flags as active
- `pytest` + `pytest-subprocess`: test framework and subprocess-faking, matched to this codebase's actual call surface (`subprocess.run`/`Popen`)
- `ruff` + `pyright`: lint/format/type-check — zero existing config today, so adopting from a blank slate avoids any migration churn
- `hypothesis`: recommended for the exact fragile seek/trim arithmetic PITFALLS.md names as the top correctness risk

### Expected Deliverables (framed as engineering maturity, not user features)

This milestone inverts the usual "features" lens: the transcode capabilities are frozen per `PROJECT.md`, so table stakes/differentiators/anti-features apply to engineering deliverables instead.

**Must have (table stakes, satisfies PROJECT.md Active):**
- Installable package + unified CLI entry point (dispatch-only, preserving the two-stage `.scenes`-file handoff)
- Pinned/locked dependencies (manifest + lockfile), replacing ad hoc `pip install`
- Unit tests for pure-logic functions (`kf_before`, `fmt_seek`, EBML byte-parsing, scene-log parsing) — zero-refactor, testable today
- Subprocess-boundary tests (mocked) for ffmpeg/ffprobe/qsvencc/mkvmerge call sites
- Mandatory regression test: parallel detection == sequential detection (software-fallback capable, belongs in ordinary CI)
- Hardware-gated integration test against real media (the single highest-value, highest-cost deliverable — closes the "never run on real video" gap)
- EBML/Cues parser isolated behind a tested module boundary
- CI pipeline (lint + unit/mocked tests + software-fallback regression test on every push)
- ThreadPool-vs-ProcessPool inconsistency resolved or explicitly documented
- Orphaned references (`dovi_tool`) removed or justified

**Should have (strengthens the above, low risk):**
- stdlib `logging` replacing `print`-based `log()`/`step()`
- Typed config layer over the existing env-var/argparse convention (names preserved for backward compat)
- `ruff` + `pyright` wired into CI
- Golden-file fixture tests for the isolated EBML parser

**Defer / explicitly out of scope:**
- Streaming/pipelined orchestrator — deferred pending SSD/NVMe migration, per `PIPELINE_DESIGN.md`'s own "do not build" verdict
- Any algorithm/seek-trim-math rewrite — correctness invariants are load-bearing, not up for re-derivation
- Full observability stack, async rewrite, public PyPI release, config-file-preset system, non-QSV encoder path, network/multi-user layer

### Architecture Approach

Move `legacy/*.py` into a `src/enpipe/` package mirroring the existing runtime architecture exactly: `detection/` and `encoding/` remain separate, coupled only by the `<video>.scenes` text file (no direct Python import between them — this is deliberate, preserves the current two-independent-CLI-invocation workflow, and keeps this milestone from drifting into the out-of-scope fused orchestrator). Both depend on a new `shared/` library layer, whose `proc.py` is the single subprocess call-through choke point (`run()`/`popen()` wrapping `subprocess.run`/`Popen`) — this is the primary testability lever for the whole codebase, chosen over constructor/parameter injection specifically because it requires zero function-signature changes, matching the "preserve current behavior exactly" success criterion. A thin `cli/` dispatch layer (`enpipe detect` / `enpipe encode`) sits on top, added last, only after both stages are independently verified. The hand-rolled EBML/Cues parser (`mkv/ebml.py`) gets pulled out as its own top-level package with a read/parse split, since it is currently impossible to unit test without real `.mkv` binary fixtures.

**Major components:**
1. `cli/` — argparse dispatch only, no orchestration logic; reproduces exact current CLI/env-var surface for backward compatibility
2. `detection/` + `encoding/` — the two existing pipelines, mechanically split into cohesive submodules (`config`, `stream`, `detect`, `parallel` / `scenes_io`, `keyframes`, `hdr`, `chunk`, `audio`, `metrics`, `pipeline`), still coupled only by the `.scenes` file
3. `mkv/ebml.py` — isolated, byte-fixture-testable EBML/Cues parser (top structural risk named directly in PROJECT.md)
4. `shared/proc.py` — the sole subprocess seam; every `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` call routes through it, enabling mocking with zero signature churn

A defined 8-step migration order exists (scaffold → move detection → introduce the proc seam → move encoding with EBML split first → add unified CLI → dedupe probe helpers last → add the mandatory regression test → retire `legacy/` only after parity verified at every step). `legacy/` stays in place throughout as the parity oracle.

### Critical Pitfalls

1. **Refactoring silently shifts frame boundaries** — the seek/trim arithmetic is correct-by-construction and currently has zero test coverage; a "readability" refactor can land a chunk boundary off a keyframe with no error anywhere (frame-count guard still passes). Avoid by building unit tests + a per-chunk content/SSIM check *before* any refactor touches this code — treat it as a "no drive-by edits" zone.
2. **Mocked-subprocess tests create false confidence** — a fully-mocked suite goes green and looks like progress but never exercises real QSV decode, real keyframe seeks, or real EBML bytes. Avoid with an explicit two-tier suite (mocked unit tests + real-hardware golden-sample tests) where only the golden-sample tier gates releases.
3. **Green CI ≠ hardware-validated** — GPU/QSV paths structurally cannot run on hosted CI runners; teams drift toward trusting the green checkmark regardless. Avoid by visibly separating "logic-only" vs "hardware-required (not run in CI)" check names, and making manual/self-hosted NAS validation an explicit, durable release-checklist item.
4. **Unpinned toolchain drift** — `qsvencc`/`dovi_tool` fetched via `latest` and unpinned Python deps mean a routine rebuild can silently break the pipeline (renamed/removed CLI flags, changed `AdaptiveDetector.post_process()` behavior). Avoid by pinning every layer (exact release tags + lockfile) and treating every bump as a deliberate, re-tested change.
5. **DV RPU desync surviving chunk splice/mux** — the only existing guard checks aggregate video frame count, never RPU-per-frame fidelity; a DV metadata desync at a chunk boundary can ship undetected and only surface as playback glitches on DV-capable displays. Avoid by wiring the already-installed-but-unused `dovi_tool` into an explicit RPU frame-count/profile check, with at least one real DV source in the golden-sample fixture set.

(Two more pitfalls are directly relevant to sequencing: the EBML parser's broad exception handling can mask a *silently wrong* — not crashing — parse, requiring cross-validation against the trusted ffprobe fallback rather than just exception-path testing; and packaging/restructuring can silently break the free-text `.scenes` protocol or CLI/env-var surface for any existing on-disk artifacts or external automation, requiring an explicit backward-compatibility entrance criterion.)

## Implications for Roadmap

All four research documents converge, independently, on the same phase ordering. This convergence is strong signal, not coincidence: STACK.md's CI/tooling recommendations, FEATURES.md's dependency graph ("package restructure is the true first deliverable"), ARCHITECTURE.md's 8-step migration order, and PITFALLS.md's "build the safety net before refactoring correctness-critical code" all point at the same sequence.

### Phase 1: Package Scaffold + Dependency Pinning
**Rationale:** Every other deliverable (both test classes, EBML isolation, CI, subprocess seam) either directly requires an installable package with stable import paths, or is far cheaper once it exists. This is explicitly the "true first deliverable" per FEATURES.md's dependency analysis, and it is zero behavior risk (ARCHITECTURE.md step 1: nothing executes yet, just scaffolding). Pinning dependencies alongside packaging closes PITFALLS.md's Pitfall 4 (unpinned toolchain drift) as early as possible, since golden-sample tests later are only meaningful against a known, pinned toolchain.
**Delivers:** `pyproject.toml` (`uv` + `uv_build`), `src/enpipe/` skeleton package, pinned/locked Python deps (`uv.lock`), `pip install -e .` working, `import enpipe` working. `legacy/` retained as parity oracle.
**Addresses:** "Installable package + unified entry point" and "Pinned/locked dependencies" table-stakes deliverables (FEATURES.md).
**Avoids:** Pitfall 4 (unpinned toolchain drift) — pin Python deps here; note qsvencc/dovi_tool/ffmpeg pinning in the devcontainer is a related but separate concern worth flagging even if it lands in this phase or shortly after.

### Phase 2: Mechanical Migration + Subprocess Seam + Fast Test Tier
**Rationale:** ARCHITECTURE.md's migration order (steps 2-4) and PITFALLS.md's Pitfall 2 both insist the safety net (fast, hardware-free tests) must exist *before* anything correctness-sensitive is refactored. Moving `detection/` first (smaller, no dependents) de-risks the src-layout/console_script wiring before touching the more complex encoder. Introducing `shared.proc` as the sole subprocess call-through here (not per-function injection — zero signature changes, matching "preserve behavior exactly") is the single testability lever for the whole codebase.
**Delivers:** `detection/` and `encoding/` packages populated via mechanical cut/paste (no logic changes), `shared/proc.py` seam applied throughout, unit tests for pure-logic functions (`kf_before`, `fmt_seek`, scene-log parsing) and subprocess-boundary tests (mocked via `pytest-subprocess`) for ffprobe/ffmpeg/qsvencc/mkvmerge call sites. Byte-identical output verified against `legacy/*.py` at each step.
**Uses:** `pytest`, `pytest-subprocess`, `pytest-mock` (STACK.md).
**Implements:** `shared/proc.py` seam, `detection/*` and `encoding/*` module split (ARCHITECTURE.md).
**Avoids:** Pitfall 2 (mocked-only false confidence) by explicitly scoping this tier as "unit tests" only — not a substitute for the hardware-gated tier in Phase 4.

### Phase 3: EBML Parser Isolation + Correctness-Critical Extractions
**Rationale:** PROJECT.md names EBML isolation as the top tech-debt item; PITFALLS.md's Pitfall 6 and ARCHITECTURE.md's Anti-Pattern 3 both warn this must not be treated as a routine "cut into a file" step — the goal is testability, not just relocation. This phase also extracts the seek/trim math (`compute_chunk_seek_trim`) and the high-water-mark flush ordering into pure, directly-testable functions (ARCHITECTURE.md Pattern 3), directly addressing Pitfall 1 (silent frame-shift from refactoring) by making the correctness-critical arithmetic unit-testable with synthetic edge cases before anyone else touches it.
**Delivers:** `mkv/ebml.py` with a read/parse split and a byte-fixture test corpus (normal Cues, missing SeekHead, corrupt/truncated structures); cross-validation test asserting EBML-parsed keyframe table matches the trusted `keyframe_table_ffprobe` output; extracted, unit-tested `compute_chunk_seek_trim` and `contiguous_ready` pure functions.
**Addresses:** "EBML/Cues parser isolated behind a tested module boundary" (PROJECT.md Active, FEATURES.md table stakes).
**Avoids:** Pitfall 1 (silent seek/trim frame-shift) and Pitfall 6 (EBML parser returns wrong-but-parseable data) — both require the exact test corpus and cross-validation this phase builds.

### Phase 4: CI Pipeline + Unified Entry Point
**Rationale:** Both fast-tier tests (Phase 2/3) need something to run automatically (FEATURES.md: "nothing to run automatically otherwise"); the unified CLI dispatcher is explicitly lowest-risk *after* both stages are independently verified, not before (ARCHITECTURE.md step 5) — sequencing it late avoids Anti-Pattern 1 (mistaking "unified entry point" for license to start fusing the two pipelines).
**Delivers:** GitHub Actions CI (lint + unit/mocked tests + software-fallback regression test on every push, pinned `uv` action, `ubuntu-latest`, real `ffmpeg`/`mkvmerge` via `apt-get` since only `qsvencc` needs hardware); `enpipe` console_script with `detect`/`encode` subcommands, dispatch-only.
**Uses:** `astral-sh/setup-uv`, `ruff`, `pyright` (STACK.md CI Strategy).
**Avoids:** Pitfall 3 (green CI mistaken for hardware-validated) — this phase must name the CI check distinctly (e.g. "ci / cpu-fallback") so it is never confused with hardware validation.

### Phase 5: ThreadPool/ProcessPool Resolution + Orphan Cleanup
**Rationale:** FEATURES.md's dependency notes are explicit: this fix must land *before* the mandatory parallel==sequential regression test is finalized, since changing the executor type could change the parallel path's output timing/behavior — capturing the regression baseline before this fix risks needing to immediately re-baseline it. PITFALLS.md's Pitfall 5 requires measurement (profiling) before deciding direction, not a guess.
**Delivers:** Profiling-informed decision (switch to `ProcessPoolExecutor` or fix the stale comment), applied and documented; orphaned `dovi_tool` reference removed or justified.
**Addresses:** "ThreadPool-vs-ProcessPool inconsistency resolved" and "orphaned references removed" (PROJECT.md Active).
**Avoids:** Pitfall 5 (GIL trap silently regressing parallel throughput on a future decode-path change).

### Phase 6: Mandatory Regression Test + Hardware-Gated Real-Media Validation
**Rationale:** This is deliberately last and deliberately split into two sub-deliverables that FEATURES.md explicitly warns not to conflate: the mandatory parallel==sequential regression test (software-fallback capable, belongs in ordinary CI) and the full hardware-gated integration test (real Arc GPU + qsvencc, closes the "never run on real media" gap, the single highest-cost/highest-value deliverable in the whole milestone). It comes after Phase 5 because the ThreadPool/ProcessPool fix must precede baselining, and after Phases 2-4 because it needs the full test infrastructure and CI plumbing to run automatically or on a self-hosted runner.
**Delivers:** `detect_scenes_parallel(f, jobs=N) == detect_scenes(f, jobs=1)` regression test (real or synthetic footage, `--no-qsv` capable, runs in ordinary CI); hardware-gated golden-sample suite covering SDR/HDR10/HDR10+/DV/VFR sources with `dovi_tool`-based RPU frame-count/profile checks (not just `count_frames`), on a self-hosted or manually-triggered workflow, restricted to trusted branches.
**Addresses:** The two explicit PROJECT.md Active requirements this milestone exists to satisfy: "validate the existing pipeline against real media end-to-end" and "the mandatory regression test."
**Avoids:** Pitfall 2 (mocked-only false confidence), Pitfall 3 (CI/hardware conflation), and Pitfall 7 (DV RPU desync surviving undetected) — all three converge on this phase needing real hardware, real DV source material, and RPU-aware verification, not just frame-count checks.

### Phase Ordering Rationale

- **Package restructure must be first** — nearly every other deliverable directly requires stable import paths or is far cheaper once the package exists (FEATURES.md dependency graph, ARCHITECTURE.md migration order both agree).
- **Tests before refactors of correctness-critical code** — PITFALLS.md's central thesis (Pitfall 1, Pitfall 2) and ARCHITECTURE.md's explicit sequencing (build the fast tier in steps 2-4 before the EBML split in step 4a, extract pure functions with direct unit tests rather than deferring) both insist the safety net exists first.
- **EBML isolation is not "just" a move — it requires its own dedicated phase** with a fixture corpus and cross-validation against the trusted ffprobe path, per PROJECT.md's explicit "tested module boundary" language and PITFALLS.md's Pitfall 6 (silent wrong-but-parseable output, not crashes).
- **ThreadPool/ProcessPool must resolve before the regression test baseline is captured** — a direct, explicit ordering constraint from FEATURES.md's Dependency Notes, otherwise the "mandatory" test could lock in behavior about to change.
- **The two "real media" deliverables (regression test vs. hardware-gated integration test) are separate, differently-gated line items**, not one — conflating them (treating a `--no-qsv` regression pass as hardware validation) is exactly Pitfall 3.
- **The unified CLI entry point is deliberately late** — added only once both stages are independently verified, specifically to prevent "unified entry point" work from drifting into the out-of-scope fused streaming orchestrator (ARCHITECTURE.md Anti-Pattern 1).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (EBML parser isolation):** Building a real MKV Cues byte-fixture corpus (multiple muxers, malformed/truncated samples) is a domain-specific task with no off-the-shelf fixture library — may need research into constructing valid-but-edge-case EBML byte sequences by hand.
- **Phase 5 (ThreadPool/ProcessPool):** Requires actual profiling methodology (py-spy or equivalent) against this specific workload before deciding a direction — the research so far identifies the trap but not the measured answer.
- **Phase 6 (hardware-gated validation):** Self-hosted GitHub Actions runner setup with `/dev/dri` passthrough and security restriction to trusted branches is a nontrivial, security-sensitive configuration task; DV/HDR10+ source acquisition and `dovi_tool` RPU-check scripting are both underspecified beyond "do this."

Phases with standard patterns (skip research-phase):
- **Phase 1 (packaging/pinning):** `uv`/`pyproject.toml`/lockfile patterns are extremely well-documented, HIGH confidence, official-docs-verified.
- **Phase 2 (mechanical migration + subprocess seam + fast tests):** `pytest-subprocess`, `src/` layout, and the call-through-module seam pattern are all well-established with direct precedent already in the codebase (`encode_scenes.py`'s existing local `run()` wrapper).
- **Phase 4 (CI pipeline):** GitHub Actions + `astral-sh/setup-uv` + hosted-runner lint/test patterns are standard, HIGH confidence.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Packaging/lint/CI tooling verified directly against PyPI/official docs with fetched version numbers; subprocess-testing strategy is MEDIUM (no single canonical "official" source naming `pytest-subprocess` as *the* standard, though well-corroborated) |
| Features | MEDIUM-HIGH | General Python packaging/testing practice is well-established; project-specific deliverables are grounded directly in this repo's own `.planning/codebase/` docs and `PROJECT.md`, which is as authoritative as it gets for scope boundaries |
| Architecture | HIGH | Grounded directly in reading `legacy/scene_detection.py` and `legacy/encode_scenes.py` source plus current official `packaging.python.org` guidance; migration order is a direct, reasoned proposal, not sourced from an external precedent |
| Pitfalls | MEDIUM-HIGH | Domain patterns (subprocess mocking, CI/GPU gap, toolchain pinning) are well-established and cross-verified; QSVEnc-specific version-break history and DV RPU concatenation failure modes are corroborated by upstream issue trackers (Rigaya NVEnc/QSVEnc family, dovi_tool discussions) but not verified against this exact codebase's currently-pinned versions — treat as MEDIUM confidence pending the real-media validation phase itself |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact qsvencc/ffmpeg/dovi_tool version pins are not yet chosen or validated** — STACK.md and PITFALLS.md both flag this as needing a deliberate decision early (Phase 1/alongside), but the specific version numbers require validation against the actual devcontainer and real media, which only happens in Phase 6. Handle by treating Phase 1's toolchain pinning as "pin to whatever currently works, documented explicitly" rather than blocking on an as-yet-unvalidated "best" version.
- **ThreadPool-vs-ProcessPool resolution direction is genuinely unknown until profiled** — do not pre-decide in the roadmap; Phase 5 must include a profiling/measurement step as its first sub-task, with the fix direction as a consequence, not an assumption.
- **Whether `mypy` or `pyright` proves better in practice for this codebase's actual dependencies (`scenedetect`, `numpy` stub quality) is unverified** — STACK.md flags this as worth a trial; low-stakes enough to resolve during Phase 1/2 implementation rather than needing dedicated research.
- **The real-media DV/HDR10+/VFR fixture library does not yet exist** — Phase 6 needs to source or construct this; PITFALLS.md notes `dovi_tool` is already installed but unused, a strong signal the intent existed but was never executed. This is likely the single largest unknown-effort item in the whole roadmap and should be flagged explicitly during phase planning as potentially needing its own research pass (sourcing legally-usable real DV/HDR10+ sample content).
- **Self-hosted GitHub Actions runner security configuration** (restricting to trusted/maintainer-triggered runs, never fork PRs) is named as a requirement in both STACK.md and PITFALLS.md but not designed in detail — needs research or a security-focused design pass before Phase 6 wiring.

## Sources

### Primary (HIGH confidence)
- [uv Projects Guide](https://docs.astral.sh/uv/guides/projects/), [uv Build Backend docs](https://docs.astral.sh/uv/concepts/build-backend/), [Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/) — official Astral docs
- PyPI project pages for `uv`, `ruff`, `pytest` — directly fetched current version numbers (2026-07-07/06-25/06-19)
- [Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/), [src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/), [Creating and packaging command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) — official Python Packaging User Guide
- [pytest-subprocess docs](https://pytest-subprocess.readthedocs.io/), [pytest.mark.skipif docs](https://docs.pytest.org/en/stable/how-to/skipping.html) — official docs
- `legacy/scene_detection.py`, `legacy/encode_scenes.py`, `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/CONCERNS.md`, `PIPELINE_DESIGN.md` — primary in-repo sources, authoritative for this project's scope and existing behavior

### Secondary (MEDIUM confidence)
- [pyright vs mypy comparison (microsoft/pyright)](https://github.com/microsoft/pyright/blob/main/docs/mypy-comparison.md) — vendor-authored, cross-checked against third-party comparisons
- [Simon Willison's pytest-subprocess TIL](https://til.simonwillison.net/pytest/pytest-subprocess), [testfixtures MockPopen docs](https://testfixtures.readthedocs.io/en/latest/popen.html) — community-verified subprocess-mocking patterns
- [FFmpeg Test Automation: Turning Guesswork into Facts](https://hoop.dev/blog/ffmpeg-test-automation-turning-guesswork-into-facts) — golden-master testing pattern
- [quietvoid/dovi_tool Discussion #78](https://github.com/quietvoid/dovi_tool/discussions/78), [staxrip/staxrip#1586](https://github.com/staxrip/staxrip/issues/1586), [rigaya/NVEnc#663](https://github.com/rigaya/NVEnc/issues/663) — DV RPU/metadata failure modes in the same encoder-tool family
- [QSVEnc Version History (VideoHelp)](https://www.videohelp.com/software/QSVEnc/version-history) — confirms active, CLI-affecting release cadence
- GitHub Actions self-hosted GPU runner pattern articles (devactivity.com, packagemain.tech, betatim.github.io) — corroborating pattern, no single authoritative source

### Tertiary (LOW confidence)
- [Astral `ty` GitHub releases](https://github.com/astral-sh/ty/releases) — confirms 0.0.x/beta status, informs "do not use yet" recommendation only
- General best-package-manager-2026 landscape commentary — directional only, detailed recommendation grounded in primary sources above

---
*Research completed: 2026-07-08*
*Ready for roadmap: yes*
