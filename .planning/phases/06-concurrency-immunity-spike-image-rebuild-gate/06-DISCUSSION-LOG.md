# Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-23
**Phase:** 6-Concurrency-Immunity Spike + Image Rebuild (GATE)
**Areas discussed:** Sweep scope & metric, COR-01 artifact & fixture, Immunity confidence bar, Gate-fail pivot plan

---

## Sweep scope & metric

| Option | Description | Selected |
|--------|-------------|----------|
| Full-file every-frame | PSNR every frame vs isolated reference; catches migrated defect; slow but one-time | ✓ |
| Hybrid: full-file + hotspot anchor | Full-file ffmpeg + qsvencc hotspot assertion | |
| Hotspot-only | Scan known-bad offsets only; risk of missing a migrated defect | |

| Option | Description | Selected |
|--------|-------------|----------|
| PSNR only | Calibrated (~15.74 vs ~41.5 dB), fast, no VMAF locale gotcha | ✓ |
| PSNR + VMAF | Perceptual cross-check; slower, fragile CSV parsing; overkill | |

| Option | Description | Selected |
|--------|-------------|----------|
| Isolated single-session encode | Reproducer's proven reference; isolates concurrency defect | ✓ |
| Decoded source frames | Conflates lossy-encode quality with corruption; noisier | |

| Option | Description | Selected |
|--------|-------------|----------|
| <30 dB = corrupt | Reproducer's calibrated cutoff, huge margin | ✓ |
| Strict bit-identity | Tightest; risks false-positive on benign non-determinism | |
| You decide | — | |

| Option | Description | Selected |
|--------|-------------|----------|
| Parse ffmpeg -v verbose init log | Proves HW-decode + P010 + B-pyramid on the clean run | ✓ |
| Probe output stream properties | Weaker on proving HW (not SW) decode | |
| You decide | — | |

**User's choice:** Full-file every-frame · PSNR only · isolated-encode reference · <30 dB threshold · triad via verbose init-log parse.
**Notes:** Full coverage chosen specifically because ffmpeg's per-component surface pools could migrate the defect off the known qsvencc hotspot.

---

## COR-01 artifact & fixture

| Option | Description | Selected |
|--------|-------------|----------|
| Real /data Cold Eyes remux | Proven to corrupt qsvencc 33–65% → SC#4 non-vacuous; hardware-gated | ✓ |
| Real fixture now, synthetic later | Gate on real, attempt synthetic follow-on | |
| Synthetic self-contained clip | CI-portable but risks vacuous qsvencc control | |

| Option | Description | Selected |
|--------|-------------|----------|
| Hardware-gated pytest | Permanent @pytest.mark.hardware test in tests/integration/ | ✓ |
| Pytest + one-time spike report | Test plus a standalone report doc | |
| Spike script + report only | No committed regression guard | |

| Option | Description | Selected |
|--------|-------------|----------|
| Committed=prod, gate=full matrix | Committed test at JOBS=3; stress 5–8 × ≥20 iters once, recorded | ✓ |
| Committed carries full matrix | Full prod+stress every run; slow | |
| You decide | — | |

| Option | Description | Selected |
|--------|-------------|----------|
| Phase SUMMARY + debug log | Env config + numbers in SUMMARY + append to scene-chunk-frame-mismatch.md | ✓ |
| Test docstring/assertion only | Couples one-time env facts to a rerunnable test | |
| You decide | — | |

**User's choice:** Real Cold Eyes fixture · hardware-gated pytest in tests/integration/ · committed=prod JOBS=3 + one-time full stress matrix · evidence in Phase SUMMARY + debug-log append.
**Notes:** Preferred the plain pytest over the pytest+report option; gate evidence still recorded via SUMMARY + debug-log append (handoff DoD §10.4).

---

## Immunity confidence bar

| Option | Description | Selected |
|--------|-------------|----------|
| 3, 5, and 8 | Production + mid + high stress; 8 is margin beyond realistic A380 concurrency | ✓ |
| 3 and 5 | Lighter; thinner margin | |
| You decide | — | |

| Option | Description | Selected |
|--------|-------------|----------|
| ≥20 iters/level, zero corrupt | Survival prob ~10⁻³ at base rate; qsvencc control positive | ✓ |
| ≥10 iters/level, zero corrupt | Lighter budget, weaker confidence | |
| You decide | — | |

**User's choice:** JOBS 3/5/8 · ≥20 iterations/level · zero corrupt frames with qsvencc control positive in the same harness.
**Notes:** —

---

## Gate-fail pivot plan

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered: prod=hard-fail, stress=cap | JOBS=3 fail → pivot; stress-only fail → proceed but cap JOBS | ✓ (Claude's discretion) |
| Strict: any corruption = pivot | Zero at all levels or full pivot | |
| You decide | — | ✓ (user delegated) |

| Option | Description | Selected |
|--------|-------------|----------|
| A (--avsw) primary, B (--jobs 1) backstop | SW-decode keeps DV/HDR; serialize backstop | |
| B (--jobs 1) only | Minimal change, guaranteed 0% corrupt, 1/3 throughput | ✓ |
| Just record + reopen | No pre-committed Plan B | |

**User's choice:** Pivot boundary → "You decide" (Claude set the tiered boundary: prod JOBS=3 hard-fail; stress-only → proceed + cap JOBS). Plan B → `--jobs 1` only.
**Notes:** User delegated the exact pivot boundary; Claude chose tiered to separate "premise invalid" (JOBS=3 failure) from "concurrency ceiling" (stress-only failure). Broader §7 workarounds deferred to the pivot effort.

---

## Claude's Discretion

- Pivot pass/fail boundary — set to tiered (prod hard-fail / stress-cap) per user delegation.
- Triad-assertion log-parsing details against ffmpeg 8.1 verbose output.
- "Modest" iteration count for the committed production-JOBS test.
- JOBS-cap value on stress-only corruption (highest proven-clean level).
- Per-frame extraction + isolated-reference workdir plumbing.

## Deferred Ideas

- Broader workaround evaluation (--avsw, output-depth 8, gop-ref-dist 1, host-side i915→Xe) — only if gate fails.
- Correct re-encode of the corrupted shipped Cold Eyes frames — post-fix, user's call (HANDOFF §0.4).
- Cleanup of the failed Tualua/QSVEnc patch branches (HANDOFF §9).
- Defense-in-depth per-frame content check on the production movie.obu concat — later pipeline phase.
