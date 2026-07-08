# Coding Conventions

**Analysis Date:** 2026-07-08

**Scope note:** This repository has no application framework or package
manifest yet — it consists of two standalone Python scripts under `legacy/`
(`legacy/scene_detection.py`, `legacy/encode_scenes.py`) plus a Russian-language
design document (`PIPELINE_DESIGN.md`) describing planned (not yet implemented)
refactoring work, and a `.devcontainer/` setup. Conventions below are derived
from the actual code in `legacy/`. Where `PIPELINE_DESIGN.md` prescribes a
convention that is not yet implemented, this is called out explicitly as
**Planned**, not existing practice.

## Language & Runtime

- **Python 3.12** (per `.devcontainer/Dockerfile`, `mcr.microsoft.com/devcontainers/python:3-3.12-trixie`).
- Every module starts with `from __future__ import annotations` (`legacy/scene_detection.py:33`, `legacy/encode_scenes.py:33`).
- Type hints use the `typing` module generics (`List`, `Optional`, `Tuple`, `Union`, `Dict`) rather than the bare `list[...]`/`tuple[...]` syntax available in 3.9+, despite targeting 3.12 — follow this existing style for consistency rather than switching to built-in generics mid-file.
- No `pyproject.toml`, `setup.py`, or `requirements.txt` exists. Dependencies (`scenedetect[opencv-headless]`, `numpy`) are installed ad hoc via `pip install` in `.devcontainer/post-create.sh:34`. There is no dependency pinning/lockfile — if you add dependencies, prefer creating a `pyproject.toml` rather than continuing the implicit-install pattern.

## Documentation Language

- **All comments, docstrings, log messages, CLI help text, and error messages are written in Russian.** This is consistent across both `legacy/` files and `PIPELINE_DESIGN.md`. Maintain Russian for in-code prose when extending these files; code identifiers (function/variable/class names) are in English.
- Module docstrings are substantial "why" documents, not just summaries — see the top of `legacy/scene_detection.py:1-31` and `legacy/encode_scenes.py:1-32`, which explain pipeline rationale, key engineering decisions, and known limitations before any code. Follow this pattern for new modules: a design-rationale docstring, not a one-liner.

## Naming Patterns

**Files:**
- Lowercase snake_case module names describing the pipeline stage: `scene_detection.py`, `encode_scenes.py`.

**Functions:**
- `snake_case`, verb-first for actions (`detect_scenes`, `probe_source`, `encode_chunk`, `read_scenes`, `keyframe_table_cues`).
- Private/internal helpers prefixed with a single underscore: `_detect_relative`, `_build_scenes`, `_min_scene_len`, `_boundary_worker`, `_segment_worker`, `_ebml_num`, `_eid`, `_esz` (`legacy/scene_detection.py`), `_SCENE_RE`, `_SSIM_RE`, `_PSNR_RE` (`legacy/encode_scenes.py`).
- Multiprocessing/thread worker functions used with `ProcessPoolExecutor`/`ThreadPoolExecutor` are defined at module level (not as closures/lambdas) because closures don't pickle — see the comment at `legacy/scene_detection.py:567-569`.

**Variables:**
- `snake_case` throughout. Short, local, math/stream-oriented names are acceptable in tight numeric code (`s`, `e`, `t`, `p`, `q`, `kf_frame`, `kf_time`) as long as the enclosing function/docstring establishes context — this is a deliberate density trade-off in hot-path binary-parsing code (`legacy/encode_scenes.py:130-263`, the Matroska/EBML Cues parser).

**Types / Classes:**
- `PascalCase` for classes and dataclasses: `DetectionConfig`, `SourceInfo`, `Scene`, `QsvPipeStream`, `SceneDetectionError`.
- Custom exceptions subclass the most specific stdlib exception that fits and get a one-line Russian docstring: `class SceneDetectionError(RuntimeError): """Ошибка этапа детектирования сцен (ffprobe/ffmpeg/пайп)."""` (`legacy/scene_detection.py:53-54`).

