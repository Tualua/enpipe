---
phase: 01-package-foundation-migration-fast-test-tier
plan: 03
subsystem: encoding
tags: [qsvencc, ffmpeg, ffprobe, mkvmerge, ebml-mkv, pytest-subprocess, subprocess-seam, parity]

# Dependency graph
requires:
  - phase: 01-package-foundation-migration-fast-test-tier (plan 01)
    provides: "enpipe.shared.proc.{run,popen} subprocess seam; enpipe.shared.logging.{die,log,step} leaf module; installable src/-layout package with hardware pytest marker"
  - phase: 01-package-foundation-migration-fast-test-tier (plan 02)
    provides: "Detection fully migrated and parity-verified first, per D-13 mechanical-migration order (encoding depends on detection completing before it starts)"
provides:
  - "src/enpipe/encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py — mechanical migration of legacy/encode_scenes.py, zero logic changes, every subprocess call routed through enpipe.shared.proc, die()/log()/step() consumed from enpipe.shared.logging"
  - "pipeline.run_encode(args) — main() minus argparse, RETAINS the shutil.which tool preflight + args.video.is_file() check as its first statements (sanctioned structural change, not a logic change)"
  - "EBML/Cues parser (_ebml_num/_eid/_esz, keyframe_table_cues) stays inline in keyframes.py per D-07 — isolation is Phase 2 (DEBT-01)"
  - "tests/unit/encoding/{test_scenes_io,test_keyframes,test_chunk}.py — TEST-01 pure-logic coverage (read_scenes incl. Pitfall-4 two-level failure, kf_before, fmt_seek, EBML byte helpers, chunk_command, parse_metrics)"
  - "tests/subprocess/encoding/{test_hdr,test_chunk,test_audio,test_keyframes}.py — TEST-02 mocked argv/error-path coverage (detect_hdr, encode_chunk/count_frames, encode_audio's (bool, Optional[str]) tuple regime, keyframe_table_ffprobe's die()/SystemExit path)"
  - "scratch/parity_encode.py — hardware-gated throwaway parity script vs legacy/encode_scenes.py (D-14), verified byte-identical pre-mux movie.obu on real Arc QSV hardware"
