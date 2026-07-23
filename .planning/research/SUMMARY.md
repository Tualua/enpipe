# Project Research Summary

**Project:** enpipe
**Domain:** Dual encode-backend addition (ffmpeg `av1_qsv` default / `qsvencc` opt-in) to a scene-chunk AV1 transcode pipeline — milestone v1.2
**Researched:** 2026-07-23
**Confidence:** HIGH (core swap verified live on the real Arc A380 + ffmpeg n8.1.2), with two named LOW-confidence gates (DV / HDR10+ hardware survival)

## Executive Summary

enpipe encodes a source video into keyframe-aligned AV1 scene chunks, byte-concatenates the raw `.obu` chunks, and muxes once with `mkvmerge`. The v1.2 milestone exists because the current `qsvencc` encoder *silently swaps single frames* under concurrent `JOBS` (~33–65% corruption on the 10-bit + B-pyramid + HW-decode triad) while `count_frames` still passes — a direct violation of the project's non-negotiable "correct, bit-exact" core value. The fix is to add an **ffmpeg `av1_qsv` backend as the corruption-free default**, retaining `qsvencc` as an opt-in backend for the metadata cases ffmpeg cannot yet cover.

**All four research agents independently converged on the same load-bearing result, and the Stack agent verified it LIVE against the real BtbN ffmpeg n8.1.2 binary on this A380/iHD GPU:** the frozen `qsvencc` preset maps cleanly onto ffmpeg `av1_qsv` (`--icq 23`→`-global_quality 23`, `--gop-len`→`-g`, `--gop-ref-dist 6`→`-bf 5` with automatic B-pyramid, tiling, 10-bit P010/Main all confirmed from encoder verbose output), and — critically — the **`-f obu` raw-elementary-stream + byte-`cat` invariant HOLDS** (verified 48/48 frames decode cleanly after concatenation). This preserves the load-bearing design without switching container formats.

**BUT the whole roadmap must respect one hard constraint:** Dolby Vision RPU and HDR10+ dynamic metadata **cannot be injected into freshly-encoded AV1 with the tools available in-container.** The `dovi_rpu` BSF only strips/rewrites RPU *already present* in a stream; `dovi_tool` is HEVC-only; `av1_qsv` drops DV/HDR10+ side-data and does not even write HDR10 static metadata or reliable color signaling in-stream. The consequence: ship ffmpeg default for **SDR + HDR10** (HDR10 static via `mkvmerge` container tags, color via the `av1_metadata` BSF), and route **HDR10+/Dolby Vision** to the retained `qsvencc` backend run corruption-safe (`--jobs 1` or `--avsw`). DV/HDR10+ passthrough *through hardware av1_qsv* is an UNVERIFIED POC gate, not a solved feature. Two further preconditions: **ffmpeg-8.1 is specified in the Dockerfile but not yet built into the running container** (`/opt/ffmpeg-8.1` absent — image rebuild is a prerequisite), and the concurrency immunity — proven only on 3 hotspot scenes — must be **RE-PROVEN at production `JOBS` with a full-file per-frame content sweep**, not assumed.

## Key Findings

### Recommended Stack

The stack introduces **no new Python dependencies and no new container format** — it is a command-builder swap plus an image rebuild. ffmpeg n8.1.2 (already staged in the Dockerfile, BtbN static GPL) supplies `av1_qsv` encode, `h264_qsv`/`hevc_qsv` HW decode, `vpp_qsv` for P010 10-bit surfaces, the `-f obu` low-overhead muxer, and the `av1_metadata`/`dovi_rpu` BSFs. HDR10 static metadata moves *out of the encoder* to the `mkvmerge` mux step (container-level `--max-content-light`/`--chromaticity-coordinates`/`--max-luminance`/…). The existing `qsvencc`, `mkvmerge`, `ffprobe`, and keyframe/seek arithmetic are all reused unchanged. See STACK.md for the full verified flag-mapping table.

