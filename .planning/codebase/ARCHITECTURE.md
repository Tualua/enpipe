# Architecture

**Analysis Date:** 2026-07-08

**Scope note:** This repository is in an early/pre-implementation state. It contains two Python scripts inherited from a prior project (`legacy/`), a Russian-language design document (`PIPELINE_DESIGN.md`) describing an *intended* streaming/pipelined architecture, and a devcontainer for an Intel Arc GPU media-encoding toolchain. **No orchestrator, package, or `src/` tree exists yet.** This document describes the architecture of the existing `legacy/` scripts as-is, and separately describes the architecture proposed in `PIPELINE_DESIGN.md` that has **not** been implemented (status explicitly recorded in the design doc as "Спроектировано... НЕ реализовано" — "Designed... NOT implemented").

---

## System Overview (Existing — `legacy/` scripts)

The existing code is two independent, sequentially-run CLI scripts connected only by a shared intermediate file format (`*.scenes` text log). There is no orchestrator process; a human (or external shell script) runs step 1, then step 2.

```text
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Scene Detection (batch, CLI)                        │
│  `legacy/scene_detection.py`                                 │
│                                                                │
│  ffmpeg (QSV decode + GPU downscale) → rawvideo bgr24 pipe    │
│      → QsvPipeStream (VideoStream impl) → PySceneDetect       │
│      AdaptiveDetector → List[Scene]                           │
└───────────────────────────┬───────────────────────────────────┘
                             │ writes
                             ▼
                  `<video>.scenes` (text file: "scene NNNN frames [S, E) ...")
                             │ read by
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Scene-aware AV1 Encoding (batch, CLI)                │
│  `legacy/encode_scenes.py`                                    │
│                                                                │
│  read_scenes() → per-scene qsvencc chunk jobs (ThreadPool)    │
│      → ordered "high-water" append into `movie.obu`           │
│      → parallel audio encode (ffmpeg, separate thread)        │
│      → mkvmerge final mux (video + audio + source subs/       │
│        chapters/attachments)                                  │
└─────────────────────────────────────────────────────────────┘
```

Both scripts are standalone `if __name__ == "__main__"` CLI entry points with `argparse`; there is no shared library layer, no package `__init__.py`, and no test suite in the repo.

## System Overview (Proposed — `PIPELINE_DESIGN.md`, NOT implemented)

The design document proposes fusing the two batch steps into a single streaming producer/consumer process using an in-process `queue.Queue`, so encoding of early scenes can start while detection is still running on the tail of the file.

```text
┌─────────────────────────────────────────────────────────────┐
│                    main() — single process                   │
├─────────────────────────────────────────────────────────────┤
│  One-time probes: probe_fps, keyframe_table (mkv Cues),       │
│  detect_hdr → hdr_flags                                       │
│  audio_future = pool.submit(encode_audio, ...)  (as today)    │
│  q = queue.Queue(maxsize=8)   ← scene buffer + backpressure   │
├──────────────────────────┬─────────────────────────────────────┤
│  PRODUCER (thread)       │  CONSUMER (main thread) +          │
│  detect_scenes_streaming │  ThreadPoolExecutor(JOBS)           │
│  (new fn, jobs=1,        │  while scene := q.get():            │
│  sequential, emits Scene │      ex.submit(encode_chunk, ...)   │
│  per SceneManager        │  ordered high-water append/flush    │
│  callback) → q.put()     │  (identical to encode_scenes.py     │
│  blocks when queue full  │  today) → chunk deleted after flush │
└──────────────────────────┴─────────────────────────────────────┘
         │                              │
         └────────────► producer.join() → all futures done →
                          next_append == N → count_frames →
                          audio_future.result() → CSV → mkvmerge
```

**Interface:** in-process `queue.Queue`, deliberately *not* a growing `.scenes` file that the encoder tails — this gives free backpressure, shared exception propagation, no half-line races, and no extra disk I/O (disk is the bottleneck resource on the reference hardware). The existing file-based mode (`<video>.scenes`) remains for offline/manual runs — the batch path becomes "producer = drain `read_scenes()[lo:hi]` into the queue + sentinel," i.e. a special case of the streaming path.

