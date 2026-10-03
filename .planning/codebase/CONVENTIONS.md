# Coding Conventions

**Analysis Date:** 2026-10-03

## Naming Patterns

**Files:**
- Lowercase `snake_case` describing the pipeline stage or module concern: `config.py`, `detect.py`, `stream.py`, `chunk.py`, `audio.py`, `keyframes.py`, `hdr.py`, `scenes_io.py`, `metrics.py`, `pipeline.py`, `ebml.py`.
- Directory names match functional hierarchy: `detection/` (scene detection stage), `encoding/` (video/audio encoding and muxing stage), `mkv/` (Matroska format utilities), `cli/` (command-line interface), `shared/` (cross-stage utilities).

**Functions:**
- Lowercase `snake_case`, verb-first: `detect_scenes()`, `probe_source()`, `encode_chunk()`, `read_scenes()`, `keyframe_table()`, `detect_hdr()`, `chunk_command()`, `encode_audio()`.
- Private/internal helpers prefixed with single underscore: `_min_scene_len()`, `_detect_relative()`, `_build_scenes()`, `_wmean()`, `_psnr_total()`, `_fmt()`, `_coverage_gap()`.
- Module-level worker functions (picklable, used with `ThreadPoolExecutor`/`ProcessPoolExecutor`) are defined at module scope, not as closures: `_boundary_worker()`, `_segment_worker()`, `encode_chunk()` (as a task tuple unpacker).

**Variables:**
- Lowercase `snake_case`: `analysis_width`, `use_qsv`, `adaptive_threshold`, `min_scene_len_frames`, `start_frame`, `end_frame`, `streams`.
- Local loop/iteration variables use short names in tight numeric code (documented context establishes meaning): `s`, `e`, `t`, `p`, `q`, `kf_frame`, `kf_time` — see `src/enpipe/mkv/ebml.py` for binary-parsing style.
- Environment-sourced module constants use `UPPER_CASE` with typed defaults: `ICQ = int(os.environ.get("ICQ", "23"))` (`src/enpipe/encoding/chunk.py:21`), `FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")` (`src/enpipe/encoding/audio.py:16`), `JOBS = int(os.environ.get("JOBS", "3"))`.

**Types & Classes:**
- `PascalCase` for classes and dataclasses: `DetectionConfig`, `SourceInfo`, `Scene`, `QsvPipeStream`, `SceneDetectionError`.
- Custom exceptions subclass the most specific stdlib exception and carry a one-line Russian docstring: `class SceneDetectionError(RuntimeError): """Ошибка этапа детектирования сцен."""` (`src/enpipe/detection/config.py:16-17`).

**Regular expressions and compiled patterns:**
- Module-level constants prefixed with underscore: `_NUM`, `_SSIM_RE`, `_PSNR_RE` (`src/enpipe/encoding/chunk.py:62-66`).

**Type aliases:**
- Declared once per module and reused: `PathLike = Union[str, Path]` (`src/enpipe/detection/config.py:13`).

## Code Style

**Formatting:**
- No formatter enforced (no `.prettierrc`, no Black/YAPF config). Code is manually formatted: ~88-100 column soft wrap, multi-line function-call argument lists broken one-arg-group-per-line with trailing comma style, section dividers for logical organization.
- Section dividers using fixed-width comment banners delimit logical blocks within a file:
  ```python
  # --------------------------------------------------------------------------- #
  # Конфигурация и модели данных
  # --------------------------------------------------------------------------- #
  ```
  or
  ```python
  # --- батч-ветка: args.input — директория (QUICK-260709-89t) --- #
  ```
  Preserve this convention when organizing new code.

**Linting:**
- Ruff with selection `["F", "E9"]` (pyflakes-only: unused imports, redefinition, undefined names, syntax errors) — see `pyproject.toml:[tool.ruff.lint] select`.
- Deliberately excludes E/W pycodestyle rules to allow deliberately dense binary-parsing style in `src/enpipe/mkv/ebml.py` without reformatting.
- No type checker is run in CI (type hints are documentation-grade, not enforced).
- `target-version = "py312"` in `pyproject.toml:[tool.ruff]`.

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, Python 3.7+ PEP 563 deferred annotations)
2. Standard library imports: `import json`, `import os`, `import sys`, `import time`, `from pathlib import Path`, `from typing import List, Optional, Tuple`, `from concurrent.futures import ThreadPoolExecutor`, etc.
3. Third-party imports: `from scenedetect import SceneManager`, `from scenedetect.detectors import AdaptiveDetector`, `import numpy as np`.
4. Local/relative imports: `from enpipe.shared import proc as _proc`, `from .config import DetectionConfig`, `from enpipe.detection.config import Scene`.

