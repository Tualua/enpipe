# Phase 4: Unified CLI + Hardware-Gated Real-Media Validation - Context

**Gathered:** 2026-07-08 (--auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

Add the single `enpipe` entry point over the two independently-verified stages, and validate the full pipeline end-to-end against real media on real Arc hardware — the milestone capstone:
- **PKG-01** — a unified `enpipe` console_script dispatching to `enpipe detect` / `enpipe encode` (thin argparse wrappers), preserving the two-stage `<video>.scenes` file handoff; equivalent `legacy/` invocations still work unmodified.
- **TEST-04** — a hardware-gated integration test running the full detect → encode → mux pipeline against real media on Intel Arc, verifying per-chunk and total frame counts, keyframe alignment, and DV RPU survival, covering SDR / HDR10 / HDR10+ / Dolby Vision sources (see the source-material reality note in decisions).

**This is the final milestone phase.** `legacy/` remains untouched as the parity oracle. The CLI is a THIN dispatcher over the already-migrated, already-verified detect/encode stages — no behavior change to either stage.

**Explicitly NOT in this phase:** the streaming orchestrator (out of scope, PROJECT.md), v2 items (logging/typed-config/pyright/coverage/dep-automation), publishing to PyPI.
</domain>

<decisions>
## Implementation Decisions

### PKG-01 — unified CLI
- **D-01:** Create `src/enpipe/cli/{__init__,main.py}` with an argparse dispatcher exposing two subcommands: `enpipe detect <input> [flags]` and `enpipe encode <video> <scenes> [flags]`. Add `[project.scripts]` `enpipe = "enpipe.cli.main:main"` to `pyproject.toml` (the slot intentionally reserved since Phase 1).
- **D-02:** The detect subcommand needs a CLI wrapper that does NOT exist yet: migrate the `.scenes`-writing logic from `legacy/scene_detection.py`'s `__main__` block (build `DetectionConfig` from flags → `detect_scenes(input, cfg, jobs)` → format `scene NNNN ...` lines → write `<video>.scenes`) into a `run_detect(args)` in the detection package, MIRRORING the existing `run_encode(args)` in `encoding/pipeline.py`. The CLI `main` builds the argparse Namespace and calls `run_detect`/`run_encode`.
- **D-03:** Reconstitute the EXACT legacy flag surfaces (argv-compatible): detect — `input`, `-o/--output`, `--width`, `--threshold`, `--min-scene-len-frames`, `--jobs`, `--no-qsv` (→ `DetectionConfig(use_qsv=False)`), etc.; encode — `video`, `scenes`, `-o/--out`, `--from`, `--to`, `--workdir`, `--keep`, `--jobs`, `--no-audio`, `--no-metrics`, etc. (the `run_encode` Namespace attribute names). Preserve Russian help text.
- **D-04:** Preserve the two-stage `<video>.scenes` handoff: `enpipe detect video.mkv` writes `video.mkv.scenes`; `enpipe encode video.mkv video.mkv.scenes` reads it. The existing `legacy/scene_detection.py`/`legacy/encode_scenes.py` scripts must still run unmodified (they stay as the parity oracle). No fused single-command orchestrator (that is the out-of-scope streaming design).

### TEST-04 — hardware-gated real-media validation
- **D-05:** Build a `hardware`-marked integration test (excluded from the default `pytest -m "not hardware"` fast tier) that runs the FULL pipeline end-to-end on real Arc: `enpipe detect` → `enpipe encode` → final `.mkv`. It verifies the load-bearing invariants: (a) per-chunk frame counts and the concatenated total match expectation (`count_frames`/ffprobe), (b) chunk boundaries land on source keyframes (keyframe alignment), (c) for DV sources, RPU survives the chunk-splice + mux.
- **D-06:** SOURCE-MATERIAL REALITY (honest scoping): SDR and HDR10 sources can be generated synthetically with ffmpeg (bt2020/smpte2084 + mastering-display metadata for HDR10) and validated end-to-end on hardware — DO this. HDR10+ (dynamic metadata) and genuine Dolby Vision (RPU) sources CANNOT be reliably synthesized in-sandbox and require real, legally-usable content. Therefore: make the HDR10+/DV cases FIXTURE-gated — the test looks for real sample files in a documented fixtures location (dir/env var); if absent, it SKIPS cleanly with a message explaining how to supply one, and NEVER fakes a pass. The DV RPU-survival check runs only when a DV fixture is present. Document this coverage boundary explicitly; do not claim DV validation ran when no DV source existed.
- **D-07:** The DV RPU-survival mechanism is UNCERTAIN and needs research: `dovi_tool extract-rpu` is documented HEVC-only (`legacy/encode_scenes.py:15-16`), while the pipeline emits AV1 with `qsvencc --dolby-vision-rpu copy`. The planner/researcher must determine the actual way to verify RPU frame-count/profile survival on the AV1 output (dovi_tool AV1 support? qsvencc RPU inspection? an alternative), and design the DV check around what actually works — or, if no reliable in-sandbox mechanism exists, scope the DV check to "RPU present in output" / frame-count parity and document the limitation honestly.
- **D-08:** Optionally add the self-hosted-Arc-runner CI stub that Phase 3 deferred (a distinct, never-auto-triggered GitHub Actions job documented as requiring a self-hosted Intel Arc runner for the `hardware` tier), so the hardware tier has a named home — without ever letting hosted CI green be mistaken for hardware validation.

### Conventions & scope
- **D-09:** Preserve conventions verbatim (Russian help/docstrings, typing generics, banners). CLI is thin dispatch — zero behavior change to detect/encode. `legacy/` untouched.

### Claude's Discretion
- Exact `run_detect(args)` location (detection/cli.py vs a `pipeline`-style module) and the argparse subparser wiring in `cli/main.py`.
- The synthetic HDR10 generation recipe (ffmpeg color-primaries/transfer/mastering-display flags) and the SDR clip recipe.
- The fixtures location convention for HDR10+/DV real samples (e.g. `tests/fixtures/media/` or an `ENPIPE_TEST_MEDIA` env var) and the skip-message wording.
- Whether keyframe-alignment is checked via the existing keyframe table + chunk seek points or via ffprobe on the output chunks.
</decisions>

<specifics>
## Specific Ideas

- The CLI must be a THIN dispatcher: `enpipe detect`/`enpipe encode` reconstitute the two legacy argparse surfaces and call the already-verified `run_detect`/`run_encode`. This deliberately does NOT fuse the stages (the fused streaming orchestrator is out of scope per PROJECT.md).
- Honesty over coverage theater: TEST-04 must not claim SDR/HDR10/HDR10+/DV were all validated if DV/HDR10+ real sources weren't available — synthesize what's synthesizable (SDR, HDR10), fixture-gate the rest, and document the boundary.
- Real Arc hardware IS present in this devcontainer, so the SDR/HDR10 end-to-end validation genuinely runs (not skipped).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### CLI + validation research
- `.planning/research/FEATURES.md` — the unified-entry-point table-stakes deliverable and the hardware-gated integration test (highest-cost/highest-value)
- `.planning/research/ARCHITECTURE.md` — the `cli/` thin-dispatch layer added last; the two-stage `.scenes` coupling to preserve
- `.planning/research/PITFALLS.md` — DV RPU desync surviving splice/mux (the invariant TEST-04's RPU check targets); green-CI≠hardware
- `.planning/research/STACK.md` — `[project.scripts]` console_scripts pattern; self-hosted GPU runner gating

### Current code
- `src/enpipe/encoding/pipeline.py` — `run_encode(args)` (the Namespace-shaped encode entry the CLI wraps; template for `run_detect`)
- `src/enpipe/detection/detect.py` — `detect_scenes` (library fn the detect CLI wraps); `src/enpipe/detection/config.py` — `DetectionConfig`
- `legacy/scene_detection.py:647-692` — the detect `__main__`/argparse + `.scenes`-writing logic to migrate into `run_detect`
- `legacy/encode_scenes.py:516+` — the encode argparse surface to reconstitute; `:15-16` — the `dovi_tool` HEVC-only note (relevant to D-07)
- `pyproject.toml` — the reserved `[project.scripts]` slot; the `hardware` marker
- `scratch/parity_encode.py` — the existing hardware encode-parity gate (a model for the TEST-04 hardware harness)

### Project scope
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md` — PKG-01, TEST-04 acceptance language; Out of Scope (no streaming orchestrator)
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_encode(args)` (encoding/pipeline.py) is already Namespace-shaped and Phase-4-ready — the encode CLI just builds argv → Namespace and calls it.
- `detect_scenes`/`detect_scenes_parallel` + `DetectionConfig` are the detect building blocks; `run_detect` wraps them + the `.scenes` writer.
- `scratch/parity_encode.py` (hardware-gated, self-detecting `/dev/dri`) is the template for the TEST-04 hardware harness (probe hardware, skip cleanly if absent).
- The `hardware` pytest marker + `-m "not hardware"` default (Phase 1) already separate this tier.

### Established Patterns
- The `.scenes` text format is the stage-coupling contract — the CLI must read/write it identically to legacy (`scene NNNN frames [S, E) ...`).
- `use_qsv` selection is via `DetectionConfig(use_qsv=...)` (no `--no-qsv` library flag) — the CLI maps `--no-qsv` → `use_qsv=False`.

### Integration Points
- New `src/enpipe/cli/` package + `[project.scripts]` in pyproject.toml; new `run_detect` in the detection package.
- New `tests/hardware/` (or `hardware`-marked) integration test + a documented media-fixtures location.
- Optional new self-hosted-runner GitHub Actions job (D-08).
</code_context>

<deferred>
## Deferred Ideas

- Streaming/pipelined orchestrator (fused single-command) — OUT OF SCOPE (PROJECT.md; do not fuse the stages).
- v2 quality items — stdlib logging, typed config layer, pyright type-checking, coverage reporting, Hypothesis, dependency-update automation, CI/devcontainer image parity (OBS-01/CFG-01/QUAL-01..03/CI-02).
- Public PyPI release / SemVer public compatibility.
- Sourcing/curating a permanent legally-usable HDR10+/DV sample library — beyond this phase; TEST-04 fixture-gates it and documents how to supply samples.
</deferred>

---

*Phase: 04-unified-cli-hardware-gated-real-media-validation*
*Context gathered: 2026-07-08*
