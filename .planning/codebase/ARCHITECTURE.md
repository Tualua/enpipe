<!-- refreshed: 2026-10-03 -->
# Architecture

**Analysis Date:** 2026-10-03

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                       enpipe CLI (argparse)                          │
│               `enpipe detect` / `enpipe encode` / `enpipe run`       │
│                  `src/enpipe/cli/main.py:build_parser`               │
└───────────┬──────────────────────────┬──────────────────┬────────────┘
            │                          │                  │
            ▼                          ▼                  ▼
      ┌──────────────┐          ┌──────────────┐   ┌───────────────┐
      │  Detection   │          │  Encoding    │   │  Orchestration
      │  Pipeline    │          │  Pipeline    │   │  (Sequential) │
      │ run_detect() │          │ run_encode() │   │run_pipeline() │
      └──────────────┘          └──────────────┘   └───────────────┘
            │                          │                  │
            ▼                          ▼                  ▼
      ┌──────────────────────────────────────────────────────────────┐
      │           Scene Detection Layer (QSV + PySceneDetect)        │
      │   `src/enpipe/detection/detect.py:detect_scenes()`           │
      │   - Sequential: AdaptiveDetector over QsvPipeStream           │
      │   - Parallel: Segment-boundaries + per-segment detect jobs   │
      └──────────────┬───────────────────────────────────────────────┘
                     │ → `<video>.scenes` (text log)
                     ▼
      ┌──────────────────────────────────────────────────────────────┐
      │           Encoding Layer (AV1 QSV + Orchestration)           │
      │   `src/enpipe/encoding/pipeline.py:run_encode()`             │
      │   - Read scenes → keyframe table (EBML fast-path)            │
      │   - Parallel chunk encode (ThreadPoolExecutor)               │
      │   - High-water-mark ordered append (flush_appends)           │
      │   - Parallel audio encode                                    │
      └──────────────┬─────────────────────────────────────────────┬─┘
                     │                                             │
         [per-chunk] │                                    movie.obu │
              chunk  │                                             │
              .obu   │                                             │
                     └─────────────────┬───────────────────────────┘
                                       ▼
      ┌──────────────────────────────────────────────────────────────┐
      │              Mux Layer (mkvmerge + Finalization)             │
      │   `src/enpipe/encoding/pipeline.py:run_encode()` tail       │
      │   - Assemble: video (movie.obu) + audio + subs/chapters     │
      │   - Preserve metadata: HDR10/HDR10+/DV, timestamps           │
      └──────────────────────────────────────────────────────────────┘
                     │
                     ▼
            Output: `<video>.av1.mkv`
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

**Overall:** Two-stage batch pipeline with load-bearing correctness invariants.

**Key Characteristics:**
- **No persistent daemon** — every subprocess (ffmpeg, ffprobe, qsvencc, mkvmerge) is invoked via `subprocess.run` and awaited immediately or collected in a thread pool.
- **GPU-centric** — Intel Arc QSV used for decode (with GPU downscale for detector) and AV1 encode; Python-side CPU work deliberately minimized.
- **Scene-boundary-aware chunking** — each scene becomes an independently seekable AV1 chunk, keyed to source keyframes; chunks concatenate bit-exactly via raw `.obu` file append.
- **Strict frame-count parity** — at encode start (per-chunk), after concatenation (full `movie.obu`), and before mux, frame counts are verified against expected values; any mismatch is fatal.
- **High-water-mark ordered append** — parallel chunk encodes finish out-of-order; results are buffered in a `ready: Dict[int, int]` map keyed by scene index, flushed to the output stream only when all earlier scenes are complete. This pattern is reused by both the current batch encoder and the (unimplemented) planned streaming orchestrator.

## Layers

