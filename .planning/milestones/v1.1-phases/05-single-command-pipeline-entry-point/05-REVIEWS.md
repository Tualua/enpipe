---
phase: 5
reviewers: [qwen, opencode]
reviewed_at: 2026-07-09T01:36:08Z
plans_reviewed: [05-01-PLAN.md]
---

# Cross-AI Plan Review — Phase 5 (Single-Command Pipeline Entry Point)

## Qwen Review

# Phase 5 Plan Review — 05-01-PLAN.md

## 1. Summary

The plan adds a third `enpipe run <video>` subcommand that sequentially calls `run_detect` then `run_encode` in one invocation. Three tasks: (1) add the `run` subparser + `run_pipeline` handler to `cli/main.py` with `--detect-jobs`/`--encode-jobs` to resolve the `--jobs` collision, (2) a fast mocked unit test proving order and per-stage arg routing, (3) a hardware-gated parity test comparing `enpipe run` output against a manual two-step detect+encode on real Arc hardware. Zero behavior change to either stage or existing commands.

## 2. Strengths

- **Byte-identical by construction**: Reusing `run_detect`/`run_encode` verbatim with identical Namespace values makes parity the default, not a property to be proven — the tests confirm rather than discover correctness.
- **Collision resolution is clean**: `--detect-jobs`/`--encode-jobs` is the right call — a single `--jobs` would silently hide which stage it targets. Separate flags with preserved legacy defaults are unambiguous.
- **Test seam is proven**: The existing `test_cli_dispatch.py` already demonstrates monkeypatching `enpipe.cli.main.run_detect`/`run_encode` at module-global scope; Task 2 extends this pattern, not invents a new one.
- **Hardware parity mirrors Phase 4 precedent**: The `movie.obu` byte-compare with `count_frames` fallback for qsvencc non-determinism is already battle-tested in `test_sdr_legacy_oracle_parity`.
- **Threat model is honest**: T-05-01 correctly identifies arg mis-routing as the primary risk, and the test plan directly addresses it.

## 3. Concerns

### MEDIUM

**C-1: `run_encode`'s `shutil.which` preflight will fire on `enpipe run` even when detect alone would fail first.** If ffmpeg/ffprobe is absent, `run_detect` will throw a `FileNotFoundError` deep in the subprocess (sanctioned deviation per its docstring), while `run_encode` would die() cleanly via its preflight. The user sees an ugly traceback from detect before encode's preflight ever runs. This is *existing* behavior for `enpipe detect`, not a regression, but the UX is jarring in a one-command flow. **Acceptable for this phase** (composition only), but worth a comment or a future v2 item.

**C-2: `run_pipeline` constructs two Namespaces via `argparse.Namespace(**{...})` but some attributes may be `None` (e.g., `qsv_device`, `csv`, `workdir`).** If either stage uses `hasattr()` or `.get()` patterns instead of direct attribute access, missing keys could diverge from the real CLI behavior. However, both stages read `args.attr` directly (verified in the pipeline code), so this is safe as long as the Namespace is shaped identically. The mocked test (Task 2) catches this if an attr is missing. **Low risk but worth a verify-step check** — run the verify assertion and also inspect `args.__dict__` keys in a test.

**C-3: Task 3's two-step side uses `src2` (fresh copy) to avoid `.scenes` path collision, but the detect command on `src2` derives `<src2>.scenes` from the *copied* path, not the original.** If `src2` is in a different tmp directory, the `.scenes` path is different — this is intentional (no collision), but the test asserts `.scenes` byte-identity between the `run` side and the two-step side. Since both sides run the same detect algorithm on identical content, the `.scenes` files *should* be byte-identical. This is sound, but relies on deterministic detect output (which PySceneDetect is, given fixed inputs).

### LOW

**C-4: Task 1 verify assertion only checks parser construction, not that `run_pipeline` actually calls `run_detect` before `run_encode`.** The plan's `<done>` criteria mentions it, but the `<automated>` verify block doesn't. Task 2 covers it via mocks, which is sufficient — the Task 1 verify is just a smoke test for the parser.

**C-5: `--scenes` optional flag (D-04) is listed as Claude's discretion but appears in Task 1's action.** If the implementer adds it, Task 2 should also test it (encode `scenes` == the explicit path, not the derived one). Currently Task 2 only tests the default-derived path. Minor gap.

