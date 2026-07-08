---
phase: 2
reviewers: [qwen, opencode]
reviewed_at: 2026-07-08T13:30:35Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md]
note: claude skipped (self); gemini/codex/cursor/coderabbit + local servers unavailable
---

# Cross-AI Plan Review — Phase 2 (Correctness-Critical Extraction)

## Qwen Review

## Cross-AI Plan Review: Phase 2 — Correctness-Critical Extraction

### Summary

Both plans are tightly scoped with strong traceability to locked decisions and research-verified code. The read/parse split is sound, the byte-fixture cases cover the right anomaly vectors, and the cross-validation recipe (`-cues_to_front 1`) was empirically proven rather than assumed. 02-02's extractions are mechanical three-line compositions of already-tested functions. The main risks are mechanical (copy-paste typos in verbatim extraction), caught immediately by the verification commands and fast-tier regression.

### Strengths

1. **Genuinely pure read/parse split** — `find_cues_position`, `peek_element_header`, `parse_cues_body` take only `bytes` + primitives; zero I/O means byte-fixture testing works without mocks or real files.
2. **Byte-fixture cases A–E hit the right hazards** — missing SeekHead, past-EOF bound check, mid-CuePoint truncation, missing-frame-0 are exactly the silent-corruption vectors PITFALLS.md flags. The `None`-on-anomaly discipline (never `pytest.raises`) is correct.
3. **Cross-validation recipe is empirically proven** — the `-cues_to_front 1` requirement was discovered by actual testing; the three-way equality (`cues == ffprobe == expected_table`) is a strong correctness proof.
4. **Thin-shell discipline explicit** — both plans guard against Pitfall 5 (no added logging/branching) and separate pure decision from I/O mutation.
5. **Executable parity backstop** — re-running `scratch/parity_encode.py` unchanged auto-skips when hardware is absent, so no spurious CI failures.

### Concerns

| ID | Severity | Description |
|----|----------|-------------|
| C-01 | MEDIUM | **`contiguous_run` tests only exercise `set` inputs, but the call site passes `Dict[int, int]`** (pipeline.py line 128: `ready: Dict[int, int] = {}`). The `in` operator on a dict checks keys, so both work, but the test suite should include at least one dict-syntax row (`{0:100, 1:200, 3:300}`) to prove the type hint contract holds. |
| C-02 | MEDIUM | **No empty-Cues-body fixture.** `parse_cues_body(b"", ...)` exercises the `if not times: return None` guard — a legal EBML structure (Cues with zero CuePoints) that could occur with minimally-muxed files. Currently untested. |
| C-03 | LOW | **`compute_chunk_seek_trim` missing `s=0` test row.** The first scene starting at frame 0 is the most common case: `kf_before` returns `(0, 0.0)`, `seek = "00:00:00.000"`, `trim = "0:{e-1}"`. Should have an explicit assertion. |
| C-04 | LOW | **No `next_append` past all-ready test for `contiguous_run`.** E.g., `next_append=10, ready={0,1,2} → []` — the post-flush idle state where all lower chunks have been consumed. Plausible, currently uncovered. |
| C-05 | LOW | **No tiny-header fixture** (< 16 bytes) for `find_cues_position`. The `while q < len(head) - 8` guard and `IndexError → None` containment should be proven for a file whose head is too short to even contain a valid EBML header walk. |

### Suggestions

1. **Add dict-syntax row to `contiguous_run` tests** (C-01):
   ```python
   assert contiguous_run(0, {0: 100, 1: 200, 3: 300}) == [0, 1]
   ```

2. **Add empty-Cues-body test** (C-02):
   ```python
   assert parse_cues_body(b"", 1, 1_000_000, 24.0) is None
   ```

3. **Add `s=0` row to `compute_chunk_seek_trim` tests** (C-03):
   ```python
   assert compute_chunk_seek_trim([(0,0.0),(48,2.0),(96,4.0)], 0, 48) == ("00:00:00.000", "0:47")
   ```

