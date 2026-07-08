---
phase: 04-unified-cli-hardware-gated-real-media-validation
reviewed: 2026-07-08T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - src/enpipe/detection/pipeline.py
  - src/enpipe/cli/__init__.py
  - src/enpipe/cli/main.py
  - pyproject.toml
  - tests/unit/cli/test_run_detect_roundtrip.py
  - tests/unit/cli/test_cli_dispatch.py
  - tests/integration/test_hardware_real_media.py
  - tests/fixtures/media/README.md
  - .github/workflows/hardware-integration.yml
findings:
  critical: 1
  warning: 1
  info: 1
  total: 3
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-08
**Depth:** deep
**Files Reviewed:** 9
**Status:** issues_found

## Summary

`run_detect(args)` is a faithful, line-for-line migration of `legacy/scene_detection.py`'s `__main__` block (config precedence, `.scenes` line format, output-path default) and round-trips correctly through `encoding.scenes_io._SCENE_RE`/`read_scenes` — verified both by direct comparison against `legacy/scene_detection.py:647-692` and by the fast unit test suite (`uv run pytest -m "not hardware"` → 92 passed). `cli/main.py`'s argparse surface reconstructs both legacy parsers verbatim, including both documented default asymmetries (`--jobs`: detect hardcodes `4`, encode reads `encoding.pipeline.JOBS`; `-o` dest: `output` vs `out`). `[project.scripts]` wiring in `pyproject.toml` is correct and the CLI dispatch/monkeypatch tests correctly exercise real `argparse` name resolution. `ruff check` is clean on all reviewed files.

