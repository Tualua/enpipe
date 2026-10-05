# Architecture Research

**Domain:** Dual encode-backend integration into an existing scene-chunk AV1 transcode pipeline (`enpipe` v1.2)
**Researched:** 2026-07-23
**Confidence:** HIGH (existing code read directly; ffmpeg `-f obu` / `av1_qsv` / `dovi_rpu` verified against ffmpeg docs + patchwork, MEDIUM on exact HDR-signaling flags)

## Executive Summary

The clean seam is **not** "add a `backend=` branch inside `chunk_command`." It is to demote the current qsvencc-specific `chunk_command` + `detect_hdr` + `parse_metrics` into **one backend among two**, behind a tiny frozen-dataclass `Backend` value object that bundles three pure callables (`build_command`, `build_hdr_args`, `parse_metrics`) plus two data fields (`name`, `output_suffix`). `pipeline.py` resolves the backend **once** at the top of `run_encode` from a CLI flag / env var, then threads the resolved `Backend` object through the existing task-building loop. Everything downstream of command construction — `count_frames` verify, high-water-mark ordered append, `JOBS` `ThreadPoolExecutor`, byte-concat into `movie.obu`, `mkvmerge` mux — is **backend-agnostic and stays untouched**.

The one piece of shared correctness logic that must **not** be duplicated per backend is the keyframe seek/trim arithmetic (`compute_chunk_seek_trim`), which the corruption handoff explicitly **exonerated** as bit-correct. Today it returns qsvencc-shaped strings (`seek="01:16:14.167"`, `trim="0:339"`). ffmpeg needs the same math in **numeric** form (keyframe time + frame offsets) for frame-accurate `-ss`/trim. The fix is to expose the numbers the function already computes internally, and let each backend format them — sharing the proven math, not re-deriving it.

## Standard Architecture

### System Overview (v1.2 target — new/changed shaded with `*`)