**Verdict recorded in the design doc (as of 2026-07-08, unchanged since authoring):** on the reference hardware (spinning-disk ZFS pool + Arc A380 GPU), the pipelined design's Amdahl ceiling is only ~10-18% because encoding is 85-90% of total wall time and is the one non-overlappable block. Disk seek contention from overlapping the sequential detect read with the seek-heavy encode read pattern is projected to erase most or all of that gain (realistic range: -5% to ~0%). **Recommendation in the doc is NOT to build the pipeline on current hardware**; sequential `detect jobs=4 → encode jobs=4` is the recommended production path. The pipeline is only judged worthwhile if the source moves to SSD/NVMe or the file is already warm in ZFS ARC cache (~7-10% gain there). This is a build/no-build engineering decision, not a completed migration — treat any future implementation as a new phase against this baseline document, not as existing behavior.

---

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

**Overall:** Two-stage batch CLI pipeline connected via an intermediate file, each stage internally using a **producer pool + ordered consumer** concurrency pattern (`ThreadPoolExecutor` + `as_completed`, with monotonic "high-water mark" reassembly to preserve output order despite out-of-order task completion).

**Key Characteristics:**
- Process-per-tool-invocation: every external tool (`ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`) is invoked as a subprocess; there is no persistent daemon or long-lived server component.
- GPU work (decode, downscale, encode) is delegated entirely to Intel Quick Sync Video via `ffmpeg -hwaccel qsv` and the external `qsvencc` binary; Python-side CPU work is deliberately minimized (small-frame scene-cut metrics only).
- Scene-boundary-aware chunked encoding: each detected scene becomes an independently encodable AV1 chunk seeked to the nearest source keyframe, so concatenation of raw `.obu` chunks (`cat`-equivalent via `shutil.copyfileobj`) is bit-exact without re-muxing tools.
- Correctness-by-construction claims (e.g., "chunk boundaries land exactly on keyframes," "DV RPU survives cat because per-frame metadata is preserved") are the load-bearing invariants of the whole design; changing seek/trim math or the mkv Cues parser risks silently corrupting output.
- No object-oriented service layer — the codebase is function-oriented with `dataclass(frozen=True)` value objects (`DetectionConfig`, `SourceInfo`, `Scene`).

## Layers

**Detection layer** (`legacy/scene_detection.py`):
- Purpose: Convert a source video into an ordered list of `Scene(index, start_frame, end_frame, start_sec, end_sec)` records.
- Location: `legacy/scene_detection.py`
- Contains: ffprobe wrapper, custom `VideoStream` subclass wrapping an `ffmpeg` subprocess pipe, PySceneDetect `AdaptiveDetector` integration, sequential and parallel (segmented) detection entry points, CLI.
- Depends on: `ffmpeg`/`ffprobe` binaries, `scenedetect` (PySceneDetect) package, `numpy`.
- Used by: `legacy/encode_scenes.py` only indirectly, via the `<video>.scenes` text file it writes — there is no direct Python import between the two scripts today.

**Encoding layer** (`legacy/encode_scenes.py`):
- Purpose: Turn a video + scene list into a final muxed AV1 `.mkv` with re-encoded/copied audio and preserved HDR/DV metadata.
- Location: `legacy/encode_scenes.py`
- Contains: scene-log parser, mkv Cues EBML parser (custom, hand-rolled), HDR/DV detection, per-scene chunk command builder, threaded chunk-encode + ordered-append orchestration, audio encode, CSV metrics writer, final mux via `mkvmerge`, CLI.
- Depends on: `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` binaries; the `<video>.scenes` file format produced by the detection layer.
- Used by: nothing else in-repo; it is the terminal stage.

**(Proposed, not implemented) Orchestration layer:** `PIPELINE_DESIGN.md` describes a `main()` that would own both stages via an in-process queue, plus a new `detect_scenes_streaming()` generator function to be added "next to `detect_scenes`" in `scene_detection.py`, and a refactor of `encode_scenes.py`'s `main()` (lines 542-645 in the current file) to accept a queue-fed consumer instead of a pre-materialized list. None of this exists in code yet.

## Data Flow

### Primary Path (Existing, sequential two-script run)

