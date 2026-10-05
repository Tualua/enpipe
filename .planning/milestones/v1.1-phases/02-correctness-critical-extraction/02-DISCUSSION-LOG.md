# Phase 2: Correctness-Critical Extraction - Discussion Log

> **Audit trail only.** Decisions captured in CONTEXT.md.

**Date:** 2026-07-08
**Mode:** discuss (--auto --no-auto, single pass; autonomous answering, auto-advance suppressed so cross-AI review runs before execute)
**Areas analyzed:** EBML module location & read/parse split, EBML symbol boundary, seek/trim extraction, high-water-mark extraction, test corpus + cross-validation, parity/behavior preservation

## Gray Areas & Auto-Selected Decisions

All areas auto-selected (`--auto`); recommended (research-backed) option chosen for each.

- **EBML module** → new `src/enpipe/mkv/ebml.py` with pure byte-parse core + thin file-reading wrapper (read/parse split); `_ebml_num`/`_eid`/`_esz`/`keyframe_table_cues` move; `keyframes.py` imports from it. (research ARCHITECTURE.md)
- **EBML symbol boundary** → only Cues/EBML byte-parsing moves; `keyframe_table_ffprobe` + `keyframe_table` dispatcher stay in keyframes.py; fallback-on-anomaly semantics preserved.
- **seek/trim** → extract pipeline.py:108-110 inline into pure `compute_chunk_seek_trim(table, s, e)`, co-located in keyframes.py with `kf_before`/`fmt_seek`.
- **high-water-mark** → extract `flush_appends()` ordering into pure `contiguous_run(next_append, ready)`; file I/O shell stays in pipeline.py.
- **test corpus** → EBML byte fixtures (normal / missing-SeekHead / truncated) + cross-validate `mkv.ebml` == legacy inline `keyframe_table_cues` == `keyframe_table_ffprobe` on a synthetic real `.mkv`.
- **parity** → zero encoded-output change; Phase-1 fast suite + hardware `parity_encode.py` are the regression backstop; identical keyframe tables pre/post.

## Corrections Made
None — auto mode, single pass.

## Deferred
ThreadPool/ProcessPool + dovi_tool (Phase 3), regression test + CI (Phase 3), unified CLI (Phase 4), hardware HDR/DV validation (Phase 4), third-party MKV library swap (out of scope).

## Todos
No pending todos matched Phase 2.
