# Retrospective: enpipe

Living retrospective across milestones. Newest milestone section on top; cross-milestone trends at the bottom.

---

## Milestone: v1.1 — Single-command pipeline entry point

**Shipped:** 2026-07-23
**Phases:** 1 (Phase 5, continuing v1.0's numbering) | **Plans:** 1

> Note: v1.1 is the repo's first formal milestone close. v1.0 (Phases 1–4) was shipped but never separately archived, so the cumulative archive under `.planning/milestones/v1.1-*.md` captures Phases 1–5. This retrospective section covers v1.1's own delivered scope (Phase 5) plus the productionization arc it caps.

### What Was Built

- `enpipe run <video>` — a thin sequential orchestrator composing the already-verified `run_detect` → `.scenes` → `run_encode`, with an additive fail-fast tool preflight and `--detect-jobs`/`--encode-jobs` to resolve the `--jobs` collision. Byte/frame-identical to the manual two-step and to the frozen `legacy/` oracle on real Arc hardware.
- This capped the v1.0 productionization arc: installable pinned package, `shared.proc` seam, isolated pure EBML/seek-trim/high-water-mark modules, fast + hardware-gated test tiers, and CI.

### What Worked

- **`legacy/` as a frozen parity oracle throughout.** Every migration and extraction was proven byte-identical against the untouched legacy scripts — the single most effective guard against silent regression in correctness-critical code.
- **Coarse granularity fit the milestone.** v1.1 was genuinely one thin wrapper over verified stages; collapsing all four RUN-* requirements into a single Phase 5 avoided artificial sub-phase overhead.
- **Measuring instead of guessing** the ThreadPool-vs-ProcessPool decision (Layer-1 wall-clock A/B + Layer-2 CPU-isolated microbench) turned a latent "fix the comment vs swap the executor" debate into an evidence-backed keep-threads decision.
- **Real-media hardware validation gate** (TEST-04) is what surfaced the concurrent-`qsvencc` corruption at all — the fast/mocked tier could never have caught a driver-level cross-process defect.

### What Was Inefficient

- **v1.0 was never formally closed**, so v1.1's archive had to absorb the full Phases 1–5 history as a cumulative snapshot. A per-milestone close discipline would have kept archives cleanly scoped.
- **The most important defect lives outside the test tiers we can run in CI.** The corruption reproduces only on real Arc hardware under concurrency, so it went undetected until manual real-media use post-Phase-5 — a structural gap between "CI green" and "output correct."

### Patterns Established

- Frozen-oracle parity checks (byte-identical `movie.obu` / `.scenes` diff) as the acceptance gate for any refactor of correctness-critical paths.
- Hardware-gated tier (`-m hardware`) kept strictly distinct from the software-fallback regression tier, so "CI passes" never over-claims real-media correctness.
- Env-var + argparse tunables over per-knob flag plumbing; typing-module generics; Russian in-code prose. (Codified in CLAUDE.md.)

### Key Lessons

- **"Frame count correct" ≠ "frames correct."** The corruption bug keeps frame counts intact and swaps individual frames' pixels — the existing frame-count guards are necessary but not sufficient. The next milestone should add a per-frame/VMAF corruption guard so silent single-frame swaps can't ship.
- **Concurrency is the enemy of this hardware's correctness.** The single load-bearing design assumption (parallel independent `qsvencc` chunks concatenate bit-exactly) is violated by an iHD cross-process aliasing defect. Fixing it may mean serializing/capping encode concurrency or an `av1_qsv` single-process path — a real product decision deferred to the next milestone.

### Cost Observations

- Model mix / sessions: not tracked this milestone (no per-session cost capture configured).
- Notable: Phase 5 was small (1 plan, 3 tasks, ~9 min execution per STATE metrics); the bulk of surrounding effort went to devcontainer/debug work (quick tasks + 3 debug sessions) chasing the hardware corruption.

---

## Cross-Milestone Trends

| Milestone | Shipped | Phases | Plans | Headline |
|-----------|---------|--------|-------|----------|
| v1.0 Productionization | 2026-07-08 | 4 | 10 | Installable, pinned, tested package behind a `shared.proc` seam; `legacy/` frozen as oracle |
| v1.1 Single-command pipeline | 2026-07-23 | 1 (Phase 5) | 1 | `enpipe run <video>` one-command sequential transcode |

**Recurring theme:** correctness-by-construction verified against the `legacy/` oracle has held for every in-repo refactor; the one place it cannot reach — real-hardware concurrent-encode behavior — is exactly where the open, unresolved risk now sits.