affects: [02-ebml-isolation, 04-unified-cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "encoding modules import enpipe.shared.proc as `_proc` (aliased, not bare `proc`) to avoid shadowing the pre-existing local `proc = run(...)` CompletedProcess variable name used in keyframe_table_ffprobe/encode_chunk/encode_audio/the final mkvmerge call"
    - "pipeline.run_encode(args) retains the shutil.which tool-preflight + args.video.is_file() check as its first two statements — the ONLY structural cut from main() is the argparse block itself"

key-files:
  created:
    - "src/enpipe/encoding/scenes_io.py"
    - "src/enpipe/encoding/keyframes.py"
    - "src/enpipe/encoding/hdr.py"
    - "src/enpipe/encoding/chunk.py"
    - "src/enpipe/encoding/audio.py"
    - "src/enpipe/encoding/metrics.py"
    - "src/enpipe/encoding/pipeline.py"
    - "tests/unit/encoding/test_scenes_io.py"
    - "tests/unit/encoding/test_keyframes.py"
    - "tests/unit/encoding/test_chunk.py"
    - "tests/subprocess/encoding/test_hdr.py"
    - "tests/subprocess/encoding/test_chunk.py"
    - "tests/subprocess/encoding/test_audio.py"
    - "tests/subprocess/encoding/test_keyframes.py"
    - "scratch/parity_encode.py"
  modified:
    - "pyproject.toml"
    - ".gitignore"

key-decisions:
  - "Preflight retention in run_encode (review opencode HIGH #2, consensus #6/#7): ONLY the argparse.ArgumentParser/add_argument/parse_args block was cut from main() — the shutil.which tool-availability loop and args.video.is_file() check are retained verbatim as run_encode's first statements. This is the sanctioned minimal structural change for the module/CLI split; ZERO logic changed (D-13 contract stays explicit, not silently contradicted)."
  - "Switched pytest to --import-mode=importlib (pyproject.toml) after tests/unit/encoding/{test_chunk,test_keyframes}.py collided on basename with tests/subprocess/encoding/{test_chunk,test_keyframes}.py under the default 'prepend' import mode. Verified the full suite (detection + encoding, 40 tests) stays green under the new mode."
  - "Task 3 hardware-gated parity run required 3 environment-driven adjustments, none of which are migration bugs (all reproduced identically against the unmodified legacy oracle): (1) -pix_fmt yuv420p on sample generation, since QSV h264 decode rejects testsrc's default yuv444p; (2) a video-only sample, since muxing an audio track shifted the first video packet's pts to ~0.003s, which made qsvencc's --seek fail (\"failed to seek\"/\"failed to initialize file reader(s)\") on a non-exact-zero seek time — reproduced against legacy/encode_scenes.py unmodified, so a synthetic-sample/qsvencc-seek interaction, not a code defect; (3) --no-metrics on both sides, since qsvencc's --psnr/--ssim require an OpenCL device confirmed unavailable in this devcontainer (pre-existing limitation, documented in .planning/codebase/STACK.md)."
  - "Determinism pre-check confirmed qsvencc IS deterministic on this box (two independent legacy runs produced byte-identical movie.obu), so the PRIMARY gate used is byte-identical cmp of the pre-mux movie.obu — the SSIM/PSNR-epsilon fallback path was not needed, though it remains implemented and documented in the script for boxes where qsvencc proves non-deterministic."

patterns-established:
  - "Env-const test overrides via monkeypatch.setattr(module, NAME, value) on the already-imported module object (Pattern 4) — applied throughout tests/unit/encoding/test_chunk.py and tests/subprocess/encoding/test_hdr.py"
  - "chunk_command tested by direct call with no pytest-subprocess fp fixture (it is 100% pure — builds and returns an argv List[str], calls no subprocess) despite being grouped under D-11's TEST-02 target list"

requirements-completed: [TEST-01, TEST-02]

# Metrics
duration: ~50min
completed: 2026-07-08
---

# Phase 1 Plan 3: Encoding Migration & Fast Test Tier Summary

**Mechanically migrated legacy/encode_scenes.py into seven src/enpipe/encoding/ modules behind the shared.proc/shared.logging seam (zero logic change, EBML parser kept inline per D-07), added TEST-01/TEST-02 encoding coverage (14 tests), and proved byte-identical pre-mux movie.obu output against the legacy oracle on real Intel Arc QSV hardware.**

## Performance

- **Duration:** ~50 min (includes real-hardware debugging for Task 3)
- **Started:** 2026-07-08T~12:19:00Z (approx.)
- **Completed:** 2026-07-08T12:37:00Z
- **Tasks:** 3/3 completed
- **Files modified:** 16 (14 created, 2 modified — pyproject.toml, .gitignore)

## Accomplishments
- `src/enpipe/encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py` created from `legacy/encode_scenes.py` with zero logic changes (D-13/D-15): Russian docstrings, `typing.List`/`Optional`/`Tuple` generics, module-level `UPPER_CASE` env-var constants (`ICQ`/`QPMAX`/`GOP_LEN`/`DV_PROFILE`/`FLAC_LEVEL`/`JOBS`), section banners, and the worker-thread `(bool, Optional[str])` tuple-return regime all preserved verbatim
- Every subprocess call routed through `enpipe.shared.proc` (imported as `_proc` to avoid shadowing the pre-existing local `proc = run(...)` CompletedProcess variable name); `die()`/`log()`/`step()` consumed from `enpipe.shared.logging`; `grep -RnE "subprocess\.(run|Popen|call|check_output)" src/enpipe/encoding/` returns zero matches, no local `def run(` remains
- EBML/Cues parser (`_ebml_num`/`_eid`/`_esz`, `keyframe_table_cues`) stays fully inline in `keyframes.py` — confirmed no `mkv/ebml.py` split (D-07; that isolation is Phase 2/DEBT-01)
- `pipeline.run_encode(args)` retains the `shutil.which` tool-availability preflight and `args.video.is_file()` check as its first statements — confirmed via `inspect.getsource(run_encode)` containing `shutil.which`; only the `argparse` parsing block was cut from `main()` (review opencode HIGH #2, consensus #6/#7 sanctioned this as the minimal non-logic structural change)
- `scenes_io.py` moves `import re` to the top of the file (legacy had it mid-file, immediately before first use — the one documented import-order inconsistency in the codebase, per CONVENTIONS.md — not repeated)
- 14 fast-tier tests added and passing under `pytest -m "not hardware"` (33 total in `tests/unit/encoding` + `tests/subprocess/encoding`, 40 total across the whole suite): TEST-01 pure-logic (`read_scenes` incl. silent-skip + die-on-zero, `kf_before`, `fmt_seek`, `_ebml_num`/`_eid`/`_esz`, `chunk_command`, `parse_metrics`) and TEST-02 mocked-subprocess (`detect_hdr`, `count_frames`/`encode_chunk`, `encode_audio`'s never-raises tuple regime, `keyframe_table_ffprobe`'s `die()`/`SystemExit` path), all via `pytest-subprocess`'s `fp` fixture asserting exact argv
- `scratch/parity_encode.py` proved byte-identical pre-mux `movie.obu` between `pipeline.run_encode()` and `legacy/encode_scenes.py` on a real synthetic clip encoded via Intel Arc QSV hardware (`qsvencc`), with a determinism pre-check confirming qsvencc is deterministic on this box (two independent legacy runs produced byte-identical `movie.obu`) before selecting the byte-identical primary gate

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate encoding into seven modules behind the seam and shared die() (preflight retained)** - `4e68d6e` (feat)
2. **Task 2: Encoding fast test tier (TEST-01 pure + TEST-02 mocked)** - `ac02275` (test)
3. **Task 3: Hardware-gated encode parity vs legacy — determinism pre-check + raw .obu compare (D-14)** - `772ba78` (test)

## Files Created/Modified
- `src/enpipe/encoding/scenes_io.py` - `_SCENE_RE`, `read_scenes` (die() on zero-match, silent per-line skip)
- `src/enpipe/encoding/keyframes.py` - `_ebml_num`/`_eid`/`_esz` (EBML byte decode), `keyframe_table_cues` (mkv Cues walk), `keyframe_table_ffprobe` (fallback + die()), `keyframe_table` (dispatcher), `kf_before` (binary search), `fmt_seek` (floor-to-ms)
- `src/enpipe/encoding/hdr.py` - `DV_PROFILE` env const, `detect_hdr` (HDR10/HDR10+/DV flag selection)
- `src/enpipe/encoding/chunk.py` - `ICQ`/`QPMAX`/`GOP_LEN` env consts, `chunk_command` (pure argv builder), `_SSIM_RE`/`_PSNR_RE`/`parse_metrics`, `count_frames`, `encode_chunk`
- `src/enpipe/encoding/audio.py` - `FLAC_LEVEL`/`LOSSLESS`, `encode_audio` ((bool, Optional[str]) tuple, never raises)
- `src/enpipe/encoding/metrics.py` - `write_metrics_csv` (per-scene + frame-weighted "ИТОГО" totals row)
- `src/enpipe/encoding/pipeline.py` - `JOBS`, `probe_fps`, `run_encode(args)` (full orchestration: scenes → keyframe table → HDR → parallel chunk encode + high-water-mark splice → audio wait → CSV → mkvmerge mux)
- `tests/unit/encoding/test_scenes_io.py` / `test_keyframes.py` / `test_chunk.py` - TEST-01 pure-logic coverage
- `tests/subprocess/encoding/test_hdr.py` / `test_chunk.py` / `test_audio.py` / `test_keyframes.py` - TEST-02 mocked-subprocess coverage via `pytest-subprocess`'s `fp` fixture
- `scratch/parity_encode.py` - throwaway D-14 hardware-gated parity script (not packaged, no `[project.scripts]` entry)
- `pyproject.toml` - added `--import-mode=importlib` to `addopts` (Rule 3 fix, see Deviations)
- `.gitignore` - added `scratch/*.metrics.csv` and `scratch/wd_*/` patterns (Rule 3 fix, see Deviations)

## Decisions Made
- **Preflight retention is the sanctioned minimal structural change (D-13):** `run_encode(args)` cuts ONLY the `argparse.ArgumentParser`/`add_argument`/`parse_args` lines from `main()`. The `shutil.which` tool loop and `args.video.is_file()` check are retained verbatim as the first two statements — dropping them silently would have contradicted D-13's "zero logic change" contract. Verified via `inspect.getsource(run_encode)` containing `shutil.which`.
- **`enpipe.shared.proc` imported as `_proc`, not bare `proc`, in all encoding modules:** legacy code already uses the local variable name `proc` for the `subprocess.CompletedProcess` result in `keyframe_table_ffprobe`, `encode_chunk`, `encode_audio`, and the final `mkvmerge` mux call in `pipeline.py`. Aliasing the module import avoids any confusion between the module and the local variable at those call sites (flagged as a naming risk in RESEARCH.md's keyframes.py section).
- **Determinism pre-check drove the parity gate choice, per plan design:** two independent `legacy/encode_scenes.py --keep` runs produced byte-identical `movie.obu` on this box, so qsvencc is confirmed deterministic here — the PRIMARY gate used is byte-identical `cmp` of the pre-mux `movie.obu` (not the SSIM/PSNR-epsilon fallback, which remains implemented but unused on this hardware).
- **Task 3 sample generation needed 3 environment-driven adjustments** (documented in detail under Deviations below) — none are migration bugs; all were verified to reproduce identically against the unmodified `legacy/encode_scenes.py` oracle before being worked around in the parity script itself (never in `src/enpipe/`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Switched pytest to `--import-mode=importlib`**
- **Found during:** Task 2 verification (`pytest -m "not hardware" tests/unit/encoding tests/subprocess/encoding`)
- **Issue:** `tests/unit/encoding/test_chunk.py`/`test_keyframes.py` and `tests/subprocess/encoding/test_chunk.py`/`test_keyframes.py` share basenames (TEST-01 vs TEST-02 coverage of the same source module, exactly as named in the plan's file list). Pytest's default "prepend" import mode requires globally-unique test-file basenames absent `__init__.py` packages, and errored on collection with an "import file mismatch".
- **Fix:** Added `--import-mode=importlib` to `[tool.pytest.ini_options] addopts` in `pyproject.toml` — resolves each test file by its own path instead of a shared module-name namespace, with no other behavior change.
- **Files modified:** `pyproject.toml`
- **Verification:** Full suite (`pytest -m "not hardware"`, detection + encoding, 40 tests) passes after the change; re-ran to confirm Plan 01-02's pre-existing tests were unaffected.
- **Committed in:** `ac02275` (Task 2 commit)

**2. [Rule 3 - Blocking] Fixed "mkv/ebml" grep false-positive in keyframes.py docstring**
- **Found during:** Task 1 acceptance-criteria verification (`grep -Rn "mkv/ebml" src/enpipe/encoding/` was required to return nothing)
- **Issue:** The module docstring explaining D-07 (EBML isolation deferred to Phase 2) originally referenced the literal future module path `mkv/ebml.py`, which the acceptance grep matched.
- **Fix:** Reworded the docstring to describe the future module without the literal `mkv/ebml` substring, preserving the same explanation.
- **Files modified:** `src/enpipe/encoding/keyframes.py`
- **Verification:** `grep -Rn "mkv/ebml" src/enpipe/encoding/` now returns nothing; module still imports cleanly.
- **Committed in:** `4e68d6e` (Task 1 commit)

**3. [Rule 3 - Blocking] Extended `.gitignore` for new scratch artifact types**
- **Found during:** Task 3 post-run cleanliness check (`git status --short --ignored -uall scratch/`)
- **Issue:** The parity script produces `*.metrics.csv` files and per-run `wd_*/` working directories (containing `chunk_*.obu`/`movie.obu`), neither of which the existing `scratch/*.mkv`/`*.scenes`/`*.obu` (single-level glob) patterns covered — nested `scratch/wd_new/movie.obu` and `scratch/new.mkv.metrics.csv` showed up as untracked.
- **Fix:** Added `scratch/*.metrics.csv` and `scratch/wd_*/` to `.gitignore`.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short --ignored -uall scratch/` shows only `scratch/parity_encode.py` as untracked (intended to be committed); all generated artifacts show as ignored (`!!`).
- **Committed in:** `772ba78` (Task 3 commit)

**4. [Rule 3 - Blocking, environment-driven, script-only] Synthetic sample generation adjustments for Task 3's real-hardware run**
- **Found during:** Task 3 execution against real Intel Arc QSV hardware
- **Issue:** Three environment interactions blocked a real encode, none inside `src/enpipe/`:
  (a) `ffmpeg -f lavfi -i testsrc=...` defaults to `yuv444p` (High 4:4:4 Predictive) for h264 output; the Arc QSV hardware decoder rejects this profile outright ("get_buffer() failed" / decode error rate exceeded).
  (b) Muxing an audio track (`sine=duration=10`) alongside the video shifted the first video packet's `pts_time` to `~0.003s` (an AV-sync/mux artifact of this specific lavfi+libx264+audio combination); `qsvencc --seek 00:00:00.003` then failed ("avqsv: failed to seek" / "failed to initialize file reader(s)") because the Cues-derived keyframe time didn't land on an exact-zero seek that qsvencc's own seek path could resolve on this box.
  (c) `qsvencc --psnr --ssim` require an OpenCL device; this devcontainer confirms (per `.planning/codebase/STACK.md`) Intel's own OpenCL ICD is unavailable on Debian trixie, causing `QSVEncC.exe finished with error!` (`clGetPlatformIDs: unknown error`).
- **Root-cause isolation:** (a) and (b) were reproduced by running `legacy/encode_scenes.py` (the unmodified oracle) against the same synthetic sample with the identical failure — confirming these are synthetic-sample/qsvencc-seek/hardware interactions, not a defect in the migrated code. (c) is a pre-existing, already-documented devcontainer limitation unrelated to this migration.
- **Fix (script-only, `scratch/parity_encode.py`, never `src/enpipe/`):** generate the sample with `-pix_fmt yuv420p` and no audio track (video-only clip — `encode_audio`'s behavior is separately covered by `tests/subprocess/encoding/test_audio.py`'s mocked TEST-02 tests, so this loses no coverage), and pass `--no-metrics`/`no_metrics=True` symmetrically to both the oracle and migrated calls.
- **Files modified:** `scratch/parity_encode.py` only
- **Verification:** `uv run python scratch/parity_encode.py` → `PARITY OK` (byte-identical pre-mux `movie.obu`, matching final-`.mkv` frame counts: 240 both sides)
- **Committed in:** `772ba78` (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (3 blocking/mechanical, 1 blocking/environment-driven-and-script-only)
**Impact on plan:** All four fixes are either test-infrastructure/tooling corrections (pytest import mode, gitignore coverage, a docstring wording tweak) or confined entirely to the throwaway `scratch/parity_encode.py` script (never touching `src/enpipe/`). No scope creep; zero logic changes to the migrated encoding modules themselves.

## Issues Encountered
None beyond the four items documented above under Deviations — all were resolved during this plan's execution with no open follow-up required.

## User Setup Required
None - no external service configuration required. Real Intel Arc QSV hardware (`/dev/dri/renderD128`, `qsvencc 8.20`) was already present and functional in this devcontainer.

## Next Phase Readiness
- Both detection (`enpipe.detection.*`, Plan 01-02) and encoding (`enpipe.encoding.*`, this plan) are now fully migrated, seam-routed through `enpipe.shared.proc`/`enpipe.shared.logging`, and independently parity-verified against their respective `legacy/` oracles — the phase's PKG-02/TEST-01/TEST-02 scope is complete.
- `pytest -m "not hardware"` runs 40 tests (7 detection + 33 encoding) in well under a second, with zero real media/hardware invoked — ready as the regression baseline for Phase 2's EBML isolation (DEBT-01) and seek/trim extraction (DEBT-02) work.
- The EBML/Cues parser remains fully inline in `src/enpipe/encoding/keyframes.py`, exactly as D-07 requires — Phase 2 has a clean, single-file target to isolate into a tested `mkv/ebml`-style module.
- `scratch/parity_encode.py` is a throwaway script (not a permanent artifact, no `[project.scripts]` entry); it and its generated `*.mkv`/`*.obu`/`*.scenes`/`*.metrics.csv`/`wd_*/` outputs are gitignored and were not committed as data (only the script itself is tracked).
- **Known environment limitation for future phases to be aware of (not a blocker):** this devcontainer's `qsvencc` cannot compute `--psnr`/`--ssim` metrics (OpenCL unavailable) — any future phase that wants real metrics validation on real hardware will need to either provision a working OpenCL ICD or accept metrics-off encodes in this environment.
- No blockers for Phase 2.

---
*Phase: 01-package-foundation-migration-fast-test-tier*
*Completed: 2026-07-08*

## Self-Check: PASSED

All 16 claimed files verified present on disk (7 src/enpipe/encoding modules, 7 test files, scratch/parity_encode.py, this SUMMARY.md). All 3 claimed commits (`4e68d6e`, `ac02275`, `772ba78`) verified present in `git log --oneline --all`.
