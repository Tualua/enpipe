# Phase 5: Single-Command Pipeline Entry Point - Context

**Gathered:** 2026-07-09 (--auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a third `enpipe` subcommand, `enpipe run <video>`, that runs scene detection then AV1 encoding **sequentially in one invocation** and produces the final `.mkv` — a thin orchestrator over the already-verified v1.0 `run_detect` and `run_encode`. Covers RUN-01..RUN-04.

**Explicitly NOT in this phase:** the overlapped/streaming orchestrator (concurrent detect+encode via `queue.Queue` — out of scope, PROJECT.md); any change to the detect or encode algorithms/behavior; any change to the existing `enpipe detect` / `enpipe encode` commands or to `legacy/`. This is composition only.
</domain>

<decisions>
## Implementation Decisions

### Command shape & structure
- **D-01:** Add a `run` subparser to `src/enpipe/cli/main.py` (alongside `detect`/`encode`). Its handler is a THIN orchestrator that: builds a detect-shaped `argparse.Namespace` → calls `run_detect(detect_args)` (writes `<video>.scenes`) → builds an encode-shaped Namespace whose `scenes` points at that written path → calls `run_encode(encode_args)`. Strictly SEQUENTIAL (run_encode starts only after run_detect returns) — no overlap, no `queue.Queue`.
- **D-02:** Reuse `run_detect`/`run_encode` VERBATIM — construct the same Namespace attributes with the same values the two-step CLI produces, so output is byte-identical by construction. Zero behavior change to either stage. The orchestrator may live inline in `cli/main.py` or a small `cli/run.py` helper (Claude's discretion), but stays thin dispatch (no pipeline logic of its own). `legacy/` and the `detect`/`encode` subcommands are untouched.

### `--jobs` collision (RUN-02)
- **D-03:** The two stages both have `--jobs` with DIFFERENT meaning and default (detect = parallel detection segments, default 4; encode = parallel `qsvencc` sessions, default `encoding.pipeline.JOBS` from env). In `enpipe run`, expose them as TWO separate, unambiguous flags: `--detect-jobs` (default 4) and `--encode-jobs` (default `ENCODE_JOBS`). Do NOT expose a single `--jobs` that silently sets both. Each forwards to its stage's `jobs` attribute with the legacy default preserved.

### `.scenes` intermediate (RUN-03)
- **D-04:** `enpipe run` writes the scene list to the SAME path `enpipe detect` uses (`<video>.scenes`, i.e. `str(video) + ".scenes"`) and KEEPS it — mirroring exactly what the manual two-step run leaves on disk. This makes the byte-identical-parity requirement trivially true (the intermediate and the final `.mkv` are produced identically). An optional `--scenes PATH` override to relocate the intermediate is Claude's discretion (nice-to-have, not required); if omitted, the default path is used.

### Output & option surface (RUN-02)
- **D-05:** `enpipe run <video> [-o/--out OUT]` — `-o/--out` is the FINAL `.mkv` (encode semantics; default `<video>.av1.mkv` as `run_encode` computes). The `.scenes` path is derived automatically (not `-o`), avoiding the detect-vs-encode `-o` dest collision.
- **D-06:** Forward the relevant per-stage options with unambiguous names:
  - Detect: `--width`, `--threshold`, `--min-scene-len-frames`, `--min-scene-len`, `--no-qsv`, `--qsv-device`, `--detect-jobs`.
  - Encode: `--from`, `--to`, `--workdir`, `--keep`, `--no-audio`, `--no-metrics`, `--csv`, `--encode-jobs`.
  Preserve Russian help text and the existing per-stage defaults. `--from`/`--to` (scene range) apply to encode.

### Testing (RUN-04)
- **D-07:** Fast (non-hardware) unit test: mock `run_detect` and `run_encode` (patch them where `cli` imports/calls them) and assert (a) `run_detect` is called BEFORE `run_encode` (order), and (b) argument routing is correct — the detect Namespace carries the detect options + `--detect-jobs`→`jobs`; the encode Namespace carries `scenes` = the detected `.scenes` path, the encode options, and `--encode-jobs`→`jobs`. No hardware, no real media.
- **D-08:** Hardware-gated end-to-end test (marker `hardware`, excluded from `pytest -m "not hardware"`; self-detects `/dev/dri`+qsvencc, clean skip if absent — reuse the Phase-4 `tests/integration/test_hardware_real_media.py` harness helpers): assert `enpipe run <video> -o out.mkv --no-metrics` produces output byte-identical to a manual `enpipe detect` + `enpipe encode` run with equivalent options (compare the pre-mux `movie.obu` via `--keep`, per the Phase-4 determinism-aware pattern, and/or `count_frames` parity on the final `.mkv`). Always pass `--no-metrics` (qsvencc `--psnr/--ssim` fails rc=255 on this devcontainer — OpenCL ICD absent).

### Conventions & scope
- **D-09:** Preserve conventions verbatim (Russian help/docstrings, `typing`-module generics not PEP 604, banners). Thin dispatch, zero behavior change; `legacy/` + `enpipe detect`/`encode` unchanged; sequential only.

### Claude's Discretion
- Orchestrator location (`cli/main.py` inline vs `cli/run.py`) and how the two sub-Namespaces are constructed (a small builder vs `argparse.Namespace(**{...})`).
- Whether to add the optional `--scenes PATH` override.
- Exact hardware-parity comparison (movie.obu byte-compare vs final-mkv frame-count parity vs both) — follow the Phase-4 precedent.
</decisions>

<specifics>
## Specific Ideas

- Byte-identical parity is guaranteed by CONSTRUCTION: `run` calls the same `run_detect`/`run_encode` with the same Namespace values the manual two-step uses, and leaves the same `.scenes` on disk. The test proves it, but the design makes it true.
- The whole value is UX (one command) at zero regression risk — this is the sequential path `PIPELINE_DESIGN.md` recommends, deliberately NOT the overlapped orchestrator.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current code (what `run` composes)
- `src/enpipe/cli/main.py` — the existing `enpipe` dispatcher (`detect`/`encode` subparsers, `build_parser`, `main(argv)`); the `run` subparser is added here. Note both `--jobs` defaults (detect 4, encode `ENCODE_JOBS`) and both `-o` dests (`output` vs `out`).
- `src/enpipe/detection/pipeline.py` — `run_detect(args)`: reads `args.{input,output,width,threshold,min_scene_len_frames,min_scene_len,no_qsv,qsv_device,jobs}`, writes `<video>.scenes`.
- `src/enpipe/encoding/pipeline.py` — `run_encode(args)`: reads `args.{video,scenes,out,frm,to,workdir,keep,jobs,no_audio,no_metrics,csv}`; `JOBS` (ENCODE_JOBS) env default; retains the `shutil.which` preflight.
- `tests/integration/test_hardware_real_media.py` — the Phase-4 hardware harness (self-detect Arc, `--no-metrics`, `--keep` movie.obu parity, clean skip) to reuse for D-08.
- `legacy/scene_detection.py:647-692`, `legacy/encode_scenes.py:516+` — the argparse surfaces the CLI reconstructs (do NOT edit legacy).

### Project scope
- `.planning/PROJECT.md` (## Current Milestone: v1.1) — the sequential-wrapper framing; overlapped orchestrator Out of Scope.
- `.planning/REQUIREMENTS.md` (## Milestone v1.1 Requirements) — RUN-01..RUN-04.
- `.planning/codebase/CONVENTIONS.md` — conventions to preserve.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_detect`/`run_encode` are already Namespace-shaped and independently verified (v1.0) — `run` just composes them; no new pipeline logic.
- The Phase-4 hardware harness (self-detecting Arc gate, `--no-metrics`, movie.obu `--keep` byte-compare) is directly reusable for the D-08 parity test.
- `build_parser()` already reconstructs both stages' flags — the `run` subparser reuses the same flag definitions with the collision-resolving `--detect-jobs`/`--encode-jobs` rename.

### Established Patterns
- `-o` means different things per stage (detect: `.scenes` out; encode: `.mkv` out) — `run` resolves this: `-o/--out` = final `.mkv`; scenes path is derived, not `-o`.
- `--no-metrics` is mandatory for any real encode on this devcontainer (OpenCL ICD absent → qsvencc `--psnr/--ssim` fails).

### Integration Points
- New `run` subparser + handler in `src/enpipe/cli/` (or a `cli/run.py`); no new `[project.scripts]` entry (same `enpipe` console_script).
- New fast unit test under `tests/unit/cli/`; new hardware case in `tests/integration/` (reusing the Phase-4 module or a sibling).
</code_context>

<deferred>
## Deferred Ideas

- Overlapped/streaming orchestrator (concurrent detect+encode) — OUT OF SCOPE (PROJECT.md; gated on SSD/NVMe).
- v2 quality items (logging/typed-config/pyright/coverage/dep-automation) — future.
- Auto-deleting the `.scenes` intermediate / a `--clean` flag — not needed for parity; could be a later convenience.
</deferred>

---

*Phase: 05-single-command-pipeline-entry-point*
*Context gathered: 2026-07-09*
