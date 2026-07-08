# Phase 1: Package Foundation, Migration & Fast Test Tier - Research

**Researched:** 2026-07-08
**Domain:** Packaging (`uv`/`uv_build`) + mechanical module-split migration + subprocess-mocked pytest tier, for a two-script Python media-transcode CLI
**Confidence:** HIGH (packaging syntax verified against current `docs.astral.sh`; migration mapping grounded directly in `legacy/*.py` line-level reads; test tooling verified against `pytest-subprocess` docs and PyPI registry)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use `uv` + the `uv_build` build backend with a single `pyproject.toml` manifest and a committed `uv.lock` lockfile. This is the sole dependency/lock/build tool — no `requirements.txt`, no Poetry, no pip-tools. (Per research STACK.md; retires the unpinned `pip install` in `.devcontainer/post-create.sh`.)
- **D-02:** Pin the existing runtime deps (`scenedetect[opencv-headless]`, `numpy`) in `pyproject.toml` `[project.dependencies]` and lock exact versions. Pin to "whatever currently works, documented," not an as-yet-unvalidated 'best' version — real-media validation of the toolchain happens in Phase 4.
- **D-03:** Update `.devcontainer/post-create.sh` to install from the lockfile (e.g. `uv sync`) instead of the ad hoc `python3 -m pip install "scenedetect[opencv-headless]" numpy`.
- **D-04:** `pip install -e .` (or `uv`-equivalent editable install) and `import enpipe` must both work as an acceptance gate.
- **D-05:** Adopt a `src/`-layout package: `src/enpipe/` containing `detection/`, `encoding/`, and a new `shared/` library layer. Detection and encoding remain coupled ONLY through the existing `<video>.scenes` text file — no direct Python import between the two stages (this preserves the two-independent-CLI-invocation workflow and keeps the phase out of the out-of-scope fused orchestrator).
- **D-06:** Split `legacy/scene_detection.py` and `legacy/encode_scenes.py` into cohesive submodules by responsibility (roughly `config`/`stream`/`detect`/`parallel` for detection; `scenes_io`/`keyframes`/`hdr`/`chunk`/`audio`/`metrics`/`pipeline` for encoding). Exact submodule names are Claude's discretion during planning, guided by research ARCHITECTURE.md.
- **D-07:** Do NOT isolate the hand-rolled EBML/Cues parser in this phase — it moves mechanically with the encoding code and lands in `encoding/`. Its extraction into a tested `mkv/ebml`-style module is Phase 2 (DEBT-01). Same for seek/trim and high-water-mark extraction (Phase 2 / DEBT-02).
- **D-08:** Introduce `src/enpipe/shared/proc.py` as the SOLE subprocess call-through choke point: `run()`/`popen()` wrapping `subprocess.run`/`subprocess.Popen`. Every `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` call site routes through it. Chosen over per-function/constructor dependency injection specifically because it requires zero function-signature changes — matching the "preserve current behavior exactly" constraint. (`encode_scenes.py` already has a local `run()` wrapper, so this generalizes an existing pattern.)
- **D-09:** Use `pytest` as the test framework with `pytest-subprocess` as the primary subprocess-faking library (it hooks `Popen`, so it exercises the real call surface rather than brittle hand-asserted call signatures). Reserve plain `unittest.mock`/`monkeypatch` for one-off mocks.
- **D-10:** Register a `hardware` pytest marker now and make it excluded from the default run (`pytest -m "not hardware"` is the default invocation). No hardware/real-media test is written in this phase, but the marker convention is established for Phase 4.
- **D-11:** TEST-01 targets: pure-logic functions with zero subprocess/GPU dependency (`kf_before`, `fmt_seek`, `read_scenes`, `_min_scene_len`, EBML byte helpers `_ebml_num`/`_eid`/`_esz`, metrics parsing) using synthetic inputs. TEST-02 targets: mocked subprocess-boundary call sites (`probe_source`, `detect_hdr`, `chunk_command`, `encode_chunk`, `encode_audio`, `keyframe_table_ffprobe`) asserting exact argv construction (flags, seek/trim, HDR selection) and error-path behavior (`die()` vs `SceneDetectionError`).
- **D-12:** Do NOT chase `main()`/CLI-glue coverage. Hypothesis property-based tests are deferred to v2 (QUAL-03).
- **D-13:** Migration is mechanical cut/paste with NO logic changes. Order: detection first (smaller, no dependents), then encoding. `legacy/scene_detection.py` and `legacy/encode_scenes.py` stay in place, unmodified, as the byte-identical parity oracle throughout this phase and beyond.
- **D-14:** Verify a sample run of the migrated package produces byte-identical output to the corresponding `legacy/` invocation as the migration acceptance check (the phase's key correctness guard, since no behavior may change).
- **D-15:** Preserve the existing code conventions verbatim during migration: Russian-language comments/docstrings, `from __future__ import annotations`, `typing.List`/`Optional`/`Union` generic style (not built-in generics), `@dataclass(frozen=True)` value objects, `# --- section --- #` banner dividers, the `log()`/`step()` progress helpers, and the env-var-globals config convention in the encoding stage. Do not modernize style as a drive-by change.

### Claude's Discretion

- Exact submodule filenames within `detection/` and `encoding/`.
- Whether to add a `ruff`/`pyright` config block in `pyproject.toml` now (enforcement in CI is Phase 3 / v2 QUAL-01) — allowed but optional, must not gate this phase.
- Whether to add a `Makefile`/`justfile` with `test` targets (v2 convenience; optional).
- Test directory layout (`tests/` mirroring package structure).

### Deferred Ideas (OUT OF SCOPE)

- Unified `enpipe` CLI entry point / `[project.scripts]` dispatch — Phase 4 (PKG-01).
- EBML/Cues parser isolation into a tested `mkv/ebml` module + golden fixtures — Phase 2 (DEBT-01) / v2 (QUAL-02).
- Seek/trim + high-water-mark extraction into pure functions — Phase 2 (DEBT-02).
- ThreadPool-vs-ProcessPool resolution + `dovi_tool` cleanup — Phase 3 (DEBT-03/DEBT-04).
- Mandatory parallel==sequential regression test + CI pipeline — Phase 3 (TEST-03/CI-01).
- Hardware-gated real-media integration test — Phase 4 (TEST-04).
- stdlib `logging` upgrade, typed config layer, ruff/pyright CI enforcement, coverage + Hypothesis, dependency-update automation — v2 (OBS-01, CFG-01, QUAL-01/03, CI-02).
- Pinning qsvencc/ffmpeg/dovi_tool binary versions in the devcontainer — related to D-02 but a separate toolchain concern; flag during planning.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PKG-02 | All Python dependencies are pinned and locked (manifest + lockfile), and container provisioning installs from the lockfile instead of ad hoc unpinned `pip install` | Concrete `pyproject.toml` `[build-system]`/`[project]`/`[tool.uv]` structure (Standard Stack, Code Examples); verified current versions for `scenedetect`, `numpy`, `uv`, `uv_build` (Package Legitimacy Audit); `.devcontainer/post-create.sh` rewrite plan (Environment Availability, Migration Order step 1) |
| TEST-01 | Pure-logic functions with no subprocess/GPU dependency have unit tests using synthetic inputs | Exact function list + target module for each (Mechanical Migration Map); pure-function test examples (Code Examples); module-level-env-var-constant gotcha for `chunk_command`/`detect_hdr` (Common Pitfalls) |
| TEST-02 | Subprocess-boundary call sites have mocked tests asserting exact argv construction and error-path behavior, with no real media | `pytest-subprocess` `fp` fixture API verified against official docs (Standard Stack, Code Examples); exact call-site list needing `shared.proc` substitution (Mechanical Migration Map); `hardware` marker registration (Code Examples) |
</phase_requirements>

## Summary

This phase has three intertwined deliverables — package scaffold, mechanical migration, fast test tier — and the research below is organized so the planner can sequence them as: **(1) scaffold + `shared/` first, (2) detection migration + its tests, (3) encoding migration + its tests, (4) parity verification, (5) acceptance gate.** The `uv`/`uv_build`/`pytest`/`pytest-subprocess` stack choice was already locked by project-level research (`STACK.md`) and is not re-litigated here; this document adds the exact `pyproject.toml` syntax, a line-level function→module mapping for both `legacy/*.py` files, and two migration-specific hazards the project-level research didn't surface: a **circular-import risk** between `detection.detect` and `detection.parallel` (they call each other), and a **module-scope-env-var layering problem** for `die()` and the `ICQ`/`QPMAX`/`GOP_LEN`/`DV_PROFILE`/`FLAC_LEVEL` globals once the single `encode_scenes.py` file is split into seven submodules.

One correction to project-level research: `STACK.md` describes `pytest-subprocess` as "latest (2.x)" — the actual current PyPI release is **1.6.0** `[VERIFIED: PyPI registry]`; there is no 2.x line as of this research date. This does not change the tooling choice, only the version pin.

A second scope clarification worth flagging up front: **this phase builds no CLI at all.** `cli/detect.py`/`cli/encode.py`/`cli/app.py` are explicitly Phase 4 (PKG-01, per REQUIREMENTS.md traceability and CONTEXT.md's Deferred list). The byte-identical parity check (D-14) therefore cannot be "run the new CLI vs the old CLI" — it must be a short, throwaway script (not part of the installed package, not committed as a permanent CLI) that imports `enpipe.detection.detect.detect_scenes(...)` / builds an `argparse.Namespace`-shaped object and calls `enpipe.encoding.pipeline.run_encode(args)` directly, then diffs output against invoking `legacy/scene_detection.py` / `legacy/encode_scenes.py` as subprocesses. This is a manual/scripted verification step for this phase, not an automated pytest case (the automated `hardware`-marked equivalent is TEST-04, Phase 4).

**Primary recommendation:** Scaffold `pyproject.toml` with `uv_build`, create `shared/proc.py` + `shared/logging.py` first (both stages depend on them), migrate detection then encoding exactly per the function→module table below (fixing the circular-import and `die()`-layering hazards as you go), and write TEST-01/TEST-02 tests module-by-module immediately after each migration step rather than batching all tests to the end — this keeps the "small, verifiable diff" discipline D-13/D-14 require.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Package/dependency management (`pyproject.toml`, `uv.lock`) | Build/Packaging | — | PEP 517/621 manifest; no runtime tier — resolved before any process starts |
| Scene detection (ffmpeg pipe → PySceneDetect) | Local batch CLI (library layer) | — | Runs as a local subprocess-orchestrating Python process; no server/client split exists in this project |
| Scene-aware AV1 encoding (qsvencc chunking + mux) | Local batch CLI (library layer) | — | Same — single-process batch orchestration, GPU work delegated to subprocesses |
| Subprocess invocation (`ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge`) | `shared.proc` seam | — | Single choke point by design (D-08); every external-tool call routes through it regardless of which stage calls it |
| Fast test tier (pure-logic + mocked subprocess) | Test/CI tier | — | Runs identically on any machine, no GPU/hardware required; this is the *entire* deliverable of TEST-01/TEST-02 |
| Hardware-gated tests (real qsvencc, real media) | Test/CI tier (excluded by default) | — | Explicitly out of scope this phase (Phase 4); only the `hardware` marker convention is established now |

This project has no browser/frontend/CDN tier — it is a local, subprocess-orchestrating CLI toolchain (per `.planning/codebase/ARCHITECTURE.md` and `PROJECT.md` Out of Scope: "no network service, auth, or multi-user layer"). The map above exists mainly to confirm there is no tier-misassignment risk to check for in this phase — the only "boundary" that matters is the `shared.proc` subprocess seam, which is a testability boundary, not a tier boundary.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `uv` | 0.11.28 `[VERIFIED: PyPI registry]` | Project/dependency manager, venv, lockfile | Already locked by `STACK.md`; confirmed current on PyPI as of this research date |
| `uv_build` | `>=0.11.28,<0.12` `[VERIFIED: uv official docs]` | PEP 517 build backend | Exact `[build-system]` syntax confirmed via `docs.astral.sh/uv/concepts/build-backend/`: `requires = ["uv_build>=0.11.28,<0.12"]`, `build-backend = "uv_build"`. src-layout discovery is **automatic, zero-config** for a package at `src/<name>/__init__.py` — no extra `[tool.uv]` entry needed for the standard case |
| `pytest` | 9.1.1 `[VERIFIED: PyPI registry]` | Test framework | Matches `STACK.md`; confirmed installed and runnable in this devcontainer already (`pytest 9.1.1` on `PATH`) |
| `pytest-subprocess` | **1.6.0** `[VERIFIED: PyPI registry]` — correcting `STACK.md`'s "2.x" claim | Fakes `subprocess.Popen` (and therefore `run`/`call`/`check_output`) for TEST-02 | `fp` fixture: `fp.register([...], stdout=..., returncode=...)` then assert `[...] in fp.calls` or inspect `recorder.calls[0].kwargs`. Confirmed against official docs (`pytest-subprocess.readthedocs.io/en/latest/usage.html`) |
| `scenedetect[opencv-headless]` | 0.7 `[VERIFIED: PyPI registry]`, `[ASSUMED]` that this is the version already validated by the prior project (per legacy docstring: "Проверено против PySceneDetect 0.7") | Scene detection engine | Already installed in this devcontainer's system Python (`scenedetect.__version__ == "0.7"` confirmed by direct import) — pin exactly this, per D-02 ("whatever currently works, documented") |
| `numpy` | 2.5.1 `[VERIFIED: PyPI registry]`, already installed in this devcontainer | Frame buffer array handling in `QsvPipeStream.read()` | Already installed (`numpy.__version__ == "2.5.1"` confirmed) — pin exactly this per D-02 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-mock` | 3.15.1 `[VERIFIED: PyPI registry]` | Thin `mocker` wrapper for one-off, non-subprocess mocks | Per D-09: reserve for one-offs (e.g., mocking `Path.stat()`/`os.environ` in an EBML edge-case test), not the primary TEST-02 mechanism |
| `pytest-cov` + `coverage` | pytest-cov 7.1.0, coverage 7.15.0 `[VERIFIED: PyPI registry]` | Coverage reporting | Optional this phase — coverage *enforcement* in CI is v2 (QUAL-03); safe to add the dependency now with no gate |
| `hypothesis` | 6.156.2 `[VERIFIED: PyPI registry]` | Property-based testing | **Do not add this phase** — explicitly deferred to v2 (QUAL-03) per D-12. Listed here only so the planner doesn't accidentally pull it in via `uv add --dev` autocomplete/habit |

### Alternatives Considered

No alternatives evaluation needed here — the stack (`uv`, `pytest`, `pytest-subprocess`) is a locked decision from `STACK.md`/CONTEXT.md D-01/D-09, not open for reconsideration in this phase.

**Installation:**
```bash
# One-time, if uv is not yet on PATH (confirmed NOT installed in the current
# devcontainer image as of this research — `command -v uv` returns nothing)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Project init (once pyproject.toml exists, or use `uv init --package enpipe --no-readme`
# then hand-edit to match the src-layout/exact deps below)
uv add "scenedetect[opencv-headless]==0.7" "numpy==2.5.1"
uv add --dev pytest pytest-subprocess pytest-mock

# Sync locked environment
uv sync --locked

# Run the fast tier
uv run pytest -m "not hardware"
```

**Version verification:** All versions in the Core/Supporting tables above were checked via `python3 -m pip index versions <pkg>` against the live PyPI index at research time (not training-data recall) — see Package Legitimacy Audit below for the full check log.

## Package Legitimacy Audit

`slopcheck` (0.6.1) was installed and run against every package this phase would add to `pyproject.toml`. All packages returned `OK` (one `info`-severity note, not a blocker).

| Package | Registry | slopcheck | Disposition |
|---------|----------|-----------|-------------|
| `scenedetect` | PyPI | OK | Approved — already installed in devcontainer, pin `0.7` |
| `numpy` | PyPI | OK | Approved — already installed in devcontainer, pin `2.5.1` |
| `pytest` | PyPI | OK | Approved |
| `pytest-subprocess` | PyPI | OK | Approved — pin `1.6.0`, not "2.x" |
| `pytest-mock` | PyPI | OK | Approved |
| `pytest-cov` | PyPI | OK (flag: `NO_REPO` / info) | Approved — slopcheck notes no source repo is linked in PyPI metadata ("harder to verify what this code actually does"); this is a well-known, long-established pytest-org package (`pytest-dev/pytest-cov` on GitHub exists, just not linked from PyPI metadata) — info-severity only, not a install blocker |
| `coverage` | PyPI | OK | Approved (transitive dep of pytest-cov) |
| `uv_build` | PyPI | OK | Approved — build backend |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none.

All packages recommended in this document are tagged `[VERIFIED: PyPI registry]` — both `pip index versions` and `slopcheck` were run successfully in this session (not a degraded/`[ASSUMED]`-only run).

## Mechanical Migration Map

The tables below are the literal function/class → target-module mapping for the D-13 mechanical cut/paste, derived directly from reading `legacy/scene_detection.py` and `legacy/encode_scenes.py` line-by-line. Line numbers are current as of this research (files are unmodified per D-13).

### Detection: `legacy/scene_detection.py` → `src/enpipe/detection/`

| Symbol | Lines | Target module | Notes |
|--------|-------|----------------|-------|
| `PathLike` | 50 | `detection/config.py` | Type alias |
| `SceneDetectionError` | 53-54 | `detection/config.py` | |
| `DetectionConfig` | 62-84 | `detection/config.py` | frozen dataclass |
| `SourceInfo` | 87-92 | `detection/config.py` | frozen dataclass |
| `Scene` | 95-107 | `detection/config.py` | frozen dataclass |
| `probe_source` | 115-167 | `detection/stream.py` | `subprocess.run` → `proc.run` |
| `QsvPipeStream` | 175-422 | `detection/stream.py` | `subprocess.Popen` → `proc.popen` in `_start_process` (line 266) |
| `_min_scene_len` | 430-433 | `detection/detect.py` | pure — TEST-01 target |
| `_detect_relative` | 436-460 | `detection/detect.py` | |
| `_build_scenes` | 463-468 | `detection/detect.py` | pure |
| `detect_scenes` | 471-485 | `detection/detect.py` | **see Circular Import hazard below** |
| `keyframes_in_window` | 498-521 | `detection/parallel.py` | `subprocess.run` → `proc.run` |
| `find_boundary` | 524-553 | `detection/parallel.py` | |
| `_sanitize_boundaries` | 556-564 | `detection/parallel.py` | pure |
| `_boundary_worker` | 571-573 | `detection/parallel.py` | module-level (pickle-safe), keep as-is |
| `_segment_worker` | 576-579 | `detection/parallel.py` | module-level (pickle-safe), keep as-is |
| `detect_scenes_parallel` | 582-644 | `detection/parallel.py` | **see Circular Import hazard below** |
| `if __name__ == "__main__":` block | 647-692 | **Not migrated this phase** | Phase 4 (`cli/detect.py`) |

### Encoding: `legacy/encode_scenes.py` → `src/enpipe/encoding/` + `src/enpipe/shared/`

| Symbol | Lines | Target module | Notes |
|--------|-------|----------------|-------|
| `ICQ`, `QPMAX`, `GOP_LEN` | 52-54 | `encoding/chunk.py` | module-level, read from env at import time — **see env-var layering note below** |
| `DV_PROFILE` | 55 | `encoding/hdr.py` | same pattern |
| `JOBS` | 56 | `encoding/pipeline.py` | used only as a default value; consumed for real by Phase 4's CLI default |
| `FLAC_LEVEL` | 57 | `encoding/audio.py` | same pattern |
| `LOSSLESS` (set constant) | 59 | `encoding/audio.py` | |
| `die` | 62-63 | `shared/logging.py` | **relocate here, not `encoding/pipeline.py`** — see Pitfall below |
| `run` (local wrapper) | 66-67 | **deleted** — becomes `shared/proc.py:run` | mechanical: delete this def, callers use `proc.run` |
| `_START`, `log`, `step` | 73-88 | `shared/logging.py` | unchanged body |
| `_SCENE_RE`, `read_scenes` | 94-107 | `encoding/scenes_io.py` | pure — TEST-01 target |
| `probe_fps` | 110-122 | `encoding/pipeline.py` | calls `die()`; not in D-11's explicit TEST-02 list — see Open Questions |
| `_ebml_num`, `_eid`, `_esz` | 130-149 | `encoding/keyframes.py` | pure — TEST-01 target. **Stays here per D-07** (not `mkv/ebml.py` — that split is Phase 2) |
| `keyframe_table_cues` | 152-262 | `encoding/keyframes.py` | file I/O + EBML walk, unchanged |
| `keyframe_table_ffprobe` | 265-288 | `encoding/keyframes.py` | calls `run()`→`proc.run`, calls `die()` — TEST-02 target (D-11) |
| `keyframe_table` | 291-300 | `encoding/keyframes.py` | dispatcher, calls `log()` |
| `kf_before` | 303-313 | `encoding/keyframes.py` | pure — TEST-01 target |
| `fmt_seek` | 316-326 | `encoding/keyframes.py` | pure — TEST-01 target |
| `detect_hdr` | 332-348 | `encoding/hdr.py` | calls `run()`×2 → `proc.run` — TEST-02 target (D-11) |
| `chunk_command` | 354-370 | `encoding/chunk.py` | **pure function** (builds argv, calls no subprocess) — TEST-02 lists it for argv-assertion but it needs **no mocking**, just direct call + assert on the returned list |
| `_SSIM_RE`, `_PSNR_RE`, `parse_metrics` | 376-391 | `encoding/chunk.py` | pure — TEST-01 target (metrics parsing) |
| `count_frames` | 394-399 | `encoding/chunk.py` | calls `run()` → `proc.run` |
| `encode_chunk` | 402-417 | `encoding/chunk.py` | calls `run()` (via itself + `count_frames`) — TEST-02 target (D-11) |
| `encode_audio` | 423-478 | `encoding/audio.py` | calls `run()`×2 → `proc.run` — TEST-02 target (D-11); returns `(bool, Optional[str])`, never raises (preserve exactly, D-15) |
| `write_metrics_csv` | 481-509 | `encoding/metrics.py` | pure-ish (file write given rows) |
| `main()` body minus argparse (531-724) | 515-724 | `encoding/pipeline.py` as `run_encode(args)` | Keep the parameter shaped as an `argparse.Namespace`-like object (same attribute names: `video`, `scenes`, `out`, `frm`, `to`, `workdir`, `keep`, `jobs`, `no_audio`, `no_metrics`, `csv`) so Phase 4's `cli/encode.py` can build a `Namespace` and call `run_encode(args)` unchanged — this is the minimal-diff shape, not a rewrite to individual keyword params |
| `if __name__ == "__main__":` guard | 727-728 | **Not migrated this phase** | Phase 4 |

## Architecture Patterns

### System Architecture Diagram (Phase 1 end-state — no CLI yet)

```
                     (no console_script this phase — Phase 4)

┌─────────────────────────────┐        ┌──────────────────────────────────────────┐
│  enpipe.detection            │        │  enpipe.encoding                          │
│  config.py  (dataclasses)    │        │  scenes_io.py (read_scenes)               │
│  stream.py  (probe_source,   │        │  keyframes.py (EBML + kf_before/fmt_seek) │
│              QsvPipeStream)  │        │  hdr.py       (detect_hdr)                │
│  detect.py  (detect_scenes)  │        │  chunk.py     (chunk_command, encode_chunk)│
│  parallel.py(detect_scenes_  │        │  audio.py     (encode_audio)              │
│              parallel)       │        │  metrics.py   (write_metrics_csv)         │
└──────────────┬────────────────┘        │  pipeline.py  (run_encode(args))          │
               │ writes                  └───────────────┬────────────────────────────┘
               ▼                                          │ reads
      `<video>.scenes` (unchanged text format) ───────────┘
      (THE ONLY COUPLING — no direct Python import either direction)

        Both packages import, never the other way:
┌───────────────────────────────────────────────────────────────────┐
│  enpipe.shared                                                     │
│  proc.py     — run()/popen(), the ONLY subprocess call-through     │
│  logging.py  — log(), step(), die(), _START                        │
└───────────────────────────────────────────────────────────────────┘

Test tiers (both hardware-free, both run by default):
  tests/  ─┬─ unit/       — TEST-01: pure-logic, zero mocking
           └─ subprocess/ — TEST-02: pytest-subprocess `fp` fixture fakes Popen
  (hardware marker registered in pyproject.toml, excluded via `-m "not hardware"`,
   but no test carries it yet — Phase 4 adds the first one)
```

### Recommended Project Structure

```
enpipe/
├── pyproject.toml
├── uv.lock
├── src/
│   └── enpipe/
│       ├── __init__.py            # version string only, no logic
│       ├── detection/
│       │   ├── __init__.py
│       │   ├── config.py          # PathLike, SceneDetectionError, DetectionConfig, SourceInfo, Scene
│       │   ├── stream.py          # probe_source, QsvPipeStream
│       │   ├── detect.py          # _min_scene_len, _detect_relative, _build_scenes, detect_scenes
│       │   └── parallel.py        # keyframes_in_window, find_boundary, _sanitize_boundaries,
│       │                          #   _boundary_worker, _segment_worker, detect_scenes_parallel
│       ├── encoding/
│       │   ├── __init__.py
│       │   ├── scenes_io.py       # _SCENE_RE, read_scenes
│       │   ├── keyframes.py       # _ebml_num/_eid/_esz, keyframe_table_cues/_ffprobe/_table,
│       │   │                      #   kf_before, fmt_seek  (EBML stays here per D-07)
│       │   ├── hdr.py             # DV_PROFILE, detect_hdr
│       │   ├── chunk.py           # ICQ/QPMAX/GOP_LEN, chunk_command, _SSIM_RE/_PSNR_RE,
│       │   │                      #   parse_metrics, count_frames, encode_chunk
│       │   ├── audio.py           # FLAC_LEVEL, LOSSLESS, encode_audio
│       │   ├── metrics.py         # write_metrics_csv
│       │   └── pipeline.py        # JOBS, probe_fps, run_encode(args)
│       └── shared/
│           ├── __init__.py
│           ├── proc.py            # run(), popen() — sole subprocess seam
│           └── logging.py         # _START, log(), step(), die()
├── tests/
│   ├── conftest.py                # shared fixtures (e.g. synthetic keyframe tables, DetectionConfig factory)
│   ├── unit/                      # TEST-01: pure-logic, no mocking, no subprocess
│   │   ├── detection/
│   │   │   └── test_detect.py     # _min_scene_len, _build_scenes
│   │   └── encoding/
│   │       ├── test_scenes_io.py  # read_scenes
│   │       ├── test_keyframes.py  # kf_before, fmt_seek, _ebml_num/_eid/_esz
│   │       └── test_chunk.py      # parse_metrics, chunk_command (pure, no mock needed)
│   └── subprocess/                # TEST-02: pytest-subprocess `fp` fixture
│       ├── detection/
│       │   └── test_stream.py     # probe_source
│       └── encoding/
│           ├── test_keyframes.py  # keyframe_table_ffprobe
│           ├── test_hdr.py        # detect_hdr
│           ├── test_chunk.py      # encode_chunk
│           └── test_audio.py      # encode_audio
└── legacy/                        # unchanged, stays as parity oracle (D-13)
```

`tests/unit/` vs `tests/subprocess/` (rather than a flat `tests/` or a single `tests/unit/`) makes the TEST-01/TEST-02 split visible in the directory tree itself, matching `STACK.md`'s recommended two-tier split and making it trivial for a future CI config to target either tier by path if ever needed — though `pytest -m` is still the primary selector, per D-10.

### Pattern 1: `shared.proc` seam — exact code, generalized from the existing local wrapper

`legacy/encode_scenes.py:66-67` already has this pattern at file scope; this promotes it unchanged:

```python
# src/enpipe/shared/proc.py
"""Единственная точка вызова subprocess — сюда заведены все обращения к
ffmpeg/ffprobe/qsvencc/mkvmerge. Даёт единый шов для подмены в тестах
(pytest-subprocess перехватывает Popen, на котором строятся run/Popen)."""
from __future__ import annotations

import subprocess
from typing import List


def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def popen(cmd: List[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(cmd, **kw)
```

Every call site changes from `subprocess.run(cmd, ...)` to `proc.run(cmd, ...)` (or `run(cmd, ...)` → `proc.run(cmd, ...)` for the encoding side, which already used the local wrapper name `run`). No function signature changes anywhere — this is the whole point of D-08/Anti-Pattern 2 in the project-level ARCHITECTURE.md research.

### Pattern 2: Fixing the `detect.py` ↔ `parallel.py` circular import (new finding, not in project-level research)

**What goes wrong if migrated naively:** `detect_scenes` (destined for `detection/detect.py`) calls `detect_scenes_parallel` when `jobs > 1` (`legacy/scene_detection.py:479-480`). `detect_scenes_parallel` (destined for `detection/parallel.py`) calls `detect_scenes(path, config, jobs=1)` as its own fallback in *two* places (`legacy/scene_detection.py:592`, `:603`). If both modules do a top-level `from .other_module import the_function`, Python's circular-import resolution can fail depending on which module is imported first — whichever module is imported second will try to pull a name from a partially-initialized sibling module that hasn't defined that name yet.

**How to avoid — use a deferred (function-body) import for one direction:**

```python
# src/enpipe/detection/detect.py
def detect_scenes(path, config=DetectionConfig(), jobs=1):
    if jobs and jobs > 1:
        from .parallel import detect_scenes_parallel  # deferred: breaks the cycle
        return detect_scenes_parallel(path, config, jobs)
    ...

# src/enpipe/detection/parallel.py
def detect_scenes_parallel(path, config, jobs):
    from .detect import detect_scenes  # deferred: breaks the cycle
    ...
    if total is None or jobs < 2 or total < jobs * min_span:
        return detect_scenes(path, config, jobs=1)
    ...
```

Both sides deferred is the safest (order-independent) fix and costs nothing functionally — Python caches the module after first full import, so the deferred import is only "slow" on the very first call, not per-call. This is a pure mechanical detail, not a logic change, so it's consistent with D-13.

### Pattern 3: `die()` relocation to `shared/logging.py`, not `encoding/pipeline.py` (new finding)

**What goes wrong if migrated naively:** `die()` (`legacy/encode_scenes.py:62-63`) is called directly from `keyframe_table_ffprobe` (destined for `encoding/keyframes.py`) and `probe_fps` (destined for `encoding/pipeline.py`), as well as from the orchestration body (also destined for `encoding/pipeline.py`). If `die()` is left in `pipeline.py` (the natural-looking home since `main()`/`run_encode` lives there), then `keyframes.py` would need to `import` from `pipeline.py` to call `die()` — but `pipeline.py` itself imports `keyframes.py` (to call `keyframe_table`), creating a circular import identical in shape to Pattern 2 above, except this one has no clean "defer one side" fix because `die()` is called at module-import-adjacent scope in some paths, not just inside functions.

**Fix:** relocate `die()` into `shared/logging.py` alongside `log()`/`step()`. This is architecturally consistent with the project-level ARCHITECTURE.md research, which already places `log()`/`step()` in `shared/logging.py` as "reused by both CLIs" — `die()` belongs in the same leaf module (depended on by everything, depends on nothing in this package), preserving its **exact** `"encode_scenes: {msg}"` message prefix per D-15 (this string is part of current behavior — the parity oracle comparison in D-14 would need it byte-identical, so do not "modernize" it to say `"enpipe: {msg}"` even though the module name changed):

```python
# src/enpipe/shared/logging.py (excerpt)
import sys

def die(msg: str) -> None:
    sys.exit(f"encode_scenes: {msg}")   # prefix preserved verbatim — see D-15/D-14
```

### Pattern 4: Module-scope env-var constants must be monkeypatched as module attributes, not via `os.environ` in tests

**What goes wrong:** `ICQ = int(os.environ.get("ICQ", "23"))` (and the sibling constants) execute exactly once, at import time (`legacy/encode_scenes.py:52-57`). After migration, `encoding/chunk.py` will have `ICQ`, `QPMAX`, `GOP_LEN` as module-level constants computed the same way. A test that does `monkeypatch.setenv("ICQ", "30")` **after** `enpipe.encoding.chunk` has already been imported (which it will have been, by pytest's collection phase) has no effect — the module-level `ICQ` was already bound to the old value.

**Correct pattern for tests that need a non-default value:**

```python
def test_chunk_command_uses_custom_icq(monkeypatch):
    from enpipe.encoding import chunk
    monkeypatch.setattr(chunk, "ICQ", 30)   # patch the already-bound module attribute
    cmd = chunk.chunk_command(Path("in.mkv"), "00:00:00.000", "0:99",
                               Path("out.obu"), [], metrics=False)
    assert "--icq" in cmd and cmd[cmd.index("--icq") + 1] == "30"
```

Most TEST-01/TEST-02 tests for `chunk_command`/`detect_hdr` can simply assert against the **default** env values (`ICQ=23`, `QPMAX=100`, `GOP_LEN=300`, `DV_PROFILE="10.1"`) without touching this at all — flag this pattern only for the subset of tests that specifically want to verify env-var overrides work.

### Anti-Patterns to Avoid

- **Adding a `runner`/`CommandRunner` parameter to any migrated function:** Already called out in project-level ARCHITECTURE.md as Anti-Pattern 2 — do not do this. All subprocess mocking happens via `monkeypatch.setattr(enpipe.shared.proc, "run", fake)` or `pytest-subprocess`'s `fp` fixture, never via new function parameters.
- **Splitting `chunk_command` into "the pure part" and "the subprocess part":** it's already 100% pure (builds and returns a `List[str]`, calls nothing). Resist the urge to add a wrapper — test it directly, no `fp` fixture needed for this one function specifically, even though D-11 groups it under "TEST-02 targets."
- **Treating the EBML parser move as an opportunity to also isolate it:** D-07 is explicit — it moves into `encoding/keyframes.py` as-is this phase. Do not create `mkv/ebml.py` yet; that read/parse split is Phase 2 (DEBT-01), and doing it early would silently expand this phase's diff surface against D-13's "small, verifiable diff" discipline.
- **Building any part of `cli/`:** No `cli/detect.py`, `cli/encode.py`, or `[project.scripts]` entry this phase (Phase 4). Parity verification (D-14) uses direct function calls from a throwaway script, not two CLIs compared against each other.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Subprocess argv/stdout/returncode faking for tests | A hand-rolled `unittest.mock.patch("subprocess.run")` per test file, or a bespoke fake-Popen class | `pytest-subprocess`'s `fp` fixture, centralized per-tool fixtures in `conftest.py` (e.g. `fake_ffprobe_json`) | `fp` hooks `Popen` itself, so it transparently covers `run`/`call`/`check_output`/`Popen` uniformly — a hand-rolled patch of just `subprocess.run` would silently miss the `Popen`-based `QsvPipeStream` and any future switch from `run` to `Popen` internally (exactly the risk project-level ARCHITECTURE.md's Pattern 1 trade-off section calls out) |
| Dependency locking / reproducible installs | A `requirements.txt` generated by `pip freeze`, or a hand-maintained pin list | `uv add` + committed `uv.lock` | `uv.lock` is a cross-platform resolved lockfile; `pip freeze` output is platform-specific and doesn't distinguish direct vs transitive deps — exactly the class of problem `STACK.md` already flags as the current risk (`CONCERNS.md`'s unpinned-`pip install` finding) |
| Package build backend / `setup.py` | A hand-written `setup.py`/`setup.cfg` with `find_packages()` | `uv_build` with zero-config src-layout discovery | Confirmed zero-config for the standard `src/<name>/__init__.py` shape (verified against current `docs.astral.sh`) — writing a custom `setup.py` here would be strictly more code for an already-solved problem |

**Key insight:** every "don't hand-roll" item above is really the same lesson stated three ways — this phase's entire purpose is to *stop* hand-rolling infrastructure (dependency pinning, subprocess mocking, build config) that has off-the-shelf, already-decided (per `STACK.md`/CONTEXT.md) tooling, so that the *actual* hand-rolled code this project legitimately owns (the EBML parser, the seek/trim math) gets to stay the sole focus of future phases' scrutiny.

## Concrete `pyproject.toml`

```toml
[build-system]
requires = ["uv_build>=0.11.28,<0.12"]
build-backend = "uv_build"

[project]
name = "enpipe"
version = "0.1.0"
description = "Scene-aware AV1 re-encode pipeline (Intel Arc QSV)"
requires-python = ">=3.12"
dependencies = [
    "scenedetect[opencv-headless]==0.7",
    "numpy==2.5.1",
]

# [project.scripts] intentionally omitted this phase — Phase 4 (PKG-01) adds
# `enpipe = "enpipe.cli.app:main"` once cli/detect.py + cli/encode.py exist.

[dependency-groups]
dev = [
    "pytest==9.1.1",
    "pytest-subprocess==1.6.0",
    "pytest-mock==3.15.1",
]

[tool.pytest.ini_options]
markers = [
    "hardware: requires real QSV hardware and real media; excluded by default (Phase 4 adds the first test)",
]
addopts = "-m \"not hardware\""
testpaths = ["tests"]

# Optional, Claude's discretion (must not gate this phase — enforcement is Phase 3/QUAL-01):
# [tool.ruff]
# target-version = "py312"
# line-length = 100  # matches existing ~88-100 col soft-wrap convention (CONVENTIONS.md)
```

**Why `dependencies` pins with `==`, not `>=`:** D-02 says "pin to whatever currently works, documented, not an as-yet-unvalidated 'best' version." Exact `==` pins on `scenedetect` and `numpy` match the versions already installed and implicitly validated in this devcontainer image (`scenedetect==0.7`, `numpy==2.5.1`, confirmed via direct `import` in this research session) — `uv.lock` will additionally pin every transitive dependency, so the `==` in `[project.dependencies]` is redundant-but-explicit documentation of intent, while `uv.lock` is the actual reproducibility mechanism.

**`.devcontainer/post-create.sh` change (D-03):** replace

```bash
python3 -m pip install --no-warn-script-location "scenedetect[opencv-headless]" numpy
```

with (note: `uv` itself is confirmed **not installed** in the current devcontainer image — `command -v uv` returned nothing in this research session — so the script must install `uv` before it can use it):

```bash
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv sync --locked
```

An alternative the planner may consider (not required by D-03, but worth flagging): add the official `ghcr.io/astral-sh/uv` devcontainer feature to `devcontainer.json` instead, which installs `uv` at image-feature time rather than in `post-create.sh`. D-03's literal text only mandates changing `post-create.sh`, so the `curl`-in-script approach above is the minimal-diff option; the feature-based approach is a reasonable alternative if the planner wants `uv` baked into the image layer instead. Flagged as an open implementation choice, not a locked decision.

## Common Pitfalls

### Pitfall 1: Refactoring "cleans up" the seek/trim arithmetic and silently shifts frames

**What goes wrong:** A migration pass that touches `kf_before`/`fmt_seek` "while moving the file" changes rounding/comparison behavior, landing a chunk boundary off by a frame — `qsvencc` still exits 0, `count_frames` still matches the aggregate total, so nothing fails loudly. (Sourced from project-level `PITFALLS.md` Pitfall 1 — directly relevant here since these two functions move in this exact phase.)
**Why it happens:** Zero test coverage today; the arithmetic looks like ordinary rounding code to someone unaware of the floor-to-millisecond-lands-on-keyframe invariant.
**How to avoid:** Move `kf_before`/`fmt_seek` with **zero logic changes** (D-13), then immediately write the TEST-01 synthetic-table unit tests for them (edge cases: frame exactly on a keyframe, frame between keyframes, first/last keyframe) *before* moving on to the next function — don't defer these two specifically to "later in the test-writing pass."
**Warning signs:** A diff touching these functions that isn't a pure copy-paste (i.e., any changed line, not just changed location).

### Pitfall 2: Mocking `subprocess` so thoroughly the tests provide false confidence

**What goes wrong:** TEST-02's mocked tests validate argv construction and error-path branching correctly, but can never validate that a real `qsvencc`/`ffmpeg` invocation with those exact flags actually produces correct output — that's precisely the class of bug this pipeline's whole value proposition depends on. (Sourced from project-level `PITFALLS.md` Pitfall 2.)
**Why it happens:** Mocked-subprocess tests are the *correct* tool for orchestration logic, but it's easy to conflate "we have tests now" with "we have validated the pipeline."
**How to avoid:** This phase's TEST-01/TEST-02 tiers are explicitly and only "orchestration logic is correct" — D-14's manual byte-identical parity check against `legacy/` (which, in this devcontainer, **can** exercise real `ffmpeg`/`qsvencc`/`mkvmerge`, since hardware is confirmed present — see Environment Availability) is what actually validates real-tool behavior for this phase. Don't let a green `pytest -m "not hardware"` run substitute for running the D-14 parity check.
**Warning signs:** Treating `pytest -m "not hardware"` passing as sufficient evidence the migration is behavior-preserving, without having run the D-14 sample-run comparison.

### Pitfall 3: Packaging silently changes the `.scenes`/CLI/env-var surface

**What goes wrong:** While splitting `encode_scenes.py` into seven files, it's tempting to "clean up" the free-text `.scenes` format, rename an env var, or adjust a default while things are already being touched. (Sourced from project-level `PITFALLS.md` Pitfall 8.) Since this phase builds no CLI, the most likely place this manifests is *env var name drift* — e.g., accidentally reading `os.environ.get("Icq")` or introducing a typo while retyping the constant block across five new files.
**Why it happens:** Retyping code across new file boundaries (rather than pure copy-paste) is exactly where "close but not identical" mistakes creep in.
**How to avoid:** Copy-paste the exact `os.environ.get("ICQ", "23")`-style lines character-for-character into their new module locations; do not retype them from memory. Add a one-line assertion test per relocated constant (`assert chunk.ICQ == 23` with a clean environment) as a cheap tripwire.
**Warning signs:** Any test that needs to explicitly `monkeypatch.delenv(...)` to get a "clean" default suggests the constant's default value or env var name may have drifted from the original.

### Pitfall 4: `read_scenes`'s silent-empty-match behavior must survive the move unchanged

**What goes wrong:** `read_scenes` (`legacy/encode_scenes.py:99-107`) already has a subtle behavior worth preserving exactly: individual non-matching lines are silently skipped (not an error), but an **entirely empty result** calls `die()` — this two-level behavior (per-line silent skip, whole-file loud failure) is easy to accidentally simplify to "loud failure per line" or "silent failure overall" during a mechanical move that isn't purely copy-paste.
**How to avoid:** Preserve the exact structure — `for line in ...: if m: append` then `if not out: die(...)` after the loop, unchanged. TEST-01 should include a test asserting a line with no `frames [N, M)` match is silently skipped while a file with **zero** matching lines triggers the `die()`/`SystemExit` path (D-11 explicitly calls out testing "error-path behavior").

### Pitfall 5: `.venv`/interpreter confusion between the devcontainer's pre-existing system Python packages and the new `uv`-managed venv

**What goes wrong:** This devcontainer's system Python already has `scenedetect`/`numpy` installed via the old ad hoc `pip install` (confirmed in this research session: `python3 -c "import scenedetect"` succeeds against system site-packages right now). Once `uv sync` creates a project-local `.venv/`, `import enpipe` and its dependencies must resolve from `.venv`, not the stale system install — a developer or the VS Code Python extension pointing at the wrong interpreter would appear to work (system packages mask the issue) while `pip install -e .`/`uv run` correctness silently isn't actually being exercised.
**How to avoid:** After scaffolding, verify `uv run python -c "import enpipe, scenedetect; print(scenedetect.__file__)"` reports a path inside `.venv/`, not `/usr/local/lib/python3.12/...`. Consider whether `.devcontainer/devcontainer.json`'s VS Code interpreter default needs a `python.defaultInterpreterPath` pointing at `.venv/bin/python` (Claude's discretion — not a locked decision, but worth flagging as a likely-needed follow-up edit).

## Code Examples

### TEST-01: pure-logic function tests (no mocking, no subprocess)

```python
# tests/unit/encoding/test_keyframes.py
from enpipe.encoding.keyframes import kf_before, fmt_seek

def test_kf_before_exact_match():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert kf_before(table, 48) == (48, 2.0)

def test_kf_before_between_keyframes():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert kf_before(table, 70) == (48, 2.0)   # last keyframe <= frame

def test_kf_before_first_frame():
    table = [(0, 0.0), (48, 2.0)]
    assert kf_before(table, 0) == (0, 0.0)

def test_fmt_seek_floors_to_millisecond():
    # 2.0009s must floor to 2.000, never round up past the keyframe's real time
    assert fmt_seek(2.0009) == "00:00:02.000"

def test_fmt_seek_hms_rollover():
    assert fmt_seek(3661.5) == "01:01:01.500"
```

```python
# tests/unit/encoding/test_scenes_io.py
import pytest
from enpipe.encoding.scenes_io import read_scenes

def test_read_scenes_parses_frame_ranges(tmp_path):
    p = tmp_path / "video.mkv.scenes"
    p.write_text(
        "scene    0  frames [       0,      48)      0.000s ..      2.000s\n"
        "scene    1  frames [      48,      96)      2.000s ..      4.000s\n"
    )
    assert read_scenes(p) == [(0, 48), (48, 96)]

def test_read_scenes_skips_non_matching_lines_silently(tmp_path):
    p = tmp_path / "video.mkv.scenes"
    p.write_text("some header\nscene 0 frames [0, 48) 0.0s .. 2.0s\ntrailer\n")
    assert read_scenes(p) == [(0, 48)]

def test_read_scenes_dies_on_zero_matches(tmp_path):
    p = tmp_path / "empty.scenes"
    p.write_text("nothing matches here\n")
    with pytest.raises(SystemExit):
        read_scenes(p)
```

### TEST-02: mocked subprocess-boundary tests with `pytest-subprocess`

```python
# tests/subprocess/detection/test_stream.py
import json
from pathlib import Path
from enpipe.detection.config import DetectionConfig
from enpipe.detection.stream import probe_source

def test_probe_source_parses_ffprobe_json(fp):
    payload = json.dumps({
        "streams": [{"width": 1920, "height": 1080, "avg_frame_rate": "24000/1001"}],
        "format": {"duration": "120.5"},
    })
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
         "-show_entries", "format=duration", "-of", "json", "irrelevant.mkv"],
        stdout=payload,
    )
    info = probe_source(Path("irrelevant.mkv"), DetectionConfig())
    assert info.width == 1920 and info.height == 1080

def test_probe_source_raises_on_missing_ffprobe(fp):
    fp.register(["ffprobe", fp.any()], returncode=127)  # simulate not-found-like failure
    # real FileNotFoundError case needs fp.register with an exception, see docs;
    # this illustrates the CalledProcessError path via non-zero returncode + check=True
```

```python
# tests/subprocess/encoding/test_hdr.py
from pathlib import Path
from enpipe.encoding import hdr

def test_detect_hdr_smpte2084_adds_master_display_flags(fp):
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", "hdr.mkv"],
        stdout="smpte2084\n",
    )
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", "%+#1", "-show_frames",
         "-show_entries", "frame=side_data_list", "-of", "default=nw=1", "hdr.mkv"],
        stdout="",
    )
    flags = hdr.detect_hdr(Path("hdr.mkv"))
    assert flags == ["--master-display", "copy", "--max-cll", "copy"]
