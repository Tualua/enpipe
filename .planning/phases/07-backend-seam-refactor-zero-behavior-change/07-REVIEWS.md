---
phase: 7
reviewers: [opencode, qwen]
reviewed_at: 2026-07-23T11:29:17Z
plans_reviewed: [07-01-PLAN.md, 07-02-PLAN.md, 07-03-PLAN.md, 07-04-PLAN.md]
skipped: [claude (self — running inside Claude Code); gemini/codex/coderabbit/cursor (not installed); ollama/lm_studio/llama_cpp (endpoints up but no models loaded)]
---

# Cross-AI Plan Review — Phase 7 (Backend Seam Refactor, zero behavior change)

Two independent external reviewers (OpenCode, Qwen Code) reviewed all four plans plus
CONTEXT.md and RESEARCH.md. Both grounded their assessment against the actual source
(OpenCode ran greps/reads to verify claims independently). Overall verdict from both:
**well-engineered, ready to execute with minor clarifications** — one reviewer rated
overall risk LOW-MEDIUM, the other LOW.

---

## OpenCode Review

I'll review these plans against the actual codebase to ground my assessment. Let me first verify the key claims.
Now let me verify the test files and other key claims.
Let me verify the integration test, the hdr module, and check for the `_concurrency_harness.py` claim.
Let me verify the hardware test, the concurrency immunity test, and the cli_run test.
Let me check the pyproject.toml for ruff config and test markers, and verify the golden test fixture path convention.
Now I have enough to write a thorough, grounded review. Let me verify one final detail about the golden test's import path to confirm the critical ordering issue I spotted.
I've completed my analysis. Here's my review:

---

# Cross-AI Plan Review: Phase 7 — Backend Seam Refactor

## 1. Summary

These four plans constitute a well-researched, methodically ordered structural refactor that introduces a `backends/` seam before any ffmpeg code exists, preserving byte-identity through verbatim moves and a two-tier parity gate (fast golden-argv snapshots + on-Arc byte-identity). The research is exceptional — every claim was verified against actual file:line content, the dangling-import inventory is complete (I confirmed it independently via grep), and the pitfall analysis (especially the silently-no-op monkeypatch risk in `test_pipeline_wiring.py` and the `_concurrency_harness.py` collection-time import breakage) catches real, subtle bugs. However, there is one **HIGH-severity wave-ordering bug**: Plan 07-03 removes `chunk_command` from `encoding/chunk.py` but does not list `tests/unit/backends/test_golden_argv.py` in its `files_modified`, even though that test (created in 07-01) imports `from enpipe.encoding.chunk import chunk_command` — the fast tier would fail with `ImportError` between waves 3 and 4. There are also a few MEDIUM concerns around the D-10 gate's actual strength (the existing test has a frame-count fallback that undercuts the "byte-identical" claim), an under-specified `fmt_seek` test move, and an ambiguous resolve-vs-preflight ordering.

---

## 2. Strengths

- **Exceptional research grounding.** Every interface signature, import site, and call site cited in the plans was verified against the actual source. I independently confirmed the complete dangling-import inventory (8 test files + 1 production file) via grep — the plans miss nothing. The `_concurrency_harness.py` collection-time breakage catch (Plan 07-03 Task 2) is a particularly sharp find: pytest imports hardware-marked modules during collection even under `-m "not hardware"`, so a stale `from enpipe.encoding.chunk import chunk_command` at `_concurrency_harness.py:28` would break the fast tier silently.

- **Verbatim-move discipline is the right byte-identity defense.** Moving `chunk_command`/`parse_metrics`/`ICQ`/`QPMAX`/`GOP_LEN`/`fmt_seek` without any logic edits, then proving equivalence via golden argv fixtures, is exactly the right approach for a zero-behavior-change refactor on correctness-critical code.

