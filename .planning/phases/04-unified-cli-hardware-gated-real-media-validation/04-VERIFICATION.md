---
phase: 04-unified-cli-hardware-gated-real-media-validation
verified: 2026-07-08T17:30:00Z
status: passed
score: 10/10 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Phase 4: Unified CLI + Hardware-Gated Real-Media Validation Verification Report

**Phase Goal:** A single `enpipe` entry point dispatches to the independently-verified detect and encode stages, and the full pipeline is validated end-to-end against real media on real Arc hardware, closing the "never run on real video" gap.
**Verified:** 2026-07-08T17:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `enpipe`, `enpipe detect --help`, `enpipe encode --help` are a real console_script (subprocess, not in-process) | VERIFIED | `uv run enpipe --help`, `uv run enpipe detect --help`, `uv run enpipe encode --help` all exit 0 with Russian help text (ran live). `pyproject.toml` has `[project.scripts] enpipe = "enpipe.cli.main:main"`. |
| 2 | `run_detect` exists in `detection/pipeline.py`, mirrors `run_encode`, no shutil.which preflight (sanctioned deviation) | VERIFIED | Read `src/enpipe/detection/pipeline.py` — no `shutil` import/usage; docstring carries the "САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ" note explaining the absent preflight explicitly. |
| 3 | `.scenes` round-trip is byte-identical to what `read_scenes` consumes | VERIFIED | `run_detect`'s line format (`f"scene {i:4d}  frames [{s:8d}, {e:8d})  ..."`) is byte-identical to `legacy/scene_detection.py:687-690`. `tests/unit/cli/test_run_detect_roundtrip.py` asserts `read_scenes(run_detect_output) == synthetic pairs`; ran green. |
| 4 | Both legacy scripts still run `--help` unmodified; legacy/ untouched | VERIFIED | `uv run python legacy/scene_detection.py --help` and `legacy/encode_scenes.py --help` both exit 0. `legacy/` is untracked in git (no commits touch it); file mtimes (2026-07-07 15:23, 2026-07-08 06:13) predate phase-4 task execution (16:41+). |
| 5 | Thin dispatch — no behavior change; `main(argv)` uses typing generics (no PEP 604) | VERIFIED | `grep -Eq " \| None\| list\[\| tuple\[\|:list\[\|:tuple\[" src/enpipe/{detection/pipeline.py,cli/main.py}` → no match (rc=1). `main.py` imports `Optional, Sequence` from `typing`. |
| 6 | `tests/integration/test_hardware_real_media.py` is `hardware`-marked and excluded from the default tier | VERIFIED | `pytestmark = pytest.mark.hardware` at module level; `pyproject.toml` `addopts = "-m \"not hardware\" ..."`; live run of `uv run pytest -m "not hardware" -q` shows `92 passed, 5 deselected` (the 5 deselected are the hardware tests). |
| 7 | Both hardware tiers run live: SDR/HDR10/legacy-oracle-parity PASS, HDR10+/DV SKIP cleanly | VERIFIED | Live run: `uv run pytest -m hardware -q -rs` → `3 passed, 2 skipped, 92 deselected` in 15.22s on real Arc (`/dev/dri/renderD128` + `qsvencc` 8.20 confirmed present). Skips carry explanatory "NOT a failure" messages pointing at README.md/`$ENPIPE_TEST_MEDIA`. |
| 8 | Independent verification present (keyframe_table_ffprobe ground truth, count_frames on --keep chunks; non-tautological keyframe check) | VERIFIED | `_verify_frame_counts_and_keyframes` re-parses `.scenes` independently, asserts `count_frames(chunk) == e-s` per chunk (load-bearing trim invariant), and cross-checks `compute_chunk_seek_trim`/`kf_before` against an independent `keyframe_table_ffprobe` ground-truth set (the old tautological `max({f<=s}) exists` check was explicitly removed per SUMMARY). |
| 9 | DV RPU check uses only ffprobe-native AV1 DOVI OBU inspection; no forbidden mutating bsf / dovi_tool extract-rpu | VERIFIED | `grep -Eq "extract-rpu\|-bsf:v(:[0-9]+)?[[:space:]]*dovi_rpu"` on the test file → no match. The only `bsf=dovi_rpu` occurrence is the read-only `ffmpeg -h bsf=dovi_rpu` self-check (line 414). |
| 10 | Legacy-oracle parity (SC4): legacy/encode_scenes.py run read-only, count_frames parity asserted | VERIFIED | `test_sdr_legacy_oracle_parity` runs `legacy/encode_scenes.py` via `subprocess.run` (never imported), asserts `count_frames(legacy_out) == count_frames(enpipe_out)` plus a determinism-aware pre-mux `movie.obu` byte/frame-count comparison. Ran live and PASSED (part of the 3 passed above). |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/enpipe/detection/pipeline.py` | `run_detect(args)` mirroring `run_encode` | VERIFIED | 52 lines, exports `run_detect`, no PEP604, no shutil preflight, sanctioned-deviation docstring present |
| `src/enpipe/cli/main.py` | `build_parser()` + `main()` argparse dispatcher | VERIFIED | 66 lines, `add_subparsers` present, both subcommands wired via `set_defaults(func=...)` |
| `src/enpipe/cli/__init__.py` | package marker | VERIFIED | 1-line Russian docstring |
| `pyproject.toml` | `[project.scripts] enpipe = "enpipe.cli.main:main"` | VERIFIED | present, replacing the old reserved-slot comment |
| `tests/integration/test_hardware_real_media.py` | TEST-04 hardware suite | VERIFIED | 527 lines, `pytest.mark.hardware`, all 5 tests present and behave as designed |
| `tests/fixtures/media/README.md` | fixtures documentation | VERIFIED | documents filenames, `$ENPIPE_TEST_MEDIA`, D-06 rationale |
| `.gitignore` | ignores operator media, keeps README tracked | VERIFIED | `tests/fixtures/media/*` + `!tests/fixtures/media/README.md` block present |
| `.github/workflows/hardware-integration.yml` | D-08 self-hosted CI stub | VERIFIED | `workflow_dispatch:` only, no `push`/`pull_request`, targets `[self-hosted, arc]`, runs `pytest -m hardware -rs` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cli/main.py` | `detection/pipeline.py` | `import run_detect` + `set_defaults(func=run_detect)` | WIRED | confirmed in source and by live `enpipe detect` subprocess run |
| `cli/main.py` | `encoding/pipeline.py` | `import run_encode` + `set_defaults(func=run_encode)` | WIRED | confirmed in source and by live `enpipe encode` subprocess run |
| `detection/pipeline.py` | `encoding/scenes_io.py` | `.scenes` line format ↔ `_SCENE_RE` | WIRED | byte-identical format string; round-trip test passes |
| `test_hardware_real_media.py` | `enpipe.cli.main` | `_run_cli` SystemExit-safe wrapper around `main(argv)` | WIRED | used by all 5 hardware tests; ran live, drove real detect→encode |
| `test_hardware_real_media.py` | `enpipe.encoding.keyframes.compute_chunk_seek_trim` | independent ground-truth cross-check | WIRED | present and exercised in `_verify_frame_counts_and_keyframes`, ran live |
| `test_hardware_real_media.py` | `legacy/encode_scenes.py` | read-only subprocess parity oracle | WIRED | `test_sdr_legacy_oracle_parity` ran live and passed |
| `test_hardware_real_media.py` | ffprobe `side_data_list` | read-only DV/HDR10 survival probes | WIRED | `_frame_side_data_types`/`_dv_rpu_frame_count` present, used by `test_hdr10` (ran live, passed) and `test_dv` (fixture-gated skip verified) |

### Behavioral Spot-Checks / Live Runs

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| console_script smoke | `uv run enpipe --help / detect --help / encode --help` | all rc=0, Russian help text | PASS |
| legacy scripts still runnable | `uv run python legacy/scene_detection.py --help`, `legacy/encode_scenes.py --help` | both rc=0 | PASS |
| fast tier unaffected | `uv run pytest -m "not hardware" -q` | `92 passed, 5 deselected` in 20.9s | PASS |
| hardware tier live | `uv run pytest -m hardware -q -rs` | `3 passed, 2 skipped, 92 deselected` in 15.2s on real Arc (`/dev/dri/renderD128`, `qsvencc` 8.20) | PASS |
| no PEP604 generics | grep gate on `detection/pipeline.py` + `cli/main.py` | no match | PASS |
| no forbidden DV bsf usage | grep gate on hardware test file | no match (only self-check `ffmpeg -h bsf=dovi_rpu`) | PASS |
| no unresolved debt markers | grep `TBD\|FIXME\|XXX` across phase-4 files | no match | PASS |
| all task commits present | `git log --oneline --all` | all 8 commit hashes from both SUMMARYs found | PASS |
| legacy/ untouched | mtime + git-tracking check | both files' mtimes predate phase-4 task timestamps; `legacy/` is untracked (never committed, never diffed) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PKG-01 | 04-01-PLAN.md | unified `enpipe` entry point over detect/encode, preserving `.scenes` handoff | SATISFIED | console_script installed and subprocess-smoke-tested; round-trip test green; legacy untouched and runnable |
| TEST-04 | 04-02-PLAN.md | hardware-gated end-to-end test verifying frame counts/keyframe alignment/DV RPU survival, marker-excluded from default CI | SATISFIED | live hardware run: 3 passed (SDR, HDR10, legacy-oracle-parity), 2 honestly skipped (HDR10+/DV, no fixtures); excluded from `-m "not hardware"` default tier |

No orphaned requirements — `.planning/REQUIREMENTS.md` traceability table maps only PKG-01 and TEST-04 to Phase 4, matching both plans' declared `requirements:` frontmatter exactly.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any phase-4-modified file. No empty stub implementations. The one `pytest.skip("libx265 encoder not available...")` line matched a generic `not available` grep but is a legitimate, intentional, documented environment-gate skip (opencode M4 in the plan), not a stub — confirmed by reading context (Task 1b design).

### Human Verification Required

None. All must-haves are verified programmatically via live subprocess/pytest runs on real hardware present in this devcontainer — no visual, UX, or external-service items requiring human judgment remain for this phase.

### Gaps Summary

No gaps. All 10 derived truths (roadmap goal decomposed via PLAN frontmatter must_haves, since ROADMAP.md phase success_criteria were not separately queried but PLAN frontmatter fully covers PKG-01 and TEST-04 scope) are VERIFIED against live command execution, not SUMMARY.md narrative. Both hardware-tier live runs (`-m hardware` and `-m "not hardware"`) were executed fresh during this verification session on the real Intel Arc GPU present in this devcontainer, producing the exact pass/skip/deselect counts the plans specified.

---

*Verified: 2026-07-08T17:30:00Z*
*Verifier: Claude (gsd-verifier)*
