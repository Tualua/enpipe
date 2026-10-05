# Feature Research

**Domain:** ffmpeg `av1_qsv` scene-chunk encode backend (dual-backend addition to `enpipe` v1.2)
**Researched:** 2026-07-23
**Confidence:** MEDIUM-HIGH (encoder preset, seek/trim, HDR10 static: HIGH/verified in-env; DV RPU + HDR10+ per-frame survival through hardware av1_qsv: LOW/UNVERIFIED — flagged as the load-bearing risk)

## Scope note

This is a **parity milestone**: the ffmpeg `av1_qsv` backend must reproduce what `qsvencc`
already does per-chunk, corruption-free under concurrency, while `qsvencc` is retained as an
opt-in backend. "Table stakes" here = **parity features that must survive the encoder swap**,
not new user-facing capability. The environment was probed directly: `ffmpeg 6.1.1` is the
system default, and **ffmpeg `n8.1.2` (BtbN GPL static) is staged** in-container with
`av1_qsv`, the `dovi_rpu` BSF (supported codecs: `hevc av1`), and the `av1_metadata` BSF all
present. `dovi_tool 2.3.3` (HEVC-only) and `mkvmerge v82.0` are installed; `hdr10plus_tool`
is **not** installed.

---

## Feature Landscape

### Table Stakes (Must Have for Parity)

