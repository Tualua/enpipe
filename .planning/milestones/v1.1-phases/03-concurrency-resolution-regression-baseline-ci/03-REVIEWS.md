---
phase: 3
reviewers: [qwen, opencode]
reviewed_at: 2026-07-08T14:47:47Z
plans_reviewed: [03-01-PLAN.md, 03-02-PLAN.md, 03-03-PLAN.md]
---

# Cross-AI Plan Review — Phase 3 (Concurrency Resolution + Regression Baseline + CI)

## Qwen Review

# Cross-AI Plan Review — enpipe Phase 3

## Summary

Three-wave plan to: (1) profile and resolve a Thread-vs-Process executor inconsistency in scene detection, document `dovi_tool`; (2) add a parallel==sequential regression test with runtime engagement guards; (3) wire ruff lint + non-hardware tests into GitHub Actions with the hardware tier visibly excluded. The plans are tightly coupled — Wave 2 depends on Wave 1's resolved executor, Wave 3 depends on Wave 2's regression test.

---

## Strengths

1. **Profiling-first discipline (D-01/D-02).** The two-layer measurement protocol (wall-clock A/B with use_qsv True/False + CPU-isolated microbenchmark) is the *only* unbiased way to resolve the contradiction. Pre-deciding the executor would be a guess.
2. **Runtime engagement guard in TEST-03.** Probing the actual clip frame count via ffprobe and asserting `actual_total_frames >= jobs*min_span` before the equality assertion is excellent — it prevents the silent-fallback-to-sequential trap that would make the test vacuous.
3. **Gate-arithmetic unit test as a second line of defense.** `test_parallel_gate.py` deterministically proves the clip parameters satisfy the parallel path gate, independent of ffmpeg output. Nice redundancy.
4. **CI supply-chain hygiene.** SHA-pinned `setup-uv`, `uv sync --locked` (not just `sync`), and conservative `select = ["F", "E9"]` ruff config are all proportionate, correct choices.
5. **Threat registers are concrete.** STRIDE entries map to specific test assertions and code paths, not generic filler.

---

## Concerns

### HIGH

**H-1: Profiling clip duration may be impractical.** Plan 01 Task 1 calls for a >=288s (4.8 min) synthetic clip at 24fps, 320x180 for jobs=4 profiling. That's ~6912 frames. Even with `-preset ultrafast` libx264, encoding a 4.8-minute video takes nontrivial time. If this is meant to run in the sandbox (which it is), the *profiling itself* could take 10-20 minutes wall-clock for the full A/B matrix (use_qsv True/False × jobs=1/jobs=4 × Layer 2 microbenchmark). Not a correctness issue, but a practical one — consider `jobs=2` (120s minimum) to cut total profiling time roughly in half, since the GIL signal doesn't need jobs=4 specifically.

