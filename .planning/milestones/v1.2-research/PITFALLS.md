# Pitfalls Research

**Domain:** Adding an ffmpeg `av1_qsv` scene-chunk AV1 encode backend to the `enpipe` pipeline (milestone v1.2), as the new corruption-free default alongside opt-in `qsvencc`.
**Researched:** 2026-07-23
**Confidence:** HIGH on the qsvencc corruption root cause + enpipe internals (read from `.planning/debug/*` and `src/enpipe/encoding/*`); MEDIUM–HIGH on ffmpeg `av1_qsv`/`dovi_rpu`/OBU behavior (verified against ffmpeg docs + intel/media-driver + cartwheel-ffmpeg issue trackers; HW behavior must be re-proven on this Arc A380).

> **Overriding principle for this milestone.** The project's non-negotiable core value is a *correct, bit-exact* scene-aware AV1 re-encode. The whole reason for v1.2 is that `qsvencc` under concurrency *silently* swaps single frames while `count_frames` still passes. Therefore every pitfall below is graded by one question: **can it reintroduce silent output corruption, or silently drop HDR/DV metadata, while all existing invariants (per-chunk + total frame count, keyframe alignment) still pass?** Those are the ones that must become *explicit verification requirements* (per-frame content checks, DV-RPU survival checks) — not left to `count_frames`.

---

## Critical Pitfalls

### Pitfall 1: Assuming ffmpeg `av1_qsv` is corruption-free without re-proving it on THIS hardware/JOBS

**What goes wrong:**
The migration is justified by "ffmpeg `av1_qsv` was 35/35 clean under 3-way/5-way concurrency." That was a *targeted contrast experiment* on three hotspot scenes (923/928/1129, off299) — not a full-pipeline, all-scenes proof, and not at the JOBS levels or scene mix a real run uses. Shipping on the strength of that datapoint, then discovering ffmpeg has its *own* concurrency failure window at higher JOBS or on a different source, reintroduces exactly the silent corruption v1.2 exists to kill.

**Why it happens:**
The debug docs read as a definitive "ffmpeg is immune" verdict. But the confirmed root cause is a **kernel-level (drm/i915) cross-process 10-bit reference-surface aliasing** bug that ffmpeg merely *dodges* via per-component `AVHWFramesContext` pools with separate `AllocId` — it is not architecturally impossible for ffmpeg to hit a related window under different surface pressure (more concurrent sessions, deeper reorder, mixed decode/VPP load). The immunity is empirical and environment-specific, and the same host kernel (`6.19.14-200.fc43`) that corrupts qsvencc is still in play.

**How to avoid:**
Make the **concurrent per-frame-content regression the acceptance gate**, run FIRST as a spike before building the full backend, and run it at the *actual production JOBS* (default 3, plus a stress level like 5–8):
- Reuse the handed-off reproducer (`.planning/debug/HANDOFF...md` §4): isolated single-session reference for a scene → N iterations of concurrent chunk encodes → extract the hotspot frame by offset → PSNR vs reference; `<30 dB` = corrupt.
- Gate on **PSNR = inf / bit-identical** at the hotspot AND a full-file per-frame VMAF/PSNR sweep (the same method that originally found frames 39121/61365/73734/110079/110992/136249), not just `count_frames`.
- Verify the ffmpeg command actually uses the corruption *triad* (HW `h264_qsv`/`av1_qsv` decode into VA video memory + `p010le`/10-bit + `GopRefDist:6` B-pyramid). If any leg silently degrades (e.g. ffmpeg falls back to SW decode), the "clean" result proves nothing — it just broke a triad leg the way `--avsw` does for qsvencc.

**Warning signs:**
- The regression harness reports 0 corrupt but the ffmpeg param-dump / `ffprobe` shows 8-bit output or SW decode — you proved a *different, weaker* pipeline is clean.
- Corruption rate is 0 at JOBS=3 but never tested at higher JOBS.
- Only the three known hotspot scenes are checked, not a full-file sweep on a fresh source.

**Phase to address:**
**Phase 1 (spike / correctness proof) — must be the gating first phase.** If ffmpeg is not provably clean under real JOBS on this host, the entire migration premise is invalid and the milestone should pivot to `--avsw` or `--jobs 1`.

---

### Pitfall 2: Silent HDR10 static-metadata loss — av1_qsv has NO way to embed mastering-display / max-CLL