```
┌───────────────────────────────────────────────────────────────────────┐
│  CLI  (cli/main.py)                                                    │
│   enpipe encode / run   --backend ffmpeg|qsvencc   [ENPIPE_BACKEND] *  │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │ args.backend
┌───────────────────────────────▼───────────────────────────────────────┐
│  Orchestration  (encoding/pipeline.py)                                 │
│   run_encode:  backend = get_backend(args.backend)  *                  │
│   ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│   │ keyframe    │  │ per-chunk task   │  │ high-water-mark append   │  │
│   │ table       │─▶│ build (loop)     │─▶│ + count_frames verify    │  │
│   │ (unchanged) │  │ backend.build_*  │* │ + JOBS ThreadPool        │  │
│   └─────────────┘  └────────┬─────────┘  │ (ALL UNCHANGED)          │  │
│                             │            └──────────────────────────┘  │
├─────────────────────────────┼──────────────────────────────────────────┤
│  Backend seam  (encoding/backends/) *                                  │
│   get_backend(name) -> Backend(frozen dataclass) *                     │
│   ┌────────────────────────┐        ┌────────────────────────────┐     │
│   │ backends/qsvencc.py *  │        │ backends/ffmpeg.py *       │     │
│   │  build_command  (argv) │        │  build_command  (argv)     │     │
│   │  build_hdr_args        │        │  build_hdr_args (dovi_rpu, │     │
│   │  parse_metrics         │        │   master-display, dhdr10)  │     │
│   │  output_suffix=".obu"  │        │  parse_metrics = no-op     │     │
│   └────────────────────────┘        │  output_suffix=".obu"      │     │
│        (moved from chunk.py/hdr.py) └────────────────────────────┘     │
├────────────────────────────────────────────────────────────────────────┤
│  Shared pure logic  (UNCHANGED, exonerated)                            │
│   keyframes.compute_chunk_seek_trim  +  *_frames() numeric variant *   │
│   count_frames · contiguous_run · scenes_io · mkv.ebml                 │
├────────────────────────────────────────────────────────────────────────┤
│  Subprocess seam  shared.proc  (UNCHANGED — single choke point)        │
│   qsvencc | ffmpeg | ffprobe | mkvmerge                                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | v1.2 change |
|-----------|----------------|-------------|
| `backends/__init__.py` (`Backend`, `get_backend`, registry) | Frozen-dataclass value object bundling the per-encoder pure callables; name→Backend lookup | **NEW** |
| `backends/qsvencc.py` | `build_command` (today's `chunk_command`), `build_hdr_args` (today's `detect_hdr`), `parse_metrics` | **NEW file, moved logic** |
| `backends/ffmpeg.py` | `build_command` (`av1_qsv` + `-f obu`), `build_hdr_args` (dovi_rpu BSF / master-display / dhdr10), `parse_metrics` no-op | **NEW** |
| `keyframes.compute_chunk_seek_trim` | Exonerated seek/trim math; add a numeric-offset sibling both backends consume | **MODIFIED (additive)** |
| `pipeline.run_encode` | Resolve backend once; pass `Backend` into task loop + `encode_chunk` | **MODIFIED (small)** |
| `pipeline.encode_chunk` | Run cmd → `count_frames` → metrics; use `backend.parse_metrics` + backend name in error text | **MODIFIED (small)** |
| `pipeline` append/verify/JOBS/mux | Ordered concat, frame-count guard, threading, mkvmerge | **UNCHANGED** |
| `chunk.py` / `hdr.py` | Current qsvencc logic | **Becomes re-export shims OR is deleted after backend move** |

## Recommended Project Structure

```
src/enpipe/encoding/
├── backends/                 # NEW: the encode-backend seam
│   ├── __init__.py           # Backend dataclass, REGISTRY, get_backend(name)
│   ├── qsvencc.py            # build_command / build_hdr_args / parse_metrics (from chunk.py+hdr.py)
│   └── ffmpeg.py             # av1_qsv + -f obu; dovi_rpu/master-display/dhdr10; no-op metrics
├── chunk.py                  # SHRINKS: keep count_frames + encode_chunk (backend-agnostic);
│                             #   chunk_command re-exports backends.qsvencc.build_command (compat)
├── hdr.py                    # Becomes thin re-export of backends.qsvencc.build_hdr_args (compat)
├── keyframes.py              # +compute_chunk_seek_trim_frames() numeric variant (additive)
├── pipeline.py               # resolve backend once; thread it through (small diff)
├── audio.py metrics.py scenes_io.py   # UNCHANGED

tests/
├── unit/encoding/
│   ├── backends/
│   │   ├── test_qsvencc_command.py   # argv assertions (moved from test_chunk.py)
│   │   └── test_ffmpeg_command.py    # NEW: -f obu, global_quality, -ss/trim, dovi_rpu argv
│   └── test_backend_registry.py      # get_backend() dispatch, default = ffmpeg
├── subprocess/encoding/
│   ├── test_hdr.py                   # split: qsvencc flags + ffmpeg args (fp-mocked)
│   └── test_ffmpeg_hdr.py            # NEW
└── integration/
    └── test_concurrent_corruption.py # NEW hardware-gated: per-frame content verify under JOBS
```

### Structure Rationale

- **`backends/` as a sub-package, not a param flag:** the two encoders differ in argv shape, HDR-flag vocabulary, **and** metrics semantics (qsvencc emits SSIM/PSNR in stderr; `av1_qsv` does not). A `backend=` branch inside one `chunk_command` would smear three concerns together and break the tight argv-assertion test style. Separate modules keep each `build_command` a **small pure function** that is independently mock-tested — preserving the property the whole test suite relies on.
- **`Backend` as a frozen dataclass, not a class hierarchy / ABC:** the codebase is deliberately function-oriented with `@dataclass(frozen=True)` value objects (`DetectionConfig`, `Scene`, `SourceInfo`) and has **no** OO service layer. A frozen `Backend` holding function references matches that grain exactly and stays trivially constructible in tests.
- **Compat shims for `chunk.py`/`hdr.py`:** existing tests import `enpipe.encoding.chunk.chunk_command` and `enpipe.encoding.hdr.detect_hdr`. Re-exporting from the new modules lets Phase 1 land as a **pure, behavior-preserving refactor** (parity-oracle green) before any ffmpeg code exists.

## Architectural Patterns

### Pattern 1: Backend as a frozen-dataclass function bundle

**What:** One value object per encoder, carrying pure callables + data. No inheritance, no runtime polymorphism beyond a dict lookup.
**When to use:** Selecting between a small, fixed set of interchangeable command builders that share a downstream runner.
**Trade-offs:** + Matches existing conventions, trivially testable, picklable-enough (thread pool, not process pool). − Slightly more indirection than a bare function; worth it for the metrics/HDR divergence.

**Example:**
```python
# backends/__init__.py
from dataclasses import dataclass
from typing import Callable, List
from pathlib import Path
from . import qsvencc, ffmpeg

