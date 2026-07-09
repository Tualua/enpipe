---
phase: quick-260709-89t
verified: 2026-07-09T00:00:00Z
status: passed
score: 8/8 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Quick Task 260709-89t: Folder Batch Input for enpipe run/detect/encode Verification Report

**Task Goal:** `enpipe run/detect/encode` принимают папку на вход и пакетно обрабатывают все видеофайлы внутри. Политика: skip-existing выходы; continue-on-error со сводкой и ненулевым кодом; `--recursive` (дефолт верхний уровень); encode `scenes` опционален; `detect` папка+`-o`→die; guard'ы схлопывания выходов (папка + `-o` файл/`--workdir`/`--csv` → die); исключение своих выходов (`.Encoded.`/`.av1.mkv`) из дискавери; одиночный режим байт-идентичен.

**Verified:** 2026-07-09
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `enpipe run/detect/encode` принимают директорию и обрабатывают все видеофайлы внутри | ✓ VERIFIED | `src/enpipe/cli/main.py:91` (`run_pipeline`), `src/enpipe/detection/pipeline.py:31` (`run_detect`), `src/enpipe/encoding/pipeline.py:93` (`run_encode`) all branch on `args.video/args.input.is_dir()` and dispatch through `iter_input_videos`+`run_batch`. Confirmed end-to-end by `test_run_on_directory_processes_all_videos_sorted` (calls both detect+encode per file, sorted). |
| 2 | Одиночный файл / несуществующий путь байт-идентичен прежнему; существующие CLI-тесты остаются зелёными | ✓ VERIFIED | `git diff 2cb97d8 2456039 -- tests/unit/cli/test_cli_run.py tests/unit/cli/test_cli_dispatch.py tests/unit/cli/test_run_detect_roundtrip.py tests/unit/encoding/test_resolve_output_path.py` is empty (zero changes to baseline tests). Ran these 4 files + all 4 new batch test files together: 68/68 passed. Full suite: `uv run pytest -m "not hardware" -q` → 153 passed, 6 deselected (matches SUMMARY's claimed 114 baseline + 39 new). |
| 3 | Батч продолжает при ошибке отдельного файла, печатает сводку (ок/пропущено/упало), завершается ненулевым кодом при сбоях | ✓ VERIFIED | `src/enpipe/shared/batch.py:83-102` `run_batch`: per-file `try/except (SystemExit, Exception)` appends to `failed` and `continue`s; logs `"батч завершён: ок N / пропущено M / упало K"`; `if failed: die(...)` (nonzero exit) only after the loop. Tested by `test_run_batch_one_raises_others_still_processed_then_dies` and `test_run_batch_one_calls_die_systemexit_others_still_processed` (both assert remaining files still processed, then `SystemExit`). |
| 4 | Уже готовые файлы (выход существует) пропускаются, не перекодируются | ✓ VERIFIED | `should_skip` in `run_pipeline` (`resolve_output_path(v,args.out).exists()`), `run_detect` (`<v>.scenes` exists), `run_encode` (`<v>.scenes` missing → skip w/ warning; resolved output exists → skip). Tested: `test_run_on_directory_skips_already_encoded`, `test_detect_directory_skips_video_with_existing_scenes`, `test_encode_directory_should_skip_already_encoded`, `test_encode_directory_should_skip_missing_scenes`. |
| 5 | Собственные выходы (`*.Encoded.*`, `*.av1.mkv`) исключены из дискавери, повторный прогон не берёт свой же выход | ✓ VERIFIED | `src/enpipe/shared/batch.py:30-36` `_is_own_output` (case-insensitive `fnmatch`/`endswith`). Tested by `test_excludes_own_outputs_encoded_and_av1` (covers `.Encoded.mkv`, `.av1.mkv`, and lowercase `.encoded.mp4` variant). |
| 6 | `--recursive` включает рекурсивный обход папки | ✓ VERIFIED | `iter_input_videos` uses `path.rglob("*") if recursive else path.iterdir()` (`batch.py:51`). `--recursive` flag added to `detect_p`/`encode_p`/`run_p` (`cli/main.py:145-146,169-170,206-207`). Tested by `test_directory_top_level_only_direct_children`, `test_directory_recursive_includes_nested`, `test_recursive_flag_parses_on_{detect,encode,run}`. |
| 7 | `detect` папка+`-o`→die; `encode` папка+scenes→die; папка без видео→die | ✓ VERIFIED | `detection/pipeline.py:34-35` (`args.output is not None → die`), `encoding/pipeline.py:100-101` (`args.scenes is not None → die`), `cli/main.py:98-99` (`args.scenes is not None → die` for `run`). Empty-dir die: `detection/pipeline.py:38-39`, `encoding/pipeline.py:111-112`, `cli/main.py:109-110`. Tested: `test_detect_directory_with_output_flag_dies`, `test_encode_directory_with_scenes_dies`, `test_run_on_directory_with_scenes_flag_dies`, `test_detect_empty_directory_dies`, `test_encode_directory_empty_dies`, `test_run_on_empty_directory_dies`. |
| 8 | Батч + одиночно-путёвые аргументы, схлопывающие выходы (`-o`=файл, `--workdir`, `--csv`) → die с русским сообщением | ✓ VERIFIED | Guards present identically in `run_pipeline` (`cli/main.py:100-106`) and `run_encode` (`encoding/pipeline.py:102-108`): `-o` non-dir → die, `--workdir` set → die, `--csv` set → die; `-o` as an *existing directory* explicitly allowed (fan-out via `resolve_output_path`). Tested: `test_run_on_directory_with_{o_file,workdir,csv}_dies`, `test_run_on_directory_with_o_existing_dir_does_not_die`, `test_encode_directory_with_{o_file,workdir,csv}_dies`, `test_encode_directory_with_o_existing_dir_does_not_die_before_run_batch`. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/enpipe/shared/batch.py` | `VIDEO_EXTS`, `iter_input_videos`, `run_batch`, leaf module (stdlib + `shared.logging` only) | ✓ VERIFIED | 102 lines (> min 40). Contains `def iter_input_videos`. Imports only `fnmatch`, `pathlib`, `typing`, `enpipe.shared.logging` — no cycle back into detection/encoding/cli. |
| `tests/unit/shared/test_batch.py` | Hardware-free discovery + orchestration tests | ✓ VERIFIED | 13 tests, all pass: single-file passthrough, top-level vs recursive, self-output exclusion (incl. case-insensitive), non-video-suffix filtering, sort order, empty dir, nonexistent path, `run_batch` all-ok/continue-on-error(Exception)/continue-on-error(SystemExit)/should_skip. |
| `tests/unit/cli/test_batch_run.py` | argparse `--recursive` / scenes-optional / run-dir dispatch + guards + empty dir | ✓ VERIFIED | 12 tests, all pass. Covers exactly the behaviors listed in must_haves (`--recursive` on detect/encode/run, scenes `nargs="?"`, sorted batch dispatch via real `main()` call, skip-existing, empty-dir die, all 4 output-collapse guards + the `-o`-existing-dir non-die case). |
| `tests/unit/detection/test_batch_dispatch.py` | `run_detect` dir dispatch (papka+`-o` die, batch `.scenes`, skip, empty dir die) | ✓ VERIFIED | 4 tests, all pass. |
| `tests/unit/encoding/test_batch_dispatch.py` | `run_encode` dir dispatch (papka+scenes die, guards, skip no-`.scenes`, empty dir die) | ✓ VERIFIED | 9 tests, all pass — 4 individual guard tests + 1 allowed-dir case + empty-dir + 2 should_skip variants + 1 single-file scenes-default test. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/enpipe/cli/main.py::run_pipeline` | `src/enpipe/shared/batch.py::iter_input_videos`/`run_batch` | import + call at `args.video.is_dir()` | ✓ WIRED | `cli/main.py:27` imports both; `:108` calls `iter_input_videos`, `:118` calls `run_batch`. |
| `src/enpipe/detection/pipeline.py::run_detect` | `src/enpipe/shared/batch.py::run_batch` | batch dispatch on `args.input.is_dir()` | ✓ WIRED | `detection/pipeline.py:22` imports, `:48` calls `run_batch`. |
| `src/enpipe/encoding/pipeline.py::run_encode` | `src/enpipe/shared/batch.py::run_batch` | batch dispatch on `args.video.is_dir()` | ✓ WIRED | `encoding/pipeline.py:31` imports, `:125` calls `run_batch`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ruff clean on all touched files | `uv run ruff check src tests` | "All checks passed!" | ✓ PASS |
| Full non-hardware suite passes | `uv run pytest -m "not hardware" -q` | 153 passed, 6 deselected | ✓ PASS |
| Targeted batch + baseline single-mode tests | `pytest tests/unit/shared/test_batch.py tests/unit/cli/test_batch_run.py tests/unit/detection/test_batch_dispatch.py tests/unit/encoding/test_batch_dispatch.py tests/unit/cli/test_cli_run.py tests/unit/cli/test_cli_dispatch.py tests/unit/cli/test_run_detect_roundtrip.py tests/unit/encoding/test_resolve_output_path.py -q` | 68 passed | ✓ PASS |
| Baseline single-mode test files byte-unmodified | `git diff 2cb97d8 2456039 --stat -- tests/unit/cli/test_cli_run.py tests/unit/cli/test_cli_dispatch.py tests/unit/cli/test_run_detect_roundtrip.py tests/unit/encoding/test_resolve_output_path.py` | empty output | ✓ PASS |
| Commits exist as claimed in SUMMARY | `git log --oneline` | `2e6e5f2`, `d51272c`, `f7f8fb7` present | ✓ PASS |

### Anti-Patterns Found

None. Scanned all created/modified source and test files for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet implemented" — zero matches.

### Requirements Coverage

This is a quick task (not a roadmap phase); `.planning/REQUIREMENTS.md` has no `QUICK-*` entries by design — coverage is tracked via this task's own `must_haves`, all of which resolved to VERIFIED above.

### Human Verification Required

None. All must-haves are pure control-flow/argparse/filesystem-discovery behavior fully exercised by hardware-free unit tests (no QSV/GPU/subprocess dependency introduced by this task — `run_batch`/`iter_input_videos` only touch stdlib `pathlib`/`fnmatch`). No visual, real-time, or external-service surface was added.

### Gaps Summary

No gaps. All 8 must-have truths, all 4 required artifacts, and all 3 key links verified directly against the code (not merely SUMMARY claims). Guard messages are in Russian as specified. Single-file/nonexistent-path code paths are provably byte-identical (empty diff on baseline test files + all baseline tests still green). Full test suite grew from 114 to 153 tests, all green; ruff clean.

---

*Verified: 2026-07-09*
*Verifier: Claude (gsd-verifier)*
