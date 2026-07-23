# Stack Research

**Domain:** ffmpeg `av1_qsv` encode backend for the enpipe scene-chunk AV1 pipeline (v1.2)
**Researched:** 2026-07-23
**Confidence:** HIGH (every mapping below was executed against the real BtbN ffmpeg **n8.1.2** binary on this Intel Arc A380 / iHD devcontainer, not inferred)

> **Verification note.** I ran ffmpeg n8.1.2-30-g45f1910444 (BtbN static GPL, downloaded from the exact URL in `.devcontainer/Dockerfile`) directly on `/dev/dri/renderD128` with `LIBVA_DRIVER_NAME=iHD`. Every "verified" row is backed by real encoder verbose output (`GopPicSize/GopRefDist/ICQQuality/BRefType/NumTile*`), a real 10-bit `-f obu` output, and a real two-chunk `cat` frame-count check. The system ffmpeg in the current image is 6.1.1 (dlstreamer base); **the ffmpeg-8.1 layer from the Dockerfile is NOT yet built into the running container** (`/opt/ffmpeg-8.1` absent, `ffmpeg-8.1` not on PATH) — the image must be rebuilt before this backend can run in-place. I verified with a locally-fetched copy of the identical build.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| ffmpeg `av1_qsv` encoder | ffmpeg **n8.1.2** (BtbN static GPL, already staged in Dockerfile) | AV1 HW encode per scene-chunk — the corruption-immune replacement for `qsvencc` under concurrency | Empirically 35/35 clean under 3-way/5-way concurrency (per-component `AVHWFramesContext` pools, no cross-process 10-bit reference aliasing). Same iHD/oneVPL runtime, full GPU speed. |
| ffmpeg `h264_qsv` / `hevc_qsv` decode + `-hwaccel qsv` | same build | HW decode of the source into QSV video surfaces feeding the encoder | Reproduces the `--avhw --va` decode leg of qsvencc; keeps decode on-GPU. Verified: `h264_qsv` decode → `vpp_qsv` → `av1_qsv` → `-f obu` = 24/24 frames. |
| `vpp_qsv` filter | same build | Force **P010** (10-bit) surface format between decode and encode (`vpp_qsv=format=p010le`) | This is how `--output-depth 10` is achieved in ffmpeg — the encoder emits AV1 Main 10-bit only when fed p010le surfaces. Verified: output `pix_fmt=yuv420p10le`, `profile=Main`. |
| `obu` muxer (`-f obu`) | same build | Emit a **raw AV1 low-overhead OBU elementary stream** (`.obu`) so chunks stay byte-concatenable | New/confirmed present in 8.1. Verified: `cat chunk0.obu chunk1.obu` → 48/48 frames decode cleanly. **This preserves the load-bearing raw-.obu + `cat` + mkvmerge invariant.** |
| `dovi_rpu` bitstream filter | same build | Dolby Vision RPU handling on **hevc AND av1** streams | Present in 8.1 (absent in system 6.1.1). BUT see the DV coverage risk below — it rewrites/strips RPU **already present** in a stream; it does **not inject** an external RPU into freshly-encoded AV1. |
| `av1_metadata` bitstream filter | same build | Force color signalling (primaries / transfer / matrix / range / chroma position) into the AV1 `color_config` | Needed because `av1_qsv` does not reliably write `color_primaries`/`transfer_characteristics` into the bitstream (verified: matrix survived, primaries+transfer came back `unknown`). Belt-and-suspenders alongside container-level tags. |