@dataclass(frozen=True)
class Backend:
    name: str
    build_command: Callable[..., List[str]]     # pure argv builder
    build_hdr_args: Callable[[Path], List[str]]  # ffprobe-driven HDR/DV flags
    parse_metrics: Callable[[str], dict]         # stderr -> metrics (ffmpeg: no-op)
    output_suffix: str                           # ".obu" for both

REGISTRY = {
    "ffmpeg":  Backend("ffmpeg",  ffmpeg.build_command,  ffmpeg.build_hdr_args,  ffmpeg.parse_metrics,  ".obu"),
    "qsvencc": Backend("qsvencc", qsvencc.build_command, qsvencc.build_hdr_args, qsvencc.parse_metrics, ".obu"),
}
DEFAULT = "ffmpeg"   # corruption-free default; qsvencc opt-in

def get_backend(name: str | None) -> Backend:
    return REGISTRY[name or DEFAULT]   # KeyError -> die() in caller
```

### Pattern 2: Share the exonerated keyframe math; format per-backend

**What:** `compute_chunk_seek_trim` already computes `kf_frame`, `kf_time`, `start_off = s - kf_frame`, `end_off = e - 1 - kf_frame`. Expose those numbers; let each backend format them. qsvencc → `--seek fmt_seek(kf_time) --trim "{start_off}:{end_off}"`. ffmpeg → `-ss kf_time` (accurate input seek lands on the keyframe) + frame-accurate trim of `[start_off, end_off]`.
**When to use:** Any time proven correctness-critical arithmetic must feed two output formats.
**Trade-offs:** + Zero re-derivation of the load-bearing math (handoff §3 exonerated it — do not touch the algorithm). − Adds one additive numeric-return function; keep the string-returning `compute_chunk_seek_trim` intact so qsvencc argv stays byte-identical to the legacy oracle.

**Example:**
```python
# keyframes.py  (ADDITIVE — original stays for the qsvencc byte-identity path)
def compute_chunk_seek_trim_frames(table, s, e) -> Tuple[float, int, int]:
    kf_frame, kf_time = kf_before(table, s)
    return kf_time, s - kf_frame, e - 1 - kf_frame   # (seek_time, start_off, end_off)
```
> ffmpeg frame-accurate trim: `-ss <kf_time>` **before** `-i` (accurate seek decodes from the keyframe so decoded frame 0 == keyframe), then select frames `[start_off, end_off]`. When `start_off == 0` (scene starts on a keyframe — the common case) this is just `-frames:v {end_off+1}`; otherwise a trim/select of the decoded stream. This is the single highest-implementation-risk mapping and gets its own SDR parity gate (Phase 2).

### Pattern 3: Keep the runner backend-agnostic; carry the Backend in the task tuple

**What:** `encode_chunk` stays module-level (ThreadPool worker) and generic: run `cmd`, `count_frames(out)`, then `backend.parse_metrics(stdout+stderr)`. Backend only influences (a) the argv built in the task loop, (b) the metrics parser, (c) the error label. Pass the `Backend` as a task-tuple field (thread pool → non-picklable callables are fine).
**When to use:** Parallel workers that must stay uniform while their payload varies.
**Trade-offs:** + High-water-mark ordering, `JOBS`, drain-then-die, frame-count guard all untouched. − Task tuple grows by one field; `encode_chunk`'s hardcoded `"qsvencc rc=…"` string becomes `f"{backend.name} rc=…"`.

**Example:**
```python
# pipeline.run_encode (task loop, minimal diff)
backend = get_backend(getattr(args, "backend", None))
hdr_args = backend.build_hdr_args(args.video)          # was detect_hdr(...)
...
cmd = backend.build_command(args.video, seek_time, start_off, end_off, cp, hdr_args, metrics_on)
tasks.append((i, cmd, cp, e - s, backend))             # backend rides along
```

## Data Flow

### Per-chunk command construction (the only path that forks by backend)

```
scenes[i]=(s,e)
    │
    ▼