**Core technologies:**
- **ffmpeg `av1_qsv` (n8.1.2)**: per-chunk AV1 HW encode — the corruption-immune default; preset parity verified live on the A380.
- **`-f obu` raw muxer**: keeps chunks byte-`cat`-concatenable — the load-bearing invariant; verified 48/48 frames post-concat.
- **`vpp_qsv=format=p010le`**: 10-bit Main-profile surfaces (replaces `--output-depth 10`); verified `yuv420p10le`/Main out.
- **`av1_metadata` BSF + `mkvmerge` container tags**: color signaling + HDR10 static metadata (av1_qsv writes neither reliably in-stream).
- **`qsvencc` (retained, opt-in)**: the ONLY in-container path that carries DV RPU / HDR10+ into AV1; run corruption-safe (`--jobs 1`/`--avsw`).

### Expected Features

This is a **parity milestone**: "table stakes" = features that must survive the encoder swap, not new user capability. See FEATURES.md.

**Must have (table stakes / parity):**
- av1_qsv encode of one scene-chunk → concatenable raw `.obu` — verified
- Corruption-free concurrent encode under `JOBS` — verified 35/35, must be re-proven at production JOBS
- ICQ-23 / 10-bit-Main / GOP-300 / B-pyramid / tiling preset parity — verified
- Frame-exact per-chunk seek/trim (keyframe input-seek + **frame-indexed** trim, never time-based `-ss`/`-t`)
- Per-chunk + total `count_frames` guards (reused, encoder-agnostic)
- SDR color signaling + HDR10 static metadata (via mkvmerge container tags)
- Backend selection (`--backend ffmpeg|qsvencc` + env, default ffmpeg)

**Should have (differentiators):**
- Per-frame content verification (PSNR/VMAF) of final `movie.obu` — defense-in-depth against *any* silent single-frame swap class
- Dual-backend A/B parity harness (+ home for the corruption regression test)

**Defer (v2+):**
- `hdr10plus_tool` out-of-band inject (only if in-band HDR10+ POC fails and parity is required — new dependency)
- `av1_vaapi` alternative path (only if av1_qsv itself ever shows aliasing)
- Host-side kernel fix for qsvencc concurrency (i915→Xe; out of container control)

### Architecture Approach

The clean seam is **not** a `backend=` branch inside `chunk_command`. It is a `backends/` sub-package where each encoder is a frozen-dataclass `Backend` value object bundling three pure callables (`build_command`, `build_hdr_args`, `parse_metrics`) plus `name`/`output_suffix`. `pipeline.run_encode` resolves the backend once and threads the object through the existing task loop; everything downstream — `count_frames` verify, high-water-mark ordered append, `JOBS` ThreadPool, byte-concat, `mkvmerge` mux — stays backend-agnostic and untouched. The exonerated keyframe seek/trim math (`compute_chunk_seek_trim`, proven bit-correct in the corruption handoff) is **shared, not re-derived**: expose its numeric `(kf_time, start_off, end_off)` and let each backend format it. See ARCHITECTURE.md.