### Supporting Libraries / Tools

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| `mkvmerge` (mkvtoolnix) | already installed | Final mux + **container-level HDR10 static + color signalling** | The pragmatic injection point for HDR10 mastering-display / max-CLL and color tags on the ffmpeg path (`--colour-primaries`, `--colour-transfer-characteristics`, `--colour-matrix-coefficients`, `--max-content-light`, `--max-frame-light`, `--chromaticity-coordinates`, `--white-colour-coordinates`, `--max-luminance`, `--min-luminance`). Already the terminal stage. |
| `ffprobe` (8.1) | staged build | Read source HDR/color side-data to translate into either `av1_metadata` values or `mkvmerge` flags | Replaces qsvencc's internal `--...  copy` semantics: qsvencc reads metadata itself; on the ffmpeg path enpipe must probe the source and re-assert values. `detect_hdr()` already does the ffprobe side-data read — extend it to emit ffmpeg/mkvmerge values instead of qsvencc flags. |
| `hdr10plus_tool` (quietvoid) | **NOT installed** | Extract + inject HDR10+ (SMPTE 2094-40) dynamic metadata into AV1 OBUs | Only needed **if** HDR10+ dynamic passthrough must work on the ffmpeg path (see gap below). Would be a new Dockerfile dependency, analogous to `dovi_tool`. |
| `qsvencc` (Rigaya) | already installed | **Retained opt-in backend** | Keep as the selectable non-default backend AND as the **only** path that currently carries DV RPU / HDR10+ into AV1. Run corruption-safe for those (JOBS=1 or `--avsw`). |
| `dovi_tool` 2.3.3 | already installed | (vestigial for AV1) | Verified **HEVC-only**: `extract-rpu`/`inject-rpu` operate on HEVC bitstreams; no AV1 injection subcommand. Cannot bridge DV RPU into AV1. Keep for HEVC-source RPU inspection only. |

### Development / Test Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `ffmpeg -lavfi psnr` (8.1) | Per-frame content verification for the concurrent-correctness regression test | The handoff reproducer already relies on decoding an offset frame and PSNR-vs-reference (<30 dB = corrupt). Reuse for the required v1.2 corruption-free proof. |
| `intel_gpu_top`, `hyperfine` | GPU-engine utilisation + reproducible throughput benchmarking | Already in the Dockerfile debug layer; use to confirm full-speed parallel `JOBS` on the ffmpeg path. |

## Installation

```bash
# ffmpeg 8.1 is ALREADY specified in .devcontainer/Dockerfile (BtbN static GPL,
# side-by-side as ffmpeg-8.1 / ffprobe-8.1 in /opt/ffmpeg-8.1). ACTION REQUIRED:
# rebuild the devcontainer image — the running container predates that layer.
#   /opt/ffmpeg-8.1/bin/ffmpeg  ->  ffmpeg-8.1
#   /opt/ffmpeg-8.1/bin/ffprobe ->  ffprobe-8.1

# Optional NEW dependency, ONLY if HDR10+ dynamic passthrough is required on the
# ffmpeg path (not currently installed):
#   quietvoid/hdr10plus_tool  (static musl binary from GitHub releases, same
#   install pattern as dovi_tool)

# No Python package changes required. Backend selection is a chunk_command
# dispatch + a new ffmpeg command builder; scenedetect/numpy/uv.lock unchanged.
```

---

## THE FLAG MAPPING (qsvencc → ffmpeg av1_qsv)

Every row marked **[verified]** was confirmed from real n8.1.2 encoder verbose output on this GPU.