**Constants:**
- Module-level `UPPER_CASE`, frequently sourced from environment variables with a typed cast and default, e.g. `ICQ = int(os.environ.get("ICQ", "23"))` (`legacy/encode_scenes.py:52-57`). This is the established pattern for making CLI/pipeline scripts tunable without argparse plumbing for every knob — reuse it for new global encode/detect parameters instead of adding new argparse flags for every tunable.

**Type aliases:**
- `PathLike = Union[str, Path]` declared once near the top of a module and reused in signatures (`legacy/scene_detection.py:50`).

## Data Modeling

- Immutable value objects use `@dataclass(frozen=True)`: `DetectionConfig`, `SourceInfo`, `Scene` (`legacy/scene_detection.py:62-107`). Use frozen dataclasses for any new config/value objects — the codebase has no precedent for mutable config objects.
- Dataclasses may carry computed `@property` members alongside stored fields, e.g. `Scene.frame_count` (`legacy/scene_detection.py:105-107`).
- Plain tuples are used freely for lightweight internal pairs/records passed between functions (e.g. `Tuple[int, int]` scene boundaries, `Tuple[int, float, bool]` boundary candidates) rather than introducing a dataclass for every internal shape — reserve dataclasses for values that cross a public function boundary or get documented; use tuples for purely internal producer/consumer plumbing.

## Code Style

**Formatting:**
- No formatter config present (no `.prettierrc`, no `black`/`ruff` config file). Existing code is manually formatted but consistent: ~88-100 col soft wrap, multi-line function-call argument lists broken one-arg-group-per-line with trailing comma style, comments aligned with `# --- section --- #` banner dividers to delimit logical sections within a file (see banners throughout `legacy/encode_scenes.py`, e.g. lines 48-51, 70-73, 91-93, 329-331, 351-353, 420-422, 512-514).
- No linter config present (no `.flake8`, `ruff.toml`, `mypy.ini`). Type hints are used throughout but never checked by a type checker in CI (there is no CI). Treat type hints as documentation-grade, not enforced.

**Section banners:**
- Both `legacy/*.py` files divide their body into named sections with a fixed-width comment banner:
  ```python
  # --------------------------------------------------------------------------- #
  # Конфигурация и модели данных
  # --------------------------------------------------------------------------- #
  ```
  Follow this exact banner style (79-char rule, Russian section title) when adding new logical sections to these files or new sibling scripts in the same pipeline.

**Inline "why" comments:**
- Comments consistently explain *why*, not *what* — e.g. the `-copyts`/`select` seek workaround (`legacy/scene_detection.py:225-251`), the stderr-to-tempfile-not-PIPE deadlock avoidance (`legacy/scene_detection.py:210-214`), the `floor_ms` seek rounding rationale (`legacy/encode_scenes.py:316-326`). New code in this style should keep justifying non-obvious engineering decisions inline rather than relying on commit messages or external docs.

## Import Organization

**Order observed** (`legacy/scene_detection.py:33-48`, `legacy/encode_scenes.py:33-46`):
1. `from __future__ import annotations`
2. Stdlib imports, alphabetized (`json`, `subprocess`, `tempfile`, then `concurrent.futures`, `dataclasses`, `fractions`, `pathlib`, `typing`)
3. Third-party imports (`numpy`, `scenedetect.*`)
4. No local/project imports exist yet (each script is self-contained).
- One exception: `encode_scenes.py` imports `re` mid-file, right before its first use in the "Разбор входных данных" section (`legacy/encode_scenes.py:94`), rather than at the top with other stdlib imports. This is inconsistent with the top-of-file import block used for everything else — do not repeat this pattern; keep new imports grouped at the top of the file with the rest of stdlib imports.

**No path aliases** — plain relative/absolute imports only (no package structure exists yet).

## Error Handling

**Two distinct error-handling regimes coexist, by module role:**

