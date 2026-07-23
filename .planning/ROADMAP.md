# Roadmap: enpipe

## Milestones

- ✅ **v1.0 Productionization** — Phases 1–4 (shipped 2026-07-08)
- ✅ **v1.1 Single-command pipeline entry point** — Phase 5 (shipped 2026-07-23)

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

## Progress

| Phase                                                 | Milestone | Plans Complete | Status   | Completed  |
| ----------------------------------------------------- | --------- | -------------- | -------- | ---------- |
| 1. Package Foundation, Migration & Fast Test Tier     | v1.0      | 3/3            | Complete | 2026-07-08 |
| 2. Correctness-Critical Extraction                    | v1.0      | 2/2            | Complete | 2026-07-08 |
| 3. Concurrency Resolution + Regression Baseline + CI  | v1.0      | 3/3            | Complete | 2026-07-08 |
| 4. Unified CLI + Hardware-Gated Real-Media Validation | v1.0      | 2/2            | Complete | 2026-07-08 |
| 5. Single-Command Pipeline Entry Point                | v1.1      | 1/1            | Complete | 2026-07-09 |