`tests/integration/test_hardware_real_media.py` correctly avoids the two most dangerous DV-verification traps (never calls `dovi_tool`'s AV1-broken RPU-extraction subcommand, never uses the mutating `dovi_rpu` bitstream filter to transcode — only a read-only `ffmpeg -h bsf=dovi_rpu` self-check), every `enpipe encode` invocation carries `--no-metrics`, and the two fixture-gated cases (`test_hdr10plus`/`test_dv`) skip honestly rather than fabricating a pass. However, the shared keyframe-alignment assertion in `_verify_frame_counts_and_keyframes` — used by all four hardware tests — is provably tautological despite being explicitly documented as a fix for a prior tautology; this is a genuine correctness-verification gap (Critical, see CR-01).

## Critical Issues

### CR-01: `_verify_frame_counts_and_keyframes`'s keyframe-alignment check is tautological (never exercises the production fast-path table)

**File:** `tests/integration/test_hardware_real_media.py:186-204`
**Severity:** HIGH

**Issue:** The module docstring (lines 154-163) and the Plan-02 SUMMARY both claim this check "replaces the old tautological `max({f<=s}) exists` check ... which could never fail." The replacement is *itself* tautological, by construction:

```python
fps = probe_fps(src)
gt_table = keyframe_table_ffprobe(src, fps)      # ground-truth, slow path
gt_kf_frames = {f for f, _ in gt_table}

for i, (s, e) in enumerate(scenes):
    seek, _trim = compute_chunk_seek_trim(gt_table, s, e)
    kf_frame, kf_time = kf_before(gt_table, s)
    assert kf_frame in gt_kf_frames, ...
    assert seek == fmt_seek(kf_time)
```

`kf_before(table, frame)` (`src/enpipe/encoding/keyframes.py:88-98`) always returns `best = table[mid]` — i.e. a literal element drawn from whatever `table` it is given. Here it is called with `gt_table`, the *very same table* `gt_kf_frames` was built from. `kf_frame in gt_kf_frames` is therefore true by construction for **any** input `s`, any bug or no bug — it can never fail. Likewise `seek == fmt_seek(kf_time)` just re-derives the same value `compute_chunk_seek_trim` computed internally from the same call, so it only proves the pure function is deterministic against itself, not that seek/trim decisions align with reality.

Critically, the test never invokes the **production** keyframe-lookup path (`enpipe.encoding.keyframes.keyframe_table`, which for `.mkv` sources takes the fast, hand-rolled EBML Cues parser `keyframe_table_cues` — the exact function `ARCHITECTURE.md` calls out as risking "silently corrupting output" if wrong) and never cross-checks it against the independent ffprobe ground truth (`keyframe_table_ffprobe`). `keyframe_table`/`keyframe_table_cues` are not imported anywhere in this file. The real `enpipe encode` runs invoked via `_run_cli` internally call `keyframe_table()` (fast Cues path) to pick every scene's actual `--seek` point; this test suite asserts nothing about whether that fast-path table agrees with ground truth. If `keyframe_table_cues` had a bug that returned a wrong-but-plausible keyframe list, none of `test_sdr`/`test_hdr10`/`test_hdr10plus`/`test_dv` would detect it — TEST-04's headline "non-tautological keyframe alignment" claim (SUMMARY line 61) is not actually satisfied for any of the four hardware tests that share this helper.

**Fix:** Cross-check the *actual* production table against ground truth, e.g.:

```python
from enpipe.encoding.keyframes import keyframe_table  # production fast-path

fps = probe_fps(src)
gt_table = keyframe_table_ffprobe(src, fps)          # independent ground truth
gt_kf_frames = {f for f, _ in gt_table}
prod_table = keyframe_table(src, fps)                # what run_encode() actually used

for i, (s, e) in enumerate(scenes):
    kf_frame, kf_time = kf_before(prod_table, s)      # decision from the REAL table
    assert kf_frame in gt_kf_frames, (
        f"scene {i}: production keyframe_table() picked frame {kf_frame} for "
        f"seek, which is NOT a real keyframe per independent ffprobe ground "
        f"truth -- keyframe_table_cues() (fast EBML path) has diverged from "
        f"the source"
    )
    seek, _trim = compute_chunk_seek_trim(prod_table, s, e)
    assert seek == fmt_seek(kf_time)
```
This makes `kf_frame in gt_kf_frames` a real assertion (it can fail if the fast Cues-parsing path is wrong) instead of a structurally-guaranteed no-op. At minimum, downgrade the docstring/SUMMARY claim so it does not assert non-tautological coverage that doesn't exist.

## Warnings

### WR-01: `keyframe_table`/`keyframe_table_cues` fast path is left entirely unverified against real hardware output

**File:** `tests/integration/test_hardware_real_media.py:58-63` (imports), `140-204` (verification helper)
**Severity:** MEDIUM

**Issue:** Even independent of CR-01's tautology bug, no test in this file — hardware-gated or otherwise, per the grep above — ever calls `enpipe.encoding.keyframes.keyframe_table()` (the function `run_encode()` actually calls to build its seek table) against a real muxed `.mkv` and compares it to `keyframe_table_ffprobe()`. TEST-04 is supposed to be the project's real-hardware, real-media correctness gate for exactly this kind of invariant (per `ARCHITECTURE.md`'s "Cues-index EBML parser" callout); as things stand, that invariant is only covered by whatever synthetic-clip coverage exists elsewhere (e.g. `test_ebml_cross_validation.py`, out of this phase's scope), not by TEST-04 itself, despite TEST-04's own docstring/SUMMARY claiming it is.

**Fix:** Same fix as CR-01 covers this — once `keyframe_table()` is exercised and cross-checked in `_verify_frame_counts_and_keyframes`, this gap closes automatically.

## Info

### IN-01: `assert seek == fmt_seek(kf_time)` proves only self-consistency, not correctness

**File:** `tests/integration/test_hardware_real_media.py:204`
**Severity:** LOW

**Issue:** `seek` comes from `compute_chunk_seek_trim(gt_table, s, e)`, which internally computes `kf_before(gt_table, s)` then `fmt_seek(kf_time)` — exactly what the assertion re-derives on the right-hand side, from the same table and the same `s`. This can only fail if `compute_chunk_seek_trim` is non-deterministic, which it structurally cannot be (pure function, same inputs). The accompanying comment is honest about this ("cross-checks the pure function against its own building block, not itself") so this is not mislabeled the way CR-01 is, but as written it adds no coverage beyond what a plain unit test of `compute_chunk_seek_trim` would already provide, and does so inside an expensive hardware-gated test.

**Fix:** Either remove the assertion (it is redundant with fast-tier unit coverage) or repurpose it to compare against an independently-derived `fmt_seek` value computed from the ground-truth table via a second, independent code path (e.g. manually locating `kf_frame`'s `pts_time` in `gt_table` without calling `kf_before`) so it isn't checking a function against its own subroutine call.

---

_Reviewed: 2026-07-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