**Detection Layer:**
- Purpose: Convert source video into an ordered list of `Scene(index, start_frame, end_frame, start_sec, end_sec)` records.
- Location: `src/enpipe/detection/`
- Contains: ffprobe wrapper (`probe_source`), custom `VideoStream` subclass (`QsvPipeStream`) wrapping an ffmpeg subprocess pipe, PySceneDetect `AdaptiveDetector` integration, sequential (`detect_scenes`) and parallel (`detect_scenes_parallel`) entry points, CLI orchestration (`run_detect`).
- Depends on: `ffmpeg`/`ffprobe` binaries, PySceneDetect 0.7 package, numpy.
- Used by: `src/enpipe/encoding/pipeline.py` indirectly via the `<video>.scenes` text file; `src/enpipe/cli/main.py` orchestration path.

**Encoding Layer:**
- Purpose: Turn a video + scene list into a final muxed AV1 `.mkv` with re-encoded/copied audio and preserved HDR/DV metadata.
- Location: `src/enpipe/encoding/`
- Contains: scene-log parser, keyframe-table builder (EBML fast-path + ffprobe fallback), HDR/DV detection, per-scene chunk command builder, threaded chunk-encode with ordered-append orchestration, parallel audio encode, CSV metrics writer, final mux via mkvmerge, CLI orchestration (`run_encode`).
- Depends on: `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` binaries; the `<video>.scenes` text file format produced by the detection layer.
- Used by: nothing else in-repo; it is the terminal stage.

**EBML/Matroska Module:**
- Purpose: Hand-rolled, pure (no I/O) binary parser for EBML/Matroska structure navigation and Cues (keyframe index) extraction.
- Location: `src/enpipe/mkv/ebml.py`
- Contains: EBML variable-length integer parsing (`_ebml_num`, `_eid`, `_esz`), SeekHead traversal, Info (TimestampScale) extraction, Tracks (video track number) extraction, Cues body parsing.
- Depends on: none (pure bytes-in, tuples-out).
- Used by: `src/enpipe/encoding/keyframes.py` (thin I/O wrapper).

**Shared Utilities:**
- Purpose: Leaf modules with no inter-package dependencies (keep layers acyclic): logging/die, subprocess wrapper, batch processing, qsvencc version checking.
- Location: `src/enpipe/shared/`
- Contains: `logging.py` (elapsed-time-prefixed log, step context manager, die/exit), `proc.py` (subprocess.run wrapper), `batch.py` (batch file iteration and error handling), `qsvencc_version.py` (runtime check for fixed qsvencc: `QSVENCC_MIN_REV = 4634`; `QSVENCC_METRICS_MIN_REV = 4658` gates the metrics path in the COR-02 lock and hardware tier).
- Depends on: none.
- Used by: all layers.

## Data Flow

### Primary Path: `enpipe run <video>`

1. **CLI entry** (`src/enpipe/cli/main.py:run_pipeline`, line 77)
   - which-preflight: check qsvencc/ffprobe/ffmpeg/mkvmerge availability
   - `ensure_qsvencc_fixed()` (fail-fast gate before long detect phase)
   - Parse video path; apply `-o`/`--out-dir`/`--scenes` rules

2. **Scene detection** (`src/enpipe/detection/pipeline.py:run_detect`, line 29)
   - Build `DetectionConfig` from CLI args
   - Call `detect_scenes(video, config, jobs=args.detect_jobs, show_progress=True)`
   - Dispatch: if `jobs > 1`, call `detect_scenes_parallel` (segment boundaries + parallel per-segment detection)
   - Sequential fallback: `QsvPipeStream(video, config)` → `AdaptiveDetector` via `SceneManager` → `_build_scenes` → `List[Scene]`
   - Write `<video>.scenes` text log (one scene per line: `scene NNNN frames [S, E) T0 .. T1`)