1. **Library code (`scene_detection.py`)** raises typed exceptions. A single custom exception class `SceneDetectionError(RuntimeError)` is raised for all domain failures (ffprobe missing, ffmpeg nonzero exit, zero frames decoded, no video stream found). Call sites wrap `subprocess` failures and translate them:
  ```python
  try:
      out = subprocess.run(cmd, capture_output=True, check=True)
  except FileNotFoundError as exc:
      raise SceneDetectionError(f"ffprobe не найден: {config.ffprobe_bin}") from exc
  except subprocess.CalledProcessError as exc:
      raise SceneDetectionError(
          f"ffprobe завершился с кодом {exc.returncode}: "
          f"{exc.stderr.decode(errors='replace').strip()}"
      ) from exc
  ```
  (`legacy/scene_detection.py:125-133`). Always use `raise ... from exc` to preserve the chain.

2. **CLI entry-point / orchestration code (`encode_scenes.py`)** uses a `die(msg)` helper that calls `sys.exit(f"encode_scenes: {msg}")` (`legacy/encode_scenes.py:62-63`) instead of raising exceptions, since this module is a top-level script whose only caller is a human/shell. `die()` is called directly at validation points (missing tool, empty scene list, chunk failures, frame-count mismatches) rather than being wrapped in try/except — fail fast, fail loud, no swallowed errors.
- **Background work must not use `die()`**: `encode_audio()` explicitly returns `(bool, Optional[str])` instead of raising/exiting because it runs inside a background `ThreadPoolExecutor` thread — see the docstring: "Ошибку НЕ бросает (крутится в фоновом потоке — падать через die() нельзя, всплыло бы криво)" (`legacy/encode_scenes.py:426-427`). Apply this rule generally: **worker-thread functions return `(success, error_message)` tuples; they never call `die()` or `sys.exit()`.** The consumer joins the future and calls `die()` on the main thread once the error surfaces.
- Cleanup/close methods distinguish "abnormal stop" (`close()` — kill process, no returncode check, `legacy/scene_detection.py:290-299`) from "normal completion" (`finish()` — wait, check returncode, raise on failure, `legacy/scene_detection.py:301-325`). When adding new resource-owning classes, provide both an idempotent forced-close and a checked graceful-finish method rather than a single `close()`.
- Streaming generators use `try/finally` to guarantee cleanup on early exit or exception from the consumer side (planned pattern in `PIPELINE_DESIGN.md:126-128`, shown with `finally: cancel.set(); manager.stop(); worker.join(timeout=35)`).
- Batch-vs-partial failure handling in `encode_scenes.py::main`: individual chunk failures are collected into an `errors: List[str]` list rather than aborting immediately, so the pipeline reports *all* failed chunks (capped at 10) before calling `die()` once, at `legacy/encode_scenes.py:653-655`. Prefer collect-then-report over fail-on-first when processing many independent parallel units.

## Concurrency Patterns

- `ThreadPoolExecutor` is used for I/O/GPU-bound parallel work (encode chunks, ffprobe boundary searches) because the actual work happens in subprocesses, so the GIL doesn't matter.
- `ProcessPoolExecutor`-style workers (functions, not the pool itself, currently only prepared for future process-pool use) are kept at module scope specifically because "CPU-детектор PySceneDetect в потоках сериализуется, в процессах — нет" (`legacy/scene_detection.py:568-569`) — i.e. genuinely CPU-bound Python work (the scene detector itself) needs real processes to bypass the GIL, whereas subprocess-driven work only needs threads.
- Ordered output from unordered parallel completion uses a "high-water mark" pattern: results keyed by index in a dict (`ready: Dict[int, int]`), flushed to the output stream only when the next expected index becomes available (`flush_appends()`, `legacy/encode_scenes.py:608-617`). This is the standard pattern in this codebase for "parallelize work, but must emit/merge results in original order" — reuse it rather than inventing a new ordering scheme (also documented as the pattern to reuse for the planned streaming consumer in `PIPELINE_DESIGN.md:52-58, 149-151`).
- Background/parallel side-work (audio encode while video chunks encode) is started via a **dedicated single-worker pool** (`ThreadPoolExecutor(max_workers=1)`, `legacy/encode_scenes.py:568`) rather than sharing the main chunk-encoding pool, keeping resource accounting explicit per concern.