| qsvencc knob | Meaning | ffmpeg av1_qsv equivalent | Status |
|---|---|---|---|
| `--avhw --va -i SRC` | HW VA decode into video surfaces | `-init_hw_device qsv=hw:/dev/dri/renderD128 -hwaccel qsv -hwaccel_output_format qsv -c:v h264_qsv -i SRC` (pick decoder by source codec: `h264_qsv`/`hevc_qsv`) | **[verified]** full chain 24/24 frames |
| `-c av1` | AV1 encode | `-c:v av1_qsv` | **[verified]** |
| `--icq 23` | Intelligent Constant Quality, q=23 | `-global_quality 23` (with **no** `-b:v`) → auto-selects ICQ | **[verified]** "Using the intelligent constant quality (ICQ) ratecontrol method … ICQQuality: 23" |
| `--qp-max 100` | Max QP cap under ICQ | **No clean equivalent.** `-qmax` is honoured only in CQP mode, not ICQ. Low impact — a loose cap that rarely binds under ICQ. Omit; document as intentionally dropped. | **[verified-absent]** — see coverage risks |
| `--output-depth 10` + `--profile main` | 10-bit (P010) Main | `-vf vpp_qsv=format=p010le` (feeds p010le) + `-profile:v main` | **[verified]** output `yuv420p10le`, `profile=Main`, "profile: av1 main; level: 30" |
| `--gop-len 300` | GOP size | `-g 300` | **[verified]** "GopPicSize: 300" |
| `--gop-ref-dist 6` | 5 B-frames between references (GopRefDist = bf+1) | `-bf 5` | **[verified]** `-bf 5` → "GopRefDist: 6" |
| `--b-pyramid` | Pyramid B-reference structure | **No flag needed — automatic.** av1_qsv sets `BRefType: pyramid` by default whenever B-frames are present | **[verified]** "BRefType: pyramid" appeared with no explicit option |
| `--tile-col 1 --tile-row 1` | 1×1 tiling | `-tile_cols 1 -tile_rows 1` | **[verified]** "NumTileColumns: 1; NumTileRows: 1" |
| `--tune perceptual` | Perceptual/psy tuning (mfxExtTuneEncodeQuality) | **No equivalent.** av1_qsv exposes no `-tune`; not reachable via `-qsv_params`. Minor quality-character delta only. | **[verified-absent]** |
| `--scenario-info archive` | mfx `ScenarioInfo = archive` hint | **No equivalent.** `-qsv_params "ScenarioInfo=5"` is **rejected** ("Failed to set parameter: ScenarioInfo", encoder open fails). Minor RC-tuning hint only. | **[verified-rejected]** |
| `--colorrange/--colormatrix/--colorprim/--transfer/--chromaloc auto` | Copy color signalling from source | Probe source (ffprobe) → set `-color_range/-colorspace/-color_primaries/-color_trc` on output **and** force into bitstream via `-bsf:v av1_metadata=color_primaries=..:transfer_characteristics=..:matrix_coefficients=..:color_range=..:chroma_sample_position=..` **and/or** assert at container level in mkvmerge | **[partial-verified]** matrix landed in bitstream; primaries+transfer came back `unknown` from av1_qsv alone → BSF / container assertion required |
| `--master-display copy --max-cll copy` (HDR10) | Static HDR10 metadata | **Not emitted by av1_qsv.** Recommended: assert at **container level** via mkvmerge (`--max-content-light`, `--max-frame-light`, `--chromaticity-coordinates`, `--white-colour-coordinates`, `--max-luminance`, `--min-luminance`), probed from source. No ffmpeg BSF inserts MDCV/CLL OBUs in 8.1. | **coverage risk (tractable)** |
| `--dhdr10-info copy` (HDR10+) | Dynamic SMPTE 2094-40 | **No ffmpeg-native path.** av1_qsv does not insert T.35 HDR10+ OBUs; `av1_metadata` has no such option. Requires external `hdr10plus_tool` (not installed) or keep on qsvencc. | **coverage GAP** |
| `--dolby-vision-rpu copy --dolby-vision-profile 10.1` (DV) | Carry DV RPU into AV1 | **No ffmpeg-native path.** `dovi_rpu` BSF only rewrites/strips RPU **already in** a stream — it cannot inject from source; `dovi_tool` is HEVC-only. av1_qsv drops DV side-data. | **coverage GAP — the load-bearing risk** |
| `--seek HH:MM:SS.mmm` | Seek to source keyframe K | `-ss HH:MM:SS.mmm` **before** `-i` (keyframe-accurate input seek) | **[verified]** (chain used `-ss`) |
| `--trim first:last` (frames from K, inclusive) | Output window `[first, last]` | `trim=start_frame=first:end_frame=last+1,setpts=N/FRAME_RATE/TB` filter (general, handles first>0). When `first==0` (K==scene start), simply `-frames:v (last+1)` | **[verified for first=0]**; `trim` filter is the general form — validate on real media |
| `-o OUT.obu` | Raw AV1 elementary stream | `-f obu OUT.obu` | **[verified]** cat-concatenation stays frame-valid |
| `--psnr --ssim` | Encoder-computed metrics | Not on encoder; compute externally with `ffmpeg -lavfi psnr/ssim` (already required for the corruption test; qsvencc's own metrics needed OpenCL anyway) | n/a |

### Concrete per-chunk ffmpeg command (SDR, replicating the qsvencc preset)

```bash
ffmpeg-8.1 -v error \
  -init_hw_device qsv=hw:/dev/dri/renderD128 \
  -hwaccel qsv -hwaccel_output_format qsv \
  -c:v h264_qsv -ss <seek_HH:MM:SS.mmm> -i <SRC> \
  -vf "vpp_qsv=format=p010le" -frames:v <E-S> \
  -c:v av1_qsv -global_quality 23 -g 300 -bf 5 \
  -tile_cols 1 -tile_rows 1 -profile:v main -preset medium \
  -f obu <OUT.obu>
```
- `-preset medium` (=TargetUsage 4) is added to lock parity with qsvencc's default balanced TU4 (both default to TU4 in testing, but pin it explicitly).
- For `first>0` chunks, replace `-frames:v <E-S>` with `-vf "vpp_qsv=format=p010le,trim=start_frame=<first>:end_frame=<last+1>,setpts=N/FRAME_RATE/TB"`.
- Decoder token (`h264_qsv`) must be chosen from the source codec (h264/hevc/…); enpipe already probes the source.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| ffmpeg `av1_qsv` default | Retain `qsvencc` default at JOBS=1 or `--avsw` | If DV/HDR10+ fidelity must be byte-for-byte with today and the content is DV/HDR10+ — route those to qsvencc (it is the only path that carries that metadata into AV1). |
| `-f obu` raw stream + `cat` + mkvmerge | `-f ivf` / per-chunk mkv + concat demuxer | Only if the raw-OBU `cat` invariant ever fails on a specific source; not needed — `cat` verified valid. Do NOT switch: it would break the load-bearing byte-concat design. |
| Container-level HDR10 via mkvmerge | Bitstream MDCV/CLL OBUs | No ffmpeg 8.1 tool inserts AV1 MDCV/CLL OBUs; container-level is the only clean route and is widely player-honoured. |
| av1_qsv (oneVPL) | `av1_vaapi` (pure VA-API, no oneVPL) | Untested escape hatch noted in the bug handoff; only investigate if av1_qsv ever shows the same aliasing (it does not). Not for v1.2. |

## What NOT to Use / NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `dovi_tool inject-rpu` on `.obu` | HEVC-only (verified 2.3.3) — silently inapplicable to AV1 | Keep DV content on the qsvencc backend, or add `hdr10plus_tool`-style AV1 tooling only if DV-on-ffmpeg is truly required |
| `-qsv_params "ScenarioInfo=…"` / tune hacks | Rejected by av1_qsv (verified) — encoder open fails | Drop `--scenario-info`/`--tune`; accept minor RC-tuning delta |
| Re-deriving seek/trim keyframe arithmetic | `compute_chunk_seek_trim` / EBML Cues parser are DONE + validated | Reuse `kf_before`/`compute_chunk_seek_trim`; add only a thin translator from `(seek, "first:last")` → ffmpeg `-ss` + frame window |
| Switching output away from raw `.obu` | Breaks the byte-`cat` + mkvmerge invariant | Keep `-f obu`; it is verified cat-valid |
| Relying on av1_qsv to emit color/HDR into the bitstream | It drops primaries/transfer and all HDR static/dynamic metadata | Assert via `av1_metadata` BSF (color) + mkvmerge (HDR10 static / color container tags) |
| `-qmax` to emulate `--qp-max 100` under ICQ | Ignored in ICQ mode | Omit; it is a non-binding cap |

## Stack Patterns by Variant (backend routing recommendation)

**If source is SDR or HDR10 (static):**
- Use ffmpeg `av1_qsv` (new default). Color via `av1_metadata` BSF; HDR10 mastering-display/CLL via mkvmerge container tags probed from source.
- Full-speed parallel `JOBS` — corruption-immune.

**If source is Dolby Vision or HDR10+ (dynamic):**
- **No clean ffmpeg-only path in 8.1.** Route to the retained `qsvencc` backend (the only path that carries DV RPU / HDR10+ into AV1), run corruption-safe (JOBS=1 or `--avsw`), OR add `hdr10plus_tool`/an AV1-DV-injection tool as new dependencies and treat as a follow-up. This is the decision the roadmap must make explicitly — it is the load-bearing risk called out in PROJECT.md.

**If maximum parity/simplicity for v1.2 scope:**
- Ship ffmpeg default for SDR+HDR10; declare DV/HDR10+ handled by the opt-in qsvencc backend. Preserves today's coverage without over-building.

## Version Compatibility

| Component | Compatible With | Notes |
|-----------|-----------------|-------|
| ffmpeg n8.1.2 BtbN GPL | iHD 26.2.x / oneVPL (vpl-gpu-rt) in dlstreamer base | `av1_qsv` + `h264_qsv`/`hevc_qsv` + `vpp_qsv` all initialise against `iHD` on this A380 (VA-API 1.23) — verified live |
| `-f obu` output | mkvmerge (mkvtoolnix) | `cat`'d raw-OBU stream muxes as today; mkvmerge is where color/HDR container tags get asserted |
| `dovi_rpu` BSF | hevc, av1 | Present 8.1 / absent 6.1.1 — but injection-from-source is NOT a capability (rewrite/strip only) |
| BtbN `latest` rolling tag | — | Non-deterministic (Dockerfile documents this): asset name stable, contents roll daily (currently n8.1.2). No SHA pin. Acceptable per existing project stance, but note the encoder-flag surface could shift on rebuild. |

## Integration Points (existing code)

- `src/enpipe/encoding/chunk.py::chunk_command` — add backend dispatch; new pure `ffmpeg_chunk_command()` builder alongside the qsvencc one (keep it a pure function, no subprocess, per project convention).
- `src/enpipe/encoding/hdr.py::detect_hdr` — currently emits qsvencc flags; add a variant emitting ffmpeg (`av1_metadata`) + mkvmerge color/HDR values from the same ffprobe side-data reads.
- `src/enpipe/encoding/pipeline.py:183` (`hdr_flags = detect_hdr(...)`), `:206–208` (chunk cmd build), `:320` (mkvmerge mux — inject container HDR/color tags here for the ffmpeg path).
- `src/enpipe/encoding/pipeline.py:41` (`JOBS`) — ffmpeg path restores safe parallelism; qsvencc path should carry a safety default (JOBS=1) when used for DV/HDR10+.
- `chunk.py::count_frames` (ffprobe packet count) invariant — unchanged; works on `-f obu` output (verified 48/48).
- Preflight `shutil.which` loop (`pipeline.py:107`) — add `ffmpeg-8.1`/`ffprobe-8.1` (and gate on the image rebuild).

## Open Questions / Flags for the Roadmap

1. **DV RPU on the ffmpeg path = unsolved with in-container tooling.** `dovi_rpu` BSF cannot inject; `dovi_tool` is HEVC-only. Decision needed: (a) keep DV on qsvencc (recommended, zero new deps), or (b) invest in AV1 DV injection tooling. This is the "whole reason qsvencc was chosen" risk — do not let the roadmap assume `dovi_rpu` BSF closes it.
2. **HDR10+ dynamic** similarly has no in-container ffmpeg path; needs `hdr10plus_tool` or stays on qsvencc.
3. **Color primaries/transfer** are dropped by av1_qsv into the bitstream — confirm the `av1_metadata` BSF + mkvmerge container-tag combo satisfies the HDR10 validation fixtures (Phase-4 TEST-04 territory).
4. **`first>0` seek/trim** (keyframe before scene start) only tested logically here (first=0 verified live); the `trim`-filter frame-accuracy must pass the existing hardware parity gate on real media.
5. **Image rebuild is a prerequisite** — ffmpeg-8.1 is specified but not present in the running container.

## Sources

- **Real ffmpeg n8.1.2-30-g45f1910444 (BtbN static GPL)** executed on this Intel Arc A380 / iHD (VA-API 1.23) — HIGH: encoder verbose (ICQ/GopPicSize/GopRefDist/BRefType/NumTile*/profile/level), 10-bit `-f obu` output, two-chunk `cat` frame-count, `qsv_params ScenarioInfo` rejection, HW-decode→vpp→encode chain.
- `ffmpeg -h encoder=av1_qsv` / `-h bsf=dovi_rpu` / `-h bsf=av1_metadata` / `-h muxer=obu` (8.1) — HIGH: option surface, `dovi_rpu` supported codecs = "hevc av1", obu muxer presence.
- `dovi_tool 2.3.3 --help` — HIGH: extract-rpu/inject-rpu are HEVC-only, no AV1 injection.
- `.devcontainer/Dockerfile` (ffmpeg-8.1 BtbN layer), `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` (ffmpeg immune 35/35; trigger triad), `src/enpipe/encoding/{chunk,hdr,keyframes,pipeline}.py` — HIGH: current command + integration points.

---
*Stack research for: ffmpeg av1_qsv backend (enpipe v1.2)*
*Researched: 2026-07-23*
