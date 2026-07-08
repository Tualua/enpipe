# Testing Patterns

**Analysis Date:** 2026-07-08

## Current State: No Automated Tests Exist

A repo-wide search for test files/frameworks turned up nothing:
- No `test_*.py`, `*_test.py`, `tests/` directory, or `conftest.py` anywhere in the repository.
- No `pytest.ini`, `pyproject.toml` `[tool.pytest]` section, `tox.ini`, or any other test-runner config.
- No CI configuration (no `.github/workflows/`, no other CI config) that would run tests.
- `.gitignore` includes standard Python test/coverage artifacts (`.pytest_cache/`, `.coverage`, `htmlcov/`, `.tox/`, `.hypothesis/`) suggesting `pytest` + `coverage` is the anticipated future toolchain, but none of these tools are installed or configured yet (`.devcontainer/post-create.sh` only installs `scenedetect[opencv-headless]` and `numpy`, no `pytest`).
- `legacy/scene_detection.py`'s own module docstring admits this directly: **"Модуль не прогонялся на реальном видео — ждёт интеграционного теста на NAS."** ("This module has not been run against real video — awaiting an integration test on the NAS.") — `legacy/scene_detection.py:30`.

**Practical implication for anyone extending this codebase:** there is no existing test harness, fixtures, or mocking convention to follow. Any testing work is greenfield. The sections below describe (a) the *planned* test that is explicitly specified but not implemented, and (b) the de facto verification strategy actually used today (manual/runtime self-checks baked into the pipeline scripts themselves), since that is the closest thing to "testing patterns" this codebase currently has.

## Planned Test (Specified, Not Implemented)

`PIPELINE_DESIGN.md` prescribes exactly one test, as a **mandatory precondition** for implementing the streaming scene-detection refactor it designs — it is explicitly called out as `(обязателен)` ("mandatory"):

> **Регресс-тест (обязателен):** `list(detect_scenes_streaming(f)) == detect_scenes(f, jobs=1)`
> по парам `(start_frame, end_frame)` — щит против будущих изменений PySceneDetect.
> (`PIPELINE_DESIGN.md:131-132`)

Translation/intent: a regression test asserting that the (not-yet-implemented) streaming detector `detect_scenes_streaming()` produces exactly the same `(start_frame, end_frame)` pairs as the existing batch `detect_scenes(path, jobs=1)`, guarding against future PySceneDetect internals changes silently breaking the streaming callback assumption (`AdaptiveDetector.post_process` returning `[]`, discussed at `PIPELINE_DESIGN.md:75-78`).

**Status:** `detect_scenes_streaming()` itself does not exist yet in `legacy/scene_detection.py` (only the design sketch at `PIPELINE_DESIGN.md:88-129` exists). Per `PIPELINE_DESIGN.md:219-229` ("Статус реализации"), both the streaming detector and its regression test are "спроектировано (готово к коду), НЕ реализовано" — designed and ready to code, but not implemented — and the design doc's own verdict is **not to build this** on current hardware (see TL;DR at the top of the file), so this test may never be written unless the hardware/storage situation changes (SSD/NVMe source, per `PIPELINE_DESIGN.md:227-229`).

**If implementing this test:** it would need a real (or fixture) video file and both PySceneDetect and the QSV/ffmpeg toolchain available — i.e. it is an integration test, not a unit test, given the current architecture (no mocking seams exist between `detect_scenes()` and subprocess/ffmpeg/PySceneDetect).

## De Facto Verification Strategy (What Exists Today Instead of Tests)

In the absence of automated tests, `legacy/encode_scenes.py` relies heavily on **runtime self-checks with hard failure** (`die()`) at multiple pipeline stages, functioning as inline invariant assertions rather than pre-run tests:

- **Per-chunk frame-count verification:** after every `qsvencc` chunk encode, `encode_chunk()` re-probes the output with `count_frames()` and compares against the expected frame count for that scene; mismatch is reported as a per-chunk error, not silently ignored (`legacy/encode_scenes.py:410-417`).
- **Post-concatenation frame-count verification:** after all chunks are streamed together into `movie.obu`, the total frame count is re-counted and compared against `total_expect` (`sum(e - s for s, e in scenes)`); mismatch calls `die()` (`legacy/encode_scenes.py:660-664`).
- **Full-file consistency check:** for non-partial runs, the final frame count is additionally compared against the last scene's `end_frame` from the scene log, logging a warning (not a hard failure) if they disagree — a softer sanity check for a symptom that "shouldn't happen" (`legacy/encode_scenes.py:665-667`).
- **Ordered-append integrity check:** `next_append != len(tasks)` after the encode loop indicates the "high-water mark" flush left a gap (a chunk failed silently or a race occurred) and is treated as fatal (`legacy/encode_scenes.py:656-657`).
- **Preflight tool availability check:** `main()` checks `shutil.which(tool)` for `qsvencc`, `ffprobe`, `ffmpeg`, `mkvmerge` before doing any work, failing fast with `die()` rather than partway through a long-running job (`legacy/encode_scenes.py:532-534`).
- `legacy/scene_detection.py`'s module docstring documents specific manual verification already performed against the PySceneDetect 0.7 source (not automated, but recorded as engineering evidence): "Проверено против PySceneDetect 0.7 (API VideoStream отличается от 0.6.x...)" (`legacy/scene_detection.py:28-29`), and separately notes chunk-boundary correctness was validated empirically: "SSIM 0.9999 к trim-от-0" for seek+trim chunk boundaries (`legacy/encode_scenes.py:11-12`) — i.e. accuracy claims in this codebase are currently backed by one-off manual SSIM comparisons run outside any test suite, not by repeatable automated tests.

**If you add tests to this codebase, prioritize covering these existing runtime invariants as real unit/integration tests** (frame-count arithmetic in `count_frames`/`total_expect` handling, the high-water-mark `flush_appends()` ordering logic, `kf_before()`'s binary search, and `_sanitize_boundaries()`/boundary-merging logic in the parallel detector) — these are the parts of the codebase with the most non-obvious numeric/ordering logic and currently zero coverage.

## Recommended Test Framework (Not Yet Adopted)

No framework has been chosen or installed. Given the Python/stdlib-heavy style of this codebase and the `.gitignore` already anticipating `pytest`/coverage artifacts, **`pytest`** is the natural fit if/when tests are introduced:
- Pure-logic helpers with no subprocess/GPU dependency are unit-testable today with no refactoring: `kf_before()`, `fmt_seek()`, `_min_scene_len()`, `_sanitize_boundaries()`, `parse_metrics()`, `write_metrics_csv()` (metrics math), `read_scenes()` (regex parsing), and the standalone EBML integer parsers `_ebml_num()`/`_eid()`/`_esz()` in `legacy/encode_scenes.py`.
- Functions that shell out to `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` (`probe_source`, `detect_hdr`, `encode_chunk`, `encode_audio`, `keyframe_table_ffprobe`) have no dependency-injection seam today (no client abstraction — `subprocess.run`/`Popen` calls are inline). Testing these would require either `subprocess` mocking (`unittest.mock.patch("subprocess.run")`) or real fixture media files; no existing convention favors one over the other yet.

## Coverage

**Requirements:** None enforced — no coverage tool configured, no coverage target documented anywhere.

---

*Testing analysis: 2026-07-08*
