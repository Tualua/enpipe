# Phase 7: Backend Seam Refactor (zero behavior change) - Research

**Researched:** 2026-07-23
**Domain:** Internal Python package refactor — extracting a backend seam (frozen-dataclass value object) from existing correctness-critical encode code, with zero behavior change verified against a frozen legacy oracle. No new external libraries.
**Confidence:** HIGH (all findings verified by direct reading of the actual current source and test files in this repository, not generic advice)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Backend contract shape (the seam)**
- **D-01:** A backend is a `@dataclass(frozen=True)` value object bundling pure, argv-testable callables plus metadata — the full contract: `build_command` callable, `parse_metrics` callable, metadata (`name`, required preflight tool(s), capability flags e.g. `supports_metrics`).
- **D-02:** `encode_chunk` becomes backend-generic — delegates argv construction and metrics parsing to the resolved backend object. `count_frames` stays shared (format-agnostic).
- **D-03:** New `backends/` package: `backends/__init__.py` (registry + resolve function), `backends/base.py` (frozen-dataclass backend type), `backends/qsvencc.py` (owns `chunk_command`, `parse_metrics`, preset constants `ICQ`/`QPMAX`/`GOP_LEN`, plus its tool name). `encoding/chunk.py` shrinks to generic `encode_chunk` + shared `count_frames`. Code moves **verbatim** (no logic edits during the move).