## Logging

**No logging framework** — a hand-rolled `log()` function prints to stdout with an elapsed-time prefix and `flush=True` for unbuffered output suitable for piping/tailing:
```python
_START = time.monotonic()

def log(msg: str) -> None:
    """Строка лога с меткой прошедшего от старта времени (unbuffered)."""
    print(f"[{time.monotonic() - _START:8.1f}s] {msg}", flush=True)
```
(`legacy/encode_scenes.py:73-78`). Use `log()`, not bare `print()`, for any user-facing progress output in scripts of this kind.

**Step/phase logging** uses a context manager that logs start and (on success only) duration — an exception propagates without a false success marker:
```python
@contextmanager
def step(name: str):
    t0 = time.monotonic()
    log(f"▶ {name}…")
    yield
    log(f"✔ {name} — {time.monotonic() - t0:.1f}с")
```
(`legacy/encode_scenes.py:81-88`). Wrap any new multi-second synchronous operation in `step("описание")` rather than manual before/after log calls.

**Log message conventions:** `▶` prefixes "starting an operation", `✔` prefixes "operation succeeded", `>>` prefixes informational status lines, plain indentation (`"  [n/total] ..."`) for per-item progress within a batch. Follow these prefix conventions for consistency.

## Function Design

**Size:** Functions are generally single-purpose and short (10-40 lines), except deliberately dense binary-parsing helpers (the EBML/Matroska Cues reader, `legacy/encode_scenes.py:152-263`) and the `main()` orchestration functions, which are intentionally long (~100-180 lines) because they represent a linear pipeline of sequential phases with heavy inline logging — this is treated as acceptable for a top-level script driver, not something to be broken up preemptively.

**Parameters:** Config is threaded through as an explicit `config: DetectionConfig` parameter rather than read from globals in `scene_detection.py`; in `encode_scenes.py` the "config" is instead process-global constants read from env vars at import time (`ICQ`, `QPMAX`, `JOBS`, etc.) — accept this dual convention (explicit config object for the library module, env-derived globals for the CLI script) rather than unifying them, since it reflects the reusable-library vs standalone-script role split between the two files.

**Return values:** Functions that can fail without raising (parallel worker results, audio encode) return typed tuples `(idx, count, error_or_None, elapsed, info_dict)` / `(success_bool, error_or_None)` — see `encode_chunk` (`legacy/encode_scenes.py:402-417`) and `encode_audio` (`legacy/encode_scenes.py:423-478`). This "result or reason" tuple return is the standard error-carrying convention for concurrently-executed units in this codebase.

## Module Design

**Exports:** No `__all__`, no barrel/`__init__.py` files — each module is used either as a library import (`from scene_detection import detect_scenes, DetectionConfig`) or run directly via `if __name__ == "__main__":` with `argparse`. Both `legacy/*.py` files provide a CLI entry point guarded this way, in addition to being importable — keep this dual-mode design (library functions + `argparse` CLI in the same file) for new pipeline-stage scripts, matching the existing two.

**CLI argument conventions:** `argparse.ArgumentParser(description=...)` with Russian help text; positional args for required file paths (`input`/`video`, `scenes`), `-o/--output`/`--out` for output path with a sensible computed default (e.g. `<input>.scenes`, `<video>.av1.mkv`), boolean flags via `action="store_true"` (`--keep`, `--no-audio`, `--no-metrics`, `--no-qsv`). Follow these flag-naming and default-computation conventions for new pipeline-stage CLIs.

---

*Convention analysis: 2026-07-08*
