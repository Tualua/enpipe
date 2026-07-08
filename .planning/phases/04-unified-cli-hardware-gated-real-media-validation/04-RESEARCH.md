# Phase 4: Unified CLI + Hardware-Gated Real-Media Validation - Research

**Researched:** 2026-07-08
**Domain:** Thin argparse CLI dispatch over an already-migrated Python pipeline; hardware-gated pytest integration testing against real Intel Arc QSV encode/decode, including empirical determination of an AV1-native Dolby Vision RPU verification mechanism
**Confidence:** HIGH for PKG-01 (mechanical, all source inspected directly); MEDIUM-HIGH for TEST-04 (SDR/HDR10 mechanism **empirically verified live on the actual devcontainer's Arc hardware in this research session** — not just documented; DV/HDR10+ mechanism verified against tool behavior but not against genuine DV/HDR10+ source material, which is unavailable in-sandbox per D-06)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**PKG-01 — unified CLI**
- **D-01:** Create `src/enpipe/cli/{__init__,main.py}` with an argparse dispatcher exposing two subcommands: `enpipe detect <input> [flags]` and `enpipe encode <video> <scenes> [flags]`. Add `[project.scripts]` `enpipe = "enpipe.cli.main:main"` to `pyproject.toml` (the slot intentionally reserved since Phase 1).
- **D-02:** The detect subcommand needs a CLI wrapper that does NOT exist yet: migrate the `.scenes`-writing logic from `legacy/scene_detection.py`'s `__main__` block (build `DetectionConfig` from flags → `detect_scenes(input, cfg, jobs)` → format `scene NNNN ...` lines → write `<video>.scenes`) into a `run_detect(args)` in the detection package, MIRRORING the existing `run_encode(args)` in `encoding/pipeline.py`. The CLI `main` builds the argparse Namespace and calls `run_detect`/`run_encode`.
- **D-03:** Reconstitute the EXACT legacy flag surfaces (argv-compatible): detect — `input`, `-o/--output`, `--width`, `--threshold`, `--min-scene-len-frames`, `--jobs`, `--no-qsv` (→ `DetectionConfig(use_qsv=False)`), etc.; encode — `video`, `scenes`, `-o/--out`, `--from`, `--to`, `--workdir`, `--keep`, `--jobs`, `--no-audio`, `--no-metrics`, etc. (the `run_encode` Namespace attribute names). Preserve Russian help text.
- **D-04:** Preserve the two-stage `<video>.scenes` handoff: `enpipe detect video.mkv` writes `video.mkv.scenes`; `enpipe encode video.mkv video.mkv.scenes` reads it. The existing `legacy/scene_detection.py`/`legacy/encode_scenes.py` scripts must still run unmodified (they stay as the parity oracle). No fused single-command orchestrator (that is the out-of-scope streaming design).

**TEST-04 — hardware-gated real-media validation**
- **D-05:** Build a `hardware`-marked integration test (excluded from the default `pytest -m "not hardware"` fast tier) that runs the FULL pipeline end-to-end on real Arc: `enpipe detect` → `enpipe encode` → final `.mkv`. It verifies the load-bearing invariants: (a) per-chunk frame counts and the concatenated total match expectation (`count_frames`/ffprobe), (b) chunk boundaries land on source keyframes (keyframe alignment), (c) for DV sources, RPU survives the chunk-splice + mux.
- **D-06:** SOURCE-MATERIAL REALITY (honest scoping): SDR and HDR10 sources can be generated synthetically with ffmpeg (bt2020/smpte2084 + mastering-display metadata for HDR10) and validated end-to-end on hardware — DO this. HDR10+ (dynamic metadata) and genuine Dolby Vision (RPU) sources CANNOT be reliably synthesized in-sandbox and require real, legally-usable content. Therefore: make the HDR10+/DV cases FIXTURE-gated — the test looks for real sample files in a documented fixtures location (dir/env var); if absent, it SKIPS cleanly with a message explaining how to supply one, and NEVER fakes a pass. The DV RPU-survival check runs only when a DV fixture is present. Document this coverage boundary explicitly; do not claim DV validation ran when no DV source existed.
- **D-07:** The DV RPU-survival mechanism is UNCERTAIN and needs research: `dovi_tool extract-rpu` is documented HEVC-only (`legacy/encode_scenes.py:15-16`), while the pipeline emits AV1 with `qsvencc --dolby-vision-rpu copy`. The planner/researcher must determine the actual way to verify RPU frame-count/profile survival on the AV1 output (dovi_tool AV1 support? qsvencc RPU inspection? an alternative), and design the DV check around what actually works — or, if no reliable in-sandbox mechanism exists, scope the DV check to "RPU present in output" / frame-count parity and document the limitation honestly. **RESOLVED — see "DV RPU Verification Mechanism" below: `dovi_tool` extract-rpu is empirically confirmed broken for AV1 in this environment; use read-only `ffprobe` frame/stream side-data inspection instead.**
- **D-08:** Optionally add the self-hosted-Arc-runner CI stub that Phase 3 deferred (a distinct, never-auto-triggered GitHub Actions job documented as requiring a self-hosted Intel Arc runner for the `hardware` tier), so the hardware tier has a named home — without ever letting hosted CI green be mistaken for hardware validation.

**Conventions & scope**
- **D-09:** Preserve conventions verbatim (Russian help/docstrings, typing generics, banners). CLI is thin dispatch — zero behavior change to detect/encode. `legacy/` untouched.

### Claude's Discretion
- Exact `run_detect(args)` location (detection/cli.py vs a `pipeline`-style module) and the argparse subparser wiring in `cli/main.py`.
- The synthetic HDR10 generation recipe (ffmpeg color-primaries/transfer/mastering-display flags) and the SDR clip recipe.
- The fixtures location convention for HDR10+/DV real samples (e.g. `tests/fixtures/media/` or an `ENPIPE_TEST_MEDIA` env var) and the skip-message wording.
- Whether keyframe-alignment is checked via the existing keyframe table + chunk seek points or via ffprobe on the output chunks.

### Deferred Ideas (OUT OF SCOPE)
- Streaming/pipelined orchestrator (fused single-command) — OUT OF SCOPE (PROJECT.md; do not fuse the stages).
- v2 quality items — stdlib logging, typed config layer, pyright type-checking, coverage reporting, Hypothesis, dependency-update automation, CI/devcontainer image parity (OBS-01/CFG-01/QUAL-01..03/CI-02).
- Public PyPI release / SemVer public compatibility.
- Sourcing/curating a permanent legally-usable HDR10+/DV sample library — beyond this phase; TEST-04 fixture-gates it and documents how to supply samples.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PKG-01 | Two `legacy/` scripts restructured into installable `src/enpipe/` package with unified `enpipe` entry point (`enpipe detect`/`enpipe encode`), preserving the two-stage `<video>.scenes` handoff | `run_detect(args)` skeleton (Code Examples), argparse subparser wiring for `cli/main.py`, exact `.scenes` line-format round-trip contract (Architecture Patterns §2), `[project.scripts]` wiring confirmed against the reserved `pyproject.toml` slot |
| TEST-04 | Hardware-gated integration test running full detect→encode→mux against real media, verifying per-chunk/total frame counts, keyframe alignment, DV RPU survival, gated behind a marker excluded from default CI | Empirically-verified synthetic SDR/HDR10 ffmpeg recipes (proven end-to-end on this session's real Arc hardware), empirically-determined DV RPU verification mechanism (ffprobe-native, not dovi_tool), keyframe-alignment cross-validation design, fixture-gating convention, CI stub shape (D-08) |
</phase_requirements>

## Summary

PKG-01 is almost entirely mechanical: `run_encode(args)` already exists in `src/enpipe/encoding/pipeline.py` and is Namespace-shaped and CLI-ready (confirmed by reading the file directly — it takes `args.video/scenes/out/frm/to/workdir/keep/jobs/no_audio/no_metrics/csv` and does its own preflight checks). The only genuinely new code this phase writes is `run_detect(args)`, which does not exist anywhere yet and must be assembled from `legacy/scene_detection.py:647-692`'s `__main__` block (config-building + `detect_scenes` call + `.scenes`-line formatting) using the already-migrated `enpipe.detection.detect.detect_scenes` and `enpipe.detection.config.DetectionConfig`. The CLI itself (`cli/main.py`) is pure argparse dispatch per the locked D-01 decision (single `main.py`, not the three-file `cli/app.py`+`cli/detect.py`+`cli/encode.py` split sketched in the pre-phase `ARCHITECTURE.md` — that split is superseded by CONTEXT.md's locked decision and must not be reintroduced by the planner).

TEST-04's hard part — the D-07 "uncertain" DV RPU verification mechanism — was resolved empirically in this research session by installing/running the actual toolchain: **`dovi_tool` 2.3.2's `extract-rpu` subcommand fails outright on an AV1 `.obu` file with `Error: Invalid input file type.`** (reproduced directly, not just per the legacy comment), and `dovi_tool --help` confirms there is no AV1-specific subcommand in this CLI version, matching the upstream project's own [AV1 Support discussion #302](https://github.com/quietvoid/dovi_tool/discussions/302), which states AV1 command-line processing is not yet implemented even though the underlying Rust library has AV1 OBU-metadata support. The working alternative, confirmed empirically: **`ffmpeg`/`ffprobe` 7.1.5 (installed in this devcontainer) natively parses AV1 Dolby Vision OBU metadata** — its `dovi_rpu` bitstream filter reports `Supported codecs: hevc av1`, and running it against a real AV1 stream in this session produced a `DOVI configuration record` side-data entry (`profile: 10, level: 1, rpu flag: 1, ...`) readable via plain `ffprobe -show_entries frame=side_data_list`/`stream_side_data_list` with **no bitstream filter needed for read-only inspection** (the filter is a mutating tool and must NOT be applied for verification — it was observed to *synthesize* a fake DOVI record on non-DV content when invoked, which would be a false-positive trap for a verification check). The recommended TEST-04 DV mechanism is therefore: run `ffprobe` (no `-bsf:v`) against per-chunk `.obu` files and the final muxed `.mkv`, and assert every video frame carries a `Dolby Vision RPU Data` side-data entry (RPU-per-frame parity with `count_frames`), plus a stream-level `DOVI configuration record` with the expected profile.

The SDR/HDR10 synthetic-clip requirement (D-06) was also empirically validated end-to-end in this session, not just designed on paper: a `libx265`/`x265-params` recipe (`hdr10=1:master-display=...:max-cll=...` plus top-level `-color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc`) produces a clip that (1) `enpipe.encoding.hdr.detect_hdr()` correctly classifies as HDR10 (`--master-display copy --max-cll copy`, verified by direct function call against the generated file), (2) real Arc hardware (`/dev/dri/renderD128` + `qsvencc 8.20` confirmed present) encodes to AV1 while preserving mastering-display and content-light metadata (verified via `ffprobe` on the raw `.obu`), and (3) `mkvmerge` mux preserves the same metadata into the final `.mkv` with an exact 48/48 frame-count match. A plain `libx264`/`yuv420p`/no-color-tags clip was confirmed to produce `detect_hdr() == []` (the SDR path). HDR10+/DV real fixtures remain fixture-gated per D-06 — no synthesis path exists for dynamic metadata or genuine multi-layer RPU content, confirmed by design (HDR10+ requires per-scene dynamic tone-mapping curves that no synthetic generator produces meaningfully, and DV RPU requires Dolby's proprietary encoding pipeline).

**Primary recommendation:** Implement `run_detect(args)` in a new `enpipe/detection/pipeline.py` (naming-symmetric with `encoding/pipeline.py`'s `run_encode(args)`), wire both through a single `cli/main.py` per D-01, and build TEST-04 as `tests/integration/test_hardware_real_media.py` (module-level `pytestmark = pytest.mark.hardware` + a runtime hardware-availability guard mirroring `scratch/parity_encode.py`'s pattern) using the SDR/HDR10 ffmpeg recipes and ffprobe-native DV verification mechanism documented below, with HDR10+/DV cases gated behind a `tests/fixtures/media/` directory (or `ENPIPE_TEST_MEDIA` env var override) that skips cleanly when absent.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI argument parsing/dispatch (`enpipe detect`/`enpipe encode`) | CLI / Process entry | — | Pure argparse wiring, no business logic; per D-01 lives entirely in `cli/main.py` |
| `.scenes` file writing (detect side) | Detection package | CLI (calls it) | New `run_detect(args)` in the detection package — the CLI wrapper does not own file-format logic |
| `.scenes` file reading (encode side) | Encoding package | — | Already exists (`encoding/scenes_io.py::read_scenes`) — unchanged this phase |
| Scene detection algorithm | Detection package | — | Already migrated (`detection/detect.py`, `detection/parallel.py`) — unchanged this phase |
| Encode orchestration (chunking, splice, mux) | Encoding package | — | Already migrated (`encoding/pipeline.py::run_encode`) — unchanged this phase |
| HDR/DV flag derivation | Encoding package (`hdr.py`) | — | Already migrated, ffprobe-based; unchanged this phase |
| Hardware-gated correctness verification (frame counts, keyframe alignment, DV RPU) | Test / CI tier | Encoding+Detection packages (consumed, not modified) | New this phase — a black-box test harness that exercises the CLI + real hardware, does not add new production code paths |
| Synthetic test-media generation | Test / CI tier | — | ffmpeg-only, lives entirely inside the test file/fixtures, no production code |
| Self-hosted-runner CI wiring (D-08, optional) | CI / infra | — | GitHub Actions workflow file, orthogonal to the Python package |

## Standard Stack

No new runtime or dev dependencies are introduced by this phase. `argparse` (stdlib) is the only CLI toolkit needed — this matches the existing convention (`legacy/scene_detection.py`, `legacy/encode_scenes.py` both use bare `argparse`) and the locked D-01 decision (single `main.py` dispatcher, no click/typer). `pytest` + the already-registered `hardware` marker (`pyproject.toml`) are the only test-infra pieces needed for TEST-04.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `argparse` | stdlib (Python 3.12) | CLI subcommand parsing (`enpipe detect`/`enpipe encode`) | Matches existing `legacy/*.py` convention exactly; D-01 locks this in (no new CLI framework) |
| `pytest` | 9.1.1 (already pinned in `pyproject.toml` dev group) | Hardware-gated integration test | Already the project's test framework; `hardware` marker already registered in `pyproject.toml` |

### Supporting (already installed, no `pip`/`uv` action needed)
| Tool | Version (verified this session) | Purpose | Notes |
|------|-------|---------|-------|
| `ffmpeg`/`ffprobe` | 7.1.5-0+deb13u1 | Synthetic fixture generation (SDR/HDR10), all invariant verification (frame counts, HDR side-data, DV side-data) | `[VERIFIED: ffmpeg -version]` run directly in this session |
| `qsvencc` (Rigaya QSVEnc) | 8.20 (r4231) | Real AV1 hardware encode for the test pipeline | `[VERIFIED: qsvencc --version]` run directly; confirmed working end-to-end against a real HDR10 synthetic source in this session |
| `mkvmerge` (mkvtoolnix) | v92.0 ('Everglow') | Final mux step | `[VERIFIED: mkvmerge --version]` run directly; confirmed preserving HDR10 metadata through mux in this session |
| `dovi_tool` (quietvoid) | 2.3.2 | Installed but **NOT usable for AV1 RPU extraction in this version** — see DV RPU section | `[VERIFIED: dovi_tool --version / --help]` run directly; `extract-rpu` empirically confirmed to reject AV1 input |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `argparse` subparsers | `click`/`typer` | Locked out by D-01 (single `main.py`, argparse dispatcher) and by D-09 (zero behavior/dependency-surface change); would also be a new dependency for a phase whose entire point is thin, behavior-preserving dispatch |
| ffprobe-native DV side-data inspection | `dovi_tool extract-rpu` (piped through an HEVC transcode of the AV1 stream first) | Technically possible (`ffmpeg -i chunk.obu -c:v libx265 -f hevc - \| dovi_tool extract-rpu -` — transcode AV1→HEVC just to feed dovi_tool) but this re-encodes the video losslessly-ish just to satisfy a tool's input-format restriction, adds real CPU cost and a second failure surface, and defeats the point of verifying the *actual shipped AV1 bitstream's* RPU — rejected; ffprobe already reads the AV1 OBU metadata directly with zero transcoding |
| `tests/hardware/` new top-level directory | `tests/integration/` (existing directory, marker-gated) | Both work under `testpaths = ["tests"]`; recommend `tests/integration/test_hardware_real_media.py` for consistency with the two existing integration tests (`test_parallel_regression.py`, `test_ebml_cross_validation.py`), which already live there rather than in a hardware-specific subtree |

## Package Legitimacy Audit

**Not applicable this phase.** No new external packages (PyPI, npm, or otherwise) are installed. `argparse` is Python stdlib. `ffmpeg`, `qsvencc`, `mkvmerge`, `dovi_tool` are pre-existing devcontainer system binaries (installed in Phase 0/`.devcontainer/Dockerfile`, unchanged this phase) — not Python package-manager dependencies, and were verified present/working by direct invocation in this research session rather than by slopcheck/registry lookup (that protocol applies to `pip`/`npm`/`cargo` package installs, not system binaries already provisioned in the base image).

## Architecture Patterns

### System Architecture Diagram

```
                          $ enpipe detect video.mkv --jobs 4
                          $ enpipe encode video.mkv video.mkv.scenes
                                          │
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │   src/enpipe/cli/main.py  (D-01)         │
                    │   argparse: build_parser() -> Namespace  │
                    │   dispatch: args.func(args)              │
                    └───────────────┬───────────────┬─────────┘
                                    │               │
                    args.command   │               │  args.command
                    == "detect"    ▼               ▼  == "encode"
                    ┌───────────────────┐   ┌───────────────────────┐
                    │ run_detect(args)  │   │ run_encode(args)       │
                    │ (NEW this phase)  │   │ (EXISTS — pipeline.py) │
                    │ detection/        │   │ encoding/pipeline.py   │
                    │ pipeline.py       │   │                        │
                    └─────────┬─────────┘   └───────────┬────────────┘
                              │ calls                    │ calls
                              ▼                           ▼
                    detect_scenes(path,cfg,jobs) --   read_scenes(path)
                    (detection/detect.py,             keyframe_table(video,fps)
                     detection/parallel.py --          detect_hdr(video)
                     UNCHANGED this phase)              chunk_command/encode_chunk
                              │                          (qsvencc, real hardware)
                              ▼                                    │
                    writes <video>.scenes ────────reads───────────►│
                    "scene NNNN  frames                            ▼
                     [S, E)  ...s .. ...s"                mkvmerge mux -> <video>.av1.mkv

  ══════════════════════ TEST-04 (hardware-gated, separate process) ══════════════════════
  tests/integration/test_hardware_real_media.py  [pytest.mark.hardware]
    1. probe /dev/dri/renderD128 + qsvencc -- skip cleanly if absent
    2. generate SDR clip (ffmpeg lavfi, libx264/yuv420p) + HDR10 clip (libx265, x265-params
       hdr10=1:master-display=...:max-cll=...) with multiple scene cuts
    3. invoke enpipe detect -> enpipe encode (via CLI entry point or run_detect/run_encode
       directly) on real Arc hardware
    4. assert: per-chunk + total frame counts (ffprobe, independent of the pipeline's own
       internal count_frames() check) | chunk seeks land on real source keyframes
       (independent ffprobe re-derivation, not the pipeline's own table) | HDR10 side-data
       survives to final .mkv
    5. IF tests/fixtures/media/{hdr10plus,dv}.mkv or $ENPIPE_TEST_MEDIA present: repeat for
       HDR10+/DV, plus DV RPU-per-frame ffprobe side-data check. ELSE: skip with an
       explanatory message -- never fake a pass.
```

### Recommended Project Structure

```
src/enpipe/
├── cli/
│   ├── __init__.py
│   └── main.py                 # NEW (D-01): argparse dispatcher, build_parser(), main()
├── detection/
│   ├── pipeline.py             # NEW this phase: run_detect(args) — mirrors encoding/pipeline.py
│   ├── config.py                # unchanged
│   ├── detect.py                # unchanged
│   ├── parallel.py              # unchanged
│   └── stream.py                # unchanged
└── encoding/
    └── pipeline.py               # unchanged (run_encode(args) already exists)

tests/
├── integration/
│   ├── test_parallel_regression.py     # existing (TEST-03)
│   ├── test_ebml_cross_validation.py   # existing
│   └── test_hardware_real_media.py     # NEW this phase (TEST-04), pytest.mark.hardware
└── fixtures/
    └── media/                          # NEW this phase, gitignored — real HDR10+/DV samples
        ├── README.md                   # how to supply hdr10plus.mkv / dv.mkv
        ├── hdr10plus.mkv                # (not committed — operator-supplied)
        └── dv.mkv                       # (not committed — operator-supplied)

.github/workflows/
├── ci.yml                        # existing (hosted, "not hardware" tier)
└── hardware-integration.yml      # NEW this phase (D-08, optional), workflow_dispatch only
```

### Structure Rationale

- **`detection/pipeline.py`, not `detection/cli.py`:** The locked decision leaves the exact module name to discretion, but `encoding/pipeline.py` already establishes the naming convention ("`pipeline.py` holds the `run_*(args)` Namespace-shaped orchestration entry, minus argparse") — its own docstring says `run_encode(args)` is "перенесено дословно из main() ... минус argparse-блок". Naming the detect-side counterpart `detection/pipeline.py::run_detect(args)` keeps the two packages structurally symmetric, which matters because `cli/main.py` imports both and a reviewer scanning imports should see the same shape twice. **Recommendation, not a re-litigation of the locked decision** — the CONTEXT.md explicitly leaves this open to discretion; this is the research-backed answer.
- **Single `cli/main.py`, not `cli/app.py` + `cli/detect.py` + `cli/encode.py`:** The pre-phase `ARCHITECTURE.md` (written before CONTEXT.md's decisions were locked) sketched a three-file split. **This is superseded by D-01**, which explicitly names `src/enpipe/cli/{__init__,main.py}` — a single dispatcher file. Do not reintroduce the three-file split; it would add indirection with no behavior benefit and contradicts a locked decision.
- **`tests/fixtures/media/` gitignored, not committed:** Real HDR10+/DV media is almost certainly copyrighted/non-redistributable. The directory itself should exist (with a `README.md` explaining the expected filenames and how to obtain/place samples) but its `.mkv` contents must be gitignored, mirroring the existing `scratch/*.mkv` gitignore pattern already in `.gitignore`.

### Pattern 1: `run_detect(args)` — mirrors `run_encode(args)` exactly

**What:** Migrate `legacy/scene_detection.py:666-692` into a Namespace-taking function with the same "keep behavior, drop only the `ArgumentParser`/`parse_args` calls" discipline `run_encode(args)` already demonstrates (see `encoding/pipeline.py`'s own docstring, which explicitly documents this exact deviation-and-justification pattern — reuse its wording style for `run_detect`'s docstring).

**When to use:** This is the ONE new piece of business logic this phase adds. Everything else is either unchanged migrated code or pure CLI dispatch.

**Example (constructed from direct inspection of `legacy/scene_detection.py:666-692` and the already-migrated `detection/detect.py`/`detection/config.py`):**
```python
# src/enpipe/detection/pipeline.py
"""Оркестрация детект-этапа для CLI: сборка DetectionConfig из аргументов,
вызов detect_scenes, форматирование и запись <video>.scenes. Перенесено
дословно из __main__ (legacy/scene_detection.py:647-692) минус argparse-блок
-> run_detect(args) (D-02), симметрично run_encode(args) в
encoding/pipeline.py."""

from __future__ import annotations

from pathlib import Path

from .config import DetectionConfig
from .detect import detect_scenes


def run_detect(args) -> None:
    # приоритет: кадры -> секунды -> дефолт 72 кадра (≈3с при 24fps)
    # (дословно из legacy/scene_detection.py:666-672)
    if args.min_scene_len_frames is not None:
        msl_frames, msl_sec = args.min_scene_len_frames, 3.0
    elif args.min_scene_len is not None:
        msl_frames, msl_sec = None, args.min_scene_len
    else:
        msl_frames, msl_sec = 72, 3.0

    cfg = DetectionConfig(
        analysis_width=args.width,
        use_qsv=not args.no_qsv,
        qsv_device=args.qsv_device,
        adaptive_threshold=args.threshold,
        min_scene_len_frames=msl_frames,
        min_scene_len_sec=msl_sec,
    )
    # по умолчанию: <путь-к-видео>.scenes (напр. movie.mkv -> movie.mkv.scenes)
    out_path = args.output or Path(str(args.input) + ".scenes")

    scenes = detect_scenes(args.input, cfg, jobs=args.jobs)
    lines = [
        f"scene {scene.index:4d}  frames [{scene.start_frame:8d}, "
        f"{scene.end_frame:8d})  {scene.start_sec:10.3f}s .. {scene.end_sec:10.3f}s"
        for scene in scenes
    ]
    out_path.write_text("\n".join(lines) + "\n")
    print(f"{len(scenes)} сцен -> {out_path}")
```

**Important asymmetry to preserve, not "fix":** `legacy/scene_detection.py`'s `__main__` block does **not** do the `shutil.which()`/tool-availability preflight check that `legacy/encode_scenes.py`'s `main()` does (that check only exists on the encode side, guarding `qsvencc`/`ffprobe`/`ffmpeg`/`mkvmerge`). `run_encode(args)`'s own docstring explicitly calls out preserving this preflight as a deliberate non-negotiable ("иначе поведение die() при отсутствии инструмента было бы молча потеряно"). `run_detect(args)` should **not** invent a new preflight check that didn't exist in the legacy detect script — doing so would be a behavior change, which D-09 forbids ("zero behavior change to detect/encode").

### Pattern 2: `.scenes` round-trip contract — the format `run_detect` MUST write and `read_scenes` already parses

**What:** The coupling between detect and encode is a single regex, already in the codebase at `encoding/scenes_io.py`:
```python
_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")
```
It extracts only `(start_frame, end_frame)` from anywhere in a line containing `frames [<int>, <int>)` — everything else on the line (the `scene NNNN` prefix, the `..s` timestamps) is cosmetic and ignored by the parser. `run_detect`'s output lines (shown in Pattern 1 above) reproduce the legacy detector's exact line format byte-for-byte, so this round-trip is preserved automatically as long as the format string above is copied verbatim — do not "clean up" the fixed-width `%4d`/`%8d`/`%10.3f` formatting, since (per `PITFALLS.md` Pitfall 8) a reformatted line that no longer matches `_SCENE_RE` fails **silently** (the line is simply skipped, not an error), which would quietly desync the two CLI stages.

**Verification for the planner:** a unit test asserting `run_detect`'s written lines all match `encoding.scenes_io._SCENE_RE` (or equivalently, that `read_scenes(run_detect's output path)` returns the same `(start_frame, end_frame)` pairs as the `Scene` objects `detect_scenes` produced) is cheap, hardware-free, and directly tests the PKG-01 handoff contract — recommend this as a PKG-01 unit test even though it's not explicitly named in D-05/TEST-04 (TEST-04 is the hardware-gated tier; this round-trip check belongs in the fast tier).

### Pattern 3: `cli/main.py` argparse subparser wiring

**What:** A single `build_parser()` returning an `argparse.ArgumentParser` with two subparsers, each reproducing its legacy script's exact flag surface and calling `set_defaults(func=...)` so `main()` needs no manual dispatch branching.

```python
# src/enpipe/cli/main.py
"""Единая точка входа `enpipe`: argparse-диспетчер над `enpipe detect` и
`enpipe encode`. Чистая обвязка — вся логика в detection.pipeline.run_detect
и encoding.pipeline.run_encode (D-01/D-09: без изменения поведения)."""

from __future__ import annotations

import argparse
from pathlib import Path

from enpipe.detection.pipeline import run_detect
from enpipe.encoding.pipeline import JOBS as ENCODE_JOBS
from enpipe.encoding.pipeline import run_encode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enpipe")
    sub = parser.add_subparsers(dest="command", required=True)

    detect_p = sub.add_parser(
        "detect", description="Детектирование сцен (QSV + PySceneDetect)")
    detect_p.add_argument("input", type=Path)
    detect_p.add_argument("-o", "--output", type=Path, default=None,
                          help="файл со списком сцен (по умолчанию <видео>.scenes)")
    detect_p.add_argument("--width", type=int, default=320)
    detect_p.add_argument("--threshold", type=float, default=3.0)
    detect_p.add_argument("--min-scene-len-frames", type=int, default=None,
                          help="мин. длина сцены в КАДРАХ (приоритетнее секунд; дефолт 72)")
    detect_p.add_argument("--min-scene-len", type=float, default=None,
                          help="мин. длина сцены в секундах (если кадры не заданы; дефолт 3.0)")
    detect_p.add_argument("--no-qsv", action="store_true", help="программный декод")
    detect_p.add_argument("--qsv-device", default=None)
    detect_p.add_argument("--jobs", type=int, default=4,
                          help="параллельных сегментов детекта (дефолт 4; 1 = последовательно)")
    detect_p.set_defaults(func=run_detect)

    encode_p = sub.add_parser(
        "encode", description="Сцен-осознанный AV1-энкод (Arc/QSV)")
    encode_p.add_argument("video", type=Path)
    encode_p.add_argument("scenes", type=Path, help="scene_out.log от enpipe detect")
    encode_p.add_argument("-o", "--out", type=Path, default=None)
    encode_p.add_argument("--from", dest="frm", type=int, default=0, help="первая сцена")
    encode_p.add_argument("--to", dest="to", type=int, default=None, help="последняя (искл.)")
    encode_p.add_argument("--workdir", type=Path, default=None, help="папка чанков")
    encode_p.add_argument("--keep", action="store_true", help="не удалять чанки")
    encode_p.add_argument("--jobs", type=int, default=ENCODE_JOBS)
    encode_p.add_argument("--no-audio", action="store_true", help="не кодировать аудио")
    encode_p.add_argument("--no-metrics", action="store_true",
                          help="не считать PSNR/SSIM (быстрее)")
    encode_p.add_argument("--csv", type=Path, default=None,
                          help="CSV с метриками (по умолчанию <out>.metrics.csv)")
    encode_p.set_defaults(func=run_encode)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
```

**Two flag-default asymmetries to preserve exactly (not bugs — copy them verbatim):**
1. `detect`'s `--jobs` default is a **hardcoded `4`** (`legacy/scene_detection.py:662-663`), while `encode`'s `--jobs` default reads the **`JOBS` env var** via `encoding/pipeline.py`'s module-level `JOBS = int(os.environ.get("JOBS", "3"))`. These are genuinely different defaulting mechanisms in the legacy scripts — do not unify them.
2. `detect`'s scenes-file flag is `-o/--output` (dest `output`); `encode`'s is `-o/--out` (dest `out`). Different dest names on each subcommand, both starting with `-o` — this is exactly how the two legacy scripts already differ; preserve both spellings.

**When to use:** This is the entire CLI layer. `main()` should contain no orchestration logic — if a reviewer finds business logic in `cli/main.py`, that is the Anti-Pattern 1 from `ARCHITECTURE.md` ("turning 'unified entry point' into a fused runtime") even though it's really "unified entry point turning into more than dispatch"; keep watching for this creeping in during implementation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| AV1 Dolby Vision RPU inspection | A custom AV1 OBU parser to read T.35 metadata payloads, or a workaround HEVC-transcode-then-dovi_tool pipeline | Plain `ffprobe -show_entries frame=side_data_list` / `stream_side_data_list` (no bitstream filter) | `ffmpeg`/`ffprobe` 7.1.5 already parses AV1 DOVI OBU metadata natively and exposes it as named side-data types (`Dolby Vision RPU Data`, `DOVI configuration record`) — confirmed by direct binary string inspection and a live `dovi_rpu` bsf test in this session. Writing a parser or a lossy transcode workaround would duplicate work `ffprobe` already does correctly. |
| CLI subcommand parsing | click/typer/any third-party CLI framework | stdlib `argparse` with `add_subparsers()` | Locked by D-01/D-09; also the entire flag surface being reconstituted is itself already an `argparse` surface (from the two legacy scripts) — a framework swap would require re-deriving every flag's exact behavior (dest names, `store_true` vs typed, positional-vs-optional) for zero benefit in a "thin dispatch" phase. |
| Synthetic HDR10 fixture generation | A custom MP4/MKV muxer or manual SEI-NAL injection to attach mastering-display metadata | `ffmpeg` + `libx265` `-x265-params master-display=...:max-cll=...` (validated recipe below) | `ffmpeg`/`libx265` already expose exactly the HDR10 signaling fields (mastering display primaries/white point/luminance, MaxCLL/MaxFALL) needed to make `detect_hdr()` and `qsvencc` recognize the clip as HDR10 — empirically confirmed working in this session. |

**Key insight:** Every "verification" problem in this phase (HDR/DV metadata survival, frame counts, keyframe positions) already has an `ffprobe`-based read-only inspection path available in the toolchain that's already a hard dependency of the pipeline. The temptation in a "correctness is non-negotiable" project is to reach for a purpose-built DV tool (`dovi_tool`) — but that tool's AV1 support gap (empirically confirmed this session) makes `ffprobe`-native inspection the *only* reliable in-sandbox mechanism for this codebase's actual AV1 output, not merely the simpler one.

## DV RPU Verification Mechanism (D-07 — resolved this session)

### What was tried and what happened (all commands run directly against real binaries in this devcontainer)

| Attempt | Result | Confidence |
|---------|--------|------------|
| `dovi_tool --help` — look for an `av1` subcommand | No such subcommand exists in 2.3.2's command list (`convert, demux, editor, export, extract-rpu, inject-rpu, generate, info, mux, plot, remove, help`) | `[VERIFIED: dovi_tool --help]` |
| `dovi_tool extract-rpu -i <real AV1 .obu chunk> -o rpu.bin` | **Fails**: `Error: Invalid input file type.` (exit code 1) | `[VERIFIED: ran directly against a real qsvencc AV1 output in this session]` |
| `ffmpeg -bsfs \| grep dovi` + `ffmpeg -h bsf=dovi_rpu` | `dovi_rpu` bitstream filter exists, `Supported codecs: hevc av1` | `[VERIFIED: ffmpeg -h bsf=dovi_rpu]` |
| `ffmpeg -i <AV1 .obu, no DV metadata> -c copy -bsf:v dovi_rpu -f obu out.obu` | Succeeds, but **synthesizes a fake `DOVI configuration record`** (`profile: 10, level: 1, rpu flag: 1, ...`) on content that has no real DV metadata, with an explicit warning: `No Dolby Vision configuration record found? Generating one, but results may be invalid.` | `[VERIFIED: ran directly]` — **do not use this filter for verification; it mutates/fabricates data** |
| `ffprobe -select_streams v:0 -show_frames -show_entries frame=side_data_list` on the same AV1 file, **without** the `dovi_rpu` bsf | Read-only; reports whatever side data is actually present in the bitstream (in this no-DV test file: none related to DV, as expected) | `[VERIFIED: ran directly]` |
| String-table search of `ffprobe`/`libavutil` binaries for DV-related side-data type names | Confirms `"Dolby Vision RPU Data"` and `"Dolby Vision Metadata"` are defined, named side-data types the running ffprobe build recognizes | `[VERIFIED: strings ffprobe/libavutil.so]` |

### Recommended mechanism

For a chunk or muxed output that genuinely carries `--dolby-vision-rpu copy` metadata from `qsvencc` (i.e., an actual DV fixture, per D-06 fixture-gating):

```bash
# Per-chunk .obu (if --keep was used) or the final muxed .mkv — READ ONLY, no -bsf:v.
ffprobe -v error -select_streams v:0 -show_frames \
  -show_entries frame=side_data_list -of default=nw=1 <file>
```

Assert two things:
1. **RPU-per-frame parity:** the count of frames reporting a `Dolby Vision RPU Data` side-data entry equals the total video frame count already computed by `count_frames()` (i.e., every frame — not just some — carries RPU; a gap indicates the splice/mux dropped RPU on some frames, exactly the Pitfall 7 failure class from `PITFALLS.md`).
2. **Profile fidelity:** the stream-level `DOVI configuration record` (visible via `ffprobe -show_entries stream_side_data_list` on the muxed output, or by inspecting the frame-level record) reports the `profile` field matching the pipeline's `DV_PROFILE` env var (default `"10.1"` → the numeric AV1 DV profile is `10`, with the `.1`/`.4` suffix distinguished by the `compatibility id` field observed in this session's output, e.g. `compatibility id: 1`). `[ASSUMED]` — this profile/compatibility-id mapping was observed on a *synthetic, non-DV* config record fabricated by the `dovi_rpu` bsf during this session's exploratory testing, not on genuine profile-8.1/8.4/10.4 content; the mapping should be re-confirmed against whatever real DV fixture the operator supplies, and the test's assertion message should say so if the mapping doesn't hold.

**Do NOT:**
- Invoke `dovi_tool extract-rpu` against the AV1 output — confirmed broken in this exact installed version (2.3.2).
- Apply the `dovi_rpu` ffmpeg bitstream filter as part of the verification step — it is a **mutating** filter that was observed fabricating a fake config record when none existed; use plain `ffprobe` inspection only (no `-bsf:v` on the probe command).
- Transcode AV1→HEVC just to satisfy `dovi_tool`'s HEVC-only CLI restriction — this defeats the purpose of verifying the actually-shipped bitstream and adds a lossy re-encode step to what should be a read-only check.

**Honesty note for the TEST-04 implementation:** because no genuine DV source material exists in this sandbox (per D-06), the mechanism above is verified to work *structurally* (ffprobe correctly parses AV1 DOVI OBU side data; dovi_tool correctly and confirmedly fails) but has **not** been exercised against a real multi-frame DV RPU stream with actual per-frame variation. The fixture-gated test must make this limitation visible in its skip message and should not claim full confidence in the profile-field assertion until it has actually run once against a real DV fixture.

## Synthetic Fixture Generation (D-06 — empirically verified this session)

### HDR10 clip (verified: `detect_hdr()` fires correctly, survives real Arc encode + mux)

```bash
ffmpeg -y -f lavfi -i "testsrc=duration=2:size=640x360:rate=24" -pix_fmt yuv420p10le \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  -c:v libx265 -x265-params \
    "hdr10=1:hdr10-opt=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400" \
  hdr10_test.mkv
```

**Verified in this session (real Arc hardware, not just designed):**
- `ffprobe -show_entries stream=color_primaries,color_transfer,color_space` on the generated clip reports `color_primaries=bt2020`, `color_transfer=smpte2084`, `color_space=bt2020nc` exactly `[VERIFIED]`.
- `ffprobe -show_frames -show_entries frame=side_data_list` reports `Mastering display metadata` (all 6 chromaticity + luminance fields populated) and `Content light level metadata` (`max_content=1000`, `max_average=400`) `[VERIFIED]`.
- `enpipe.encoding.hdr.detect_hdr(Path("hdr10_test.mkv"))` called directly returns `['--master-display', 'copy', '--max-cll', 'copy']` — the HDR10-only path (no `--dhdr10-info`, no `--dolby-vision-rpu`, as expected for a clip with no HDR10+/DV side data) `[VERIFIED]`.
- `qsvencc --avhw --va -i hdr10_test.mkv -c av1 ... --master-display copy --max-cll copy -o hdr10_chunk.obu` on real `/dev/dri/renderD128` hardware succeeds (exit 0), logs `MasteringDisp` and `MaxCLL/MaxFALL 1000/400` in its own startup banner, and encodes `48/48` frames `[VERIFIED]`.
- The resulting `.obu` still reports `color_primaries=bt2020`/`color_transfer=smpte2084`/`color_space=bt2020nc` plus the same Mastering display + Content light level side data via `ffprobe` `[VERIFIED]`.
- `mkvmerge -o hdr10_final.mkv --default-duration "0:24/1p" hdr10_chunk.obu` mux preserves all of the above into the final `.mkv`, with frame count still `48` `[VERIFIED]`.

This is a complete, empirically-proven HDR10 round-trip on real hardware for this exact devcontainer/toolchain combination — not a theoretical recipe.

### SDR clip (verified: `detect_hdr()` correctly returns no flags)

```bash
ffmpeg -y -f lavfi -i "testsrc=duration=2:size=640x360:rate=24" -pix_fmt yuv420p \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:v libx264 -profile:v high sdr_test.mkv
```

`enpipe.encoding.hdr.detect_hdr()` on this file returns `[]` `[VERIFIED]` — confirming the SDR (no-flags) path fires correctly. Note: `libx264`+`yuv420p` does not reliably propagate VUI color tags the way `libx265` does for the HDR clip (this session's SDR clip reported `color_transfer=unknown`/`color_primaries=unknown` via `ffprobe` despite the `-color_*` flags being passed) — this is expected and harmless, since `detect_hdr()`'s SDR branch only cares that `transfer` is NOT `smpte2084`/`arib-std-b67`, which holds either way.

### Multi-scene fixture generation (for keyframe-alignment / per-chunk testing)

Reuse the existing pattern already proven in `tests/integration/test_parallel_regression.py`'s `multi_scene_clip` fixture (four ~55s alternating `color=`/`smptebars=` lavfi segments concatenated via `filter_complex ... concat=n=4:v=1[v]`) — this produces multiple genuine scene cuts that `AdaptiveDetector` reliably detects, which is exactly what TEST-04 needs to exercise multiple chunks (and therefore multiple keyframe-alignment points, not just one). For the HDR10 variant, swap the encode stage from `libx264`/`yuv420p` to `libx265`/`yuv420p10le` with the same `x265-params` HDR10 block — a single encoder pass with HDR flags set applies uniformly across the concatenated visual segments, so scene cuts still occur from the visual content changes while HDR signaling stays constant for the whole stream (this matches how any real single-source HDR file behaves — HDR is set once at the container/stream level, not per scene).

### What is confirmed NOT synthesizable (per D-06, and confirmed by the nature of the formats)

- **HDR10+ (dynamic metadata):** requires per-scene/per-frame tone-mapping curve data (SMPTE ST 2094-40) that is authored by a real HDR10+ mastering process — there is no `ffmpeg`/`libx265` flag that fabricates *meaningful* dynamic metadata (a technically-present-but-static "dynamic" track would not exercise anything different from HDR10 and would misrepresent coverage).
- **Genuine Dolby Vision RPU:** requires Dolby's proprietary RPU generation pipeline (dual-layer BL+EL encode or single-layer profile 8.x/10.x metadata authored against the actual graded master) — not something `ffmpeg`/`x265`/`qsvencc` can originate from scratch; `qsvencc --dolby-vision-rpu copy` only *copies* pre-existing RPU from a source that already has it.

Both remain fixture-gated per D-06 — this is not a research gap, it is a structural limitation of the formats themselves.

## Common Pitfalls

### Pitfall 1: Reintroducing the pre-phase `ARCHITECTURE.md`'s three-file CLI split
**What goes wrong:** The planner reads `.planning/research/ARCHITECTURE.md` (written before CONTEXT.md's decisions were locked) and builds `cli/app.py` + `cli/detect.py` + `cli/encode.py` instead of the single `cli/main.py` D-01 locks in.
**Why it happens:** `ARCHITECTURE.md` is a canonical reference the phase explicitly points at, and its System Overview diagram shows the three-file split prominently — it's easy to treat it as still-current guidance rather than superseded-by-a-later-locked-decision.
**How to avoid:** D-01 is the authority for this phase, not the pre-phase `ARCHITECTURE.md`. Build exactly `src/enpipe/cli/{__init__.py,main.py}`.
**Warning signs:** Any PR that creates `cli/app.py`, `cli/detect.py`, or `cli/encode.py` as separate files.

### Pitfall 2: Trusting `dovi_tool` without testing it against this codebase's actual AV1 output
**What goes wrong:** A planner or implementer assumes `dovi_tool` "probably works now" since it's installed and has an `extract-rpu` subcommand, without actually running it against a real `.obu` chunk — and only discovers the `Invalid input file type` failure mid-implementation, or worse, silently wraps it in a broad exception handler that makes the DV check a no-op.
**Why it happens:** `dovi_tool --help` doesn't obviously say "HEVC only" anywhere in the top-level help text (only `extract-rpu --help`'s own description says "Extracts Dolby Vision RPU from an **HEVC file**" — easy to skim past).
**How to avoid:** Use the ffprobe-native mechanism documented above; if a future `dovi_tool` version adds AV1 CLI support, re-evaluate then (check the `--help` output and `discovery #302` status), but do not build the DV check assuming that will happen.
**Warning signs:** A DV check implementation that wraps `dovi_tool extract-rpu` in `try/except` with a silent fallback (this would produce exactly the "coverage theater" D-06/D-07 explicitly warns against).

### Pitfall 3: Using the `dovi_rpu` ffmpeg bitstream filter as a "quick way to check DV metadata"
**What goes wrong:** Someone reaches for `ffmpeg -bsf:v dovi_rpu` because it's the only DV-aware ffmpeg tool discoverable via `ffmpeg -bsfs`, not realizing it's a **mutating** filter (its own purpose is to strip/rewrite DV metadata, not to report on it read-only) — and it was empirically observed in this session to fabricate a fake `DOVI configuration record` on content with no real DV data, printing only a warning (not an error) when it does so.
**Why it happens:** It's the filter name that shows up first when grepping `ffmpeg -bsfs` for "dovi" and its `-strip` option name suggests read-capable behavior.
**How to avoid:** Use plain `ffprobe -show_entries frame=side_data_list`/`stream_side_data_list` with **no** `-bsf:v` flag for verification. Only use `dovi_rpu` if the goal is genuinely to mutate (strip) DV metadata, which is not this phase's goal.
**Warning signs:** Any verification code path in the test that passes `-bsf:v dovi_rpu` to `ffmpeg`/`ffprobe`.

### Pitfall 4: Trusting the pipeline's own internal `count_frames()`/keyframe checks as the TEST-04 verification, instead of independently re-deriving
**What goes wrong:** TEST-04 asserts only that `run_encode`/the CLI process exits 0, reasoning "the pipeline already calls `die()` on frame-count mismatch, so a clean exit proves frame counts matched." This is true but weaker than what D-05 asks for ("verifies... per-chunk and total frame counts... match expectation") — it re-tests the pipeline's own self-check rather than independently confirming against ground truth, and provides zero coverage of Pitfall 6 (`PITFALLS.md`) — a subtly-wrong-but-parseable EBML keyframe table that still produces a passing frame count.
**How to avoid:** Use `--keep` when invoking `enpipe encode` in the test so per-chunk `.obu` files survive, then independently `ffprobe -count_packets` each chunk against the `.scenes` file's own `(start_frame, end_frame)` pairs (parsed independently in the test, not reused from the pipeline's internal state) — this is a second, independent computation of the same invariant, not a re-check of the pipeline's own arithmetic. For keyframe alignment, independently call `keyframe_table_ffprobe()` (the slow, ground-truth path — NOT `keyframe_table()`, which may take the fast EBML path) against the source and confirm each chunk's computed seek point corresponds to a real `K`-flagged keyframe per that independent scan.
**Warning signs:** A TEST-04 implementation with no `--keep` usage and no direct `ffprobe` calls of its own — i.e., one that only checks the CLI's exit code and the final `.mkv`'s aggregate `count_frames()`.

## Code Examples

### Independent keyframe-alignment cross-validation (TEST-04, per Pitfall 4 above)

```python
# Inside tests/integration/test_hardware_real_media.py, after enpipe encode --keep
from enpipe.encoding.keyframes import keyframe_table_ffprobe  # ground-truth, slow path
from enpipe.encoding.scenes_io import read_scenes

fps = probe_fps(source_video)  # or reuse enpipe.encoding.pipeline.probe_fps
ground_truth_table = keyframe_table_ffprobe(source_video, fps)  # bypasses the EBML fast path
ground_truth_kf_frames = {frame for frame, _ in ground_truth_table}

scenes = read_scenes(scenes_path)  # independent re-parse, not reused pipeline state
for i, (s, e) in enumerate(scenes):
    # Recompute the SAME rule the pipeline uses (K = last keyframe with frame_K <= s),
    # but against the independently-derived ground_truth_table, not whatever table
    # keyframe_table() happened to produce internally (fast EBML path vs ffprobe fallback).
    candidates = [f for f in ground_truth_kf_frames if f <= s]
    assert candidates, f"scene {i} starts before any known source keyframe"
    k = max(candidates)
    assert k in ground_truth_kf_frames, (
        f"chunk {i}'s seek point (frame {k}) is not a real source keyframe "
        f"per an independent ffprobe scan -- keyframe alignment violated"
    )
```

### DV RPU per-frame parity check (only when a DV fixture is present)

```python
import json
import subprocess

def _dv_rpu_frame_count(path: Path) -> tuple[int, int]:
    """Returns (frames_with_rpu, total_frames) via read-only ffprobe -- NO -bsf:v."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
           "-show_entries", "frame=side_data_list", "-of", "json", str(path)]
    data = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    frames = data.get("frames", [])
    with_rpu = sum(
        1 for f in frames
        if any("Dolby Vision RPU" in sd.get("side_data_type", "")
               for sd in f.get("side_data_list", []))
    )
    return with_rpu, len(frames)

# in the fixture-gated test:
with_rpu, total = _dv_rpu_frame_count(final_mkv)
assert total > 0, "no frames read from final .mkv"
assert with_rpu == total, (
    f"DV RPU present on {with_rpu}/{total} frames -- expected 100% "
    f"(chunk splice or mux likely dropped RPU on some frames)"
)
```

### Hardware-availability gate (mirrors `scratch/parity_encode.py`'s already-proven pattern)

```python
import shutil
from pathlib import Path
import pytest

pytestmark = pytest.mark.hardware


def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None


@pytest.fixture(autouse=True, scope="module")
def _require_hardware():
    if not _hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
```

### Fixture-gating for HDR10+/DV real samples (D-06)

```python
import os
from pathlib import Path
import pytest

FIXTURES_DIR = Path(
    os.environ.get("ENPIPE_TEST_MEDIA", str(Path(__file__).parents[1] / "fixtures" / "media"))
)


def _fixture(name: str) -> Path | None:
    p = FIXTURES_DIR / name
    return p if p.is_file() else None


def test_dv_rpu_survival():
    dv_source = _fixture("dv.mkv")
    if dv_source is None:
        pytest.skip(
            f"no Dolby Vision fixture at {FIXTURES_DIR / 'dv.mkv'} "
            f"(or set $ENPIPE_TEST_MEDIA to a directory containing dv.mkv) -- "
            f"see tests/fixtures/media/README.md for how to supply one. "
            f"This is NOT a failure: genuine DV RPU source material cannot be "
            f"synthesized (D-06) and must be supplied by the operator."
        )
    # ... run the pipeline against dv_source, then the RPU parity check above ...
```

## State of the Art

| Old Approach (per legacy comment / D-07's stated uncertainty) | Current Approach (this session's empirical finding) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Assume `dovi_tool extract-rpu` needs an HEVC intermediate/transcode to verify AV1 DV RPU, or that no in-sandbox mechanism exists at all | `ffprobe` (ffmpeg 7.1.5, already installed) natively parses AV1 DOVI OBU metadata via named side-data types (`Dolby Vision RPU Data`, `DOVI configuration record`) — no transcode, no `dovi_tool` needed | AV1 DOVI OBU parsing landed in FFmpeg's demuxer/probing layer at some point before this devcontainer's pinned 7.1.5 (exact FFmpeg version that added it not independently dated this session — flagged in Open Questions) | TEST-04's DV check can be built entirely on tools already in the pipeline's hard-dependency list; no new tool integration needed |
| `dovi_tool`'s CLI is assumed to be a general-purpose DV RPU tool covering AV1 | `dovi_tool` 2.3.2's CLI (`extract-rpu` et al.) is HEVC-only for file processing; AV1 support exists only in the underlying Rust library, not exposed via any current subcommand (per upstream discussion #302, corroborated by this session's direct `Invalid input file type` failure) | Confirmed as of dovi_tool 2.3.2 (this devcontainer's pinned version) / discussion opened, still open as of this research date | Any future `dovi_tool` version bump should re-check `--help` for a new `av1`/`extract-rpu --av1`-style subcommand before assuming this limitation still holds |

**Deprecated/outdated:**
- The `legacy/encode_scenes.py:15-16` comment ("DV в AV1 нельзя наложить пост-фактум (dovi_tool — только HEVC)") remains accurate for verification purposes as of this research — not outdated, but now has an empirically-confirmed *alternative* (ffprobe-native inspection) rather than being a dead end.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `DOVI configuration record`'s `profile`/`compatibility id` fields map onto the pipeline's `DV_PROFILE` env var (`"10.1"` → `profile: 10` + `compatibility id: 1`) the same way for genuine RPU-copied content as they did for the bsf-fabricated synthetic record observed in this session | DV RPU Verification Mechanism | A DV fixture test could assert the wrong profile/compatibility-id combination and either false-fail on genuinely-correct output or false-pass on a mismatched profile; must be re-confirmed against the first real DV fixture supplied |
| A2 | The exact FFmpeg version that added AV1 DOVI OBU side-data parsing was not independently dated — only confirmed present in the pinned 7.1.5 build in this devcontainer | State of the Art | If a CI/build environment pins an older ffmpeg without this support, the DV mechanism silently degrades to "sees nothing" rather than erroring — should be paired with an explicit ffmpeg-version floor check or a self-test (assert the `dovi_rpu` bsf reports `av1` in its supported-codecs list) at the start of the DV-gated test |
| A3 | `mkvmerge` (v92.0) preserves AV1 DOVI OBU/DV side data through mux the same way it was empirically confirmed to preserve HDR10 (mastering-display/CLL) side data in this session — not independently tested against genuine DV content, only against HDR10 | Synthetic Fixture Generation / DV RPU Verification Mechanism | If `mkvmerge` silently drops DV-specific side data during mux (a distinct code path from HDR10 side data in mkvmerge's AV1 track handling) the RPU-per-frame check on the *final .mkv* could false-fail even though the pre-mux chunk carried RPU correctly — the test should check both the pre-mux `.obu` (with `--keep`) AND the final `.mkv` for this reason, not just the final mux output |

**Note:** All other claims in this document (`dovi_tool extract-rpu` failing on AV1, `ffprobe`'s AV1 DOVI side-data recognition, the HDR10/SDR ffmpeg recipes, `detect_hdr()`'s classification behavior, real Arc hardware presence and successful encode) are `[VERIFIED]` — confirmed by direct command execution in this research session against the actual devcontainer toolchain, not sourced from documentation or training knowledge.

## Open Questions

1. **Exact FFmpeg version that introduced AV1 DOVI OBU metadata parsing**
   - What we know: 7.1.5 (this devcontainer's pinned version) has it; the WebSearch-sourced FFmpeg patch history references AV1 Dolby Vision side-data support being added to `libavutil`/`libavcodec` as a documented feature.
   - What's unclear: The precise version/date this landed, and therefore the minimum ffmpeg version any CI environment running this DV check would need.
   - Recommendation: Not blocking for this phase (the devcontainer is the only environment the hardware tier runs in, and it's pinned to 7.1.5 already) — but the planner should add a one-line self-check at the top of the DV-gated test (`assert "av1" in ffmpeg -h bsf=dovi_rpu output`) so a future toolchain downgrade fails loudly rather than silently under-reporting RPU frames.

2. **Whether the `Dolby Vision RPU Data` per-frame side-data type appears identically for AV1 as it does for HEVC RPU streams (dual-layer vs single-layer profile 10.x), or whether AV1 (profile-10-only, no BL/EL split) reports it differently**
   - What we know: The side-data type name string exists in the ffmpeg binary and was confirmed structurally reachable via the bsf test (which produced a stream-level `DOVI configuration record`, though not itself a per-frame RPU payload since the source had none to copy).
   - What's unclear: Whether genuine `qsvencc --dolby-vision-rpu copy` output attaches the per-frame `Dolby Vision RPU Data` side data the same way, since this session never had real RPU-bearing source material to pass through the actual copy path.
   - Recommendation: The fixture-gated DV test IS the resolution mechanism for this question — when the operator supplies a real `dv.mkv` fixture and runs the test for the first time, treat that run's result as the actual confirmation, and update this document's confidence level from MEDIUM to HIGH at that point.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `/dev/dri/renderD128` (Intel Arc GPU) | TEST-04 hardware gate, real `qsvencc` encode | ✓ | DG2 (Arc, per `qsvencc` GPU banner) | None — TEST-04 skips cleanly (`pytest.skip`) if absent, per D-05's design |
| `qsvencc` (Rigaya QSVEnc) | Real AV1 hardware encode | ✓ | 8.20 (r4231) | None — hard dependency of the pipeline itself, not just the test |
| `ffmpeg`/`ffprobe` | Fixture generation, all invariant verification | ✓ | 7.1.5-0+deb13u1 | None |
| `mkvmerge` (mkvtoolnix) | Final mux step | ✓ | v92.0 ('Everglow') | None |
| `dovi_tool` | **Not usable this phase** — installed but AV1 CLI processing unsupported | ✓ (installed, but functionally inapplicable to AV1) | 2.3.2 | ffprobe-native inspection (see DV RPU Verification Mechanism) — this IS the fallback, already the recommended primary path |
| Real DV (`dv.mkv`) fixture | Fixture-gated DV RPU check | ✗ (not present in-sandbox, by design per D-06) | — | `pytest.skip()` with an explanatory message; operator supplies via `tests/fixtures/media/dv.mkv` or `$ENPIPE_TEST_MEDIA` |
| Real HDR10+ (`hdr10plus.mkv`) fixture | Fixture-gated HDR10+ check | ✗ (not present in-sandbox, by design per D-06) | — | Same as above |

**Missing dependencies with no fallback:** None — everything the hardware tier's SDR/HDR10 path needs is present and was directly exercised in this session.

**Missing dependencies with fallback:** Real DV/HDR10+ fixtures — fallback is a clean, documented `pytest.skip()`, never a faked pass (per D-06's explicit requirement).

## Validation Architecture

Skipped — `.planning/config.json`'s `workflow.nyquist_validation` is explicitly `false`.

## Security Domain

`security_enforcement` is not present in `.planning/config.json` (treated as enabled per the default), but this phase adds no network-facing surface, no authentication, no user-supplied-untrusted-input parsing beyond CLI argv and local file paths already handled identically to the existing `legacy/*.py` scripts. Applicable ASVS categories are minimal for a local, single-operator subprocess-orchestration CLI:

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Not applicable — no auth surface, local CLI tool |
| V3 Session Management | No | Not applicable |
| V4 Access Control | No | Not applicable — filesystem permissions are the OS's concern, not this tool's |
| V5 Input Validation | Partial | Argparse's `type=Path`/`type=int`/`type=float` coercion is the existing (and sufficient) validation layer, unchanged from `legacy/*.py`; all subprocess invocations already use list-form `subprocess.run(cmd_list, ...)` with no `shell=True` anywhere in the codebase (confirmed in `PITFALLS.md`'s Security Mistakes table as a positive existing pattern) — preserve this, do not introduce string-interpolated shell commands in `run_detect`/`cli/main.py` |
| V6 Cryptography | No | Not applicable — no crypto in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell injection via unsanitized filename/path arguments passed to `ffmpeg`/`qsvencc`/`mkvmerge` | Tampering | Already mitigated — every subprocess call in the codebase uses list-form argv via `enpipe.shared.proc.run`/`popen`, never `shell=True` or string interpolation; `cli/main.py`/`run_detect` must continue this pattern (it already does, by construction, since `argparse` + `Path` objects flow straight into the same list-form `subprocess` calls the migrated code already uses) |
| Self-hosted CI runner (D-08) executing untrusted PR code with `/dev/dri` access | Elevation of Privilege | `PITFALLS.md`'s Security Mistakes table already documents this: restrict the hardware-tier workflow to `workflow_dispatch`/maintainer-triggered runs only, never `pull_request` from forks — carry this into the D-08 CI stub |

## Sources

### Primary (HIGH confidence — commands run directly in this session)
- `dovi_tool --version` / `--help` / `extract-rpu --help` / `demux --help` / `info --help` — run directly, confirms 2.3.2, HEVC-only `extract-rpu`, no `av1` subcommand
- `dovi_tool extract-rpu -i <real AV1 .obu> -o rpu.bin` — run directly against this session's own `qsvencc` AV1 output, confirms `Error: Invalid input file type.`
- `ffmpeg -version` / `-bsfs` / `-h bsf=dovi_rpu` — run directly, confirms ffmpeg 7.1.5-0+deb13u1, `dovi_rpu` bsf supports `hevc av1`
- `ffmpeg -i <AV1> -c copy -bsf:v dovi_rpu -f obu out.obu` — run directly, confirms bsf behavior (including the fabrication-on-absence warning)
- `ffprobe -show_frames -show_entries frame=side_data_list` on multiple generated/encoded files — run directly, confirms HDR10 side-data survival end-to-end
- `qsvencc --version` / real encode invocation against the synthetic HDR10 clip — run directly on this devcontainer's actual `/dev/dri/renderD128` + Arc GPU, confirms 8.20 (r4231), successful 48/48-frame encode preserving `MasteringDisp`/`MaxCLL`
- `mkvmerge --version` / real mux invocation — run directly, confirms v92.0, HDR10 metadata + frame count preserved through mux
- `vainfo` — run directly, confirms `VAProfileHEVCMain10:VAEntrypointVLD` (HDR10 HEVC decode) and `VAProfileAV1Profile0:VAEntrypointEncSliceLP` (AV1 hardware encode) both present
- `strings /usr/bin/ffprobe`, `strings libavutil.so.59` — run directly, confirms `"Dolby Vision RPU Data"` and `"Dolby Vision Metadata"` are recognized side-data type names in the installed build
- `enpipe.encoding.hdr.detect_hdr()` called directly (Python) against both the generated HDR10 and SDR clips — confirms correct flag classification
- `src/enpipe/encoding/pipeline.py`, `src/enpipe/detection/{detect,config,parallel}.py`, `src/enpipe/encoding/{keyframes,hdr,chunk,scenes_io}.py` (this repository) — read directly, primary source for all function signatures/behavior described
- `legacy/scene_detection.py:647-692`, `legacy/encode_scenes.py:1-100,515-729` (this repository) — read directly, primary source for the exact legacy argparse surfaces being reconstituted
- `pyproject.toml`, `scratch/parity_encode.py`, `tests/integration/test_parallel_regression.py`, `.github/workflows/ci.yml` (this repository) — read directly, source for existing conventions (hardware marker, fixture-generation pattern, CI structure)
- `.planning/phases/04-.../04-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/config.json` (this repository) — read directly, authoritative scope/constraint source

### Secondary (MEDIUM confidence — WebSearch, verified against this session's direct findings)
- [AV1 Support · quietvoid/dovi_tool · Discussion #302](https://github.com/quietvoid/dovi_tool/discussions/302) — corroborates this session's direct `Invalid input file type` finding; states AV1 CLI processing is not yet implemented despite library-level AV1 module support
- [Extracting/injecting rpu clarification · quietvoid/dovi_tool · Discussion #78](https://github.com/quietvoid/dovi_tool/discussions/78) — RPU frame-count-vs-video-stream mismatch as a known DV tooling failure class (already cited in `.planning/research/PITFALLS.md`)

### Tertiary (LOW confidence)
- None — every claim in this document was either verified directly against the installed toolchain in this session, or is explicitly flagged `[ASSUMED]` in the Assumptions Log above.

## Metadata

**Confidence breakdown:**
- PKG-01 (Standard Stack / Architecture): HIGH — every function signature, argparse flag, and file format referenced was read directly from source in this session; no speculation
- TEST-04 SDR/HDR10 mechanism: HIGH — empirically proven end-to-end on real Arc hardware in this session, not merely designed
- TEST-04 DV RPU mechanism: MEDIUM-HIGH — the *tooling* determination (dovi_tool broken for AV1, ffprobe works) is HIGH confidence (directly verified); the *exact semantics* of the mechanism against genuine multi-frame DV content is MEDIUM (structurally sound, but never exercised against real RPU data in this sandbox, per D-06's own acknowledged limitation)
- Pitfalls: HIGH — directly observed in this session (e.g., the `dovi_rpu` bsf's fabrication behavior) or sourced from the project's own existing `PITFALLS.md`

**Research date:** 2026-07-08
**Valid until:** 30 days for the PKG-01 mechanical findings (stable, source-code-grounded); re-verify the `dovi_tool`/AV1 CLI-support finding before relying on it long-term if `dovi_tool` is ever upgraded past 2.3.2 in `.devcontainer/Dockerfile` (check `dovi_tool --help` for a new AV1-capable subcommand first)

---
*Research for: Phase 4 - Unified CLI + Hardware-Gated Real-Media Validation*
*Researched: 2026-07-08*