1. User runs `python3 scene_detection.py video.mkv` → `probe_source` (`legacy/scene_detection.py:115`) → `QsvPipeStream` spawns `ffmpeg` decode+downscale pipe (`legacy/scene_detection.py:263`) → `SceneManager.detect_scenes` drives `AdaptiveDetector` frame-by-frame → `detect_scenes` builds `List[Scene]` (`legacy/scene_detection.py:471`) → CLI writes `video.mkv.scenes` (`legacy/scene_detection.py:683`).
2. User runs `python3 encode_scenes.py video.mkv video.mkv.scenes` → `read_scenes` parses the log (`legacy/encode_scenes.py:99`) → `probe_fps` + `keyframe_table` (Cues-index fast path) + `detect_hdr` run once (`legacy/encode_scenes.py:515-562`).
3. Audio encode is kicked off immediately on a background thread (`audio_pool.submit(encode_audio, ...)`, `legacy/encode_scenes.py:574`), running concurrently with video chunk encoding (CPU/ffmpeg work overlapping GPU/qsvencc work).
4. For each scene, `main()` computes `kf_before` + `fmt_seek` + `trim` and builds a `qsvencc` command per chunk (`legacy/encode_scenes.py:581-589`).
5. `ThreadPoolExecutor(max_workers=args.jobs)` runs `encode_chunk` for all scenes concurrently; as each completes (`as_completed`, order not guaranteed), the "high-water mark" `flush_appends()` writes any run of contiguous-by-index completed chunks into `movie.obu` and deletes the source chunk file (`legacy/encode_scenes.py:608-645`).
6. After all chunks complete and frame-count is verified (`count_frames` sanity check against `total_expect`), the code waits for the audio future, writes the metrics CSV, and invokes `mkvmerge` to produce the final `.mkv` (video + audio + source subs/chapters/attachments unless `--from/--to` partial mode) (`legacy/encode_scenes.py:659-724`).

**State Management:** All state is local to a single script invocation — in-memory dicts/lists (`chunk_paths`, `meta`, `ready`, `rows`) keyed by scene index, plus files on disk (`workdir/chunk_*.obu`, `workdir/movie.obu`, `workdir/audio.mka`) that are deleted after use unless `--keep` is passed. There is no database, no persistent job queue, and no cross-invocation state beyond the `<video>.scenes` text file and the final output `.mkv`.

### (Proposed) Streaming Path — `PIPELINE_DESIGN.md`

1. `detect_scenes_streaming()` (new, sketched but not implemented) would run `SceneManager.detect_scenes(..., callback=_on_cut)` on a background thread, translating each PySceneDetect cut callback into a `Scene` yielded through a `queue.Queue`-backed generator, with a final EOF-triggered scene and `stream.finish()` return-code check.
2. An orchestrator `main()` (not implemented) would read from this generator into a bounded `queue.Queue(maxsize=8)`, providing backpressure so detection cannot race far ahead of encoding on contended disk I/O.
3. The encoder side's `main()` would be refactored so its scene-reader thread pulls from the queue instead of a pre-read list, submitting `qsvencc` chunk jobs as scenes arrive; the existing ordered high-water append/flush consumer logic is explicitly stated to be reused "verbatim."
4. This is a **design proposal only** — see `PIPELINE_DESIGN.md` "Статус реализации" section, which explicitly states the streaming detector, the encoder's streaming consumer refactor, and the orchestrator queue are all "Спроектировано... НЕ реализовано" (designed, not implemented), and recommends implementing it only if the source moves to SSD/NVMe.

## Key Abstractions

**`Scene` (frozen dataclass):**
- Purpose: Represents one detected scene as a half-open frame interval `[start_frame, end_frame)` plus derived second-based timestamps.
- Examples: `legacy/scene_detection.py:95`
- Pattern: Immutable value object; `frame_count` computed property.

**`DetectionConfig` (frozen dataclass):**
- Purpose: All tunables for scene detection (analysis width, QSV on/off, `AdaptiveDetector` thresholds, min scene length in frames or seconds, ffmpeg/ffprobe binary paths).
- Examples: `legacy/scene_detection.py:62`
- Pattern: Single config object threaded through every detection function instead of individual keyword args.

**`QsvPipeStream` (VideoStream subclass):**
- Purpose: Adapts an `ffmpeg` subprocess (QSV decode + GPU downscale, raw BGR24 over stdout pipe) to PySceneDetect's `VideoStream` interface contract (`read`, `reset`, `seek`, frame/position properties).
- Examples: `legacy/scene_detection.py:175`
- Pattern: Adapter pattern; deliberately non-seekable (`is_seekable` False) except `seek(0)` which restarts the subprocess; supports a "segment mode" (`seek_sec`/`to_sec`) used only by the parallel-detection segment splitter.