compute_chunk_seek_trim_frames(table, s, e)      ── shared, exonerated math
    │   (kf_time, start_off, end_off)
    ▼
backend.build_command(src, kf_time, start_off, end_off, out.obu, hdr_args, metrics)
    │
    ├── qsvencc:  qsvencc --avhw --va … --seek HH:MM:SS.mmm --trim s:e -o out.obu
    └── ffmpeg :  ffmpeg -ss <kf_time> -i src … -c:v av1_qsv -global_quality … \
                         [-bsf:v dovi_rpu …] -f obu out.obu
    │
    ▼  (IDENTICAL from here on — backend-agnostic)
encode_chunk → count_frames(out.obu) == expect  ─┐
    │                                            │ per-chunk frame-count guard (UNCHANGED)
    ▼                                            │
high-water-mark ordered byte-concat → movie.obu ─┘
    │
    ▼
count_frames(movie.obu) == total_expect          ── final guard (UNCHANGED)
    │
    ▼
mkvmerge -o out.mkv --default-duration movie.obu + audio + subs/chapters (UNCHANGED)
```

### The load-bearing output invariant (must hold for BOTH backends)

`movie.obu` is built by **raw byte concatenation** (`shutil.copyfileobj`) of per-chunk `.obu` files, then muxed once by `mkvmerge`. For ffmpeg this requires the **`-f obu` low-overhead OBU muxer** (verified present in ffmpeg; inserts temporal-delimiter OBUs per temporal unit). Each per-chunk encode is independent, so each `.obu` carries its own sequence-header OBU — the same self-contained property qsvencc chunks have today. **This concatenability is the single invariant most likely to bite and MUST be proven empirically** (byte-concat + `count_frames` + mkvmerge + real decode) in the SDR phase before trusting it. Do not assume; the whole `cat`-is-bit-exact design rests on it.

## Concurrency & Correctness Scaling

This is a local/NAS toolchain — "scale" here means **encode throughput and correctness under parallel `JOBS`**, not user count.

| Concern | qsvencc (current) | ffmpeg av1_qsv (v1.2 default) |
|---------|-------------------|------------------------------|
| `JOBS=1` | correct, ⅓ throughput | correct |
| `JOBS=3` (default) | **~33–65% silent single-frame corruption** (handoff §1) | empirically **35/35 clean**, full throughput |
| Root cause exposure | iHD/i915 cross-process 10-bit reference aliasing (unified OR-combined VA pool) | per-component `AVHWFramesContext`, separate `AllocId` → immune |
| Frame-count guard catches it? | **No** (count stays correct — silent) | N/A (clean) |

### Priorities

1. **Correctness first:** ffmpeg default eliminates the silent-corruption class outright — the entire milestone rationale.
2. **Defense-in-depth (recommended, handoff §7):** a per-frame **content** verification gate (PSNR/VMAF of `movie.obu` vs source) on top of `count_frames`, so a silent single-frame swap physically cannot ship regardless of backend. Slots cleanly at the existing final-`count_frames` checkpoint in `pipeline.py`. Consider as a cross-cutting requirement, not backend-specific.

## Anti-Patterns

### Anti-Pattern 1: `backend=` branch inside a single `chunk_command`
**What people do:** Add `if backend == "ffmpeg": …` inside the existing function.
**Why it's wrong:** Conflates three diverging concerns (argv, HDR-flag vocabulary, metrics stderr parsing); makes `hdr_flags: List[str]` ambiguous (qsvencc `--master-display copy` vs ffmpeg `-bsf:v dovi_rpu`); bloats one function the whole suite tests by tight argv-index assertions.
**Do this instead:** One `build_command` per backend module behind the `Backend` dataclass.

### Anti-Pattern 2: Re-deriving seek/trim for ffmpeg
**What people do:** Write fresh keyframe/offset math for the ffmpeg path.
**Why it's wrong:** `compute_chunk_seek_trim` is the **exonerated, correctness-critical** core (handoff §3 proved it bit-exact); a parallel derivation is a new corruption surface.
**Do this instead:** Add the additive numeric-offset accessor (Pattern 2); both backends consume the same math.

### Anti-Pattern 3: Touching the legacy oracle or the high-water-mark/verify path
**What people do:** "Simplify" `flush_appends`, the frame-count guards, or `legacy/`.
**Why it's wrong:** `legacy/encode_scenes.py` is the frozen byte-parity oracle; the ordered-append + `count_frames` guards are the last line of defense against silent corruption.
**Do this instead:** Backends only build argv + HDR args + parse metrics. Everything else stays byte-identical; the qsvencc path must still match the legacy oracle after the refactor.

### Anti-Pattern 4: Letting ffmpeg metrics silently vanish
**What people do:** Assume `--psnr/--ssim`-style metrics exist on the ffmpeg path.
**Why it's wrong:** `av1_qsv` does not print SSIM/PSNR to stderr; qsvencc's own metrics also need OpenCL (usually absent on trixie). Metrics would just go blank.
**Do this instead:** `ffmpeg.parse_metrics` returns the empty dict (size still recorded; `write_metrics_csv` already tolerates `None` fields). If metrics matter, compute them in a separate external ffmpeg/libvmaf post-step — out of scope for v1.2 but the seam allows it.

## Integration Points

### External tools (all via `shared.proc`, unchanged seam)

| Tool | Backend usage | Notes |
|------|---------------|-------|
| `ffmpeg` (8.1, staged in devcontainer) | ffmpeg backend encode (`av1_qsv`, `-f obu`, `dovi_rpu` BSF); metrics/keyframe probes both backends | 8.1 required for `dovi_rpu` BSF + mature `av1_qsv` |
| `qsvencc` | qsvencc backend only (opt-in) | retained, preflight `shutil.which` stays |
| `ffprobe` | HDR/DV detection, keyframe table, `count_frames` | backend-agnostic |
| `mkvmerge` | final mux of `movie.obu` | backend-agnostic; relies on OBU concat invariant |

**Preflight note:** `run_encode`/`run_pipeline` currently hard-require `qsvencc` via `shutil.which`. With ffmpeg as default, requiring `qsvencc` unconditionally is wrong — make the qsvencc check conditional on the selected backend (only `ffmpeg`/`ffprobe`/`mkvmerge` are mandatory for the default path).

### Internal boundaries

| Boundary | Communication | Consideration |
|----------|---------------|---------------|
| CLI ↔ pipeline | `args.backend` (`--backend`, default from `ENPIPE_BACKEND` env, following the `ICQ`/`JOBS` env-tunable convention) | add to `encode` + `run` subparsers; default `"ffmpeg"` |
| pipeline ↔ backend | `get_backend(name)` → `Backend` object; `build_command` / `build_hdr_args` / `parse_metrics` | resolve once, pass object down |
| keyframes ↔ backends | numeric `(kf_time, start_off, end_off)` tuple | shared exonerated math |
| backend ↔ runner | task tuple gains `backend`; `encode_chunk` calls `backend.parse_metrics`, labels errors `backend.name` | thread pool → callables in tuple are fine |

## Suggested Build Order (phases)

Ordered by dependency + risk, SDR→HDR→DV, legacy oracle frozen throughout. Each phase gates on its own test/parity check before the next.

1. **Backend seam refactor (zero behavior change).** Introduce `backends/` package, `Backend` dataclass, registry with **qsvencc as the only + default backend**; move `chunk_command`/`detect_hdr`/`parse_metrics` in, leave `chunk.py`/`hdr.py` as re-export shims; add `compute_chunk_seek_trim_frames`; thread `Backend` through `run_encode`/`encode_chunk`; add `--backend` flag (only `qsvencc` valid yet). **Gate:** existing argv tests + legacy byte-parity oracle stay green. This de-risks everything by proving the seam is behavior-preserving before any ffmpeg code exists.
2. **ffmpeg SDR backend.** Implement `backends/ffmpeg.py::build_command` (`av1_qsv` preset mapping: `-global_quality`↔ICQ, `-g`↔GOP, `-bf`/B-pyramid, `-tile_cols/-tile_rows`, `p010le`/main-10) + `-f obu` output + frame-accurate `-ss`/trim from the numeric tuple; `parse_metrics` no-op; register `ffmpeg`. **Gate (highest-value):** (a) SDR real-media parity — per-chunk + total `count_frames`, keyframe alignment, byte-concat+mkvmerge decodes clean; (b) **concurrent-corruption regression test** (per-frame content verify under `JOBS`, using the §4 reproducer) proving 0% corruption. Validates the OBU-concat invariant and the seek/trim mapping — the two real risks.
3. **Flip default to ffmpeg; qsvencc opt-in.** Change `DEFAULT="ffmpeg"`; make the `qsvencc` preflight `which` conditional. **Gate:** CLI dispatch tests; `--backend qsvencc` still works and matches legacy oracle.
4. **HDR10 static metadata through ffmpeg.** `ffmpeg.build_hdr_args` emits mastering-display / max-cll signaling for `av1_qsv`. **Gate:** HDR10 fixture — transfer/primaries/mastering metadata survive concat+mux.
5. **HDR10+ (dhdr10) and Dolby Vision RPU (highest risk, last).** `dovi_rpu` BSF passthrough + dhdr10 dynamic metadata. This is the load-bearing risk PROJECT.md names — the whole reason qsvencc was originally chosen. **Gate:** DV/HDR10+ fixture parity vs the qsvencc path (RPU present per-frame, profile correct, survives `cat`). Keep the DV verification distinct from SDR.

## Sources

- Existing code (HIGH): `src/enpipe/encoding/{chunk,hdr,keyframes,pipeline}.py`, `src/enpipe/cli/main.py`, `tests/unit/encoding/test_chunk.py`, `tests/subprocess/encoding/test_hdr.py`
- Corruption root-cause + solution space (HIGH): `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` (§1 symptom, §3 exoneration of seek/trim + ffmpeg immunity 35/35, §7 options, §8 code map)
- Project constraints/conventions (HIGH): `.planning/PROJECT.md`, `CLAUDE.md`
- ffmpeg OBU muxer `-f obu` (MEDIUM): [FFmpeg Formats Documentation](https://ffmpeg.org/ffmpeg-formats.html)
- ffmpeg `av1_qsv` encoder options (MEDIUM): [ffmpeg -h encoder=av1_qsv gist](https://gist.github.com/nico-lab/4d61b5ac482fcf18b829448f5f0a2bd6)
- ffmpeg `dovi_rpu` bitstream filter (MEDIUM): [FFmpeg Bitstream Filters](https://ffmpeg.org/ffmpeg-bitstream-filters.html), [FFmpeg-devel dovi_rpu patch](https://patchwork.ffmpeg.org/project/ffmpeg/patch/20240624172044.101722-9-ffmpeg@haasn.xyz/), [DeepWiki: Dolby Vision and HDR Metadata](https://deepwiki.com/FFmpeg/FFmpeg/5.5-dolby-vision-and-hdr-metadata)

---
*Architecture research for: dual encode-backend integration (enpipe v1.2 ffmpeg av1_qsv)*
*Researched: 2026-07-23*
</content>
</invoke>