3. **Encoding orchestration** (`src/enpipe/encoding/pipeline.py:run_encode`, line 107)
   - Read `<video>.scenes` text log via `read_scenes()` → `List[(start_frame, end_frame)]`
   - Probe FPS via `probe_fps()` (ffprobe)
   - Build keyframe table via `keyframe_table()` (EBML fast-path or ffprobe fallback)
   - Detect HDR metadata via `detect_hdr()` (ffprobe side-data)
   - **Parallel phase start**: 
     - Audio encode in background thread (`ThreadPoolExecutor(max_workers=1)`, `encode_audio()`)
     - For each scene, build task tuple `(scene_index, qsvencc_command, output_path, expected_frames)`
   - **Chunk encoding loop** (`ThreadPoolExecutor(max_workers=args.jobs)`, line 248):
     - Submit all tasks to executor
     - For each completed task (via `as_completed`):
       - `encode_chunk()`: run qsvencc, verify frame count, parse PSNR/SSIM from stderr
       - Store result in `ready[scene_index] = frame_count`
       - Call `flush_appends()`: write all contiguous ready chunks to `movie.obu` (high-water-mark pattern)
       - Delete chunk file if not `--keep`
   - **Post-encode validation** (line 288):
     - `count_frames(movie.obu)` must equal `sum(scene.frame_count for scene in scenes)`
     - If not: fatal error (drain-then-die: all remaining futures are allowed to complete before exit)
   - **Audio join** (line 303): wait for background audio encode future; fail if error
   - **Metrics CSV** (line 315): if `--no-metrics` not set, write per-scene table + frame-weighted-total line
   - **Final mux** (line 329): `mkvmerge -o output.mkv movie.obu audio.mka [source subs/chapters]`
   - **Cleanup** (line 341): delete chunk workdir if not `--keep`

### Parallel Detection Path: `detect_scenes_parallel()`

**Boundary-finding phase** (`src/enpipe/detection/parallel.py`, lines 120–160):
- Divide timeline into `jobs` segments at uniform time/frame points
- For each segment, `find_boundary()`: probe for nearest real scene cut via quick ffprobe window scan + short AdaptiveDetector run
- Collect boundaries; sanitize (sort, dedupe, clamp to [0, total_frames])

**Per-segment detection** (lines 160–180):
- For each segment `[start_frame, end_frame)`, spawn `_segment_worker()`:
  - Create `QsvPipeStream` (segment mode: `seek_sec`/`to_sec` cropping)
  - Run `_detect_relative()` to get scene-boundary tuples relative to segment start
  - Adjust back to absolute frame numbers
- Collect all relative results
- Merge results: sort, dedupe adjacent boundaries, rebuild `List[Scene]`