4. **Add `next_append` past all-ready test** (C-04):
   ```python
   assert contiguous_run(10, {0, 1, 2}) == []
   ```

5. **Add tiny-header fixture** (C-05):
   ```python
   assert find_cues_position(b"\x00" * 10, 10) is None
   ```

None of these are blockers — all are straightforward additions to the existing test files within the plan's current task scope.

### Risk: **LOW**

The plans are well-bounded extraction-only work with specific tests for each silent-corruption vector. The cross-validation + parity-encode gates provide end-to-end proof. The `None`-on-anomaly contract prevents "wrong-but-parseable" tables from silently reaching the dispatcher. No new dependencies, no algorithm changes, no behavioral branching added.

---

## OpenCode Review

---

# Cross-AI Plan Review — enpipe Phase 2 (DEBT-01 / DEBT-02)

## 1) Summary

Two well-scoped, extraction-onI've verified the plans against the actual codebase (`keyframes.py:26-222`, `pipeline.py:1-250`, `legacy/encode_scenes.py:130-326`, `scratch/parity_encode.py`, `pyproject.toml`, existing tests). Here's my review.

---

## 1) Summary

Two well-scoped extraction plans for Phase 2. **02-01** isolates the hand-rolled EBML/Cues parser into `enpipe.mkv.ebml` via a genuine read/parse split (`find_cues_position` / `peek_element_header` / `parse_cues_body` pure + thin I/O shell), backed by 5 verified byte fixtures + a synthetic-`.mkv` cross-validation. **02-02** extracts `compute_chunk_seek_trim` and `contiguous_run` as pure functions with edge-case unit tests. Both are behavior-preserving refactors with `legacy/` as the frozen parity oracle. The RESEARCH doc empirically verified the fixtures and the ffmpeg `-cues_to_front 1` recipe against a prototype — this is not a sketch. The extractions are verbatim moves of `keyframes.py:48-158` and `pipeline.py:108-110,134-143` (I confirmed line-by-line). Overall solid; the gaps below are mostly around locked-decision letter vs. spirit and a non-hardware end-to-end proof hole.

## 2) Strengths

- **Genuine read/parse split.** The three pure functions take `bytes`/`int`/`float` only — no `Path`/`open`/`stat`/`subprocess`. This is the real testability win D-02 demands, not a relocation. Verified the current `keyframe_table_cues` body (`keyframes.py:48-158`) maps cleanly onto the three functions.
- **Deliberate exception duplication (Pitfall 2).** Each pure function keeps its own `except (IndexError, ValueError): return None` so fixtures observe `None`, not tracebacks. This is the correct call and is explicitly flagged as non-redundant.
- **`total_size` parameterization.** Folding `cues_pos >= sz` into `find_cues_position(head, total_size)` makes the truncated-file case (Case C) a pure-function fixture instead of requiring a real truncated file. Clean.
- **`contiguous_run` returns a concrete `List[int]`** (not a generator) — avoids the lazy-re-evaluation footgun and is trivially testable.
- **Wave dependency is load-bearing**, not just conservative: 02-01 updates `test_keyframes.py`'s import line (dropping `_eid/_ebml_num/_esz`), and 02-02 adds `compute_chunk_seek_trim` to that same line. 02-02 cannot run before 02-01 without an import break.
- **Threat model maps threats to specific fixture cases** (T-02-01→Cases B/C/D, T-02-02→Case E+D-08, T-02-03/T-02-06→parity gate). STRIDE register covers the right silent-corruption risks.
- **Cross-validation recipe was empirically tested** (RESEARCH confirmed `keyframe_table_cues == keyframe_table_ffprobe == [(0,0.0),(12,0.5),(24,1.0),(36,1.5)]` on a real generated file). The `-cues_to_front 1` discovery is non-obvious and valuable.
- **`legacy/` confirmed identical** to `src/` pre-split (`legacy/encode_scenes.py:130-262` vs `keyframes.py:26-158` are byte-for-byte the same algorithm), validating the parity-oracle premise.