**What goes wrong:**
`qsvencc` embeds HDR10 static metadata via `--master-display copy --max-cll copy` (see `hdr.py::detect_hdr`). The **ffmpeg `av1_qsv` encoder has no equivalent** — there is no `-av1qsv_params`, no AVOption, and no side-data passthrough that writes `METADATA_TYPE_HDR_MDCV` / `METADATA_TYPE_HDR_CLL` OBUs into the stream. The encoder happily produces a valid 10-bit Main-profile AV1 with correct `color_primaries`/`transfer`/`matrix` but **zero mastering-display and max-CLL metadata**. It muxes fine, plays fine on SDR, and looks plausible — but HDR10 tone-mapping targets are gone. This is a silent HDR downgrade that passes every frame-count check.

**Why it happens:**
This is a documented, long-standing gap in `av1_qsv` (intel/media-driver #1592, cartwheel-ffmpeg #221, intel/libvpl #87). Developers assume "10-bit + correct transfer = HDR done" and never diff the output's static metadata against the source.

**How to avoid:**
- **Do not rely on the encoder** for HDR10 static metadata. Plan a **post-encode metadata-OBU injection** step: for AV1, MDCV/CLL live in Metadata OBUs; re-attach them after `av1_qsv` (via a bitstream filter that injects the metadata OBUs, and/or via `mkvmerge`/container-level `--colour-*` + mastering-display signaling on the final mux).
- Make **static-metadata survival an explicit verification requirement**: after mux, `ffprobe -show_frames -show_entries frame=side_data_list` on the output must show `Mastering display metadata` and `Content light level metadata` matching the source values. Add this to the HDR fixture test — parity with the qsvencc path, not merely "is HDR-ish."
- Preserve container-level signaling in the `mkvmerge` step (`pipeline.py` mux) as a belt-and-suspenders, since some players read mastering-display from Matroska even if the bitstream lacks the OBU.

**Warning signs:**
- Output plays but HDR looks flat / wrong peak brightness vs the qsvencc encode.
- `ffprobe` on the av1_qsv output shows `color_transfer=smpte2084` but no `Mastering display metadata` side data.
- The HDR test only asserts transfer characteristics, never the actual MDCV/CLL values.

**Phase to address:**
**Phase 2 (HDR/DV metadata passthrough).** This is the load-bearing risk of the whole milestone — the reason qsvencc was chosen. Feasibility of MDCV/CLL re-injection should be de-risked EARLY (a spike alongside Phase 1), because if it cannot be made bit-faithful, HDR10 sources may need to stay on the qsvencc/`--avsw` backend.

---

### Pitfall 3: Silent Dolby Vision RPU loss or misalignment through the ffmpeg path

**What goes wrong:**
`qsvencc` does per-frame DV RPU passthrough natively (`--dolby-vision-rpu copy --dolby-vision-profile 10.1`). The ffmpeg `av1_qsv` encoder does **not** carry RPU through the HW encode — the RPU is per-frame side data that the hardware encoder drops. Getting DV through ffmpeg requires an explicit pipeline: extract the RPU stream from the source (dovi_tool / `dovi_rpu` BSF), then re-attach it to the encoded AV1 as T.35 Metadata OBUs. Failure modes, all of which **still mux and still pass `count_frames`**:
- RPU silently dropped entirely → output is plain HDR10 (or SDR) with no DV layer.
- RPU **misaligned to frames**: `av1_qsv` reorders output via B-pyramid (`GopRefDist:6`); if RPU is re-attached in decode/display order but the OBU stream is in a different order, per-frame RPU lands on the wrong frame → DV drives wrong tone-mapping per frame.
- **Per-chunk RPU boundary breakage**: enpipe encodes independent scene chunks and byte-concatenates them. RPU must be sliced per chunk on the same `[S, E)` frame interval as the video, or chunk boundaries desync the RPU from the picture.
- **Profile mismatch**: source profile 7 (dual-layer) vs 8.1 vs the AV1 DV profile 10.x; wrong `--dolby-vision-profile`/conversion yields an RPU a player rejects or ignores.

**Why it happens:**
DV RPU is invisible to normal QC — it needs a DV-aware probe. The `dovi_rpu` BSF is new (ffmpeg mid-2024, present in 8.1) and its AV1 T.35 wrapping path is far less battle-tested than the HEVC path. Reorder/alignment bugs are precisely the class that survives frame-count checks.

**How to avoid:**
- Treat DV RPU as a **first-class per-chunk artifact**: extract source RPU once, slice per scene `[S, E)` exactly as video seek/trim, re-attach after encode, and verify count.
- Make **RPU survival + alignment an explicit verification requirement**, not a `count_frames` afterthought:
  - RPU frame count on the final `movie.obu` must equal the video frame count (total-expect).
  - Spot-check RPU L1 metadata per frame against source at scene boundaries and at least one reordered (B) frame inside a chunk, to catch order swaps.
  - Confirm profile/level via `dovi_tool info` on the output.
- Keep the qsvencc backend as the DV fallback if ffmpeg RPU parity can't be proven on real DV fixtures.

**Warning signs:**
- Output has no `DOVI configuration record` / DV side data in `ffprobe`.
- `dovi_tool info` shows RPU count ≠ frame count, or profile ≠ expected.
- DV plays but tone-mapping "pops" on individual frames (misalignment through B-reorder).
- The DV test is fixture-gated and got skipped in CI (it already is HDR10+/DV fixture-gated in v1.0) — a skipped test is not a passing test.

**Phase to address:**
**Phase 2 (HDR/DV metadata passthrough).** Highest-risk sub-item; needs a real DV fixture (the current suite only fixture-gates DV). If no DV fixture exists on hardware, that gap itself is a risk to flag.

---

### Pitfall 4: Seek/trim off-by-one — ffmpeg input-vs-output seek breaks the exact-frame-interval contract

**What goes wrong:**
enpipe's contract (`keyframes.py::compute_chunk_seek_trim`) is exact and load-bearing: `K = last keyframe ≤ S`, then qsvencc `--seek floor_ms(K) --trim (S-K):(E-1-K)` emits exactly frames `[S, E)`. qsvencc's `--seek`+`--trim` counts frames deterministically from the keyframe. Naively porting this to ffmpeg gets it subtly wrong because ffmpeg seeking is timestamp-based, not frame-index-based:
- `-ss <time> -i` (input seek) lands on the nearest keyframe *at or before* the timestamp and **resets frame numbering / PTS to that seek point** — the frame-index arithmetic `(S-K):(E-1-K)` no longer maps cleanly.
- `-ss` *after* `-i` (output seek) is frame-accurate but decodes from file start (catastrophically slow at 1382 chunks).
- Timestamp rounding: enpipe deliberately `floor`s seek time to ms (`fmt_seek`) so seek lands *on* the keyframe. ffmpeg's seek-to-nearest may land one keyframe early/late if the source keyframe PTS doesn't match `floor_ms(K)`, shifting the whole trim window by a frame or a GOP.
- Using `-t <duration>` or `-to` instead of an exact **frame count** introduces VFR/rounding drift; the source is CFR here but the pattern is fragile.

The result: a chunk that is off by one frame at head or tail. On concatenation the total `count_frames` may *still equal* total-expect (one chunk long, an adjacent one short), so the guard passes while a scene boundary is misplaced by a frame — a silent temporal corruption.

**Why it happens:**
"`-ss`/`-t` = trim" is the universal ffmpeg mental model, but it's timestamp-semantics, whereas enpipe's invariant is frame-index-exact relative to a specific keyframe. The existing `compute_chunk_seek_trim` is *proven correct for qsvencc's counting model* and was explicitly eliminated as a corruption source — porting must preserve frame-exactness, not re-derive it in timestamp space.

**How to avoid:**
- Reproduce **frame-exact** semantics: use fast input seek to the keyframe (`-ss <keyframe_time> -i`), then select the exact frame window by *frame index* (e.g. `trim=start_frame=(S-K):end_frame=(E-K)` filter, or `-frames:v (E-S)` after discarding `(S-K)` frames), and set `-vsync 0`/`-fps_mode passthrough` so no frames are dropped/duplicated. Do **not** rely on `-t`/`-to` durations.
- Anchor on the same keyframe table enpipe already computes — do not let ffmpeg pick the keyframe. Verify ffmpeg's realized seek point equals `K` (log the first output PTS).
- Add a **per-chunk exactness assertion beyond count**: for a sample of chunks, decode the first and last frame and PSNR-match them against the source frames `S` and `E-1`. This catches head/tail off-by-one that `count_frames` misses (a single-frame shift with correct count).
- Keep `compute_chunk_seek_trim` as the single source of `(S, E, K)`; the backend adapter converts that to ffmpeg args — do not fork the arithmetic per backend.

**Warning signs:**
- A chunk has correct frame count but its first/last frame PSNR-mismatches source `S`/`E-1`.
- Concatenated total is correct but a per-chunk sweep shows one chunk `+1` and a neighbor `-1`.
- ffmpeg logs a first output PTS that differs from `floor_ms(K)`.

**Phase to address:**
**Phase 1 (av1_qsv backend: seek/trim + preset parity).** This is core correctness and must have per-chunk head/tail content verification in its acceptance criteria.

---

### Pitfall 5: GOP / closed-GOP mismatch so chunk boundaries no longer land on keyframes

**What goes wrong:**
enpipe's whole byte-concatenation scheme rests on "each chunk starts with a clean random-access point (keyframe) so raw `.obu` chunks `cat` bit-exactly." qsvencc is driven with `--gop-len 300 --gop-ref-dist 6 --b-pyramid` and *forces the encoded chunk to open on an IDR/key-frame at its first output frame*. If the ffmpeg `av1_qsv` mapping doesn't force a **closed GOP with a keyframe on the first output frame of every chunk** — e.g. relies on `-g` alone without forcing an IДR at frame 0, allows open-GOP B-frames referencing across the chunk start, or lets the encoder choose its own GOP structure — then chunk boundaries stop being independently-decodable random-access points. Concatenation then yields a stream with dangling inter-frame references: silent visual corruption at every scene boundary, or a stream mkvmerge accepts but players glitch on.

**Why it happens:**
Different encoders express "closed GOP / force keyframe" differently. av1_qsv GOP control (`-g`, `-bf`, `-idr_interval`, low-delay/pyramid options, `-forced_idr`) does not map 1:1 to qsvencc's `--gop-len/--gop-ref-dist/--b-pyramid`, and closed-GOP behavior may differ by default. Because each chunk is encoded from its own seek point, the *first* frame is naturally an I-frame — but "I-frame" ≠ "IDR/keyframe/random-access point with a repeated sequence header," and open-GOP can still reach backward.

**How to avoid:**
- Force **closed GOP + keyframe (IDR/KEY_FRAME) as the first output frame of every chunk**, and ensure a **sequence header OBU is emitted at every chunk start** (see Pitfall 6). Confirm the *encoder's* first output frame `frame_type` is KEY/INTRA and `show_frame` semantics are clean.
- Verify via `ffprobe -show_frames` on each chunk that frame 0 is a keyframe (`key_frame=1`) and that no frame references across the chunk boundary (closed GOP).
- Match the reorder depth to qsvencc's (`GopRefDist:6` / B-pyramid) so quality/rate-control is comparable (Pitfall 7), but never at the cost of an open GOP across chunk starts.
- Add a **concatenation-decodability check**: fully decode the assembled `movie.obu` (not just `count_packets`) and per-frame content-verify a window around several chunk boundaries against source.

**Warning signs:**
- First frame of a chunk has `key_frame=0` in `ffprobe`.
- Decoding the concatenated `movie.obu` throws OBU/reference errors or shows a glitch at scene boundaries while `count_frames` still passes.
- av1_qsv chosen GOP length differs from 300 and shifts internal keyframes (fine internally, but the *chunk-start* keyframe is the invariant that matters).

**Phase to address:**
**Phase 1 (av1_qsv backend: preset parity + raw OBU output).** Keyframe-alignment is a stated load-bearing invariant; its verification (frame-0-is-keyframe per chunk + boundary content check) must be an explicit acceptance criterion.

---

### Pitfall 6: Raw `.obu` output differences that break byte-concatenation or mkvmerge

**What goes wrong:**
The pipeline (`pipeline.py::flush_appends`) byte-concatenates chunk `.obu` files with `shutil.copyfileobj` and muxes the result with `mkvmerge --default-duration ... movie.obu`. This works because qsvencc emits a **raw low-overhead OBU stream** with a self-contained structure (sequence header + temporal-delimiter framing) that survives naive `cat`. ffmpeg's raw AV1 output has several footguns that break this:
- Wrong output format: writing an **IVF** or **Annex-B**-framed stream, or a full Matroska, instead of the low-overhead OBU stream (`-f obu`) — the bytes won't `cat` into a valid single stream and mkvmerge chokes or mis-frames.
- **Sequence header only in extradata / global header**: if av1_qsv puts the sequence header in extradata (global header) and *not* at each chunk's first keyframe, then chunk 2..N begin without a sequence header OBU — the concatenated stream is undecodable after chunk 0, silently, until a player hits the second chunk. Must ensure sequence header is **repeated at each chunk start** (the `-f obu` low-overhead muxer + no global-header flag, or an explicit repeat-headers option).
- **Temporal-delimiter (TD) OBU** insertion differences: the OBU muxer inserts a TD per temporal unit; if enpipe's concatenation ends up with missing or doubled TDs at chunk seams (e.g. one backend emits leading TD, the other doesn't), the stream frames incorrectly.
- **Extradata duplication**: `dump_extradata`/global-header interplay can prepend extradata that's already present, or omit it, changing byte layout so `count_frames` (packet count) or mkvmerge timing drifts.