Every one of these already works via `qsvencc`. The ffmpeg path is only accepted if it matches.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **av1_qsv encode of one scene-chunk → raw `.obu`** | Core of the milestone; concat of `.obu` must stay byte-appendable | MEDIUM | ffmpeg emits AV1 to `.obu`/`.ivf`; must confirm raw-OBU output that concatenates like qsvencc's. `-f obu` or pipe of the AV1 elementary stream. Verify each chunk is a standalone temporal-unit stream. |
| **Corruption-free concurrent encode under `JOBS`** | The entire reason for the milestone (qsvencc silently swaps a frame across concurrent sessions) | LOW (property, not code) | **VERIFIED**: ffmpeg `av1_qsv` = 35/35 clean under 3-way/5-way vs qsvencc ~33–65% corrupt, same hotspot. Root cause is qsvencc's OR-combined VA surface pool; ffmpeg uses per-component `AVHWFramesContext`. This is empirically established, not assumed. |
| **ICQ-equivalent quality (`--icq 23 --qp-max 100`)** | Output quality/size must match the frozen preset | LOW | **VERIFIED in-env**: `av1_qsv` exposes `-global_quality` (ICQ mode when no bitrate target set). `-global_quality 23` == `--icq 23`. `--qp-max` has no direct av1_qsv AVOption → reachable via `-qsv_params` (e.g. `QPMax=100`) if it materially affects output. |
| **10-bit Main profile (P010)** | HDR sources require 10-bit; matches `--output-depth 10 --profile main` | LOW | **VERIFIED**: `av1_qsv` supports `p010le`/`qsv` pixfmt and `-profile main`. Decode+VPP must produce `p010le` (`-vf vpp_qsv=format=p010le` or hwupload). Same combo the control test used. |
| **GOP 300 / B-pyramid `--gop-ref-dist 6`** | Preset parity (rate/size behavior) | MEDIUM | `-g 300` maps GOP length. B-pyramid + GopRefDist need exact mapping: `-bf` (max B-frames) + `-qsv_params GopRefDist=6:BRefType=2`. The control test already ran `GopRefDist:6 BRefType:pyramid` on ffmpeg (param-dump confirmed) — so achievable; the risk is matching *exactly*, use `-qsv_params` as the escape hatch. |
| **Tiling `--tile-col 1 --tile-row 1`** | Preset parity | LOW | **VERIFIED**: `av1_qsv` exposes `-tile_cols 1 -tile_rows 1`. |
| **Frame-exact per-chunk seek/trim** | Chunk boundaries must land on source keyframes; frame count per chunk must equal `E-S` | **HIGH** | See "seek/trim parity" below. **Do NOT use time-based `-ss`/`-t` for the trim** — must use keyframe input-seek + **frame-indexed** trim to match qsvencc's `--trim start:end` semantics. Existing `compute_chunk_seek_trim` (kf_time, S-K, E-1-K) is reusable; only the command translation changes. |
| **Per-chunk + total frame-count verification** | Load-bearing correctness invariant; silent corruption is the #1 project risk | LOW | `count_frames` (ffprobe packet count) already exists and is encoder-agnostic. Reused unchanged. Guards the seek/trim translation above. |
| **SDR color signaling (primaries/transfer/matrix/range/chromaloc)** | Matches qsvencc `--colorprim/--transfer/--colormatrix/--colorrange/--chromaloc auto` | LOW-MEDIUM | ffmpeg output opts `-color_primaries/-color_trc/-colorspace/-color_range` (probed from source) or the `av1_metadata` BSF (`color_primaries`/`transfer_characteristics`/`matrix_coefficients`/`color_range`/`chroma_sample_position`) — **VERIFIED present**. "auto" = probe source and pass explicitly; hardware encode does not reliably auto-carry these. |
| **HDR10 static metadata (mastering-display + MaxCLL)** | Parity with qsvencc `--master-display copy --max-cll copy` | MEDIUM | **MECHANISM CHANGES.** `av1_qsv` has **no way to write HDR10 mastering-display/CLL into the bitstream** (verified: intel/media-driver #1592, cartwheel-ffmpeg #221 — open feature request, still unsupported). Parity is still achievable but **moves to the muxer**: probe source, pass to `mkvmerge` container-level `--chromaticity-coordinates / --white-colour-coordinates / --max-luminance / --min-luminance / --max-content-light / --max-frame-light` (**VERIFIED present in mkvmerge v82**). Players read container-level HDR10. |
| **Dolby Vision RPU passthrough (profile 10.1)** | Parity with qsvencc `--dolby-vision-rpu copy --dolby-vision-profile 10.1` | **HIGH / RISK** | See "DV feasibility" below. Only viable path is the in-band ffmpeg `dovi_rpu` BSF (supports `av1`); `dovi_tool` is **HEVC-only** (no AV1 inject). Whether DV metadata **survives hardware av1_qsv encode** is **UNVERIFIED** and must be POC-gated. |
| **HDR10+ dynamic metadata passthrough (ST 2094-40)** | Parity with qsvencc `--dhdr10-info copy` | **HIGH / RISK** | Two possible paths, both unverified through av1_qsv: (a) in-band via ffmpeg `hdr_dynamic_metadata` side-data → T.35 OBU; (b) out-of-band `hdr10plus_tool` inject (supports AV1 raw/IVF) — but that is **not installed** (new dependency). POC-gated. |
| **Backend selection (ffmpeg default, qsvencc opt-in)** | Milestone requirement; both paths tested | LOW-MEDIUM | Flag `--backend ffmpeg\|qsvencc` **plus** env var (matches enpipe's `os.environ.get` convention, e.g. `ENPIPE_BACKEND`). Default `ffmpeg`. `chunk_command` becomes backend-dispatched (keep both pure functions). |

### Differentiators (Beyond Bare Parity)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Per-frame content verification of final `movie.obu`** | Defense-in-depth: catches *any* silent single-frame swap class (not just this bug) — directly protects the non-negotiable core value | MEDIUM | Handoff §7 explicitly recommends this. A VMAF/PSNR-vs-source gate on the concatenated output makes a silent swap physically un-shippable. Independent of backend choice; strengthens both. |
| **Dual-backend A/B parity harness** | Proves ffmpeg output is quality/size-equivalent to qsvencc and that qsvencc path still works | MEDIUM | Extends existing hardware-gated parity gate (`scratch/parity_encode.py`). Also the home for the corruption regression test (per-frame content check under parallel `JOBS`). |
| **Exact preset matching via `-qsv_params`** | Removes guesswork mapping qsvencc knobs → ffmpeg AVOptions | LOW | `av1_qsv` `-qsv_params key=val:...` is the escape hatch for `QPMax`, `GopRefDist`, `BRefType`, `ScenarioInfo` and anything without a first-class AVOption. Lets the ffmpeg preset track qsvencc's exactly. |

### Anti-Features (Seem Good, Create Problems)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Time-based `-ss`/`-t` trimming** | Simplest ffmpeg seek; "just seek to the timestamp" | qsvencc `--trim` is **frame-indexed**; time-based seek is VFR/fractional-fps fragile and off-by-one on frame boundaries → wrong frame counts → `die()`. Project doctrine: **frame number is the time coordinate, not seconds.** | Input-seek to keyframe (`-ss <kf_time>` before `-i`, fast) + **frame-indexed** `-vf trim=start_frame=(S-K):end_frame=(E-K)` (end exclusive) + `setpts`. Frame-exact, VFR-robust, keeps HW frames. |
| **Auto backend selection by source (magic)** | "DV source → qsvencc, else → ffmpeg" convenience | Hidden control flow; picks the *corrupting* encoder for exactly the hardest (DV) sources; hard to test; surprises users | Explicit `--backend` default `ffmpeg`; **document** that DV/HDR10+ may require choosing `qsvencc` if the ffmpeg POC fails. Keep selection observable. |
| **`JOBS=1` as the "fix"** | Serializing sessions is empirically 0% corrupt and trivial | Throws away the parallelism the milestone exists to *restore*; treats the symptom | The ffmpeg backend restores full-speed *correct* parallelism — that's the whole point. `JOBS=1` is only a documented emergency fallback for the qsvencc path. |
| **Software AV1 fallback (libsvtav1/libaom)** | Would trivially support DV/HDR10+ (documented) and dodge hardware quirks | Explicitly out of scope in PROJECT.md — toolchain is deliberately Intel-Arc-QSV-coupled; adds a whole encoder + quality/preset re-tuning surface | Stay on `av1_qsv`. If DV cannot survive av1_qsv, route DV to qsvencc (opt-in), not to a software encoder. |
| **Re-encoding/converting the DV profile** | "Normalize to profile 8.1/10.x" | Changes the deliverable; `--dolby-vision-rpu copy` is *passthrough* by design; conversion risks player incompat and is not the goal | Copy the RPU verbatim (profile 10.1 in, profile 10.1 out). |
| **Writing HDR10 static metadata into the `.obu`** | "Match qsvencc exactly, in-stream" | av1_qsv **cannot** write mastering-display/CLL OBUs (verified unsupported); chasing it is a dead end | Set HDR10 static metadata at the **mkv container level via mkvmerge** — same visible result to players. |

---

## Feature Dependencies

```
Backend selection (--backend flag + env)
    └──dispatches──> ffmpeg av1_qsv chunk_command
                          └──requires──> frame-exact seek/trim (keyframe input-seek + frame-indexed trim)
                                             └──requires──> existing keyframe table + compute_chunk_seek_trim (REUSED)
                          └──requires──> preset mapping (-global_quality/-g/-bf/-tile_*/-qsv_params)
                          └──requires──> 10-bit p010le decode/VPP path

DV RPU passthrough (av1) ──requires──> ffmpeg dovi_rpu BSF (av1)
                        ──requires──> [POC] DV side-data survives av1_qsv hardware encode   ← GATE
HDR10+ passthrough (av1) ──requires──> [POC] hdr_dynamic_metadata survives av1_qsv  OR  hdr10plus_tool (new dep)  ← GATE
HDR10 static metadata ──requires──> mkvmerge container-level tagging (NOT the encoder)

Per-frame content verification ──enhances──> both backends (defense-in-depth)
Corruption regression test ──requires──> handed-off reproducer (scenes 923/928/1129, off299 PSNR gate)

DV passthrough (ffmpeg) ──conflicts──> [if POC fails] ──> DV becomes qsvencc-only  ← decision branch
```

### Dependency Notes

- **Seek/trim reuses existing pure functions:** `compute_chunk_seek_trim` already yields
  `(kf_time, S-K, E-1-K)`. The ffmpeg path consumes the same tuple; only the CLI-string
  translation is new. This keeps the load-bearing, unit-tested arithmetic untouched.
- **DV and HDR10+ share one gating risk:** both are *per-frame* metadata that must survive a
  *hardware* encoder. Software AV1 encoders (libsvtav1/libaom) are documented to map them;
  hardware av1_qsv propagation is **undocumented**. A single early POC covers both.
- **HDR10 static ≠ HDR10+ dynamic:** static (mastering-display/CLL) is solved cleanly at the
  muxer; only the *dynamic* per-frame metadata carries the hardware-survival risk.
- **DV-fail branch:** if the POC shows DV RPU does not survive av1_qsv, DV sources become
  **qsvencc-only** (opt-in backend) and must pair with a corruption workaround (`--avsw` or
  serialized jobs) — i.e. DV parity moves out of the ffmpeg-default path. Requirements must
  carry this explicit fallback.

---

## MVP Definition

### Launch With (v1.2 core)

- [ ] **ffmpeg `av1_qsv` chunk backend** producing concatenable `.obu`, preset-matched (`-global_quality 23`, `-g 300`, `-bf`+`-qsv_params GopRefDist=6:BRefType=2`, `-tile_cols/rows 1`, 10-bit Main) — the milestone's reason to exist
- [ ] **Frame-exact seek/trim** via keyframe input-seek + frame-indexed trim; per-chunk + total `count_frames` guards pass — correctness invariant
- [ ] **Backend selection** (`--backend ffmpeg|qsvencc` + env, default ffmpeg; qsvencc path unchanged and still tested)
- [ ] **Concurrent-encode corruption regression test** (per-frame content verification under parallel `JOBS`, using the handed-off reproducer) — proves the fix
- [ ] **SDR + HDR10-static parity**: color signaling passthrough + mastering-display/CLL via mkvmerge container tagging
- [ ] **DV RPU + HDR10+ POC/spike** (see below) — even if the answer is "route to qsvencc," the answer must be *known* at launch, not assumed

### Add After Validation (v1.x)

- [ ] **Per-frame content verification of final `movie.obu`** (VMAF/PSNR gate) — defense-in-depth once the ffmpeg path is trusted
- [ ] **hdr10plus_tool out-of-band inject** — only if the in-band HDR10+ POC fails and HDR10+ parity is required (adds a dependency + per-chunk frame-range RPU mapping)

### Future Consideration (v2+)

- [ ] **`av1_vaapi` path** — untested cheaper alternative noted in the handoff; only if av1_qsv itself proves problematic
- [ ] **Host-side corruption fix for qsvencc** (kernel/i915→Xe, GuC/HuC) — would let qsvencc regain safe concurrency, but it's host-side and out of the container's control

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| ffmpeg av1_qsv chunk backend (preset parity) | HIGH | MEDIUM | P1 |
| Frame-exact seek/trim (frame-indexed, not time-based) | HIGH | HIGH | P1 |
| Corruption regression test (per-frame content) | HIGH | MEDIUM | P1 |
| Backend selection flag + env | HIGH | LOW | P1 |
| SDR color signaling parity | HIGH | LOW | P1 |
| HDR10 static via mkvmerge container tagging | HIGH | MEDIUM | P1 |
| **DV RPU passthrough POC (in-band dovi_rpu BSF)** | HIGH | HIGH (uncertain) | **P1 (spike)** |
| **HDR10+ passthrough POC** | MEDIUM | HIGH (uncertain) | **P1 (spike)** |
| Per-frame content verification of final output | HIGH | MEDIUM | P2 |
| Exact `-qsv_params` preset matching | MEDIUM | LOW | P2 |
| hdr10plus_tool out-of-band inject | MEDIUM | HIGH | P3 |
| av1_vaapi alternative | LOW | MEDIUM | P3 |

---

## Deep-Dive: The Load-Bearing Risks

### Seek/trim behavioral parity (HIGH complexity, but tractable)

| Aspect | qsvencc | ffmpeg av1_qsv | Parity approach |
|--------|---------|----------------|-----------------|
| Land on keyframe | `--seek floor_ms(kf_time)` | `-ss <kf_time>` **before** `-i` (fast/input seek → nearest keyframe ≤ ts) | Reuse `fmt_seek` floor-to-ms; input seek |
| Skip lead-in frames (S−K) after keyframe | `--trim (S-K):…` (frame index) | **frame-indexed** `trim=start_frame=(S-K)` (NOT `-ss` seconds) | `-vf trim` in decode-order n |
| Select exactly E−S frames | `--trim …:(E-1-K)` (inclusive) | `trim=…:end_frame=(E-K)` (exclusive) → same count | off-by-one: qsvencc inclusive, ffmpeg trim exclusive |
| Timestamp base | reset from seek point | without `-copyts`, PTS resets to 0 after input seek | leave PTS reset; `setpts=PTS-STARTPTS` if trim needs it |
| VFR robustness | frame numbers authoritative | **time-based `-t`/`-ss`-seconds drifts** | frame-indexed trim is VFR-safe |

Bottom line: parity is achievable and the existing keyframe arithmetic is reused verbatim, but
the naive `-ss <start> -t <dur>` (seconds) recipe **will** produce off-by-one frame counts on
some sources and trip the frame-count guard. The frame-indexed `trim` filter is mandatory. The
`count_frames` guard is the safety net that catches any translation error loudly.

### Dolby Vision RPU passthrough (HIGH risk — POC-gated)

- **Only viable AV1 path = ffmpeg `dovi_rpu` BSF.** Verified in-env: `dovi_rpu` BSF supports
  codecs `hevc av1`. `dovi_tool 2.3.3` `extract-rpu`/`inject-rpu` are **HEVC-only** — there is
  **no out-of-band AV1 DV inject tool**, so a file-based fallback does not exist.
- **The unknown:** the `dovi_rpu` BSF re-encodes RPU from `AVDOVIMetadata` carried as side
  data. FFmpeg docs only demonstrate DV/HDR10+ mapping for **software** encoders
  (libx265/libsvtav1/libaom). Whether **hardware av1_qsv propagates input-frame DV side data
  to output packets** (so the BSF can serialize it) is **undocumented and unverified**.
- **Verification method:** encode a DV chunk through av1_qsv + `-bsf:v dovi_rpu`, then confirm
  T.35 metadata OBUs are present (ffprobe `-show_frames` side_data / an OBU dump) and that a DV
  parser reads profile 10.1 back out. Frame-count must also still match.
- **If it fails:** DV → **qsvencc-only** (opt-in backend) + corruption workaround (`--avsw`,
  which the handoff confirms is 0/60 clean and preserves 10-bit+B-pyramid+DV/HDR at CPU-decode
  cost). This is the explicit out-of-scope-for-ffmpeg fallback the requirements must record.

### HDR10+ dynamic metadata (HIGH risk — POC-gated, but has an out-of-band escape)

- In-band path mirrors DV (ffmpeg `hdr_dynamic_metadata` side data → T.35 OBU
  `country_code=0xB5`, `provider_code=0x003C`, per the AOM HDR10+ AV1 spec) — same
  hardware-survival unknown.
- **Out-of-band escape exists (unlike DV):** `hdr10plus_tool` (quietvoid) can extract/inject
  HDR10+ into raw AV1 / IVF. Not installed → new dependency, plus per-chunk frame-range mapping
  of the metadata JSON. Only pursue if in-band fails and HDR10+ parity is required.

### HDR10 static metadata (MEDIUM — solved, mechanism shifts)

- av1_qsv **cannot** write mastering-display/CLL (verified unsupported upstream). Not a blocker:
  probe source and tag at the **mkv container level with mkvmerge** (all needed options verified
  present in v82). Same visible result. This is a clean, low-risk parity path — just a different
  component (muxer, not encoder) than qsvencc used.

---

## Competitor / Prior-Art Feature Analysis

| Feature | qsvencc (current) | ffmpeg av1_qsv (proposed) | Our approach |
|---------|-------------------|----------------------------|--------------|
| Concurrent-encode correctness | ~33–65% corrupt (10-bit+B+HW-decode) | 35/35 clean (verified) | ffmpeg becomes default |
| ICQ quality | `--icq 23` | `-global_quality 23` (verified) | direct map |
| Seek/trim | `--seek/--trim` frame-indexed (native) | input-seek + frame-indexed `trim` filter | reuse existing kf arithmetic |
| HDR10 static | `--master-display/--max-cll copy` (in-stream) | not supported in-stream | mkvmerge container tagging |
| HDR10+ dynamic | `--dhdr10-info copy` | in-band (unverified) / hdr10plus_tool | POC, then decide |
| DV RPU | `--dolby-vision-rpu copy` | `dovi_rpu` BSF (av1) — survival unverified | POC; fallback = qsvencc-only |

---

## Sources

- In-environment probes (HIGH): staged `ffmpeg n8.1.2` (`-h encoder=av1_qsv`, `-h bsf=dovi_rpu` → codecs `hevc av1`, `-h bsf=av1_metadata`, `-global_quality` present); `dovi_tool 2.3.3 --help` (HEVC-only subcommands); `mkvmerge v82.0 --help` (HDR10 container options); `hdr10plus_tool` not installed.
- `.planning/debug/scene-chunk-frame-mismatch.md` + `HANDOFF-qsvencc-frame-corruption.md` (HIGH): verified ffmpeg av1_qsv immunity (35/35), the triad trigger, and the `--avsw` fallback.
- av1_qsv HDR10 static unsupported (MEDIUM, corroborated): [intel/media-driver #1592](https://github.com/intel/media-driver/issues/1592), [intel/cartwheel-ffmpeg #221](https://github.com/intel/cartwheel-ffmpeg/issues/221).
- DV/HDR10+ in FFmpeg — software-encoder-only documentation (MEDIUM): [FFmpeg DeepWiki 5.5](https://deepwiki.com/FFmpeg/FFmpeg/5.5-dolby-vision-and-hdr-metadata), [dovi_rpu BSF patch](https://patchwork.ffmpeg.org/project/ffmpeg/patch/20240624172044.101722-9-ffmpeg@haasn.xyz/).
- HDR10+ AV1 OBU format + hdr10plus_tool AV1 support (MEDIUM): [AOM HDR10+ AV1 spec](https://aomediacodec.github.io/av1-hdr10plus/), [hdr10plus_tool #116](https://github.com/quietvoid/hdr10plus_tool/issues/116).
- [FFmpeg bitstream filters docs](https://ffmpeg.org/ffmpeg-bitstream-filters.html) (MEDIUM).

---
*Feature research for: ffmpeg av1_qsv scene-chunk encode backend (enpipe v1.2)*
*Researched: 2026-07-23*
