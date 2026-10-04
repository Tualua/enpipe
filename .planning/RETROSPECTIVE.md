# Retrospective: enpipe

Living retrospective across milestones. Newest milestone section on top; cross-milestone trends at the bottom.

---

## Milestone: v1.2 — Concurrent-encode correctness

**Shipped:** 2026-10-04
**Phases:** 3 (Phases 6–8) | **Plans:** 14

### What Was Built

- **Phase 6 GATE:** a per-frame concurrency harness that proved ffmpeg `av1_qsv` immune to the corruption (320 sessions, 0 corrupt) while qsvencc corrupted in the same harness — the evidence that later became the qsvencc lock. Re-confirmed on ffmpeg n9.0.2 at close.
- **Phase 7:** adopted the upstream-fixed qsvencc (`45003f1`) behind a fail-closed revision gate (runtime + post-create) and inverted the Phase 6 control into the COR-02 regression lock, non-vacuous on r4604.
- **Phase 8:** hardened the lock to byte identity vs an isolated reference, frame-count triangulation, triad on every session and both metrics variants (640-session matrix, 0 mismatches); runtime image on ubuntu:24.04 + Intel PPA.
- Around the phases: qsvencc pinned to the Tualua fork (vppsync4 → 6 → 7, r4665) as `--seek` and open-GOP `--trim` bugs were found, handed off and fixed; both images moved to pinned BtbN ffmpeg n9.0.2.

### What Worked

- **Gate before building.** Phase 6 proved (or could have disproved) the migration premise on real hardware before any backend code; when the root cause turned up in qsvencc, nothing had to be thrown away — the harness became the lock.
- **Fixing upstream instead of routing around.** Root-causing into qsvencc (45003f1, co-authored by the owner) and the fork handoff workflow (`HANDOFF-*.md` → fix → raise `QSVENCC_MIN_REV`) kept the DV/HDR10+ path untouched and avoided a costly encoder migration.
- **Non-vacuity as a first-class check.** Every lock run is paired with an old-binary run (r4604) that must fail — so "0 corrupt" is never vacuous.
- **Byte identity over thresholds.** Once hardware determinism was confirmed, sha256 equality replaced the PSNR ≥ 30 dB gate that could miss partial corruption.

### What Was Inefficient

- **Mid-milestone re-scope** (2026-10-02) left a trail: four parked PLANs under 999.1 that health/progress tools count as in-progress, and SDK counters (STATE frontmatter, `milestone.complete`) that mixed backlog plans into milestone totals and had to be corrected by hand twice.
- **Environment churn outran the scripts.** The ffmpeg 8.1 → 9 switch (quick 261004-h8e) renamed a harness function but missed `scratch/gate_stress_matrix.py`; it surfaced only in the Phase 06 UAT re-run (fixed in 261004-mse, guard extended to `scratch/`).
- **Stale human-verification items** (Phase 06 written against ffmpeg-8.1 and a "qsvencc corrupts" control) had to be translated to the current environment before they could be closed.

### Patterns Established

- Fail-closed version gate with a single threshold constant synced between runtime code and post-create (test-enforced), raised each time an upstream fix lands.
- Lock = byte identity + frame-count triangulation + triad-on-every-session + paired non-vacuity run on a known-bad binary.
- Upstream bug workflow: `.planning/debug/HANDOFF-*.md` with repro/evidence → owner fixes in the fork → enpipe raises the gate; loud refusal until then.
- Pin-sync guards (`test_ffmpeg_pin_sync.py`, qsvencc threshold sync) to stop partial updates between the two images and helper scripts.

### Key Lessons

- **Find the real root cause before migrating.** The driver-aliasing hypothesis was wrong; the actual defect was a missing VPP→encoder sync in qsvencc. A migration would have "fixed" it while leaving the reason unknown.
- **Hardware-only correctness needs hardware-only tests — and they rot quietly.** Scripts under `scratch/` are part of the evidence chain and need the same stale-reference guards as the images.
- **"Frame count correct" ≠ "frames correct" (v1.1 lesson) is now enforced** by byte identity in the lock.

### Cost Observations

- Model mix: planning on opus, execution on sonnet (per config); per-session cost not tracked.
- Sessions: not tracked.
- Notable: most wall-clock went to hardware runs (stress matrices of 320–640 sessions, ~25–60 min each) and upstream qsvencc debugging, not to in-repo code.

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
| v1.2 Concurrent-encode correctness | 2026-10-04 | 3 (Phases 6–8) | 14 | Concurrent qsvencc corruption fixed upstream, gated and locked by byte-identity hardware test |

**Recurring theme:** correctness-by-construction verified against the `legacy/` oracle has held for every in-repo refactor. v1.2 closed the gap it could not reach — real-hardware concurrent-encode behavior — with a hardware byte-identity lock plus a known-bad-binary non-vacuity run; the remaining risk now sits in upstream qsvencc releases, guarded by the fail-closed revision gate.