All of these can produce a file that *muxes without error* and *counts correct frames* but is subtly malformed.

**Why it happens:**
ffmpeg has multiple AV1 raw encapsulations (raw OBU / IVF / Annex-B) and the sequence-header placement depends on global-header flags and muxer choice. qsvencc's single opinionated output masks this complexity; the port surfaces it.

**How to avoid:**
- Output the **low-overhead OBU stream** (`-f obu`) per chunk, with sequence header + TD repeated at each chunk start (do **not** set `AV_CODEC_FLAG_GLOBAL_HEADER` for the raw path). Diff a byte-dump (`ffprobe -show_packets`/an OBU parser) of an ffmpeg chunk vs a qsvencc chunk to confirm equivalent OBU framing.
- Validate the **assembled** stream, not just chunks: fully decode `movie.obu` end-to-end and per-frame content-verify, plus confirm mkvmerge produces the same frame count and duration as the qsvencc path.
- Test concatenation at a **backend boundary is impossible** (a run uses one backend) but test that an all-ffmpeg `movie.obu` decodes identically to an all-qsvencc one for an SDR fixture.

**Warning signs:**
- `movie.obu` decodes only up to the first chunk's frames, then errors — sequence header missing on later chunks.
- mkvmerge warns about "no frames" or wrong duration; playback stutters at chunk seams.
- ffmpeg chunk `.obu` is dramatically smaller/larger in header bytes than the qsvencc equivalent.

