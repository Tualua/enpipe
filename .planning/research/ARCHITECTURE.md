# Architecture Research

**Domain:** Packaging an existing two-script subprocess-orchestration media pipeline (Python) into a testable, installable package — no runtime-behavior change
**Researched:** 2026-07-08
**Confidence:** HIGH (grounded directly in `legacy/scene_detection.py` and `legacy/encode_scenes.py` source, `.planning/codebase/ARCHITECTURE.md`, and current `packaging.python.org` guidance)

## Scope Boundary (read first)

This research covers **structural packaging** only: how to move `legacy/*.py` into an installable package with module boundaries and testing seams, **without** changing what the code does. It explicitly does **not** design, sketch, or recommend the in-process streaming/queue orchestrator described in `PIPELINE_DESIGN.md` — that is out of scope for this milestone per `PROJECT.md` and its own "do not build on current hardware" verdict. Where this document proposes a "unified entry point," that means a single **CLI dispatcher** (`enpipe detect …` / `enpipe encode …`) that calls the same two independent pipelines connected by the same `<video>.scenes` intermediate file — not a fused runtime. This distinction is load-bearing; do not let "unified entry point" work drift into orchestrator work.

## Standard Architecture

### System Overview (target, after restructuring)

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      console_script: `enpipe` (cli/app.py)                 │
│                        argparse subcommands, dispatch only                 │
├───────────────────────────────┬─────────────────────────────────────────────┤
│  `enpipe detect`  (cli/detect.py)   │  `enpipe encode` (cli/encode.py)         │
│  thin argparse wrapper              │  thin argparse wrapper                    │
└───────────────┬─────────────────────┴───────────────────┬─────────────────────┘
                │                                          │
                ▼                                          ▼
┌───────────────────────────────┐        ┌────────────────────────────────────────┐
│   enpipe.detection (package)   │        │   enpipe.encoding (package)             │
│   config / probe / stream /    │        │   scenes_io / keyframes / hdr / chunk / │
│   detect / parallel            │        │   audio / metrics / pipeline            │
└───────────────┬────────────────┘        └───────┬───────────────────┬────────────┘
                │ writes                            │ reads            │ uses
                ▼                                    ▼                  ▼
        `<video>.scenes` (unchanged text format, still the ONLY coupling)
                                                                          ▼
                                                              ┌───────────────────┐
                                                              │  enpipe.mkv.ebml   │
                                                              │  (isolated, tested)│
                                                              └───────────────────┘

        Both `enpipe.detection` and `enpipe.encoding` depend on:
┌───────────────────────────────────────────────────────────────────────────┐
│                          enpipe.shared (library layer)                     │
│   proc.py (subprocess seam)  |  ffprobe.py (probe helpers)  | logging.py   │
└───────────────────────────────────────────────────────────────────────────┘
```

This mirrors the existing runtime architecture exactly (`.planning/codebase/ARCHITECTURE.md`): two independent batch stages connected only by the `.scenes` file, each internally a producer-pool + ordered-consumer. The only new things are (1) a package boundary and shared library layer, (2) a CLI dispatcher on top, (3) a subprocess seam for testing. No queue, no fused process, no change to what `detect_scenes` / `main()` in the encoder compute.

### Component Responsibilities

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `cli/app.py` | `enpipe` console_script entry point; argparse subparsers `detect`/`encode` that dispatch to `cli/detect.py:run()` / `cli/encode.py:run()` | Pure dispatch, no logic |
| `cli/detect.py` | Reproduces `legacy/scene_detection.py`'s exact argparse surface; calls `detection.detect.detect_scenes`; writes `.scenes` file | Behavior-identical to today's `__main__` block |
| `cli/encode.py` | Reproduces `legacy/encode_scenes.py`'s exact argparse surface + env var precedence (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY`); calls `encoding.pipeline.run_encode` | Behavior-identical to today's `main()` |
| `detection.config` | `DetectionConfig`, `SourceInfo`, `Scene` frozen dataclasses | Pure data, zero I/O |
| `detection.stream` | `QsvPipeStream` (VideoStream adapter over an ffmpeg subprocess pipe) | Subprocess boundary — see Testability Seams |
| `detection.detect` | `detect_scenes`, `_detect_relative`, `_build_scenes` | Sequential path |
| `detection.parallel` | `detect_scenes_parallel`, `find_boundary`, `keyframes_in_window`, `_boundary_worker`, `_segment_worker` | Segmented parallel path |
| `encoding.scenes_io` | `read_scenes` — parses the `<video>.scenes` text format | Shared wire format; must stay byte-compatible with the detector's writer |
| `mkv.ebml` | Isolated hand-rolled EBML var-int reader + Cues-index parser (`_ebml_num`, `_eid`, `_esz`, `keyframe_table_cues`) | See dedicated section below — highest-priority isolation target |
| `encoding.keyframes` | `keyframe_table` (dispatches to `mkv.ebml` or ffprobe fallback), `keyframe_table_ffprobe`, `kf_before`, `fmt_seek`, new `compute_chunk_seek_trim` | Correctness-critical seek/trim math — see dedicated section |
| `encoding.hdr` | `detect_hdr` | ffprobe-based HDR10/HDR10+/DV flag derivation |
| `encoding.chunk` | `chunk_command`, `encode_chunk`, `parse_metrics`, `count_frames` | Per-chunk qsvencc invocation + verification |
| `encoding.audio` | `encode_audio` | Background-thread audio encode/copy |
| `encoding.metrics` | `write_metrics_csv` | Pure-ish CSV writer given rows |
| `encoding.pipeline` | `run_encode(args)` — the orchestration currently in `main()`: task building, `ThreadPoolExecutor` chunk phase, high-water append, frame-count verification, mux, cleanup | Kept sequential/threaded exactly as today; only extraction target is pulling pure sub-steps out (see Testability Seams) |
| `shared.proc` | `run(cmd, **kw)` / `popen(cmd, **kw)` — the only place `subprocess.run`/`Popen` are called | The dependency-injection seam for all subprocess-invoking code |
| `shared.ffprobe` | Candidate future home for deduplicated ffprobe-JSON parsing (currently duplicated as `probe_source` vs `probe_fps`) | **Do this last** — see Migration Order, step 6 |
| `shared.logging` | `log()`/`step()` context-manager helpers, currently only in `encode_scenes.py` | Reused by both CLIs for consistent output |

## Recommended Project Structure

```
enpipe/
├── pyproject.toml            # [project] metadata, [project.scripts] enpipe=..., deps + dev deps
├── src/
│   └── enpipe/
│       ├── __init__.py               # version only; no logic
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py                # console_script entry: `enpipe {detect,encode}`
│       │   ├── detect.py             # argparse surface, mirrors legacy scene_detection.py __main__
│       │   └── encode.py             # argparse surface, mirrors legacy encode_scenes.py __main__/args
│       ├── detection/
│       │   ├── __init__.py
│       │   ├── config.py             # DetectionConfig, SourceInfo, Scene
│       │   ├── stream.py             # QsvPipeStream
│       │   ├── detect.py             # detect_scenes, _detect_relative, _build_scenes, _min_scene_len
│       │   └── parallel.py           # detect_scenes_parallel, find_boundary, keyframes_in_window, workers
│       ├── encoding/
│       │   ├── __init__.py
│       │   ├── scenes_io.py          # read_scenes (the <video>.scenes format parser)
│       │   ├── keyframes.py          # keyframe_table, keyframe_table_ffprobe, kf_before, fmt_seek,
│       │   │                          #   compute_chunk_seek_trim (new pure extraction)
│       │   ├── hdr.py                # detect_hdr
│       │   ├── chunk.py              # chunk_command, encode_chunk, parse_metrics, count_frames
│       │   ├── audio.py              # encode_audio
│       │   ├── metrics.py            # write_metrics_csv
│       │   └── pipeline.py           # run_encode(args): orchestration, high-water append, mux, cleanup
│       ├── mkv/
│       │   ├── __init__.py
│       │   └── ebml.py               # _ebml_num/_eid/_esz + keyframe_table_cues, I/O split from parsing
│       └── shared/
│           ├── __init__.py
│           ├── proc.py               # run(), popen() — the sole subprocess seam
│           ├── ffprobe.py            # (post-migration) deduplicated probe helpers
│           └── logging.py            # log(), step()
├── tests/
│   ├── unit/
│   │   ├── test_ebml.py              # mkv/ebml.py against a small corpus of Cues byte fixtures — no real files
│   │   ├── test_keyframes.py         # kf_before, fmt_seek, compute_chunk_seek_trim — pure, no mocking
│   │   ├── test_scenes_io.py         # read_scenes round-trip against known-good log text
│   │   ├── test_chunk_command.py     # chunk_command argv construction (pure)
│   │   ├── test_hdr.py               # detect_hdr flag derivation, shared.proc.run mocked
│   │   ├── test_probe.py             # probe_source/probe_fps, shared.proc.run mocked with canned ffprobe JSON
│   │   ├── test_stream.py            # QsvPipeStream read/reset/seek against a fake Popen (no real ffmpeg)
│   │   └── test_high_water.py        # pure sequencing helper extracted from flush_appends
│   ├── integration/
│   │   ├── test_detect_parallel_matches_sequential.py  # mandatory regression test (PROJECT.md Active scope)
│   │   └── test_end_to_end.py        # real media, real qsvencc — requires devcontainer/hardware, marked slow
│   └── fixtures/
│       └── mkv_headers/              # small synthetic/real mkv Cues byte blobs for the EBML parser
└── legacy/                            # left in place until parity is verified per file (see Migration Order)
```

