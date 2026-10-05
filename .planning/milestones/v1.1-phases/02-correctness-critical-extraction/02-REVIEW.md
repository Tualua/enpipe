---
phase: 02-correctness-critical-extraction
reviewed: 2026-07-08T15:10:00Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - src/enpipe/mkv/__init__.py
  - src/enpipe/mkv/ebml.py
  - src/enpipe/encoding/keyframes.py
  - src/enpipe/encoding/pipeline.py
  - tests/unit/mkv/_ebml_builder.py
  - tests/unit/mkv/test_ebml.py
  - tests/integration/test_ebml_cross_validation.py
  - tests/unit/encoding/test_keyframes.py
  - tests/unit/encoding/test_pipeline_ordering.py
  - tests/unit/encoding/test_pipeline_wiring.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-08T15:10:00Z
**Depth:** deep
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 2 is an extraction-only refactor (DEBT-01: hand-rolled EBML/Cues parser → `enpipe.mkv.ebml`; DEBT-02: seek/trim math + high-water-mark flush ordering → pure functions) with an explicit zero-behavior-change contract. I verified this claim directly rather than trusting the plan/summary docs:

- Diffed `git show 8bbe87a` (EBML extraction) and `git show 384f3e0` (seek/trim + `contiguous_run` extraction) against the pre-extraction inline code and against `legacy/encode_scenes.py:130-326`. Both extractions are byte-verbatim moves — no algorithm bytes changed. The `cues_pos >= sz` bound check, the `except (IndexError, ValueError)` duplication inside both pure functions (Pitfall 2), the frame-0 defensive guard, and the `contiguous_run`/`next_append` advance semantics all match the pre-extraction code exactly.
- `enpipe.mkv.ebml` is provably pure — confirmed independently by reading the full module source (no `Path`/`open`/`.stat(`/`subprocess` anywhere) and by re-running the plan's own purity grep.
- `contiguous_run` returns a concrete `List[int]` (not a generator — Pitfall 3), and I confirmed by direct execution (not just reading) that it never mutates `ready` and never advances `next_append` itself.
- D-08 cross-validation genuinely compares against BOTH independent oracles: ran `tests/integration/test_ebml_cross_validation.py` directly in this environment (ffmpeg+libx264 present, so it executed rather than skipped) — `keyframe_table_cues == keyframe_table_ffprobe == legacy inline keyframe_table_cues (importlib-isolated) == [(0,0.0),(12,0.5),(24,1.0),(36,1.5)]`, confirmed PASS. The legacy module is loaded read-only via `importlib.util.spec_from_file_location`; `legacy/encode_scenes.py` itself is untouched.
- The mocked `run_encode` wiring test (`test_pipeline_wiring.py`) genuinely drives the real `run_encode` orchestration (not a stub of the function under test) — `contiguous_run`, `flush_appends`, and `compute_chunk_seek_trim` all execute for real; only the external I/O boundaries (`shutil.which`, `probe_fps`, `keyframe_table`, `detect_hdr`, `read_scenes`, `encode_chunk`, `_proc.run`) are mocked. It correctly asserts both the byte-identical concat order and the exact `(seek, trim)` wiring against `compute_chunk_seek_trim`.
- All 5 cross-AI review follow-ups recorded in `02-REVIEWS.md` (C-01 dict-input row for `contiguous_run`, C-02 empty-Cues-body fixture, C-03 `s=0` row for `compute_chunk_seek_trim`, C-04 all-consumed row, C-05 tiny-header fixture) are present in the shipped test files exactly as promised, and pass.
- Ran the full fast tier (`pytest -m "not hardware" -q`): 67 passed, 0 failures, 0 collection errors.
- Checked for unused imports / dead code left behind by the extraction (e.g. `_eid`/`_esz`/`_ebml_num` no longer referenced in `keyframes.py`, `fmt_seek`/`kf_before` no longer directly imported into `pipeline.py`) — none found; all imports are used.

I found no BLOCKER-level defects: no purity leak, no fallback-on-anomaly regression, no ordering/seek-trim off-by-one, no generator-instead-of-list bug, and no test that asserts nothing or asserts the wrong outcome in a way that would mask a real defect. One WARNING is reported below — a test whose docstring/threat-model claim doesn't match the code path it actually exercises (a coverage-labeling gap, not a production bug).

## Warnings

### WR-01: Byte-fixture "Case G" doesn't exercise the IndexError-containment path it claims to prove

**File:** `tests/unit/mkv/test_ebml.py:115-120`
**Issue:** The test and its comment (mirrored in `02-01-PLAN.md`'s Task 2 action text and the phase threat model `T-02-01`: *"Case G (sub-header/too-short input → None, not a traceback)"*) claim this fixture proves `find_cues_position`'s internal `except (IndexError, ValueError): return None` containment on a too-short buffer. Tracing the actual execution:

```python
>>> from enpipe.mkv.ebml import _eid, find_cues_position
>>> _eid(b"\x00" * 10, 0)
(0, 9)   # no exception -- _ebml_num's bounded VINT-length loop
         # (`while length <= 8`) terminates cleanly at length=9 and
         # returns id=0 via ordinary control flow, not via an exception
>>> find_cues_position(b"\x00" * 10, 10)
None     # returned via the *first* `if idv != 0x1A45DFA3: return None`
         # check (ordinary "wrong element ID" rejection) -- the `except`
         # clause is never entered for this specific input
```

`b"\x00" * 10` never triggers an `IndexError`: `_ebml_num`'s length-scan loop is bounded (`length <= 8`) and Python bytes slicing (`b[p:p+length]`) never raises even when the requested end exceeds `len(b)`. The function returns `None` only because the decoded element ID (`0`) doesn't match `0x1A45DFA3` — the same "wrong ID" path every other well-formed-prefix case takes, not the exception-containment path the case name and comment claim to demonstrate. I independently confirmed the real exception-containment path *is* implemented correctly and *does* work (e.g. `find_cues_position(b"", 0)` and `find_cues_position(bytes.fromhex("1a45dfa3"), total_size=4)` both correctly return `None` via the `except (IndexError, ValueError)` branch) — but no fixture in the shipped corpus (Cases A-G) actually drives `find_cues_position` through that branch. (For contrast, `parse_cues_body`'s IndexError containment *is* genuinely exercised, by Case D's mid-CuePoint truncation.)

This is not a production defect — the parser correctly fails closed either way — but it means the `T-02-01` threat-register claim ("DoS via malformed/truncated bytes... mitigated... prove containment with fixtures ... Case G") overstates what Case G actually proves for `find_cues_position`, and a future maintainer reading the corpus could reasonably (but wrongly) conclude the exception-containment branch of `find_cues_position` has direct test coverage.

**Fix:** Either reword Case G's comment/the threat-model entry to describe what's actually tested ("too-short-but-still-indexable input, rejected by the ordinary ID check"), or add a fixture that genuinely drives the exception path, e.g.:
```python
def test_case_g2_truncated_before_esz_raises_internally_caught():
    # 4-byte EBML header ID only, no continuation bytes for the Segment
    # size VINT that follows -- the second `_eid`/`_esz` call indexes
    # past EOF, raising IndexError internally, caught by
    # find_cues_position's own except clause.
    assert find_cues_position(bytes.fromhex("1a45dfa3"), total_size=4) is None
```

---

_Reviewed: 2026-07-08T15:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