**Keyframe table `List[Tuple[frame:int, pts_time:float]]`:**
- Purpose: Maps every source keyframe to its exact frame number and PTS time, used to compute the nearest-keyframe `--seek` point for each scene chunk in the encoder.
- Examples: `legacy/encode_scenes.py:152` (`keyframe_table_cues`, fast EBML parse of mkv Cues), `legacy/encode_scenes.py:265` (`keyframe_table_ffprobe`, slow full-file fallback), `kf_before` binary search at `legacy/encode_scenes.py:303`.
- Pattern: Precomputed lookup table, read once per run, queried per-scene.

**"High-water mark" ordered append:**
- Purpose: Reassemble out-of-order parallel chunk-encode completions into strictly-ordered output without buffering all chunks in memory.
- Examples: `flush_appends()` closure at `legacy/encode_scenes.py:608`, using `next_append` counter and a `ready: Dict[int, int]` map.
- Pattern: Same pattern is explicitly slated for reuse unchanged by the proposed streaming consumer in `PIPELINE_DESIGN.md`.

## Entry Points

**`legacy/scene_detection.py` (CLI, `__main__` block):**
- Location: `legacy/scene_detection.py:647`
- Triggers: Manual `python3 scene_detection.py <input> [options]` invocation.
- Responsibilities: Parse CLI args (analysis width, threshold, min-scene-len, QSV on/off, jobs), run `detect_scenes`, write `<video>.scenes` text log.

