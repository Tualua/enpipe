# enpipe

## What This Is

`enpipe` is a scene-aware AV1 transcode pipeline for Intel Arc (Quick Sync Video) hardware. It detects scene cuts in a source video, encodes each scene as an independently-seekable AV1 chunk via `qsvencc`, reassembles the chunks in order, and muxes the result with re-encoded/copied audio and preserved HDR10/HDR10+/Dolby Vision metadata into a final `.mkv`. It runs as a local/NAS transcoding toolchain, not a deployed service.

## Core Value

Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

## Current State

**Shipped:** v1.1 Single-command pipeline entry point (2026-07-23).

`enpipe` is now an installable, pinned, tested `src/enpipe/` package with a unified CLI: `enpipe detect`, `enpipe encode`, and the v1.1 headline command `enpipe run <video>` — one command that runs scene detection → `.scenes` → AV1 encode → mux sequentially, byte/frame-identical to the manual two-step and to the frozen `legacy/` oracle. Correctness-critical logic (EBML/Cues parser, seek/trim, high-water-mark ordering) is isolated behind pure, unit-tested functions; a fast hardware-free test tier plus a parallel==sequential regression baseline run in GitHub Actions CI on every push, with a hardware-gated real-Arc tier named out.

**Open correctness debt (deferred at v1.1 close — see STATE.md Deferred Items):** real-media use surfaced a **silent frame-corruption bug** — concurrent `qsvencc` sessions on the Arc A380 can emit isolated frames whose pixels come from a *different* concurrent encode (root cause: iHD/media-driver cross-process 10-bit reference-surface aliasing; frame counts stay correct, so it is silent). This directly threatens the non-negotiable core value and is the leading candidate to drive the next milestone.

## Next Milestone Goals

Not yet scoped. The dominant candidate is **encode-correctness hardening**: eliminate the concurrent-`qsvencc` cross-process frame corruption (e.g. serialize/cap encode concurrency, or an `av1_qsv`-based single-process path) and add a VMAF/per-frame corruption guard so the failure can never again ship silently. Secondary candidates: the deferred v2 observability (OBS-01) and typed-config (CFG-01) items. Run `/gsd:new-milestone` to scope.

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

<!-- Next milestone not yet scoped. Leading candidate: encode-correctness hardening (concurrent-qsvencc frame corruption). See Current State / Next Milestone Goals. -->

- (none — run `/gsd:new-milestone` to define the next milestone's requirements)

### Validated

<!-- v1.1 — shipped and verified. -->

- ✓ `enpipe run <video>` transcodes a file end-to-end in one command (detect → `.scenes` → encode, sequential), detect/encode options passed through, byte/frame-identical to the manual two-step on real Arc — v1.1 (RUN-01..RUN-04)

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

- **Current codebase:** The productionized code lives in `src/enpipe/{detection,encoding,shared,mkv,cli}` — an installable `uv`/`uv_build` package with a pinned `uv.lock` (scenedetect==0.7, numpy==2.5.1), a `shared.proc` subprocess seam, a fast hardware-free test tier plus a hardware-gated real-Arc tier, and GitHub Actions CI. `legacy/scene_detection.py` / `legacy/encode_scenes.py` remain in place, unmodified, as the byte-identical parity oracle. See `.planning/codebase/` for the original map.
- **Verification state:** No longer "unverified against real media" — v1.0/v1.1 were hardware-validated end-to-end on a real Intel Arc A380 (SDR/HDR10 live; HDR10+/DV fixture-gated), with per-chunk/total frame counts, keyframe alignment, and legacy-oracle parity all checked.
- **Open correctness debt:** real-media use surfaced concurrent-`qsvencc` cross-process frame corruption on the Arc A380 (silent single-frame swaps; root cause is iHD/media-driver 10-bit reference-surface aliasing). Tracked in `.planning/debug/{scene-chunk-frame-mismatch,qsvenc-upstream-issue}.md`, deferred at v1.1 close (STATE.md Deferred Items). Also open: a devcontainer `/data` bind-mount permission issue (fix pending host rebuild) and two `human_needed` Phase-03 UAT/verification markers.
- **Resolved debt (v1.0):** dependencies are pinned+locked; the 130-line hand-rolled EBML parser is isolated into a pure `enpipe.mkv.ebml` module; the ThreadPool-vs-ProcessPool inconsistency was resolved by profiling (kept threads, comment corrected with measured numbers); `dovi_tool` retention is documented.
- **Design doc:** `PIPELINE_DESIGN.md` (Russian) is a completed engineering analysis of a streaming-pipeline redesign whose conclusion is to keep the sequential `detect jobs=4 → encode jobs=4` workflow on current hardware. It is a baseline/decision document, not a spec for work to build now.

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
| v1.1: `enpipe run` is a SEQUENTIAL one-command wrapper (detect→.scenes→encode), not the overlapped orchestrator | Delivers the single-command UX users want at zero regression risk, reusing the verified v1.0 stages; matches PIPELINE_DESIGN.md's recommended sequential path | ✓ Good — v1.1 shipped byte/frame-identical to the manual two-step on real Arc |
| Acknowledge (not resolve) the concurrent-`qsvencc` frame-corruption bug at v1.1 close | v1.1's own scope (the `run` wrapper) is complete; the corruption is a pre-existing hardware/driver-level defect discovered post-Phase-5, best scoped as its own milestone | ⚠️ Revisit — deferred to next milestone; silent-corruption risk to the core value until fixed |

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
*Last updated: 2026-07-23 after v1.1 milestone*