- **The golden-argv fixture design is sound.** Keying fixtures on the numeric record `(kf_frame, kf_time, start_off, end_off)` rather than formatted strings means the D-04 seek/trim numeric split cannot change the fixtures — the same 24 rows validate both pre-refactor `chunk_command` and post-refactor `build_command`. The `_argv_for(row)` isolation in 07-01 Task 2 is well-designed for the 07-04 re-point.

- **The wiring test monkeypatch fix is correctly identified as the highest-risk point.** Plan 07-03 Task 1 explicitly calls out that `monkeypatch.setattr(p, "chunk_command", ...)` would silently no-op after the refactor (pipeline.py would call `backend.build_command` instead), and prescribes re-pointing the spy to exercise the real seam. This is the kind of subtle test-rot that would otherwise make the test pass for the wrong reason.

- **`resolve()` raising `ValueError` instead of `die()`** (Pitfall 4) correctly preserves the codebase's pure/CLI split — unit tests can `pytest.raises(ValueError)` without catching `SystemExit`.

- **The `Backend` frozen-dataclass follows the exact `Scene`/`DetectionConfig` precedent** — no ABC/Protocol hierarchy, matching the "no object-oriented service layer" convention.

- **Threat model is proportionate.** The only new input surface (backend-name string → `resolve()`) is correctly identified and mitigated via a fixed-dict allowlist with fail-fast `ValueError`. No over-engineering.

---

## 3. Concerns

### HIGH

**C1: Golden test import breakage between Plan 07-03 and Plan 07-04** (wave-ordering bug)

Plan 07-01 Task 2 creates `tests/unit/backends/test_golden_argv.py` with `_argv_for(row)` importing `from enpipe.encoding.chunk import chunk_command` and `from enpipe.encoding.keyframes import fmt_seek`. Plan 07-03 Task 1 **deletes** `chunk_command` from `encoding/chunk.py`, and Task 2 **deletes** `fmt_seek` from `encoding/keyframes.py`. But `tests/unit/backends/test_golden_argv.py` is **not in 07-03's `files_modified` list**, and neither task describes fixing its imports.

Plan 07-04 Task 2 re-points `_argv_for` to `build_command` — but that's one wave later. Between 07-03 and 07-04, the fast tier would fail at collection with `ImportError: cannot import name 'chunk_command' from 'enpipe.encoding.chunk'`.

This directly contradicts 07-03's own acceptance criteria: `python -m pytest -q -m "not hardware"` exits 0, and `grep -rnE "from enpipe.encoding.chunk import.*(chunk_command|parse_metrics)|from enpipe.encoding.keyframes import.*(fmt_seek|compute_chunk_seek_trim\b)" src/ tests/` returns nothing. The golden test's import matches that grep pattern — the acceptance criteria **requires** fixing it, but the task doesn't include it.

**Fix:** Add `tests/unit/backends/test_golden_argv.py` to 07-03 Task 2's `files_modified` and re-point its imports to `enpipe.backends.qsvencc` (`chunk_command`, `fmt_seek`) in the same wave that removes them from their old homes. Then 07-04 Task 2 only changes the assertion from `chunk_command(seek, trim, ...)` to `build_command(kf_frame, kf_time, start_off, end_off, ...)`.

### MEDIUM

**C2: D-10 byte-identity claim vs the existing test's frame-count fallback**

Plan 07-04 Task 3 claims the existing `test_sdr_legacy_oracle_parity` is the D-10 gate and states: *"Expected: PASS — the assertion that `legacy_movie.read_bytes() == enpipe_movie.read_bytes()` (byte-identical pre-mux movie.obu) holds."* But the actual test (`test_hardware_real_media.py:393-399`) has a **determinism-aware fallback**:

```python
if legacy_movie.read_bytes() == enpipe_movie.read_bytes():
    pass  # deterministic qsvencc on this box -- byte-identical parity holds
else:
    assert count_frames(legacy_movie) == count_frames(enpipe_movie), (
        "pre-mux movie.obu differs AND frame counts differ -- qsvencc "
        "non-determinism alone cannot explain this; real parity failure"
    )
```

