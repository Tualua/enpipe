---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Single-command pipeline entry point
status: milestone_complete
stopped_at: Milestone complete (Phase 5 was final phase)
last_updated: 2026-07-09T01:58:25.420Z
last_activity: 2026-07-09 -- Phase 5 execution started
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 11
  completed_plans: 11
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-09)

**Core value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.
**Current focus:** Milestone complete

## Current Position

Phase: 5
Plan: Not started
Status: Milestone complete
Last activity: 2026-07-09

## Performance Metrics

**Velocity:**

- Total plans completed: 11
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 2 | - | - |
| 3 | 3 | - | - |
| 4 | 2 | - | - |
| 5 | 1 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 20min | 2 tasks | 10 files |
| Phase 01 P02 | 20min | 3 tasks | 7 files |
| Phase 01 P03 | 50min | 3 tasks | 16 files |
| Phase 02 P01 | 7min | 3 tasks | 8 files |
| Phase 02 P02 | 5min | 3 tasks | 5 files |
| Phase 03 P01 | 6min | 3 tasks | 5 files |
| Phase 03 P02 | 14min | 3 tasks | 3 files |
| Phase 03 P03 | 6min | 2 tasks | 3 files |
| Phase 04 P01 | 12min | 3 tasks | 6 files |
| Phase 04 P02 | 15min | 4 tasks | 4 files |
| Phase 05 P01 | 9min | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Package scaffold + dependency pinning (Phase 1) must precede everything else — nearly all other deliverables require stable import paths
- Roadmap: Fast test tier + `shared.proc` seam (Phase 1) must exist before any refactor of correctness-critical code (EBML isolation, seek/trim extraction — Phase 2)
- Roadmap: ThreadPool-vs-ProcessPool resolution (DEBT-03) must land before the parallel==sequential regression baseline (TEST-03) is captured — both placed in Phase 3
- Roadmap: Unified CLI entry point (PKG-01) deliberately deferred to Phase 4, after both detect and encode stages are independently verified
- Roadmap (v1.1): Phase numbering continues from v1.0 (starts at Phase 5, not reset to 1)
- Roadmap (v1.1): All 4 RUN-* requirements collapsed into a single Phase 5 — coarse granularity + this is a thin sequential wrapper over already-verified v1.0 stages, not a multi-capability milestone; no natural sub-boundary to split on
- Roadmap (v1.1): Phase 5 depends only on Phase 4 (needs `run_detect`/`run_encode` + the unified CLI dispatcher to exist and be hardware-verified before wrapping them)
- [Phase 01-01]: Confirmed scenedetect exact pin ==0.7 matches installed/working version (PEP 440 0.7.0); no other 0.7.x exists on PyPI
- [Phase 01-01]: Ran uv lock immediately after writing pyproject.toml deps (fail-fast) before scaffolding source files, per plan instruction
- [Phase 01-02]: jobs=1 used on both sides of the D-14 detection parity check (oracle CLI and migrated detect_scenes) for a deterministic comparison, isolating mechanical-migration correctness from the separately-verified parallel-jobs circular-import path
- [Phase 01-02]: use_qsv probed once via Path('/dev/dri/renderD128').exists() (True in this devcontainer) and applied explicitly/identically to both the legacy oracle CLI and DetectionConfig(use_qsv=...) for the parity check
- [Phase 01-03]: Preflight (shutil.which + video.is_file()) retained in run_encode as the sanctioned minimal structural change while stripping argparse - D-13 zero-logic-change contract stays explicit
- [Phase 01-03]: Switched pytest to --import-mode=importlib to resolve test_chunk.py/test_keyframes.py basename collision between tests/unit/encoding and tests/subprocess/encoding
- [Phase 01-03]: Determinism pre-check confirmed qsvencc deterministic on this box - byte-identical pre-mux movie.obu used as the primary D-14 parity gate
- [Phase 01-03]: qsvencc --psnr/--ssim require OpenCL, unavailable in this devcontainer (pre-existing) - Task 3 parity gate runs with metrics disabled symmetrically on both oracle and migrated sides
- [Phase 02-01]: Used exact RESEARCH.md hex blobs for Cases A-D rather than re-deriving them with the builder (avoids transcription-error risk on nested SeekHead/Tracks/Cues structures)
- [Phase 02-01]: Reworded mkv/ebml.py module docstring to avoid tripping the Task 1 purity check's naive substring search on the literal word 'subprocess'
- [Phase 02-02]: Used the 2-tuple (seek, trim) return for compute_chunk_seek_trim per D-04's minimal-diff allowance
- [Phase 02-02]: contiguous_run annotated Union[Dict[int,int], Set[int]] using typing generics (D-11), not PEP 604 |
- [Phase 02-02]: chunk_command wrapped (not stubbed) in the wiring test so real command-building logic runs while recording seek/trim args
- [Phase 03-01]: DEBT-03: measured Layer-1 (0.67x-0.80x speedup) and Layer-2 (1.43x ratio) both fall short of the quantified switch thresholds -- kept ThreadPoolExecutor, rewrote the contradictory comment with measured rationale
- [Phase 03-01]: DEBT-04: kept dovi_tool installed in devcontainer, documented retention for planned Phase-4 TEST-04 DV RPU work without overclaiming AV1 support (extract-rpu is HEVC-only)
- [Phase 03-02]: TEST-03 clip recipe (four ~55s color/smptebars segments, 220s@24fps) verified via ffprobe to clear the jobs*min_span gate for jobs=[2,3] with margin
- [Phase 03-02]: Engagement proof primary target is enpipe.detection.detect.detect_scenes (deferred fallback), call_count==0, executor-agnostic; _segment_worker call_count>1 refinement gated on active executor to avoid PicklingError under ProcessPoolExecutor
- [Phase 03-03]: ruff pinned exactly (==0.15.20) to match project's exact-pin convention, rather than uv add's default >= constraint
- [Phase 03-03]: select = ["F", "E9"] only for ruff — fuller E/W set fires 15x E702 on the deliberately dense mkv/ebml.py parser
- [Phase 03-03]: mkvtoolnix install kept as a separate continue-on-error CI step so an unavailable mkvmerge package cannot block the ffmpeg-only TEST-03 regression test
- [Phase 03-03]: Comment-only hardware-tier exclusion in ci.yml (no stub self-hosted job) per RESEARCH Open Question 3 discretion
- [Phase 04-01]: run_detect docstring documents the intentionally-absent shutil.which preflight as a sanctioned deviation, mirroring run_encode's docstring style but for the opposite deviation
- [Phase 04-01]: cli/main.py uses typing.Optional[Sequence[str]] for main(argv=...), not RESEARCH.md's draft PEP 604 syntax, per typing-generics requirement
- [Phase 04-01]: uv sync used (not uv pip install -e .) since the lockfile still resolved cleanly for the console_script wiring
- [Phase 04-02]: Empirical correction: HDR10 mastering-display/max-CLL survival is checked via ffprobe FRAME-level side data (frame=side_data_list), not STREAM-level -- this pipeline's mkvmerge-muxed raw-OBU AV1 output has no stream-level side_data_list at all
- [Phase 04-02]: Multi-scene synthetic clips (SDR + HDR10) reuse test_parallel_regression.py's 4-segment color=/smptebars= lavfi cut recipe, shortened to 10s/segment (40s total, 3 cuts) for fast real-hardware wall time
- [Phase 05]: run_pipeline additive shutil.which preflight before run_detect; run_encode keeps its own preflight unchanged (D-02 zero-behavior-change invariant)
- [Phase 05]: Detect-jobs and encode-jobs flags resolve the jobs collision; no bare jobs flag on enpipe run (D-03)
- [Phase 05]: Optional scenes-path override implemented (Claude's discretion, D-04), routing to both detect output and encode scenes

### Pending Todos

None yet.

### Blockers/Concerns

- Carried from v1.0: self-hosted GitHub Actions runner with `/dev/dri` passthrough remains a nontrivial, security-sensitive setup for hardware-gated CI; real DV/HDR10+ source material sourcing remains manual

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | OBS-01 (stdlib logging) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | CFG-01 (typed config layer) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | QUAL-01/02/03, CI-02 (ruff+pyright in CI, golden-file EBML fixtures, coverage/hypothesis, image parity+Renovate) | Deferred to v2 | Roadmap creation 2026-07-08 |
| Out of scope | Overlapped/streaming orchestrator (`queue.Queue` producer/consumer) | Deferred until source moves to SSD/NVMe | v1.1 scoping 2026-07-08 |

## Session Continuity

Last session: 2026-07-09T01:52:47.633Z
Stopped at: Completed 05-01-PLAN.md
Resume file: None
</content>