**Special case — Deferred import for cycle breaking:**
- `detect.py` and `parallel.py` break a circular import by deferring `from .parallel import detect_scenes_parallel` inside the function body (line 85, `src/enpipe/detection/detect.py`). Document this with a comment: `# deferred: breaks the cycle`.

**Qualified imports for same-named stdlib modules:**
- When a local module shadows stdlib (e.g., `enpipe.shared.logging` shadows `import logging`), import as `from enpipe.shared import logging` or `from enpipe.shared.logging import die`, never bare `import logging`. This is documented in the module docstring: `src/enpipe/shared/logging.py:7-10`.

## Typing Patterns

**Typing style:**
- Use `typing` module generics (`List`, `Optional`, `Tuple`, `Union`, `Dict`), NOT Python 3.10+ built-in generics (`list[...]`, `tuple[...]`, `str | None`). This is consistent across the codebase despite targeting Python 3.12+.
- `from __future__ import annotations` is present in every module, enabling deferred evaluation of all annotations (backward compatibility, shorter syntax).
- Type hints are present throughout but never checked by a type checker (no `mypy.ini`, no `pyright` in CI). Treat them as documentation.

**Examples:**
```python
from typing import List, Optional, Tuple, Union, Dict

def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    ...

def detect_scenes(
    path: PathLike, config: DetectionConfig = DetectionConfig(), jobs: int = 1,
    show_progress: bool = False,
) -> List[Scene]:
    ...

streams: List[dict] = json.loads(...)
```

## Data Modeling

**Immutable value objects:**
- Use `@dataclass(frozen=True)` for config and value types: `DetectionConfig`, `SourceInfo`, `Scene` (`src/enpipe/detection/config.py:25-70`).
- Frozen dataclasses may carry computed `@property` members: `Scene.frame_count` (`src/enpipe/detection/config.py:68-70`).

**Plain tuples for internal plumbing:**
- Lightweight internal pairs/records passed between functions use plain `Tuple[int, int]` (scene boundaries) or `Tuple[int, float, bool]` (boundary candidates) rather than dataclasses — reserve dataclasses for values that cross a public function boundary.

## Error Handling

**Fatal errors on main thread:**
- Use `die(msg: str)` from `enpipe.shared.logging` to exit with an error message. It is the error-exit path (`src/enpipe/shared/logging.py:27-28`); the only other `SystemExit` is the quiet Ctrl-C exit `SystemExit(130)` in `src/enpipe/cli/main.py:247`.
- Example: `die(f"не найден qsvencc")` in `src/enpipe/cli/main.py:92`.

**Background/worker thread errors:**
- Worker functions that run in a `ThreadPoolExecutor` MUST NOT raise exceptions or call `die()`. Instead, return `Tuple[bool, Optional[str]]` — success flag and error message.
- Example: `encode_audio()` returns `Tuple[bool, Optional[str]]` with docstring explaining: "Ошибку НЕ бросает (крутится в фоновом потоке — падать через die() нельзя)" (`src/enpipe/encoding/audio.py:21-25`).
- The consumer joins the future on the main thread and calls `die()` if an error message surfaces.

**Resource cleanup:**
- Classes owning subprocesses or streams distinguish "abnormal stop" (`close()` — kill process forcibly, no return code check) from "normal completion" (`finish()` — wait, check return code, raise on failure).
- Streaming generators use `try/finally` to guarantee cleanup on early exit or exception from the consumer side.

## Logging

**Framework:** `enpipe.shared.logging` (not stdlib `logging`)

**Functions:**
- `die(msg: str)` — prints "encode_scenes: {msg}" to stderr and exits with code 1. This prefix is preserved for byte-identity with legacy output.
- `log(msg: str)` — prints "[{elapsed:.1f}s] {msg}" to stdout unbuffered. Elapsed time is computed from `_START = time.monotonic()` captured at module import.
- `step(name: str)` — context manager: logs "▶ {name}…" on entry, logs "✔ {name} — {elapsed:.1f}с" on successful exit (exception passes through without the checkmark).