**Major components:**
1. **`backends/` package** (`Backend` dataclass + `get_backend` registry, default `ffmpeg`) — NEW seam
2. **`backends/qsvencc.py`** (today's `chunk_command`/`detect_hdr`/`parse_metrics`, moved) + **`backends/ffmpeg.py`** (`av1_qsv` + `-f obu`; no-op metrics) — NEW
3. **`keyframes.compute_chunk_seek_trim_frames`** (additive numeric sibling; original stays for qsvencc byte-identity) — MODIFIED additively
4. **`pipeline.py` runner + `mkvmerge` mux** (small diff to carry `Backend`, container HDR tags; append/verify/JOBS UNCHANGED)

### Critical Pitfalls

Every pitfall is graded by one question: can it reintroduce *silent* output corruption or *silently* drop HDR/DV while `count_frames` still passes? Those must become explicit content-verification requirements. See PITFALLS.md.

1. **Unproven immunity on THIS host/JOBS** — the 35/35 result is 3 hotspot scenes only; ffmpeg merely *dodges* a kernel-level i915 aliasing bug. Make the concurrent full-file per-frame PSNR/VMAF sweep the *gating first* acceptance test, at production JOBS (3) and stress (5–8), with HW-decode+p010+GopRefDist6 confirmed in the param dump (a SW-decode fallback silently invalidates the proof).
2. **Silent HDR10 static-metadata loss** — av1_qsv cannot embed MDCV/max-CLL (intel/media-driver #1592). Inject at the `mkvmerge` container level and make an `ffprobe` side-data diff-vs-source an explicit HDR test assertion.
3. **Silent Dolby Vision RPU loss/misalignment** — encoder drops per-frame RPU; B-pyramid reorder can land RPU on the wrong frame. Verify RPU-count == frame-count + boundary/reordered-frame L1 spot-check via `dovi_tool info`; keep qsvencc as the DV fallback.
4. **Seek/trim off-by-one** — ffmpeg seeking is timestamp-based; a naive `-ss`/`-t` port drifts a frame at head/tail while total count still matches. Use keyframe input-seek + frame-indexed `trim`; assert first/last decoded frame PSNR-matches source `S`/`E-1`.
5. **GOP / raw-`.obu` concat breakage** — chunk frame 0 must be a closed-GOP keyframe with a repeated sequence-header OBU. Verify `movie.obu` *fully decodes end-to-end* (not just `count_packets`) with per-frame content match around chunk seams.

## Implications for Roadmap

Based on research, suggested phase structure. Ordering is **risk-first** (prove the premise before building on it) then **SDR→HDR→DV**, with the frozen `legacy/` byte-parity oracle preserved throughout.

### Phase 1: Concurrency-immunity spike (gating proof)
**Rationale:** The entire milestone premise — "ffmpeg av1_qsv is corruption-free" — rests on a 3-scene contrast experiment. If it does not hold at production JOBS on this exact kernel, the migration is invalid and must pivot to `--avsw`/`--jobs 1`. Prove it FIRST, before building the backend. (Also unblocks the image rebuild prerequisite.)
**Delivers:** Rebuilt devcontainer image with ffmpeg-8.1 on PATH; a concurrent per-frame-content regression harness (handed-off reproducer + full-file PSNR/VMAF sweep) proving 0 corruption at JOBS 3 and 5–8, with HW-decode+p010+GopRefDist6 asserted.
**Addresses:** "Corruption-free concurrent encode" (the reason the milestone exists).
**Avoids:** Pitfall 1 (unproven immunity), and the SW-decode-fallback false-positive.

### Phase 2: Backend seam refactor (zero behavior change)
**Rationale:** De-risk the integration by proving the seam is behavior-preserving *before* any ffmpeg encode code exists — qsvencc stays the only + default backend, must still match the legacy oracle byte-for-byte.
**Delivers:** `backends/` package + `Backend` dataclass + registry; `chunk_command`/`detect_hdr`/`parse_metrics` moved (with re-export shims); `compute_chunk_seek_trim_frames` numeric sibling; `Backend` threaded through `run_encode`/`encode_chunk`; `--backend` flag (only `qsvencc` valid yet).
**Uses:** Frozen-dataclass value-object convention (STACK/ARCHITECTURE).
**Implements:** The `backends/` seam and shared-keyframe-math patterns.
**Avoids:** Anti-pattern of a `backend=` branch; Anti-pattern of re-deriving seek/trim.

### Phase 3: ffmpeg SDR backend + flip default
**Rationale:** The highest-value real work — implement and validate the corruption-free default on the simplest (SDR) path, where all the load-bearing invariants (OBU concat, seek/trim, keyframe alignment) live.
**Delivers:** `backends/ffmpeg.py::build_command` (verified preset mapping + `-f obu` + frame-accurate `-ss`/frame-indexed trim); no-op metrics; flip `DEFAULT="ffmpeg"`; make the `qsvencc` preflight `which` conditional; SDR color signaling via `av1_metadata` BSF.
**Uses:** ffmpeg `av1_qsv`/`vpp_qsv`/`-f obu`/`av1_metadata` (STACK, verified).
**Avoids:** Pitfalls 4 (seek/trim off-by-one), 5/6 (GOP + raw-OBU concat) — each an explicit content-verify acceptance gate, not a count-only check.

### Phase 4: HDR10 static metadata through ffmpeg
**Rationale:** HDR10 static is a *solved-but-relocated* problem (moves from encoder to muxer) — lower risk than DV, so it lands before the POC-gated work.
**Delivers:** `ffmpeg.build_hdr_args` + `mkvmerge` container tagging emitting mastering-display/max-CLL/color probed from source.
**Avoids:** Pitfall 2 (silent HDR10 downgrade) — `ffprobe` side-data diff-vs-source is the acceptance assertion.

### Phase 5: Dolby Vision + HDR10+ decision (POC-gated, highest risk, last)
**Rationale:** This is the load-bearing risk PROJECT.md names — the whole reason qsvencc was originally chosen. DV RPU / HDR10+ passthrough through *hardware* av1_qsv is undocumented and unverified; the answer must be *known* at milestone close, not assumed. The likely outcome (per all four agents) is: **route DV/HDR10+ to the retained qsvencc backend run corruption-safe**, with in-band `dovi_rpu`/`hdr10plus_tool` treated as a follow-up.
**Delivers:** A POC verdict (does DV side-data survive av1_qsv? does the `dovi_rpu` BSF serialize it? RPU-count == frame-count, correct profile, aligned through B-reorder?) and a documented routing decision. If POC fails: DV/HDR10+ become qsvencc-only (opt-in), explicitly recorded as a known gap with the `--avsw`/`--jobs 1` safety default.
**Avoids:** Pitfall 3 (silent DV RPU loss/misalignment).

### Phase Ordering Rationale
- **Risk-first:** the concurrency proof (Phase 1) is a *gate* — everything else is wasted if the premise fails. The DV/HDR10+ POC (Phase 5) is the second-biggest unknown and is deferred so it cannot block the SDR/HDR10 value delivery.
- **Refactor-before-feature:** Phase 2 lands a behavior-preserving seam validated against the legacy oracle, so Phase 3's new encoder code slots into a proven structure.
- **SDR→HDR→DV** matches increasing metadata complexity and increasing hardware-survival uncertainty; each phase gates on its own content-verification test before the next.

### Research Flags

Phases likely needing deeper research during planning (`/gsd:plan-phase --research-phase <N>`):
- **Phase 5 (DV / HDR10+):** the load-bearing UNVERIFIED gate — hardware av1_qsv side-data survival, `dovi_rpu` BSF AV1/T.35 wrapping, per-chunk RPU slicing + B-reorder alignment, and the qsvencc-fallback routing all need spike-level validation on a real DV fixture (which may not exist on hardware — a gap in itself).
- **Phase 1 (concurrency spike):** methodology needs care (full-file sweep vs hotspot-only, JOBS thresholds, triad-integrity assertion) even though the tools are known.

Phases with standard patterns (skip research-phase):
- **Phase 2 (seam refactor):** well-scoped mechanical refactor matching existing frozen-dataclass conventions; ARCHITECTURE.md already specifies the structure.
- **Phase 3 (SDR backend):** the flag mapping and per-chunk command are already verified live in STACK.md; execution risk is in testing, not discovery.
- **Phase 4 (HDR10 static):** mkvmerge container options verified present; mechanism is documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every flag-mapping row executed against real ffmpeg n8.1.2 on this A380/iHD; `-f obu` cat-concat verified 48/48. Gaps (DV/HDR10+/HDR10-in-stream) are *verified-absent*, not unknown. |
| Features | MEDIUM-HIGH | Preset/seek-trim/HDR10-static: HIGH/verified in-env. DV RPU + HDR10+ per-frame survival through hardware av1_qsv: LOW/UNVERIFIED — explicitly POC-gated. |
| Architecture | HIGH | Existing code read directly; seam design matches proven conventions; keyframe math exonerated by the corruption handoff. MEDIUM only on exact HDR-signaling flag placement. |
| Pitfalls | HIGH | qsvencc root cause + enpipe internals read from primary debug docs; ffmpeg/av1_qsv/dovi_rpu behavior corroborated against official issue trackers; HW behavior flagged as must-re-prove. |

**Overall confidence:** HIGH for the SDR + HDR10 default path (the milestone's core); the two named LOW-confidence gates (DV, HDR10+ hardware survival) are deliberately isolated to the final POC-gated phase with a known qsvencc fallback, so they do not threaten core delivery.

### Gaps to Address

- **DV / HDR10+ hardware survival (the load-bearing gap):** undocumented whether av1_qsv propagates DV/HDR10+ side-data to output packets for the BSF to serialize. Handle via the Phase 5 POC spike with an explicit qsvencc-only fallback recorded in requirements — do NOT let the roadmap assume the `dovi_rpu` BSF closes it.
- **Image rebuild prerequisite:** ffmpeg-8.1 is in the Dockerfile but absent from the running container (`/opt/ffmpeg-8.1` missing). Fold the rebuild into Phase 1 before any in-place ffmpeg run.
- **Concurrency proof scope:** must be a full-file per-frame sweep at production + stress JOBS with triad integrity asserted, not the 3-hotspot smoke check — else a SW-decode fallback yields a false "clean."
- **`first>0` seek/trim on real media:** only `first==0` was verified live; the frame-indexed `trim` filter's frame-accuracy must pass the hardware parity gate on real media (Phase 3).
- **No real DV fixture may exist on hardware:** the current suite only fixture-gates DV/HDR10+. Confirm a real fixture runs in the hardware tier before Phase 5 close, or flag the absence as a shipped-untested risk.
- **Cross-backend comparability:** ICQ-23 ≠ av1_qsv "23" in general; define the v1.2 correctness basis as per-frame-content parity + a quality/size band (not byte-identity to legacy), and calibrate/document the mapping (Phase 5 / dual-backend).

## Sources

### Primary (HIGH confidence)
- **Real ffmpeg n8.1.2-30-g45f1910444 (BtbN static GPL) executed on this Intel Arc A380 / iHD (VA-API 1.23)** — full qsvencc→av1_qsv flag mapping from encoder verbose (ICQ/GopPicSize/GopRefDist/BRefType/NumTile*/profile/level), 10-bit `-f obu` output, two-chunk `cat` frame-count (48/48), HW-decode→vpp→encode chain (24/24), `ScenarioInfo` rejection, `dovi_tool 2.3.3` HEVC-only.
- `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` + `scene-chunk-frame-mismatch.md` — qsvencc concurrent 10-bit reference-surface aliasing root cause, kernel i915 localization, ffmpeg immunity 35/35 contrast, `--avsw`/`--jobs 1` fallbacks, defense-in-depth per-frame recommendation.
- `src/enpipe/encoding/{chunk,hdr,keyframes,pipeline}.py`, `cli/main.py`, existing tests — current command, exonerated seek/trim, integration points, byte-concat + count_frames guards.
- `.planning/PROJECT.md`, `CLAUDE.md` — project constraints, conventions, non-negotiable core value.

### Secondary (MEDIUM confidence)
- intel/media-driver #1592, intel/cartwheel-ffmpeg #221, intel/libvpl #87 — av1_qsv has NO HDR10 static-metadata passthrough (corroborated across trackers).
- FFmpeg `dovi_rpu` BSF docs + FFmpeg-devel patch + DeepWiki "Dolby Vision and HDR Metadata" — RPU strip/rewrite only, software-encoder-only DV/HDR10+ documentation; BSF added mid-2024 (present in 8.1).
- FFmpeg Formats/BSF docs — `-f obu` low-overhead muxer, temporal-delimiter/sequence-header/global-header handling.
- AOM HDR10+ AV1 spec, quietvoid/hdr10plus_tool #116 — T.35 OBU carriage; hdr10plus_tool AV1 support (not installed → would be a new dependency).

### Tertiary (LOW confidence / needs validation)
- Hardware av1_qsv DV/HDR10+ side-data survival — inferred from software-encoder docs only; must be POC-validated (Phase 5).
- `first>0` frame-indexed `trim` accuracy — logically derived; needs real-media hardware parity gate (Phase 3).

---
*Research completed: 2026-07-23*
*Ready for roadmap: yes*