**C-6: Task 2's "COLLISION" test asserts the parser rejects bare `--jobs`, but argparse doesn't reject unknown flags by default — it would error with "unrecognized arguments: --jobs" only if `--jobs` is not defined on the `run` subparser.** Since `--jobs` won't be defined on `run` (only `--detect-jobs`/`--encode-jobs`), argparse will raise SystemExit with "unrecognized arguments". This is correct behavior but the error message will be generic. The test just needs to assert SystemExit is raised, not the message.

**C-7: No test for `enpipe run` with `--from/--to` partial range.** The plan's Task 2 tests forwarded values but doesn't explicitly test a partial encode (`--from 1 --to 3`). This isn't a gap in routing (the flags are forwarded), but `run_encode`'s `die("пустой диапазон сцен")` path on an empty range is untested in the `run` context. The existing `encode` dispatch tests don't cover this either, so it's consistent with the project's test coverage.

## 4. Suggestions

1. **Task 2 — add a `scenes`-override test case**: If `--scenes` is added, test that `enpipe run --scenes /tmp/custom.scenes` routes `scenes=/tmp/custom.scenes` to the encode Namespace and `output=/tmp/custom.scenes` to the detect Namespace.
2. **Task 3 — add a `.scenes` path collision guard**: Explicitly assert that `src` and `src2` produce *different* `.scenes` paths (by construction of different tmp copies), confirming the collision-avoidance strategy works.
3. **Task 1 — add a `run_pipeline` call-order assert to the verify**: The existing verify only checks parsing. A one-liner `python -c` that patches both stages and asserts order would close C-4. Not required since Task 2 covers it, but useful as a standalone sanity check.
4. **Document the `FileNotFoundError` vs `die()` UX gap** as a v2 candidate (C-1). The `run_pipeline` handler could one day add a lightweight preflight before calling `run_detect`, but that's outside this phase's "zero behavior change" constraint.

## 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Arg mis-routing (wrong attr to wrong stage) | Low | High | Task 2 asserts per-stage Namespace contents exhaustively |
| `.scenes` path derivation differs from `enpipe detect` | Low | Medium | Task 1 uses `str(args.video) + ".scenes"` (identical derivation); Task 2 asserts `output == Path("x.mkv.scenes")` |
| `run` diverges from two-step on hardware (qsvencc non-determinism) | Medium | Medium | Task 3's frame-count gate is the correct fallback; `--no-metrics` is mandatory |
| Bare `--jobs` silently accepted | None | — | Not defined on `run` subparser → argparse rejects it |
| Regression to `enpipe detect`/`encode` | Low | High | Plan explicitly forbids edits to existing subparsers; CI fast tier covers dispatch |

**Overall risk: LOW**. This is a thin composition over verified stages. The primary failure mode (arg mis-routing) is directly addressed by Task 2's mocked routing assertions. Hardware non-determinism is handled correctly by the Phase 4 precedent. The plan is sound and ready to execute.

---

## OpenCode Review

# Cross-AI Plan Review — enpipe Phase 5 (`enpipe run`)

## 1) Summary
Add a thin, sequential `enpipe run <video>` subcommand composing the v1.0-verified `run_detect` → `run_encode` in one invocation, with `--detect-jobs`/`--encode-jobs` resolving the `--jobs` collision and a mocked unit test + hardware-gated parity test. Verified against source: the composition is genuinely byte-identical-by-construction — `run_detect` (detection/pipeline.py:23-51) and `run_encode` (encoding/pipeline.py:71-262) read exactly the Namespace attrs the plan forwards, nothing more.