**Examples:**
```python
from enpipe.shared.logging import die, log, step

log("Starting encode pipeline")
with step("detecting scenes"):
    scenes = detect_scenes(path)
die("ffmpeg not found")
```

## Comments

**Why over what:**
- Comments explain *why* a non-obvious design choice is made, not *what* the code does. The code itself should be readable.
- Example: The `-copyts`/`select` seek workaround explanation in `src/enpipe/detection/stream.py:92-99`, or stderr-to-tempfile deadlock avoidance.
- Prefer inline comments at the exact line of non-obvious code rather than block comments above the function.

**Documentation language:**
- All comments, docstrings, log messages, CLI help text, and error messages are in Russian. Code identifiers (function names, variable names, class names) remain in English.
- Example: Russian docstring with design rationale at the top of each module (see `src/enpipe/detection/config.py:1-4`, `src/enpipe/encoding/chunk.py:1-5`).

## Module Docstrings

- Each module starts with a substantial "why" document explaining pipeline rationale, key engineering decisions, and known limitations — not a one-liner.
- Example: `src/enpipe/detection/config.py:1-4` explains the purpose and imports of the config module.
- Example: `src/enpipe/encoding/pipeline.py:1-18` documents the orchestration strategy and refactoring decisions.

## Function Design

**Parameters:**
- Configuration is threaded through function calls as a `@dataclass(frozen=True)` config object (e.g., `DetectionConfig`) rather than individual keyword arguments. This keeps signatures compact and makes it easy to add new tunable parameters.
- Long argument lists are broken across lines with trailing commas: see `src/enpipe/detection/detect.py:72-75`.

**Return values:**
- Functions return typed tuples or dataclass instances, not bare dicts or unwrapped values.
- Worker functions return `(success: bool, error_msg: Optional[str])` tuples; see `src/enpipe/encoding/audio.py:21-25`.

**Size guideline:**
- Functions are generally 10-50 lines (brief, focused tasks). Helper functions (prefixed `_`) may be 5-15 lines and called from a single parent.

## Concurrency Patterns

**Executor type:**
- `ThreadPoolExecutor` is used for I/O/GPU-bound parallel work (encode chunks, ffprobe lookups) because the actual work happens in subprocesses, so the GIL doesn't matter.
- Module-level worker functions are defined at module scope (not closures/lambdas) because they must be picklable if used with `ProcessPoolExecutor` in the future.

**Ordered output from unordered completion:**
- Results keyed by index in a dict, flushed to output stream only when the next expected index becomes available. This is the "high-water mark" pattern: see the `flush_appends()` closure at `src/enpipe/encoding/pipeline.py:237` and the pure helper `contiguous_run()` at `src/enpipe/encoding/pipeline.py:45`.

**Parallel side-work:**
- Background/parallel side-work (audio encode while video chunks encode in parallel) is started via a dedicated single-worker pool (`ThreadPoolExecutor(max_workers=1)`) rather than sharing the main chunk-encoding pool. This keeps resource accounting explicit per concern.

## Subprocess Invocation

**Single point of substitution:**
- All subprocess calls (`ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`) route through `enpipe.shared.proc.run()` or `enpipe.shared.proc.popen()`. This provides a single seam for test substitution (pytest-subprocess hooks `Popen`, which both functions use).
- Example: `src/enpipe/shared/proc.py:9-14`.
- Never call `subprocess.run()` or `subprocess.Popen()` directly in application code.

## Architecture Constraints (as conventions)

**Non-seekable video stream:**
- `QsvPipeStream.is_seekable` is `False`; only `seek(0)` (full process restart) is supported. Code using this stream must not assume arbitrary seeks.

**Frame-number primary time coordinate:**
- Frame numbers (not wall-clock seconds) are the source of truth for scene boundaries. Second-based timestamps are approximate and can drift for VFR sources.

**No persistent daemon:**
- The pipeline is entirely stateless subprocess orchestration. Every external tool invocation is a separate process with no persistent server or daemon.

---

*Conventions analysis: 2026-10-03*