**Phase to address:**
**Phase 1 (av1_qsv backend: raw OBU output).** Add "assembled `movie.obu` fully decodes + per-frame matches source" to acceptance, above the existing packet-count guard.

---

### Pitfall 7: Divergent rate-control / quality making the two backends incomparable (dual-backend trap)

**What goes wrong:**
`--icq 23`/ICQ on qsvencc and av1_qsv's quality knobs (`-global_quality`/`-q`, ICQ vs CQP vs whatever av1_qsv exposes) are **not the same scale**. If the ffmpeg backend is mapped to a superficially-similar quality value, the two backends produce visibly different bitrate/size/quality for the "same" settings. Consequences specific to enpipe:
- The metrics CSV (`write_metrics_csv`) and any parity/regression comparison become meaningless across backends — you can't tell a quality regression from a backend difference.
- Users switching backends see file size swing 20–30% unexpectedly.
- The frozen `legacy/` single-pass oracle no longer parity-checks the ffmpeg path (it was a qsvencc oracle), so v1.2 loses its byte-identity safety net and must define a *new* acceptance basis (per-frame content correctness + a quality band, not byte-identity).

Additional dual-backend footguns:
- **Backend selection ambiguity**: env var vs CLI flag precedence, default drift (is ffmpeg really the default everywhere, including batch mode and `enpipe run`?), and a footgun where a user *thinks* they're on ffmpeg but a fallback silently used qsvencc (reintroducing corruption).
- **Test-matrix blowup**: SDR/HDR10/HDR10+/DV × 2 backends × concurrency = large; naively doubling every hardware test is slow and CI already names-out the hardware tier.

