# Phase 7: Backend Seam Refactor (zero behavior change) - Pattern Map

**Mapped:** 2026-07-23
**Files analyzed:** 8 (3 new backend package files + 4 modified + 1 new test area; test-import-fixups covered under "Modified" since RESEARCH.md already enumerates every site)
**Analogs found:** 8 / 8 (all files have a same-repo analog; this phase moves/refactors existing code more than it invents new patterns)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/enpipe/backends/base.py` | model (value object) | transform (pure data shape, no I/O) | `src/enpipe/detection/config.py` (`Scene`/`DetectionConfig`) | exact |
| `src/enpipe/backends/__init__.py` | service (registry + resolver) | request-response (name in -> Backend out / raise) | No exact registry precedent exists; closest are the env-cast module constants (`encoding/chunk.py:21-23`, `encoding/hdr.py:13`, `encoding/pipeline.py:41`) + `detection/config.SceneDetectionError` for the exception shape | role-match (constant pattern) / partial (registry itself is new) |
| `src/enpipe/backends/qsvencc.py` | service (pure argv/parse builder, verbatim-moved) | transform (string-in/string-out, no subprocess) | `src/enpipe/encoding/chunk.py` (current `chunk_command`/`parse_metrics`/`ICQ`/`QPMAX`/`GOP_LEN`) + `src/enpipe/encoding/keyframes.py` (`fmt_seek`) | exact (verbatim source) |
| `src/enpipe/encoding/chunk.py` (modified — shrinks) | service (backend-generic orchestrator) | request-response (subprocess run + verify) | itself, pre-refactor (`encode_chunk`/`count_frames` as they exist today, `encoding/chunk.py:66-89`) | exact |
| `src/enpipe/encoding/keyframes.py` (modified — adds numeric core) | utility (pure arithmetic) | transform | itself, pre-refactor `compute_chunk_seek_trim` (`keyframes.py:114-122`) | exact |
| `src/enpipe/encoding/pipeline.py` (modified — threads backend) | controller/orchestration | request-response + batch | itself, pre-refactor `run_encode` (`pipeline.py:106-181` imports/preflight/chunk-task loop) | exact |
| `src/enpipe/cli/main.py` (modified — `--backend` flag) | controller (CLI) | request-response | itself, pre-refactor `build_parser`'s `encode_p`/`run_p` blocks + `_pipeline_one`'s hand-built Namespaces | exact |
| New tests: golden-argv fast test (D-09) | test | transform (pure assertion, no subprocess) | `tests/unit/encoding/test_chunk.py` (pure-logic tier, TEST-01) | exact |
| New/updated tests: on-Arc byte-identity (D-10) | test | request-response (subprocess-driven, hardware-gated) | `tests/integration/test_hardware_real_media.py::test_sdr_legacy_oracle_parity` (already implements this check end-to-end) | exact (already exists — expected to need zero edits) |

## Pattern Assignments

### `src/enpipe/backends/base.py` (model, transform)

**Analog:** `src/enpipe/detection/config.py` (full file read; `DetectionConfig`/`Scene` at lines 25-70)

**Frozen-dataclass idiom to copy exactly** (`detection/config.py:25-47`, `:58-70`):
```python
@dataclass(frozen=True)
class DetectionConfig:
    analysis_width: int = 320
    use_qsv: bool = True
    qsv_device: Optional[str] = None
    adaptive_threshold: float = 3.0
    min_scene_len_frames: Optional[int] = 72
    min_scene_len_sec: float = 3.0
    window_width: int = 2
    min_content_val: float = 15.0
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"


