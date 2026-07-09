# enpipe

## What This Is

`enpipe` is a scene-aware AV1 transcode pipeline for Intel Arc (Quick Sync Video) hardware. It detects scene cuts in a source video, encodes each scene as an independently-seekable AV1 chunk via `qsvencc`, reassembles the chunks in order, and muxes the result with re-encoded/copied audio and preserved HDR10/HDR10+/Dolby Vision metadata into a final `.mkv`. It runs as a local/NAS transcoding toolchain, not a deployed service.

## Core Value

Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

## Current Milestone: v1.1 Single-command pipeline entry point

**Goal:** Give the user one command — `enpipe run <video>` — that runs scene detection then encoding **sequentially** in a single invocation and produces the final `.mkv`, so no manual two-step `detect` → `encode` orchestration is required.

**Target features:**
- `enpipe run <video>` executes `run_detect` → writes the `<video>.scenes` intermediate → `run_encode`, in sequence (no overlap), producing the final output.
- Relevant detect + encode options pass through to the correct stage; the result is identical to running `enpipe detect` then `enpipe encode` by hand.
- The existing two-stage `enpipe detect` / `enpipe encode` commands remain available and unchanged.

**Key context:** This is the sequential `detect jobs=4 → encode jobs=4` workflow `PIPELINE_DESIGN.md` recommends — a thin convenience wrapper over the already-verified v1.0 stages, NOT the overlapped/streaming orchestrator (which remains out of scope on current hardware).

## Requirements

### Validated

<!-- Inferred from existing legacy/ code — working per in-code documentation, though not yet run against real media (see Context). -->

- ✓ Scene detection via ffmpeg QSV decode/downscale → PySceneDetect `AdaptiveDetector`, emitting an ordered `List[Scene]` written to a `<video>.scenes` text log — existing (`legacy/scene_detection.py`)
- ✓ Parallel segmented scene detection (`jobs`), splitting at real detected cut boundaries and stitching per-segment results — existing (`legacy/scene_detection.py`)
- ✓ Scene-aware AV1 chunked encoding via `qsvencc`, each chunk seeked to the nearest source keyframe (mkv Cues fast path + ffprobe fallback) — existing (`legacy/encode_scenes.py`)
- ✓ Ordered "high-water mark" reassembly of out-of-order parallel chunk completions into a bit-exact concatenated `movie.obu` — existing (`legacy/encode_scenes.py`)
- ✓ HDR10 / HDR10+ / Dolby Vision detection and per-chunk RPU handling (`qsvencc --dolby-vision-rpu copy`) — existing (`legacy/encode_scenes.py`)
- ✓ Parallel audio encode (lossless→FLAC, other→Opus, already-target→copy) on a background thread — existing (`legacy/encode_scenes.py`)
- ✓ Per-scene + frame-weighted SSIM/PSNR/size metrics CSV — existing (`legacy/encode_scenes.py`)
- ✓ Final mux via `mkvmerge` (video + audio + source subs/chapters/attachments) with frame-count verification guards — existing (`legacy/encode_scenes.py`)
- ✓ Reproducible Intel Arc QSV dev/runtime environment (devcontainer: ffmpeg QSV, qsvencc, iHD driver, `/dev/dri` passthrough) — existing (`.devcontainer/`)

### Active

<!-- v1.1 milestone: the single-command sequential pipeline wrapper. -->

- [ ] `enpipe run <video>` transcodes a file end-to-end in one command (detect → `.scenes` → encode, sequential), with detect/encode options passed through and output identical to the manual two-step run

### Validated

<!-- v1.0 (Productionization) — shipped and verified. -->

- ✓ Installable `uv`/`uv_build` package with pinned lockfile; `import enpipe` / `pip install -e .` work — v1.0 (PKG-02)
- ✓ Both stages migrated into `src/enpipe/{detection,encoding,shared}` behind a single `shared.proc` subprocess seam, byte-identical to `legacy/` (the parity oracle) — v1.0
- ✓ EBML/Cues parser isolated into a pure `enpipe.mkv.ebml` module; seek/trim + high-water-mark extracted into pure, unit-tested functions — v1.0 (DEBT-01, DEBT-02)
- ✓ Fast test tier (pure-logic + mocked-subprocess) + parallel==sequential regression test; ThreadPool-vs-ProcessPool resolved by profiling (kept threads) — v1.0 (TEST-01/02/03, DEBT-03)
- ✓ GitHub Actions CI (ruff + `pytest -m "not hardware"` on push) with the hardware tier named-out; `dovi_tool` documented — v1.0 (CI-01, DEBT-04)
- ✓ Unified `enpipe detect` / `enpipe encode` CLI (`[project.scripts]`); hardware-gated real-media validation on real Arc (SDR/HDR10/legacy-parity), HDR10+/DV fixture-gated — v1.0 (PKG-01, TEST-04)