```

`chunk_command` needs no `fp` fixture at all — call it directly:

```python
# tests/unit/encoding/test_chunk.py
from pathlib import Path
from enpipe.encoding.chunk import chunk_command, parse_metrics

def test_chunk_command_includes_seek_and_trim():
    cmd = chunk_command(Path("in.mkv"), "00:00:02.000", "0:47",
                         Path("out.obu"), hdr_flags=[], metrics=False)
    assert "--seek" in cmd and cmd[cmd.index("--seek") + 1] == "00:00:02.000"
    assert "--trim" in cmd and cmd[cmd.index("--trim") + 1] == "0:47"
    assert "--psnr" not in cmd  # metrics=False

def test_parse_metrics_extracts_ssim_and_psnr():
    output = (
        "SSIM YUV: 0.9999 (40.12), 0.9998 (39.90), 0.9997 (39.50), "
        "All: 0.99985 (38.24), (Frames: 48)\n"
        "PSNR YUV: 45.1, 44.2, 43.9, Avg: 44.8, (Frames: 48)\n"
    )
    m = parse_metrics(output)
    assert m["ssim_all"] == 0.99985 and m["psnr_avg"] == 44.8
```

## State of the Art

| Old Approach (current repo state) | New Approach (this phase) | When Changed | Impact |
|--------------------------------|------------------------|---------------|--------|
| `.devcontainer/post-create.sh` runs `python3 -m pip install --no-warn-script-location "scenedetect[opencv-headless]" numpy` unpinned, at every container rebuild | `uv sync --locked` against a committed `uv.lock` | This phase (PKG-02) | Reproducible installs; rebuild months apart no longer silently pulls a different `scenedetect`/`numpy` version |
| Two standalone top-level scripts with no shared code, run via `python3 legacy/scene_detection.py` | `pip install -e .` / `import enpipe`, no CLI wiring yet | This phase (PKG-02, structural) | Enables everything downstream (Phase 2 EBML isolation, Phase 3 CI, Phase 4 unified CLI) — this phase is purely foundational |
| Zero tests anywhere in the repo | Fast, hardware-free `pytest -m "not hardware"` tier covering pure-logic + mocked-subprocess-boundary functions | This phase (TEST-01/TEST-02) | First automated safety net for the correctness-critical seek/trim/EBML/argv-construction code, ahead of any Phase 2 refactor touching it (matches `PITFALLS.md`'s explicit sequencing recommendation: "test harness... before any refactor phase") |

**Deprecated/outdated by this phase:** the local `run()` wrapper in `encode_scenes.py` (superseded by `shared.proc.run`, though the *legacy file itself is untouched* — only the migrated copy changes).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `scenedetect==0.7` and `numpy==2.5.1` (the versions currently installed in this devcontainer image) are the correct versions to pin per D-02's "whatever currently works" — i.e., this devcontainer's current state reflects what the prior project actually validated against, not a subsequently-drifted state | Standard Stack, `pyproject.toml` | If the devcontainer image was rebuilt/updated since the pipeline was last actually run successfully, pinning "whatever's installed now" could pin a version that was never truly validated. Low risk given `numpy 2.5.1`/`scenedetect 0.7` and the legacy docstring's own "verified against PySceneDetect 0.7" claim agree, but this hasn't been independently cross-checked against a changelog |
| A2 | Installing `uv` via `curl -LsSf https://astral.sh/uv/install.sh \| sh` inside `post-create.sh` (rather than a devcontainer feature) is an acceptable interpretation of D-03's "update post-create.sh" | `pyproject.toml`/post-create.sh section | If the planner/user prefers the devcontainer-feature approach instead, this is a one-line implementation choice to revisit, not a blocking assumption — flagged explicitly as an open alternative in the same section |
| A3 | `probe_fps` (encoding stage) is intentionally *not* in D-11's TEST-02 target list, and this is a deliberate scope decision rather than an oversight | Mechanical Migration Map, Open Questions | If it was an oversight, the fast tier has a coverage gap symmetrical to `probe_source` (detection stage) being explicitly required — low risk since `probe_fps` is simple and its die()-on-failure path is easy to add opportunistically even if not strictly required |

