# Hardware-tier media fixtures (HDR10+ / Dolby Vision)

`tests/integration/test_hardware_real_media.py` (TEST-04, `pytest.mark.hardware`)
validates the full `enpipe detect` -> `enpipe encode` -> mux pipeline against
real media on real Intel Arc QSV hardware. SDR and HDR10 sources are
synthesized in-test with `ffmpeg` and require no fixture files.

**HDR10+ (dynamic metadata) and genuine Dolby Vision (RPU) sources cannot be
reliably synthesized in-sandbox** (D-06): HDR10+ requires per-scene/per-frame
tone-mapping curve data (SMPTE ST 2094-40) authored by a real HDR10+
mastering process, and genuine DV RPU requires Dolby's proprietary RPU
generation pipeline (dual-layer BL+EL or single-layer profile 8.x/10.x
metadata authored against an actual graded master). Neither `ffmpeg`/`x265`
nor `qsvencc` can originate this data from scratch -- `qsvencc
--dolby-vision-rpu copy` only *copies* pre-existing RPU from a source that
already has it.

Because of this, the `test_hdr10plus` and `test_dv` cases in
`test_hardware_real_media.py` are **fixture-gated**: they look for real
sample files at a documented location and, when absent, **skip cleanly**
with an explanatory message -- they never fake a pass.

## Expected filenames

Place operator-supplied sample files here:

- `tests/fixtures/media/hdr10plus.mkv` -- a real HDR10+ (dynamic metadata) sample
- `tests/fixtures/media/dv.mkv` -- a real Dolby Vision profile 8.1 sample
  (HDR10-compatible base layer, bl_signal_compatibility_id 1); may be a symlink
- `tests/fixtures/media/dv-p5.mkv` -- a real Dolby Vision profile 5 sample
  (bl_signal_compatibility_id 0), used by `test_dv_profile5`

## Location override

Set the `ENPIPE_TEST_MEDIA` environment variable to point at a different
directory containing the same filenames, e.g.:

```bash
ENPIPE_TEST_MEDIA=/data/media/enpipe-fixtures uv run pytest -m hardware
```

## Verification ffprobe (ENPIPE_TEST_FFPROBE)

The DV checks need an ffprobe from ffmpeg >= 7 with AV1 Dolby Vision support
(the libdav1d decoder exports "Dolby Vision Metadata" and the `dovi_rpu`
bitstream filter lists av1). Both images (runtime and devcontainer) now ship
ffmpeg 9 (BtbN static, n9.0.2, pinned by URL + SHA256) as the primary
`ffmpeg`/`ffprobe` (`/usr/local/bin` -> `/opt/ffmpeg-9/bin`), so the DV checks run
with the default `ffprobe` on PATH. The system ffmpeg 6.1 on Ubuntu 24.04 cannot
verify AV1 DV, so the DV tests would skip honestly there.
`ENPIPE_TEST_FFPROBE` stays as an override and affects ONLY the read-only
verification probes; the pipeline under test keeps using ffmpeg/ffprobe from
PATH. The self-check uses the ffmpeg sitting next to that ffprobe.

```bash
ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures uv run pytest -m hardware -k dv
```

Override example (another build, e.g. outside the images):

```bash
ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware -k dv
```

## Why these files are not committed

