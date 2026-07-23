# DV RPU into AV1 — Feasibility (replicating qsvencc's mechanism outside qsvencc)

**Domain:** Dolby Vision RPU carriage into freshly-encoded AV1, for enpipe's ffmpeg `av1_qsv` default backend (v1.2 Phase 5)
**Researched:** 2026-07-23
**Confidence:** HIGH on the mechanism (read from the installed binary's symbol table + upstream changelogs); MEDIUM on the "build-your-own-injector" effort estimate.

---

## VERDICT

**A mechanism to attach DV RPU to fresh AV1 provably exists — it is `libdovi` (quietvoid's `dovi` Rust crate, C-API) writing an ITU-T T.35 metadata OBU per frame.** qsvencc does *not* have secret sauce: the installed `qsvencc` binary **statically bundles `libdovi` 3.1.2 + `hdr10plus_rs`** and adds one small piece of its own (the AV1 T.35 OBU *header* constant `av1_itut_t35_header_dovirpu`). That is the entire trick. It is reachable outside qsvencc **only at the library level** — **no packaged CLI in this container (or upstream) injects DV RPU into a raw AV1 `.obu` today.**

Therefore, for enpipe's ffmpeg-default path, there are exactly two honest options:

- **(Recommended, zero new dev) Route DV to the qsvencc backend, made corruption-safe with `--avsw`.** qsvencc *is* the packaged libdovi injector; `--avsw` breaks the corruption triad (0/60 clean per the handoff) while preserving 10-bit + B-pyramid + DV. The raw-`.obu` concat invariant is preserved (qsvencc emits `.obu`), and per-frame/B-reorder alignment is handled *inside* qsvencc (correct today — it has display-order POC in hand during encode). **This proves the "there is a way" directive without touching the ffmpeg path.**
- **(True DV-on-ffmpeg, but a build project) Post-process the ffmpeg `av1_qsv` `.obu` with a custom libdovi-based injector.** Same mechanism qsvencc uses, decoupled: `dovi_tool extract-rpu` (HEVC source → `RPU.bin`) → a small tool linked against `libdovi ≥3.2.0` (`dovi_write_av1_rpu_metadata_obu_t35_complete`) that wraps each RPU in a T.35 metadata OBU and interleaves it per-frame **in display order** into the `.obu`. Feasible and standards-clean, but it is **new C/Rust code + a new dependency**, and the per-frame display-order alignment through B-pyramid reorder is the real risk (exactly Pitfall 3).

**Overturning the stale conclusion:** the earlier "DV RPU cannot be injected into fresh AV1 with in-container tools" is **half wrong and now precisely bounded**:
- FALSE that no mechanism exists — libdovi does it, and qsvencc bundles libdovi to do exactly this for AV1 today.
- TRUE that **no standalone CLI** injects DV RPU into a raw AV1 elementary stream: `dovi_tool` CLI 2.3.3 (latest) is HEVC-only, `ffmpeg`'s `dovi_rpu` BSF is strip/compress-only (cannot inject), and **`hdr10plus_tool` 1.7.2 CLI is *also* HEVC-only** (correcting a claim in the current SUMMARY/STACK/FEATURES that it can inject into AV1 — it cannot; that capability is library-only in `hdr10plus_rs`).

---

## Ranked candidate paths

| # | Path | In-container today? | Raw-`.obu` compatible? | Per-frame / B-reorder alignment | Effort | Confidence |
|---|------|--------------------|------------------------|-------------------------------|--------|-----------|
| **1** | **qsvencc DV backend + `--avsw`** (SW decode, HW AV1 encode, `--dolby-vision-rpu copy` or `<file>` `--dolby-vision-profile 10.1`) | **Yes** (installed, bundles libdovi 3.1.2) | Yes — qsvencc emits `.obu`; concat unchanged | **Handled internally** (correct today) | **None** (already the recommended fallback) | **HIGH** — verified: qsvencc option surface + libdovi symbols live; `--avsw` 0/60 per handoff |
| **2** | **ffmpeg `av1_qsv` `.obu` + custom libdovi T.35 injector** (post-process; RPU from `dovi_tool extract-rpu` on HEVC source) | **No** — needs building a tool + adding `libdovi ≥3.2.0` as a dep | Yes — operates on `.obu`, but must slice RPU per chunk and re-align | **HIGH RISK** — must parse AV1 OBU headers to map display→decode order; chunk-boundary RPU slicing | **HIGH** (new C/Rust code) | **MEDIUM** — API exists (verified in changelog + qsvencc symbols); no reference CLI proves it end-to-end |
| **3** | **ffmpeg `av1_qsv` + `-bsf:v dovi_rpu`** (in-band, hoping av1_qsv passes DV side-data through) | Partially — needs ffmpeg-8.1 built (absent now) | Yes | N/A | Low | **LOW / likely dead** — BSF is **strip/compress-only, no inject** (verified from docs); and av1_qsv drops DV side-data |
| **4** | **`dovi_tool` CLI `inject-rpu`/`mux` on `.obu`** | No | — | — | — | **DEAD** — CLI is HEVC-only (verified live 2.3.3 + maintainer: "not supported for processing files yet") |
| **5** | **`hdr10plus_tool` CLI inject into AV1** (HDR10+, for contrast) | No | — | — | — | **DEAD** — CLI 1.7.2 is HEVC-only (verified upstream). Corrects prior "AV1 inject" claim. |

---

## qsvencc mechanism — reverse-engineered from the installed binary

Read directly from `strings /usr/bin/qsvencc` (QSVEncC 8.22 r4385, the installed build) — **verified-live**, not inferred:

**1. It statically bundles `libdovi` (quietvoid's `dovi` crate) and `hdr10plus_rs`.**
- Version banner symbol: `libdovi    : %s`; embedded version strings `3.1.2` / `v3.1.0` → **libdovi 3.1.2**.
- Rust demangled symbols present: `dovi::rpu::dovi_rpu::DoviRpu`, `dovi::rpu::rpu_data_mapping::RpuDataMapping::parse`, `dovi::c_structs::…`, and crucially **`dovi::av1::emdf::write_emdf_container_with_dovi_rpu_payload`** — the AV1 EMDF payload writer.
- HDR10+ counterpart: **`hdr10plus_rs_write_av1_metadata_obu_t35_complete`** — this is how `--dhdr10-info copy` writes HDR10+ into AV1 (same library-level trick, different metadata).

**2. It supplies its own AV1 T.35 OBU *header*** — local C++ symbol `av1_itut_t35_header_dovirpu` (the `_ZL…` prefix = file-local, i.e. rigaya's `rgy` shared code, not libdovi). Validation strings confirm the exact wire format it emits:
- `itu_t_t35_terminal_provider_code == 0x3B` (0x3B = Dolby), `itu_t_t35_terminal_provider_oriented_code == 0x800`, `emdf_payload_id == 31`, `emdf_payload_id_ext == 225`, `emdf_version == 0`, `key_id == 6`.
- i.e. it builds an `OBU_METADATA` with `metadata_type = METADATA_TYPE_ITUT_T35`, country code `0xB5`, Dolby provider code, wrapping an **EMDF container** whose payload is the DV RPU — precisely the AOM/Dolby "DV in AV1" T.35 carriage.

**3. Where the RPU comes from and how it's aligned:**
- `--dolby-vision-rpu copy` → the avhw/avsw **reader demuxes DV from the source** and hands each frame's RPU to the encoder as side data. Symbol/string evidence: `Dolby Vision enabled, but received frame without AV_FRAME_DATA_DOVI_METADATA` (ffmpeg-style side-data naming; qsvencc's libavcodec-based reader parses source DV).
- `--dolby-vision-rpu <file>` → reads an **external RPU `.bin`** (the same byte format `dovi_tool extract-rpu` produces from an HEVC DV source). This is the decoupled path that matters: RPU source is independent of the encode.
- Profile handling: `convert_dovi_rpu(vector<u8>, RGYDOVIProfile, RGYDOVIRpuConvertParam)` + `getDOVIProfile`/`list_dovi_profile` — it can convert the RPU profile (e.g. HEVC profile 8.1 RPU → **AV1 profile 10.1**, which is what `hdr.py` requests). AV1 DV = "profile 10.x"; the RPU bytes are the same, the container/OBU carriage differs.
- **Alignment:** because qsvencc owns the frames in-flight during encode, it knows each frame's display order (POC) and simply attaches the matching RPU's T.35 OBU to that frame's temporal unit **before** encoding output — reorder is a non-issue for it. This is exactly the property a `.obu` post-processor loses and must reconstruct.

**Bottom line:** qsvencc's `--dolby-vision-rpu copy … --dolby-vision-profile 10.1` for AV1 = *bundled libdovi RPU parse/convert* + *libdovi EMDF payload writer* + *rigaya's T.35 OBU header* + *per-frame interleave in display order*. Nothing here is Intel/QSV-specific; it is a library operation on the elementary stream. (Source: `rigaya/QSVEnc` shared `rgy` code — `rgy_bitstream`/`rgy_dovi_metadata` — linked against `libdovi`/`hdr10plus_rs`; confirmed via the installed binary's symbol table.)

---

## Per-path detail

### Path 1 — qsvencc DV backend, `--avsw` (RECOMMENDED)

This is the "prove a way exists" answer, already the handoff's Option A. Command sketch (from `chunk.py` + `hdr.py`, swap decode leg):

```bash
qsvencc --avsw -i <SRC> -c av1 \
  --icq 23 --qp-max 100 --output-depth 10 --profile main \
  --gop-len 300 --gop-ref-dist 6 --b-pyramid --tile-col 1 --tile-row 1 \
  --dolby-vision-rpu copy --dolby-vision-profile 10.1 \
  --master-display copy --max-cll copy \
  --seek <kf_time> --trim <S-K>:<E-1-K> -o chunk.obu
```

- **`--avsw`** replaces `--avhw --va`: SW decode + HW AV1 encode. Breaks the decode leg of the corruption triad → **0/60 clean** (handoff §7) at CPU-decode cost (single-session ~310→125 fps). Full 10-bit + B-pyramid + DV preserved.
- Raw-`.obu` invariant: **preserved** — output is `.obu`, byte-concat as today.
- Alignment: **correct today**, done inside qsvencc.
- Availability: **installed now** (no rebuild, no new dep). Bundles libdovi 3.1.2.
- Enpipe fit: routes cleanly as the `qsvencc` opt-in backend for DV sources; keep `--jobs 1` or `--avsw` for correctness. `hdr.py::detect_hdr` already emits these exact flags.
- Caveat: for `--dolby-vision-rpu copy` the **source must be a real DV source** whose DV the reader can demux; profile 7 (dual-layer) inputs need `--dolby-vision-profile 8.1`-style conversion (see QSVEnc #222) — but enpipe targets single-layer BL+RPU → profile 10.1 AV1, which is the supported case ("BL+RPU only; BL+EL not supported").

### Path 2 — ffmpeg `av1_qsv` `.obu` + custom libdovi injector (TRUE DV-on-ffmpeg)

The only way to keep DV on the corruption-free ffmpeg default encoder. Pipeline:

```
HEVC DV source ──dovi_tool extract-rpu──> RPU.bin        (works: HEVC extract is supported)
ffmpeg av1_qsv  ─────────────────────────> movie.obu      (clean AV1, no DV)
RPU.bin + movie.obu ──[custom injector]──> movie_dv.obu   (T.35 metadata OBUs, per-frame)
```

The `[custom injector]` is the missing piece. It must:
1. Link `libdovi ≥3.2.0` and call **`dovi_write_av1_rpu_metadata_obu_t35_complete`** (C-API) — the exact function qsvencc's bundled libdovi provides — to turn each RPU into a complete AV1 `OBU_METADATA`/`METADATA_TYPE_ITUT_T35` payload (changelog: `av1` module added 3.2.0; `_complete` variant 3.3.0; crate now at 3.4.0).
2. Parse the AV1 `.obu` temporal units, and for each *shown* frame insert the matching RPU's metadata OBU **in display order** (respecting `show_frame`/`show_existing_frame`/`order_hint`). The metadata OBU must sit in the frame's temporal unit ahead of the frame OBU.
3. Handle enpipe's **per-chunk** reality: RPU stream is global/display-order; each `.obu` chunk covers `[S,E)` in display order but stores frames in **decode order** with B-pyramid reorder. Slice `RPU[S:E]` per chunk and map to decode-order positions.

- Raw-`.obu` invariant: **compatible** — you can inject per chunk (before concat) or once on `movie.obu` (after concat). Post-concat-once is simpler (single display-order timeline) and avoids chunk-boundary RPU seams.
- **Alignment risk: HIGH** — this is Pitfall 3 made concrete. A single off-by-one maps every RPU to the wrong frame while frame-count still passes. Mitigation: inject on the final `movie.obu` (one monotone display timeline), and verify RPU-count == frame-count + spot-check L1 on reordered/boundary frames.
- Availability: **not in container** — needs `libdovi.so`/crate + writing the tool (Rust binding to `dovi` crate is the least-effort route; the C-API `dovi_write_av1_rpu_metadata_obu_t35_complete` is stable). New Dockerfile dependency, analogous to how `dovi_tool` is already fetched.
- Effort: this is a **spike/build**, not a config change. It reimplements the ~200 lines qsvencc already ships. Only pursue if DV *must* ride the ffmpeg encoder rather than qsvencc.

### Path 3 — in-band `dovi_rpu` BSF (LIKELY DEAD)

`ffmpeg -bsf:v dovi_rpu` options are **`strip` + `compression` only** (verified from the official BSF docs). It manipulates RPU **already present** in a HEVC/AV1 stream; there is **no `rpu_file=` / inject** capability. Combined with av1_qsv dropping DV side-data (no DOVI passthrough from a hardware encoder), there is nothing for the BSF to serialize. Not a path. (Also: ffmpeg-8.1 is specified in the Dockerfile but **not built into the running container** — `/opt/ffmpeg-8.1` absent — so it cannot even be probed in-place until an image rebuild.)

### Paths 4 & 5 — dovi_tool / hdr10plus_tool CLI (DEAD, and a correction)

- `dovi_tool` **2.3.3 is the current latest release** (published 2026-07-12; the GitHub "latest" API returns 2.3.3). Live-probed subcommands `inject-rpu` ("…HEVC encoded bitstream"), `extract-rpu` ("…HEVC file"), `mux` ("…HEVC bitstream") — **HEVC-only**. Maintainer in discussion #302: AV1 file processing "not supported yet." The AV1 T.35 writers exist **only in the `dolby_vision` library** (crate 3.2.0+), never wired to the CLI.
- `hdr10plus_tool` **1.7.2 CLI is also HEVC-only** (extract/inject/remove all "HEVC"). **This corrects the current SUMMARY/STACK/FEATURES claim that hdr10plus_tool can inject HDR10+ into raw AV1/IVF** — it cannot at CLI level; that is library-only (`hdr10plus_rs`, which qsvencc bundles). So **HDR10+ has the *same* gap as DV**, not an easier out-of-band escape. The only in-container AV1 HDR10+ writer is, again, qsvencc (`--dhdr10-info copy`).

---

## Verification method (did the RPU survive in AV1, correctly aligned?)

No single clean tool reads DV back out of an AV1 `.obu` (dovi_tool can't parse AV1). Use a layered check:

1. **Count guard:** number of `METADATA_TYPE_ITUT_T35` OBUs with Dolby provider code (0x3B) **== frame count**. A raw OBU walk (or `ffprobe -show_frames` side-data on ffmpeg-8.1, which parses AV1 T.35 → `AV_FRAME_DATA_DOVI_METADATA`) gives per-frame presence. Mismatch = misalignment/drop.
2. **Presence + profile:** `mediainfo` (installed) on the final `.mkv`/`.obu` should report `HDR format: Dolby Vision, Version 1.0, dvhe/dav1…, Profile …` — confirms DV is signalled and the profile (expect AV1 profile 10.1). Cross-check container DV config with `mp4box -info` if remuxed to MP4.
3. **RPU content correctness:** for the *external-RPU* paths, `dovi_tool info -i RPU.bin -f <n> -s` on the **source** RPU gives the ground-truth per-frame L1 (min/avg/max nits). After injection, decode the AV1 with an ffmpeg build that surfaces `AV_FRAME_DATA_DOVI_METADATA` and diff the parsed L1 for boundary + reordered frames against `dovi_tool info` on the source RPU. Equality on those spot frames is the real alignment proof (frame-count alone is not).
4. **Regression against qsvencc:** encode the same DV chunk via Path 1 (qsvencc, known-good DV) and via Path 2, and diff extracted RPU-per-frame — qsvencc is the oracle for "correctly aligned DV in AV1."

---

## Confidence & sources

**HIGH (verified-live in this environment):**
- qsvencc 8.22 r4385 bundles **libdovi 3.1.2** + **hdr10plus_rs**, has its own `av1_itut_t35_header_dovirpu` T.35 OBU header and `dovi::av1::emdf::write_emdf_container_with_dovi_rpu_payload` — `strings /usr/bin/qsvencc` symbol table (this is the definitive mechanism proof).
- qsvencc `--dolby-vision-rpu {copy|<file>}` + `--dolby-vision-profile {…,10.1,…}` exist and take an **external RPU file** — `qsvencc --help`.
- `dovi_tool 2.3.3` (latest) CLI `inject-rpu`/`extract-rpu`/`mux` are **HEVC-only** — live `--help`; latest-release API = 2.3.3.
- Installed `ffmpeg` 6.1.1 has no `dovi_rpu` BSF (only `av1_metadata`/`av1_frame_*`); ffmpeg-8.1 not built in-container (`/opt/ffmpeg-8.1` absent).

**HIGH (verified upstream):**
- `dolby_vision` crate (libdovi) AV1 T.35 OBU writers: `write_av1_rpu_metadata_obu_t35_payload` (3.2.0), `write_av1_rpu_metadata_obu_t35_complete` + C-API `dovi_write_av1_rpu_metadata_obu_t35_{payload,complete}` (3.3.0), crate at 3.4.0 — [dovi_tool CHANGELOG](https://github.com/quietvoid/dovi_tool/blob/main/dolby_vision/CHANGELOG.md).
- dovi_tool CLI AV1 file processing "not supported yet" — [discussion #302](https://github.com/quietvoid/dovi_tool/discussions/302), [issue #254](https://github.com/quietvoid/dovi_tool/issues/254).
- `dovi_rpu` BSF = `strip` + `compression` only, no inject — [FFmpeg BSF docs](https://ffmpeg.org/ffmpeg-bitstream-filters.html).
- `hdr10plus_tool` 1.7.2 CLI HEVC-only — [quietvoid/hdr10plus_tool](https://github.com/quietvoid/hdr10plus_tool).
- QSVEnc DV options doc (external RPU file; "BL+RPU only"; HEVC+AV1) — [QSVEncC_Options.en.md](https://github.com/rigaya/QSVEnc/blob/master/QSVEncC_Options.en.md); profile-convert behavior — [QSVEnc #222](https://github.com/rigaya/QSVEnc/issues/222).

**MEDIUM (inferred):**
- Path 2 end-to-end works (libdovi C-API + T.35 OBU + display-order interleave) — every piece is verified to exist, but no reference CLI executes the full raw-`.obu` inject, so integration + B-reorder alignment is unproven until built/spiked.
- ffprobe/ffmpeg-8.1 surfacing AV1 DV T.35 as `AV_FRAME_DATA_DOVI_METADATA` for verification — consistent with the haasn DV-in-AV1 patch series, not probed live (8.1 absent).

---

## Roadmap implication (Phase 5)

- **DV can ride the ffmpeg default path only by building Path 2** (custom libdovi injector on the `.obu`). It is genuinely feasible — it is qsvencc's own mechanism, minus the encoder — but it is a **spike/build with a new dependency and a real B-reorder alignment risk**, not a flag.
- **The low-risk, ship-now decision is Path 1:** DV/HDR10+ sources route to the retained **qsvencc backend run `--avsw`** (0/60 clean, all metadata preserved), documented as the DV/HDR10+ path while the ffmpeg default owns SDR + HDR10. This satisfies "if qsvencc can do it, there is a way" — the way is qsvencc's bundled libdovi, made corruption-safe.
- **Correct two stale claims in the milestone research when this becomes a requirement:** (a) DV *is* injectable into fresh AV1 via libdovi (not impossible — just no CLI); (b) `hdr10plus_tool` does **not** give an AV1 out-of-band escape for HDR10+ (CLI is HEVC-only) — HDR10+ is in the same boat as DV, both currently served only by qsvencc's bundled `hdr10plus_rs`/`libdovi`.

---
*Researched: 2026-07-23 — targeted feasibility for enpipe v1.2 Phase 5 (DV/HDR10+)*