If qsvencc is non-deterministic on the test box (a documented possibility — see the test's own comments), the test passes on **frame-count parity alone**, not byte-identity. SC#2 says "byte-identical pre-mux `movie.obu`" — but the existing test does not guarantee that. The plan overstates what D-10 proves.

The D-09 golden-argv test + the wiring test together provide strong coverage of argv correctness and seek/trim wiring (which is the real refactor risk), so this doesn't leave the phase unguarded — but the D-10 success criterion should either be honestly downgraded to "frame-count parity (byte-identity when qsvencc is deterministic)" or the test should be strengthened to require byte-identity for the refactor specifically (e.g., compare enpipe-pre-refactor output vs enpipe-post-refactor output, not enpipe vs legacy oracle — since the same qsvencc argv on the same input should produce identical bytes across two runs of the same code, whereas enpipe-vs-legacy compares two different code paths).

**C3: `fmt_seek` test move not explicitly specified in Plan 07-02**

Plan 07-03 Task 2 says: *"remove the `fmt_seek` and `compute_chunk_seek_trim` test functions [from `test_keyframes.py`] (they are covered in `tests/unit/backends/test_qsvencc.py` per 07-02)."* But Plan 07-02 Task 2 only explicitly says to *"carry over the chunk_command + parse_metrics pure-logic assertions from tests/unit/encoding/test_chunk.py"* — it does not mention carrying over the `fmt_seek` tests from `test_keyframes.py`. The RESEARCH.md "Open Question 1 (RESOLVED)" says `fmt_seek` tests should move to `test_qsvencc.py`, but the plan task itself doesn't encode this. An implementer following 07-02 Task 2 literally would miss the `fmt_seek` test move, then 07-03 Task 2 would remove `fmt_seek` tests from `test_keyframes.py` leaving them with no home — a coverage gap.

**Fix:** Add explicit instruction to 07-02 Task 2: "Also carry over the `fmt_seek` tests from `tests/unit/encoding/test_keyframes.py` (lines 31-37) into `tests/unit/backends/test_qsvencc.py`, importing `fmt_seek` from `enpipe.backends.qsvencc`."

**C4: `resolve()` vs preflight ordering ambiguity affects the `--backend bogus` test**

Plan 07-03 Task 1 says: *"Near the top of `run_encode`, resolve the backend defensively... place it before/with the preflight so a bad name fails fast."* The phrase "before/with" is ambiguous. Plan 07-04 Task 1's acceptance criterion requires: *"`enpipe encode --backend bogus <video>` exits non-zero with a message listing valid backends."* If `resolve()` is placed **after** the preflight (the "with" reading), and tools are not stubbed, the preflight `die("не найден qsvencc")` would fire first — the test would pass (SystemExit) but with the **wrong error message**, not the backend-listing message. If `resolve()` is placed **before** the preflight (the "before" reading), the test works correctly regardless of tool availability.

**Fix:** Specify unambiguously: "`resolve()` is the FIRST statement in `run_encode`, before the preflight loop." This also makes the `--backend bogus` test work without needing to stub `shutil.which`.

### LOW

**C5: `_concurrency_harness.py` docstring has a second stale reference**

Plan 07-03 Task 2 says to reword the harness docstring's reference to `tests/unit/encoding/test_chunk.py` → `tests/unit/backends/test_qsvencc.py`. But the same docstring (`_concurrency_harness.py:108`) also references `enpipe.encoding.chunk.ICQ` — which becomes `enpipe.backends.qsvencc.ICQ` after the move. The plan only mentions "that one sentence" about the test file. The implementer should update both references.

**C6: `pipeline.py` importing `fmt_seek` from `backends/qsvencc.py` creates temporary cross-layer coupling**

Plan 07-03 Task 1 has `pipeline.py` import `fmt_seek` from `enpipe.backends.qsvencc` to keep the CSV seek column byte-identical. This means the general orchestration module imports from a specific backend module — a temporary coupling that Phase 8 must generalize. The plan acknowledges this ("SANCTIONED minimal-diff coupling... Phase 8 will generalize per-backend logging") and prescribes a Russian comment. This is a reasonable trade-off for zero-behavior-change, but worth noting as tech debt that Phase 8 inherits.

**C7: `List` import in `chunk.py` becomes unused after the move**

After 07-03 removes `chunk_command` (the only user of `List[str]` in `chunk.py`), the `from typing import List, Optional, Tuple` line has an unused `List`. The plan says "Drop the now-unused `os`/`re` imports" but doesn't mention `List`. The `ruff check` acceptance criterion (F401) would catch this, so it's self-correcting — but explicitly noting it would save a ruff-fail-fix cycle.

**C8: The "first_gt0" matrix row label is slightly misleading**

Plan 07-01's "first_gt0" row (`kf_frame=48, kf_time=2.0, start_off=22, end_off=47`) is labeled as testing "a non-zero-indexed chunk of the run." But `chunk_command` receives no chunk index — the only thing that distinguishes this row from "on_kf" is `start_off=22` (mid-GOP start). The "first>0" property (chunk position within a run) is not testable through `chunk_command` alone. The row IS valuable (it tests mid-GOP seek/trim), just the label conflates chunk position with seek/trim values. No functional impact.

---

## 4. Suggestions

- **Fix C1 first** — it's the only issue that would cause CI to fail. Add `tests/unit/backends/test_golden_argv.py` to 07-03 Task 2's `files_modified` and describe the import re-point there (to `enpipe.backends.qsvencc.chunk_command`/`fmt_seek`), leaving only the `chunk_command`→`build_command` assertion change for 07-04.

- **For C2**, consider adding a NEW test (in 07-04 Task 3 or a new task) that compares enpipe-post-refactor's `movie.obu` against enpipe-**pre-refactor**'s `movie.obu` (captured as a fixture or by running `legacy/encode_scenes.py` which is the frozen oracle). This would be a true byte-identity gate for the refactor itself, independent of qsvencc non-determinism concerns. Alternatively, honestly restate D-10 as "frame-count parity with byte-identity when qsvencc is deterministic" and rely on D-09 + wiring test for the byte-identity proof.

- **For C3**, add the `fmt_seek` test carry-over to 07-02 Task 2's `<action>` explicitly, with file:line reference to `test_keyframes.py:31-37`.

- **For C4**, change "place it before/with the preflight" to "place it as the first statement in `run_encode`, before the preflight loop" — removing the ambiguity.

- **Consider a pre-flight `ruff check` after each task**, not just at the end of each plan. The plans run `ruff check` in acceptance criteria, but an intermediate ruff pass after the verbatim move (07-02 Task 2) would catch unused imports before they propagate.

- **The `_concurrency_harness.py:103` `qsvencc_command` function** overrides `--icq` in the returned argv via `cmd.index("--icq"); cmd[idx + 1] = str(icq)`. After the move, `chunk_command` is imported from `enpipe.backends.qsvencc` — verify this argv-mutation pattern still works identically (it should, since `chunk_command` returns a fresh list each call, but worth an explicit assertion in the test).

---

## 5. Risk Assessment

**Overall: LOW-MEDIUM**

The plans are thorough, well-researched, and grounded in direct codebase reads. The refactor is a pure code relocation on a small, well-tested surface with no new dependencies, no new algorithms, and no new subprocess calls. The primary risk is mechanical (dangling imports), and the research enumerates every import site — I verified this independently and found no gaps in the inventory.

The one HIGH concern (C1: golden test import breakage) is a **wave-ordering artifact**, not a design flaw — the fix is a one-line `files_modified` addition and a paragraph in 07-03 Task 2. It would cause CI to fail between waves 3 and 4 if left unfixed, but it does not threaten the correctness of the final state.

The MEDIUM concerns (C2-C4) are about **plan precision**, not design soundness — the D-10 gate is slightly overstated, one test move is under-specified, and one ordering is ambiguous. None of these would produce incorrect output; they would at worst cause a test to pass for the wrong reason (C2) or require a ruff-fail-fix cycle (C3/C4).

The load-bearing invariant — qsvencc argv byte-identity through the seam refactor — is well-defended by the combination of: (1) verbatim-move discipline, (2) D-09 golden-argv fast-tier test (24 rows × 4 HDR cases × metrics on/off), (3) the wiring test exercising the real `build_command` path with seek/trim assertions, and (4) the on-Arc D-10 check. With C1 fixed, the plans achieve the phase goals reliably.

---

## Qwen Review

# Phase 7 Plan Review — Backend Seam Refactor

## Summary

These four plans present a well-sequenced, mechanically disciplined refactor with exceptional attention to the zero-behavior-change invariant. The plans correctly identify every dangling import site, correctly scope the `--backend` scaffold to qsvencc-only (per D-06), and construct a sound two-tier parity gate (fast golden-argv snapshot + on-Arc byte-identity). The wave ordering (fixtures → additive seam → atomic swap → CLI + hardware gate) is optimal. My review focuses on a few remaining gaps and one medium-risk ambiguity in the wiring-test monkeypatch rewrite.

---

## Strengths

- **Complete dangling-import inventory.** The Research/Pitfall-1 table enumerates every production and test import site of every symbol being moved, with file:line anchors. This is the single most critical artifact for a pure-move refactor, and nothing is missed.
- **Wave ordering is optimal.** 07-01 captures golden truth *before* any code moves; 07-02 is purely additive; 07-03 performs the swap in one coherent wave; 07-04 closes the CLI and hardware gates. No wave breaks a predecessor.
- **Verbatim-move discipline is explicit and checkable.** Plans call out exact source ranges (`chunk.py:21-23`, `keyframes.py:101-111`, etc.) and state "no logic edits" with acceptance-criteria grep assertions to confirm the move landed.
- **Two-tier parity gate is sound.** The fast golden-argv test (D-09) catches preset/arg drift on every push, and the existing `test_sdr_legacy_oracle_parity` test genuinely does drive the pipeline end-to-end via public CLI, making it a valid D-10 proxy with zero edits needed beyond the import fix in 07-03.
- **`resolve()` raises `ValueError`, not `SystemExit` (Pitfall 4).** This preserves the codebase's established pure/CLI split and lets unit tests use `pytest.raises(ValueError)`.
- **The `_argv_for` helper isolation in 07-01 Task 2 is a small but excellent detail.** It makes the 07-04 re-point to `build_command` a surgical single-function edit with zero risk of touching the fixture-loading/parametrization boilerplate.
- **`tests/integration/_concurrency_harness.py` import fix is correctly flagged as a BLOCKER in 07-03.** This module is imported at module-level by `test_concurrency_immunity.py`, so a stale import breaks fast-tier *collection*, not just runtime — correctly identified and prioritized.

---

## Concerns

### MEDIUM: `test_pipeline_wiring.py` monkeypatch rewrite is underspecified

07-03 Task 1 describes two options (a) and (b) for rewriting the wiring test's monkeypatch targets, but does not commit to one. The plan says "replace the chunk_command spy with **either** (a) monkeypatching `p.resolve` to return a fake Backend whose `build_command` is a spy... **or** (b) leaving the real backend and asserting the recorded argv equals `build_command(...)`."

This is a critical design decision with downstream consequences:
- **Option (a)** requires creating a `Backend` fake with a spy `build_command`, which means either subclassing the frozen dataclass (impossible) or wrapping it (feasible but introduces a mock layer).
- **Option (b)** is simpler but means the test exercises the *real* `build_command` path — which is actually fine, since the golden test already verifies that path's output.

**Recommendation:** Commit to option (b) — leave the real backend, monkeypatch only `encode_chunk` and `count_frames`, and assert the argv recorded from the real `build_command` matches the numeric core. This avoids introducing a mock Backend shape that future Phase-8 implementers might copy as precedent.

### MEDIUM: `meta[i]` seek/trim strings in `run_encode` — how are they formatted post-refactor?

07-03 Task 1 says: "keep `meta[i] = (s, e, seek, trim)` unchanged" and separately says "seek = fmt_seek(kf_time); trim = f'{start_off}:{end_off}'" — but this code lives in `pipeline.py`, which no longer imports `fmt_seek`. The plan says to import it from `enpipe.backends.qsvencc` ("SANCTIONED minimal-diff coupling"), but this couples the *orchestration* layer to a *specific backend's* string formatter.

This is actually **correct and necessary** for byte-identical CSV/log output in this phase, but it needs an explicit comment in the plan (and in the eventual code) that this coupling is intentional, phase-scoped, and will be generalized in Phase 8 (e.g., via a backend-supplied formatting callable or by having `meta` store the numeric record instead).

### LOW: `--backend` help text inconsistency between `encode` and `run` subparsers

07-04 Task 1 adds `--backend` to both `encode_p` and `run_p` with `default=None`. The plan does not explicitly state whether `--help` should show the current resolved default ("qsvencc") or `None`. The existing `--jobs` arg uses `default=ENCODE_JOBS` (a concrete number), so users seeing `--backend None` in help would be mildly confusing. This is cosmetic, but worth a one-line decision.

### LOW: `test_chunk.py` deletion in 07-03 Task 2

The plan says to DELETE `tests/unit/encoding/test_chunk.py` because its assertions moved to `test_qsvencc.py` (07-02). However, if this file contains *any* `count_frames` tests that are NOT covered in `tests/subprocess/encoding/test_chunk.py`, those would be lost. The plan should add a quick grep assertion like `grep -c "count_frames" tests/unit/encoding/test_chunk.py` to confirm nothing of value is being deleted.

### LOW: No explicit acceptance criterion for the `_concurrency_harness.py` docstring reword

07-03 Task 2 says "reword that one sentence [in `_concurrency_harness.py`] to cite `tests/unit/backends/test_qsvencc.py` instead" but the acceptance criteria for 07-03 don't include a check for this. Minor, but should be added to the grep checklist.

### LOW: `BACKEND` env-var shadowing edge case in `backends/__init__.py`

The `resolve()` function uses `name = flag_value or BACKEND`. If a user passes `--backend ""` (empty string), this resolves to the env default, not the empty string — which is actually **correct behavior** (empty string is not a valid backend name). But if someone sets `BACKEND=""` in the environment, `BACKEND` module constant is `""`, and `resolve(None)` would try to look up `""` in the registry, raising `ValueError`. This is a corner case that only arises from misconfiguration, and the error message ("неизвестный backend ''; допустимые: qsvencc") is actually informative. No action needed, just noting it.

---

## Suggestions

1. **Commit to option (b) for the wiring-test rewrite** (see MEDIUM concern above). The plan should not leave this as "either/or" — pick one and spec it out fully in the task's `<action>` block.

2. **Add an explicit `meta` formatting comment to 07-03 Task 1.** Note that importing `fmt_seek` from `enpipe.backends.qsvencc` into `pipeline.py` is intentional, phase-scoped, and will be generalized in Phase 8 (e.g., `backend.format_seek(kf_time, start_off, end_off)`).

3. **Add a deletion guard to 07-03 Task 2** for `test_chunk.py`: confirm that `count_frames` test coverage survives in `tests/subprocess/encoding/test_chunk.py` before deleting the unit test file.

4. **Add `--backend` help-text decision to 07-04 Task 1.** Either use `default=BACKEND` (shows "qsvencc" in help, matching `--jobs` precedent) or add a note that `None` is intentional (defers display to `resolve()`).

5. **Consider adding a quick `ruff check` run to each plan's verification step** as an acceptance criterion (only 07-02 and 07-03 currently have this). It is cheap and catches unused imports immediately after each move.

6. **Add the concurrency-harness docstring fix to 07-03 acceptance criteria.** A simple `grep -c "test_qsvencc" tests/integration/_concurrency_harness.py` confirms the comment was updated.

---

## Risk Assessment: **LOW**

These plans are exceptionally well-engineered for a pure structural refactor. The risks are almost entirely mechanical (dangling imports, monkeypatch target drift, Namespace field omission) and every single one is identified, enumerated with file:line anchors, and guarded by acceptance criteria. The two-tier parity gate (golden argv fast test + existing hardware oracle test) provides both CI-frequency and end-to-end byte-identity verification.

The only non-trivial risk is the wiring-test monkeypatch rewrite ambiguity (MEDIUM), which could result in a test that silently passes for the wrong reason if not carefully implemented. Committing to option (b) and adding an explicit argv assertion against the real `build_command` closes this gap.

No scope creep detected — the plans stay strictly within the Phase 7 boundary (no ffmpeg code, no HDR routing, no streaming orchestrator). The plans are ready to execute with the minor clarifications noted above.

---

## Consensus Summary

Both reviewers independently rate the plans as exceptionally well-researched for a pure
structural refactor, with risk concentrated in mechanical (dangling-import / test-target)
failure modes that the research enumerates exhaustively. Neither found a design flaw; all
findings are plan-precision or wave-ordering refinements. The load-bearing invariant —
qsvencc argv byte-identity through the seam — is judged well-defended by the combination of
verbatim-move discipline + D-09 golden-argv fast test + the wiring test on the real
`build_command` path + the on-Arc D-10 check.

### Agreed Strengths (raised by both reviewers)
- **Complete dangling-import inventory** with file:line anchors — the single most critical
  artifact for a pure-move refactor; OpenCode independently re-verified it via grep and found
  no gaps.
- **Optimal wave ordering** — fixtures (07-01) capture golden truth *before* any move;
  07-02 is purely additive; 07-03 is one coherent swap; 07-04 closes CLI + hardware gates.
- **Verbatim-move discipline** made explicit with exact source ranges and grep acceptance
  criteria proving the move landed with no logic edits.
- **Two-tier parity gate is sound** (fast golden-argv snapshot + on-Arc byte-identity).
- **`resolve()` raises `ValueError`, not `SystemExit`** (Pitfall 4) — preserves the pure/CLI
  split so unit tests can use `pytest.raises(ValueError)`.
- **`_argv_for` helper isolation** in 07-01 Task 2 makes the 07-04 re-point surgical.
- **`_concurrency_harness.py` collection-time import** correctly flagged/prioritized in 07-03
  (module-level import by a hardware-marked test breaks fast-tier *collection*, not runtime).
- **Proportionate threat model** — the only new input (backend-name string) is mitigated by a
  fixed-allowlist fail-fast `ValueError`; no over-engineering.

### Agreed Concerns (raised by both — highest priority for a --reviews replan)
- **[MEDIUM] Wiring-test monkeypatch rewrite is underspecified.** Both flag that 07-03 Task 1
  leaves the rewrite ambiguous. Qwen recommends **committing to option (b)**: leave the real
  backend, monkeypatch only `encode_chunk`/`count_frames`, and assert the argv recorded from
  the *real* `build_command` matches the numeric core — avoids introducing a mock `Backend`
  shape Phase-8 implementers might copy. Risk if unhandled: a test that passes for the wrong
  reason.
- **[MEDIUM] `pipeline.py` importing `fmt_seek` from `backends/qsvencc`** couples the
  orchestration layer to a specific backend's formatter. Both agree it is *necessary* for
  byte-identical CSV/log output this phase, but both want it explicitly commented as
  intentional, phase-scoped tech debt that Phase 8 must generalize (e.g. a backend-supplied
  format callable, or storing the numeric record in `meta`).
- **[LOW] Per-task `ruff check`** — both suggest promoting `ruff check` (F401 unused imports)
  to an acceptance criterion on *every* move task, not just some, to catch drift immediately.
- **[LOW] `_concurrency_harness.py` docstring** has stale references beyond the one the plan
  rewords (OpenCode: also `enpipe.encoding.chunk.ICQ`), and 07-03 has no acceptance criterion
  asserting the reword landed.

### Divergent Views (worth investigating before/at replan)
- **Golden-argv test import breakage between waves 3 and 4 (OpenCode C1, HIGH — Qwen did not
  raise).** OpenCode argues `tests/unit/backends/test_golden_argv.py` (created in 07-01)
  imports `chunk_command`/`fmt_seek` from `enpipe.encoding.*`, which 07-03 deletes, but the
  re-point to `build_command` only happens in 07-04 — so the fast tier would fail at
  *collection* between the two waves, contradicting 07-03's own "pytest -m 'not hardware'
  exits 0" acceptance criterion and its repo-wide dangling-import grep. Qwen instead praised
  the `_argv_for` isolation as making the re-point clean, implicitly assuming it is handled in
  the swap wave. **This is the single most important item to confirm:** verify whether 07-03
  re-points `test_golden_argv.py` (and lists it in `files_modified`) or defers it to 07-04. If
  deferred, OpenCode's fix applies — move the import re-point into 07-03, leaving only the
  `chunk_command`→`build_command` assertion change for 07-04.
- **Strength of the D-10 gate (OpenCode C2, MEDIUM vs Qwen "valid proxy, zero edits").**
  OpenCode notes the existing `test_sdr_legacy_oracle_parity` has a determinism-aware fallback
  that passes on *frame-count* parity alone when qsvencc is non-deterministic — so SC#2's
  "byte-identical `movie.obu`" is overstated by that test. Suggests a true refactor byte-identity
  gate comparing enpipe-**pre**-refactor vs enpipe-**post**-refactor output (same argv, same
  input → identical bytes across two runs of the code), independent of qsvencc non-determinism.
  Qwen judged the same test a valid D-10 proxy needing only the import fix. **Recommendation:**
  either honestly restate D-10 as "frame-count parity, byte-identical when qsvencc is
  deterministic" or add the pre/post self-comparison OpenCode proposes.

### Unique lower-severity items (single reviewer)
- OpenCode C3: `fmt_seek` test carry-over to `test_qsvencc.py` is stated in 07-03 but not
  encoded in 07-02 Task 2's action — an implementer following 07-02 literally would miss it,
  leaving those tests homeless after 07-03 removes them from `test_keyframes.py`.
- OpenCode C4: "place `resolve()` before/with the preflight" is ambiguous; if placed *after*
  the preflight, `enpipe encode --backend bogus` (tools present) dies with the preflight
  message, not the backend-listing message — making the 07-04 test pass on the wrong error.
  Fix: make `resolve()` the first statement in `run_encode`.
- OpenCode C7: `List` import in `chunk.py` becomes unused after the move (ruff F401 self-catches).
- Qwen LOW: `--backend default=None` shows `None` in `--help` (vs `--jobs` showing a concrete
  default) — decide `default=BACKEND` or add a note.
- Qwen LOW: add a deletion guard grep before removing `tests/unit/encoding/test_chunk.py` to
  confirm no unique `count_frames` coverage is lost.
- Qwen LOW: `BACKEND=""` env misconfiguration → `resolve(None)` raises a (correctly informative)
  `ValueError`; no action needed, noted for awareness.

---

*To incorporate this feedback into the plans, run:* `/gsd:plan-phase 7 --reviews`