**Why it happens:**
Encoder quality parameters rarely translate across implementations; teams assume "ICQ 23 is ICQ 23." And byte-identity-to-legacy was the v1.0/v1.1 safety net — it silently stops applying once the encoder changes, but nobody re-defines "correct."

**How to avoid:**
- Define the v1.2 correctness basis explicitly: **per-frame content parity to source** (not byte-identity to legacy) + a **quality/size band** the ffmpeg backend must stay within vs the qsvencc reference on a fixture. Don't chase byte-identity between backends — it's unattainable.
- Calibrate av1_qsv quality to land in a comparable SSIM/PSNR + size band as qsvencc ICQ 23 on a reference clip; document the mapping (it will not be "23").
- Make backend selection **explicit and logged** (log which backend + full command per run, as `chunk_command` output is already logged), with **no silent cross-backend fallback** — if the chosen backend's tool is missing, `die()`, don't switch.
- Keep the test matrix tiered: fast hardware-free tests validate command-building for both backends; the expensive hardware/concurrency proof runs on the **default (ffmpeg)** path, with qsvencc's path getting the cheaper existing coverage (it's opt-in and already characterized).

**Warning signs:**
- Same "quality setting," very different output size between backends.
- Metrics CSV totals jump when switching backends and nobody can say if it's a regression.
- A run log doesn't state which backend ran, or shows a fallback.