@dataclass(frozen=True)
class Scene:
    """Границы сцены. Кадры 0-based, end_frame — исключительно."""

    index: int
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame
```

**Imports pattern to copy** (`detection/config.py:1-13`):
```python
"""<module docstring: substantial "why", Russian prose, cites the legacy
line range this was extracted from — see convention below>"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path       # only if PathLike-style aliases are needed
from typing import Optional, Union
```
For `backends/base.py`, the field types need `Callable`/`List`/`Tuple` from `typing` (this codebase uses `typing`-module generics, not bare `list[...]`/`tuple[...]`, per `CLAUDE.md` — see RESEARCH.md's own recommended shape, which already follows this: `from typing import Callable, List, Tuple`).

**Module docstring convention to copy** (style, not content — see `detection/config.py:1-4` and `encoding/chunk.py:1-5`): a "why" docstring naming the source of the pattern (`Scene`/`DetectionConfig`) and the decision ID (D-01) it satisfies, in Russian, e.g.:
```python
"""Контракт бэкенда энкодера: неизменяемый value-объект, объединяющий чистые,
argv-тестируемые колбэки + метаданные. Тот же паттерн, что Scene/DetectionConfig
(enpipe.detection.config) — см. CONTEXT.md D-01."""
```

**No custom exception needed here** — `base.py` is a pure value object, no error paths. (The nearest exception precedent for `backends/__init__.py`'s `resolve()` error path is `SceneDetectionError(RuntimeError)` at `detection/config.py:16-17` — a one-line Russian-docstring subclass of the most specific stdlib exception; use `ValueError` directly per RESEARCH.md Pitfall 4's recommendation, or subclass it the same way if the planner wants a named type.)

---

### `src/enpipe/backends/__init__.py` (service, request-response)

**Analog 1 — env-cast module constant convention** (`src/enpipe/encoding/chunk.py:17-23`):
```python
# --------------------------------------------------------------------------- #
# Пресет видео (1:1 из encode_av1_opus.sh; --i-adapt/--b-adapt убраны — они
# требуют lookahead, а LA-ICQ на Alchemist не поддержан, т.е. были no-op).
# --------------------------------------------------------------------------- #
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))
```
Also `encoding/pipeline.py:41`: `JOBS = int(os.environ.get("JOBS", "3"))` and `encoding/hdr.py:13`: `DV_PROFILE = os.environ.get("DV_PROFILE", "10.1")` — note `DV_PROFILE` is the closest **string** (uncast) env constant, matching `BACKEND`'s own type (`str`, no `int()`/`float()` cast needed):
```python
BACKEND = os.environ.get("BACKEND", "qsvencc")   # D-07: bare env-var name, str default
```

**Analog 2 — exception-raising convention for pure/testable logic** (`detection/config.py:16-17`):
```python
class SceneDetectionError(RuntimeError):
    """Ошибка этапа детектирования сцен (ffprobe/ffmpеg/пайп)."""
```
`resolve()` should raise a plain `ValueError` (per RESEARCH.md Pattern 1 / Pitfall 4) so unit tests use `pytest.raises(ValueError)` rather than catching `SystemExit`; the CLI/`run_encode` call site converts to `die()`. This mirrors the codebase's existing split: pure functions raise, only CLI-facing call sites (`probe_fps` at `pipeline.py:91-103`, the `for tool in (...) if not shutil.which(tool): die(...)` preflight at `pipeline.py:107-109`) call `die()` directly.

**No registry/dispatch-table precedent exists elsewhere in the repo** — this is genuinely new structure. Keep it minimal per RESEARCH.md's "Don't Hand-Roll" table: a plain `Dict[str, Backend]` literal, no plugin discovery.

**Imports pattern** (module-level, matching `pipeline.py:19-39` grouping convention — stdlib first, then first-party, all at top, never mid-file per the "Import Organization" convention that flags `encode_scenes.py`'s mid-file `import re` as an anti-pattern to avoid repeating):
```python
from __future__ import annotations

import os
from typing import Dict, Optional

from enpipe.backends.base import Backend
from enpipe.backends.qsvencc import QSVENC_BACKEND
```

---

### `src/enpipe/backends/qsvencc.py` (service, verbatim-moved + thin wrapper)

**Analog:** `src/enpipe/encoding/chunk.py` (full file, 90 lines) + `src/enpipe/encoding/keyframes.py:101-111` (`fmt_seek`)

**Verbatim move #1 — preset constants** (`encoding/chunk.py:17-23`, move unchanged):
```python
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))
```

**Verbatim move #2 — `chunk_command`** (`encoding/chunk.py:26-42`, move unchanged, including comment):
```python
def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
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
    if metrics:                                  # PSNR/SSIM считает сам qsvencc
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd
```

**Verbatim move #3 — metrics regex + `parse_metrics`** (`encoding/chunk.py:45-63`, move unchanged):
```python
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
```

**Verbatim move #4 — `fmt_seek`** (`encoding/keyframes.py:101-111`, move unchanged, including the floor-rounding rationale docstring — RESEARCH.md flags this as the highest-risk arithmetic in the migration, so do not touch the body):
```python
def fmt_seek(t: float) -> str:
    """Секунды -> HH:MM:SS.mmm, ОКРУГЛЯЯ ВНИЗ до мс.

    floor гарантирует seek_time ≤ времени keyframe, поэтому seek (который
    приземляется на первый keyframe ≥ времени seek) попадёт именно на него.
    """
    ms = int(t * 1000)  # floor
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
```

**New thin wrapper — `build_command`** (the only genuinely new logic in this file; reproduces `compute_chunk_seek_trim`'s old formula, `keyframes.py:119-121`, exactly):
```python
def build_command(src: Path, kf_frame: int, kf_time: float, start_off: int,
                   end_off: int, out: Path, hdr_flags: List[str],
                   metrics: bool) -> List[str]:
    seek = fmt_seek(kf_time)
    trim = f"{start_off}:{end_off}"
    return chunk_command(src, seek, trim, out, hdr_flags, metrics)
```

**Backend instance construction — pairs with `backends/base.py`'s `Backend` dataclass:**
```python
QSVENC_BACKEND = Backend(
    name="qsvencc",
    build_command=build_command,
    parse_metrics=parse_metrics,
    required_tools=("qsvencc",),
    supports_metrics=True,
)
```

**Imports pattern** (matching `encoding/chunk.py:7-15`, plus the new intra-`backends`/`encoding` cross-import):
```python
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from enpipe.backends.base import Backend
from enpipe.encoding.keyframes import compute_chunk_seek_trim_numeric
```

**Module docstring convention** — copy the "dословно перенесено из <origin> (D-code), без изменения логики" phrasing style from `encoding/chunk.py:1-5` / `encoding/keyframes.py:1-11`, but cite the intra-repo origin (`encoding/chunk.py`, `encoding/keyframes.py`) rather than `legacy/`, since this is a phase-7 internal move, not the phase-4 legacy extraction.

---

### `src/enpipe/encoding/chunk.py` (modified — shrinks to generic `encode_chunk` + `count_frames`)

**Analog:** itself, pre-refactor (`encoding/chunk.py:66-89`)

**`count_frames` stays completely unchanged** (`encoding/chunk.py:66-71`):
```python
def count_frames(path: Path) -> int:
    """Число видеокадров через пакеты (без декода — 1 пакет = 1 кадр в AV1)."""
    got = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
              capture_output=True, text=True).stdout.strip().rstrip(",")
    return int(got) if got.isdigit() else -1
```

**`encode_chunk` becomes backend-generic** — current shape (`encoding/chunk.py:74-89`) vs. target shape (RESEARCH.md Pattern 3, verified against current signature):
```python
# CURRENT (before):
def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    ...

# TARGET (after — backend passed as explicit 2nd positional arg, not folded
# into the task tuple, per RESEARCH.md Pattern 3 rationale: task is already
# constructed once per chunk and consumed elsewhere in pipeline.py's
# completion loop; backend is a single constant value for the whole run):
def encode_chunk(task, backend: "Backend") -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **backend.parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    ...  # rest unchanged
```
`chunk_command`, `parse_metrics`, `ICQ`/`QPMAX`/`GOP_LEN`, and the `_SSIM_RE`/`_PSNR_RE` regexes are **removed** from this file (they moved verbatim to `backends/qsvencc.py`, above).

**Error-handling convention preserved unchanged** — the `(idx, got, err_or_None, elapsed, info)` tuple-return, never-raise shape stays exactly as-is; this is the established "worker functions return tuples, never `die()`/`sys.exit()`" rule from `CLAUDE.md`'s Error Handling section, already followed by this exact function.

---

### `src/enpipe/encoding/keyframes.py` (modified — adds numeric core, removes `fmt_seek`)

**Analog:** itself, pre-refactor `compute_chunk_seek_trim` (`keyframes.py:114-122`)

**Current (before — to be split):**
```python
def compute_chunk_seek_trim(table: List[Tuple[int, float]], s: int, e: int) -> Tuple[str, str]:
    """seek/trim-строки для сцены [s, e) по keyframe-таблице источника.
    Вынесено дословно из pipeline.py:108-110 (D-04, фаза 2, DEBT-02) — без
    изменения логики. K = последний keyframe источника с frame_K <= S;
    qsvencc --seek floor_ms(K) --trim (S-K):(E-1-K)."""
    kf_frame, kf_time = kf_before(table, s)
    seek = fmt_seek(kf_time)
    trim = f"{s - kf_frame}:{e - 1 - kf_frame}"
    return seek, trim
```

**Target — numeric core stays here (backend-agnostic, no `fmt_seek` import), string formatting moves to `backends/qsvencc.py`:**
```python
def compute_chunk_seek_trim_numeric(
    table: List[Tuple[int, float]], s: int, e: int
) -> Tuple[int, float, int, int]:
    """Numeric keyframe derivation shared by every backend (D-04). Returns
    (kf_frame, kf_time, start_off, end_off). Extracted verbatim from the old
    compute_chunk_seek_trim's arithmetic (keyframes.py:119-121) — only the
    STRING formatting (fmt_seek + f"{s}:{e}") moved out, into
    backends/qsvencc.py, since it is qsvencc-specific."""
    kf_frame, kf_time = kf_before(table, s)
    start_off = s - kf_frame
    end_off = e - 1 - kf_frame
    return kf_frame, kf_time, start_off, end_off
```
`fmt_seek` (`keyframes.py:101-111`) is **removed** from this file (moved verbatim to `backends/qsvencc.py`, see above). `kf_before` (`keyframes.py:88-98`) and everything else in this file (EBML Cues parsing, ffprobe fallback) stays untouched.

**Docstring/comment convention** — copy the "Вынесено дословно из X:Y-Z (D-code, фаза N, DEBT-NN)" citation style already used at `keyframes.py:114-118` and `pipeline.py:44-49` (`contiguous_run`'s docstring) for the new function's own extraction note.

---

### `src/enpipe/encoding/pipeline.py` (modified — threads resolved backend through `run_encode`)

**Analog:** itself, pre-refactor (imports `:30-39`, preflight `:106-109`, log line `:174-176`, chunk-task loop `:200-210`, submit call `:240-241`)

**Import block to update** (`pipeline.py:30-39`, current):
```python
from enpipe.shared import proc as _proc
from enpipe.shared.batch import iter_input_videos, run_batch
from enpipe.shared.logging import _START, die, log, step

from .audio import encode_audio
from .chunk import GOP_LEN, ICQ, QPMAX, chunk_command, count_frames, encode_chunk
from .hdr import detect_hdr
from .keyframes import compute_chunk_seek_trim, keyframe_table
from .metrics import write_metrics_csv
from .scenes_io import read_scenes
```
Target: `from .chunk import count_frames, encode_chunk` (drop `GOP_LEN`/`ICQ`/`QPMAX`/`chunk_command`), `from .keyframes import compute_chunk_seek_trim_numeric, keyframe_table` (drop the old `compute_chunk_seek_trim`), plus `from enpipe.backends import resolve` (or equivalent) to obtain the backend object. Keep the log line's `ICQ`/`QPMAX`/`GOP_LEN` reference (`pipeline.py:175-176`) working by reading them off the resolved backend module or accepting the RESEARCH.md discretion to log via `backend.name` instead — **flag for planner**: this log-line detail is a byte-identity surface (D-10 covers stdout too per Pitfall 2's spirit) and needs an explicit decision in the plan.

**Preflight loop — pattern to preserve exactly, only source of the tool tuple changes** (`pipeline.py:106-109`, current):
```python
def run_encode(args) -> None:
    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")
```
Target — per RESEARCH.md Pitfall 2, backend tools **must stay first** in the concatenated tuple to preserve the exact `die()` message when multiple tools are missing simultaneously:
```python
    for tool in (*backend.required_tools, "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")
```
`cli/main.py::run_pipeline`'s duplicate loop (`cli/main.py:88-90`) must be updated in the same commit/task — it currently repeats the identical 4-tuple independently.

**Chunk-task assembly loop — pattern to preserve, only the two calls change shape** (`pipeline.py:204-210`, current):
```python
    for i, (s, e) in enumerate(scenes):
        seek, trim = compute_chunk_seek_trim(table, s, e)
        cp = workdir / f"chunk_{i:05d}.obu"
        chunk_paths.append(cp)
        cmd = chunk_command(args.video, seek, trim, cp, hdr_flags, metrics_on)
        tasks.append((i, cmd, cp, e - s))
        meta[i] = (s, e, seek, trim)
```
Target — `compute_chunk_seek_trim_numeric` + `backend.build_command`:
```python
    for i, (s, e) in enumerate(scenes):
        kf_frame, kf_time, start_off, end_off = compute_chunk_seek_trim_numeric(table, s, e)
        cp = workdir / f"chunk_{i:05d}.obu"
        chunk_paths.append(cp)
        cmd = backend.build_command(args.video, kf_frame, kf_time, start_off, end_off,
                                     cp, hdr_flags, metrics_on)
        tasks.append((i, cmd, cp, e - s))
        meta[i] = (s, e, ...)  # meta's (seek, trim) strings were only used for
                                # the per-chunk log line (pipeline.py:258) and
                                # CSV row (pipeline.py:258) — planner must decide
                                # whether to keep formatting them for logging
                                # (e.g. via backend-specific re-derivation) or
                                # change what meta stores; flag as an explicit
                                # task decision, not silently dropped
```

**`ThreadPoolExecutor.submit` call — signature gains the `backend` arg** (`pipeline.py:241`, current):
```python
        futs = {ex.submit(encode_chunk, t): t[0] for t in tasks}
```
Target:
```python
        futs = {ex.submit(encode_chunk, t, backend): t[0] for t in tasks}
```

**Where `backend` itself is resolved** — insert near the top of `run_encode`, using `getattr(args, "backend", None)` (matching this codebase's existing defensive-`getattr` convention for hand-built test Namespaces, see `_ensure_out_dir`'s `getattr(args, "out_dir", None)` at `pipeline.py:81`):
```python
    from enpipe.backends import resolve  # or module-level import, planner's choice
    try:
        backend = resolve(getattr(args, "backend", None))
    except ValueError as exc:
        die(str(exc))
```

---

### `src/enpipe/cli/main.py` (modified — `--backend` scaffold on `encode_p`/`run_p`)

**Analog:** itself, pre-refactor `encode_p` block (`cli/main.py:174` area, `--jobs` argument) and `_pipeline_one`'s hand-built Namespace (`cli/main.py:59-73`)

**Argparse-option pattern to copy** (matching the existing `--jobs` default-from-env-constant idiom, `cli/main.py:174`):
```python
encode_p.add_argument("--jobs", type=int, default=ENCODE_JOBS)
```
Target, added to both `encode_p` and `run_p` (D-08):
```python
encode_p.add_argument("--backend", default=None,
                       help="энкод-бэкенд (по умолчанию из BACKEND/qsvencc)")
```
Import needed at top of file: `from enpipe.backends import BACKEND` (for the help text / default-display convention) — or simply pass `default=None` and let `resolve()` apply the env/default fallback inside `run_encode`, matching D-05's flag>env>default precedence being resolved in one place (`backends.resolve`), not duplicated in argparse defaults. **Flag for planner**: decide whether argparse's own `default=` should show `BACKEND` env value (nice UX, matches `--jobs`'s `default=ENCODE_JOBS` precedent) or stay `None` and defer entirely to `resolve()` (simpler, single source of truth) — RESEARCH.md leaves this as discretion.

**Hand-built Namespace threading — the exact pitfall RESEARCH.md flags (Pitfall 3)** (`cli/main.py:59-72`, current):
```python
    encode_args = argparse.Namespace(
        video=video,
        scenes=scenes_path,
        out=args.out,
        out_dir=args.out_dir,
        frm=args.frm,
        to=args.to,
        workdir=args.workdir,
        keep=args.keep,
        jobs=args.encode_jobs,
        no_audio=args.no_audio,
        no_metrics=args.no_metrics,
        csv=args.csv,
    )
```
Target — **must** add `backend=args.backend` (or `getattr(args, "backend", None)` if `run_p` itself doesn't declare it under a `backend` name) to this Namespace in the same task as adding the `--backend` flag, per the `cli/main.py:39-40` in-file warning comment ("Namespace-поля НЕ переименовывать -- test_cli_run.py проверяет их поимённо"):
```python
    encode_args = argparse.Namespace(
        video=video,
        scenes=scenes_path,
        out=args.out,
        out_dir=args.out_dir,
        frm=args.frm,
        to=args.to,
        workdir=args.workdir,
        keep=args.keep,
        jobs=args.encode_jobs,
        no_audio=args.no_audio,
        no_metrics=args.no_metrics,
        csv=args.csv,
        backend=args.backend,      # NEW — D-08; omission = AttributeError only
                                    # on the `enpipe run` path, not `enpipe encode`
    )
```

**Test pattern to mirror for the new `--backend` routing test** — `tests/unit/cli/test_cli_run.py::test_encode_routing` (lines 66-80, read in full):
```python
def test_encode_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main([
        "run", "x.mkv", "-o", "out.mkv", "--no-metrics",
        "--workdir", "wd", "--keep", "--no-audio", "--csv", "m.csv",
        "--encode-jobs", "9",
    ])

    e = captured["encode"]
    assert e.video == Path("x.mkv")
    assert e.scenes == Path("x.mkv.scenes")
    ...
```
Add a `backend` assertion in the same style (`assert e.backend == "qsvencc"` default-path, plus a case asserting `--backend qsvencc` flows through on `enpipe run`), following this file's `_stub_all_tools_present` + `monkeypatch.setattr(cli_main, "run_encode", ...)` + `captured.setdefault(...)` capture idiom exactly.

---

### Golden-argv fast test (D-09) — new file

**Analog:** `tests/unit/encoding/test_chunk.py` (full file, 66 lines — read above), which is the established TEST-01 "pure-logic, no subprocess, no mocking" tier home for exactly this kind of pure-function argv assertion.

**Structure to copy** (docstring convention, no-fixture-needed rationale, `Path(...)` literal inputs, plain `assert cmd[...] == ...` style):
```python
"""TEST-01: pure-logic golden-argv snapshot test for
enpipe.backends.qsvencc.build_command (D-09) — asserts the qsvencc backend
reproduces committed golden argv byte-for-byte across a SDR/HDR10/HDR10+/DV x
representative-scene permutation matrix (including a first>0 chunk), so any
future preset/arg drift is caught instantly by the fast, hardware-free CI
tier. Hand-written hdr_flags literals (RESEARCH.md Pitfall 5) — NOT derived
via detect_hdr()/ffprobe, to keep this test subprocess-free."""

from __future__ import annotations

from pathlib import Path

from enpipe.backends.qsvencc import build_command

_SDR_FLAGS: list = []
_HDR10_FLAGS = ["--master-display", "copy", "--max-cll", "copy"]
_HDR10PLUS_FLAGS = ["--master-display", "copy", "--max-cll", "copy",
                    "--dhdr10-info", "copy"]
_DV_FLAGS = ["--master-display", "copy", "--max-cll", "copy",
             "--dolby-vision-rpu", "copy", "--dolby-vision-profile", "10.1"]


def test_golden_argv_sdr_first_chunk():
    cmd = build_command(Path("in.mkv"), 0, 0.0, 0, 47, Path("chunk_00000.obu"),
                         _SDR_FLAGS, metrics=False)
    assert cmd == [ ... ]  # committed golden literal
```
Verified real `hdr_flags` values come from `src/enpipe/encoding/hdr.py:26-31` (`detect_hdr`, read above) — confirm the exact flag lists against that function's actual `if`-branches (transfer-based `master-display`/`max-cll`, side-data-based `dhdr10-info`, side-data-based `dolby-vision-rpu`/`dolby-vision-profile`) rather than assuming, since a real HDR10+/DV source typically triggers the transfer-based branch too (combined flags), matching the lists above.

**Location decision (Claude's Discretion per CONTEXT.md):** create `tests/unit/backends/test_qsvencc.py`, mirroring the new `backends/` package 1:1 — this matches the established "test file lives next to the module it tests" convention (e.g. `enpipe.mkv.ebml` -> `tests/unit/mkv/test_ebml.py`, phase 2 DEBT-01 precedent, confirmed present at `tests/unit/mkv/test_ebml.py`). Move the existing `chunk_command`/`parse_metrics` tests from `tests/unit/encoding/test_chunk.py` (lines 1-66, read above) into this new file too, since those functions physically relocate to `backends/qsvencc.py`.

---

### On-Arc byte-identity test (D-10) — existing file, expected zero edits

**Analog:** `tests/integration/test_hardware_real_media.py::test_sdr_legacy_oracle_parity` (lines 335-... , read in full above)

This test already drives the pipeline exclusively through the public `enpipe` CLI (`_run_cli([...])`, calling `enpipe.cli.main.main`) and byte-compares `movie.obu` / final `.mkv` frame counts against the frozen `legacy/encode_scenes.py` oracle:
```python
def test_sdr_legacy_oracle_parity(tmp_path: Path) -> None:
    ...
    _run_cli(["detect", str(src), "--jobs", "2"])
    ...
    _run_cli([
        "encode", str(src), str(scenes),
        "-o", str(enpipe_out), "--workdir", str(wd_enpipe),
        "--keep", "--no-audio", "--no-metrics", "--jobs", "2",
    ])
    ...
    legacy_proc = subprocess.run(legacy_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    ...
    assert count_frames(legacy_out) == count_frames(enpipe_out), (...)
    ...
    if legacy_movie.read_bytes() == enpipe_movie.read_bytes():
        pass  # byte-identical parity holds
```
**Required edit is import-only, not test-logic**: this file imports `compute_chunk_seek_trim, fmt_seek, kf_before, keyframe_table, keyframe_table_ffprobe` from `enpipe.encoding.keyframes` (lines 58-64) and `count_frames` from `enpipe.encoding.chunk` (line 56). Post-move, `compute_chunk_seek_trim`/`fmt_seek` no longer live in `keyframes.py`. Per RESEARCH.md's Open Question #2 recommendation, rewrite the `_verify_frame_counts_and_keyframes` ground-truth helper (lines ~141-220) to import `compute_chunk_seek_trim_numeric` from `enpipe.encoding.keyframes` (stays) and `fmt_seek` from `enpipe.backends.qsvencc` (moved), reconstructing the same non-tautological check locally rather than importing the removed `compute_chunk_seek_trim` name. `kf_before`/`keyframe_table`/`keyframe_table_ffprobe`/`count_frames` import paths are unchanged.

---

## Shared Patterns

### Env-cast module constant (applies to `backends/__init__.py`'s `BACKEND`)
**Source:** `src/enpipe/encoding/chunk.py:21-23`, `src/enpipe/encoding/pipeline.py:41`, `src/enpipe/encoding/hdr.py:13`
```python
ICQ = int(os.environ.get("ICQ", "23"))
JOBS = int(os.environ.get("JOBS", "3"))
DV_PROFILE = os.environ.get("DV_PROFILE", "10.1")   # uncast (str) — the BACKEND analog
```
**Apply to:** `backends/__init__.py`'s `BACKEND = os.environ.get("BACKEND", "qsvencc")` — uncast, matching `DV_PROFILE`'s shape exactly (both are bare strings, not `int()`/`float()`-cast).

### Frozen-dataclass value object (applies to `backends/base.py`)
**Source:** `src/enpipe/detection/config.py:25-70` (`DetectionConfig`, `Scene`)
**Apply to:** `Backend` in `backends/base.py` — same `@dataclass(frozen=True)` idiom, plain fields + optional `@property`, no `__post_init__` validation precedent exists in this codebase for these types, so don't add any unless the plan explicitly needs it.

### Worker functions return tuples, never raise/die (applies to `encode_chunk`)
**Source:** `CLAUDE.md` Error Handling section + `src/enpipe/encoding/chunk.py:74-89` (`encode_chunk`'s existing `(idx, got, err_or_None, elapsed, info)` return shape)
**Apply to:** `encode_chunk`'s backend-generic version — the tuple-return contract is unchanged by this refactor; only the internal `parse_metrics` call becomes `backend.parse_metrics`.

### Preflight `shutil.which` loop, first-tool-first-in-die-message ordering
**Source:** `src/enpipe/encoding/pipeline.py:106-109`, duplicated at `src/enpipe/cli/main.py:88-90`
**Apply to:** Both call sites, updated in the same task, backend tools listed first in the concatenated tuple (RESEARCH.md Pitfall 2).

### Defensive `getattr(args, "x", None)` for hand-built test Namespaces
**Source:** `src/enpipe/encoding/pipeline.py:81` (`_ensure_out_dir`'s `getattr(args, "out_dir", None)`)
**Apply to:** `run_encode`'s new `getattr(args, "backend", None)` read when resolving the backend, so existing hand-built test `Namespace(...)` objects that don't set `backend` (e.g. `tests/unit/encoding/test_pipeline_wiring.py:31-35`, which constructs a `Namespace` without a `backend` field) don't raise `AttributeError` and instead fall through to the `BACKEND` env / `"qsvencc"` default.

### Docstring citation convention ("Вынесено дословно из X:Y-Z (D-code)")
**Source:** `src/enpipe/encoding/keyframes.py:114-118`, `src/enpipe/encoding/pipeline.py:44-49` (`contiguous_run`)
**Apply to:** Every new function created by this phase's move (`build_command`, `compute_chunk_seek_trim_numeric`, `Backend`, `resolve`) should carry a one-line citation of its origin file:line and decision ID, in Russian prose, matching this exact phrasing pattern.

## No Analog Found

None. Every file in this phase's scope either moves existing code verbatim or directly extends an existing, well-precedented pattern (frozen dataclass, env-cast constant, argparse subparser, TEST-01/TEST-02 test tier). The one genuinely new structure — the `backends/__init__.py` registry/`resolve()` function — has no exact registry precedent in the repo, but is explicitly scoped by CONTEXT.md/RESEARCH.md to be a minimal `Dict[str, Backend]` + lookup function, not a pattern requiring invention of new codebase conventions.

## Conventions

Convention derivation skipped (reason: `no-readable-files` — the shared `gsd-tools.cjs verify conventions --derive` module targets JS/TS source files; this repository is 100% Python (`legacy/*.py`, `src/enpipe/**/*.py`), so the tool found nothing to scan under any scope tried (`src/enpipe`, repo-root). No axis table (file-name casing, identifier casing, export style, import style) could be derived mechanically this way for this codebase.

In lieu of the tool output, the manually-documented conventions already captured in `CLAUDE.md` (and re-verified by direct reading in this session) are the authoritative source for this phase: `snake_case` modules/functions, `PascalCase` frozen dataclasses, `UPPER_CASE` env-cast module constants, `typing`-module generics (`List`/`Optional`/`Tuple`, not bare `list[...]`), Russian in-code docstrings/comments/log text with English identifiers, imports grouped stdlib-then-first-party at the top of the file (never mid-file), and no formatter/linter config to defer to. These are treated as **named contract** (share effectively 100% — every file read in this session without exception follows them) for this phase's new/modified files.

### Contested hotspots (author's choice)

Not applicable to this phase's files — everything in scope (`backends/`, `encoding/chunk.py`, `encoding/keyframes.py`, `encoding/pipeline.py`, `cli/main.py`) is pure first-party Python under `src/enpipe/`, with a single, uncontested style already established across every file read. For reference, this repository's one known intentional-contested split is the CJS<->SDK dual resolver pattern used by the GSD tooling itself (`bin/lib/**` CJS `module.exports`/`require` vs `sdk/src/**` ESM `export`/`import`) — each half internally consistent per-directory, contested only repo-wide. That split is not present anywhere in `src/enpipe/` or `tests/`, so no directory-local deviation applies to this phase's planner output.

## Metadata

**Analog search scope:** `src/enpipe/detection/`, `src/enpipe/encoding/` (`chunk.py`, `keyframes.py`, `pipeline.py`, `hdr.py`), `src/enpipe/cli/main.py`, `src/enpipe/shared/logging.py`, `tests/unit/encoding/`, `tests/unit/cli/`, `tests/subprocess/encoding/`, `tests/integration/test_hardware_real_media.py`
**Files scanned (full or targeted reads):** `encoding/chunk.py`, `encoding/keyframes.py`, `encoding/pipeline.py`, `encoding/hdr.py`, `detection/config.py`, `cli/main.py`, `shared/logging.py`, `tests/unit/encoding/test_chunk.py`, `tests/unit/encoding/test_keyframes.py`, `tests/unit/encoding/test_pipeline_wiring.py`, `tests/subprocess/encoding/test_chunk.py`, `tests/unit/cli/test_cli_run.py`, `tests/integration/test_hardware_real_media.py` (targeted grep + section read)
**Pattern extraction date:** 2026-07-23
