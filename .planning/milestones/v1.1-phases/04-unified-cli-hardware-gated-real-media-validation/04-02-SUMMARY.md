---
phase: 04-unified-cli-hardware-gated-real-media-validation
plan: 02
subsystem: testing
tags: [pytest, hardware-gated, qsvencc, ffprobe, hdr10, dolby-vision, av1, ci]

# Dependency graph
requires:
  - phase: 04-unified-cli-hardware-gated-real-media-validation (Plan 01)
    provides: "the `enpipe` console_script (enpipe detect/enpipe encode via enpipe.cli.main:main) this test drives end-to-end"
provides:
  - "tests/integration/test_hardware_real_media.py -- TEST-04 hardware-gated end-to-end validation (pytest.mark.hardware)"
  - "test_sdr / test_hdr10: live SDR + synthetic HDR10 pipeline validation on real Intel Arc QSV hardware"
  - "test_sdr_legacy_oracle_parity: executable SC4 parity check against the frozen legacy/encode_scenes.py oracle"
  - "test_hdr10plus / test_dv: fixture-gated HDR10+/Dolby Vision cases (tests/fixtures/media/, ENPIPE_TEST_MEDIA override)"
  - ".github/workflows/hardware-integration.yml -- D-08 self-hosted-Arc CI stub (workflow_dispatch only)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Independent re-verification pattern: --keep chunks + independently re-parsed .scenes + keyframe_table_ffprobe ground truth, never trusting the pipeline's own internal count_frames()/keyframe_table() checks"
    - "Read-only ffprobe side-data inspection (frame=side_data_list) for both HDR10 mastering-display/max-CLL survival and DV RPU survival -- never a mutating bitstream filter for verification"
    - "Fixture-gating: ENPIPE_TEST_MEDIA env var override + tests/fixtures/media/ directory, clean pytest.skip with a how-to-supply message when a real sample is absent, never a faked pass"

key-files:
  created:
    - tests/integration/test_hardware_real_media.py
    - tests/fixtures/media/README.md
    - .github/workflows/hardware-integration.yml
  modified:
    - .gitignore

key-decisions:
  - "D-05/D-06/D-07/D-08/SC4 all satisfied per the plan's Truths — Decision Traceability mapping"
  - "Empirical correction (Rule 1): HDR10 mastering-display/max-CLL metadata survives this pipeline's mkvmerge-muxed raw-OBU AV1 output ONLY at the FRAME level (frame=side_data_list), not at ffprobe's STREAM level as the plan's draft interface assumed -- verified directly (ffprobe -show_streams -show_entries stream=side_data_list returns no side_data_list key at all; mkvinfo confirms mkvmerge does not lift it into a Matroska Colour element for a raw-OBU AV1 track). test_hdr10 checks frame-level survival instead; documented inline in the module docstring as an 'EMPIRICAL CORRECTION' so a future reader isn't misled by the stale assumption."
  - "Multi-scene synthetic clips use 4x10s alternating color=/smptebars= segments (40s total) for BOTH SDR and HDR10, reusing test_parallel_regression.py's proven cut recipe -- short enough to keep real hardware-encode wall time low while still producing 3 genuine scene cuts (multiple chunks/keyframe points) that clear the default 72-frame/3s min-scene-len gate"

requirements-completed: [TEST-04]

# Metrics
duration: 15min
completed: 2026-07-08
---

# Phase 4 Plan 2: Hardware-Gated Real-Media Validation Summary