### Out of Scope

<!-- Explicit boundaries with reasoning to prevent re-adding. -->

- **Overlapped / streaming orchestrator** (in-process `queue.Queue` producer/consumer running detect + encode *concurrently*) — `PIPELINE_DESIGN.md`'s own verdict is "do not build" on current spinning-disk ZFS + Arc A380 hardware: Amdahl ceiling ~10–18%, erased by disk seek contention (realistic −5% to ~0%). Deferred until the source moves to SSD/NVMe. NOTE: the v1.1 `enpipe run` command is the *sequential* (non-overlapped) single-command wrapper, which IS in scope and is distinct from this.
- Rewriting the core detect/encode algorithms or seek/trim math — the correctness-by-construction invariants (keyframe-aligned chunks, DV RPU survives `cat`) are load-bearing; productionization must preserve them, not re-derive them.
- A non-QSV / alternative-encoder AV1 path — the toolchain is deliberately coupled to Intel Arc QSV; a software-encode fallback is not a goal.
- Any network service, auth, or multi-user layer — this is a local/NAS CLI toolchain by design.

## Context

- **Prior work:** The working code lives in `legacy/scene_detection.py` and `legacy/encode_scenes.py` — two standalone `argparse` CLI scripts connected only by the `<video>.scenes` intermediate file. There is no shared library, no package structure, and no test suite. See `.planning/codebase/` for the full map.
- **Verification state:** `legacy/scene_detection.py`'s docstring states outright it has not been run against real video ("ждёт интеграционного теста на NAS"). The code is written with production-level defensiveness (error handling, edge cases, frame-count guards) but is unverified against real media.
- **Design doc:** `PIPELINE_DESIGN.md` (Russian) is a completed engineering analysis of a streaming-pipeline redesign whose conclusion is to keep the sequential `detect jobs=4 → encode jobs=4` workflow on current hardware. It is a baseline/decision document, not a spec for work to build now.
- **Known debt:** unpinned dependencies; 130+ lines of hand-rolled EBML parsing embedded in the encode script; a latent ThreadPool-vs-ProcessPool inconsistency in parallel detection; `dovi_tool` installed in the devcontainer but unused by any script.

## Constraints

- **Tech stack**: Python 3.12; external binaries `ffmpeg`/`ffprobe`, `qsvencc` (Rigaya QSVEnc), `mkvmerge` invoked via `subprocess` — no persistent daemon. Must stay compatible with existing behavior.
- **Hardware**: Intel Arc GPU (Alchemist, e.g. A380) with QSV/VA-API (`iHD` driver) and `/dev/dri` passthrough required; reference storage is a spinning-disk ZFS pool.
- **Environment**: Development and runtime happen inside the `.devcontainer/` (Docker/Podman); Debian 13 "trixie" is required for `qsvencc`'s glibc ≥ 2.39.
- **Correctness**: Frame-count verification and keyframe-alignment invariants must be preserved through any refactor — silent output corruption is the primary risk.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Productionize the existing sequential pipeline; do not build the streaming orchestrator | `PIPELINE_DESIGN.md` verdict: no meaningful gain on spinning-disk hardware, tail risk of regression; orchestrator gated on SSD/NVMe | — Pending |
| Keep sequential `detect jobs=4 → encode jobs=4` as the production path | Proven faster than jobs=3 encode; sequential detect warms ZFS ARC so encode reads from RAM | — Pending |
| Preserve existing correctness invariants rather than rewrite core algorithms | Keyframe-alignment and DV RPU handling are load-bearing and hard to re-derive safely | ✓ Good — v1.0 shipped byte-identical to legacy oracle |
| v1.1: `enpipe run` is a SEQUENTIAL one-command wrapper (detect→.scenes→encode), not the overlapped orchestrator | Delivers the single-command UX users want at zero regression risk, reusing the verified v1.0 stages; matches PIPELINE_DESIGN.md's recommended sequential path | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-09 — started milestone v1.1 (single-command pipeline entry point) after v1.0 complete*