### Structure Rationale

- **`src/` layout, not flat:** Prevents accidental imports of the working-tree copy instead of the installed package during tests (standard `packaging.python.org` guidance — see Sources), and forces `pip install -e .` to be the actual dev workflow from day one, matching the "proper installable module structure" requirement in `PROJECT.md`.
- **`detection/` and `encoding/` stay separate packages, coupled only by `encoding/scenes_io.py` reading the same text format `detection` writes:** This is not a stylistic choice — it is the existing, load-bearing architecture (`.planning/codebase/ARCHITECTURE.md`: "there is no direct Python import between the two scripts today"). Preserving the file-based boundary (rather than having `encoding` import `detection` directly) keeps the current two-independent-CLI-invocation workflow valid and keeps this milestone from quietly becoming the fused orchestrator.
- **`mkv/ebml.py` is its own top-level package, not a submodule of `encoding/`:** `PROJECT.md` names this explicitly as the top tech-debt item ("isolate the hand-rolled EBML/Cues parser behind a tested module boundary"). Giving it a standalone package signals it is a general-purpose Matroska-parsing utility, not encoder-orchestration logic, and lets its test suite (byte-fixture based, no ffmpeg/qsvencc needed) run fast and in isolation.
- **`shared/proc.py` is the single subprocess choke point:** Every current subprocess call (`subprocess.run` in `scene_detection.py`'s `probe_source`/`keyframes_in_window`, `subprocess.Popen` in `QsvPipeStream`, `subprocess.run` throughout `encode_scenes.py` via its existing local `run()` wrapper) gets routed through one importable module. This is the primary testability lever for this whole codebase — see next section.
- **`cli/` is intentionally thin:** argparse definitions and env-var reads only, calling into `detection`/`encoding` functions that take plain arguments. This makes the argument-parsing logic testable independently (e.g., "does `--min-scene-len-frames` take priority over `--min-scene-len`" is a pure function of parsed args, testable without subprocesses) and keeps `cli/app.py`'s dispatch role honest — it cannot accidentally grow orchestration logic.
- **`legacy/` is not deleted as part of this restructuring** — it is the parity oracle. Delete or archive it only after each moved module has a passing behavior-parity check (see Migration Order).

## Architectural Patterns

### Pattern 1: Subprocess seam via call-through module (not constructor injection)

**What:** Instead of adding a `runner` parameter to every function that shells out (which would touch every call site's signature and risk subtly changing default behavior), route all `subprocess.run`/`subprocess.Popen` calls through two module-level functions in `enpipe.shared.proc`:

```python
# enpipe/shared/proc.py
import subprocess
from typing import List

def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)

def popen(cmd: List[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(cmd, **kw)
```

Every other module calls `proc.run(...)` / `proc.popen(...)` instead of `subprocess.run(...)` / `subprocess.Popen(...)`. Tests then do `monkeypatch.setattr(enpipe.shared.proc, "run", fake_run)` (or `unittest.mock.patch("enpipe.shared.proc.run")`) to substitute canned `CompletedProcess`/fake process objects, with **zero signature changes** to any existing function — this is the minimal-diff seam that satisfies "preserve current behavior exactly."

**When to use:** Every function that currently calls `ffprobe`/`ffmpeg`/`qsvencc`/`mkvmerge` — `probe_source`, `keyframes_in_window`, `find_boundary` (indirectly), `probe_fps`, `keyframe_table_ffprobe`, `detect_hdr`, `encode_chunk`, `count_frames`, `encode_audio`, the final `mkvmerge` call in `pipeline.run_encode`, and `QsvPipeStream._start_process`/`finish`.

**Trade-offs:** Monkeypatching a module attribute is slightly less explicit than constructor/parameter injection, but this codebase is function-oriented with no service/class layer (per `.planning/codebase/ARCHITECTURE.md`: "no object-oriented service layer"), so a call-through module matches the existing style and requires touching only call sites (`subprocess.run(` → `proc.run(`), not signatures. `encode_scenes.py` already has a local `run()` wrapper doing exactly this at file scope (line 66) — this pattern promotes that existing idiom to a shared, importable, mockable module rather than inventing a new one.

**Example test using the seam:**
```python
def test_probe_source_parses_ffprobe_json(monkeypatch):
    fake = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({
            "streams": [{"width": 1920, "height": 1080, "avg_frame_rate": "24000/1001"}],
            "format": {"duration": "120.5"},
        }).encode(),
    )
    monkeypatch.setattr(proc, "run", lambda cmd, **kw: fake)
    info = probe_source(Path("irrelevant.mkv"), DetectionConfig())
    assert info.width == 1920 and info.frame_rate == Fraction(24000, 1001)
```

### Pattern 2: Isolate the EBML/Cues parser behind a read/parse split

**What:** `keyframe_table_cues` today mixes file I/O (`src.stat()`, two `src.open("rb")` reads at different offsets) with pure byte-parsing (EBML element walking to find `SeekHead`→`Cues` position, then walking `Cues` body for `CuePoint`/`CueTime`/`CueTrackPositions`). Split it:

```python
# enpipe/mkv/ebml.py — pure, no file I/O, fully unit-testable with byte fixtures
def find_cues_position(head: bytes) -> Optional[tuple[int, int, int]]:
    """Walk EBML header + Segment + SeekHead/Info/Tracks to locate Cues.
    Returns (cues_pos, timestamp_scale, video_track_number) or None."""
    ...

def parse_cues_body(cues_bytes: bytes, video_track: int, scale: int,
                     fps: float) -> Optional[List[Tuple[int, float]]]:
    """Walk a Cues element body, return sorted (frame, pts_time) keyframe table."""
    ...

# enpipe/encoding/keyframes.py — the thin I/O shell, same public function name/signature
def keyframe_table_cues(src: Path, fps: float) -> Optional[List[Tuple[int, float]]]:
    head = src.open("rb").read(16_000_000)   # unchanged read pattern
    located = ebml.find_cues_position(head)
    if located is None:
        return None
    cues_pos, scale, vtrack = located
    cues_bytes = _read_cues_body(src, cues_pos)   # unchanged targeted read
    return ebml.parse_cues_body(cues_bytes, vtrack, scale, fps)
```

**When to use:** This is specifically what `PROJECT.md` calls out ("isolate the hand-rolled EBML/Cues parser behind a tested module boundary") and what `.planning/codebase/ARCHITECTURE.md`'s Anti-Patterns section flags as the top structural risk ("130+ lines of manual byte-offset arithmetic... no unit tests"). The split must preserve the exact fallback contract: any structural anomaly still returns `None` (never raises), so `keyframe_table()`'s caller still falls back to the slow ffprobe scan exactly as today.

**Trade-offs:** This is the one place in this milestone where "pure refactor" (extracting functions without changing logic) is worth doing proactively rather than deferring, because it is currently *impossible* to unit test without real or crafted `.mkv` binary fixtures at the full-file level. After the split, `find_cues_position`/`parse_cues_body` can be tested with a handful of small synthetic byte sequences (a few hundred bytes each, handcrafted EBML) covering: normal Cues, missing SeekHead, Cues past EOF, non-zero-based keyframe table, multiple tracks, corrupt/truncated element sizes — none of which require a real video file.

### Pattern 3: Extract correctness-critical math into pure, dependency-free functions

**What:** Two blocks of correctness-critical arithmetic are currently inlined inside larger I/O-heavy functions and should be pulled out as their own pure, directly-testable functions — with **no logic change**, only extraction:

1. **Seek/trim computation**, currently inline in `encode_scenes.py main()` (lines 581–589):
   ```python
   # enpipe/encoding/keyframes.py
   @dataclass(frozen=True)
   class ChunkPlan:
       seek: str
       trim: str
       kf_frame: int

   def compute_chunk_seek_trim(scene: Tuple[int, int],
                                table: List[Tuple[int, float]]) -> ChunkPlan:
       s, e = scene
       kf_frame, kf_time = kf_before(table, s)
       return ChunkPlan(seek=fmt_seek(kf_time), trim=f"{s - kf_frame}:{e - 1 - kf_frame}",
                         kf_frame=kf_frame)
   ```
   This is the exact rule documented in the encoder's module docstring ("K = последний keyframe источника с frame_K ≤ S; qsvencc --seek floor_ms(K) --trim (S−K):(E−1−K)") — currently verifiable only by reading a full `main()` run's log output. After extraction it gets a direct table-driven unit test (e.g., scene starting exactly on a keyframe, scene starting one frame after a keyframe, first scene at frame 0, empty/degenerate table).

2. **High-water-mark flush ordering**, currently a closure over `next_append`/`ready`/an open file handle (`flush_appends`, lines 608–617):
   ```python
   # enpipe/encoding/pipeline.py (or a new small module if reused)
   def contiguous_ready(next_append: int, ready: Dict[int, int]) -> Iterator[int]:
       """Yield indices to flush, in order, given current high-water mark."""
       i = next_append
       while i in ready:
           yield i
           i += 1
   ```
   The orchestration loop keeps doing the file I/O; the *decision* of which indices are safe to flush becomes a pure function tested with plain dicts (e.g., out-of-order completion `{2, 0, 1, 4}` → flush `[0, 1, 2]`, next_append becomes 3; `PIPELINE_DESIGN.md` already documents this exact pattern is slated for verbatim reuse by any future streaming consumer, so locking it under a unit test now also de-risks that future (out-of-scope) work).

**When to use:** Any time correctness depends on arithmetic/sequencing that is currently only exercised end-to-end through a real qsvencc/mkvmerge run. Per `PROJECT.md`'s Constraints ("Frame-count verification and keyframe-alignment invariants must be preserved through any refactor — silent output corruption is the primary risk"), these are exactly the functions that most need direct, fast, hardware-free tests.

**Trade-offs:** None functionally — these are behavior-preserving extractions (same expressions, moved to a named function and given a return type). The only cost is the extra module/import indirection, which is worth it given these are the two places `.planning/codebase/ARCHITECTURE.md` names explicitly as "correctness-by-construction" invariants.

## Data Flow

### Existing Flow (preserved unchanged by this restructuring)

```
enpipe detect <video>              enpipe encode <video> <video>.scenes
        │                                    │
        ▼                                    ▼
 detection.detect.detect_scenes    encoding.pipeline.run_encode
        │                                    │
        ▼                                    │
  <video>.scenes  (text file) ───────────────┘
        (THE ONLY COUPLING — unchanged format, unchanged content)
```

The restructuring must not add any direct Python import from `enpipe.encoding` to `enpipe.detection` (or vice versa) beyond both depending on `enpipe.shared`. If a future phase needs both stages in one process (the streaming orchestrator), that is a new, explicitly-scoped design — not a side effect of this packaging work.

### Key Data Flows (unchanged, now module-scoped)

1. **Detection:** `probe_source` → `QsvPipeStream` (ffmpeg subprocess pipe) → `AdaptiveDetector`/`SceneManager` → `List[Scene]` → CLI writes `<video>.scenes`. Same as `.planning/codebase/ARCHITECTURE.md` Data Flow, now split across `detection/{config,stream,detect,parallel}.py`.
2. **Encoding:** `read_scenes` → `keyframe_table` (Cues fast path via `mkv.ebml`, ffprobe fallback via `encoding.keyframes`) → `detect_hdr` → per-scene `compute_chunk_seek_trim` + `chunk_command` → `ThreadPoolExecutor` `encode_chunk` → high-water `contiguous_ready`-driven append into `movie.obu` → parallel `encode_audio` → `write_metrics_csv` → `mkvmerge` mux. Same as today, now split across `encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py`.

## Migration / Refactor Order

**Guiding rule:** every step below must leave the system runnable and behavior-identical to `legacy/*.py` at that point (verify by diffing `.scenes` output and final `.mkv`/`.metrics.csv` output against the legacy scripts on a real or synthetic sample before proceeding). Do not batch multiple steps into one commit if it can be avoided — the point of the ordering is a small, verifiable diff at each stage.

1. **Scaffold only.** Create `pyproject.toml` (recommend `hatchling` or `setuptools` build backend — either is fine per current `packaging.python.org` guidance; pick whichever has less config for a single-package `src/` layout), empty `src/enpipe/` package, `tests/` directory, pin known runtime deps (`scenedetect[opencv-headless]`, `numpy`) plus `pytest`. No code moved. Verify `pip install -e .` and `import enpipe` work. Zero behavior risk — nothing executes yet.

2. **Move detection first.** Split `legacy/scene_detection.py` into `detection/{config,stream,detect,parallel}.py` as a **mechanical** cut/paste (no logic changes yet). Add `cli/detect.py` reproducing the exact current argparse surface, wired to `detection.detect.detect_scenes`. Verify byte-identical `.scenes` output vs. the legacy script on a sample file. Rationale for going first: it's the smaller of the two scripts, has no dependents, and de-risks the "does the src-layout/console_script wiring even work" question before touching the more complex encoder.

3. **Introduce the `shared.proc` seam, applied to the newly-moved detection module.** Change `subprocess.run(...)`/`subprocess.Popen(...)` call sites in `detection/*` to `proc.run(...)`/`proc.popen(...)` — pure call-site substitution. Write the first unit tests here (`test_probe.py`, `test_stream.py` with a fake Popen) to prove out the seam pattern before replicating it into the larger encoder module.

4. **Move encoding, with the EBML parser split out first as its own sub-step.** Order within this step matters:
   - 4a. Extract `mkv/ebml.py` (read/parse split as described in Pattern 2) and write its byte-fixture test corpus. This is the single highest-debt item named in `PROJECT.md` — give it dedicated attention rather than folding it into a larger diff.
   - 4b. Extract `encoding/keyframes.py` (`kf_before`, `fmt_seek`, new `compute_chunk_seek_trim`) and unit test directly (no mocking needed — pure functions).
   - 4c. Mechanically move `hdr.py`, `chunk.py`, `audio.py`, `metrics.py`, applying the `proc.run` seam substitution as in step 3; the existing qsvencc/ffprobe stderr output formats documented in code comments (e.g. `SSIM YUV: ...`) are ready-made fixtures for `parse_metrics` tests.
   - 4d. Extract the pure `contiguous_ready` sequencing helper from `flush_appends` (Pattern 3) and unit test it standalone.
   - 4e. `encoding/pipeline.py` retains the orchestration as `run_encode(args)`, calling the above; `cli/encode.py` reproduces the exact argparse + env var surface.
   - Verify byte-identical `.mkv`/`.metrics.csv` output vs. `legacy/encode_scenes.py` on the same sample before proceeding.

5. **Add the unified `enpipe` console_script** (`cli/app.py`, `[project.scripts] enpipe = "enpipe.cli.app:main"`) with `detect`/`encode` subcommands dispatching to the already-verified `cli/detect.py`/`cli/encode.py`. This is dispatch-only wiring on top of already-proven code — lowest-risk step, do it after both stages are independently verified, not before.

6. **(Optional/last, may be a follow-up milestone) Dedupe `probe_source` vs `probe_fps`** into `shared/ffprobe.py`. Deliberately last: both functions now have direct test coverage from steps 3/4c, so any subtle behavioral difference between them (error-raise via `SceneDetectionError` vs. `sys.exit` via `die()`; different fallback key order) will be caught by existing tests rather than surfacing as a production regression. If it doesn't fit this milestone's budget, defer explicitly rather than rush it.

7. **Add the mandatory parallel-vs-sequential detection regression test** (named explicitly in `PROJECT.md` Active scope) as an integration test comparing `detect_scenes_parallel` against `detect_scenes` by `(start_frame, end_frame)` pairs on real media. This requires QSV hardware (the devcontainer), so mark it as an integration/hardware-gated test (`pytest.mark.integration` or similar), separate from the fast, hardware-free unit suite built in steps 3–4.

8. **Retire `legacy/`** only after every step above has a passing parity check — either delete it from the working tree or leave it as a frozen historical reference; do not delete it as part of an earlier step, since it is the parity oracle for every other step.

**Explicitly not part of this order:** reconciling the `ThreadPoolExecutor`-vs-`ProcessPoolExecutor` inconsistency in `detection.parallel` (flagged in `.planning/codebase/ARCHITECTURE.md` Architectural Constraints and `PROJECT.md` Active scope). The module-level worker functions (`_boundary_worker`, `_segment_worker`) are already structured pickle-safe for a `ProcessPoolExecutor`, so this is a low-effort follow-up — but swapping executor types changes concurrency/timing behavior (not output correctness, since the algorithm is unchanged and the workers are pure-ish), which is a different kind of change than pure packaging/testability work. Treat it as a separate, explicitly-scoped phase item, not a migration step to bundle in here.

## Anti-Patterns

### Anti-Pattern 1: Turning "unified entry point" into a fused runtime

**What people do:** Reading "package the two scripts... with a unified entry point" (`PROJECT.md` Active scope) as license to start wiring `detect` and `encode` together in-process (queues, threads spanning both stages), because `PIPELINE_DESIGN.md` already sketches exactly that.
**Why it's wrong:** The milestone context is explicit — "Do NOT design the streaming orchestrator (out of scope)" — and `PIPELINE_DESIGN.md`'s own verdict is not to build it on current hardware. Conflating "one CLI binary with subcommands" with "one fused pipeline process" would silently pull out-of-scope, higher-risk work into a milestone whose whole point is behavior preservation.
**Do this instead:** `enpipe`'s unified entry point is a **dispatch table only** — `cli/app.py` picks between `cli/detect.py:run()` and `cli/encode.py:run()`, each of which is otherwise unchanged from today's two independent scripts, still connected only by the `.scenes` file on disk.

### Anti-Pattern 2: Adding a `runner`/`CommandRunner` parameter to every subprocess-calling function

**What people do:** The "textbook" dependency-injection answer is to add an explicit `runner: Callable = subprocess.run` parameter to every function that shells out, so tests pass a fake runner as an argument.
**Why it's wrong:** This touches the signature of nearly every function in the codebase (`probe_source`, `keyframes_in_window`, `find_boundary`, `probe_fps`, `keyframe_table_ffprobe`, `detect_hdr`, `encode_chunk`, `count_frames`, `encode_audio`, `chunk_command`'s caller, the final mux call) for a milestone whose success criterion is "preserve current behavior exactly" — larger signature surface area means larger risk of an accidental default-value or call-site mismatch during the mechanical move.
**Do this instead:** Route all calls through the two `shared.proc` functions (Pattern 1) and mock at the module-attribute level (`monkeypatch.setattr` / `unittest.mock.patch`). Zero signature changes; the seam lives at the import boundary instead of the parameter list.

### Anti-Pattern 3: Treating the EBML parser move as a routine "cut into a file" step

**What people do:** Since most of this migration is mechanical (move function, add import), it's tempting to treat `keyframe_table_cues` the same way — cut it into `mkv/ebml.py` verbatim, done.
**Why it's wrong:** `.planning/codebase/ARCHITECTURE.md`'s own Anti-Patterns section already flags this code as "significant unencapsulated complexity... with no unit tests"; moving it verbatim into a new file changes its *location* but not its *testability*, which is the actual goal `PROJECT.md` names ("isolate... behind a **tested** module boundary" — emphasis on tested, not just moved).
**Do this instead:** Apply the read/parse split (Pattern 2) so the byte-parsing logic can be unit tested with small synthetic fixtures, independent of real `.mkv` files or the filesystem.

## Integration Points

### External Tools (unchanged by this restructuring)

| Tool | Integration Pattern | Notes |
|------|---------------------|-------|
| `ffmpeg`/`ffprobe` | `subprocess.run`/`Popen` via `shared.proc`, invoked by `detection.stream`, `detection.parallel`, `encoding.keyframes`, `encoding.hdr`, `encoding.chunk`, `encoding.audio` | No wrapper library (e.g. `ffmpeg-python`) — keep raw `subprocess` + `shared.proc`, matching current style |
| `qsvencc` (Rigaya QSVEnc) | `subprocess.run` via `shared.proc`, invoked by `encoding.chunk.encode_chunk` | Hard dependency, no software-encode fallback (per `PROJECT.md` Constraints) |
| `mkvmerge` | `subprocess.run` via `shared.proc`, invoked by `encoding.pipeline.run_encode` final mux step | Return code 1 (warnings) is treated as success, same as today — preserve this check exactly |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `enpipe.detection` ↔ `enpipe.encoding` | `<video>.scenes` text file only (no direct import) | This is the existing, deliberate architecture — preserve it; do not add a direct Python call path between the two packages as part of this milestone |
| `enpipe.encoding.pipeline` ↔ `enpipe.mkv.ebml` | Direct Python import (new — currently inline in the same file) | One-directional; `mkv` package has no knowledge of `encoding` |
| `cli/*` ↔ `detection`/`encoding` | Direct Python import, thin argparse-to-function-call wiring | `cli/` modules contain no orchestration logic of their own |
| Any module ↔ `shared.proc` | Direct Python import, called at every subprocess invocation site | The sole testing seam; see Pattern 1 |

## Sources

- [Writing your pyproject.toml — Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) — HIGH confidence, official/current
- [src layout vs flat layout — Python Packaging User Guide](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) — HIGH confidence, official/current; basis for the `src/` layout recommendation
- [Creating and packaging command-line tools — Python Packaging User Guide](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) — HIGH confidence, official/current; basis for `[project.scripts]` console_script recommendation
- [pytest-subprocess (PyPI)](https://pypi.org/project/pytest-subprocess/) and [testfixtures MockPopen docs](https://testfixtures.readthedocs.io/en/latest/popen.html) — MEDIUM confidence, community-verified patterns; informed the choice of a simple call-through module (`shared.proc`) over a heavier mocking framework, since the codebase's existing local `run()` wrapper in `encode_scenes.py:66` already demonstrates the same idiom without external dependencies
- `legacy/scene_detection.py`, `legacy/encode_scenes.py` (this repository) — HIGH confidence, primary source for all function/module boundaries, line references, and behavior descriptions in this document
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/PROJECT.md` (this repository) — HIGH confidence, authoritative project context

---
*Architecture research for: packaging a subprocess-orchestration media pipeline into a testable Python package*
*Researched: 2026-07-08*