## Open Questions

1. **Should `probe_fps` get a TEST-02 mocked test even though D-11 doesn't name it explicitly?**
   - What we know: D-11 lists `probe_source` (detection) but not `probe_fps` (encoding) — both are structurally identical (ffprobe JSON call, `die()`/exception on failure), and `probe_fps` is the fps source of truth used throughout `run_encode`.
   - What's unclear: whether this was a deliberate scoping choice (keep TEST-02 minimal, matching the 6 named functions exactly) or an oversight in CONTEXT.md's drafting.
   - Recommendation: treat D-11's list as the binding minimum (don't block phase completion on `probe_fps` coverage), but note it as a natural, cheap addition if time permits within this phase — it reuses the exact same `fp.register(["ffprobe", ...])` pattern as `probe_source`'s test with no new technique needed.

2. **Exact byte-identical parity verification mechanics for the encoding stage, given it needs real hardware.**
   - What we know: this research session confirmed `ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`, and `/dev/dri/renderD128` are all present and functional in this devcontainer (see Environment Availability) — so D-14's "sample run" comparison for `run_encode` can genuinely execute against real QSV hardware, not just be simulated.
   - What's unclear: whether the planner should source/create a tiny synthetic test video (e.g., via `ffmpeg -f lavfi`) for this one-time parity check, or require access to a real media file under `/data/media`. A synthetic clip is faster to set up and sufficient for byte-identical-output comparison (the goal is "does the migrated code produce the same bytes as the old code," not "is the encode visually correct" — that's Phase 4's concern).
   - Recommendation: use a short (a few seconds) synthetic source generated with `ffmpeg -f lavfi -i testsrc=duration=10:size=640x360:rate=24 -f lavfi -i sine=duration=10 parity_sample.mkv` (or similar) for both the detection and encoding parity checks — avoids needing real media access for a mechanical-migration acceptance gate.

