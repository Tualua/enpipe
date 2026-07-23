# Roadmap: enpipe

## Milestones

- ✅ **v1.0 Productionization** — Phases 1–4 (shipped 2026-07-08)
- ✅ **v1.1 Single-command pipeline entry point** — Phase 5 (shipped 2026-07-23)
- 🚧 **v1.2 ffmpeg backend** — Phases 6–10 (in progress, started 2026-07-23)

Full phase detail is archived per milestone under `.planning/milestones/`:
- `.planning/milestones/v1.1-ROADMAP.md` (cumulative — captures Phases 1–5, the repo's first milestone archive)
- `.planning/milestones/v1.1-REQUIREMENTS.md`

## Phases

<details>
<summary>✅ v1.0 Productionization (Phases 1–4) — SHIPPED 2026-07-08</summary>

- [x] Phase 1: Package Foundation, Migration & Fast Test Tier (3/3 plans) — completed 2026-07-08
- [x] Phase 2: Correctness-Critical Extraction (2/2 plans) — completed 2026-07-08
- [x] Phase 3: Concurrency Resolution + Regression Baseline + CI (3/3 plans) — completed 2026-07-08
- [x] Phase 4: Unified CLI + Hardware-Gated Real-Media Validation (2/2 plans) — completed 2026-07-08

</details>

<details>
<summary>✅ v1.1 Single-command pipeline entry point (Phase 5) — SHIPPED 2026-07-23</summary>

- [x] Phase 5: Single-Command Pipeline Entry Point (1/1 plan) — completed 2026-07-09

`enpipe run <video>` composes detect → `.scenes` → encode sequentially in one invocation, byte/frame-identical to the manual two-step and to the `legacy/` oracle on real Arc hardware.

</details>

### 🚧 v1.2 ffmpeg backend (Phases 6–10) — IN PROGRESS

Add an ffmpeg `av1_qsv` encode backend (empirically immune to the concurrent-encode silent frame corruption) as the new **default**, retaining `qsvencc` as an opt-in selectable backend. Risk-first ordering: prove the immunity premise, land a behavior-preserving backend seam, ship the SDR default, then HDR10, then the POC-gated DV/HDR10+ decision. `legacy/` stays the frozen parity oracle; the v1.2 correctness basis is **per-frame content parity** (not byte-identity to qsvencc — ICQ-23 ≠ av1_qsv "23").

- [ ] **Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE)** — Rebuild the devcontainer to ffmpeg-8.1 and prove ffmpeg av1_qsv is corruption-free at production+stress JOBS with per-frame content verification, before any backend code exists.
- [ ] **Phase 7: Backend Seam Refactor (zero behavior change)** — Land a `backends/` seam validated byte-identical against the legacy oracle; qsvencc remains the only valid backend.
- [ ] **Phase 8: ffmpeg SDR Backend + Flip Default** — Implement the ffmpeg av1_qsv backend on the SDR path, flip the default to ffmpeg, verify OBU byte-concat + frame-exact seek/trim + keyframe alignment.
- [ ] **Phase 9: HDR10 Static Metadata Through ffmpeg** — Carry HDR10 static metadata + color signaling through the ffmpeg path via mkvmerge container tags + the av1_metadata BSF.
- [ ] **Phase 10: DV / HDR10+ Decision (POC-gated, highest risk, LAST)** — Spike dovi_tool PR #389 AV1 inject-rpu on a real DV fixture and route DV/HDR10+ by the verdict, never a silent downgrade.

## Phase Details

### Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE)
**Goal**: Prove the milestone's load-bearing premise — that ffmpeg `av1_qsv` is corruption-free under concurrent `JOBS` with per-frame content verification — and rebuild the devcontainer to ffmpeg-8.1, before any backend code is written. If the immunity does not hold at production JOBS on this exact kernel, the entire migration premise is invalid and must pivot.
**Depends on**: Nothing (first v1.2 phase; builds on the shipped v1.1 pipeline)
**Requirements**: ENV-01, COR-01
**Success Criteria** (what must be TRUE):
  1. `ffmpeg-8.1`/`ffprobe-8.1` are on PATH inside the rebuilt devcontainer with `av1_qsv` encode plus the `av1_metadata` and `dovi_rpu` BSFs available, confirmed by the post-create self-check.
  2. A concurrent full-file per-frame content sweep (PSNR/VMAF) over ffmpeg `av1_qsv` output shows zero corrupted frames at production JOBS (3) and stress JOBS (5–8).
  3. The corruption triad (HW-decode + P010 10-bit + B-pyramid/`gop-ref-dist`) is asserted present in the encode parameter dump, so a silent SW-decode fallback cannot yield a false "clean."
  4. The same harness reproduces nonzero corruption on the qsvencc path under identical concurrent JOBS (the handed-off reproducer engages), proving the regression test is non-vacuous.
**Plans**: TBD
**Research**: recommended at plan time — concurrency-spike methodology (full-file sweep vs hotspot-only, JOBS thresholds, triad-integrity assertion) per SUMMARY Research Flags.

### Phase 7: Backend Seam Refactor (zero behavior change)
**Goal**: Land a `backends/` seam validated byte-identical against the frozen legacy oracle BEFORE any ffmpeg encode code exists, so Phase 8's new encoder slots into a proven, behavior-preserving structure. qsvencc stays the only valid and default backend at this point.
**Depends on**: Phase 6 (immunity premise must be proven before investing in the migration seam)
**Requirements**: BK-02
**Success Criteria** (what must be TRUE):
  1. Both encode paths route through a `backends/` seam where each backend is a frozen-dataclass value object bundling pure, argv-testable command-builder callables (per the ARCHITECTURE convention).
  2. The qsvencc backend produces byte-identical pre-mux `movie.obu` to the pre-refactor output on real Arc hardware (legacy-oracle parity preserved, zero behavior change).
  3. A `--backend` flag/env scaffold threads a resolved backend object through `run_encode`/`encode_chunk`, with only `qsvencc` accepted as valid until Phase 8 lands ffmpeg.
  4. The exonerated keyframe seek/trim math is exposed as a shared numeric sibling for backends to format, without re-deriving it or disturbing the qsvencc byte-identity path.
**Plans**: TBD

### Phase 8: ffmpeg SDR Backend + Flip Default
**Goal**: Implement the corruption-free ffmpeg `av1_qsv` backend on the simplest (SDR) path — where all the load-bearing invariants live — flip the default to ffmpeg, and verify OBU byte-concat, frame-exact seek/trim, and keyframe alignment as explicit content-verify gates (not count-only checks).
**Depends on**: Phase 7 (needs the behavior-preserving `backends/` seam + shared keyframe math to slot into)
**Requirements**: FF-01, FF-02, FF-03, BK-01
**Success Criteria** (what must be TRUE):
  1. ffmpeg `av1_qsv` encodes a scene chunk to a raw `-f obu` stream reproducing the qsvencc preset (ICQ→`-global_quality`, GOP length, B-pyramid/`gop-ref-dist`, tiling, 10-bit Main); the byte-concatenated `movie.obu` fully decodes to the expected frame count.
  2. Per-chunk seek/trim is frame-exact (keyframe input-seek + frame-indexed trim, never time-based `-ss`/`-t`): first/last decoded frame content-matches source `S`/`E-1`, and per-chunk + total `count_frames` guards pass — including a `first>0` chunk on real media.
  3. `enpipe run`/`enpipe encode` transcodes an SDR source end-to-end on the ffmpeg default backend, producing correct output at full parallel `JOBS`.
  4. `--backend ffmpeg|qsvencc` (and env var) selects the path, the default is `ffmpeg`, the qsvencc `which` preflight is made conditional, and both backends stay tested and verified.
**Plans**: TBD