**TEST-04 hardware-gated pytest suite (`tests/integration/test_hardware_real_media.py`) driving the real `enpipe` CLI (detect -> encode -> mux) end-to-end on real Intel Arc QSV hardware, independently verifying per-chunk/total frame counts, non-tautological keyframe alignment, legacy-oracle parity, and DV RPU survival, with HDR10+/DV fixture-gated for honest coverage.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-08T16:49:30Z
- **Completed:** 2026-07-08T17:04:30Z
- **Tasks:** 4
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments
- `test_sdr` and `test_hdr10` actually RUN (not skipped) on this devcontainer's real Arc GPU and PASS: the full `enpipe detect` -> `enpipe encode` -> mux pipeline is exercised end-to-end via a SystemExit-safe CLI wrapper, every encode invocation carries `--no-metrics` (qsvencc's `--psnr`/`--ssim` needs OpenCL, unavailable here), and per-chunk + total frame counts are independently re-derived from a fresh `.scenes` parse + `--keep` chunks rather than trusting the pipeline's own internal checks
- Non-tautological keyframe-alignment verification: an independent `keyframe_table_ffprobe` ground-truth scan (not the pipeline's own possibly-fast-EBML-path table) is cross-checked against the pipeline's own `compute_chunk_seek_trim`/`kf_before` decision for every scene, replacing the old always-true `max({f<=s}) exists` tautology
- `test_sdr_legacy_oracle_parity` makes SC4 ("legacy remains the parity oracle") an EXECUTABLE check: runs the frozen `legacy/encode_scenes.py` read-only via subprocess on the same sample+scenes, asserting final-`.mkv` frame-count parity plus a determinism-aware pre-mux `movie.obu` comparison (byte-identical when qsvencc is deterministic on this box; frame-count fallback otherwise, mirroring `scratch/parity_encode.py`'s proven pattern) -- zero edits under `legacy/`
- `test_hdr10plus`/`test_dv` are fixture-gated (D-06): absent operator media -> clean `pytest.skip` with an explanatory how-to-supply message pointing at `tests/fixtures/media/README.md`/`$ENPIPE_TEST_MEDIA`, never a faked pass. `test_dv` additionally self-checks AV1 DOVI support via a read-only `ffmpeg -h bsf=dovi_rpu` probe and, when a fixture is present, asserts SOURCE-parity of the per-frame Dolby Vision RPU side-data count on both the final `.mkv` and the pre-mux `.obu` chunks -- never the mutating `dovi_rpu` bitstream filter or `dovi_tool`'s AV1-broken RPU-extraction subcommand
- `.github/workflows/hardware-integration.yml` (D-08): a `workflow_dispatch`-only CI stub giving the `hardware` pytest tier a named self-hosted-Arc home, without letting hosted `ci.yml` green be mistaken for hardware validation

## Task Commits

Each task was committed atomically:

1. **Task 1a: hardware gate + SDR end-to-end + independent frame-count/keyframe verification** - `a7a0612` (test)
2. **Task 1b: synthetic HDR10 end-to-end + HDR10-metadata-survival verification** - `e0146f3` (test)
3. **Task 1c: legacy-oracle SDR parity (SC4)** - `6427f44` (test)
4. **Task 2: fixture-gated HDR10+/DV cases + DV RPU source-parity + fixtures README/gitignore** - `9b1880a` (test)
5. **Task 3: D-08 self-hosted-Arc CI stub** - `0b0e30e` (feat)

**Plan metadata:** (this SUMMARY.md commit)

## Files Created/Modified
- `tests/integration/test_hardware_real_media.py` - the full TEST-04 suite: hardware-availability gate, `_run_cli` (SystemExit-safe CLI wrapper), `_make_multiscene_clip` (shared 4-segment lavfi synthetic-clip generator), `_verify_frame_counts_and_keyframes` (shared independent invariant check), `test_sdr`, `test_hdr10` (+ `_encoder_available`, `_frame_side_data_types`), `test_sdr_legacy_oracle_parity`, `test_hdr10plus`/`test_dv` (+ `_fixture`, `_av1_dovi_self_check`, `_dv_rpu_frame_count`) -- 526 lines
- `tests/fixtures/media/README.md` - documents `hdr10plus.mkv`/`dv.mkv` expected filenames, the `$ENPIPE_TEST_MEDIA` override, and why HDR10+/DV cannot be synthesized (D-06)
- `.gitignore` - `tests/fixtures/media/*` ignored except the tracked `README.md`, mirroring the existing `scratch/*.mkv` pattern
- `.github/workflows/hardware-integration.yml` - D-08 stub, `workflow_dispatch` only, targets a `[self-hosted, arc]` runner label, runs `pytest -m hardware -rs`; `ci.yml` untouched

## Decisions Made
- Reused `tests/integration/test_parallel_regression.py`'s proven 4-segment `color=`/`smptebars=` lavfi concat recipe for both SDR and HDR10 multi-scene clips (10s/segment, 40s total, 3 real cuts) -- fast enough for real hardware wall time while reliably clearing the default 72-frame/3.0s min-scene-len gate
- Both `test_sdr` and `test_hdr10` reuse the same shared `_verify_frame_counts_and_keyframes` helper (no duplicated verification logic between the two live-hardware paths)
- HDR10 and DV verification share the same underlying `_frame_side_data_types`/read-only `ffprobe -show_entries frame=side_data_list` probe, differing only in which `side_data_type` string each test asserts on (`"Mastering display metadata"`/`"Content light level metadata"` vs `"Dolby Vision RPU Data"`)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] HDR10 metadata-survival check moved from ffprobe STREAM level to FRAME level**
- **Found during:** Task 1b (synthetic HDR10 end-to-end + metadata-survival verification)
- **Issue:** The plan's `<interfaces>` block specified checking HDR10 mastering-display/max-CLL survival via `ffprobe -show_streams -show_entries stream=side_data_list` (explicitly "STREAM-level, NOT per-frame"). Empirically running this exact command against a real produced HDR10 `.mkv` from this pipeline (both the pre-QSV libx265 source and the post-QSV-encode, post-mkvmerge-mux output) showed the `side_data_list` key is entirely ABSENT at the stream level -- `ffprobe` reports zero stream-level side data, and `mkvinfo` confirms `mkvmerge` does not lift Mastering-display/MaxCLL into a Matroska `Colour` element for a raw-OBU AV1 track. The metadata genuinely DOES survive, but only at the FRAME level (`frame=side_data_list`), on every single video frame.
- **Fix:** Implemented the HDR10 survival check against `frame=side_data_list` instead (shared `_frame_side_data_types` helper, reused by the DV RPU check for a different side-data type string). Documented the discrepancy inline in the module docstring as an "EMPIRICAL CORRECTION" so a future maintainer reading the plan's interface text isn't misled.
- **Files modified:** `tests/integration/test_hardware_real_media.py`
- **Verification:** `test_hdr10` passes on real Arc hardware; independently confirmed via direct `ffprobe`/`mkvinfo` commands run against a real produced HDR10 output during implementation (all 72/72 frames carry both `Mastering display metadata` and `Content light level metadata`)
- **Committed in:** `e0146f3` (Task 1b commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix, an empirically-incorrect plan assumption about ffprobe's side-data reporting level)
**Impact on plan:** The fix is necessary for the HDR10 survival check to assert anything meaningful at all -- asserting on a stream-level key that never exists in this pipeline's actual output would either be a vacuous no-op or a guaranteed false-fail. No scope creep; the fix stays within Task 1b's stated goal (verify HDR10 metadata survival to the final `.mkv`).

## Issues Encountered

None beyond the deviation above. Real Intel Arc hardware (`/dev/dri/renderD128` + `qsvencc` 8.20) was confirmed present at the start of execution and used for all three live-hardware test runs (`test_sdr`, `test_hdr10`, `test_sdr_legacy_oracle_parity`).

## User Setup Required

None for the tests themselves -- `test_sdr`/`test_hdr10`/`test_sdr_legacy_oracle_parity` run fully automatically on this devcontainer's real Arc hardware with no operator action needed.

**Optional, for full DV/HDR10+ coverage:** an operator who wants `test_hdr10plus`/`test_dv` to actually run (rather than skip) must supply real, legally-usable sample files at `tests/fixtures/media/hdr10plus.mkv` / `tests/fixtures/media/dv.mkv`, or point `$ENPIPE_TEST_MEDIA` at a directory containing them -- see `tests/fixtures/media/README.md`. This is explicitly out of scope for this plan (D-06: genuine HDR10+/DV source material cannot be synthesized in-sandbox) and does not block milestone completion; the tests document the coverage boundary honestly rather than faking it.

## Next Phase Readiness

- TEST-04 fully satisfied: hardware-gated (`pytest.mark.hardware`, excluded from the default `pytest -m "not hardware"` tier) end-to-end validation of the full `enpipe` CLI pipeline against real media on real Intel Arc hardware, with independent (not self-referential) verification of every load-bearing correctness invariant this project cares about.
- This is the milestone's final phase (per PROJECT.md/ROADMAP.md) -- `enpipe` now has: an installable unified CLI (`enpipe detect`/`enpipe encode`, Plan 04-01), a fast hardware-free test tier (92 passing tests), and a hardware-gated real-media validation tier (3 passing + 2 honestly-skipped tests) confirming correctness on the actual target hardware.
- No blockers for milestone close. The only outstanding item is the pre-acknowledged, out-of-scope HDR10+/DV real-fixture sourcing (deferred per D-06, tracked in `tests/fixtures/media/README.md`, not a v1.0 blocker).

## Self-Check: PASSED

All created files verified present on disk; all 5 task commit hashes (`a7a0612`, `e0146f3`, `6427f44`, `9b1880a`, `0b0e30e`) verified present in `git log --oneline --all`.

---
*Phase: 04-unified-cli-hardware-gated-real-media-validation*
*Completed: 2026-07-08*