3. **Does the `pyproject.toml` `[tool.ruff]`/`[tool.pyright]` block get added this phase?**
   - What we know: D-46 (Claude's Discretion) says optional, must not gate.
   - What's unclear: whether adding an empty/minimal config now (with zero enforcement, just so Phase 3 has less setup) is worth the extra `pyproject.toml` surface area in a phase focused on packaging + migration + tests.
   - Recommendation: skip it this phase — keep `pyproject.toml` minimal and focused on D-01/D-02/D-09/D-10's literal requirements; Phase 3 (QUAL-01) can add the config block when it's actually going to be enforced, avoiding a config block that sits unused for two phases.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | Everything | ✓ | 3.12.13 | — |
| `uv` | PKG-02 (D-01/D-03) | **✗** | — | Must be installed via `curl -LsSf https://astral.sh/uv/install.sh \| sh` as part of this phase's `post-create.sh` change — see `pyproject.toml` section |
| `pytest` | TEST-01/TEST-02 | ✓ (system-wide, pre-`uv`) | 9.1.1 | Will be re-provided via `uv`-managed `.venv` after scaffolding; matches the version this research pinned |
| `ffmpeg`/`ffprobe` | Detection/encoding subprocess calls (parity check only — not part of the fast test tier, which mocks these) | ✓ | 7.1.5 | — |
| `qsvencc` | Encoding parity check (D-14) | ✓ | 8.20 (r4231) | — |
| `mkvmerge` | Encoding parity check (D-14, final mux) | ✓ | v92.0 | — |
| `/dev/dri/renderD128` (Intel Arc QSV) | Encoding parity check (D-14) | ✓ | — | — |
| `scenedetect` | Detection stage | ✓ (system-wide, pre-`uv`) | 0.7 | Re-provided via `uv`-managed `.venv` |
| `numpy` | Detection stage (frame buffers) | ✓ (system-wide, pre-`uv`) | 2.5.1 | Re-provided via `uv`-managed `.venv` |

**Missing dependencies with no fallback:** none — `uv` is the only missing piece, and it has a documented, low-risk install path (official installer script) that this phase's own `post-create.sh` change will provide.

**Missing dependencies with fallback:** `uv` itself (see above) — trivial one-line install, not a blocker.

This is a notable, favorable finding: **this devcontainer session already has the full hardware toolchain available** (`ffmpeg`, `qsvencc`, `mkvmerge`, `/dev/dri`), meaning D-14's byte-identical parity verification for the *encoding* stage can be run for real during this phase's execution, not deferred or simulated — the planner should schedule it as a real verification step, not a "best effort" one.

## Security Domain

`security_enforcement` is not set in `.planning/config.json` (absent = enabled per policy), so this section is included for completeness, though most ASVS categories do not apply — `enpipe` is a local, single-user, no-network batch CLI (confirmed by `.planning/codebase/ARCHITECTURE.md`: "Not applicable — this is a local CLI media-processing toolchain with no network service, no auth boundary, and no multi-user concerns"; also `PROJECT.md` Out of Scope: "no network service, auth, or multi-user layer").

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | No | No auth boundary exists or is planned |
| V3 Session Management | No | Not applicable — stateless batch CLI |
| V4 Access Control | No | Not applicable — single local user |
| V5 Input Validation | Partial | Subprocess argv is built from typed values (`Path`, `int`, pre-validated strings), never string-interpolated shell commands — `shell=True` is never used anywhere in `legacy/*.py` (confirmed by grep and by `PITFALLS.md`'s own Security Mistakes table, which explicitly flags this as a positive pattern to preserve through the refactor). This phase's mechanical migration must not introduce `shell=True` or string-formatted command construction as a "convenience" during the move |
| V6 Cryptography | No | Not applicable — no secrets, no crypto operations in this codebase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Command injection via unsanitized filenames/paths passed to subprocess argv | Tampering | Already mitigated in `legacy/*.py` by using argv lists (never shell strings) — preserve this exactly; `shared.proc.run`/`popen` must never gain a `shell=True` default |
| Supply-chain: unpinned dependency install (the actual current-state risk this phase fixes) | Tampering | `uv.lock` + exact-pin `[project.dependencies]` (D-01/D-02) — this *is* the mitigation this phase implements, not a residual risk |
| Supply-chain: package-name typosquatting in newly-added test dependencies (`pytest-subprocess`, `pytest-mock`) | Tampering | Package Legitimacy Audit above — all packages checked via `slopcheck` + live PyPI registry lookup this session, all `OK` |

No other STRIDE categories apply meaningfully to a local, offline, single-user batch CLI with no network listeners.

## Sources

### Primary (HIGH confidence)
- [uv Build Backend docs](https://docs.astral.sh/uv/concepts/build-backend/) — exact `[build-system]` syntax, src-layout auto-discovery, fetched directly this session
- [uv Projects Guide](https://docs.astral.sh/uv/guides/projects/) — `uv add`/`uv sync`/`uv lock` command syntax, fetched directly this session
- [uv Dependencies concepts](https://docs.astral.sh/uv/concepts/projects/dependencies/) — `[dependency-groups]` PEP 735 syntax vs legacy `[tool.uv] dev-dependencies`, fetched directly this session
- [pytest-subprocess usage docs](https://pytest-subprocess.readthedocs.io/en/latest/usage.html) — `fp.register`/`fp.calls`/`recorder.calls[...].kwargs` API, fetched directly this session
- PyPI registry (`python3 -m pip index versions <pkg>`) — live version check for `scenedetect`, `numpy`, `pytest`, `pytest-subprocess`, `pytest-mock`, `pytest-cov`, `hypothesis`, `ruff`, `pyright`, `uv`, `uv_build`, `coverage`, run directly in this session
- `slopcheck` 0.6.1 (`pip install slopcheck`) — package legitimacy scan for all 8 candidate packages, run directly in this session, all `OK`
- `legacy/scene_detection.py`, `legacy/encode_scenes.py` (this repository, full read this session) — primary source for every line number, function signature, and behavior claim in the Mechanical Migration Map
- This devcontainer session's own environment (`command -v`, direct Python `import`, `ls /dev/dri`) — confirms `ffmpeg 7.1.5`, `qsvencc 8.20`, `mkvmerge v92.0`, `/dev/dri/renderD128`, `scenedetect 0.7`, `numpy 2.5.1` are all present; `uv` is confirmed absent

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` (project-level research, this repository) — base stack/architecture/pitfall decisions this document builds on and, in two cases (circular import, `die()` layering), extends with migration-specific detail not present in the source documents

### Tertiary (LOW confidence)
- None — every claim in this document is either grounded in direct source-code reads, live registry/tool checks performed this session, or official documentation fetched this session.

## Metadata

**Confidence breakdown:**
- Standard stack (packaging syntax, version pins): HIGH — verified against live PyPI registry and current `docs.astral.sh` this session, not training-data recall
- Mechanical Migration Map: HIGH — derived from direct line-by-line reads of both `legacy/*.py` files this session, not summarized from memory
- Circular-import / `die()`-layering hazards: HIGH — derived from tracing actual call graphs in the source files; these are new findings not present in project-level research, specific to this phase's implementation
- Pitfalls (reused from project-level `PITFALLS.md`): MEDIUM-HIGH — inherited confidence level from that document, re-scoped to this phase's specific deliverables
- Environment Availability: HIGH — directly probed in this devcontainer session (`command -v`, tool `--version`, `ls /dev/dri`)

**Research date:** 2026-07-08
**Valid until:** ~30 days (stable packaging ecosystem; re-verify PyPI versions if planning is deferred materially past this window, per `STACK.md`'s own note about `uv`'s fast release cadence)
</content>