**H-2: ProcessPoolExecutor → pickling risk on `QsvPipeStream`-adjacent state.** The plan correctly notes `_boundary_worker` and `_segment_worker` are module-level and take simple types (PathLike, DetectionConfig, ints/floats). However, DetectionConfig is a `@dataclass(frozen=True)` — frozen dataclasses pickle fine. The *real* risk: if any worker indirectly touches global state (e.g., `scenedetect` module-level singletons, OpenCV's GStreamer backend state), multiprocessing can break silently. The plan should add an explicit verification step: after switching to `ProcessPoolExecutor`, run the smoke check from Plan 01 Task 2's verify block, plus a second clip with different content, to confirm no pickling subprocess errors. This is low-probability but high-impact (it would fail in CI, not just produce wrong results).

### MEDIUM

**M-1: TEST-03 clip with only 2 segments (jobs=2) barely exercises the stitching path.** The regression test uses `jobs=2`, producing 2 segments. The `_sanitize_boundaries` + `non_cut_offsets` merge logic in `parallel.py` is most interesting with 3+ segments where boundary ordering and merge adjacency matter. A 2-segment case exercises the basic split but not the multi-boundary merge. The plan acknowledges this implicitly (the gate arithmetic test is parameterized), but the integration test itself only exercises the `jobs=2` case. Recommend parameterizing the integration test to also cover `jobs=3` (3 segments, 2 interior boundaries, 1 potential merge point).

**M-2: CI workflow `apt-get install ffmpeg mkvtoolnix` on ubuntu-latest.** The plan correctly identifies that non-QSV ffmpeg is needed. However, ubuntu-latest runners already ship with ffmpeg (often an older build). The `apt-get install` may conflict with or be a no-op alongside the pre-installed version. Consider `apt-get install --reinstall` or explicitly using the installed ffmpeg path. Also, `mkvtoolnix` may not be in the default ubuntu-latest apt repos without adding a PPA — verify this or pin to a known-available version.

**M-3: Ruff `E9` alone is insufficient for "syntax errors".** `E9` in ruff/pycodestyle covers `E902` (IOError reading file) and `E999` (SyntaxError). This is correct for the stated goal. However, the plan's description says "pyflakes + syntax errors only" — `E9` is correct for syntax errors, but `F` (pyflakes) alone would miss some real defects that `E` catches (e.g., `E722` bare except, `E711` None comparison). The chosen set is defensible, but the doc-comment should accurately state what it catches rather than overclaiming.

### LOW

**L-1: `scratch/profiling_debt03.py` as a throwaway.** It's fine in scratch/, but if the profiling methodology needs to be rerun (e.g., after a dependency upgrade), the script must be findable. A short README note in scratch/ would help. Minor.

**L-2: dovi_tool comment accuracy.** The plan correctly flags the HEVC-only limitation. Ensure the comment doesn't say "RPU extraction" without qualifying "HEVC-only" — the Phase-4 investigation might need a completely different mechanism for AV1.

---

## Suggestions

1. **Reduce profiling clip to jobs=2 (>=120s).** The GIL-vs-I/O signal is binary — you don't need jobs=4 to distinguish them. This cuts profiling time by ~2× with no loss of diagnostic power.
2. **Add `jobs=3` to the regression test parameterization.** `@pytest.mark.parametrize("jobs", [2, 3])` exercises the multi-boundary merge path that `non_cut_offsets` handles. The gate arithmetic test already covers the formula generically; the integration test should too.
3. **Verify mkvtoolnix availability on ubuntu-latest.** Quick check: `apt-cache show mkvtoolnix` on a fresh ubuntu-latest container. If unavailable, use `apt-get install -y mkvtoolnix` from the official MKVToolNix APT repo, or skip the mkvmerge-dependent tests in CI until Phase 4 (TEST-03 doesn't need mkvmerge — only TEST-02's EBML cross-validation does).
4. **Add a ProcessPool smoke-check step after the executor swap.** After Task 2 in Plan 01, run the equality assertion on a *second* distinct synthetic clip (even a 10s one, since the point is "processes start and return results", not profiling). This catches pickling issues before the regression test formalizes the baseline.
5. **Clarify the ruff doc-comment.** Replace any phrasing like "catches dead code" with "catches unused imports (F401), undefined names (F821), unused locals (F841), and syntax errors (E999)" — precise and defensible.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Profiling takes too long / OOM on sandbox | MEDIUM | LOW (just rerun with shorter clip) | Use jobs=2, 120s clip |
| ProcessPoolExecutor breaks on scenedetect/opencv internal state | LOW | HIGH (fails in CI, blocks Wave 2) | Smoke check with 2nd clip before formalizing baseline |
| TEST-03 exercises only 2-segment path, misses merge bugs | MEDIUM | MEDIUM | Parameterize jobs=2,3 |
| mkvtoolnix unavailable on ubuntu-lapt repos | MEDIUM | LOW (CI step fails, easily fixable) | Pre-check or use official APT repo |
| CI green but hardware behavior differs | LOW (by design) | LOW (explicitly named-out, documented) | Job naming + comment, per D-08 |
| Ruff config misses real defects due to conservative ruleset | LOW | LOW (pyflakes catches the common ones; pyright deferred to v2) | Document the tradeoff explicitly |

**Overall verdict:** The plans are well-structured, correctly ordered, and demonstrate strong awareness of the non-obvious failure modes (silent fallback gate, GIL masking, HEVC-vs-AV1 dovi_tool limitation). The HIGH concerns are addressable with small scope adjustments — none require re-architecting the approach. **Proceed with the suggested refinements.**

---

## OpenCode Review

## 1) Summary

Three wave-ordered plans: profile-and-resolve the `ThreadPoolExecutor`/`ProcessPoolExecutor` contradiction in `parallel.py` (03-01), capture a parallel==sequential regression baseline (03-02), and wire ruff + non-hardware tests into GitHub Actions (03-03). Well-researched, grounded in actual code (the `jobs*min_span` gate discovery at `parallel.py:120-123` is real and load-bearing). The picklability claim for a ProcessPool swap checks out: `_boundary_worker`/`_segment_worker` take primitive tuples and construct `QsvPipeStream` internally — genuinely low-risk. The main gap is an **incomplete engagement guard** in TEST-03 that misses a second fallback path.

## 2) Strengths

- **Measure-then-decide discipline** with locked ordering (DEBT-03 → TEST-03 → CI) is correct and load-bearing.
- **Gate arithmetic** (`min_span = max(2*72, round(60*24)) = 1440` → `jobs*60s`) verified at `parallel.py:120-123`; the dual guard (pure unit test + runtime ffprobe) is good defense-in-depth in intent.
- **ProcessPool picklability** confirmed — workers are module-level, args are `(path, config, marks/fps/total)` all primitives, return types picklable. The "low-risk swap" claim holds.
- **ruff `select=["F","E9"]`** verified-clean choice; correctly avoids the 15× `E702` on `mkv/ebml.py`. The `hardware` marker is already registered (`pyproject.toml:27`), so `-m "not hardware"` is sound.
- **setup-uv SHA-pinned**, `uv sync --locked`, tier naming — CI supply-chain hygiene is solid.
- **dovi_tool** doc correctly avoids overclaiming AV1 `extract-rpu` (HEVC-only, per `legacy/encode_scenes.py:15-16`).

## 3) Concerns

**HIGH — TEST-03 engagement guard misses the second fallback (`parallel.py:133-135`).** `detect_scenes_parallel` falls back to sequential in *two* places: the gate (line 121) **and** `if len(bnds) < 3` after boundary-finding (line 133: "границы схлопнулись -> последовательно"). The plan's runtime guard asserts `total_frames >= jobs*min_span` (first gate only) + `>=2 scenes` — but the sequential fallback *also* yields `>=2 scenes`, so it cannot distinguish a real parallel run from a silent fallback. If a future change breaks `find_boundary` (returns `None`), `bnds` collapses to `[start, end]` (len 2 < 3), the code falls back, and the equality test passes vacuously — **false green on the exact regression the test exists to catch**. The threat model's T-03-04 claims this is mitigated; it isn't fully.

**MEDIUM — `non_cut_offsets` merge path (`parallel.py:168-175`) is never exercised.** With one cut aligned to the segment mark, `is_cut=True`, so `non_cut_offsets` is empty and the merge — the most complex stitching logic — is skipped. The test proves happy-path equality but not merge-path correctness.

**MEDIUM — Decision rule infers ProcessPool benefit without measuring it on the real path.** Layer 2 is pure-CPU *by construction*, so ProcessPool will trivially win there; that doesn't confirm the real path benefits once process-startup/re-import overhead applies. Layer 1 measures ThreadPool only. If leaning toward switching, there's no direct measurement of the alternative.

**MEDIUM — Decision threshold is qualitative.** "Materially capture" is undefined, leaving room for implementer bias in a task explicitly framed as evidence-based. Specify concrete ratios.

**LOW — Profiling script (03-01 Task 1) has the same engagement gap** (">=2 scenes" doesn't prove >1 segment); the decision-backing numbers could come from a fallback run. Also LOW: CI doesn't explicitly install Python (likely fine via `uv sync` managed-Python, worth confirming). LOW: `jobs=2` only — more jobs exercises more stitching (tradeoff vs clip length/CI time).

## 4) Suggestions

- **Fix the HIGH gap**: add a direct engagement assertion to TEST-03 — wrap `_segment_worker` (or `_boundary_worker`) with a call-counter via `pytest-mock` and assert `call_count == jobs` (or `>1`). This is instrumentation, not mocking the logic under test; it doesn't weaken the regression assertion and definitively proves the parallel branch ran.
- **Exercise the merge path**: design the clip with a cut *not* aligned to a mark (so `find_boundary` returns `is_cut=False`), or add a focused unit test for `_sanitize_boundaries` + the `non_cut_offsets` merge with synthetic boundary inputs (`is_cut=False` cases). This is where stitching bugs would hide.
- **Quantify the DEBT-03 threshold**: e.g. "Layer 1 ThreadPool speedup < 1.5× AND Layer 2 ProcessPool/ThreadPool ratio > 2× → switch; else keep threads."
- **If ProcessPool is chosen, add a Layer 1.5**: temporarily swap executors and measure real-path `detect_scenes_parallel(jobs=4)` *before* committing the switch — confirm the microbenchmark win materializes end-to-end.
- Consider `--strict-markers` in addopts (marker is registered, so it's safe) to catch future marker-name typos.

## 5) Risk

**LOW–MEDIUM overall.** Detection output is unchanged regardless of executor choice (the smoke check and regression test guard it), and the CI/lint/DEBT-04 portions are low-risk and ready to execute. The residual risk is that **TEST-03 as written can pass vacuously** (via the `len(bnds) < 3` fallback, or by skipping the `non_cut_offsets` merge), giving false confidence that the parallel stitching is regression-guarded when it's only partially covered. This doesn't threaten output correctness but undermines TEST-03's *standing* value as the guard — fixable with a call-count assertion and a merge-path case before the baseline is considered captured.

---

## Consensus Summary

Both reviewers endorse the plans (qwen: proceed with refinements; opencode: LOW-MEDIUM). Measure-then-decide discipline, locked ordering, ProcessPool picklability (low-risk), ruff `F,E9`, and CI supply-chain hygiene all validated against the real code. The critical delta is that **TEST-03 can pass vacuously** — opencode found a second silent fallback the current engagement guard doesn't cover.

### Agreed Strengths
- Profiling-first, un-pre-decided executor resolution with locked DEBT-03→TEST-03→CI ordering.
- Runtime ffprobe engagement guard + pure gate-arithmetic test (defense in depth).
- ProcessPool picklability confirmed (module-level workers, primitive args); ruff `select=["F","E9"]` verified clean (avoids E702 on mkv/ebml.py); SHA-pinned setup-uv + `uv sync --locked`; dovi_tool HEVC-only caveat honored.

### Agreed Concerns / integrate (priority first)
1. **[HIGH — opencode] TEST-03 can pass VACUOUSLY via the second fallback.** `detect_scenes_parallel` falls back to sequential in TWO places: the `total_frames < jobs*min_span` gate (line 121) AND `if len(bnds) < 3` after boundary-finding (line 133). The current guard (`total_frames >= jobs*min_span` + `>=2 scenes`) does NOT distinguish a real parallel run from the second fallback (which also yields >=2 scenes). If `find_boundary` breaks, the equality test passes on a sequential run — false green on the exact regression it guards. **Fix: add a DIRECT engagement assertion — wrap `_segment_worker` (or `_boundary_worker`) with a `pytest-mock` call-counter and assert `call_count == jobs` (or `>1`). Instrumentation, not mocking the logic under test.** Apply the same to the 03-01 profiling script so its decision numbers can't come from a fallback run.
2. **[MEDIUM — opencode] The `non_cut_offsets` merge path (`parallel.py:168-175`) is never exercised** — the most complex stitching logic. Add a focused unit test for `_sanitize_boundaries` + the `non_cut_offsets` merge with synthetic `is_cut=False` boundary inputs, and/or design the clip with a cut NOT aligned to a segment mark.
3. **[MEDIUM — qwen M-1] Parameterize the regression test `jobs=[2,3]`** — a 3-segment case exercises the multi-boundary merge; jobs=2 only covers the basic split.
4. **[MEDIUM — opencode] Quantify the DEBT-03 decision threshold.** "Materially capture" is qualitative → implementer bias. Specify concrete ratios, e.g. "Layer-1 ThreadPool speedup < 1.5x AND Layer-2 ProcessPool/ThreadPool ratio > 2x → switch to ProcessPool; else keep threads."
5. **[MEDIUM — opencode] If leaning ProcessPool, add a Layer-1.5 real-path measurement** (temporarily swap executors, measure `detect_scenes_parallel(jobs=N)` end-to-end) BEFORE committing — Layer-2 is pure-CPU by construction so ProcessPool trivially wins there; confirm the win survives process-startup/re-import overhead on the real path.
6. **[MEDIUM — qwen H-2] ProcessPool pickling smoke-check** on a 2nd distinct clip after any swap (guards against scenedetect/opencv module-state issues that fail in CI) before the baseline is considered captured.

### Practical / lower priority
- **[qwen H-1] Profiling clip time:** a >=288s jobs=4 clip makes the A/B matrix slow. Profile at `jobs=2` (>=120s + margin) — the GIL signal is binary and doesn't need jobs=4 — to cut profiling wall-clock ~2x. (Keep the regression test's jobs=[2,3] parameterization for stitching coverage.)
- **[qwen M-2 / opencode LOW] CI ffmpeg/mkvtoolnix on ubuntu-latest:** ffmpeg is pre-installed (apt may no-op); mkvtoolnix may need a PPA. TEST-03 needs only ffmpeg (not mkvmerge) — make the mkvtoolnix install best-effort / confirm availability, and don't let it block the ffmpeg-only tests.
- **[qwen M-3 / opencode] Precise ruff doc-comment:** state exactly what `F,E9` catches (F401 unused imports, F811/F841, F821 undefined names, E999 syntax) rather than "catches dead code."
- **[opencode LOW] `--strict-markers`** in addopts (marker already registered) to catch future marker typos. Note the profiling `scratch/` script's findability.

### Divergent
None material — opencode went deeper on the vacuous-pass hole and merge path; qwen on profiling practicality and CI apt specifics. Complementary.

### Recommendation
No re-plan. Integrate via `/gsd:plan-phase 3 --reviews`. Priority = #1 (call-count engagement assertion — closes the vacuous-pass hole that is TEST-03's whole reason to exist), then #2/#3 (merge-path coverage + jobs=[2,3]), then the decision-threshold quantification (#4/#5) and the practical CI/profiling items.