## 3) Concerns

### MEDIUM

**M1. D-08 partially implemented — no direct `legacy/` comparison.**
D-08 (locked) requires the isolated module to equal *both* (a) `legacy/encode_scenes.py`'s inline `keyframe_table_cues` *and* (b) `keyframe_table_ffprobe`. The plan's Task 3 test (`02-01-PLAN.md:149`) only checks `keyframe_table_cues == keyframe_table_ffprobe`. The RESEARCH ("Note on legacy comparison") argues (a) is redundant since legacy == src-pre-split (verbatim migration). That transitivity is sound *today* for a frozen oracle, and ffprobe is the stronger independent oracle (legacy is the same algorithm, so it would share any bug). But the plan's "Truths — Decision Traceability" claims to implement D-08, which literally says "both." A direct legacy comparison via `importlib.util.spec_from_file_location` (avoiding legacy's module-level side effects) would close this trivially and satisfy the locked letter.

**M2. `must_haves.truths` overstates the DEBT-02 byte-identical guarantee.**
`02-02-PLAN.md` truth: *"the hardware scratch/parity_encode.py gate still yields byte-identical movie.obu"*. But the gate itself (`scratch/parity_encode.py:94,192-249`) sets `METRICS_UNAVAILABLE = True` (OpenCL absent) and runs a determinism pre-check; when qsvencc is non-deterministic (common for HW AV1 per the script's own comments at `:21-29`), it falls back to **frame-count match only** — NOT byte-identical. The Task 3 `<acceptance_criteria>` hedges correctly ("byte-identical ... *or* the frame-count + SSIM/PSNR-epsilon fallback"), but the `must_haves.truths` does not. The truth statement should say "byte-identical when qsvencc is deterministic; frame-count + epsilon match otherwise" to match the gate's actual contract.

**M3. No non-hardware end-to-end proof for DEBT-02.**
The "zero behavior change" claim for DEBT-02 rests on: (a) pure unit tests of `compute_chunk_seek_trim`/`contiguous_run` (correct *in isolation*) + (b) the hardware parity gate (SKIPs off Arc). There's no middle layer: no test exercises `run_encode`/`flush_appends` end-to-end with a mocked `encode_chunk` to prove the wiring (seek/trim strings flowing into `chunk_command`, concat order flowing through `flush_appends`) is byte-identical pre/post extraction. I confirmed no `test_pipeline.py` exists today (`tests/unit/encoding/` has only `test_chunk/test_keyframes/test_metrics/test_scenes_io`). A mocked integration test (canned `.obu` bytes per chunk, assert `movie.obu` is the ordered concatenation + assert emitted seek/trim strings) would close this without hardware. This is partly a pre-existing gap, but DEBT-02's "zero encoded-output change" truth would benefit from a non-hardware backstop.

### LOW

**L1. `contiguous_run` type hint violates CONVENTIONS.md typing style.**
The `<interfaces>` block and RESEARCH Pattern 3 both show `ready: Dict[int, int] | set[int]` (PEP 604 `|` union). CONVENTIONS.md (D-11, "preserve typing style verbatim") mandates `typing.Union[...]` over bare `|` syntax. Should be `Union[Dict[int, int], Set[int]]` (or simplify — `ready` is always `Dict[int, int]` at the call site; the `set` accommodation is only for the unit tests passing set literals, which could pass `{0:1, 1:1, 3:1}` dicts instead).

**L2. Cross-validation test `skipif` doesn't guard `libx264`.**
`02-01-PLAN.md:149` guards `shutil.which("ffmpeg") is None`, but the recipe uses `-c:v libx264`. If ffmpeg exists but lacks libx264 (minimal/static builds), the test raises `CalledProcessError` instead of skipping. Defensive skipif should probe `ffmpeg -encoders` for libx264, or use a codec always present in Debian's ffmpeg (e.g., `ffv1` supports `-g`). Low because the devcontainer's apt ffmpeg includes libx264.

**L3. `mkv.ebml` purity not auto-verified.**
`<verification>` lists "enpipe.mkv.ebml is pure (no `import`/call of `Path`/`open`/`stat`/subprocess)" but no `<automated>` check enforces it. A one-liner AST/import check would make the purity claim executable rather than review-only.

**L4. 02-01 Task 1 verify's import-string assertion is brittle.**
`assert 'from enpipe.mkv import ebml' in inspect.getsource(k)` fails if the executor writes `import enpipe.mkv.ebml as _ebml` (a valid form the RESEARCH itself suggests with `as _ebml`). The `must_haves.key_links` regex `ebml\.(find_cues_position|...)` is robust to both forms; the verify command should match that pattern instead of a literal import substring.

**L5. `compute_chunk_seek_trim` tests miss `s=0` edge case.**
Task 2 tests on-keyframe (s=48) and off-keyframe (s=70) but not s=0 (first scene at frame 0 → `kf_before` returns `(0,0.0)` → seek `00:00:00.000`, trim `0:{e-1}`). This is the most common real case and worth one assertion.

## 4) Suggestions

- **Add a direct legacy comparison to the D-08 test** (M1): load `legacy/encode_scenes.py` via `importlib.util.spec_from_file_location` (isolates its module-level side effects like `_START = time.monotonic()`), call its `keyframe_table_cues`, assert equality. Trivially satisfies D-08's literal "both (a) and (b)".
- **Add a mocked `run_encode` integration test** (M3): with `encode_chunk` patched to write canned N-byte `.obu` files and `count_frames` patched to return the expected count, assert `movie.obu` bytes == concatenation in scene order, and capture/assert the seek/trim strings passed to `chunk_command`. This is the non-hardware end-to-end backstop DEBT-02 currently lacks.
- **Sharpen the `must_haves.truths` wording** (M2) to match the gate's actual determinism-conditional contract.
- **Add a small fuzz test** to `test_ebml.py`: loop ~1000 random byte strings through `find_cues_position` and `parse_cues_body`, assert each returns `None` or a valid table, never raises. Strengthens the "never an uncaught exception" truth beyond the 5 hand-built fixtures.
- **Fix the `contiguous_run` type hint** to `Union[Dict[int, int], Set[int]]` (L1).

## 5) Risk

**LOW-MEDIUM.**

The plans are thorough, the RESEARCH did empirical prototype verification (not just reading), and the extractions are verbatim moves of confirmed line ranges — a real silent-corruption regression is unlikely. The residual risk concentrates in M3 (DEBT-02's "zero behavior change" has no non-hardware end-to-end proof, only isolated unit tests + a gate that SKIPs in most environments) and M1 (locked-decision letter not literally satisfied). Neither blocks execution: the verbatim-extraction discipline + ffprobe cross-validation + hardware parity gate (when available) provide strong correctness assurance. The LOW items are polish.

---

## Consensus Summary

Both reviewers agree the plans are well-scoped, genuinely isolate a pure testable core (read/parse split), and use empirically-verified fixtures + the `-cues_to_front 1` cross-validation recipe. qwen: risk LOW. opencode: risk LOW-MEDIUM. No blockers; the deltas are correctness-proof completeness and edge coverage.

### Agreed Strengths
- Genuine pure read/parse split (`find_cues_position`/`peek_element_header`/`parse_cues_body` take bytes only) — the real DEBT-01 testability win.
- Byte-fixture cases A–E hit the right silent-corruption vectors; `None`-on-anomaly discipline (never raises) is correct.
- Cross-validation recipe empirically proven; `legacy/` confirmed byte-identical to `src/` pre-split (valid parity oracle).
- `contiguous_run` returns a concrete list; wave dependency (02-01→02-02) is load-bearing (shared test_keyframes.py import line).

### Agreed Concerns / integrate
1. **[MEDIUM — opencode M3] DEBT-02 has no NON-hardware end-to-end proof.** Only isolated unit tests + the hardware parity gate (which SKIPs off-Arc). Add a mocked `run_encode` integration test: patch `encode_chunk` to write canned N-byte `.obu` files and `count_frames` to the expected count, assert `movie.obu` == the scene-ordered concatenation AND assert the seek/trim strings passed to `chunk_command`. This is the strongest addition — proves the wiring byte-identically without hardware. (New `tests/unit/encoding/test_pipeline_wiring.py` or similar; no `test_pipeline.py` exists today.)
2. **[MEDIUM — opencode M1] D-08 letter: compare vs BOTH legacy inline AND ffprobe.** Task 3 only checks `cues == ffprobe`. D-08 (locked) says "both." Add a direct comparison against `legacy/encode_scenes.py`'s `keyframe_table_cues`, loaded via `importlib.util.spec_from_file_location` (isolates legacy's module-level `_START = time.monotonic()` side effect). Trivially satisfies the locked letter.
3. **[MEDIUM — opencode M2] Truth wording overstates the gate contract.** 02-02 `must_haves.truths` says "byte-identical movie.obu" but `scratch/parity_encode.py` falls back to frame-count + SSIM/PSNR-epsilon when qsvencc is non-deterministic. Reword the truth to "byte-identical when qsvencc is deterministic; frame-count + epsilon match otherwise" to match the gate + the Task-3 acceptance criteria.
4. **[MEDIUM — qwen C-01] `contiguous_run` must be tested with a dict input** — the call site passes `Dict[int,int]` (pipeline.py:128), not a set. Add `contiguous_run(0, {0:100,1:200,3:300}) == [0,1]`.
5. **[MEDIUM — qwen C-02] Add an empty-Cues-body fixture** — `parse_cues_body(b"", ...) is None` (legal zero-CuePoint Cues); exercises the `if not times: return None` guard.

### Edge test rows (LOW — both) / add
- `compute_chunk_seek_trim` `s=0` row (qwen C-03 / opencode L5): first scene at frame 0 → `("00:00:00.000", "0:{e-1}")`.
- `contiguous_run(10, {0,1,2}) == []` — post-flush all-consumed idle state (qwen C-04).
- tiny-header fixture `find_cues_position(b"\x00"*10, 10) is None` (qwen C-05).
- optional fuzz: ~1000 random byte strings through `find_cues_position`/`parse_cues_body`, assert None-or-valid, never raises (opencode).

### LOW polish (opencode) / apply where cheap
- **L1:** `contiguous_run` type hint should use `typing.Union[Dict[int,int], Set[int]]`, not PEP 604 `|` (D-11 CONVENTIONS mandates `typing` generics).
- **L2:** cross-validation `skipif` guards only `ffmpeg` presence but the recipe uses `-c:v libx264`; probe `ffmpeg -encoders` for libx264 (or use a codec always present).
- **L3:** make the `mkv.ebml` purity claim executable (AST/import check that it imports no `Path`/`open`/`stat`/`subprocess`), not review-only.
- **L4:** the Task-1 import-string assertion (`'from enpipe.mkv import ebml' in source`) is brittle vs the valid `import enpipe.mkv.ebml as _ebml` form — assert the `ebml\.(find_cues_position|...)` call pattern (matching `key_links`) instead.

### Divergent
None material — opencode simply went deeper (M1/M3, purity/import robustness); qwen focused on unit-test edge rows. No contradictions.

### Recommendation
No re-plan from scratch. Integrate items 1–5 (the MEDIUMs) + the edge rows + L1–L4 via `/gsd:plan-phase 2 --reviews`. M3 (mocked non-hardware e2e proof) and M1 (D-08 direct legacy comparison) are the priority — they make the two locked correctness claims backed by executable, hardware-independent steps.