**Phase to address:**
**Phase 3 (backend selection + dual-backend testing).** Selection plumbing, the new correctness/quality-band definition, and matrix tiering all live here.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Ship ffmpeg backend, defer HDR10 MDCV/CLL re-injection ("10-bit is close enough") | Faster to a working SDR/parallel default | **Silent HDR downgrade** on every HDR10 source — the core-value violation, undetectable without a metadata diff | Only if HDR sources are explicitly routed to qsvencc/`--avsw` in the meantime AND the gap is loudly logged/documented |
| Reuse `count_frames` (packet count) as the only correctness gate for the new backend | Zero new test infra | Misses single-frame swaps, head/tail off-by-one, DV/HDR loss — the entire class v1.2 targets | Never — the milestone exists *because* count-only checks were insufficient |
| Map ICQ→av1_qsv quality by "same number" | No calibration work | Incomparable outputs, meaningless metrics, surprise size swings | Never — always calibrate to a band |
| Let av1_qsv choose GOP/keyframe placement (only pass `-g`) | Simpler command | Chunk-start may not be a clean random-access point → concat corruption | Never for the chunk-boundary frame; internal GOP is fine |
| Test only the 3 known hotspot scenes for concurrency | Fast to run | Proves nothing about full runs / other sources / higher JOBS | Only as a *smoke* check, never as the acceptance gate |
| Keep DV path fixture-gated and let CI skip it | Green CI | DV parity never actually verified; regressions ship silently | Only if a real DV fixture runs in the hardware tier before milestone close |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ffmpeg `av1_qsv` HDR10 static metadata | Assume encoder embeds MDCV/CLL from source side data | It does NOT (intel/media-driver #1592). Inject metadata OBUs post-encode and/or signal at mkvmerge; verify with `ffprobe` side-data diff |
| ffmpeg `dovi_rpu` BSF (AV1 / T.35) | Assume RPU flows through the HW encoder like qsvencc | Encoder drops it. Extract RPU, slice per chunk `[S,E)`, re-attach as T.35 OBUs, verify RPU-count == frame-count + alignment through B-reorder |
| ffmpeg raw AV1 output | Use IVF/Annex-B/Matroska, or global-header sequence header | Use `-f obu` low-overhead; repeat sequence header + TD at each chunk start so byte-`cat` stays decodable |
| ffmpeg seek/trim | Use `-ss`/`-t` timestamp trim | Anchor to enpipe's keyframe `K`; select exact **frame window** by index (`trim`/`-frames:v`, `-vsync 0`); verify first output PTS == `floor_ms(K)` |
| ffmpeg QSV decode into VA memory | Let ffmpeg silently fall back to SW decode | If it does, the corruption triad is broken and the "clean" concurrency result is invalid — assert HW decode + p010 + GopRefDist6 in a param dump |
| mkvmerge final mux | Assume container carries HDR/DV if bitstream lost it | Container signaling helps HDR10 but not DV RPU; don't rely on it to paper over bitstream metadata loss |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Higher JOBS to "restore full speed" without re-testing corruption | Fast, but maybe a fresh concurrency window opens in ffmpeg | Re-run the per-frame concurrency proof at each JOBS level you intend to ship | Unknown JOBS threshold on this i915 kernel — must be measured, not assumed |
| Full per-frame VMAF/PSNR verification of every run in production | Correct but doubles wall-time (full decode) | Make deep content-verify a *test/CI* gate on fixtures; production keeps count + spot-checks | When applied to every real 170k-frame encode |
| Output seek (`-ss` after `-i`) to get frame accuracy | Correct but decodes from file start per chunk | Fast input seek to keyframe + frame-index trim | Catastrophic at 1382 chunks/file |
| DV RPU extract/attach per chunk re-reading whole source each time | I/O storm on spinning-disk ZFS | Extract source RPU once, slice in memory per chunk | At high chunk counts on the ZFS pool |

## Security Mistakes

Not a meaningful axis for this local/NAS CLI transcoder (no network, auth, or untrusted input surface beyond media files). The relevant analog is **data integrity**, covered above: the "attack" is silent bitstream corruption from the driver, and the "defense" is per-frame content verification. One robustness note: parsing untrusted `.obu`/RPU byte streams should fail loudly (`die()` on the main thread), never silently truncate — consistent with enpipe's existing collect-then-die pattern.

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent backend fallback (chosen tool missing → other backend runs) | User believes they got corruption-free ffmpeg, actually got qsvencc | Hard `die()` if selected backend unavailable; never auto-switch |
| Not logging which backend + full command ran | Can't diagnose a bad output after the fact | Log backend name + resolved command per run (extend existing command logging) |
| Changing the default to ffmpeg without a migration note | Existing scripts/size expectations break silently | Document the default flip + expected size/quality delta in release notes; keep `qsvencc` one flag away |
| HDR downgrade with no warning | User ships flat HDR unknowingly | If HDR source + backend can't carry metadata, warn loudly or route to qsvencc |

## "Looks Done But Isn't" Checklist

- [ ] **av1_qsv encode:** Often missing — closed-GOP keyframe as the *first* frame of every chunk. Verify `ffprobe -show_frames` frame 0 `key_frame=1` per chunk AND no cross-boundary references.
- [ ] **Raw OBU output:** Often missing — sequence header repeated at each chunk start. Verify `movie.obu` fully **decodes end-to-end** (not just `count_packets`), and per-frame matches source around chunk seams.
- [ ] **Seek/trim parity:** Often missing — head/tail frame exactness. Verify first/last decoded frame of a chunk PSNR-matches source `S`/`E-1`, not just that the count is right.
- [ ] **HDR10:** Often missing — MDCV + max-CLL in the output. Verify `ffprobe` side-data shows `Mastering display metadata` + `Content light level` matching source values (parity with qsvencc output).
- [ ] **HDR10+:** Often missing — 2094-40 dynamic metadata OBUs. Verify presence + per-frame count on the assembled stream.
- [ ] **Dolby Vision:** Often missing — RPU present, count == frames, correct profile, aligned through B-reorder. Verify with `dovi_tool info` + boundary/reordered-frame L1 spot-check.
- [ ] **Concurrency immunity:** Often missing — proof at *real* JOBS on *this* host with a *full-file* per-frame sweep, with HW-decode + p010 + GopRefDist6 confirmed. A single-hotspot 0/N is not proof.
- [ ] **Backend selection:** Often missing — no silent fallback; default is ffmpeg *everywhere* (single, batch, `enpipe run`); command logged.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| ffmpeg NOT immune at production JOBS | HIGH | Pivot backend default to `--avsw` qsvencc or `--jobs 1`; keep ffmpeg opt-in; re-scope milestone |
| HDR10 MDCV/CLL infeasible through ffmpeg | MEDIUM | Route HDR10 sources to qsvencc/`--avsw`; ship ffmpeg for SDR; document limitation |
| DV RPU won't align through av1_qsv B-reorder | MEDIUM–HIGH | Route DV sources to qsvencc backend; ship ffmpeg for non-DV; flag as known gap |
| Seek/trim off-by-one found late | MEDIUM | Adapter converts single `compute_chunk_seek_trim` output; fix is localized; re-run per-chunk head/tail content check |
| Concat/OBU malformation | LOW–MEDIUM | Switch to `-f obu` low-overhead + repeat headers; re-verify full decode of `movie.obu` |
| Backends incomparable | LOW | Define per-frame-parity + quality-band basis; calibrate av1_qsv quality; document mapping |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Unproven immunity on this HW/JOBS | **Phase 1 (spike, gating first)** | Full-file per-frame PSNR/VMAF sweep + hotspot reproducer at JOBS 3 and 5–8, HW-decode+p010+GopRefDist6 asserted; 0 corrupt |
| 4. Seek/trim off-by-one | Phase 1 (backend core) | Per-chunk first/last frame PSNR-match to source `S`/`E-1`; first output PTS == `floor_ms(K)` |
| 5. GOP / keyframe misalignment | Phase 1 (preset parity) | Per-chunk frame 0 `key_frame=1`, closed GOP; boundary content-verify on assembled stream |
| 6. Raw `.obu` concat breakage | Phase 1 (OBU output) | `movie.obu` fully decodes end-to-end + per-frame matches source; mkvmerge frame-count/duration parity |
| 2. HDR10 static-metadata loss | Phase 2 (HDR/DV) | `ffprobe` side-data diff: MDCV + max-CLL present and equal to source |
| 3. DV RPU loss/misalignment | Phase 2 (HDR/DV) | `dovi_tool info`: RPU count == frames, correct profile, boundary + reordered-frame alignment spot-check |
| HDR10+ dynamic-metadata loss | Phase 2 (HDR/DV) | 2094-40 OBU presence + per-frame count on assembled stream |
| 7. Divergent RC / incomparable backends | Phase 3 (dual-backend) | av1_qsv quality lands in SSIM/PSNR+size band vs qsvencc reference; mapping documented |
| Backend-selection footguns / silent fallback | Phase 3 (dual-backend) | Default = ffmpeg in all entry points; `die()` on missing tool; backend + command logged |

## Sources

- `.planning/debug/scene-chunk-frame-mismatch.md` — full root-cause chain: qsvencc concurrent 10-bit reference-surface aliasing, kernel drm/i915 localization, ffmpeg av1_qsv 35/35 clean contrast, negative-result patch log. (HIGH — primary, this project)
- `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` — reproducer recipe, corruption triad, solution space (avsw / jobs=1 / ffmpeg migration), defense-in-depth per-frame verification recommendation. (HIGH — primary)
- `src/enpipe/encoding/{chunk,keyframes,hdr,pipeline}.py` — current qsvencc command, seek/trim arithmetic, HDR/DV flag detection, byte-concat + mux + count_frames guards. (HIGH — read directly)
- [intel/media-driver #1592 — HDR10 mastering-display metadata for av1_qsv](https://github.com/intel/media-driver/issues/1592) and [intel/cartwheel-ffmpeg #221](https://github.com/intel/cartwheel-ffmpeg/issues/221), [intel/libvpl #87](https://github.com/intel/libvpl/issues/87) — confirms av1_qsv has NO HDR10 static-metadata passthrough. (MEDIUM–HIGH — official issue trackers)
- [FFmpeg dovi_rpu BSF docs](https://ffmpeg.org/ffmpeg-bitstream-filters.html) + [DeepWiki: Dolby Vision and HDR Metadata](https://deepwiki.com/FFmpeg/FFmpeg/5.5-dolby-vision-and-hdr-metadata) + [dovi_rpu BSF patch (T.35 for AV1)](https://patchwork.ffmpeg.org/project/ffmpeg/patch/20240624172044.101722-9-ffmpeg@haasn.xyz/) — RPU stripping/compression, HEVC NAL vs AV1 T.35 wrapping; BSF added mid-2024 (present in ffmpeg 8.1). (MEDIUM — official docs + patchwork)
- [FFmpeg Formats/BSF docs — AV1 low-overhead OBU muxer, temporal-delimiter + dump_extradata](https://ffmpeg.org/ffmpeg-formats.html) and [av1_metadata / extract_extradata AV1 support](https://ffmpeg.org/ffmpeg-bitstream-filters.html) — OBU framing, sequence-header/global-header handling for raw output. (MEDIUM — official docs)
- [FFmpeg -ss input vs output seeking](https://dev.to/javidjamae/ffmpeg-ss-t-and-to-flags-input-vs-output-seeking-2b3p) + [FFmpeg codecs docs](https://ffmpeg.org/ffmpeg-codecs.html) — input-seek keyframe-snap vs output-seek frame accuracy tradeoff. (MEDIUM — verified against official docs)
- [HDR10+ AV1 Metadata Handling Specification (AOM)](https://aomediacodec.github.io/av1-hdr10plus/) — METADATA_TYPE_ITUT_T35 OBU carriage of HDR10+/DV in AV1. (HIGH — spec)

---
*Pitfalls research for: adding ffmpeg av1_qsv scene-chunk backend to enpipe (v1.2)*
*Researched: 2026-07-23*
