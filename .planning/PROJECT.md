# enpipe

## What This Is

`enpipe` is a scene-aware AV1 transcode pipeline for Intel Arc (Quick Sync Video) hardware. It detects scene cuts in a source video, encodes each scene as an independently-seekable AV1 chunk via `qsvencc`, reassembles the chunks in order, and muxes the result with re-encoded/copied audio and preserved HDR10/HDR10+/Dolby Vision metadata into a final `.mkv`. It runs as a local/NAS transcoding toolchain, not a deployed service.

## Core Value

Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

## Current State

**Shipped:** v1.1 Single-command pipeline entry point (2026-07-23).

`enpipe` is now an installable, pinned, tested `src/enpipe/` package with a unified CLI: `enpipe detect`, `enpipe encode`, and the v1.1 headline command `enpipe run <video>` — one command that runs scene detection → `.scenes` → AV1 encode → mux sequentially, byte/frame-identical to the manual two-step and to the frozen `legacy/` oracle. Correctness-critical logic (EBML/Cues parser, seek/trim, high-water-mark ordering) is isolated behind pure, unit-tested functions; a fast hardware-free test tier plus a parallel==sequential regression baseline run in GitHub Actions CI on every push, with a hardware-gated real-Arc tier named out.

**Open correctness debt (deferred at v1.1 close — see STATE.md Deferred Items):** real-media use surfaced a **silent frame-corruption bug** — concurrent `qsvencc` sessions on the Arc A380 can emit isolated frames whose pixels come from a *different* concurrent encode (root cause: iHD/media-driver cross-process 10-bit reference-surface aliasing; frame counts stay correct, so it is silent). This directly threatens the non-negotiable core value and is the leading candidate to drive the next milestone.

**Phase 6 GATE complete (2026-07-23) — v1.2 premise PROVEN:** the milestone's load-bearing gate passed on real Arc A380 hardware — ffmpeg `av1_qsv` is **immune** to the cross-process frame corruption (320 concurrent sessions across JOBS 3/5/8, **0 corrupt frames, 0 failed starts**), while `qsvencc` corrupts in the identical harness (96 frames, control non-vacuous). D-12 verdict = **PROCEED** at full JOBS (no cap). ENV-01 hard-assert self-check landed in the devcontainer; the COR-01 concurrency-immunity harness + hardware-gated pytest are committed. Evidence: `.planning/debug/scene-chunk-frame-mismatch.md` (`## ФАЗА 6 (GATE)`). Documented residual: the gate evidence was captured on a side-loaded ffmpeg 8.1, not a canonical rebuilt image (`06-HUMAN-UAT.md` tracks the clean-rebuild re-confirmation). Phase 7 (backend seam refactor) is cleared to start.

## Current Milestone: v1.2 ffmpeg backend

**Goal:** Eliminate the concurrent-encode silent frame corruption by adding an ffmpeg `av1_qsv` encode backend (empirically immune) as the new default, while retaining `qsvencc` as an opt-in selectable backend — restoring full-speed parallel encoding with correct output.

**Target features:**
- ffmpeg `av1_qsv` encode backend (ffmpeg 8.1), mapping the current qsvencc preset (ICQ/quality, GOP length, `--gop-ref-dist`/B-pyramid, tile config, tune) with equivalent per-chunk seek/trim semantics.
- HDR10 / HDR10+ / Dolby Vision RPU passthrough through the ffmpeg path — via the ffmpeg 8.1 `dovi_rpu` BSF plus master-display/max-cll/dhdr10 signaling — matching qsvencc's current coverage.
- Backend selection: ffmpeg `av1_qsv` default, `qsvencc` opt-in behind a flag/env var; both fully supported and tested.
- Concurrent-encode correctness proof: a regression test with per-frame content verification demonstrating the ffmpeg backend is corruption-free under parallel `JOBS` (using the handed-off reproducer), kept distinct from the qsvencc path.
- Preserve the correctness invariants (per-chunk + total frame counts, keyframe alignment) across both backends.

**Key context:** Direct sequel to the v1.1 close audit's open debt — qsvencc concurrent-encode frame corruption (root cause: iHD/i915 cross-process 10-bit reference-surface aliasing; ffmpeg `av1_qsv` empirically immune, 35/35 clean). ffmpeg 8.1 is already staged in the devcontainer (quick task 260723-36w) specifically for `av1_qsv` + `dovi_rpu`. Full analysis: `.planning/debug/scene-chunk-frame-mismatch.md` and `HANDOFF-qsvencc-frame-corruption.md`. The DV/HDR10+ passthrough through ffmpeg is the load-bearing risk — the whole reason qsvencc was chosen originally.

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

<!-- v1.2 ffmpeg backend — dual-backend, ffmpeg av1_qsv default (corruption-free), qsvencc opt-in. Detailed REQ-IDs in REQUIREMENTS.md. -->

- [ ] ffmpeg `av1_qsv` encode backend (default) reproducing the qsvencc preset + per-chunk seek/trim, corruption-free under parallel `JOBS`
- [ ] HDR10 / HDR10+ / Dolby Vision RPU passthrough through the ffmpeg path (parity with qsvencc), via ffmpeg 8.1 `dovi_rpu` BSF
- [ ] Selectable backend (ffmpeg default, qsvencc opt-in) with both paths tested and frame-count/keyframe invariants preserved
- [ ] Concurrent-encode correctness regression test (per-frame content verification) proving the ffmpeg backend is corruption-free

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
*Last updated: 2026-07-23 — Phase 6 (concurrency-immunity GATE) complete; v1.2 ffmpeg-migration premise proven (av1_qsv immune, D-12 PROCEED)*