**Seek/trim sharing (SC#4)**
- **D-04:** Extract a numeric core as the single source of the keyframe derivation, in `keyframes.py`: `compute_chunk_seek_trim_numeric(table, s, e) -> (kf_frame, kf_time, start_off, end_off)`. qsvencc's string formatting (`fmt_seek` + `"{start_off}:{end_off}"`) becomes a thin wrapper over this core and moves into `backends/qsvencc.py`. No duplicated derivation. Phase 8's ffmpeg backend formats the same numeric record its own way.

**`--backend` scaffold & strictness**
- **D-05:** Resolution precedence: flag > env > default (`qsvencc`). Resolved backend object threads through `run_encode` / `encode_chunk`.
- **D-06:** Registry contains only `qsvencc` this phase. Any `--backend`/env value not in the registry is rejected at resolve time with a clear error message listing valid backends. ffmpeg is not registered (no stub, no dead build_command).
- **D-07:** Env var is the bare name `BACKEND`, read via `os.environ.get` with a typed default constant, matching the established convention (`JOBS`, `ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`).
- **D-08 (scaffold surface):** Add `--backend` to the `encode` and `run` subparsers, defaulting from the `BACKEND` env constant.

**Zero-behavior-change parity gate**
- **D-09:** Golden argv snapshots (fast tier). Snapshot current `chunk_command` argv across SDR/HDR10/HDR10+/DV × representative scenes (incl. a `first>0` chunk), commit as fixtures. Fast hardware-free test asserts the qsvencc backend reproduces the golden argv byte-for-byte on every push.
- **D-10:** On-Arc byte-identity (hardware tier). Pre-mux `movie.obu` verified byte-identical to pre-refactor output against the legacy oracle on real Arc hardware (satisfies SC#2), in the existing hardware-gated tier.

### Claude's Discretion
- Exact registry data structure (dict vs mapping helper) and the `resolve()` signature.
- Precise `base.py` dataclass field names and the full capability-flag set.
- The `build_command` signature detail (how it receives the numeric seek/trim record + src/out/hdr_flags/metrics).
- Golden-fixture file format and location under the test tree; the exact permutation matrix rows (must include SDR, HDR10, HDR10+, DV, and a `first>0` chunk).

### Deferred Ideas (OUT OF SCOPE)
- The actual ffmpeg `av1_qsv` backend (`backends/ffmpeg.py`, registration, default flip) — explicitly Phase 8 (FF-01/02/03, BK-01).
- HDR10 static-metadata routing (Phase 9) and DV/HDR10+ decision (Phase 10) — later phases.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| BK-02 | Both encode backends live behind a shared `backends/` seam that keeps each backend's command-builder a pure, argv-testable function; the qsvencc backend stays byte-identical to the pre-refactor output (legacy-oracle parity preserved, zero behavior change). | See "Architecture Patterns" (target `backends/` layout + exact move map), "Code Examples" (verified current signatures + target wrappers), "Common Pitfalls" (dangling-import inventory — every current call site of every symbol being moved), and "Common Pitfalls" (existing `test_sdr_legacy_oracle_parity` hardware test already implements the D-10 byte-identity check end-to-end through the public CLI, so it should keep passing unmodified if the CLI-level argv/behavior is truly unchanged). |
</phase_requirements>

## Summary

This phase is a pure code-relocation exercise on a small, already-well-tested surface (`src/enpipe/encoding/chunk.py`, `keyframes.py`, `pipeline.py`, `cli/main.py`). Every symbol that must move has exactly one production call site (`pipeline.py`) plus several test-file import sites, all enumerated below with file:line anchors. There is no new external dependency, no new subprocess call, and no new algorithm — the entire risk is mechanical: (1) leaving a stale import that raises `ImportError`/`AttributeError` at collection or run time, (2) silently changing the qsvencc argv or the tool-preflight order while splitting `chunk_command`'s pure-string-formatting arguments away from the newly-introduced numeric seek/trim core, and (3) breaking the `argparse.Namespace`-passing convention this codebase uses everywhere (`run_encode(args)`, `_pipeline_one`'s hand-built Namespaces) by forgetting to thread a new `args.backend` attribute through every Namespace-construction site.

The codebase already has the exact scaffolding this phase needs: a "fast" hardware-free tier (`tests/unit/*`, `tests/subprocess/*`, pytest marker default `-m "not hardware"`) and a hardware-gated tier (`tests/integration/*`, `pytest.mark.hardware`) with an existing `test_sdr_legacy_oracle_parity` test that already runs the frozen `legacy/encode_scenes.py` oracle side-by-side with the enpipe CLI and byte-compares `movie.obu` — this is functionally the D-10 test already, just needs re-running (unmodified) post-refactor as regression proof, since it drives the pipeline only through the public `enpipe` CLI entry points.

**Primary recommendation:** Do the move in this literal order to minimize breakage risk: (1) add `compute_chunk_seek_trim_numeric` to `keyframes.py` beside the existing `compute_chunk_seek_trim`/`fmt_seek`/`kf_before` (additive, non-breaking); (2) create `backends/base.py` + `backends/__init__.py` (additive, no existing import touched yet); (3) create `backends/qsvencc.py`, moving `chunk_command`, `parse_metrics`, `ICQ`/`QPMAX`/`GOP_LEN`, and `fmt_seek` into it verbatim, plus a new 2-line `build_command`/`compute_chunk_seek_trim` wrapper over the numeric core; (4) update `pipeline.py`'s imports and the 5 call sites (preflight loop, log line, chunk-task loop, `encode_chunk` call, `count_frames` call — the last two unchanged) to route through the resolved backend; (5) update `cli/main.py` to add `--backend` to `encode`/`run` and thread `args.backend` through `_pipeline_one`'s hand-built encode Namespace; (6) fix every test import (enumerated below) last, running `pytest -m "not hardware"` after each step to catch breakage immediately rather than at the end.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Backend contract type (`Backend` frozen dataclass) | Library / pure-logic (`backends/base.py`) | — | Value object, no I/O, no subprocess — same tier as `Scene`/`DetectionConfig` |
| Backend registry + resolution (flag>env>default) | Library / pure-logic (`backends/__init__.py`) | CLI (argparse default wiring) | Resolution logic itself is pure (string lookup); only the argparse default read (`os.environ.get`) touches process env |
| qsvencc argv construction (`chunk_command`) | Library / pure-logic (`backends/qsvencc.py`) | — | Pure string-list builder, no subprocess — proven pattern already (existing `chunk_command` calls no subprocess) |
| qsvencc metrics parsing (`parse_metrics`) | Library / pure-logic (`backends/qsvencc.py`) | — | Pure regex over a string, no I/O |
| Numeric seek/trim derivation | Library / pure-logic (`encoding/keyframes.py`) | — | Backend-agnostic arithmetic over an in-memory keyframe table; shared by all future backends per D-04 |
| Chunk subprocess execution + frame-count verification (`encode_chunk`, `count_frames`) | Backend-generic orchestration (`encoding/chunk.py`) | Subprocess seam (`shared/proc.py`) | Delegates argv/metrics to the backend object but itself stays format-agnostic; the actual `subprocess.run` call is one tier down in `shared/proc.py` |
| Encode orchestration (`run_encode`) | Orchestration / CLI-adjacent (`encoding/pipeline.py`) | — | Threads the resolved backend through chunk-task assembly; unchanged threading/ordering logic |
| `--backend` flag / env resolution entry point | CLI (`cli/main.py`) | — | argparse surface only; all resolution logic itself lives in `backends/__init__.py` |

## Standard Stack

No new external dependencies. This phase is an internal restructuring of existing first-party code (`stdlib` `dataclasses`, `os`, `re` — already used).

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `dataclasses` (stdlib) | 3.12 | `@dataclass(frozen=True)` backend value-object | Exact precedent already established by `Scene`/`DetectionConfig` in `src/enpipe/detection/config.py:25,50` [VERIFIED: codebase grep] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Plain dict `Dict[str, Backend]` registry in `backends/__init__.py` | `importlib.metadata` entry-point plugin discovery | Overkill for 1-2 first-party backends (D-06 explicitly registers only `qsvencc` this phase); a dict is simpler, is fully static-analyzable, and matches the codebase's "no framework, function-oriented" convention noted in `.planning/codebase/ARCHITECTURE.md` |
| `os.environ.get("BACKEND", "qsvencc")` module constant | A typed `Settings`/config class | `CFG-01` (typed config/Settings layer) is explicitly deferred to v2 per `.planning/REQUIREMENTS.md`; the env-cast-constant pattern (`ICQ = int(os.environ.get("ICQ", "23"))`) is this codebase's established convention, not to be replaced mid-refactor |

**Installation:** None — no `pyproject.toml` change needed for this phase.

## Package Legitimacy Audit

Not applicable — this phase installs zero external packages. All work is internal module relocation of existing first-party code plus new first-party glue (`backends/base.py`, `backends/__init__.py`, `backends/qsvencc.py`, `keyframes.compute_chunk_seek_trim_numeric`).

## Architecture Patterns

### System Architecture Diagram (target state, this phase)

```text
                         cli/main.py
                    (encode_p/run_p subparsers)
                 args.backend: Optional[str] ────────┐
                                                       │
                                                       ▼
                                          backends/__init__.py
                                          resolve(flag, env) -> Backend
                                          (flag > env > BACKEND env > "qsvencc" default;
                                           unknown name -> raise, caller die()s)
                                                       │
                                                       ▼
                            encoding/pipeline.py :: run_encode(args)
   ┌── preflight: shared tools (ffprobe/ffmpeg/mkvmerge)
   │            + backend.required_tools (e.g. ("qsvencc",))
   │
   ├── keyframe_table(video, fps)  [UNCHANGED — keyframes.py]
   │        │
   │        ▼  per scene (s, e):
   │   compute_chunk_seek_trim_numeric(table, s, e)
   │        -> (kf_frame, kf_time, start_off, end_off)   [NEW — keyframes.py, backend-agnostic]
   │        │
   │        ▼
   │   backend.build_command(src, kf_frame, kf_time, start_off, end_off,
   │                          out, hdr_flags, metrics) -> List[str]
   │        │                                             (backends/qsvencc.py:
   │        │                                              formats seek/trim strings,
   │        │                                              then calls chunk_command
   │        │                                              VERBATIM, unchanged args)
   │        ▼
   ├── ThreadPoolExecutor(JOBS).submit(encode_chunk, task, backend)
   │        │                          (encoding/chunk.py — now backend-generic:
   │        │                           runs cmd via shared/proc.run, calls
   │        │                           backend.parse_metrics(stdout+stderr),
   │        │                           calls shared count_frames)
   │        ▼
   ├── high-water-mark ordered append -> movie.obu   [UNCHANGED]
   ├── count_frames(movie)  [UNCHANGED — shared, encoding/chunk.py]
   └── mkvmerge mux  [UNCHANGED]
```

### Recommended Project Structure (additions only)

```
src/enpipe/
├── backends/
│   ├── __init__.py      # registry (dict) + resolve(name_from_flag, env) -> Backend
│   ├── base.py           # @dataclass(frozen=True) Backend value object
│   └── qsvencc.py        # chunk_command (verbatim move), parse_metrics (verbatim move),
│                          # ICQ/QPMAX/GOP_LEN (verbatim move), fmt_seek (verbatim move),
│                          # build_command (NEW thin wrapper), QSVENC_BACKEND instance
├── encoding/
│   ├── chunk.py           # SHRINKS: keeps encode_chunk (now backend-generic) + count_frames
│   │                      # only; chunk_command/parse_metrics/ICQ/QPMAX/GOP_LEN REMOVED
│   ├── keyframes.py       # keeps kf_before/keyframe_table*/compute_chunk_seek_trim_numeric (NEW);
│   │                      # fmt_seek REMOVED (moved to backends/qsvencc.py)
│   └── pipeline.py        # imports Backend resolution, threads backend through run_encode
└── cli/main.py            # --backend added to encode_p/run_p; _pipeline_one threads args.backend
```

### Pattern 1: Backend as a frozen-dataclass value object (D-01)
**What:** A `Backend` value object bundling pure callables + metadata, mirroring the existing `Scene`/`DetectionConfig` convention exactly.
**When to use:** Any time a "family of interchangeable strategies" needs to be threaded through orchestration code without introducing a class hierarchy (this codebase has zero classes beyond dataclasses and one adapter, per `.planning/codebase/ARCHITECTURE.md`'s "No object-oriented service layer" note).
**Example (recommended shape — Claude's Discretion on exact field names, per CONTEXT.md):**
```python
# src/enpipe/backends/base.py
"""Контракт бэкенда энкодера: неизменяемый value-объект, объединяющий чистые,
argv-тестируемые колбэки + метаданные. Тот же паттерн, что Scene/DetectionConfig
(enpipe.detection.config) -- см. ARCHITECTURE.md D-01."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple


@dataclass(frozen=True)
class Backend:
    name: str
    build_command: Callable[
        [Path, int, float, int, int, Path, List[str], bool], List[str]
    ]
    parse_metrics: Callable[[str], dict]
    required_tools: Tuple[str, ...]
    supports_metrics: bool = True
```
```python
# src/enpipe/backends/qsvencc.py (excerpt — verbatim-moved pieces + new wrapper)
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

from enpipe.backends.base import Backend
from enpipe.encoding.keyframes import compute_chunk_seek_trim_numeric

# --- verbatim move from encoding/chunk.py:21-23 --- #
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))


def fmt_seek(t: float) -> str:
    """Verbatim move from encoding/keyframes.py:101-111 -- unchanged body."""
    ms = int(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
    """Verbatim move from encoding/chunk.py:26-42 -- unchanged body, unchanged argv."""
    cmd = [
        "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
        "--icq", str(ICQ), "--qp-max", str(QPMAX),
        "--output-depth", "10", "--profile", "main",
        "--gop-len", str(GOP_LEN), "--gop-ref-dist", "6", "--b-pyramid",
        "--tile-col", "1", "--tile-row", "1",
        "--tune", "perceptual", "--scenario-info", "archive",
        "--colorrange", "auto", "--colormatrix", "auto", "--colorprim", "auto",
        "--transfer", "auto", "--chromaloc", "auto",
        *hdr_flags,
    ]
    if metrics:
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd


def build_command(src: Path, kf_frame: int, kf_time: float, start_off: int,
                   end_off: int, out: Path, hdr_flags: List[str],
                   metrics: bool) -> List[str]:
    """NEW thin wrapper (D-04) -- formats the backend-agnostic numeric record
    into qsvencc's seek/trim string convention, then calls chunk_command
    verbatim. This is the ONLY new logic in the qsvencc backend module; it
    reproduces exactly compute_chunk_seek_trim's old formula
    (encoding/keyframes.py:114-122)."""
    seek = fmt_seek(kf_time)
    trim = f"{start_off}:{end_off}"
    return chunk_command(src, seek, trim, out, hdr_flags, metrics)


# --- verbatim move from encoding/chunk.py:45-63 --- #
_SSIM_RE = re.compile(
    r"SSIM\s+YUV:\s*([\d.]+)\s*\([\d.]+\),.*?All:\s*([\d.]+)\s*\(([\d.]+)\)", re.I)
_PSNR_RE = re.compile(r"PSNR\s+YUV:\s*([\d.]+),.*?Avg:\s*([\d.]+)", re.I)


def parse_metrics(output: str) -> dict:
    m = {"ssim_y": None, "ssim_all": None, "ssim_db": None,
         "psnr_y": None, "psnr_avg": None}
    s = _SSIM_RE.search(output)
    if s:
        m["ssim_y"], m["ssim_all"], m["ssim_db"] = (
            float(s.group(1)), float(s.group(2)), float(s.group(3)))
    p = _PSNR_RE.search(output)
    if p:
        m["psnr_y"], m["psnr_avg"] = float(p.group(1)), float(p.group(2))
    return m


QSVENC_BACKEND = Backend(
    name="qsvencc",
    build_command=build_command,
    parse_metrics=parse_metrics,
    required_tools=("qsvencc",),
    supports_metrics=True,
)
```
```python
# src/enpipe/backends/__init__.py
from __future__ import annotations

import os
from typing import Dict, Optional

from enpipe.backends.base import Backend
from enpipe.backends.qsvencc import QSVENC_BACKEND

BACKEND = os.environ.get("BACKEND", "qsvencc")   # D-07: bare env-var name

_REGISTRY: Dict[str, Backend] = {"qsvencc": QSVENC_BACKEND}


def resolve(flag_value: Optional[str]) -> Backend:
    """flag > env > default (D-05). Raises ValueError on an unknown name
    (D-06) -- caller (CLI/run_encode) converts to die() for user-facing
    consistency with the rest of this codebase's error handling; resolve()
    itself stays a plain function so unit tests can assert-raises without
    catching SystemExit (matches this codebase's existing split between
    pure/testable logic and die()-based CLI surfacing)."""
    name = flag_value or BACKEND
    try:
        return _REGISTRY[name]
    except KeyError:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"неизвестный backend {name!r}; допустимые: {valid}") from None
```

### Pattern 2: Numeric/formatting split for seek-trim (D-04)
**What:** `compute_chunk_seek_trim_numeric` in `keyframes.py` is the single backend-agnostic source of truth; qsvencc's `compute_chunk_seek_trim`-shaped string formatting becomes a thin wrapper living in the backend module.
**Verified current formula (`encoding/keyframes.py:114-122`):**
```python
def compute_chunk_seek_trim(table, s: int, e: int) -> Tuple[str, str]:
    kf_frame, kf_time = kf_before(table, s)
    seek = fmt_seek(kf_time)
    trim = f"{s - kf_frame}:{e - 1 - kf_frame}"
    return seek, trim
```
**Target split:**
```python
# encoding/keyframes.py (stays here — pure numeric, backend-agnostic, no fmt_seek import)
def compute_chunk_seek_trim_numeric(
    table: List[Tuple[int, float]], s: int, e: int
) -> Tuple[int, float, int, int]:
    """Numeric keyframe derivation shared by every backend (D-04). Returns
    (kf_frame, kf_time, start_off, end_off) -- kf_frame/kf_time are the
    chosen source keyframe; start_off = s - kf_frame, end_off = e - 1 -
    kf_frame are the trim offsets relative to that keyframe. Extracted
    verbatim from the old compute_chunk_seek_trim's arithmetic
    (keyframes.py:119-121, unchanged from Phase 2's DEBT-02 extraction) --
    only the STRING formatting (fmt_seek + f"{s}:{e}") moved out, into
    backends/qsvencc.py, since it is qsvencc-specific."""
    kf_frame, kf_time = kf_before(table, s)
    start_off = s - kf_frame
    end_off = e - 1 - kf_frame
    return kf_frame, kf_time, start_off, end_off
```
This is arithmetically identical to today's code — `fmt_seek(kf_time)` and `f"{start_off}:{end_off}"` in the qsvencc wrapper reproduce the exact same two strings the old `compute_chunk_seek_trim` returned. **No duplicated derivation, no logic change** — verified by direct comparison against `keyframes.py:114-122`.

### Pattern 3: Backend-generic `encode_chunk` (D-02)
**Verified current signature (`encoding/chunk.py:74-89`):**
```python
def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    ...
```
**Target (backend-generic — recommended shape; Claude's Discretion per CONTEXT on exact call convention):**
```python
def encode_chunk(task, backend: "Backend") -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **backend.parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    ...  # rest unchanged: count_frames(out), size stat, mismatch check
```
Pass `backend` as an explicit second positional argument to `ThreadPoolExecutor.submit(encode_chunk, task, backend)` rather than embedding it in the `task` tuple — the `task` tuple (`idx, cmd, out, expect`) is already constructed once per chunk and consumed by both `encode_chunk` and the log/CSV code in `pipeline.py`'s completion loop (`pipeline.py:243-264`); adding the backend object to every tuple element is unnecessary indirection when a single `backend` value is constant across the whole run. `count_frames` is called internally by `encode_chunk` unchanged (it stays in `encoding/chunk.py`, shared).

## Common Pitfalls

### Pitfall 1: Dangling imports — every current call site of every moved symbol (the top mechanical risk this phase)
**What goes wrong:** A verbatim code move that misses updating even one import line raises `ImportError` at collection time (breaks the entire fast test tier) or `NameError`/`AttributeError` at runtime (breaks only the specific call path — worse, because it may not be caught until the hardware tier runs).
**Complete inventory of production call sites (verified by grep, no import site missed):**

| Moved/renamed symbol | Origin (verbatim, file:line) | New home | Every current importer/caller |
|---|---|---|---|
| `chunk_command` | `encoding/chunk.py:26-42` | `backends/qsvencc.py` | `encoding/pipeline.py:35` (import), `:208` (call) |
| `parse_metrics` | `encoding/chunk.py:53-63` | `backends/qsvencc.py` | `encoding/chunk.py` itself (`encode_chunk`'s internal call, becomes `backend.parse_metrics`) |
| `ICQ`, `QPMAX`, `GOP_LEN` | `encoding/chunk.py:21-23` | `backends/qsvencc.py` | `encoding/pipeline.py:35` (import), `:175-176` (log line f-string) |
| `fmt_seek` | `encoding/keyframes.py:101-111` | `backends/qsvencc.py` | `encoding/keyframes.py`'s own `compute_chunk_seek_trim` (removed), `tests/integration/test_hardware_real_media.py:59,220` (import + call — see Pitfall 2) |
| `compute_chunk_seek_trim` (old 2-tuple string-returning form) | `encoding/keyframes.py:114-122` | Becomes qsvencc's `build_command` wrapper in `backends/qsvencc.py` (new name/shape) OR kept as a same-named thin wrapper in `backends/qsvencc.py` for backward-compatible call sites | `encoding/pipeline.py:37` (import), `:205` (call — MUST become the numeric core call instead); `tests/unit/encoding/test_keyframes.py:13,45-58` (imports + 3 tests); `tests/unit/encoding/test_pipeline_wiring.py:18` (import as reference oracle in the wiring test, `:87-88` call); `tests/integration/test_hardware_real_media.py:59` (import), `:213` (call) |
| `count_frames` | `encoding/chunk.py:66-71` | **STAYS** in `encoding/chunk.py` (D-02, shared/format-agnostic) | `encoding/chunk.py`'s `encode_chunk` (internal), `encoding/pipeline.py:35` (import), `:282` (call); `tests/subprocess/encoding/test_chunk.py:10` (import); `tests/integration/test_hardware_real_media.py:56` (import) |
| `encode_chunk` | `encoding/chunk.py:74-89` | **STAYS** in `encoding/chunk.py`, signature gains `backend` param (D-02) | `encoding/pipeline.py:35` (import), `:241` (submit call — gains second arg); `tests/subprocess/encoding/test_chunk.py:10` (import, 3 tests at lines 28,42,52 all call `encode_chunk((idx, cmd, out, expect))` with **no backend arg** — these WILL break unless updated to pass a backend, e.g. the real `QSVENC_BACKEND` or a stub `Backend`) |

**Test-file import sites requiring updates (enumerated, not "some tests"):**
1. `tests/unit/encoding/test_chunk.py` — imports `from enpipe.encoding import chunk` and `from enpipe.encoding.chunk import chunk_command, parse_metrics`; also does `monkeypatch.setattr(chunk, "ICQ", 30)` (line 39). After the move, `chunk_command`/`parse_metrics`/`ICQ` no longer exist in `enpipe.encoding.chunk` — this entire file's target module changes to `enpipe.backends.qsvencc` (or the file itself should relocate to a new `tests/unit/backends/test_qsvencc.py`, consistent with the "test file lives next to the module it tests" convention already used everywhere else in this repo, e.g. `mkv/ebml.py` -> `tests/unit/mkv/test_ebml.py` per Phase 2's DEBT-01 precedent).
2. `tests/subprocess/encoding/test_chunk.py` — imports `count_frames, encode_chunk`; both stay in `enpipe.encoding.chunk`, but the 3 `encode_chunk(...)` calls (lines 38, 46, 62) need a `backend` argument added once `encode_chunk`'s signature changes.
3. `tests/unit/encoding/test_keyframes.py` — imports `compute_chunk_seek_trim, fmt_seek, kf_before` from `enpipe.encoding.keyframes`; `fmt_seek` and the string-returning `compute_chunk_seek_trim` no longer live there post-move. `kf_before` stays. The 2 `fmt_seek` tests and 3 `compute_chunk_seek_trim` tests need to either move to a new `tests/unit/backends/test_qsvencc.py` (testing the qsvencc wrapper) or be replaced with tests of the new `compute_chunk_seek_trim_numeric` (numeric-only assertions, no string formatting) plus separate qsvencc-wrapper tests.
4. `tests/unit/encoding/test_pipeline_wiring.py` — imports `chunk_command as _real_chunk_command` from `enpipe.encoding.chunk` (line 17) and `compute_chunk_seek_trim` from `enpipe.encoding.keyframes` (line 18); both import paths change. This file also does `monkeypatch.setattr(p, "chunk_command", ...)`, `monkeypatch.setattr(p, "count_frames", ...)`, `monkeypatch.setattr(p, "encode_chunk", ...)` where `p` is the `enpipe.encoding.pipeline` module object — these monkeypatches target **names bound in `pipeline.py`'s own namespace** (re-exported via `from .chunk import ...`), so they will silently stop having any effect if `pipeline.py` no longer imports a symbol under that exact name (e.g. once `pipeline.py` calls `backend.build_command(...)` instead of a module-level `chunk_command(...)`, `monkeypatch.setattr(p, "chunk_command", ...)` patches a name pipeline.py never reads — the test would pass for the wrong reason, silently not exercising the mock). **This is the highest-value re-verification point after the refactor**: re-read this test file's monkeypatch targets against the new `pipeline.py` body and rewrite them to patch what `pipeline.py` actually calls (e.g. `monkeypatch.setattr(p, "backend", <fake Backend with a spy build_command>)` or patch the resolved backend's `build_command` attribute directly).
5. `tests/integration/test_hardware_real_media.py` — imports `compute_chunk_seek_trim, fmt_seek, kf_before, keyframe_table, keyframe_table_ffprobe` from `enpipe.encoding.keyframes` (lines 58-64) and `count_frames` from `enpipe.encoding.chunk` (line 56). `kf_before`/`keyframe_table`/`keyframe_table_ffprobe`/`count_frames` stay put; `compute_chunk_seek_trim`/`fmt_seek` import paths must change to `enpipe.backends.qsvencc` (or this ground-truth-verification helper (`_verify_frame_counts_and_keyframes`, lines 141-220) should be rewritten to call `compute_chunk_seek_trim_numeric` directly and format with the moved `fmt_seek`, whichever keeps the independent-ground-truth check meaningful — this file's checks are explicitly designed to be non-tautological (opencode H2 comment, line 155-163), so prefer importing the numeric core and re-deriving the formatted string locally rather than importing the qsvencc backend's private wrapper into an integration test that is meant to stay backend-agnostic in spirit).

### Pitfall 2: Tool-preflight order must stay identical for `die()` message reproducibility
**What goes wrong:** `run_encode`'s preflight loop (`encoding/pipeline.py:107-109`, `for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge")`) and the duplicate loop in `cli/main.py::run_pipeline` (`cli/main.py:88-90`, same 4-tuple) both check tools in a fixed order and `die()` on the **first** missing one. Once the qsvencc-specific tool name becomes `backend.required_tools`, the combined check (e.g. `(*backend.required_tools, "ffprobe", "ffmpeg", "mkvmerge")` vs `("ffprobe", "ffmpeg", "mkvmerge", *backend.required_tools)`) determines which tool's name appears in the die() message when multiple tools are simultaneously missing.
**Why it happens:** Zero-behavior-change means byte-identical stdout/stderr too, not just the produced `.mkv`/`.obu` — an easy detail to overlook when refactoring "just the seam."
**How to avoid:** Keep `backend.required_tools` **first** in the concatenated preflight tuple (matching today's literal ordering, where `"qsvencc"` is listed first), i.e. `(*backend.required_tools, "ffprobe", "ffmpeg", "mkvmerge")`. Both `run_encode` and `run_pipeline` must be updated in sync (they currently duplicate this exact 4-tuple independently — `encoding/pipeline.py:107` and `cli/main.py:88` — do not update only one).
**Warning signs:** Any test asserting the exact `die()` message text on a missing-tool path (none currently exist per the test inventory above, but a future test might).

### Pitfall 3: `argparse.Namespace` attribute completeness across every hand-built Namespace site (D-08 threading risk)
**What goes wrong:** This codebase constructs `argparse.Namespace` objects by hand in several places instead of always going through `parser.parse_args()`: `cli/main.py::_pipeline_one` builds a fresh `encode_args = argparse.Namespace(video=..., scenes=..., out=..., ..., csv=args.csv)` (lines 59-72) that is passed to `run_encode`. If `--backend` is added to the `encode`/`run` subparsers (D-08) but `_pipeline_one`'s hand-built `encode_args` Namespace is not also given a `backend=args.backend` field, `run_encode(encode_args)` will raise `AttributeError: 'Namespace' object has no attribute 'backend'` the first time it tries to resolve the backend — but ONLY on the `enpipe run` code path (single-file and batch), not on the direct `enpipe encode` path (which always goes through `parser.parse_args()` and therefore always has every declared attribute). This asymmetry means a naive test of `enpipe encode --backend qsvencc` could pass while `enpipe run` silently breaks.
**Why it happens:** `test_cli_run.py::test_namespace_non_contamination` (`tests/unit/cli/test_cli_run.py:136`) already exists specifically because this codebase has been bitten by this class of bug before (per the module's own comment at `cli/main.py:39-40`: "Namespace-поля НЕ переименовывать -- test_cli_run.py проверяет их поимённо").
**How to avoid:** When adding `--backend` to `encode_p`/`run_p` in `cli/main.py::build_parser`, also add `backend=args.backend` to `_pipeline_one`'s `encode_args` Namespace construction (line ~68) in the same commit/task, and add a new `test_cli_run.py`-style test asserting the `backend` field is present and correctly routed on the `enpipe run` path (mirroring the existing pattern at `test_cli_run.py:66` `test_encode_routing`).
**Warning signs:** Any `AttributeError` surfacing only through `enpipe run`, never through direct `enpipe encode` — a signature of exactly this Namespace-completeness gap.

### Pitfall 4: The `resolve()` function's error path must not raise `SystemExit` directly
**What goes wrong:** If `backends.resolve()` calls `die()` (which does `sys.exit`) internally on an unknown backend name, unit tests that want to assert "resolving an invalid backend raises" must catch `SystemExit`, breaking this codebase's established convention of using `pytest.raises(ValueError)`-style assertions for pure-logic errors and reserving `SystemExit`/`die()` strictly for the CLI-facing surface.
**Why it happens:** `die()` (`shared/logging.py`) is a fail-fast `sys.exit` helper used everywhere in this codebase's orchestration layer (`run_encode`, `run_detect`), so it is tempting to reuse it directly inside the new `resolve()` too.
**How to avoid:** `resolve()` raises a plain Python exception (`ValueError` is sufficient — no existing precedent for a dedicated exception class at this granularity, though `SceneDetectionError(RuntimeError)` in `detection/config.py:16` is the nearest analogous pattern if the planner prefers a named exception type); the CLI/`run_encode` call site catches it and converts to `die(str(exc))` for user-facing consistency, exactly mirroring how `probe_fps` (`pipeline.py:91-103`) itself calls `die()` directly when it IS the CLI-facing surface, versus how pure functions elsewhere raise normally.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Backend selection / plugin discovery | A dynamic plugin-loading system (`importlib.metadata` entry points, `pkgutil.iter_modules` scanning) | A plain `Dict[str, Backend]` literal in `backends/__init__.py` | D-06 registers only `qsvencc` this phase and explicitly rejects any dynamic-discovery complexity ("no stub, no dead build_command... Fail-fast at resolve, no half-wired path"); this codebase has zero plugin infrastructure anywhere and the convention is explicit function-oriented modules, not frameworks |
| Seek/trim math for the future ffmpeg backend | Re-deriving keyframe-before/frame-offset arithmetic independently in `backends/ffmpeg.py` (Phase 8) | `compute_chunk_seek_trim_numeric` (this phase's deliverable) | Explicitly the entire point of D-04 — "No duplicated derivation; ... Phase 8's ffmpeg backend formats the same numeric record its own way, without re-deriving the math" |
| Backend contract typing | A `Protocol`/ABC class hierarchy for backends | `@dataclass(frozen=True)` value object holding callables (D-01) | Matches the zero-OOP convention already established (`Scene`, `DetectionConfig`) — introducing an ABC/Protocol here would be the first class hierarchy in the codebase and contradicts `.planning/codebase/ARCHITECTURE.md`'s explicit "No object-oriented service layer" note |

**Key insight:** Every "don't hand-roll" temptation in this phase is really "don't over-engineer the seam" — the correct amount of abstraction here is a frozen dataclass and a dict, not a plugin framework, because there are exactly two backends ever anticipated (qsvencc, ffmpeg) and the registry itself is locked to one entry this phase by explicit decision (D-06).

## Common Pitfalls (continued — golden-argv snapshot mechanics, D-09)

### Pitfall 5: Golden argv fixtures must use literal, non-derived `hdr_flags` inputs
**What goes wrong:** If the fast, hardware-free golden-argv test tries to derive its HDR10/HDR10+/DV `hdr_flags` inputs by calling `detect_hdr()` against a synthetic media file, it silently becomes a mixed unit/subprocess test (needs `ffprobe` present) and stops being "fast" per this codebase's own TEST-01/TEST-02 tier split (pure-logic vs mocked-subprocess).
**How to avoid:** Hand-write the four representative `hdr_flags` literal lists directly in the golden-argv test module, matching exactly what `detect_hdr()` (`encoding/hdr.py:16-32`) is verified to emit for each case:
- SDR: `[]`
- HDR10: `["--master-display", "copy", "--max-cll", "copy"]`
- HDR10+: `["--master-display", "copy", "--max-cll", "copy", "--dhdr10-info", "copy"]`
- DV: `["--master-display", "copy", "--max-cll", "copy", "--dolby-vision-rpu", "copy", "--dolby-vision-profile", "10.1"]` (using the `DV_PROFILE` default `"10.1"` per `encoding/hdr.py:13`)

Combine each with 2-3 representative `(kf_frame, kf_time, start_off, end_off)` tuples including at minimum: a scene starting exactly on frame 0 (`start_off=0`), a scene starting mid-GOP off a keyframe (`start_off>0`), and explicitly a scene where the resulting chunk index within a run would be `first>0` (i.e. not the first chunk of the run — this exercises the `--seek`/`--trim` values for a non-zero-indexed chunk, which the CONTEXT explicitly calls out as a required matrix row since it is the case most likely to reveal an off-by-one in the numeric/formatting split). Assert the resulting `List[str]` argv equals a committed golden fixture byte-for-byte (a Python literal in the test file, or a small JSON/text fixture under a new `tests/fixtures/golden_argv/` directory — format is Claude's Discretion per CONTEXT).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `resolve()` should raise a plain `ValueError` rather than call `die()` directly, and the CLI/`run_encode` call site converts it | Pitfall 4, Pattern 1 | Low — this is a design recommendation (Claude's Discretion per CONTEXT explicitly leaves `resolve()`'s signature open), not a verified fact; if the planner prefers `resolve()` to `die()` directly for simplicity, that is a valid alternative, just less consistent with the existing pure/CLI split |
| A2 | `test_sdr_legacy_oracle_parity` (`tests/integration/test_hardware_real_media.py:335`) will keep passing unmodified after the refactor, serving as the de facto D-10 proof | Summary, Phase Requirements | Medium — this is true ONLY if every behavior-preserving invariant genuinely holds; if it does NOT pass post-refactor, that is itself the correctness signal the phase needs, not evidence the assumption was wrong. Flagged here so the planner explicitly runs this specific test (hardware-gated, so requires real Arc hardware) as the final verification step rather than assuming fast-tier green is sufficient |
| A3 | The exact new `encode_chunk(task, backend)` two-argument call convention (vs. embedding backend in the task tuple) is the best shape | Pattern 3 | Low — CONTEXT explicitly leaves this as discretion; either shape satisfies D-02, this is a recommendation grounded in the existing tuple's shared use elsewhere in `pipeline.py`'s completion loop, not a locked decision |

**If this table is empty:** N/A — see above; all three assumptions are explicitly flagged Claude's-Discretion areas per CONTEXT.md, not compliance-critical or ambiguous factual claims.

## Open Questions (RESOLVED)

1. **Where should the golden-argv fast test and its fixtures physically live?**
   - What we know: CONTEXT.md D-09 requires a fast, hardware-free test asserting byte-for-byte argv reproduction; the existing test-tree convention colocates pure-logic tests next to the module under test (`tests/unit/encoding/test_chunk.py` next to `encoding/chunk.py`, `tests/unit/mkv/test_ebml.py` next to `mkv/ebml.py` per Phase 2's DEBT-01 precedent).
   - What's unclear: Whether the new test belongs in a new `tests/unit/backends/test_qsvencc.py` (mirroring the new `backends/` package) or should stay logically grouped with the existing `tests/unit/encoding/test_chunk.py` (renamed/refocused). CONTEXT.md explicitly leaves file format/location as discretion.
   - Recommendation: Create `tests/unit/backends/test_qsvencc.py`, mirroring the new package structure 1:1 (this codebase's established convention per Phase 2), and move the existing `chunk_command`/`parse_metrics`/`fmt_seek` tests there since those functions physically relocate too.
   - **RESOLVED (Plan 07-01/07-02):** `tests/unit/backends/test_qsvencc.py` created for the relocated `chunk_command`/`parse_metrics`/`fmt_seek`/`build_command` tests (07-02 Task 2), and the D-09 golden-argv fixtures + fast test live at `tests/fixtures/golden_argv/qsvencc.json` + `tests/unit/backends/test_golden_argv.py` (07-01, re-pointed to `build_command` in 07-04 Task 2). Mirrors the new `backends/` package 1:1 per the recommendation.

2. **Should the qsvencc backend's `compute_chunk_seek_trim` (old 2-tuple-string shape) be kept as a named, independently-tested function in `backends/qsvencc.py`, or inlined directly into `build_command`?**
   - What we know: D-04 describes it as "a thin wrapper... moves into backends/qsvencc.py" — implying it remains a distinct, nameable unit.
   - What's unclear: Whether `tests/integration/test_hardware_real_media.py`'s existing non-tautological keyframe-alignment check (lines 208-220, which currently calls `compute_chunk_seek_trim(prod_table, s, e)` directly) should keep calling a qsvencc-specific function, or should be rewritten to call the backend-agnostic numeric core plus local formatting — the latter keeps that specific integration test conceptually backend-agnostic (it is testing keyframe alignment, not qsvencc's string format), which seems more aligned with the test's own stated purpose.
   - Recommendation: Rewrite `test_hardware_real_media.py`'s ground-truth check to call `compute_chunk_seek_trim_numeric` + locally format with `fmt_seek` imported from `enpipe.backends.qsvencc` (since `fmt_seek` genuinely is qsvencc-specific formatting and this integration test is explicitly verifying the qsvencc production path) — this is Claude's Discretion, flagged for the planner to confirm during task-writing.
   - **RESOLVED (Plan 07-03 Task 2):** adopted the recommendation — `test_hardware_real_media.py`'s `_verify` ground-truth block is rewritten to call `compute_chunk_seek_trim_numeric` and format seek locally via `fmt_seek` imported from `enpipe.backends.qsvencc`; the numeric core stays the single shared derivation (D-04) and `build_command` is the qsvencc-side formatter (not a separately kept `compute_chunk_seek_trim` name).

## Sources

### Primary (HIGH confidence — direct codebase reads, this session)
- `src/enpipe/encoding/chunk.py` (full file read) — verified exact current signatures of `chunk_command`, `parse_metrics`, `count_frames`, `encode_chunk`, and `ICQ`/`QPMAX`/`GOP_LEN` env-cast constants
- `src/enpipe/encoding/keyframes.py` (full file read) — verified exact current signatures of `keyframe_table_cues`, `keyframe_table_ffprobe`, `keyframe_table`, `kf_before`, `fmt_seek`, `compute_chunk_seek_trim`
- `src/enpipe/encoding/pipeline.py` (full file read) — verified the preflight loop (`:107-109`), all import lines (`:30-39`), chunk-task assembly (`:201-210`), and every call site of the symbols being moved
- `src/enpipe/cli/main.py` (full file read) — verified `_pipeline_one`'s hand-built Namespace construction (`:31-73`), `run_pipeline`'s duplicate preflight loop (`:88-90`), and `build_parser`'s `encode_p`/`run_p` subparser definitions
- `src/enpipe/detection/config.py` (full file read) — verified the `@dataclass(frozen=True)` `Scene`/`DetectionConfig` precedent SC#1 requires the backend type to follow
- `src/enpipe/shared/proc.py`, `src/enpipe/encoding/hdr.py` (full file reads) — verified the unchanged subprocess seam and the exact `hdr_flags` strings `detect_hdr()` emits for SDR/HDR10/HDR10+/DV, used to construct the golden-argv matrix
- `tests/unit/encoding/test_chunk.py`, `tests/subprocess/encoding/test_chunk.py`, `tests/unit/encoding/test_keyframes.py`, `tests/unit/encoding/test_pipeline_wiring.py`, `tests/unit/cli/*.py` (full/partial reads) — verified every current test import site of the symbols being moved, and the existing `monkeypatch.setattr(chunk, "ICQ", 30)`-style patterns
- `tests/integration/test_hardware_real_media.py` (full read) — verified `test_sdr_legacy_oracle_parity` already implements the D-10 legacy-oracle byte-identity check end-to-end via public CLI entry points, and the `_verify_frame_counts_and_keyframes` independent-ground-truth helper's exact import/call sites
- `pyproject.toml` — verified the `hardware` pytest marker, `-m "not hardware"` default addopts, `--import-mode=importlib` rationale, and the `dev` dependency group (no new deps needed)
- `.github/workflows/ci.yml` — verified the fast tier runs via `uv run pytest -m "not hardware"` on `ubuntu-latest` (no GPU), confirming the golden-argv test must not require hardware
- `.planning/phases/07-backend-seam-refactor-zero-behavior-change/07-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/codebase/ARCHITECTURE.md` — full reads, per task instructions

### Secondary (MEDIUM confidence)
- `.planning/phases/02-correctness-critical-extraction/02-RESEARCH.md` — prior-phase research on the original `compute_chunk_seek_trim`/`contiguous_run` extraction, used to confirm this codebase's established RESEARCH.md conventions and the exact historical rationale for the current (soon-to-be-split) `compute_chunk_seek_trim` shape

### Tertiary (LOW confidence)
- None — this phase required no web research; it is entirely internal-codebase analysis.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries, `dataclasses`/`os`/`re` already in use and verified in situ
- Architecture: HIGH — target structure derived directly from CONTEXT.md's locked decisions (D-01 through D-04) cross-checked against the actual current file contents, not generic advice
- Pitfalls: HIGH — every pitfall enumerated is grounded in an actual grep/read of a real call site or test file in this repository, not a hypothetical

**Research date:** 2026-07-23
**Valid until:** Effectively indefinite for the mechanical-move findings (they are anchored to specific file:line content that will only change via this phase's own edits); re-verify the "Dangling imports" table if any other concurrent phase/quick-task touches `encoding/chunk.py`, `encoding/keyframes.py`, `encoding/pipeline.py`, or `cli/main.py` before this phase's plan executes.
