# Requirements: enpipe

**Defined:** 2026-07-23
**Core Value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

**Milestone scope (v1.2 Concurrent-encode correctness, re-scoped 2026-10-02):** Eliminate the concurrent-encode silent frame corruption. The corruption was fixed upstream in rigaya/QSVEnc (`45003f1`, issue #308) and verified on our Arc A380, so v1.2 adopts the fixed qsvencc and locks it in with a regression test instead of migrating the default encoder to ffmpeg `av1_qsv`. The ffmpeg migration (former BK/FF/HDR requirements, former Phases 7–10) is parked as backlog item 999.1. NOT: rewriting detect/seek-trim algorithms; NOT the streaming orchestrator. `legacy/` stays the frozen parity oracle.

---

## v1.2 Requirements (ACTIVE)

### Environment (ENV)

- [x] **ENV-01**: The devcontainer image is rebuilt with ffmpeg 8.1 on PATH (av1_qsv encode + `av1_metadata`/`dovi_rpu` BSFs available), verified by the post-create self-check — a prerequisite before any in-container ffmpeg encode.

### qsvencc fix adoption (QSV)

- [ ] **QSV-01**: The devcontainer installs a qsvencc build containing upstream commit `45003f1` (source build until an upstream release includes it, then a pinned release), and the post-create self-check asserts the installed revision.
- [x] **QSV-02**: `enpipe encode`/`enpipe run` fail fast with an explicit error when the qsvencc on PATH predates the fix, so a downgraded or stale build can never silently produce corrupted output.

### Encode correctness (COR)

- [x] **COR-01**: A concurrent-encode regression test proves the ffmpeg backend produces zero corrupted frames under parallel `JOBS` (production and stress levels), using **per-frame content verification** (not just frame counts), with the HW-decode + P010 + B-pyramid corruption triad asserted present so a decode-fallback cannot yield a false "clean."
- [x] **COR-02**: A hardware-gated regression test proves the fixed qsvencc produces zero corrupted frames under parallel `JOBS` (production and stress levels) with per-frame content verification and the corruption triad asserted active — inverting the Phase 6 "qsvencc control corrupts" expectation into a permanent lock.

---

## Future Requirements

Deferred; tracked but not in the v1.2 roadmap.

### ffmpeg av1_qsv backend (backlog 999.1, parked 2026-10-02)

Former v1.2 requirements, parked when the qsvencc corruption was fixed upstream. Full text preserved in git history and in `.planning/phases/999.1-ffmpeg-av1qsv-backend/`.

- **BK-01**: `--backend ffmpeg|qsvencc` selection (+ env var).
- **BK-02**: Shared `backends/` seam with the qsvencc backend byte-identical to pre-refactor output.
- **FF-01/02/03**: ffmpeg `av1_qsv` chunk encode reproducing the qsvencc preset, frame-exact seek/trim, end-to-end SDR on full JOBS.
- **HDR-01/02/03**: HDR10 static metadata via mkvmerge tags + `av1_metadata`; DV/HDR10+ never silently downgraded; `dovi_tool` PR #389 AV1 `inject-rpu` spike.

### Dolby Vision / HDR10+

- **DV-F1**: If the PR #389 spike (HDR-03) succeeds but the branch is not yet merged/maintainable, harden the DV-on-ffmpeg path into a pinned/vendored production dependency once `dovi_tool` AV1 support stabilizes upstream.
- **DV-F2**: Native in-band HDR10+ dynamic-metadata carriage on the ffmpeg path once tooling (hdr10plus / dovi_tool AV1) is CLI-stable.

### Carried from prior milestones (v2)

- **OBS-01**: stdlib `logging` replaces the `print`-based `log()`/`step()` helpers.
- **CFG-01**: typed config/Settings layer formalizing the env-var + argparse convention.
- **QUAL-01/02/03, CI-02**: ruff+pyright in CI, golden-file EBML fixtures, coverage/Hypothesis, image parity + Renovate.

---

## Out of Scope

Explicitly excluded for v1.2.

| Feature | Reason |
|---------|--------|
| Building a custom libdovi-linked injector from scratch | `dovi_tool` PR #389 already implements AV1 `inject-rpu` — spike the existing code (HDR-03), don't re-implement it |
| Adopting an unmerged `dovi_tool` branch as a blind committed dependency | Correctness-critical project; the branch is spike-gated (HDR-03), with a single-pass whole-file qsvencc encode as the guaranteed fallback |
| Auto-routing DV/HDR10+ to qsvencc **silently** | Violates the core value — routing (if used) must be explicit + logged, never a silent metadata downgrade (HDR-02) |
| Overlapped / streaming orchestrator | Out of scope since v1.0; gated on SSD/NVMe, not this milestone |
| Rewriting detect / seek-trim / EBML algorithms | Load-bearing correctness invariants reused unchanged; `compute_chunk_seek_trim` exonerated by the corruption debug and shared, not re-derived |
| Removing qsvencc from the pipeline | qsvencc remains the sole encoder; with the upstream fix it is corruption-free under concurrency and keeps DV/HDR10+ support |
| Host-side kernel fix for the qsvencc corruption (i915→Xe, GuC/HuC) | Unnecessary — root cause was a missing VPP-output sync in qsvencc, fixed upstream (`45003f1`) |

---

## Traceability

Phase numbering continues from v1.1 (which ended at Phase 5); v1.2 phases are 6–7 (re-scoped 2026-10-02).

| Requirement | Phase   | Status   |
|-------------|---------|----------|
| ENV-01  | Phase 6  | Complete |
| COR-01  | Phase 6  | Complete |
| QSV-01  | Phase 7  | Pending  |
| QSV-02  | Phase 7  | Complete |
| COR-02  | Phase 7  | Complete |

**Coverage (v1.2, active):**
- v1.2 requirements: 5 total
- Mapped to phases: 5 ✅
- Unmapped: 0

---
*Requirements defined: 2026-07-23*
*Last updated: 2026-10-02 — v1.2 re-scoped: qsvencc corruption fixed upstream (`45003f1`); ffmpeg migration parked as backlog 999.1*