Real HDR10+/Dolby Vision media is almost certainly copyrighted and
non-redistributable. This directory's `.mkv`/`.obu` contents are gitignored
(see the repository `.gitignore`'s `tests/fixtures/media/` block) -- only
this `README.md` is tracked. Supply your own legally-usable sample files
locally or point `ENPIPE_TEST_MEDIA` at a directory that already has them
(e.g. a NAS media library).

## What the tests check when a fixture IS present

- `test_hdr10plus`: runs the full `enpipe detect` -> `enpipe encode` pipeline
  against `hdr10plus.mkv` on real Arc hardware and independently verifies
  per-chunk/total frame counts and keyframe alignment (the same invariants
  `test_sdr`/`test_hdr10` check).
- `test_dv`: self-checks that the ffmpeg next to `ENPIPE_TEST_FFPROBE`
  (default: `ffmpeg` on PATH) has a `dovi_rpu` bitstream filter reporting AV1
  support (a read-only `-h` inspection, never used to mutate/verify media),
  then asserts the number of frames carrying "Dolby Vision Metadata" side data
  (not "Dolby Vision RPU Data" -- that entry exists only on the HEVC source and
  is absent on AV1 after libdav1d) matches the **source** fixture's count, both
  on the final muxed `.mkv` and on the pre-mux per-scene `.obu` chunks --
  proving RPU survives the chunk splice/mux. It also checks the output's
  "DOVI configuration record": `dv_profile` 10 and
  `dv_bl_signal_compatibility_id` equal to the source's (8.1 -> 10.1).
- `test_dv_profile5`: the same on `dv-p5.mkv`; expects profile 10 with
  compat 0 (P5 -> 10.0). The record is derived by mkvmerge from the stream.

## Chunk content check (first frame vs source)

Frame counts and keyframe alignment do not see a chunk that silently starts
one GOP late. So every hardware test that keeps its chunks (`--keep`) also
compares the **first frame** of each `chunk_{i:05d}.obu` with source frame `S`
(the scene start), decoded by the ffmpeg next to `ENPIPE_TEST_FFPROBE`:

- PSNR(chunk first frame, source frame `S`) must be at least 30 dB.
- Negative control: source frame `S + (K_next - K)` (where the chunk lands if
  `--seek` jumps to the next keyframe) must score at least 3 dB lower. If
  source frames `S` and `S+delta` are nearly identical (static content) the
  control is reported as non-discriminating and only the 30 dB floor applies.

Why: the content check guards against `qsvencc --seek` landing one GOP late
with rc=0 and the expected frame count (fixed in qsvencc 8.32-vppsync6, r4663,
now the required minimum; see `.planning/debug/HANDOFF-qsvencc-seek-firstpkt.md`).

`test_dv_profile5` is a normal test now. The synthetic open-GOP HEVC mp4
sources (RASL after CRA and RADL after IDR_W_RADL) are encoded and
content-checked (`test_chunk_content_open_gop[rasl|radl]`): qsvencc shifted
`--trim` by -N on such sources until r4665 (8.32-vppsync7), see
`.planning/debug/HANDOFF-qsvencc-opengop-trim-offset.md`. Their closed-GOP twin
is `test_chunk_content_closed_gop`, and `test_hdr10` uses x265's default open
GOP. Hardware tests require qsvencc >= r4747 on PATH.

## ENPIPE_TEST_VC1: a short real VC-1 cut

`test_chunk_edges_avsw_vc1` (D-08.2) encodes chunks of a real VC-1 source with
`qsvencc --avsw` (VC-1 is not decodable in hardware on the Arc B50) and checks
the first and last frame of every chunk against source frames S and E-1. On
VC-1 in mkv the block timestamps are in decode order, so keyframe numbers taken
from Cues differ from decode-order numbers by -1/0/+1; only a real VC-1 file
exercises that. The cut is NOT stored in the repository. Without
`ENPIPE_TEST_VC1` the test is skipped.

Cut about 30 s without re-encoding (the source path has no `/temp/`; `DIR` is
any scratch directory outside `/data`):

```bash
DIR=$(mktemp -d)
mkvmerge -o "$DIR/fringe_s02e01_cut.mkv" --no-audio --no-subtitles --no-chapters --no-attachments --no-global-tags --split parts:00:10:00.000-00:10:30.000 "/data/downloads/Fringe.COMPLETE.SERIES.1080p.REMUX-FraMeSToR/Fringe.S02.BluRay.1080p.DD.5.1.VC-1.REMUX-FraMeSToR/Fringe.S02E01.A.New.Day.in.the.Old.Town.1080p.DD.5.1.VC-1.REMUX-FraMeSToR.mkv"
```

Run:

```bash
ENPIPE_TEST_VC1="$DIR/fringe_s02e01_cut.mkv" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k vc1 -s
```

## ENPIPE_TEST_VC1_TIES and ENPIPE_TEST_VC1_TIES_CLOSED: VC-1 cuts with I-frame ties

On the full Fringe S02E01 the old numbering rule (nearest I-frame within +-2)
refused in 97 places: two I-frames lie through one frame from a Cues keyframe
(for example Cues 750 -> [749, 751], gap G-1). Since 10.1-14 the rule is
"ordinal with window": stage 1 is the old rule; only where it refuses on a tie
(or non-strict growth) stage 2 matches the n-th Cues keyframe to the n-th decoder
I-frame (equal counts, every pair within +-2). `test_chunk_edges_avsw_vc1_ties`
and `test_run_auto_vc1_ties_cut` (each parametrized over both variables) encode
chunks around the former ties with `--avsw` and check the frame counts and the
first and last frame of every chunk. The cuts are NOT stored in the repository;
without the variables the tests are skipped. The tests fail with `precondition`
if the old rule does not refuse on a cut (the regression would prove nothing).

Two cuts, because the sign of the shift differs (the intervals were chosen by the
orchestrator, not the operator):

- `ENPIPE_TEST_VC1_TIES` (open start): 04:05-04:35 starts with an open GOP; the
  decoder drops the leading B-frame (717 packets, 716 decoded frames), shifts are
  -1/0/+1; the old rule refuses on 1 tie (Cues 334 -> [333, 335]).
- `ENPIPE_TEST_VC1_TIES_CLOSED` (closed start): 04:19.790-04:49.800 starts on a
  keyframe (724 packets = 724 frames), shifts are 0/+1/+2; the old rule refuses on
  3 ties (Cues 1, 219, 312).

The start of the series is not usable: identical black frames make the edge
comparison inconclusive. `DIR` is any scratch directory outside `/data`:

```bash
DIR=$(mktemp -d)
mkvmerge -o "$DIR/fringe_s02e01_ties_cut.mkv" --no-audio --no-subtitles --no-chapters --no-attachments --no-global-tags --split parts:00:04:05.000-00:04:35.000 "/data/downloads/Fringe.COMPLETE.SERIES.1080p.REMUX-FraMeSToR/Fringe.S02.BluRay.1080p.DD.5.1.VC-1.REMUX-FraMeSToR/Fringe.S02E01.A.New.Day.in.the.Old.Town.1080p.DD.5.1.VC-1.REMUX-FraMeSToR.mkv"
mkvmerge -o "$DIR/fringe_closed_gop_cut.mkv" --no-audio --no-subtitles --no-chapters --no-attachments --no-global-tags --split parts:00:04:19.790-00:04:49.800 "/data/downloads/Fringe.COMPLETE.SERIES.1080p.REMUX-FraMeSToR/Fringe.S02.BluRay.1080p.DD.5.1.VC-1.REMUX-FraMeSToR/Fringe.S02E01.A.New.Day.in.the.Old.Town.1080p.DD.5.1.VC-1.REMUX-FraMeSToR.mkv"
```

Check that the old rule refuses on a cut (prints `production: ok, ...` now, the
old rule's ties and the ordinal shifts):

```bash
uv run python scratch/vc1_tie_diag.py "$DIR/fringe_s02e01_ties_cut.mkv" --list
```

Run:

```bash
ENPIPE_TEST_VC1_TIES="$DIR/fringe_s02e01_ties_cut.mkv" ENPIPE_TEST_VC1_TIES_CLOSED="$DIR/fringe_closed_gop_cut.mkv" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k vc1_ties -s
```

## ENPIPE_TEST_WMV3: a short real wmv3 (WMV9, ASF) cut

ASF has no Cues and the packets of this cut carry no pts (`pts_time=N/A` on
every video packet), so enpipe encodes such a source as ONE chunk (10.1-13)
instead of cutting by scenes. Two hardware tests use the cut:

- `test_keyframe_table_refuses_wmv3_without_pts` pins the facts of quick
  261112-dab: all packets lack pts, `probe_pts` reports it, and the production
  `keyframe_table` refuses loudly.
- `test_run_single_chunk_wmv3_cut` runs `enpipe run` end to end on the cut: one
  `--avsw` chunk without `--seek/--trim`, no detect, the output frame count
  equals the source decoded frame count, the metrics CSV has one row + total,
  and the chunk content is compared with the source by PSNR (nearest frame
  among neighbours -2..+2) at frames 0, total/4, total/2, 3*total/4 and
  total-1. A mismatch or an inconclusive frame fails the test: do not loosen
  the check, a failure here is a finding about the encode path.

The chunk-edge measurement of 261112-dab is lifted (it cannot pass by
construction on a source without pts); scene cutting of such sources is
backlog 999.8. The cut is operator-supplied and not stored in the repository.

Cut (from the file start, no re-encode; prints a summary and the run command):

```
scratch/wmv3_cut.sh /data/downloads/wmv_test4.wmv 100
```

Run:

```
ENPIPE_TEST_WMV3="<cut path>" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k wmv3 -s
```
