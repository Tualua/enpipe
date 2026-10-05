# Phase 1: Package Foundation, Migration & Fast Test Tier - Context

**Gathered:** 2026-07-08 (--auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `enpipe` an installable, dependency-pinned Python package: mechanically migrate the two `legacy/` scripts into `src/enpipe/{detection,encoding,shared}` behind a single subprocess seam, with byte-identical runtime behavior, and add a fast, hardware-free test tier (pure-logic unit tests + mocked subprocess-boundary tests). Covers PKG-02, TEST-01, TEST-02.

**Explicitly NOT in this phase:** the unified `enpipe` CLI entry point (Phase 4 / PKG-01), EBML parser isolation (Phase 2 / DEBT-01), seek/trim extraction (Phase 2 / DEBT-02), ThreadPool/ProcessPool resolution (Phase 3 / DEBT-03), the regression test and CI (Phase 3), and any hardware/real-media test (Phase 4). No behavior changes, no algorithm changes.
</domain>

<decisions>
## Implementation Decisions

### Packaging & dependency locking
- **D-01:** Use `uv` + the `uv_build` build backend with a single `pyproject.toml` manifest and a committed `uv.lock` lockfile. This is the sole dependency/lock/build tool — no `requirements.txt`, no Poetry, no pip-tools. (Per research STACK.md; retires the unpinned `pip install` in `.devcontainer/post-create.sh`.)
- **D-02:** Pin the existing runtime deps (`scenedetect[opencv-headless]`, `numpy`) in `pyproject.toml` `[project.dependencies]` and lock exact versions. Pin to "whatever currently works, documented," not an as-yet-unvalidated 'best' version — real-media validation of the toolchain happens in Phase 4.
- **D-03:** Update `.devcontainer/post-create.sh` to install from the lockfile (e.g. `uv sync`) instead of the ad hoc `python3 -m pip install "scenedetect[opencv-headless]" numpy`.
- **D-04:** `pip install -e .` (or `uv`-equivalent editable install) and `import enpipe` must both work as an acceptance gate.

### Target package layout & module split
- **D-05:** Adopt a `src/`-layout package: `src/enpipe/` containing `detection/`, `encoding/`, and a new `shared/` library layer. Detection and encoding remain coupled ONLY through the existing `<video>.scenes` text file — no direct Python import between the two stages (this preserves the two-independent-CLI-invocation workflow and keeps the phase out of the out-of-scope fused orchestrator).
- **D-06:** Split `legacy/scene_detection.py` and `legacy/encode_scenes.py` into cohesive submodules by responsibility (roughly `config`/`stream`/`detect`/`parallel` for detection; `scenes_io`/`keyframes`/`hdr`/`chunk`/`audio`/`metrics`/`pipeline` for encoding). Exact submodule names are Claude's discretion during planning, guided by research ARCHITECTURE.md.
- **D-07:** Do NOT isolate the hand-rolled EBML/Cues parser in this phase — it moves mechanically with the encoding code and lands in `encoding/`. Its extraction into a tested `mkv/ebml`-style module is Phase 2 (DEBT-01). Same for seek/trim and high-water-mark extraction (Phase 2 / DEBT-02).

### Subprocess testability seam
- **D-08:** Introduce `src/enpipe/shared/proc.py` as the SOLE subprocess call-through choke point: `run()`/`popen()` wrapping `subprocess.run`/`subprocess.Popen`. Every `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` call site routes through it. Chosen over per-function/constructor dependency injection specifically because it requires zero function-signature changes — matching the "preserve current behavior exactly" constraint. (`encode_scenes.py` already has a local `run()` wrapper, so this generalizes an existing pattern.)

### Test framework & subprocess mocking
- **D-09:** Use `pytest` as the test framework with `pytest-subprocess` as the primary subprocess-faking library (it hooks `Popen`, so it exercises the real call surface rather than brittle hand-asserted call signatures). Reserve plain `unittest.mock`/`monkeypatch` for one-off mocks.
- **D-10:** Register a `hardware` pytest marker now and make it excluded from the default run (`pytest -m "not hardware"` is the default invocation). No hardware/real-media test is written in this phase, but the marker convention is established for Phase 4.
- **D-11:** TEST-01 targets: pure-logic functions with zero subprocess/GPU dependency (`kf_before`, `fmt_seek`, `read_scenes`, `_min_scene_len`, EBML byte helpers `_ebml_num`/`_eid`/`_esz`, metrics parsing) using synthetic inputs. TEST-02 targets: mocked subprocess-boundary call sites (`probe_source`, `detect_hdr`, `chunk_command`, `encode_chunk`, `encode_audio`, `keyframe_table_ffprobe`) asserting exact argv construction (flags, seek/trim, HDR selection) and error-path behavior (`die()` vs `SceneDetectionError`).
- **D-12:** Do NOT chase `main()`/CLI-glue coverage. Hypothesis property-based tests are deferred to v2 (QUAL-03).

### Migration strategy & parity verification
- **D-13:** Migration is mechanical cut/paste with NO logic changes. Order: detection first (smaller, no dependents), then encoding. `legacy/scene_detection.py` and `legacy/encode_scenes.py` stay in place, unmodified, as the byte-identical parity oracle throughout this phase and beyond.
- **D-14:** Verify a sample run of the migrated package produces byte-identical output to the corresponding `legacy/` invocation as the migration acceptance check (the phase's key correctness guard, since no behavior may change).

### Conventions to preserve (mechanical move = no rewrite)
- **D-15:** Preserve the existing code conventions verbatim during migration: Russian-language comments/docstrings, `from __future__ import annotations`, `typing.List`/`Optional`/`Union` generic style (not built-in generics), `@dataclass(frozen=True)` value objects, `# --- section --- #` banner dividers, the `log()`/`step()` progress helpers, and the env-var-globals config convention in the encoding stage. Do not modernize style as a drive-by change.

### Claude's Discretion
- Exact submodule filenames within `detection/` and `encoding/`.
- Whether to add a `ruff`/`pyright` config block in `pyproject.toml` now (enforcement in CI is Phase 3 / v2 QUAL-01) — allowed but optional, must not gate this phase.
- Whether to add a `Makefile`/`justfile` with `test` targets (v2 convenience; optional).
- Test directory layout (`tests/` mirroring package structure).
</decisions>

<specifics>
## Specific Ideas

- The `shared.proc` seam mirrors the local `run()` wrapper already present in `legacy/encode_scenes.py` — generalize that, don't invent a new pattern.
- "Preserve current behavior exactly" is the governing constraint for the whole phase; every decision above is subordinate to byte-identical parity with `legacy/`.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Tooling & stack decisions
- `.planning/research/STACK.md` — uv/uv_build/pyproject/lockfile, pytest + pytest-subprocess, ruff/pyright, CI/hardware-gating strategy (with versions, rationale, confidence)

### Target architecture & migration order
- `.planning/research/ARCHITECTURE.md` — target `src/enpipe/` layout, module boundaries, the `shared.proc` seam, the behavior-preserving 8-step migration order
- `.planning/research/SUMMARY.md` — convergent phase ordering and Phase 1 scope rationale
- `.planning/research/FEATURES.md` — table-stakes deliverables, dependency graph, anti-features

### Risks to avoid
- `.planning/research/PITFALLS.md` — silent frame-shift on refactor, mocked-only false confidence, packaging breaking the `.scenes`/CLI surface

### Existing code (parity oracle & conventions)
- `legacy/scene_detection.py` — detection stage source; migrate mechanically, keep as oracle
- `legacy/encode_scenes.py` — encoding stage source (incl. inline EBML parser to move as-is this phase); keep as oracle
- `.planning/codebase/ARCHITECTURE.md` — existing architecture, load-bearing invariants, component→file map
- `.planning/codebase/CONVENTIONS.md` — code style/naming/error-handling/concurrency conventions to preserve
- `.planning/codebase/STRUCTURE.md` — current layout and "where to add new code" guidance
- `.planning/codebase/TESTING.md` — current zero-test state and highest-value test targets

### Project scope
- `.planning/PROJECT.md` — Core Value, Out of Scope (no orchestrator, no algorithm rewrite)
- `.planning/REQUIREMENTS.md` — PKG-02, TEST-01, TEST-02 acceptance language
- `PIPELINE_DESIGN.md` — streaming orchestrator (out of scope) + the mandatory regression-test spec (Phase 3, not here)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `legacy/encode_scenes.py` local `run()` subprocess wrapper — the seed for `shared/proc.py` (D-08).
- Pure-logic helpers already isolated enough to unit-test with no refactor: `kf_before`, `fmt_seek`, `read_scenes`, `_min_scene_len`, `_ebml_num`/`_eid`/`_esz`, metrics parsing (`_SSIM_RE`/`_PSNR_RE`).
- Frozen dataclasses (`DetectionConfig`, `SourceInfo`, `Scene`) move as-is and are trivially constructible in tests.

### Established Patterns
- Dual-mode files (library functions + `argparse` CLI in one module) — migration must keep functions importable; the unified CLI wrapper itself is Phase 4.
- Detection ↔ encoding coupling is ONLY the `<video>.scenes` text file — must be preserved as a boundary (no cross-import).
- Preflight tool-availability checks, `die()` (CLI) vs typed `SceneDetectionError` (library), worker-thread `(success, error)` tuple returns — preserve these regimes unchanged.

### Integration Points
- `.devcontainer/post-create.sh` dependency install step (D-03) — the one devcontainer touchpoint this phase changes.
- `pyproject.toml` `[project.scripts]` will be populated in Phase 4; this phase establishes the package it points at.
</code_context>

<deferred>
## Deferred Ideas

- Unified `enpipe` CLI entry point / `[project.scripts]` dispatch — Phase 4 (PKG-01).
- EBML/Cues parser isolation into a tested `mkv/ebml` module + golden fixtures — Phase 2 (DEBT-01) / v2 (QUAL-02).
- Seek/trim + high-water-mark extraction into pure functions — Phase 2 (DEBT-02).
- ThreadPool-vs-ProcessPool resolution + `dovi_tool` cleanup — Phase 3 (DEBT-03/DEBT-04).
- Mandatory parallel==sequential regression test + CI pipeline — Phase 3 (TEST-03/CI-01).
- Hardware-gated real-media integration test — Phase 4 (TEST-04).
- stdlib `logging` upgrade, typed config layer, ruff/pyright CI enforcement, coverage + Hypothesis, dependency-update automation — v2 (OBS-01, CFG-01, QUAL-01/03, CI-02).
- Pinning qsvencc/ffmpeg/dovi_tool binary versions in the devcontainer — related to D-02 but a separate toolchain concern; flag during planning.
</deferred>

---

*Phase: 01-package-foundation-migration-fast-test-tier*
*Context gathered: 2026-07-08*