### Phase 9: HDR10 Static Metadata Through ffmpeg
**Goal**: Carry HDR10 static metadata and color signaling through the ffmpeg path — a solved-but-relocated problem that moves from the encoder to the muxer (`mkvmerge` container tags + the `av1_metadata` BSF) — with an `ffprobe` side-data diff against the source as the acceptance gate.
**Depends on**: Phase 8 (needs the ffmpeg SDR backend as the default path to extend)
**Requirements**: HDR-01
**Success Criteria** (what must be TRUE):
  1. Mastering-display + max-CLL probed from the source are emitted as `mkvmerge` container tags on the final `.mkv`.
  2. Color signaling (primaries/transfer/matrix) is written via the `av1_metadata` BSF on the ffmpeg path.
  3. An `ffprobe` side-data diff of the output against the source shows HDR10 static metadata + color signaling preserved with no silent downgrade on a real HDR10 source.
**Plans**: TBD

### Phase 10: DV / HDR10+ Decision (POC-gated, highest risk, LAST)
**Goal**: Resolve the load-bearing risk PROJECT.md names — DV/HDR10+ passthrough, the whole reason qsvencc was originally chosen. Spike `dovi_tool` PR #389 AV1 `inject-rpu` on a real DV fixture and route the outcome: ffmpeg-native if it validates, else a single-pass whole-file qsvencc encode (the legacy route, no scene splitting — corruption-free by construction). The answer must be KNOWN at milestone close, never a silent downgrade.
**Depends on**: Phase 9 (SDR→HDR→DV ordering; DV is the highest-uncertainty metadata path, deferred last so it cannot block core value delivery)
**Requirements**: HDR-03, HDR-02
**Success Criteria** (what must be TRUE):
  1. A recorded POC verdict on `dovi_tool` PR #389 AV1 `inject-rpu` over an ffmpeg-encoded `.obu` on a real DV fixture: RPU-count == frame-count and correct per-frame display-order alignment through B-pyramid (or a documented failure/unbuildable result).
  2. Routing follows the verdict: if the spike passes, DV/HDR10+ ride the ffmpeg default byte-preserving; if it fails, DV/HDR10+ are encoded via a single-pass whole-file qsvencc job — a distinct encode MODE that bypasses the scene-chunk orchestration (one session → corruption-free by construction), not a flag on the chunk pipeline.
  3. A DV or HDR10+ source under the ffmpeg default is never silently downgraded — the chosen route is explicit and logged, with metadata verified present on the output (`mediainfo`/`ffprobe`).
  4. The verdict and routing decision are recorded in the planning/requirements docs as the milestone-close answer to the load-bearing DV/HDR10+ risk.
**Plans**: TBD
**Research**: recommended at plan time — DV/HDR10+ hardware survival, PR #389 build, `dovi_rpu`/T.35 wrapping, per-chunk RPU slicing + B-reorder alignment, and real-fixture availability (SUMMARY Research Flags; deep dive in `research/DV-RPU-AV1.md`).

## Progress

| Phase                                                 | Milestone | Plans Complete | Status      | Completed  |
| ----------------------------------------------------- | --------- | -------------- | ----------- | ---------- |
| 1. Package Foundation, Migration & Fast Test Tier     | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 2. Correctness-Critical Extraction                    | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 3. Concurrency Resolution + Regression Baseline + CI  | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 4. Unified CLI + Hardware-Gated Real-Media Validation | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 5. Single-Command Pipeline Entry Point                | v1.1      | 1/1            | Complete    | 2026-07-09 |
| 6. Concurrency-Immunity Spike + Image Rebuild (GATE)  | v1.2      | 0/?            | Not started | -          |
| 7. Backend Seam Refactor                              | v1.2      | 0/?            | Not started | -          |
| 8. ffmpeg SDR Backend + Flip Default                  | v1.2      | 0/?            | Not started | -          |
| 9. HDR10 Static Metadata Through ffmpeg               | v1.2      | 0/?            | Not started | -          |
| 10. DV / HDR10+ Decision (POC-gated)                  | v1.2      | 0/?            | Not started | -          |
