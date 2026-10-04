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
GOP. Hardware tests require qsvencc >= r4665 on PATH.
