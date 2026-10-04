<!-- GSD:project-start source:PROJECT.md -->
## Project

**enpipe**

`enpipe` is a scene-aware AV1 transcode pipeline for Intel Arc (Quick Sync Video) hardware. It detects scene cuts in a source video, encodes each scene as an independently-seekable AV1 chunk via `qsvencc`, reassembles the chunks in order, and muxes the result with re-encoded/copied audio and preserved HDR10/HDR10+/Dolby Vision metadata into a final `.mkv`. It runs as a local/NAS transcoding toolchain, not a deployed service.

**Core Value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

### Constraints

- **Tech stack**: Python 3.12; external binaries `ffmpeg`/`ffprobe`, `qsvencc` (Rigaya QSVEnc), `mkvmerge` invoked via `subprocess` — no persistent daemon. Must stay compatible with existing behavior.
- **Hardware**: Intel Arc GPU (Alchemist, e.g. A380) with QSV/VA-API (`iHD` driver) and `/dev/dri` passthrough required; reference storage is a spinning-disk ZFS pool.
- **Environment**: Development and runtime happen inside the `.devcontainer/` (Docker/Podman); Ubuntu 24.04 (devcontainer: intel/dlstreamer base; runtime image: ubuntu:24.04 + Intel graphics PPA) — qsvencc .deb needs glibc ≥ 2.39; intel-opencl-icd from the PPA enables --psnr/--ssim.
- **Correctness**: Frame-count verification and keyframe-alignment invariants must be preserved through any refactor — silent output corruption is the primary risk.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12 - `src/enpipe/` (refactored package), `legacy/` (historical scripts for reference), all encoding/detection logic
- Bash/Shell - `.devcontainer/post-create.sh` (dev environment provisioning), Dockerfile RUN blocks
- Dockerfile - `Dockerfile` (production runtime image), `.devcontainer/Dockerfile` (development environment)
- JSON - `.devcontainer/devcontainer.json`, `.devcontainer/devcontainer-lock.json` (devcontainer config/lockfile)
- TOML - `pyproject.toml` (project manifest)
## Runtime
- Python 3.12 on Ubuntu 24.04 (from `ubuntu:24.04` base in `Dockerfile`)
- glibc 2.39+ (required by qsvencc .deb)
- Python 3.12 on intel/dlstreamer base (Ubuntu 24.04 with Intel media stack pre-installed, in `.devcontainer/Dockerfile`)
- Node.js LTS (installed via devcontainer feature `ghcr.io/devcontainers/features/node:2`, used only for AI CLI agents; not part of application code)
- uv (Astral) - modern, fast Python package manager and resolver (https://github.com/astral-sh/uv)
- Lockfile: `uv.lock` (present, revision 3, requires Python >= 3.12)
## Frameworks
- PySceneDetect 0.7 (with `opencv-headless` extra) - scene-cut detection via `AdaptiveDetector`, `SceneManager`; imported in `src/enpipe/detection/`
- NumPy 2.5.1 - frame buffer reshaping via `np.frombuffer` for raw BGR24 stream processing from ffmpeg
- pytest 9.1.1 - test runner with markers; test files in `tests/unit/`, `tests/subprocess/`, `tests/integration/`
- pytest-subprocess 1.6.0 - subprocess mocking via fixtures for isolating external binary calls
- pytest-mock 3.15.1 - `mocker` fixture for patching functions and objects
- ruff 0.15.20 - fast Python linter/formatter; checks `src tests` with pyflakes-only rules (F, E9xx) — no style rules (E/W) to avoid conflicts with dense binary-parsing code in `src/enpipe/mkv/ebml.py`
- uv_build (>=0.11.28, <0.12) - PEP 517 build backend for wheel building in `Dockerfile` builder stage
- Docker / Podman - container orchestration for devcontainer and slim production runtime image
- VS Code Dev Containers - devcontainer CLI support
## Key Dependencies
- scenedetect[opencv-headless] == 0.7 - PyOpenCV-based scene-cut detection engine
- numpy == 2.5.1 - numerical array operations for frame buffers
- ffmpeg / ffprobe (BtbN static n9.0.2, pinned URL+SHA256, /opt/ffmpeg-9 symlinked into /usr/local/bin in both images) - QSV-accelerated decode, audio transcode, metadata probing via `src/enpipe/shared/proc.py`
- qsvencc 8.32+vppsync7 (r4665, tag 8.32-vppsync7, sha256 297d474c…; Tualua/QSVEnc fork, GitHub releases, pinned by SHA256 in both `Dockerfile` and `.devcontainer/Dockerfile`) - Intel Arc AV1 hardware encoder; invoked with `--backend qsv --avhw` in `src/enpipe/encoding/chunk.py`
- mkvmerge (mkvtoolnix apt package) - final `.mkv` muxing via `src/enpipe/encoding/pipeline.py`
- dovi_tool (x86_64-unknown-linux-musl static binary, GitHub releases) - Dolby Vision RPU extraction; currently unused (DEBT-04, reserved for Phase 4)
- Intel Media driver (iHD, from Intel PPA `kobuk-team/intel-graphics`) - VA-API for Intel Arc A380
- oneVPL (libvpl2, libmfx-gen1.2 from Ubuntu 24.04 + Intel PPA) - GPU dispatcher and runtime
- OpenCL (intel-opencl-icd, ocl-icd-libopencl1) - qsvencc VPP metrics (--psnr/--ssim stable, measured on r4658: 0 failures from 640 sessions)
- vainfo (libva-utils) - VA-API diagnostics
## Configuration
- `ICQ` (default "23") - qsvencc quality (lower = better)
- `QPMAX` (default "100") - max quantization parameter
- `GOP_LEN` (default "300") - GOP length in frames
- `DV_PROFILE` (default "10.1") - Dolby Vision profile
- `JOBS` (default "3") - concurrent qsvencc encoding sessions in `src/enpipe/encoding/pipeline.py`
- `FLAC_LEVEL` (default "8") - FLAC compression level in `src/enpipe/encoding/audio.py`
- `AUDIO_COPY` ("0" or "1", default "0") - bypass audio re-encode flag in `src/enpipe/encoding/audio.py`
- `LIBVA_DRIVER_NAME=iHD` (set in `.devcontainer/devcontainer.json` `containerEnv` and `Dockerfile` `ENV`)
- `PATH=/opt/venv/bin:$PATH` (production `Dockerfile` only, for `enpipe` CLI entry point)
- `pyproject.toml` - project metadata, dependencies, dev groups (pytest, ruff), pytest config, ruff settings
- `uv.lock` - pinned dependency versions with hashes and source URLs
- `.devcontainer/devcontainer.json` - devcontainer spec, Node.js feature, GPU passthrough (`--device=/dev/dri`), volume mounts, `containerEnv`
- `.dockerignore` - production build context (excludes `.git`, `tests/`, `legacy/`, `.planning/`, dev files to minimize image size)
## Platform Requirements
- Docker or Podman with devcontainer CLI support
- Intel Arc GPU on host exposing `/dev/dri/renderD128` (Alchemist, e.g., A380)
- Host directories: `/data/media` (input videos), `/data/downloads` (scratch/output) as per `.devcontainer/devcontainer.json` `mounts`
- Named volumes for credential persistence: `enpipe-claude`, `enpipe-qwen`, `enpipe-opencode-data`, `enpipe-opencode-config`
- Podman rootless: `--group-add keep-groups` required for render-group membership
- Docker or Podman with `--device /dev/dri` for GPU access
- Ubuntu 24.04 (glibc 2.39+) or compatible distro with Intel PPA for intel-opencl-icd
- No dev tools, tests, or source code in final image (multi-stage build; only `src/enpipe` + `.venv` shipped)
- Local machine or NAS with Intel Arc GPU
- No cloud deployment; runs interactively or via cron as standalone pipeline
- Output: `.mkv` with AV1 video, HDR10/HDR10+/Dolby Vision metadata, audio (FLAC/Opus/copied), scene chapters
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Lowercase `snake_case` describing the pipeline stage or module concern: `config.py`, `detect.py`, `stream.py`, `chunk.py`, `audio.py`, `keyframes.py`, `hdr.py`, `scenes_io.py`, `metrics.py`, `pipeline.py`, `ebml.py`.
- Directory names match functional hierarchy: `detection/` (scene detection stage), `encoding/` (video/audio encoding and muxing stage), `mkv/` (Matroska format utilities), `cli/` (command-line interface), `shared/` (cross-stage utilities).
- Lowercase `snake_case`, verb-first: `detect_scenes()`, `probe_source()`, `encode_chunk()`, `read_scenes()`, `keyframe_table()`, `detect_hdr()`, `chunk_command()`, `encode_audio()`.
- Private/internal helpers prefixed with single underscore: `_min_scene_len()`, `_detect_relative()`, `_build_scenes()`, `_wmean()`, `_psnr_total()`, `_fmt()`, `_coverage_gap()`.
- Module-level worker functions (picklable, used with `ThreadPoolExecutor`/`ProcessPoolExecutor`) are defined at module scope, not as closures: `_boundary_worker()`, `_segment_worker()`, `encode_chunk()` (as a task tuple unpacker).
- Lowercase `snake_case`: `analysis_width`, `use_qsv`, `adaptive_threshold`, `min_scene_len_frames`, `start_frame`, `end_frame`, `streams`.
- Local loop/iteration variables use short names in tight numeric code (documented context establishes meaning): `s`, `e`, `t`, `p`, `q`, `kf_frame`, `kf_time` — see `src/enpipe/mkv/ebml.py` for binary-parsing style.
- Environment-sourced module constants use `UPPER_CASE` with typed defaults: `ICQ = int(os.environ.get("ICQ", "23"))` (`src/enpipe/encoding/chunk.py:21`), `FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")` (`src/enpipe/encoding/audio.py:16`), `JOBS = int(os.environ.get("JOBS", "3"))`.
- `PascalCase` for classes and dataclasses: `DetectionConfig`, `SourceInfo`, `Scene`, `QsvPipeStream`, `SceneDetectionError`.
- Custom exceptions subclass the most specific stdlib exception and carry a one-line Russian docstring: `class SceneDetectionError(RuntimeError): """Ошибка этапа детектирования сцен."""` (`src/enpipe/detection/config.py:16-17`).
- Module-level constants prefixed with underscore: `_NUM`, `_SSIM_RE`, `_PSNR_RE` (`src/enpipe/encoding/chunk.py:62-66`).
- Declared once per module and reused: `PathLike = Union[str, Path]` (`src/enpipe/detection/config.py:13`).
## Code Style
- No formatter enforced (no `.prettierrc`, no Black/YAPF config). Code is manually formatted: ~88-100 column soft wrap, multi-line function-call argument lists broken one-arg-group-per-line with trailing comma style, section dividers for logical organization.
- Section dividers using fixed-width comment banners delimit logical blocks within a file:
- Ruff with selection `["F", "E9"]` (pyflakes-only: unused imports, redefinition, undefined names, syntax errors) — see `pyproject.toml:[tool.ruff.lint] select`.
- Deliberately excludes E/W pycodestyle rules to allow deliberately dense binary-parsing style in `src/enpipe/mkv/ebml.py` without reformatting.
- No type checker is run in CI (type hints are documentation-grade, not enforced).
- `target-version = "py312"` in `pyproject.toml:[tool.ruff]`.
## Import Organization
- `detect.py` and `parallel.py` break a circular import by deferring `from .parallel import detect_scenes_parallel` inside the function body (line 85, `src/enpipe/detection/detect.py`). Document this with a comment: `# deferred: breaks the cycle`.
- When a local module shadows stdlib (e.g., `enpipe.shared.logging` shadows `import logging`), import as `from enpipe.shared import logging` or `from enpipe.shared.logging import die`, never bare `import logging`. This is documented in the module docstring: `src/enpipe/shared/logging.py:7-10`.
## Typing Patterns
- Use `typing` module generics (`List`, `Optional`, `Tuple`, `Union`, `Dict`), NOT Python 3.10+ built-in generics (`list[...]`, `tuple[...]`, `str | None`). This is consistent across the codebase despite targeting Python 3.12+.
- `from __future__ import annotations` is present in every module, enabling deferred evaluation of all annotations (backward compatibility, shorter syntax).
- Type hints are present throughout but never checked by a type checker (no `mypy.ini`, no `pyright` in CI). Treat them as documentation.
## Data Modeling
- Use `@dataclass(frozen=True)` for config and value types: `DetectionConfig`, `SourceInfo`, `Scene` (`src/enpipe/detection/config.py:25-70`).
- Frozen dataclasses may carry computed `@property` members: `Scene.frame_count` (`src/enpipe/detection/config.py:68-70`).
- Lightweight internal pairs/records passed between functions use plain `Tuple[int, int]` (scene boundaries) or `Tuple[int, float, bool]` (boundary candidates) rather than dataclasses — reserve dataclasses for values that cross a public function boundary.
## Error Handling
- Use `die(msg: str)` from `enpipe.shared.logging` to exit with an error message. It is the error-exit path (`src/enpipe/shared/logging.py:27-28`); the only other `SystemExit` is the quiet Ctrl-C exit `SystemExit(130)` in `src/enpipe/cli/main.py:247`.
- Example: `die(f"не найден qsvencc")` in `src/enpipe/cli/main.py:92`.
- Worker functions that run in a `ThreadPoolExecutor` MUST NOT raise exceptions or call `die()`. Instead, return `Tuple[bool, Optional[str]]` — success flag and error message.
- Example: `encode_audio()` returns `Tuple[bool, Optional[str]]` with docstring explaining: "Ошибку НЕ бросает (крутится в фоновом потоке — падать через die() нельзя)" (`src/enpipe/encoding/audio.py:21-25`).
- The consumer joins the future on the main thread and calls `die()` if an error message surfaces.
- Classes owning subprocesses or streams distinguish "abnormal stop" (`close()` — kill process forcibly, no return code check) from "normal completion" (`finish()` — wait, check return code, raise on failure).
- Streaming generators use `try/finally` to guarantee cleanup on early exit or exception from the consumer side.
## Logging
- `die(msg: str)` — prints "encode_scenes: {msg}" to stderr and exits with code 1. This prefix is preserved for byte-identity with legacy output.
- `log(msg: str)` — prints "[{elapsed:.1f}s] {msg}" to stdout unbuffered. Elapsed time is computed from `_START = time.monotonic()` captured at module import.
- `step(name: str)` — context manager: logs "▶ {name}…" on entry, logs "✔ {name} — {elapsed:.1f}с" on successful exit (exception passes through without the checkmark).
## Comments
- Comments explain *why* a non-obvious design choice is made, not *what* the code does. The code itself should be readable.
- Example: The `-copyts`/`select` seek workaround explanation in `src/enpipe/detection/stream.py:92-99`, or stderr-to-tempfile deadlock avoidance.
- Prefer inline comments at the exact line of non-obvious code rather than block comments above the function.
- All comments, docstrings, log messages, CLI help text, and error messages are in Russian. Code identifiers (function names, variable names, class names) remain in English.
- Example: Russian docstring with design rationale at the top of each module (see `src/enpipe/detection/config.py:1-4`, `src/enpipe/encoding/chunk.py:1-5`).
## Module Docstrings
- Each module starts with a substantial "why" document explaining pipeline rationale, key engineering decisions, and known limitations — not a one-liner.
- Example: `src/enpipe/detection/config.py:1-4` explains the purpose and imports of the config module.
- Example: `src/enpipe/encoding/pipeline.py:1-18` documents the orchestration strategy and refactoring decisions.
## Function Design
- Configuration is threaded through function calls as a `@dataclass(frozen=True)` config object (e.g., `DetectionConfig`) rather than individual keyword arguments. This keeps signatures compact and makes it easy to add new tunable parameters.
- Long argument lists are broken across lines with trailing commas: see `src/enpipe/detection/detect.py:72-75`.
- Functions return typed tuples or dataclass instances, not bare dicts or unwrapped values.
- Worker functions return `(success: bool, error_msg: Optional[str])` tuples; see `src/enpipe/encoding/audio.py:21-25`.
- Functions are generally 10-50 lines (brief, focused tasks). Helper functions (prefixed `_`) may be 5-15 lines and called from a single parent.
## Concurrency Patterns
- `ThreadPoolExecutor` is used for I/O/GPU-bound parallel work (encode chunks, ffprobe lookups) because the actual work happens in subprocesses, so the GIL doesn't matter.
- Module-level worker functions are defined at module scope (not closures/lambdas) because they must be picklable if used with `ProcessPoolExecutor` in the future.
- Results keyed by index in a dict, flushed to output stream only when the next expected index becomes available. This is the "high-water mark" pattern: see the `flush_appends()` closure at `src/enpipe/encoding/pipeline.py:237` and the pure helper `contiguous_run()` at `src/enpipe/encoding/pipeline.py:45`.
- Background/parallel side-work (audio encode while video chunks encode in parallel) is started via a dedicated single-worker pool (`ThreadPoolExecutor(max_workers=1)`) rather than sharing the main chunk-encoding pool. This keeps resource accounting explicit per concern.
## Subprocess Invocation
- All subprocess calls (`ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`) route through `enpipe.shared.proc.run()` or `enpipe.shared.proc.popen()`. This provides a single seam for test substitution (pytest-subprocess hooks `Popen`, which both functions use).
- Example: `src/enpipe/shared/proc.py:9-14`.
- Never call `subprocess.run()` or `subprocess.Popen()` directly in application code.
## Architecture Constraints (as conventions)
- `QsvPipeStream.is_seekable` is `False`; only `seek(0)` (full process restart) is supported. Code using this stream must not assume arbitrary seeks.
- Frame numbers (not wall-clock seconds) are the source of truth for scene boundaries. Second-based timestamps are approximate and can drift for VFR sources.
- The pipeline is entirely stateless subprocess orchestration. Every external tool invocation is a separate process with no persistent server or daemon.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| CLI dispatcher | Argparse wrapper; route `detect`/`encode`/`run` subcommands | `src/enpipe/cli/main.py` |
| Scene detection | FFprobe/ffmpeg pipe + PySceneDetect; sequential or parallel split-and-merge | `src/enpipe/detection/detect.py`, `src/enpipe/detection/parallel.py` |
| QSV video stream | Custom `VideoStream` adapter: ffmpeg subprocess (QSV decode + GPU downscale, raw BGR24 pipe) | `src/enpipe/detection/stream.py` |
| Keyframe table builder | EBML/Cues index parser (fast mkv path) + ffprobe fallback; binary search for nearest keyframe | `src/enpipe/encoding/keyframes.py`, `src/enpipe/mkv/ebml.py` |
| Chunk command builder | Assemble qsvencc CLI command (seek/trim/HDR flags/metrics) | `src/enpipe/encoding/chunk.py:chunk_command` |
| Chunk encoder | Subprocess orchestration, frame-count verification, PSNR/SSIM parsing | `src/enpipe/encoding/chunk.py:encode_chunk` |
| Parallel chunk orchestration | `ThreadPoolExecutor` job submission, high-water-mark ordered append (`flush_appends`), per-scene frame-count validation | `src/enpipe/encoding/pipeline.py:run_encode` (lines 220–287) |
| Audio encoder | Parallel background thread: encode/copy audio via ffmpeg preset rules | `src/enpipe/encoding/audio.py` |
| CSV metrics writer | Per-scene + frame-weighted-total SSIM/PSNR/bitrate table | `src/enpipe/encoding/metrics.py` |
| Pipeline orchestrator | Sequential `detect_scenes` → `run_encode` (no overlap; designed for fast-path skip if output exists) | `src/enpipe/cli/main.py:run_pipeline` |
| Scene log I/O | Text format parsing: `scene NNNN frames [S, E) T0 .. T1` | `src/enpipe/encoding/scenes_io.py` |
| HDR/DV detection | Ffprobe side-data inspection → qsvencc flag list (`--dolby-vision-rpu`, `--masteringdisplaydata`, etc.) | `src/enpipe/encoding/hdr.py` |
## Pattern Overview
- **No persistent daemon** — every subprocess (ffmpeg, ffprobe, qsvencc, mkvmerge) is invoked via `subprocess.run` and awaited immediately or collected in a thread pool.
- **GPU-centric** — Intel Arc QSV used for decode (with GPU downscale for detector) and AV1 encode; Python-side CPU work deliberately minimized.
- **Scene-boundary-aware chunking** — each scene becomes an independently seekable AV1 chunk, keyed to source keyframes; chunks concatenate bit-exactly via raw `.obu` file append.
- **Strict frame-count parity** — at encode start (per-chunk), after concatenation (full `movie.obu`), and before mux, frame counts are verified against expected values; any mismatch is fatal.
- **High-water-mark ordered append** — parallel chunk encodes finish out-of-order; results are buffered in a `ready: Dict[int, int]` map keyed by scene index, flushed to the output stream only when all earlier scenes are complete. This pattern is reused by both the current batch encoder and the (unimplemented) planned streaming orchestrator.
## Layers
- Purpose: Convert source video into an ordered list of `Scene(index, start_frame, end_frame, start_sec, end_sec)` records.
- Location: `src/enpipe/detection/`
- Contains: ffprobe wrapper (`probe_source`), custom `VideoStream` subclass (`QsvPipeStream`) wrapping an ffmpeg subprocess pipe, PySceneDetect `AdaptiveDetector` integration, sequential (`detect_scenes`) and parallel (`detect_scenes_parallel`) entry points, CLI orchestration (`run_detect`).
- Depends on: `ffmpeg`/`ffprobe` binaries, PySceneDetect 0.7 package, numpy.
- Used by: `src/enpipe/encoding/pipeline.py` indirectly via the `<video>.scenes` text file; `src/enpipe/cli/main.py` orchestration path.
- Purpose: Turn a video + scene list into a final muxed AV1 `.mkv` with re-encoded/copied audio and preserved HDR/DV metadata.
- Location: `src/enpipe/encoding/`
- Contains: scene-log parser, keyframe-table builder (EBML fast-path + ffprobe fallback), HDR/DV detection, per-scene chunk command builder, threaded chunk-encode with ordered-append orchestration, parallel audio encode, CSV metrics writer, final mux via mkvmerge, CLI orchestration (`run_encode`).
- Depends on: `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` binaries; the `<video>.scenes` text file format produced by the detection layer.
- Used by: nothing else in-repo; it is the terminal stage.
- Purpose: Hand-rolled, pure (no I/O) binary parser for EBML/Matroska structure navigation and Cues (keyframe index) extraction.
- Location: `src/enpipe/mkv/ebml.py`
- Contains: EBML variable-length integer parsing (`_ebml_num`, `_eid`, `_esz`), SeekHead traversal, Info (TimestampScale) extraction, Tracks (video track number) extraction, Cues body parsing.
- Depends on: none (pure bytes-in, tuples-out).
- Used by: `src/enpipe/encoding/keyframes.py` (thin I/O wrapper).
- Purpose: Leaf modules with no inter-package dependencies (keep layers acyclic): logging/die, subprocess wrapper, batch processing, qsvencc version checking.
- Location: `src/enpipe/shared/`
- Contains: `logging.py` (elapsed-time-prefixed log, step context manager, die/exit), `proc.py` (subprocess.run wrapper), `batch.py` (batch file iteration and error handling), `qsvencc_version.py` (runtime check for fixed qsvencc: `QSVENCC_MIN_REV = 4634`; `QSVENCC_METRICS_MIN_REV = 4658` gates the metrics path in the COR-02 lock and hardware tier).
- Depends on: none.
- Used by: all layers.
## Data Flow
### Primary Path: `enpipe run <video>`
### Parallel Detection Path: `detect_scenes_parallel()`
- Divide timeline into `jobs` segments at uniform time/frame points
- For each segment, `find_boundary()`: probe for nearest real scene cut via quick ffprobe window scan + short AdaptiveDetector run
- Collect boundaries; sanitize (sort, dedupe, clamp to [0, total_frames])
- For each segment `[start_frame, end_frame)`, spawn `_segment_worker()`:
- Collect all relative results
- Merge results: sort, dedupe adjacent boundaries, rebuild `List[Scene]`
## Key Abstractions
### `Scene` (Immutable Value Object)
```python
```
### `DetectionConfig` (Immutable Config Object)
### `QsvPipeStream` (Adapter Pattern)
### Keyframe Table (`List[Tuple[int, float]]`)
### High-Water-Mark Ordered Append (`flush_appends()`)
### HDR/DV Metadata Preservation
## Entry Points
- Location: `src/enpipe/cli/main.py:run_detect`
- Triggers: Manual CLI invocation (or `enpipe run` internal call).
- Responsibilities: Parse detect-specific CLI args, build `DetectionConfig`, call `detect_scenes()`, format and write `<video>.scenes`.
- Location: `src/enpipe/encoding/pipeline.py:run_encode` (line 107)
- Triggers: Manual CLI invocation (or `enpipe run` internal call).
- Responsibilities: Full encode pipeline (described in Data Flow above); tool-availability preflight; qsvencc version check (fail-fast gate).
- Location: `src/enpipe/cli/main.py:run_pipeline` (line 77)
- Triggers: Manual CLI invocation; meant for one-shot end-to-end usage.
- Responsibilities: which-preflight, qsvencc version check, orchestrate sequential `detect_scenes` → `run_encode` for single file or batch directory recursion.
## Architectural Constraints
- **Threading model**: Both detection and encoding use `ThreadPoolExecutor` for concurrency, not multiprocessing. For encoding, this is safe because GPU/qsvencc work dominates; the GIL is not a bottleneck. For parallel detection, `ThreadPoolExecutor` was kept deliberately after measurement (DEBT-03, `scratch/profiling_debt03.py`; rationale in the comment at `src/enpipe/detection/parallel.py:99-110`) — the old "needs processes to bypass the GIL" claim was removed as contradicted by the numbers. Workers are kept at module scope (not closures) to prepare for future ProcessPoolExecutor migration.
- **Global mutable state**: `_START = time.monotonic()` at module import in `src/enpipe/shared/logging.py:31`. Used by `log()` for elapsed-time prefixes. No other module-level mutable singletons.
- **Non-seekable video stream**: `QsvPipeStream.is_seekable = False`; only `seek(0)` (full process restart) is supported. Segment-mode seeking (`seek_sec`/`to_sec`) is simulated via ffmpeg `-ss` / `-to` flags passed to the subprocess, not via the VideoStream interface.
- **Frame number is the primary time coordinate**: For VFR sources, second-based timestamps (`frame / avg_fps`) are explicitly approximate and can drift from real PTS. Frame numbers are the source of truth for scene boundaries and carried unchanged through to the encoder. Encoded chunk frame counts are validated against expected values (derived from scene frame ranges).
- **Stderr-to-tempfile, not PIPE**: `QsvPipeStream` writes ffmpeg stderr to `SpooledTemporaryFile` rather than `subprocess.PIPE`, specifically to avoid a documented deadlock risk: ffmpeg's chatty stderr can fill the 64KB pipe buffer while the consumer blocks on stdout waiting for frame data (pipe deadlock). This is a known correctness workaround preserved from legacy code.
- **Hardware coupling**: The entire toolchain assumes Intel Arc GPU with QSV/VA-API support (iHD driver). `--no-qsv` software-decode fallback exists for debugging but only covers the detection stage. No fallback AV1 encoder exists; `qsvencc` is a hard external-tool dependency (attempted qsvencc absence is caught by preflight check before any long-running work).
- **Cyclic import prevention**: `detect_scenes` and `detect_scenes_parallel` import each other (deferred inside function bodies), broken by a deferred `from .parallel import detect_scenes_parallel` inside `detect_scenes` (`src/enpipe/detection/detect.py:85`). `encoding/keyframes.py` → `mkv/ebml.py` is a plain one-way import (ebml is pure, imports nothing from enpipe).
## Anti-Patterns
### Hand-rolled Binary Format Parsing Embedded in Production Code
### Silent Frame-Count Mismatches Due to Seek/Trim Math
## Error Handling
- **Preflight**: `shutil.which()` loop checks qsvencc/ffprobe/ffmpeg/mkvmerge before any real work (`src/enpipe/encoding/pipeline.py:108`). `ensure_qsvencc_fixed()` verifies qsvencc version ≥ r4665 (includes upstream fix 45003f1 for cross-session frame corruption the `--seek` fix and the open-GOP `--trim` fix); the pinned build is the Tualua fork 8.32+vppsync7 (r4665).
- **Background thread errors**: `encode_audio()` returns `(bool, Optional[str])` (success, error message) instead of raising, because it runs in a background thread. The main thread calls `.result()` on the future and checks the error tuple, then calls `die()` if needed—keeping error handling on the main thread.
- **Batch-vs-immediate failure**: In parallel chunk encoding, all in-flight futures complete even if one fails. Errors are collected in an `errors` list, capped at 10, and reported once before calling `die()` (drain-then-die). This gives users visibility into all failures, not just the first one.
- **Cleanup on error**: `try/finally` blocks in `QsvPipeStream` ensure `close()` (force-kill subprocess) is always called on early exit or exception.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
