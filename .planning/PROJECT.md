# enpipe

## What This Is

`enpipe` is a scene-aware AV1 transcode pipeline for Intel Arc (Quick Sync Video) hardware. It detects scene cuts in a source video, encodes each scene as an independently-seekable AV1 chunk via `qsvencc`, reassembles the chunks in order, and muxes the result with re-encoded/copied audio and preserved HDR10/HDR10+/Dolby Vision metadata into a final `.mkv`. It runs as a local/NAS transcoding toolchain, not a deployed service.

## Core Value

Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

## Current State

**Shipped:** v1.2 Concurrent-encode correctness (2026-10-04). Previous: v1.1 Single-command pipeline entry point (2026-07-23), v1.0 Productionization (2026-07-08).

`enpipe` is an installable, pinned, tested `src/enpipe/` package with a unified CLI (`enpipe detect`, `enpipe encode`, `enpipe run <video>`), byte/frame-identical to the frozen `legacy/` oracle. Parallel chunk encoding is **correct again at full JOBS**: the silent cross-session frame corruption in concurrent `qsvencc` was fixed upstream (rigaya/QSVEnc `45003f1`, issue #308, co-authored by the project owner), and enpipe now:

- pins qsvencc to the Tualua/QSVEnc fork release **8.32+vppsync7 (r4665)** in both images — upstream 8.32 + `45003f1` + fixes for the metrics VPP sync, the silent flush frame drop, `--seek` landing in the next GOP (vppsync6) and open-GOP `--trim` offset (vppsync7);
- fails fast (`QSVENCC_MIN_REV = 4665`) on any older qsvencc in `enpipe encode`/`run` and in the post-create self-check;
- locks correctness with a hardware-gated COR-02 regression test: byte identity (sha256) against an isolated reference, packets == decoded == scene frames, the HW-decode + P010 + B-pyramid triad checked on every session, both metrics variants. A380 evidence: 640-session stress matrix, 0 mismatches; non-vacuity proven on r4604.

Both images ship BtbN static **ffmpeg n9.0.2** (URL+sha256 pinned); the runtime image is ubuntu:24.04 + Intel PPA with OpenCL (`--psnr/--ssim` reliable). ffmpeg `av1_qsv` is a proven corruption-free alternative (Phase 6 gate; re-confirmed 2026-10-04 on ffmpeg 9: 320 sessions, 0 corrupt) parked as backlog 999.1.

## Next Milestone Goals

Not yet defined — start with `/gsd:new-milestone`. Candidates from the backlog:
- 999.6 — sources with non-zero `start_time` (MPEG-TS/m2ts)
- 999.5 — Dolby Vision profile 5 → HDR10 via libplacebo
- 999.4 — return to an official qsvencc release once it carries the fork's fixes
- 999.3 — qsvencc version gate in `legacy/encode_scenes.py`
- 999.1 — ffmpeg `av1_qsv` backend (parked; planning artifacts preserved)

## Requirements

### Validated

<!-- v1.2 — shipped and verified. -->

- ✓ Devcontainer + runtime image ship a qsvencc containing `45003f1` (now r4665), revision asserted by the self-check — v1.2 (QSV-01)
- ✓ `enpipe encode`/`run` fail fast on a qsvencc older than the fix — v1.2 (QSV-02)
- ✓ Hardware-gated regression lock: fixed qsvencc has 0 corrupted frames at production+stress JOBS (byte identity, triad on every session, both metrics variants) — v1.2 (COR-02, hardened in Phase 8)
- ✓ ffmpeg `av1_qsv` proven corruption-free under concurrent JOBS with per-frame verification (evidence base for backlog 999.1) — v1.2 (COR-01)
- ✓ Devcontainer ffmpeg self-check (av1_qsv, av1_metadata, dovi_rpu for AV1) — v1.2 (ENV-01; adjusted from ffmpeg 8.1 to n9.0.2)

<!-- v1.1 — shipped and verified. -->

- ✓ `enpipe run <video>` transcodes a file end-to-end in one command (detect → `.scenes` → encode, sequential), detect/encode options passed through, byte/frame-identical to the manual two-step on real Arc — v1.1 (RUN-01..RUN-04)

<!-- v1.0 (Productionization) — shipped and verified. -->

- ✓ Installable `uv`/`uv_build` package with pinned lockfile; `import enpipe` / `pip install -e .` work — v1.0 (PKG-02)
- ✓ Both stages migrated into `src/enpipe/{detection,encoding,shared}` behind a single `shared.proc` subprocess seam, byte-identical to `legacy/` (the parity oracle) — v1.0
- ✓ EBML/Cues parser isolated into a pure `enpipe.mkv.ebml` module; seek/trim + high-water-mark extracted into pure, unit-tested functions — v1.0 (DEBT-01, DEBT-02)
- ✓ Fast test tier (pure-logic + mocked-subprocess) + parallel==sequential regression test; ThreadPool-vs-ProcessPool resolved by profiling (kept threads) — v1.0 (TEST-01/02/03, DEBT-03)
- ✓ GitHub Actions CI (ruff + `pytest -m "not hardware"` on push) with the hardware tier named-out; `dovi_tool` documented — v1.0 (CI-01, DEBT-04)
- ✓ Unified `enpipe detect` / `enpipe encode` CLI (`[project.scripts]`); hardware-gated real-media validation on real Arc (SDR/HDR10/legacy-parity), HDR10+/DV fixture-gated — v1.0 (PKG-01, TEST-04)

<!-- Pre-existing behavior inherited from legacy/, validated through the v1.0 migration. -->

- ✓ Scene detection via ffmpeg QSV decode/downscale → PySceneDetect `AdaptiveDetector`, emitting an ordered `List[Scene]` written to a `<video>.scenes` text log
- ✓ Parallel segmented scene detection (`jobs`), splitting at real detected cut boundaries and stitching per-segment results
- ✓ Scene-aware AV1 chunked encoding via `qsvencc`, each chunk seeked to the nearest source keyframe (mkv Cues fast path + ffprobe fallback)
- ✓ Ordered "high-water mark" reassembly of out-of-order parallel chunk completions into a bit-exact concatenated `movie.obu`
- ✓ HDR10 / HDR10+ / Dolby Vision detection and per-chunk RPU handling (`qsvencc --dolby-vision-rpu copy`)
- ✓ Parallel audio encode (lossless→FLAC, other→Opus, already-target→copy) on a background thread
- ✓ Per-scene + frame-weighted SSIM/PSNR/size metrics CSV
- ✓ Final mux via `mkvmerge` (video + audio + source subs/chapters/attachments) with frame-count verification guards
- ✓ Reproducible Intel Arc QSV dev/runtime environment (devcontainer + runtime image, `/dev/dri` passthrough)

### Active

<!-- Empty between milestones — defined by /gsd:new-milestone. -->

(none — next milestone not yet defined)

### Out of Scope

<!-- Explicit boundaries with reasoning to prevent re-adding. -->

- **Overlapped / streaming orchestrator** (in-process `queue.Queue` producer/consumer running detect + encode *concurrently*) — `PIPELINE_DESIGN.md`'s own verdict is "do not build" on current spinning-disk ZFS + Arc A380 hardware: Amdahl ceiling ~10–18%, erased by disk seek contention (realistic −5% to ~0%). Deferred until the source moves to SSD/NVMe. The v1.1 `enpipe run` command is the *sequential* wrapper, distinct from this.
- Rewriting the core detect/encode algorithms or seek/trim math — the correctness-by-construction invariants (keyframe-aligned chunks, DV RPU survives `cat`) are load-bearing; productionization must preserve them, not re-derive them.
- A non-QSV / software AV1 encode path — the toolchain is deliberately coupled to Intel Arc QSV. (ffmpeg `av1_qsv` is still QSV and remains a parked option, backlog 999.1.)
- Any network service, auth, or multi-user layer — this is a local/NAS CLI toolchain by design.
- Migrating the default encoder to ffmpeg `av1_qsv` *as a corruption fix* — invalidated in v1.2: the corruption was fixed in qsvencc itself, and qsvencc keeps DV/HDR10+ handling intact.

## Context

- **Current codebase:** `src/enpipe/{detection,encoding,shared,mkv,cli}` — installable `uv`/`uv_build` package with a pinned `uv.lock`, a `shared.proc` subprocess seam, a fast hardware-free test tier (218+ unit tests), a hardware-gated real-Arc tier (real-media, concurrency lock, stress matrix), and GitHub Actions CI. `legacy/` remains unmodified as the byte-identical parity oracle.
- **Upstream dependency model:** qsvencc fixes are developed by the project owner in the Tualua/QSVEnc fork and handed off from enpipe via `.planning/debug/HANDOFF-*.md`; enpipe refuses older builds loudly until a fix lands, then raises `QSVENCC_MIN_REV`.
- **Known open items (carried):** devcontainer `/data` bind-mount permission debug (`keep-groups` fix applied; not re-verified as the `vscode` user) and two Phase-03 `human_needed` UAT/verification markers from v1.0. See STATE.md Deferred Items.
- **Design doc:** `PIPELINE_DESIGN.md` (Russian) — completed analysis concluding to keep the sequential `detect jobs=4 → encode jobs=4` workflow on current hardware.

## Constraints

- **Tech stack**: Python 3.12; external binaries `ffmpeg`/`ffprobe`, `qsvencc` (Rigaya QSVEnc), `mkvmerge` invoked via `subprocess` — no persistent daemon. Must stay compatible with existing behavior.
- **Hardware**: Intel Arc GPU (Alchemist, e.g. A380) with QSV/VA-API (`iHD` driver) and `/dev/dri` passthrough required; reference storage is a spinning-disk ZFS pool.
- **Environment**: Development and runtime happen inside the `.devcontainer/` (Docker/Podman); Ubuntu 24.04 (devcontainer: intel/dlstreamer base; runtime image: ubuntu:24.04 + Intel graphics PPA) — qsvencc .deb needs glibc ≥ 2.39; intel-opencl-icd from the PPA enables --psnr/--ssim.
- **Correctness**: Frame-count verification and keyframe-alignment invariants must be preserved through any refactor — silent output corruption is the primary risk.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Productionize the existing sequential pipeline; do not build the streaming orchestrator | `PIPELINE_DESIGN.md` verdict: no meaningful gain on spinning-disk hardware, tail risk of regression; orchestrator gated on SSD/NVMe | — Pending (hardware unchanged) |
| Keep sequential `detect jobs=4 → encode jobs=4` as the production path | Proven faster than jobs=3 encode; sequential detect warms ZFS ARC so encode reads from RAM | — Pending |
| Preserve existing correctness invariants rather than rewrite core algorithms | Keyframe-alignment and DV RPU handling are load-bearing and hard to re-derive safely | ✓ Good — v1.0 shipped byte-identical to legacy oracle |
| v1.1: `enpipe run` is a SEQUENTIAL one-command wrapper, not the overlapped orchestrator | Single-command UX at zero regression risk, reusing verified stages | ✓ Good — byte/frame-identical to the manual two-step on real Arc |
| Acknowledge (not resolve) the concurrent-`qsvencc` frame-corruption bug at v1.1 close | v1.1's scope was complete; the corruption deserved its own milestone | ✓ Good — resolved by v1.2 |
| v1.2: gate the ffmpeg migration on a hardware concurrency-immunity spike (Phase 6) before writing backend code | The migration premise (ffmpeg immune) had to be proven first | ✓ Good — premise proven; harness reused as the qsvencc lock |
| v1.2 re-scope (2026-10-02): adopt fixed qsvencc instead of migrating to ffmpeg `av1_qsv`; park ffmpeg as 999.1 | Root cause found and fixed in qsvencc (45003f1); keeps DV/HDR10+ path untouched | ✓ Good — corruption eliminated with no encoder change |
| Fail closed on old qsvencc (runtime gate + self-check) rather than warn | Silent corruption is the primary risk; a stale binary must never encode | ✓ Good — threshold raised r4634 → r4658 → r4663 → r4665 as fixes landed |
| Pin qsvencc to the Tualua fork until an official release carries the fixes | Upstream release lags; fixes (metrics sync, flush drop, seek, open-GOP trim) needed now | ⚠️ Revisit — return to official release (backlog 999.4) |
| Byte identity (sha256 vs isolated reference) as the lock criterion instead of PSNR threshold | Hardware encode proved deterministic; PSNR ≥ 30 dB missed partial corruption | ✓ Good — 640 sessions, 0 mismatches; r4604 still caught |
| ffmpeg 9 (BtbN n9.0.2 static, pinned URL+sha256) as the primary ffmpeg in both images | dovi_rpu for AV1, av1_qsv; one pinned binary for dev and runtime | ✓ Good — ENV-01 and COR-01 re-verified on it 2026-10-04 |

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
*Last updated: 2026-10-04 after v1.2 milestone*
