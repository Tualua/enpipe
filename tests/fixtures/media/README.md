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
- `tests/fixtures/media/dv.mkv` -- a real Dolby Vision (RPU) sample

## Location override

Set the `ENPIPE_TEST_MEDIA` environment variable to point at a different
directory containing the same filenames, e.g.:

```bash
ENPIPE_TEST_MEDIA=/data/media/enpipe-fixtures uv run pytest -m hardware
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
- `test_dv`: additionally self-checks that the installed `ffmpeg`'s
  `dovi_rpu` bitstream filter reports AV1 support (a read-only `-h`
  inspection, never used to mutate/verify media), then asserts the output's
  per-frame Dolby Vision RPU side-data count matches the **source**
  fixture's RPU frame count -- both on the final muxed `.mkv` and on the
  pre-mux per-scene `.obu` chunks -- proving RPU survives the chunk
  splice/mux, not merely "some RPU exists somewhere".