## 2) Strengths
- **Composition is sound.** I traced every attr read in both `run_detect` and `run_encode`; the plan forwards the complete set for each stage. No missing attr, no extra attr depended on. The "byte-identical by construction" claim holds for the `.mkv` and `.scenes` outputs.
- **`--jobs` split is correct.** Defaults preserved verbatim: detect hardcoded `4` (cli/main.py:38), encode `ENCODE_JOBS` from env (cli/main.py:51, encoding/pipeline.py:39). No bare `--jobs` on `run` → argparse rejects it, testable.
- **Monkeypatch seam accurately described.** test_cli_dispatch.py:69-72 confirms `build_parser()` re-resolves `run_detect`/`run_encode` from module globals at call time, so `run_pipeline` calling them as bare names is interceptable — Task 2's mocks will be non-vacuous.
- **Hardware test reuses the right precedent.** Mirrors `test_sdr_legacy_oracle_parity` (test_hardware_real_media.py:335-399) including the determinism-aware movie.obu byte-compare → frame-count fallback, and correctly mandates `--no-metrics` (qsvencc `--psnr/--ssim` rc=255, OpenCL ICD absent). `addopts` already excludes `hardware` by default (pyproject.toml:39), so the fast tier stays clean automatically.
- **The one real single-process-vs-two-process divergence (`_START`) is already project-documented as non-parity** (logging.py:16-18: "текст лога не входит в parity-поверхность"). So no surprise there.

## 3) Concerns

**MEDIUM — No fail-fast encode preflight before detect.** `run_pipeline` calls `run_detect` first; `run_encode`'s `shutil.which` preflight (encoding/pipeline.py:72-74) only runs after detect completes. If `qsvencc`/`mkvmerge` are absent, `enpipe run` burns the full detect pass (potentially long on spinning disk) before dying. The manual two-step surfaces this at `enpipe encode` before any encode work. D-02 forbids "pipeline logic," but a 4-line `shutil.which` guard in `run_pipeline` is defensible fail-fast UX, not pipeline logic. At minimum, document the consequence in the SUMMARY.

**LOW — `_START` inflates the encode stage's "ГОТОВО за Xс" line.** `_START` is captured at import (logging.py:31); in `enpipe run` the final `ГОТОВО за {now-_START}с` (encoding/pipeline.py:258) reports detect+encode wall time, not encode-only. Per `[ 12.3s]` prefixes this is clearly cosmetic and already excluded from parity (logging.py:16-18), but the `ГОТОВО за` line reads as a *stage-duration* claim and will diverge from standalone `enpipe encode`. Acceptable, but worth a one-line note so a future reader doesn't "fix" the wrong thing.