**Guarantee**: Output is frame-count-identical to sequential `detect_scenes(..., jobs=1)` by construction (boundaries are set at real cuts, so each segment's AdaptiveDetector sees the same context it would in a full pass).

## Key Abstractions

### `Scene` (Immutable Value Object)

**Purpose**: Represents one detected scene as a half-open frame interval `[start_frame, end_frame)` plus derived second-based timestamps.

**Examples**: `src/enpipe/detection/config.py:59`

**Pattern**: `@dataclass(frozen=True)` with computed property `frame_count`.

```python
@dataclass(frozen=True)
class Scene:
    index: int
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float
    
    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame
```

### `DetectionConfig` (Immutable Config Object)

**Purpose**: All tunables for scene detection (analysis width, QSV on/off, AdaptiveDetector thresholds, min scene length, ffmpeg/ffprobe binary paths).

**Examples**: `src/enpipe/detection/config.py:26`

**Pattern**: Single frozen dataclass threaded through every detection function instead of individual keyword args. Enables testability (fixture-driven) and parity checking (swappable configs).

### `QsvPipeStream` (Adapter Pattern)

**Purpose**: Adapts an `ffmpeg` subprocess (QSV decode + GPU downscale, raw BGR24 over stdout pipe) to PySceneDetect's `VideoStream` interface contract.

**Examples**: `src/enpipe/detection/stream.py:175`

**Pattern**: Adapter pattern; deliberately non-seekable (`is_seekable = False`) except `seek(0)` (restarts subprocess). Supports "segment mode" (`seek_sec`/`to_sec` crop window) used only by parallel detection. Stderr written to `SpooledTemporaryFile` (not `PIPE`) to avoid stdout/stderr deadlock on chattiness.

### Keyframe Table (`List[Tuple[int, float]]`)

**Purpose**: Maps every source keyframe to exact frame number and PTS time; used to compute the nearest-keyframe `--seek` point for each scene chunk.

**Examples**: `src/enpipe/encoding/keyframes.py:76` (main entry point), `src/enpipe/mkv/ebml.py` (EBML parser).

**Pattern**: Precomputed at encode start, read once per run, queried per-scene via binary search (`kf_before` in `compute_chunk_seek_trim`). Fast-path: EBML Cues-index parse (mkv files, milliseconds). Fallback: ffprobe full-file packet scan (slow, I/O-bound, needed for non-mkv or corrupted Cues).

### High-Water-Mark Ordered Append (`flush_appends()`)

**Purpose**: Reassemble out-of-order parallel chunk-encode completions into strictly-ordered output without buffering all chunks in memory.

**Examples**: `src/enpipe/encoding/pipeline.py:237` (flush_appends closure), `contiguous_run` helper at line 45.

**Pattern**: `next_append` counter tracks the index of the next chunk to write; `ready: Dict[int, int]` holds frame counts of finished chunks keyed by index. After each chunk completes, call `flush_appends()`: write all chunks from `next_append` onwards that are in `ready` (contiguous run). This pattern is **load-bearing** (same implementation reused by the unimplemented streaming orchestrator per `PIPELINE_DESIGN.md:149-151`).

### HDR/DV Metadata Preservation

**Purpose**: Detect and propagate HDR10, HDR10+, and Dolby Vision metadata through per-chunk encoding.

**Pattern**: `detect_hdr()` inspects ffprobe side-data → builds qsvencc flag list (`--dolby-vision-rpu copy`, `--masteringdisplaydata`, `--contentlightlevel`, etc.). These flags are baked into every `chunk_command()`. Per-frame metadata (DV RPU, mastering data) is preserved because `qsvencc` with these flags copies it frame-by-frame, and concatenation (`cat` of .obu chunks) is lossless for frame-level side data.

## Entry Points

**`enpipe detect <video> [options]`**:
- Location: `src/enpipe/cli/main.py:run_detect`
- Triggers: Manual CLI invocation (or `enpipe run` internal call).
- Responsibilities: Parse detect-specific CLI args, build `DetectionConfig`, call `detect_scenes()`, format and write `<video>.scenes`.

**`enpipe encode <video> <scenes> [options]`**:
- Location: `src/enpipe/encoding/pipeline.py:run_encode` (line 107)
- Triggers: Manual CLI invocation (or `enpipe run` internal call).
- Responsibilities: Full encode pipeline (described in Data Flow above); tool-availability preflight; qsvencc version check (fail-fast gate).

**`enpipe run <video> [options]`**:
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

**What happens**: EBML/Matroska Cues-index parsing (`src/enpipe/mkv/ebml.py`) is implemented as hand-written variable-length-integer parsing and element-tree traversal, without relying on a third-party mkv library.

**Why it's wrong**: Binary format parsing is fragile; even small typos (off-by-one in size calculations, wrong endianness, incorrect element ID constants) can silently corrupt interpretation of metadata.

**How it's mitigated (not removed entirely)**: 
1. **Isolation**: Parsing logic is in a pure module (`enpipe.mkv.ebml`) with no I/O or subprocess calls. All test fixtures are byte strings, not real files.
2. **Comprehensive test suite**: `tests/unit/mkv/test_ebml.py` covers the parser with synthetic Matroska structures + edge cases (truncated elements, missing Cues, structural anomalies).
3. **Fallback path**: If Cues parsing fails or returns None, the encoder automatically falls back to `keyframe_table_ffprobe()` (slow but correct full-file scan). Thus, a parsing bug only risks performance regression, not data corruption.
4. **Validity checks**: Return types and boundary checks on every parsing step; the parser **never raises**, only returns None on any structural anomaly, triggering fallback.

**Do this instead**: Use a proper mkv library (e.g., pymkv, matroska-python) if available and with acceptable dependency footprint. Current implementation is justified because the hand-rolled parser is lightweight (pure bytes-in), thoroughly tested, and has a bulletproof fallback.

### Silent Frame-Count Mismatches Due to Seek/Trim Math

**What happens**: Chunk seek-time and trim-duration calculations (`compute_chunk_seek_trim`, `src/enpipe/encoding/keyframes.py:103`) use floating-point floor/ceil rounding to align to millisecond boundaries (ffmpeg `-ss` / `-t` granularity). Rounding errors can cause off-by-one frame discrepancies between expected and actual chunk output.

**Why it's wrong**: Incorrect frame counts at mux time could silently result in missing or duplicated frames in the final output, breaking parity with the source.

**How it's mitigated**:
1. **Explicit rounding**: Seek times are floored to milliseconds (discard sub-ms precision), not truncated arbitrarily. Rationale documented in-code (`src/enpipe/encoding/keyframes.py:316-326`): "floor_ms" ensures consistency between sequential and parallel detection, and between single-file and chunked encoding.
2. **Post-hoc verification**: After every chunk encodes, frame count is verified via `count_frames()` (ffprobe packet count). If actual ≠ expected, the chunk is marked as failed; failed chunks prevent mux completion (drain-then-die).
3. **End-to-end validation**: After concatenation of all chunks, `count_frames(movie.obu)` is verified against the sum of all scene frame ranges. Any mismatch is fatal before mux.

**Do this instead**: This is the correct pattern. No better alternative exists without re-implementing ffmpeg's internal seek logic (not tractable).

## Error Handling

**Strategy**: Fail-fast on preflight checks (tool availability, qsvencc version, source file existence); collect and report batch errors; drain-then-die for parallel chunk failures.

**Patterns**:
- **Preflight**: `shutil.which()` loop checks qsvencc/ffprobe/ffmpeg/mkvmerge before any real work (`src/enpipe/encoding/pipeline.py:108`). `ensure_qsvencc_fixed()` verifies qsvencc version ≥ r4663 (includes upstream fix 45003f1 for cross-session frame corruption and the `--seek` fix); the pinned build is the Tualua fork 8.32+vppsync6 (r4663).
- **Background thread errors**: `encode_audio()` returns `(bool, Optional[str])` (success, error message) instead of raising, because it runs in a background thread. The main thread calls `.result()` on the future and checks the error tuple, then calls `die()` if needed—keeping error handling on the main thread.
- **Batch-vs-immediate failure**: In parallel chunk encoding, all in-flight futures complete even if one fails. Errors are collected in an `errors` list, capped at 10, and reported once before calling `die()` (drain-then-die). This gives users visibility into all failures, not just the first one.
- **Cleanup on error**: `try/finally` blocks in `QsvPipeStream` ensure `close()` (force-kill subprocess) is always called on early exit or exception.

## Cross-Cutting Concerns

**Logging**: Elapsed time prefix (time since startup), unbuffered output. Implemented in `src/enpipe/shared/logging.py`. `log()` for status messages, `step()` context manager for time-tracked operations (prints `✔ name — Xs` only on success).

**Validation**: Frame-count verification at encode start, per-chunk, and post-concatenation. FFprobe availability is assumed (hard requirement). Scene boundary detection uses PySceneDetect's `AdaptiveDetector` with configurable threshold and min-scene-length.

**Authentication**: None (local/NAS toolchain; no network or user identity).

**Batch processing**: `iter_input_videos()` discovers video files in a directory (with `--recursive` flag); `run_batch()` processes each with error isolation (per-file skip reasons logged, batch proceeds). Output path collision detection: if two input files would write to the same output file, the second is skipped (correctness-first: no silent data loss).

---

*Architecture analysis: 2026-10-03*
