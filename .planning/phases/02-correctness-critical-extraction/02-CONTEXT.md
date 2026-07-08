# Phase 2: Correctness-Critical Extraction - Context

**Gathered:** 2026-07-08 (--auto)
**Status:** Ready for planning

<domain>
## Phase Boundary

Isolate the two correctness-critical pieces of the migrated encoding stage into pure, directly unit-tested modules with ZERO behavior change, verified against `legacy/`:
1. **DEBT-01** — the hand-rolled EBML/Cues parser (currently inline in `src/enpipe/encoding/keyframes.py`) → a dedicated `mkv` module with a read/parse split, testable with byte fixtures.
2. **DEBT-02** — the seek/trim math and the high-water-mark flush ordering (currently inline in `src/enpipe/encoding/pipeline.py`) → pure functions with unit tests over synthetic edge cases.

**Explicitly NOT in this phase:** the ThreadPool/ProcessPool resolution (Phase 3 / DEBT-03), the parallel==sequential regression test + CI (Phase 3), the unified CLI (Phase 4), hardware/real-media HDR validation (Phase 4). No algorithm changes — extraction only, output must stay byte-identical.
</domain>

<decisions>
## Implementation Decisions

### EBML/Cues parser isolation (DEBT-01)
- **D-01:** Create a new subpackage `src/enpipe/mkv/` with `src/enpipe/mkv/ebml.py`. Move the EBML primitives `_ebml_num`, `_eid`, `_esz` and the Cues parsing logic out of `encoding/keyframes.py` into it. (Follows research ARCHITECTURE.md's `enpipe.mkv.ebml` recommendation.)
- **D-02:** Apply a **read/parse split**: a PURE function that takes the raw Cues/SeekHead bytes (or an in-memory buffer) and returns the keyframe table `List[Tuple[frame:int, pts_time:float]]` with NO file I/O, plus a thin I/O shell that opens the `.mkv`, locates/reads the Cues bytes, and calls the pure core. The pure core is what byte-fixture tests exercise. This is what makes it testable — not merely relocating the code.
- **D-03:** `keyframe_table_ffprobe` (the slow fallback) and `keyframe_table` (the dispatcher that tries Cues then falls back) STAY in `encoding/keyframes.py`; only the Cues/EBML byte-parsing moves to `mkv/ebml.py`. `encoding/keyframes.py` imports the Cues entry point from `enpipe.mkv.ebml`. The fallback-on-anomaly semantics (Cues parse returns `None` → dispatcher falls to ffprobe) are preserved exactly.

### Seek/trim + high-water-mark extraction (DEBT-02)
- **D-04:** Extract the inline per-scene seek/trim computation at `pipeline.py:108-110` (`kf_before` → `fmt_seek` → `trim = f"{s-kf_frame}:{e-1-kf_frame}"`) into a PURE function `compute_chunk_seek_trim(table, s, e) -> (seek: str, trim: str)` (returning the kf_frame too if useful), co-located in `encoding/keyframes.py` next to `kf_before`/`fmt_seek`. `pipeline.py` calls it; the exact seek/trim strings must be unchanged.
- **D-05:** Extract the high-water-mark flush ORDERING from the `flush_appends()` closure (`pipeline.py:134-143`) into a PURE function (e.g. `contiguous_run(next_append, ready_keys) -> list[int]` returning the contiguous run of ready indices starting at `next_append`). The file I/O (`copyfileobj`, `unlink`, `next_append` advance) stays in `pipeline.py` as a thin shell that calls the pure ordering function. The pure function is unit-tested for out-of-order completion (e.g. ready={0,1,3} at next_append=0 → [0,1]; 3 blocked by missing 2).
- **D-06:** These extractions are behavior-preserving refactors, NOT logic changes — the encoded output and the concat order must be byte-identical to before. `kf_before`/`fmt_seek` themselves already exist and are already unit-tested (Phase 1); do not rewrite them.

### Testing & verification
- **D-07:** Build an EBML byte-fixture corpus (no real media): a normal Cues block, a missing-SeekHead case, and malformed/truncated structures — asserting the pure parser returns the right table or safely signals "unparseable" (→ `None` for the dispatcher to fall back), never a wrong-but-parseable table silently.
- **D-08:** Cross-validation test on a synthetic real `.mkv` (generate with ffmpeg): the isolated `mkv.ebml` keyframe table MUST equal both (a) `legacy/encode_scenes.py`'s inline `keyframe_table_cues` output and (b) the trusted `keyframe_table_ffprobe` output, on the same file. This is the DEBT-01 correctness proof.
- **D-09:** Pure unit tests for `compute_chunk_seek_trim` (scene boundaries on/off keyframe) and `contiguous_run` (out-of-order completion) covering synthetic edge cases (DEBT-02 proof).
- **D-10:** Regression guard: the existing Phase-1 fast-tier suite (`pytest -m "not hardware"`) must still pass unchanged, and the hardware-gated `scratch/parity_encode.py` must still produce byte-identical `movie.obu` vs the legacy oracle (proves zero encoded-output change end-to-end).

### Conventions
- **D-11:** Preserve conventions verbatim (Russian docstrings, typing style, banners, frozen dataclasses). `legacy/` stays untouched as the parity oracle.

### Claude's Discretion
- Exact function signatures/return tuples for `compute_chunk_seek_trim` and `contiguous_run`.
- Whether `contiguous_run` lives module-level in `pipeline.py` or in a tiny new `encoding/ordering.py` (either is fine; keep it importable and pure).
- The exact internal shape of the `mkv.ebml` read/parse boundary (e.g. one pure `parse_cues(buf, fps)` vs a `find_cues_position`/`parse_cues_body` pair).
- Byte-fixture construction approach (hand-authored bytes vs. extracting Cues bytes from a synthetic mkv).
</decisions>

<specifics>
## Specific Ideas

- The read/parse split is the whole point of DEBT-01 — a pure byte→table core is the only thing that makes the 130-line hand-rolled parser testable without shipping real `.mkv` files in the repo.
- "Zero behavior change" governs everything: byte-identical encoded output and identical keyframe tables before vs after, proven by the cross-validation + hardware parity gates.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Extraction design
- `.planning/research/ARCHITECTURE.md` — `enpipe.mkv.ebml` read/parse split, `compute_chunk_seek_trim` / `contiguous_ready` pure-function extractions, migration order
- `.planning/research/PITFALLS.md` — EBML "wrong-but-parseable" silent-corruption risk (Pitfall 6) and silent seek/trim frame-shift (Pitfall 1); the exact hazards this phase's tests must catch

### Current code (extraction sources + parity oracle)
- `src/enpipe/encoding/keyframes.py` — inline EBML (`_ebml_num`/`_eid`/`_esz`/`keyframe_table_cues` at lines 26-158), `keyframe_table_ffprobe`, `keyframe_table`, `kf_before`, `fmt_seek`
- `src/enpipe/encoding/pipeline.py` — inline seek/trim (lines 108-110) and `flush_appends()` high-water-mark closure (lines 134-143)
- `src/enpipe/encoding/chunk.py` — `chunk_command` (consumes seek/trim strings)
- `legacy/encode_scenes.py` — the parity oracle; its inline `keyframe_table_cues` is the cross-validation reference
- `.planning/phases/01-package-foundation-migration-fast-test-tier/01-03-SUMMARY.md` — how encoding was migrated (what exists to refactor)

### Project scope
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md` — DEBT-01, DEBT-02 acceptance language
- `.planning/codebase/CONVENTIONS.md` — conventions to preserve
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `kf_before`/`fmt_seek` (keyframes.py) are already pure and unit-tested (Phase 1) — reuse, don't rewrite; `compute_chunk_seek_trim` composes them.
- `tests/unit/encoding/test_keyframes.py` already tests `kf_before`/`fmt_seek` — extend it (or add `tests/unit/mkv/test_ebml.py`) for the new pure functions.
- Phase 1's `pytest -m "not hardware"` suite (43 tests) + `scratch/parity_encode.py` hardware gate are the regression backstop.

### Established Patterns
- Read/parse split mirrors Phase 1's `shared.proc` seam philosophy: isolate the untestable boundary (byte parsing / file I/O) behind a pure core.
- The dispatcher's fallback-on-anomaly (`keyframe_table_cues` returns `None` → ffprobe path) is load-bearing and must be preserved exactly.

### Integration Points
- `encoding/keyframes.py` will import from the new `enpipe.mkv.ebml`; `encoding/pipeline.py` will import the extracted pure seek/trim + ordering functions.
- New package dir `src/enpipe/mkv/__init__.py` + `src/enpipe/mkv/ebml.py`.
</code_context>

<deferred>
## Deferred Ideas

- ThreadPool-vs-ProcessPool resolution + `dovi_tool` cleanup — Phase 3 (DEBT-03/DEBT-04).
- Mandatory parallel==sequential regression test + CI — Phase 3 (TEST-03/CI-01).
- Unified CLI entry point — Phase 4 (PKG-01).
- Hardware-gated real-media HDR/DV validation — Phase 4 (TEST-04).
- Swapping the hand-rolled EBML parser for a third-party library — out of scope (isolate + test the existing one; PROJECT.md).
</deferred>

---

*Phase: 02-correctness-critical-extraction*
*Context gathered: 2026-07-08*