**LOW — Hardware parity test is mildly tautological.** Both sides invoke the same `run_detect`+`run_encode` with equivalent args, so Task 3 mainly re-guards Namespace-construction drift (already caught by Task 2's mocks) plus the integration fact that `.scenes` survives between stages. Its marginal value over Task 2 is real but modest; the plan slightly oversells it as an independent "real-Arc parity" proof. Frame it as an integration guard.

**LOW — Task 3 `scenes2` derivation underspecified.** Must be `Path(str(src2) + ".scenes")` to match `run_detect`'s exact derivation (detection/pipeline.py:42). Existing tests use `src.with_name(src.name + ".scenes")` (test_hardware_real_media.py:232,348) — equivalent for flat `tmp_path` paths but not identical as expressions; the executor should be explicit and mirror the production derivation.

**LOW — Brittle `>=92 tests` count** (Task 2 done criteria). Prefer "no fewer than current fast-tier count" or drop the literal.

## 4) Suggestions
- Add the fail-fast `shutil.which` preflight in `run_pipeline` before `run_detect` (or explicitly accept the detect-then-die UX in the SUMMARY).
- In Task 3, derive `scenes2` via the same `str(src2)+".scenes"` expression `run_detect` uses; assert `src.scenes` (run side) and `src2.scenes` (two-step side) are byte-identical *and* that `src.scenes` still exists after `run` (proves D-04 "kept").
- Define `run_pipeline` above `build_parser()` — defensive ordering, free cost (avoids any future NameError if `build_parser()` is ever called at import time).
- Consider one unit-test case asserting `--scenes CUSTOM` override routes to *both* `detect_args.output` and `encode_args.scenes` (the override path is currently untested; default path is covered).
- Add a unit-test assertion that the encode Namespace carries NO `input`/`output` attrs and the detect Namespace carries NO `video`/`scenes`/`frm`/`to` attrs — guards against accidental attr cross-contamination between the two hand-built Namespaces.

## 5) Risk
**LOW.** This is the lowest-risk phase the project could run — pure composition over verified stages, zero algorithmic change, `legacy/` and the existing subcommands untouched. The only failure mode is a Namespace-construction bug, which Task 2's mocks catch deterministically and cheaply. No correctness risk to the encoded `.mkv` output. The MEDIUM preflight item is UX, not correctness. Ship-ready after the suggestions above are considered.

---

## Consensus Summary

Both reviewers traced the plan against the actual source and agree: **risk LOW, ship-ready** — the composition is byte-identical-by-construction (`run_detect`/`run_encode` read exactly the Namespace attrs the plan forwards, nothing more), the `--detect-jobs`/`--encode-jobs` split is correct, the monkeypatch seam is non-vacuous, and the hardware parity test mirrors the proven Phase-4 pattern with mandatory `--no-metrics`. Integrate the following (one MEDIUM + cheap LOW hardening).

### Agreed Strengths
- Byte-identical-by-construction: parity is the default, tests confirm rather than discover it.
- `--jobs` collision cleanly split; bare `--jobs` on `run` → argparse rejects it (testable).
- Monkeypatch seam proven by the existing `test_cli_dispatch.py`; Task 2 mocks are non-vacuous.
- Hardware test reuses `test_sdr_legacy_oracle_parity`'s determinism-aware `movie.obu`→frame-count fallback; `hardware` already excluded from the fast tier.
- The one single-process-vs-two-process difference (`_START` timing in the log line) is already project-documented as outside the parity surface.

### Agreed Concerns / integrate
1. **[MEDIUM — both] Fail-fast tool preflight in `run_pipeline`.** `enpipe run` runs the (potentially long, spinning-disk) detect pass BEFORE `run_encode`'s `shutil.which` preflight — so if `qsvencc`/`ffprobe`/`ffmpeg`/`mkvmerge` are missing, it burns the whole detect pass before dying (the manual two-step surfaces this at `enpipe encode`, before any encode work). Add a lightweight `shutil.which` preflight for the encode-stage tools at the START of `run_pipeline` (fail fast with the same clean `die()` message), so `enpipe run` fails before wasting detect. This is fail-fast UX, NOT pipeline logic and NOT a behavior change to run_detect/run_encode — but document in the SUMMARY that it's an additive guard. (If you'd rather not add it, explicitly document the detect-then-die consequence instead.)

### Hardening (LOW — apply, cheap)
- **Task 3 `.scenes` derivation + kept assertions:** derive the two-step side's scenes path via the EXACT production expression `Path(str(src2) + ".scenes")` (matches `run_detect` detection/pipeline.py:42), assert the `run`-side `<video>.scenes` STILL EXISTS after `enpipe run` (proves D-04 "kept"), and assert the run-side vs two-step-side `.scenes` are byte-identical while their paths differ (collision-avoidance holds; PySceneDetect is deterministic on fixed input).
- **Task 2 Namespace cross-contamination guards:** assert the encode Namespace carries NO `input`/`output` attrs and the detect Namespace carries NO `video`/`scenes`/`frm`/`to` attrs (guards accidental attr cross-contamination between the two hand-built Namespaces). Also assert `args.__dict__` keys of each sub-Namespace exactly match what its stage reads.
- **Task 2 argparse rejection:** assert `enpipe run <video> --jobs 4` raises `SystemExit` (bare `--jobs` not defined on `run`).
- **Task 2 `--from/--to` routing:** add a case asserting `--from`/`--to` route to the encode Namespace `frm`/`to` (partial-range forwarding).
- **`--scenes` override (only if implemented, D-04 discretion):** if added, test that `--scenes CUSTOM` routes to BOTH `detect_args.output` and `encode_args.scenes`.
- **Ordering/robustness:** define `run_pipeline` above `build_parser()` (defensive, avoids any future import-time NameError); drop the brittle literal `>=92 tests` done-criterion in favor of "no fewer than the current fast-tier count."
- **Docs:** one-line note that the encode stage's `ГОТОВО за {t}с` log line reports detect+encode wall time under `enpipe run` (cosmetic, `_START` at import; already outside the parity surface) so a future reader doesn't "fix" it.

### Divergent
None material — both converged on the preflight MEDIUM and the same LOW hardening; complementary emphasis only.

### Recommendation
No re-plan. Integrate via `/gsd:plan-phase 5 --reviews`. Priority = #1 (fail-fast preflight), then the Task 3 `.scenes`-kept/derivation asserts and Task 2 cross-contamination/edge-routing guards. All within the thin-wrapper, zero-behavior-change scope.
