# Roadmap: enpipe

## Milestones

- ✅ **v1.0 Productionization** — Phases 1–4 (shipped 2026-07-08)
- ✅ **v1.1 Single-command pipeline entry point** — Phase 5 (shipped 2026-07-23)
- 🚧 **v1.2 Concurrent-encode correctness** — Phases 6–7 (in progress, started 2026-07-23; re-scoped 2026-10-02)

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

### 🚧 v1.2 Concurrent-encode correctness (Phases 6–7) — IN PROGRESS

Eliminate the concurrent-encode silent frame corruption. **Re-scoped 2026-10-02:** the corruption was fixed upstream in rigaya/QSVEnc (`45003f1`, issue #308 — missing sync of the MFX VPP output before encoder submit with VA memory; verified on our Arc A380). The ffmpeg `av1_qsv` migration (former Phases 7–10) is parked as backlog item 999.1; v1.2 now adopts the fixed qsvencc and locks it in with a regression test. `legacy/` stays the frozen parity oracle.

- [x] **Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE)** — Rebuild the devcontainer to ffmpeg-8.1 and prove ffmpeg av1_qsv is corruption-free at production+stress JOBS with per-frame content verification, before any backend code exists. (completed 2026-07-23)
- [ ] **Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock** — Ship qsvencc ≥ `45003f1` in the devcontainer, fail fast on older builds, and prove 0 corrupt frames at production+stress JOBS with the corruption triad active.

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
**Plans**: 3 plans
- [x] 06-01-PLAN.md — ENV-01: hard-assert ffmpeg-8.1 + av1_qsv + av1_metadata/dovi_rpu BSFs in post-create.sh, verified on the rebuilt image (SC#1)
- [x] 06-02-PLAN.md — COR-01: author the concurrency-immunity harness + committed hardware-gated pytest + one-time stress-matrix script (per-frame PSNR sweep, triad assert, qsvencc control)
- [x] 06-03-PLAN.md — COR-01/gate proof: lock the HW-decode triad regex, run the pytest + stress matrix on hardware, apply the D-12 tiered verdict, record D-09 evidence (SC#2/#3/#4)
**Research**: recommended at plan time — concurrency-spike methodology (full-file sweep vs hotspot-only, JOBS thresholds, triad-integrity assertion) per SUMMARY Research Flags.

### Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock
**Goal**: Replace the corrupting qsvencc build with one containing the upstream fix (rigaya/QSVEnc `45003f1`) and turn the Phase 6 harness's qsvencc *control* into a regression lock, so the concurrent-encode corruption cannot silently return with a qsvencc downgrade or a driver/runtime change.
**Depends on**: Phase 6 (reuses the COR-01 concurrency-immunity harness + Cold Eyes reproducer)
**Requirements**: QSV-01, QSV-02, COR-02
**Success Criteria** (what must be TRUE):
  1. The devcontainer installs a qsvencc build that contains `45003f1` (source build until an upstream release ships it, then a pinned release), and the post-create self-check asserts the revision.
  2. `enpipe encode`/`enpipe run` refuse (fail fast, explicit Russian error) to run on a qsvencc build older than the fix.
  3. A hardware-gated regression test runs qsvencc at production and stress JOBS with the HW-decode + P010 + B-pyramid triad asserted active and finds 0 corrupt frames by per-frame content verification (the former "qsvencc control corrupts" expectation is inverted).
  4. The corruption debug sessions and PROJECT.md open-debt entry are closed with the upstream fix as the recorded resolution.
**Plans**: 5 plans
- [x] 07-01-PLAN.md — QSV-01: mirror the r4634 (45003f1) nightly .deb as Release asset deps-qsvencc-r4634 (human checkpoint, deadline 2026-10-15) + anonymous sha256/revision verification
- [x] 07-02-PLAN.md — QSV-02: fail-closed revision gate (shared/qsvencc_version.py) wired into run_encode/run_pipeline + autouse test stub; `--backend qsv` in chunk_command
- [x] 07-03-PLAN.md — QSV-01: pin both Dockerfiles to the sha256-verified mirror + build-time revision check; post-create QSV-01 hard-assert; D-06 todo; host build checkpoint
- [x] 07-04-PLAN.md — COR-02: invert the qsvencc control into a regression lock (production argv, ANSI-safe qsvencc triad, fail-not-skip); stress/non-vacuity runner
- [ ] 07-05-PLAN.md — COR-02 gate on hardware: D-16 non-vacuity on r4604, lock + stress matrix on r4634, D-18 regression checks, D-19 debt closure

## Progress

| Phase                                                 | Milestone | Plans Complete | Status      | Completed  |
| ----------------------------------------------------- | --------- | -------------- | ----------- | ---------- |
| 1. Package Foundation, Migration & Fast Test Tier     | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 2. Correctness-Critical Extraction                    | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 3. Concurrency Resolution + Regression Baseline + CI  | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 4. Unified CLI + Hardware-Gated Real-Media Validation | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 5. Single-Command Pipeline Entry Point                | v1.1      | 1/1            | Complete    | 2026-07-09 |
| 6. Concurrency-Immunity Spike + Image Rebuild (GATE)  | v1.2      | 3/3 | Complete   | 2026-07-23 |
| 7. Adopt Fixed qsvencc + Regression Lock              | v1.2      | 4/5 | In Progress|  |

## Backlog

### Phase 999.1: ffmpeg av1_qsv backend (BACKLOG)

**Goal:** [Captured for future planning] Бывшие фазы 7–10 v1.2: слой `backends/` без изменения поведения, ffmpeg `av1_qsv` для SDR, HDR10 через ffmpeg, решение по DV/HDR10+. Отложено 2026-10-02: тихая порча кадров qsvencc при параллельном кодировании исправлена в апстриме (rigaya/QSVEnc `45003f1`, issue #308) и проверена на Arc A380, поэтому главного довода за переход на ffmpeg больше нет. Артефакты планирования бывшей фазы 7 (CONTEXT/RESEARCH/PATTERNS/REVIEWS + 4 PLAN) лежат в каталоге этого пункта; результаты GATE фазы 6 и `research/` остаются на месте для возможного возврата.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)