**`legacy/encode_scenes.py` (CLI, `main()` + `__main__` guard):**
- Location: `legacy/encode_scenes.py:515`, guard at `legacy/encode_scenes.py:727`
- Triggers: Manual `python3 encode_scenes.py <video> <scenes-log> [options]` invocation, or environment variables (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY`).
- Responsibilities: Full encode pipeline orchestration described in Data Flow above; tool-availability preflight check (`shutil.which` for `qsvencc`/`ffprobe`/`ffmpeg`/`mkvmerge`) before doing any work (`legacy/encode_scenes.py:532`).

**(Proposed) Unified orchestrator `main()`:** Described in `PIPELINE_DESIGN.md` as a single process combining both stages via threads + queue; no file or function exists for this yet.

## Architectural Constraints

- **Threading:** Both scripts use `ThreadPoolExecutor` for concurrency, not multiprocessing, for the *encode* side — encoding work is dominated by external `qsvencc` subprocess time, so Python's GIL is not a bottleneck. The *parallel scene detection* path (`detect_scenes_parallel`, `legacy/scene_detection.py:582`) explicitly notes that PySceneDetect's CPU-bound detector "serializes in threads" and needs real OS processes for parallelism — see the `_boundary_worker`/`_segment_worker` module-level function comment at `legacy/scene_detection.py:567` ("Настоящий параллелизм в обход GIL... в потоках сериализуется, в процессах — нет"), though the current `detect_scenes_parallel` implementation actually uses `ThreadPoolExecutor(max_workers=jobs)` for both boundary-finding and segment workers (`legacy/scene_detection.py:596`, `:614`) rather than a `ProcessPoolExecutor` — the module-level worker functions are structured to be process-pool-compatible (no closures/lambdas) but are not currently invoked through a process pool. This is a latent inconsistency between the comment's stated intent and the actual executor used.
- **Global state:** `_START = time.monotonic()` module-level timestamp in `legacy/encode_scenes.py:73`, used by the `log()`/`step()` helpers for elapsed-time-prefixed logging. No other module-level mutable state.
- **Non-seekable video stream:** `QsvPipeStream.is_seekable` is `False`; only `seek(0)` (full process restart) is supported. Any code path requiring arbitrary seeks on this stream type will raise `SeekError` (`legacy/scene_detection.py:367`).
- **Frame-number is the primary time coordinate, not wall-clock seconds:** For VFR sources, second-based timestamps (`frame/avg_fps`) are explicitly documented as approximate and can drift from real PTS; frame numbers are the source of truth for scene boundaries and are carried through to the encoder unchanged (`legacy/scene_detection.py:24-26`).
- **Stderr-to-tempfile, not PIPE:** `QsvPipeStream` writes ffmpeg stderr to a `SpooledTemporaryFile` rather than a `subprocess.PIPE`, specifically to avoid a documented deadlock risk (chatty stderr filling the 64KB pipe buffer while the consumer blocks on stdout) — `legacy/scene_detection.py:210-214`.
- **Hardware coupling:** The entire toolchain assumes an Intel Arc GPU with QSV/VA-API support (`iHD` driver), reflected in `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json` (`--device=/dev/dri`). Scripts have a `--no-qsv`/`use_qsv=False` software-decode fallback for debugging, but no equivalent fallback exists for the `qsvencc` AV1 encode step (hard external-tool dependency, no alternative encoder path in code).

## Anti-Patterns

### Hand-rolled binary format parsing embedded in the encoding script

**What happens:** `legacy/encode_scenes.py` contains a full hand-written EBML/Matroska parser (`_ebml_num`, `_eid`, `_esz`, `keyframe_table_cues`, lines `130`-`262`) to read the mkv `Cues` index directly from raw bytes, rather than shelling out to `mkvinfo`/`ffprobe` for this data.
**Why it's wrong:** This is significant unencapsulated complexity (130+ lines of manual byte-offset arithmetic) mixed into a top-level orchestration script with no unit tests and no separate module boundary. Any Matroska structural edge case (segments split across multiple SeekHeads, unusual EBML lacing) risks silently returning `None` (safe fallback to slow ffprobe path) or, worse, a wrong-but-parseable table.
**Do this instead:** If this parser is kept, it should be isolated into its own module with a dedicated test corpus of real mkv headers; the current mitigation (falling back to `keyframe_table_ffprobe` whenever anything looks off — `legacy/encode_scenes.py:294-300`) is reasonable but only covers *detected* failures, not silent wrong-answer cases.

### Untested, unvalidated-against-real-media code marked as production-ready

**What happens:** The module docstring for `legacy/scene_detection.py` states outright: "Модуль не прогонялся на реальном видео — ждёт интеграционного теста на NAS" ("This module has not been run against real video — awaiting an integration test on the NAS"), line `30`.
**Why it's wrong:** There is no test suite anywhere in the repository (no `tests/` directory, no `pytest`/`unittest` files), so this is not merely a documentation note but reflects the actual verification state of the code that is otherwise written with production-level defensiveness (error handling, edge cases, detailed comments).
**Do this instead:** Any future phase touching this code should add integration tests (at minimum, a regression test comparing `detect_scenes_parallel` output against sequential `detect_scenes` on a real sample file) before relying on it in an automated pipeline. `PIPELINE_DESIGN.md` line 131 independently calls out an equivalent required regression test for the not-yet-built streaming detector.

## Error Handling

**Strategy:** Fail-fast with `sys.exit` via a `die()` helper in the encoder (`legacy/encode_scenes.py:62`), and custom exception types in the detector (`SceneDetectionError(RuntimeError)`, `legacy/scene_detection.py:53`). Subprocess failures are checked via return codes (`subprocess.CalledProcessError` handling in `probe_source`, explicit `returncode != 0` checks after `qsvencc`/`mkvmerge`/ffmpeg runs) rather than allowing silent partial output.

**Patterns:**
- Preflight tool-availability checks before starting any real work (`shutil.which` loop, `legacy/encode_scenes.py:532`).
- "Drain-then-die": if any parallel chunk-encode job errors, the loop still drains all remaining futures (via `as_completed`) before calling `die()` with an aggregated error list, because in-flight `qsvencc` processes cannot be cleanly cancelled (`legacy/encode_scenes.py:626-657`, documented explicitly in `PIPELINE_DESIGN.md` line 167 as "drain-then-die, т.к. запущенные qsvencc чисто не отменить").
- Post-hoc frame-count verification as a correctness guard: both `encode_chunk` (per-chunk) and the final concatenated `movie.obu` are checked against expected frame counts via `count_frames` (ffprobe packet count), and any mismatch is a hard `die()` (`legacy/encode_scenes.py:415`, `:662`).
- Background-thread errors are captured as return values, not raised: `encode_audio` explicitly returns `(bool, Optional[str])` rather than raising, with a comment explaining that raising from a background thread would surface incorrectly (`legacy/encode_scenes.py:426-427`).

## Cross-Cutting Concerns

**Logging:** Custom `log()`/`step()` context-manager helpers print timestamped (`[{elapsed:8.1f}s]`), unbuffered (`flush=True`) lines to stdout; no logging framework, no log levels, no log file output (`legacy/encode_scenes.py:76-88`). `scene_detection.py`'s CLI has no equivalent logging helper — it only prints a final summary line.

**Validation:** Extensive defensive validation of external-tool output (ffprobe JSON parsing with explicit fallback chains for frame rate, frame-count cross-checks after every encode step, mkv Cues parser falls back safely on any structural anomaly) but no input schema validation library — all hand-written.

**Authentication:** Not applicable — this is a local CLI media-processing toolchain with no network service, no auth boundary, and no multi-user concerns.

---

*Architecture analysis: 2026-07-08*
