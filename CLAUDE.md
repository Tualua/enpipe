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

## Project Status Note
- `legacy/scene_detection.py`, `legacy/encode_scenes.py` — a working (per
- `PIPELINE_DESIGN.md` — a Russian-language design document proposing a
- `.devcontainer/` — a fully specified Docker-based dev environment for the
## Languages
- Python 3.12 - `legacy/scene_detection.py`, `legacy/encode_scenes.py` (base image `mcr.microsoft.com/devcontainers/python:3-3.12-trixie`, pinned in `.devcontainer/Dockerfile`)
- Bash - `.devcontainer/post-create.sh` (devcontainer provisioning/self-check script)
- Dockerfile - `.devcontainer/Dockerfile` (image build recipe)
- JSON - `.devcontainer/devcontainer.json`, `.devcontainer/devcontainer-lock.json` (devcontainer config/lockfile)
- Markdown (Russian) - `PIPELINE_DESIGN.md` (design/decision doc, not code)
## Runtime
- Python 3.12 on Debian 13 "trixie" (chosen specifically because prebuilt `qsvencc` .deb requires glibc ≥2.39, unavailable on Debian 12 "bookworm" — see `.devcontainer/Dockerfile` comments)
- Runs inside a VS Code / Claude Code **devcontainer** (Docker or Podman); GPU access requires `/dev/dri` passthrough (Intel Arc A380 "Alchemist")
- Node.js LTS - installed via devcontainer feature `ghcr.io/devcontainers/features/node:2` (used only to host npm-installed AI CLI agents, not for application code)
- **Python:** plain `pip` (no venv — base image's Python is not "externally managed"), invoked directly in `.devcontainer/post-create.sh`:
- **Node:** `npm` (global installs only, no `package.json` in repo): `npm install -g opencode-ai @qwen-code/qwen-code`
- **System packages:** `apt-get` inside `.devcontainer/Dockerfile` (Debian trixie, non-free/contrib enabled for `intel-media-va-driver-non-free`)
- Lockfile: present only for devcontainer features (`.devcontainer/devcontainer-lock.json`, pins `claude-code` feature 1.0.5 and `node` feature 2.1.0 by digest). No lockfile for Python or npm dependencies.
## Frameworks
- None (no web framework, no application framework). The codebase is a pair of standalone CLI scripts orchestrating external binaries via `subprocess`.
- `scenedetect` (PySceneDetect) 0.7.x - `legacy/scene_detection.py` - scene-cut detection library (`SceneManager`, `AdaptiveDetector`, `VideoStream` custom backend). Version constraint noted only in a docstring ("Проверено против PySceneDetect 0.7") — not pinned in any manifest.
- `numpy` - `legacy/scene_detection.py` - frame buffer handling (`np.frombuffer` on raw BGR24 pipe output)
- None detected. No test framework, no test files, no CI config (`.github/` absent, no `*.yml`/`*.yaml` workflow files anywhere in the repo).
- Docker/Podman (devcontainer build) - `.devcontainer/Dockerfile`
- VS Code Dev Containers - `.devcontainer/devcontainer.json`
- Claude Code CLI (+ GSD plugin) - installed via devcontainer feature and `claude plugin install gsd@gsd-plugin` in `post-create.sh`; used for AI-assisted development, not part of the runtime pipeline
- opencode / qwen-code - additional AI CLI agents installed globally via npm in `post-create.sh`, dev-tooling only
## Key Dependencies
- `scenedetect[opencv-headless]` (PySceneDetect) - unpinned - core scene-boundary detection engine
- `numpy` - unpinned - raw frame buffer reshaping from ffmpeg pipe output
- `qsvencc` (Rigaya QSVEnc) - latest GitHub release .deb, installed in `.devcontainer/Dockerfile` with dependency patching (strips `intel-opencl-icd`/`libmfx1` deps not available on Debian trixie) - AV1 hardware encoder driving Intel Arc QSV; invoked via `subprocess` in `legacy/encode_scenes.py::chunk_command`
- `ffmpeg` / `ffprobe` (Debian trixie apt package) - QSV-accelerated decode/downscale pipe for scene detection (`legacy/scene_detection.py::QsvPipeStream`), audio transcode (`legacy/encode_scenes.py::encode_audio`), and metadata probing throughout
- `mkvmerge` (mkvtoolnix, apt) - final muxing of encoded video/audio/subs/chapters (`legacy/encode_scenes.py::main`)
- `intel-media-va-driver-non-free` (iHD driver), `libva2`/`libva-drm2`/`vainfo`, `libvpl2` (oneVPL dispatcher), `libmfx-gen1.2`/`libmfxgen1`/`libmfx-gen1` (oneVPL GPU runtime, package name varies by distro release — Dockerfile tries all three), `ocl-icd-libopencl1` (OpenCL loader, required by qsvencc for VPP filters Intel's OpenCL ICD (intel-opencl-icd) comes from the kobuk-team PPA; qsvencc metrics work but are flaky under concurrency (VIDEOMETRIC, Phase 8 D-12)) - all installed in `.devcontainer/Dockerfile`
- `dovi_tool` (quietvoid, static musl binary from GitHub releases) - installed in `.devcontainer/Dockerfile` but **not referenced anywhere in `legacy/*.py`** — Dolby Vision RPU handling is done per-chunk by `qsvencc --dolby-vision-rpu copy` instead, making this dependency currently unused/vestigial in the existing code
- `tmux` - apt package, interactive session persistence tool, not invoked by any script
## Configuration
- No `.env` file support; configuration is via **plain OS environment variables read directly with `os.environ.get`** in `legacy/encode_scenes.py`:
- `legacy/scene_detection.py` config is via a frozen dataclass `DetectionConfig` (analysis width, QSV on/off, detector thresholds, ffmpeg/ffprobe binary paths) constructed programmatically or via CLI flags — no env-var or file-based config for this stage.
- `LIBVA_DRIVER_NAME=iHD` set as `containerEnv` in `.devcontainer/devcontainer.json` (selects Intel Media driver for VA-API)
- `.gitignore` explicitly excludes `.env`, `.envrc`, `.venv`/`venv/`/`env/` — standard Python secret/venv hygiene, though no such files currently exist in the repo.
- `.devcontainer/Dockerfile` - full image build (Python base + Intel media stack + qsvencc + dovi_tool)
- `.devcontainer/devcontainer.json` - devcontainer features, GPU device passthrough (`--device=/dev/dri:/dev/dri`), host media directory bind mounts, `postCreateCommand`
- `.devcontainer/post-create.sh` - post-build provisioning: GPU render-group permissions, npm AI-CLI installs, Claude Code GSD plugin install, Python pip installs, environment self-check (`vainfo`, ffmpeg QSV encoder list, `qsvencc --version`, etc.)
- No `tsconfig.json`, `eslintrc`, `pyproject.toml`, `setup.py`, or similar build/lint config exists at the repo root.
## Platform Requirements
- Docker or Podman with devcontainer support (VS Code Dev Containers extension or `devcontainer` CLI)
- Host machine with an Intel Arc GPU exposing `/dev/dri/renderD128` (Alchemist architecture, e.g. Arc A380) for QSV/VA-API hardware decode+encode
- Host bind-mount paths expected at `/data/media` and `/data/downloads` (hardcoded in `.devcontainer/devcontainer.json` `mounts`)
- Podman-specific build fix present in Dockerfile (disables apt sandboxing, fixes `/tmp` permissions, needed because devcontainer features run apt-get as a non-root user that fails under Podman's build environment)
- No deployment target defined — this is a local/NAS transcoding toolchain run interactively or via cron/manual invocation, not a deployed service. `PIPELINE_DESIGN.md` refers to running on a "NAS" with a "spindle ZFS" disk array and Intel Arc A380.
## Planned / Not Implemented (per `PIPELINE_DESIGN.md`)
- **In-process streaming orchestrator**: Python `threading` + `queue.Queue(maxsize=8)` bridging a producer thread (`detect_scenes_streaming()`, new function planned for `legacy/scene_detection.py`) and a consumer (refactored `main()` in `legacy/encode_scenes.py`, lines 542-645) to overlap scene detection and encoding via backpressure.
- No new external dependency would be introduced — same `scenedetect`, `ffmpeg`, `qsvencc` stack, just restructured control flow (`ThreadPoolExecutor` usage expands, ordered "high-water mark" flush logic generalized).
- Explicit regression-test requirement documented but not written: `list(detect_scenes_streaming(f)) == detect_scenes(f, jobs=1)`.
- **Decision:** implementation is gated on migrating source storage to SSD/NVMe (or a separate need for an orchestrator); not to be built on the current spinning-disk ZFS array.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Language & Runtime
- **Python 3.12** (per `.devcontainer/Dockerfile`, `mcr.microsoft.com/devcontainers/python:3-3.12-trixie`).
- Every module starts with `from __future__ import annotations` (`legacy/scene_detection.py:33`, `legacy/encode_scenes.py:33`).
- Type hints use the `typing` module generics (`List`, `Optional`, `Tuple`, `Union`, `Dict`) rather than the bare `list[...]`/`tuple[...]` syntax available in 3.9+, despite targeting 3.12 — follow this existing style for consistency rather than switching to built-in generics mid-file.
- No `pyproject.toml`, `setup.py`, or `requirements.txt` exists. Dependencies (`scenedetect[opencv-headless]`, `numpy`) are installed ad hoc via `pip install` in `.devcontainer/post-create.sh:34`. There is no dependency pinning/lockfile — if you add dependencies, prefer creating a `pyproject.toml` rather than continuing the implicit-install pattern.
## Documentation Language
- **All comments, docstrings, log messages, CLI help text, and error messages are written in Russian.** This is consistent across both `legacy/` files and `PIPELINE_DESIGN.md`. Maintain Russian for in-code prose when extending these files; code identifiers (function/variable/class names) are in English.
- Module docstrings are substantial "why" documents, not just summaries — see the top of `legacy/scene_detection.py:1-31` and `legacy/encode_scenes.py:1-32`, which explain pipeline rationale, key engineering decisions, and known limitations before any code. Follow this pattern for new modules: a design-rationale docstring, not a one-liner.
## Naming Patterns
- Lowercase snake_case module names describing the pipeline stage: `scene_detection.py`, `encode_scenes.py`.
- `snake_case`, verb-first for actions (`detect_scenes`, `probe_source`, `encode_chunk`, `read_scenes`, `keyframe_table_cues`).
- Private/internal helpers prefixed with a single underscore: `_detect_relative`, `_build_scenes`, `_min_scene_len`, `_boundary_worker`, `_segment_worker`, `_ebml_num`, `_eid`, `_esz` (`legacy/scene_detection.py`), `_SCENE_RE`, `_SSIM_RE`, `_PSNR_RE` (`legacy/encode_scenes.py`).
- Multiprocessing/thread worker functions used with `ProcessPoolExecutor`/`ThreadPoolExecutor` are defined at module level (not as closures/lambdas) because closures don't pickle — see the comment at `legacy/scene_detection.py:567-569`.
- `snake_case` throughout. Short, local, math/stream-oriented names are acceptable in tight numeric code (`s`, `e`, `t`, `p`, `q`, `kf_frame`, `kf_time`) as long as the enclosing function/docstring establishes context — this is a deliberate density trade-off in hot-path binary-parsing code (`legacy/encode_scenes.py:130-263`, the Matroska/EBML Cues parser).
- `PascalCase` for classes and dataclasses: `DetectionConfig`, `SourceInfo`, `Scene`, `QsvPipeStream`, `SceneDetectionError`.
- Custom exceptions subclass the most specific stdlib exception that fits and get a one-line Russian docstring: `class SceneDetectionError(RuntimeError): """Ошибка этапа детектирования сцен (ffprobe/ffmpeg/пайп)."""` (`legacy/scene_detection.py:53-54`).
- Module-level `UPPER_CASE`, frequently sourced from environment variables with a typed cast and default, e.g. `ICQ = int(os.environ.get("ICQ", "23"))` (`legacy/encode_scenes.py:52-57`). This is the established pattern for making CLI/pipeline scripts tunable without argparse plumbing for every knob — reuse it for new global encode/detect parameters instead of adding new argparse flags for every tunable.
- `PathLike = Union[str, Path]` declared once near the top of a module and reused in signatures (`legacy/scene_detection.py:50`).
## Data Modeling
- Immutable value objects use `@dataclass(frozen=True)`: `DetectionConfig`, `SourceInfo`, `Scene` (`legacy/scene_detection.py:62-107`). Use frozen dataclasses for any new config/value objects — the codebase has no precedent for mutable config objects.
- Dataclasses may carry computed `@property` members alongside stored fields, e.g. `Scene.frame_count` (`legacy/scene_detection.py:105-107`).
- Plain tuples are used freely for lightweight internal pairs/records passed between functions (e.g. `Tuple[int, int]` scene boundaries, `Tuple[int, float, bool]` boundary candidates) rather than introducing a dataclass for every internal shape — reserve dataclasses for values that cross a public function boundary or get documented; use tuples for purely internal producer/consumer plumbing.
## Code Style
- No formatter config present (no `.prettierrc`, no `black`/`ruff` config file). Existing code is manually formatted but consistent: ~88-100 col soft wrap, multi-line function-call argument lists broken one-arg-group-per-line with trailing comma style, comments aligned with `# --- section --- #` banner dividers to delimit logical sections within a file (see banners throughout `legacy/encode_scenes.py`, e.g. lines 48-51, 70-73, 91-93, 329-331, 351-353, 420-422, 512-514).
- No linter config present (no `.flake8`, `ruff.toml`, `mypy.ini`). Type hints are used throughout but never checked by a type checker in CI (there is no CI). Treat type hints as documentation-grade, not enforced.
- Both `legacy/*.py` files divide their body into named sections with a fixed-width comment banner:
- Comments consistently explain *why*, not *what* — e.g. the `-copyts`/`select` seek workaround (`legacy/scene_detection.py:225-251`), the stderr-to-tempfile-not-PIPE deadlock avoidance (`legacy/scene_detection.py:210-214`), the `floor_ms` seek rounding rationale (`legacy/encode_scenes.py:316-326`). New code in this style should keep justifying non-obvious engineering decisions inline rather than relying on commit messages or external docs.
## Import Organization
- One exception: `encode_scenes.py` imports `re` mid-file, right before its first use in the "Разбор входных данных" section (`legacy/encode_scenes.py:94`), rather than at the top with other stdlib imports. This is inconsistent with the top-of-file import block used for everything else — do not repeat this pattern; keep new imports grouped at the top of the file with the rest of stdlib imports.
## Error Handling
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
## Function Design
## Module Design
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview (Existing — `legacy/` scripts)
```text
```
## System Overview (Proposed — `PIPELINE_DESIGN.md`, NOT implemented)
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| `probe_source` | ffprobe-based width/height/frame_rate/duration extraction | `legacy/scene_detection.py:115` |
| `QsvPipeStream` | `VideoStream` adapter: owns an `ffmpeg` subprocess piping raw BGR24 frames (QSV decode + GPU downscale) to PySceneDetect; sequential-read only, `seek(0)` = process restart | `legacy/scene_detection.py:175` |
| `detect_scenes` / `_detect_relative` | Runs `AdaptiveDetector` via `SceneManager` over a `QsvPipeStream`, returns `List[Scene]` | `legacy/scene_detection.py:436`, `legacy/scene_detection.py:471` |
| `detect_scenes_parallel` + `find_boundary` / `_segment_worker` | Splits a file into `jobs` segments at real detected cut boundaries (found via short parallel pre-passes), detects each segment independently in a `ProcessPoolExecutor`-style worker, then stitches results | `legacy/scene_detection.py:582` |
| `keyframes_in_window` | ffprobe-based fast keyframe lookup in a narrow time window (used only during parallel boundary-finding) | `legacy/scene_detection.py:498` |
| CLI entry (`scene_detection.py __main__`) | argparse wrapper; writes `<video>.scenes` text file | `legacy/scene_detection.py:647` |
| `read_scenes` | Parses `<video>.scenes` text log into `(start_frame, end_frame)` tuples | `legacy/encode_scenes.py:99` |
| `keyframe_table_cues` / `keyframe_table_ffprobe` / `keyframe_table` | Fast-path: parse mkv Cues index via hand-rolled EBML reader for a keyframe table; fallback: full ffprobe packet scan | `legacy/encode_scenes.py:130`-`301` |
| `detect_hdr` | ffprobe-based detection of HDR10/HDR10+/Dolby Vision side data → qsvencc flag list | `legacy/encode_scenes.py:332` |
| `chunk_command` | Builds the `qsvencc` CLI command for one scene chunk (AV1, seek+trim, HDR flags, optional PSNR/SSIM) | `legacy/encode_scenes.py:354` |
| `encode_chunk` | Runs one `qsvencc` chunk subprocess, verifies frame count via `count_frames`, parses SSIM/PSNR from stderr | `legacy/encode_scenes.py:402` |
| `encode_audio` | ffmpeg-based audio encode/copy per preset rules (lossless→FLAC, other→Opus, already-target→copy); runs in a background thread parallel to video chunking | `legacy/encode_scenes.py:423` |
| `write_metrics_csv` | Writes per-scene + frame-weighted-total SSIM/PSNR/size CSV | `legacy/encode_scenes.py:481` |
| `main()` (encode_scenes.py) | Orchestrates: read scenes → build chunk tasks → `ThreadPoolExecutor(JOBS)` encode → ordered "high-water" append into `movie.obu` → wait audio → CSV → `mkvmerge` final mux → cleanup | `legacy/encode_scenes.py:515` |
## Pattern Overview
- Process-per-tool-invocation: every external tool (`ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`) is invoked as a subprocess; there is no persistent daemon or long-lived server component.
- GPU work (decode, downscale, encode) is delegated entirely to Intel Quick Sync Video via `ffmpeg -hwaccel qsv` and the external `qsvencc` binary; Python-side CPU work is deliberately minimized (small-frame scene-cut metrics only).
- Scene-boundary-aware chunked encoding: each detected scene becomes an independently encodable AV1 chunk seeked to the nearest source keyframe, so concatenation of raw `.obu` chunks (`cat`-equivalent via `shutil.copyfileobj`) is bit-exact without re-muxing tools.
- Correctness-by-construction claims (e.g., "chunk boundaries land exactly on keyframes," "DV RPU survives cat because per-frame metadata is preserved") are the load-bearing invariants of the whole design; changing seek/trim math or the mkv Cues parser risks silently corrupting output.
- No object-oriented service layer — the codebase is function-oriented with `dataclass(frozen=True)` value objects (`DetectionConfig`, `SourceInfo`, `Scene`).
## Layers
- Purpose: Convert a source video into an ordered list of `Scene(index, start_frame, end_frame, start_sec, end_sec)` records.
- Location: `legacy/scene_detection.py`
- Contains: ffprobe wrapper, custom `VideoStream` subclass wrapping an `ffmpeg` subprocess pipe, PySceneDetect `AdaptiveDetector` integration, sequential and parallel (segmented) detection entry points, CLI.
- Depends on: `ffmpeg`/`ffprobe` binaries, `scenedetect` (PySceneDetect) package, `numpy`.
- Used by: `legacy/encode_scenes.py` only indirectly, via the `<video>.scenes` text file it writes — there is no direct Python import between the two scripts today.
- Purpose: Turn a video + scene list into a final muxed AV1 `.mkv` with re-encoded/copied audio and preserved HDR/DV metadata.
- Location: `legacy/encode_scenes.py`
- Contains: scene-log parser, mkv Cues EBML parser (custom, hand-rolled), HDR/DV detection, per-scene chunk command builder, threaded chunk-encode + ordered-append orchestration, audio encode, CSV metrics writer, final mux via `mkvmerge`, CLI.
- Depends on: `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` binaries; the `<video>.scenes` file format produced by the detection layer.
- Used by: nothing else in-repo; it is the terminal stage.
## Data Flow
### Primary Path (Existing, sequential two-script run)
### (Proposed) Streaming Path — `PIPELINE_DESIGN.md`
## Key Abstractions
- Purpose: Represents one detected scene as a half-open frame interval `[start_frame, end_frame)` plus derived second-based timestamps.
- Examples: `legacy/scene_detection.py:95`
- Pattern: Immutable value object; `frame_count` computed property.
- Purpose: All tunables for scene detection (analysis width, QSV on/off, `AdaptiveDetector` thresholds, min scene length in frames or seconds, ffmpeg/ffprobe binary paths).
- Examples: `legacy/scene_detection.py:62`
- Pattern: Single config object threaded through every detection function instead of individual keyword args.
- Purpose: Adapts an `ffmpeg` subprocess (QSV decode + GPU downscale, raw BGR24 over stdout pipe) to PySceneDetect's `VideoStream` interface contract (`read`, `reset`, `seek`, frame/position properties).
- Examples: `legacy/scene_detection.py:175`
- Pattern: Adapter pattern; deliberately non-seekable (`is_seekable` False) except `seek(0)` which restarts the subprocess; supports a "segment mode" (`seek_sec`/`to_sec`) used only by the parallel-detection segment splitter.
- Purpose: Maps every source keyframe to its exact frame number and PTS time, used to compute the nearest-keyframe `--seek` point for each scene chunk in the encoder.
- Examples: `legacy/encode_scenes.py:152` (`keyframe_table_cues`, fast EBML parse of mkv Cues), `legacy/encode_scenes.py:265` (`keyframe_table_ffprobe`, slow full-file fallback), `kf_before` binary search at `legacy/encode_scenes.py:303`.
- Pattern: Precomputed lookup table, read once per run, queried per-scene.
- Purpose: Reassemble out-of-order parallel chunk-encode completions into strictly-ordered output without buffering all chunks in memory.
- Examples: `flush_appends()` closure at `legacy/encode_scenes.py:608`, using `next_append` counter and a `ready: Dict[int, int]` map.
- Pattern: Same pattern is explicitly slated for reuse unchanged by the proposed streaming consumer in `PIPELINE_DESIGN.md`.
## Entry Points
- Location: `legacy/scene_detection.py:647`
- Triggers: Manual `python3 scene_detection.py <input> [options]` invocation.
- Responsibilities: Parse CLI args (analysis width, threshold, min-scene-len, QSV on/off, jobs), run `detect_scenes`, write `<video>.scenes` text log.
- Location: `legacy/encode_scenes.py:515`, guard at `legacy/encode_scenes.py:727`
- Triggers: Manual `python3 encode_scenes.py <video> <scenes-log> [options]` invocation, or environment variables (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY`).
- Responsibilities: Full encode pipeline orchestration described in Data Flow above; tool-availability preflight check (`shutil.which` for `qsvencc`/`ffprobe`/`ffmpeg`/`mkvmerge`) before doing any work (`legacy/encode_scenes.py:532`).
## Architectural Constraints
- **Threading:** Both scripts use `ThreadPoolExecutor` for concurrency, not multiprocessing, for the *encode* side — encoding work is dominated by external `qsvencc` subprocess time, so Python's GIL is not a bottleneck. The *parallel scene detection* path (`detect_scenes_parallel`, `legacy/scene_detection.py:582`) explicitly notes that PySceneDetect's CPU-bound detector "serializes in threads" and needs real OS processes for parallelism — see the `_boundary_worker`/`_segment_worker` module-level function comment at `legacy/scene_detection.py:567` ("Настоящий параллелизм в обход GIL... в потоках сериализуется, в процессах — нет"), though the current `detect_scenes_parallel` implementation actually uses `ThreadPoolExecutor(max_workers=jobs)` for both boundary-finding and segment workers (`legacy/scene_detection.py:596`, `:614`) rather than a `ProcessPoolExecutor` — the module-level worker functions are structured to be process-pool-compatible (no closures/lambdas) but are not currently invoked through a process pool. This is a latent inconsistency between the comment's stated intent and the actual executor used.
- **Global state:** `_START = time.monotonic()` module-level timestamp in `legacy/encode_scenes.py:73`, used by the `log()`/`step()` helpers for elapsed-time-prefixed logging. No other module-level mutable state.
- **Non-seekable video stream:** `QsvPipeStream.is_seekable` is `False`; only `seek(0)` (full process restart) is supported. Any code path requiring arbitrary seeks on this stream type will raise `SeekError` (`legacy/scene_detection.py:367`).
- **Frame-number is the primary time coordinate, not wall-clock seconds:** For VFR sources, second-based timestamps (`frame/avg_fps`) are explicitly documented as approximate and can drift from real PTS; frame numbers are the source of truth for scene boundaries and are carried through to the encoder unchanged (`legacy/scene_detection.py:24-26`).
- **Stderr-to-tempfile, not PIPE:** `QsvPipeStream` writes ffmpeg stderr to a `SpooledTemporaryFile` rather than a `subprocess.PIPE`, specifically to avoid a documented deadlock risk (chatty stderr filling the 64KB pipe buffer while the consumer blocks on stdout) — `legacy/scene_detection.py:210-214`.
- **Hardware coupling:** The entire toolchain assumes an Intel Arc GPU with QSV/VA-API support (`iHD` driver), reflected in `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json` (`--device=/dev/dri`). Scripts have a `--no-qsv`/`use_qsv=False` software-decode fallback for debugging, but no equivalent fallback exists for the `qsvencc` AV1 encode step (hard external-tool dependency, no alternative encoder path in code).
## Anti-Patterns
### Hand-rolled binary format parsing embedded in the encoding script
### Untested, unvalidated-against-real-media code marked as production-ready
## Error Handling
- Preflight tool-availability checks before starting any real work (`shutil.which` loop, `legacy/encode_scenes.py:532`).
- "Drain-then-die": if any parallel chunk-encode job errors, the loop still drains all remaining futures (via `as_completed`) before calling `die()` with an aggregated error list, because in-flight `qsvencc` processes cannot be cleanly cancelled (`legacy/encode_scenes.py:626-657`, documented explicitly in `PIPELINE_DESIGN.md` line 167 as "drain-then-die, т.к. запущенные qsvencc чисто не отменить").
- Post-hoc frame-count verification as a correctness guard: both `encode_chunk` (per-chunk) and the final concatenated `movie.obu` are checked against expected frame counts via `count_frames` (ffprobe packet count), and any mismatch is a hard `die()` (`legacy/encode_scenes.py:415`, `:662`).
- Background-thread errors are captured as return values, not raised: `encode_audio` explicitly returns `(bool, Optional[str])` rather than raising, with a comment explaining that raising from a background thread would surface incorrectly (`legacy/encode_scenes.py:426-427`).
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
