# Requirements: enpipe

**Defined:** 2026-07-23
**Core Value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

**Milestone scope (v1.2 ffmpeg backend):** Eliminate the concurrent-encode silent frame corruption by adding an ffmpeg `av1_qsv` encode backend (empirically immune) as the new **default**, while retaining `qsvencc` as an opt-in selectable backend. Dual-backend. ffmpeg owns SDR + HDR10; DV/HDR10+ are carried through ffmpeg **only if** a dovi_tool AV1 `inject-rpu` spike validates, otherwise encoded as a single-pass whole-file qsvencc job (legacy route, no scene splitting — corruption-free by construction) — never silently downgraded. NOT: rewriting detect/seek-trim algorithms (reused unchanged); NOT the streaming orchestrator. `legacy/` stays the frozen parity oracle.

---

## v1.2 Requirements (ACTIVE)

### Environment (ENV)

- [ ] **ENV-01**: The devcontainer image is rebuilt with ffmpeg 8.1 on PATH (av1_qsv encode + `av1_metadata`/`dovi_rpu` BSFs available), verified by the post-create self-check — a prerequisite before any in-container ffmpeg encode.

### Backend selection & seam (BK)

- [ ] **BK-01**: User can choose the encode backend via `--backend ffmpeg|qsvencc` (and an env var), defaulting to `ffmpeg`; the choice applies to every scene chunk in a run.
- [ ] **BK-02**: Both encode backends live behind a shared `backends/` seam that keeps each backend's command-builder a pure, argv-testable function; the qsvencc backend stays byte-identical to the pre-refactor output (legacy-oracle parity preserved, zero behavior change).

### ffmpeg av1_qsv encode (FF)

- [ ] **FF-01**: ffmpeg `av1_qsv` encodes a scene chunk into a byte-concatenable raw `.obu` reproducing the qsvencc preset (ICQ→`-global_quality`, GOP length, B-pyramid/`gop-ref-dist`, tiling, 10-bit Main), with the concatenated `movie.obu` fully decoding to the expected frame count.
- [ ] **FF-02**: Per-chunk seek/trim on the ffmpeg path is frame-exact (keyframe input-seek + frame-indexed trim, never time-based `-ss`/`-t`), so chunk boundaries land on source keyframes and per-chunk + total `count_frames` guards pass.
- [ ] **FF-03**: `enpipe run`/`enpipe encode` on an SDR source transcodes end-to-end on the ffmpeg default backend, producing correct output at full parallel `JOBS`.

### Encode correctness (COR)

- [ ] **COR-01**: A concurrent-encode regression test proves the ffmpeg backend produces zero corrupted frames under parallel `JOBS` (production and stress levels), using **per-frame content verification** (not just frame counts), with the HW-decode + P010 + B-pyramid corruption triad asserted present so a decode-fallback cannot yield a false "clean."

### HDR / Dolby Vision (HDR)

- [ ] **HDR-01**: HDR10 static metadata (mastering-display + max-CLL) and color signaling survive the ffmpeg path (via `mkvmerge` container tags + the `av1_metadata` BSF), verified by an `ffprobe` side-data diff against the source.
- [ ] **HDR-02**: DV and HDR10+ sources are never silently downgraded under the ffmpeg default — they are either carried through the ffmpeg path (if HDR-03 validates) or encoded via a **single-pass whole-file qsvencc job** (the legacy `encode_av1_opus.sh` route: no scene splitting, one session — therefore corruption-free *by construction* since the corruption needs concurrent sessions — at full HW-decode+encode speed with 10-bit/B-pyramid/DV preserved), with the chosen behavior explicit and logged.
- [ ] **HDR-03**: A spike validates `dovi_tool` PR #389 AV1 `inject-rpu` over an ffmpeg-encoded `.obu` (RPU-count == frame-count, correct per-frame display-order alignment through B-pyramid) on a real DV fixture; the verdict decides HDR-02's routing and is recorded.

---

## Future Requirements

Deferred; tracked but not in the v1.2 roadmap.

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
| Removing qsvencc from the pipeline | Dual-backend by decision — qsvencc is the DV/HDR10+ fallback and the corruption-safe path |
| Host-side kernel fix for the qsvencc corruption (i915→Xe, GuC/HuC) | Outside container control; the whole point of v1.2 is to route around it via ffmpeg, not fix the kernel |

---

## Traceability

Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01  | Phase _ | Pending |
| BK-01   | Phase _ | Pending |
| BK-02   | Phase _ | Pending |
| FF-01   | Phase _ | Pending |
| FF-02   | Phase _ | Pending |
| FF-03   | Phase _ | Pending |
| COR-01  | Phase _ | Pending |
| HDR-01  | Phase _ | Pending |
| HDR-02  | Phase _ | Pending |
| HDR-03  | Phase _ | Pending |

**Coverage (v1.2, active):**
- v1.2 requirements: 10 total
- Mapped to phases: 0 (roadmap not yet created)
- Unmapped: 10 ⚠️

---
*Requirements defined: 2026-07-23*
*Last updated: 2026-07-23 after v1.2 requirements definition*
