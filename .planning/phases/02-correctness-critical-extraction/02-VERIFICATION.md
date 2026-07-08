---
phase: 02-correctness-critical-extraction
verified: 2026-07-08T14:30:00Z
status: passed
score: 6/6 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Phase 2: Correctness-Critical Extraction Verification Report

**Phase Goal:** The hand-rolled EBML/Cues parser and the seek/trim/high-water-mark arithmetic are isolated into pure, directly unit-tested modules with ZERO behavior change, verified against legacy/.
**Verified:** 2026-07-08T14:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `src/enpipe/mkv/ebml.py` exists and is provably PURE (no `subprocess`/`open(`/`.stat(`/`Path(` call sites) | VERIFIED | `grep -n "subprocess\|open(\|\.stat(\|Path(" src/enpipe/mkv/ebml.py` → zero matches; independent AST-free source-substring re-check via `inspect.getsource` also returns `bad: []` |
| 2 | `encoding/keyframes.py::keyframe_table_cues` is a thin I/O shell importing `find_cues_position`/`peek_element_header`/`parse_cues_body` from `enpipe.mkv.ebml`; `keyframe_table_ffprobe` + `keyframe_table` dispatcher stayed; None→ffprobe fallback intact | VERIFIED | keyframes.py:18 `from enpipe.mkv import ebml as _ebml`; lines 30/39/47 call `_ebml.find_cues_position`/`_ebml.peek_element_header`/`_ebml.parse_cues_body`; `keyframe_table_ffprobe` (line 50) and `keyframe_table` dispatcher (line 76, `if table is not None: ... else fallback to ffprobe`) unchanged in place |
| 3 | `compute_chunk_seek_trim` lives in keyframes.py and `contiguous_run` (typing.Union, concrete list) lives in pipeline.py; both call sites in pipeline.py rewired | VERIFIED | `compute_chunk_seek_trim` at keyframes.py:114, co-located with `kf_before`/`fmt_seek`; `contiguous_run` at pipeline.py:42, annotated `Union[Dict[int, int], Set[int]] -> List[int]`, materializes a concrete list (not a generator); call site 1 at pipeline.py:122 `seek, trim = compute_chunk_seek_trim(table, s, e)`; call site 2 at pipeline.py:148 `for i in contiguous_run(next_append, ready):` inside `flush_appends` |
| 4 | Byte-fixture corpus covers anomalies returning None (never raising); D-08 cross-validation compares vs BOTH ffprobe AND legacy inline (importlib); mocked run_encode wiring test proves concat order + seek/trim wiring | VERIFIED | `tests/unit/mkv/test_ebml.py` Cases A-G present (well-formed, missing-SeekHead, past-EOF, mid-CuePoint truncation, no-keyframe-at-0, empty-Cues, sub-header) — all anomaly cases assert `is None`, none use `pytest.raises`; `tests/integration/test_ebml_cross_validation.py` asserts `fast == slow == legacy == _EXPECTED_TABLE` with legacy loaded via `importlib.util.spec_from_file_location` against `legacy/encode_scenes.py`; `tests/unit/encoding/test_pipeline_wiring.py` asserts `movie.obu == b"".join(canned...)` and `recorded_seek_trim[i] == compute_chunk_seek_trim(...)` for every scene |
| 5 | `uv run pytest -m "not hardware"` passes (~67 tests) | VERIFIED | Ran directly: `67 passed in 1.02s`, zero collection errors, zero skips (cross-validation test executed, not skipped — ffmpeg+libx264 present) |
| 6 | Hardware parity gate `scratch/parity_encode.py` yields byte-identical `movie.obu` (or documented skip) | VERIFIED | Ran directly against real Arc hardware (`/dev/dri/renderD128` present): determinism pre-check confirmed qsvencc deterministic; `byte-identical movie.obu (legacy1 vs migrated): True`; secondary gate frame counts 240=240; script exited 0, `PARITY OK` |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/enpipe/mkv/__init__.py` | mkv subpackage marker | VERIFIED | Empty file present, matches `encoding`/`shared` style |
| `src/enpipe/mkv/ebml.py` | Pure EBML read/parse core | VERIFIED | Exposes `_ebml_num`, `_eid`, `_esz`, `peek_element_header`, `find_cues_position`, `parse_cues_body`; substantive (166 lines, full logic moved verbatim); provably pure; wired (imported by keyframes.py, imported by test_ebml.py) |
| `src/enpipe/encoding/keyframes.py` | thin I/O shell + dispatcher unchanged + `compute_chunk_seek_trim` | VERIFIED | `keyframe_table_cues` reduced to ~25 lines of I/O (stat/open/seek/read) delegating byte parsing to `_ebml`; `keyframe_table_ffprobe`/`keyframe_table`/`kf_before`/`fmt_seek` unchanged; `compute_chunk_seek_trim` added and composes `kf_before`/`fmt_seek` (not rewritten) |
| `src/enpipe/encoding/pipeline.py` | `contiguous_run` + thin `flush_appends` shell + call sites | VERIFIED | `contiguous_run` module-level, pure, `typing.Union`/`typing.Set` generics (not PEP 604 `|`); `flush_appends` is a thin shell (copyfileobj/flush/unlink/next_append advance) consuming `contiguous_run`'s result |
| `tests/unit/mkv/_ebml_builder.py` | byte-fixture builder | VERIFIED | VINT/element helpers + named ID constants matching parser's magic numbers |
| `tests/unit/mkv/test_ebml.py` | Cases A-G + moved primitive tests + purity | VERIFIED | 11 test functions covering all 7 cases + 4 moved `_ebml_num`/`_eid`/`_esz` tests |
| `tests/integration/test_ebml_cross_validation.py` | D-08 cross-validation | VERIFIED | Present, executes (not skipped), passes |
| `tests/unit/encoding/test_pipeline_ordering.py` | `contiguous_run` edge cases | VERIFIED | 10 tests: empty/single/gap/not-ready/fully-contiguous/nonzero-high-water/dict-input/all-consumed/no-mutation (dict+set) |
| `tests/unit/encoding/test_pipeline_wiring.py` | mocked `run_encode` wiring proof | VERIFIED | 1 comprehensive test, all external boundaries patched, asserts byte-identical concat order + seek/trim wiring |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `encoding/keyframes.py` | `mkv/ebml.py` | `_ebml.find_cues_position`/`peek_element_header`/`parse_cues_body` | WIRED | Grep confirms `ebml\.(find_cues_position\|peek_element_header\|parse_cues_body)` pattern present at lines 30, 39, 47 |
| `encoding/keyframes.py` | `keyframe_table_ffprobe` | dispatcher fallback on None | WIRED | `keyframe_table` (line 76) checks `if table is not None: ... return table` else logs and falls through to `keyframe_table_ffprobe` |
| `pipeline.py` chunk-task loop | `compute_chunk_seek_trim` | direct call | WIRED | Line 122, imported at line 35 |
| `pipeline.py flush_appends` | `contiguous_run` | iterate result, advance `next_append` | WIRED | Line 148, module-level function defined at line 42 |

### Data-Flow Trace (Level 4)

Not applicable in the strict UI-data-flow sense (this is a CLI/library refactor, not a component rendering dynamic data), but the equivalent check — real bytes flowing through the extracted functions end-to-end — was performed via the hardware parity gate (`scratch/parity_encode.py`), which drove the actual `run_encode` orchestration on real Arc hardware and confirmed byte-identical `movie.obu` output against the `legacy/` oracle. This is the strongest possible Level-4 equivalent for a pure-arithmetic extraction phase.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full fast test tier passes | `uv run pytest -m "not hardware" -q` | `67 passed in 1.02s` | PASS |
| Purity of `enpipe.mkv.ebml` | inline Python substring check (`subprocess`/`open(`/`.stat(`/`Path(`) | `bad: []` | PASS |
| D-08 cross-validation actually executes (not silently skipped) | `uv run pytest tests/integration/test_ebml_cross_validation.py -v` | `PASSED` (ffmpeg+libx264 present, no skip) | PASS |
| Hardware parity gate | `uv run python scratch/parity_encode.py` | `byte-identical movie.obu (legacy1 vs migrated): True`, `PARITY OK`, exit 0 | PASS |
| `legacy/encode_scenes.py` / `legacy/scene_detection.py` unmodified during phase | `stat` mtime comparison vs phase-2 commit timestamps | mtimes (2026-07-07 15:23 / 2026-07-08 06:13) both predate first phase-2 commit (2026-07-08 ~13:41) | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this project; the phase's explicit auto-verification step is `scratch/parity_encode.py`, executed above under Behavioral Spot-Checks (equivalent role to a probe, and PLAN-declared as an `<automated>` verify command).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| DEBT-01 | 02-01-PLAN.md | Hand-rolled EBML/Cues parser isolated into own module with read/parse split, behind tested boundary | SATISFIED | `enpipe.mkv.ebml` pure module + thin shell + byte-fixture corpus + D-08 cross-validation, all verified above |
| DEBT-02 | 02-02-PLAN.md | Seek/trim math and high-water-mark flush ordering extracted into pure, directly unit-testable functions with no behavior change | SATISFIED | `compute_chunk_seek_trim`/`contiguous_run` extracted, unit-tested, wired, mocked wiring test + hardware parity gate confirm zero behavior change |

No orphaned requirements — REQUIREMENTS.md traceability table maps only DEBT-01 and DEBT-02 to Phase 2, both claimed by the two plans.

### Anti-Patterns Found

None. Scanned all 10 phase-modified/created files for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet implemented"/empty-return stubs — zero matches.

### Human Verification Required

None. All must-haves are programmatically verifiable (pure-function purity, byte-fixture assertions, cross-validation equality, mocked wiring assertions, and a real hardware byte-identical parity gate run). No visual, real-time, or subjective-UX surface exists in this phase.

### Gaps Summary

No gaps. All 6 derived observable truths (from ROADMAP Phase 2 Success Criteria + both PLAN frontmatter must_haves, merged and deduplicated) verified directly against the codebase:
- `enpipe.mkv.ebml` exists, is provably pure, and is the sole home of the byte-parsing logic.
- `keyframe_table_cues` is a genuine thin I/O shell; `keyframe_table_ffprobe`/`keyframe_table` dispatcher and fallback-on-None behavior are unchanged.
- `compute_chunk_seek_trim` and `contiguous_run` are correctly located, correctly typed (`typing.Union`, concrete `List`), and correctly wired at both pipeline.py call sites.
- The byte-fixture corpus (Cases A-G) and the D-08 cross-validation (vs both ffprobe and legacy inline) both exist, run, and pass — anomalies fail closed (`None`, never an exception).
- The full fast test tier (67 tests) passes with zero collection errors.
- The hardware parity gate was re-run live in this environment (real Arc hardware present) and produced a byte-identical `movie.obu`, the strongest available end-to-end proof of zero behavior change.
- `legacy/encode_scenes.py` and `legacy/scene_detection.py` are confirmed untouched (mtimes predate phase start) and remain the frozen parity oracle.

---

*Verified: 2026-07-08T14:30:00Z*
*Verifier: Claude (gsd-verifier)*
