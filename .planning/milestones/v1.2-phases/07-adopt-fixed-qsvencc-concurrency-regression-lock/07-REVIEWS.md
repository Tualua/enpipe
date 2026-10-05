---
phase: 7
reviewers: [opencode, qwen]
reviewed_at: 2026-10-02T09:23:11Z
plans_reviewed: [07-01-PLAN.md, 07-02-PLAN.md, 07-03-PLAN.md, 07-04-PLAN.md, 07-05-PLAN.md]
---

# Cross-AI Plan Review — Phase 7

> Рецензенты: OpenCode и Qwen Code. Claude пропущен (текущий рантайм — независимость ревью);
> локальные серверы (Ollama/LM Studio/llama.cpp) отвечали HTTP 503 — не запущены.

## OpenCode Review

# Cross-AI Plan Review — Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock

## Overall Assessment

This is an exceptionally well-grounded plan set: nearly every load-bearing assumption was verified empirically on real hardware (both binaries extracted and run, harness executed against the real fixture, both positive and negative controls observed). Decision IDs (D-01..D-19) trace cleanly from CONTEXT → research → plans, each plan carries an explicit threat model, and the wave structure correctly front-loads the time-boxed human step (nightly artifact expires 2026-10-15). All four success criteria are covered: SC#1 (07-01+07-03), SC#2 (07-02), SC#3 (07-04+07-05), SC#4 (07-05 Task 3). I verified key grounding claims against the repo: CI runs `pytest -m "not hardware"` over the whole tree, `tests/subprocess/` never invokes `run_encode`/`run_pipeline`, `chunk.py` matches the stated interfaces, and the `releases/latest` greps correctly target only the qsvencc blocks (dovi_tool untouched).

---

## 07-01-PLAN.md — Release mirror (human checkpoint)

### Summary
Correctly scoped as a blocking, human-only first task with Claude doing all verifiable prep work (download, digest, size, revision extraction) before pausing. Anonymous post-upload verification (Task 2) closes the loop without credentials ever entering the devcontainer.

### Strengths
- Failure stops the plan ("do not ask the human to upload an unverified file") — digest verification before the irreversible human action is the right order.
- Task 2's fail-on-404/mismatch with "never fall back to nightly.link for the Dockerfiles" prevents silent degradation.
- Extracted r4634 tree retained at a stable scratch path for 07-05's fallback — good cross-plan plumbing.
- No-token design matches the public-repo reality (verified in research R6).

### Concerns
- **MEDIUM — unrecoverable-artifact path:** if nightly.link is already expired when the plan executes, the .deb is gone unless rigaya re-runs CI. The plan says STOP, but doesn't name the escalation (ask upstream for a new artifact run). Given the 13-day window and today being 2026-10-02, this is a scheduling risk, not a design flaw.
- **LOW — asset mutability:** the Release asset could in principle be replaced/re-uploaded after Task 2. Downstream sha256 pins in the Dockerfiles make this detectable, so this is acceptable — worth one sentence in the summary.

### Suggestions
- Add an explicit escalation note to Task 1's failure path: "if the nightly artifact is gone, request a new upstream Actions run before proceeding."
- Record in 07-01-SUMMARY that downstream pins (07-03 ARGs) re-verify the digest at every build, so post-Task-2 asset tampering cannot propagate silently.

### Risk Assessment: **LOW** — well-ordered, time-boxed, verified values; residual risk is calendar-driven only.

---

## 07-02-PLAN.md — Runtime gate + `--backend qsv`

### Summary
Delivers QSV-02 as a fail-closed leaf module plus the D-12 argv change, with the autouse conftest stub landing **in the same plan** — the single most important sequencing decision, since the gate would otherwise break ~30 fast tests. Test matrix for fail-closed cases (rc≠0, empty, ANSI-prefixed, timeout, OSError) is complete and matches research R3.

### Strengths
- I verified `tests/subprocess/` contains no `run_encode`/`run_pipeline` references — the `tests/unit/conftest.py` stub scope is sufficient; no fallout outside the listed files.
- ANSI-prefixed version line fails closed in the parser but is stripped in the triad function — the correct asymmetric policy, consistently applied across plans.
- Named-import patch targets (`enpipe.encoding.pipeline.ensure_qsvencc_fixed`) with module-object monkeypatch — idiomatic and auto-restoring.
- D-10 enforced by acceptance grep (no `os.environ`), not just by intent.
- The end-to-end "restore the real gate + fp-register r4604" test in `test_cli_run.py` correctly avoids the `_proc.run` Mock collision in `test_pipeline_wiring.py`.
- `cmd.index("--backend") < cmd.index("--avhw")` adjacency-style assertions instead of absolute indices — robust to argv reordering.

### Concerns
- **LOW — brittle grep acceptance:** `grep -c '"qsvencc", "--backend", "qsv", "--avhw"' == 1` breaks on any reformat of `chunk_command`'s list literal (it is currently line-wrapped exactly that way, so it works today, but it's fragile as a standing check).
- **LOW — conftest stub returns `QSVENCC_MIN_REV`:** fine, but creates a second import surface; if the constant ever moves, conftest fails at collection. Acceptable for a test helper.
- **LOW — requirements tag:** `COR-02` on this plan is only the argv prerequisite; the lock itself is 07-04. Harmless but slightly generous tagging.
- **LOW — batch-mode double gate** (once in `run_pipeline`, then per-file in `run_encode` recursion) is documented as intentional (7 ms, stateless per R8) — correct call; just ensure the Russian comment records it so a future "optimize this" doesn't break the per-file protection.

### Suggestions
- Soften the argv-head grep to pair-presence + adjacency (matching the test's philosophy) or accept the brittleness knowingly.
- In the batch-mode comment, state explicitly that the per-file repeat is a feature (each recursion re-guards), not an accident.

### Risk Assessment: **LOW** — highest-risk part (test-suite fallout) is defused by landing the stub in the same plan; fail-closed matrix is thorough.

---

## 07-03-PLAN.md — Dockerfile pinning + post-create assert

### Summary
Switches both images to the sha256-pinned mirror, removes the obsolete dep-strip dance, adds build-time + post-create revision asserts, and correctly identifies that image builds can only be verified on the host (blocking human-verify checkpoint). The `set +x` fix for the token under `set -eux` is a genuine security improvement that closes a latent leak in the pre-existing pattern.

### Strengths
- I verified both Dockerfiles: each has exactly one `rigaya/QSVEnc/releases/latest` occurrence to remove, and the dovi_tool `releases/latest` blocks (which also use jq) are correctly preserved — the verify greps are scoped to avoid false failure.
- Revision check in the RUN (`test "${rev:-0}" -ge 4634`) makes the build itself fail-closed; capture-into-variable avoids both SIGPIPE and pipefail ambiguity.
- Negative verification (bad sha256 must fail the build) proves the digest check isn't decorative.
- Post-create follows ENV-01 convention (flag + `ПРОВАЛЕН` summary, no mid-script exit) — resolved in research Open Question 1, correctly carried into the task text.
- Layer-cache-aware ARG placement (pins before the RUN).

### Concerns
- **MEDIUM — threshold literal duplication:** `4634` now exists in the Python constant, both Dockerfile RUNs, and post-create.sh. The D-06 todo file (Task 2) tells the future bump to update `ARG QSVENCC_URL`/`QSVENCC_SHA256` and "keep the runtime gate threshold," but does **not** enumerate the post-create literal or the two Dockerfile `-ge 4634` checks. A partial bump could produce a state where post-create flags ПРОВАЛЕН while the runtime gate passes (or vice versa) — exactly the kind of drift this phase exists to prevent.
- **LOW — CI dependency on the release asset:** `docker-publish.yml` builds will now anonymously download the asset; rate limiting or repo renames become CI failure modes. Fail-closed, acceptable — but worth noting in the summary.
- **LOW — `apt-get update` position:** if earlier layers cache stale lists, the dependency resolution for `libva-x11-2` on slim-trixie could fail spuriously. The plan's ordering (update immediately before install) is correct; just don't let a later refactor hoist it.

### Suggestions
- Amend the D-06 todo body to enumerate **all four** threshold locations (Python constant, devcontainer Dockerfile RUN, root Dockerfile RUN, post-create.sh) plus the two ARG pairs.
- Add one acceptance line asserting the post-create threshold and Dockerfile thresholds are the same literal (e.g., `grep -c "4634"` counts match across files) so a partial bump is grep-detectable.

### Risk Assessment: **LOW-MEDIUM** — mechanically sound; the residual risk is future maintenance drift, not this phase's execution.

---

## 07-04-PLAN.md — Concurrency regression lock

### Summary
The heart of COR-02, and the best plan of the five: the control test is inverted in place, the harness becomes production-faithful (byte-equal to `chunk_command` by default, with a fast-tier equality test guarding against drift), and the qsvencc triad gets seven positive legs plus fallback markers, ANSI-stripped, and unit-tested against a captured real log. The fail-not-skip discipline on old revisions is exactly right for a correctness lock.

### Strengths
- I verified CI runs `pytest -m "not hardware"` tree-wide — `test_qsvencc_triad_parse.py` in `tests/integration/` without the hardware marker **will** run in CI. Placement is sound.
- The `_require_hardware` split (ffmpeg-8.1 requirement moves into the ffmpeg test) fixes the silent-skip anti-pattern cleanly; I verified the three availability helpers exist as described.
- Two independent 10-bit legs (log + ffprobe ground truth) and the extra VA-memory/VPP legs compensate honestly for the A3 assumption (`avsw:` negative is assumed) — good epistemic hygiene, and it's labeled as such.
- `--expect corrupt` / `--expect clean` verdict semantics on the stress script make the D-16 non-vacuity run mechanically checkable rather than narrative.
- Statistical framing disclosed: committed lock P(false-pass|broken) ≈ 0.4%, stress ≈ 1e-6 — honest about what the lock does and doesn't guarantee.
- Harness fidelity test (default argv == `chunk_command(...)`) directly attacks Pitfall 5 (lock testing a different pipeline than production).

### Concerns
- **MEDIUM — committed-lock false-pass window:** at ~0.5 per-iteration corruption rate on a *still-broken* build, 8 clean iterations pass with ~0.4% probability. This is disclosed and acceptable, but it means **one green lock run is not proof** — the phase correctly treats the stress matrix as the evidence, and 07-05 records the JOBS=5/8 not-permanently-guarded limitation. No action needed; just ensure the limitation note lands as planned.
- **LOW — marker over-matching:** generic `"fallback"` in `_QSVENCC_FALLBACK_MARKERS` could match benign log text. The 07-05 Step C path (inspect → tighten with justification → rerun, "never loosen a positive leg") is the right remedy; consider excluding whole-line context in the regex if it fires benignly.
- **LOW — `strip_backend` failure mode:** `cmd.index("--backend")` raises `ValueError` if a future `chunk_command` drops the flag. Loud, which is fine — but the D-16 runner could give a confusing traceback; a one-line explicit error would help.
- **LOW — `_fixture_hdr_flags` lru_cache:** cached across tests in one session. Fine (same file → same result), but monkeypatch-based fast tests patch the name, not the cache — consistent as designed; just don't ever call `.cache_clear()` assumptions in tests.

### Suggestions
- In `_run_immunity`, also assert the expected total session count (IMMUNITY_ITERS × JOBS) so a silently-shrunk loop can't pass vacuously.
- Have the qsvencc lock's failure message embed `qsvencc_version_line()` (not just the revision int) — cheap and disambiguates custom/self-built binaries in CI logs.

### Risk Assessment: **LOW** — the lock's own failure modes (vacuous pass, silent skip, argv drift) are each individually addressed with a test or a structural guard.

---

## 07-05-PLAN.md — Hardware gate + debt closure

### Summary
Executes the evidence: non-vacuity **first** (a vacuous lock is caught before any clean claim), then the committed lock, the one-time stress matrix, the D-18 non-concurrency checks, and finally the D-19 debt closure with the conscious-limitation note. The run-in-background handling of the ~20–25 min stress matrix respects the 10-min foreground cap. Evidence format matches Phase 6 precedent.

### Strengths
- Correct ordering (D-16 before Step B/C) with a hard STOP and no silent fallback if r4604 doesn't reproduce — this is the anti-vacuity backbone of the whole phase.
- Binary-provenance discipline throughout: `which qsvencc` + version line in every log header (Pitfall 6), side-loaded fixed binary recorded as residual, r4604 verified by digest and never installed.
- Fallback-marker tightening path is bounded (inspect → justify → rerun B/C; positive legs never loosened).
- D-18 determinism check correctly reuses one `detect` + two `encode` runs, isolating encode determinism from detection; byte-comparison of pre-mux `movie.obu` is the right granularity.
- Debt closure includes the r4604-output warning ("re-encode anything produced at JOBS>1") and the JOBS=5/8 not-permanently-guarded limitation — honest bookkeeping.

### Concerns
- **MEDIUM — determinism assumption (D-18) has no contingency:** if r4634's encode is nondeterministic run-to-run (hardware encoders can be, and the fix touches submit/sync ordering), Task 2's byte-identity check fails and stalls the gate with no diagnostic path. The plan should say what a mismatch means: compare frame counts and per-frame PSNR between the two outputs to distinguish "nondeterministic but correct" (report, deliberate decision needed — D-18 as written would fail) from a genuine regression (hard stop).
- **LOW — implicit dependency on 07-02:** `depends_on: [07-01, 07-03, 07-04]` covers it transitively via 07-04, but listing 07-02 explicitly would make the evidence chain legible (Task 1's lock pytest requires both).
- **LOW — Task 3 verify greps** match English `resolved` against Russian-prose docs; fine since the action text mandates those tokens, but slightly brittle if wording drifts (D-19 grants wording discretion — the greps constrain it more than the decision does; minor tension).
- **LOW — /tmp scratch volatility:** the 07-01 retained r4634 extraction may vanish on container restart; the fallback (re-download + re-verify) is already specified. Good.

### Suggestions
- Add the D-18 mismatch diagnostic (frame counts + PSNR between the two runs) to Task 2's action before any stop-and-report.
- Relax Task 3's verify to check the mandated artifacts (45003f1, timestamped section, limitation note + re-run command) rather than a specific English status token, aligning with the granted wording discretion.

### Risk Assessment: **MEDIUM** — not because the plan is weak, but because it is the only plan whose success depends on real-world nondeterminism (D-18) and on ~25 minutes of hardware behavior behaving as observed once in research; both are evidenced but inherently less certain than the code plans.

---

## Cross-Plan Observations

1. **Threshold-literal sprawl (the main systemic risk):** `4634` lives in Python + 2 Dockerfiles + post-create; the parse logic exists in 2 regexes + 2 sed one-liners. This is unavoidable across shell/Python, but the D-06 bump procedure must enumerate every location — currently it doesn't (see 07-03 concern). Suggest one canonical "bump checklist" in the todo file.
2. **Dependency graph:** waves are correct; 07-05 → 07-02 is transitive-only (cosmetic). 07-01's blocking human gate correctly precedes 07-03, and 07-03's host-verify gate correctly precedes 07-05's canonical-image runs, with the side-load fallback documented as a residual — matching Phase 6 practice.
3. **Security posture is coherent end-to-end:** digest pin at build, revision gate at runtime, fail-closed on every anomaly, no bypass by design, no tokens in the container, `set +x` leak fix. One accepted residual worth stating in 07-05's summary: the runtime gate trusts the revision *string*; it does not verify the binary digest at runtime — a swapped binary reporting `(r4634)` would pass. Acceptable for a correctness (not security) boundary, but name it.
4. **Scope discipline:** no scope creep detected. The `set +x` fix and harness fidelity test are small, justified additions; ffmpeg backend stays parked; `legacy/` untouched (multiple greps enforce it).
5. **Coverage of success criteria:** SC#1–4 all mapped with evidence artifacts and named files. Nothing in the roadmap's phase definition is unaddressed.

## Final Verdict

| Plan | Risk | Gate-ready? |
|------|------|-------------|
| 07-01 | LOW | Yes — with escalation note for expired artifact |
| 07-02 | LOW | Yes |
| 07-03 | LOW-MEDIUM | Yes — with D-06 checklist amendment |
| 07-04 | LOW | Yes |
| 07-05 | MEDIUM | Yes — add D-18 mismatch diagnostic first |

**Overall: LOW-MEDIUM risk. Approve to execute** after two amendments: (a) expand the D-06 bump checklist to enumerate all threshold literals, and (b) define the diagnostic path for a D-18 determinism mismatch so a spurious encoder-nondeterminism result can't stall the phase without classification data. The plan set's defining strength — claims verified on real hardware before planning, with negative controls — materially de-risks what is otherwise a hardware-dependent correctness phase.

---

## Qwen Review

# Phase 7 Plan Review

## Overall Assessment

These are exceptionally well-prepared plans. The research phase was thorough (nearly everything verified on real hardware), the decisions are locked with clear rationale, and each plan maps cleanly to specific requirements. The wave decomposition is sound: Plans 01 and 02 can proceed in parallel (no code dependency), Plans 03 and 04 can proceed in parallel (both depend on 01/02 but not each other), and Plan 05 closes the gate after all code is in place. The threat models are unusually detailed for an internal toolchain phase, which is appropriate given that this phase is fundamentally about supply-chain integrity (pinned external binary) and correctness assurance (regression lock against silent data corruption).

---

## Plan 07-01: Mirror qsvencc .deb as Release Asset

### Summary
A two-task plan: (1) human downloads, verifies, and uploads the .deb as a GitHub Release asset before the 2026-10-15 nightly.link expiry; (2) automated anonymous download + sha256 + revision verification. Clean, minimal, and correctly sequenced as the phase's first task since everything downstream depends on a durable mirror URL.

### Strengths
- **Correct prioritization** — the time-boxed human checkpoint is Task 1, not buried after code changes
- **Defense-in-depth verification** — sha256 + size + `--version` revision checked before upload AND after anonymous download
- **Asset naming** (`qsvencc_8.31-r4634_amd64.deb`) avoids confusion with upstream's r4604 file of the same base name
- **Pre-release flag** prevents the deps release from becoming the repo's "latest"
- **Threat model** correctly identifies T-07-03 (credential isolation — no token enters the devcontainer)

### Concerns
- **LOW — Single point of human failure:** If the user doesn't act before 2026-10-15, the entire phase blocks. The plan acknowledges this but has no mitigation beyond the deadline callout. Consider: could Claude pre-download and pre-verify the file into `scratch/` so the user only needs to run the `gh release create` command? (The plan already does this — Task 1 action prepares the file — so the remaining human step is just the upload.)
- **LOW — No rollback if the Release is wrong:** If the upload succeeds but the digest turns out wrong (extremely unlikely given the pre-upload verification), Task 2 would fail, but there's no explicit "delete the bad release and re-upload" instruction. Minor — the user can figure this out.

### Suggestions
- Consider adding a note in the SUMMARY template about the nightly.link fallback: if the Release upload fails for any reason, the nightly.link URL is still live until 2026-10-15, so there's time to retry. This reduces panic if the first upload attempt fails.

### Risk: LOW
The only real risk is calendar pressure, and the plan handles it correctly by making this the first task.

---

## Plan 07-02: Runtime Version Gate + `--backend qsv` + Autouse Stub

### Summary
Three tasks: (1) leaf module `enpipe.shared.qsvencc_version` with fail-closed parser + gate, fully unit-tested via `fp`; (2) wire the gate into both `run_encode` and `run_pipeline` preflights, create `tests/unit/conftest.py` autouse stub, add refusal/ordering tests; (3) add `--backend qsv` to `chunk_command` with adjacency tests. This is the plan with the most code touchpoints and the highest risk of breaking existing tests.

### Strengths
- **Pitfall 1 addressed at the architectural level** — the autouse conftest stub lands in the *same plan* as the gate, not a follow-up. This is critical: without it, ~30 existing tests break. The plan explicitly calls this out and designs the conftest to patch both import sites.
- **Fail-closed design is exhaustive** — unparseable output, non-zero exit, `FileNotFoundError`, `TimeoutExpired`, ANSI-prefixed lines all refuse. The parser's anchored regex (`^QSVEncC\b`) means a leading ANSI escape fails closed, which is the correct default.
- **No bypass by design** — acceptance criteria include `grep -c "os.environ" == 0`, which is a structural guarantee, not just a convention.
- **`--backend qsv` placement** — right after the binary, before `--avhw`, with pair-adjacency tests (not absolute index). This is robust against future argv changes.
- **Gate ordering tests** — explicit test that `enpipe run` refuses *before* `run_detect` is called, mirroring the existing `test_preflight_fails_before_run_detect` pattern.
- **Return value design** — `ensure_qsvencc_fixed() -> int` returns the revision, which callers can ignore. This is future-proof without being over-engineered.

### Concerns
- **MEDIUM — `test_pipeline_wiring.py` interaction:** The research notes that this test replaces `p._proc.run` with a Mock returning `stdout=""`. With the gate wired in, the autouse stub must be active for this test. The plan's conftest patches `ensure_qsvencc_fixed` (not `_proc.run`), so the gate is fully stubbed and the Mock is irrelevant to it. But if someone later removes the autouse stub or adds a test that explicitly restores the real gate *and* also mocks `_proc.run`, they'll get a fail-closed die. The plan's Task 2 tests handle this by using `fp` for the real-gate end-to-end test, which is correct. The risk is maintainability — a future developer might not understand why the conftest exists.
  - **Mitigation:** The conftest's Russian docstring explains Pitfall 1 in detail. This is adequate.
- **LOW — Batch mode re-entry:** The plan acknowledges that `process_one -> run_encode` re-enters the preflight per file (7 ms each). This is acceptable but worth noting: for a 100-file batch, that's 700 ms of redundant `qsvencc --version` calls. Not a real problem (7 ms × 100 = 0.7 s), but a comment in the code explaining "intentionally no caching; 7 ms per call is cheaper than state" would help.
- **LOW — `die()` prefix:** The plan says `die()` prefixes `encode_scenes: `. If the gate fires in `run_pipeline` (before detect), the error message will say `encode_scenes: qsvencc ...` which is slightly misleading (we haven't started encoding). This is cosmetic and inherited from the existing `die()` convention. Not worth changing.

### Suggestions
- **Task 2:** Consider adding a brief Russian comment next to the `ensure_qsvencc_fixed()` call in `run_encode` explaining the lack of caching: `# Намеренно без кэша: 7 мс на файл дешевле состояния; в батч-режиме повтор на каждый файл (D-11, R8)`. The plan's task description already has this rationale; making it a code comment helps future readers.
- **Task 1:** The test for ANSI-prefixed input (`"\x1b[39mQSVEncC (x64) 8.31 (r4634)"` → None) is correct and important. Consider also testing a *trailing* ANSI sequence (e.g., the real format might have `\x1b[0m` at the end of the line) to ensure the regex doesn't require end-of-string anchoring. The current regex `\(r(\d+)\)` doesn't anchor to `$`, so this should pass, but an explicit test would lock the behavior.

### Risk: MEDIUM
This is the highest-risk plan due to the number of touchpoints and the test-suite fallout potential. But the plan is well-designed: the autouse stub is the load-bearing piece, and it lands at the right time. The main execution risk is getting the conftest patch targets right on the first try.

---

## Plan 07-03: Dockerfile Pins + Post-Create + D-06 Todo

### Strengths
- **Both images switch** (D-04) — the plan correctly identifies that leaving the root image on r4604 would make QSV-02 just refuse to run in it.
- **xtrace fix** (T-07-13) — the plan catches a latent information disclosure in the existing `set -eux` + `github_token` pattern and adds `set +x` / `set -x` around the secret read. This is a real security improvement, not just theoretical.
- **Build-time revision check** — `rev=$(qsvencc --version | sed -n '1s/.*(r\([0-9]*\)).*/\1/p'); test "${rev:-0}" -ge 4634` is robust shell: captures to a variable (no SIGPIPE risk), defaults to 0 on parse failure (which fails the `-ge 4634` test), and uses `test` which is POSIX.
- **ARG placement** — `ARG QSVENCC_URL` / `ARG QSVENCC_SHA256` directly before the RUN, so a pin bump only edits ARGs without busting earlier layer caches. Good Docker practice.
- **Dep-strip removal** (D-05) with a Russian WHY-comment — clean, documented, reversible.
- **TODO(D-06)** — both Dockerfiles + a pending todo file track the later switch to an upstream release. The todo file includes the exact check to perform (`compare tag...45003f1 behind_by=0`).
- **Host build checkpoint** — correctly identifies that docker/podman aren't in the devcontainer and makes this a human-verify step with explicit commands.

### Concerns
- **MEDIUM — A1 assumption (root image on trixie):** The plan acknowledges that the root `python:3.12-slim-trixie` image install can't be tested in the devcontainer. The new .deb depends on `libva-x11-2`, which pulls in X11 libraries on a slim image. This *should* work (the .deb is built on Ubuntu 20.04 with glibc 2.31, and trixie has glibc 2.36+), but if it fails, the discoverable-at-first-build mitigation is the only safety net. The plan's build-time revision check means the failure would be loud and immediate, not silent.
  - **Mitigation:** The host build checkpoint (Task 3) catches this before merge.
- **LOW — `apt-get update` + `apt-get install ./deb` ordering:** The plan runs `apt-get update` before `apt-get install /tmp/qsvencc.deb`. This is correct (the .deb's dependencies need the apt cache), but the cleanup `rm -rf /var/lib/apt/lists/*` after must also be present to keep the image slim. The plan includes this.
- **LOW — jq retention:** The plan correctly notes that `jq` stays (used by dovi_tool). Good — removing it would be scope creep.

### Suggestions
- **Task 1:** The plan's Russian comment block explaining *why* the mirror exists is excellent. Consider also including the nightly.link URL in a comment (marked as expired/unused) so a future developer can trace the provenance: `# Первоисточник (умер 2026-10-15): https://nightly.link/rigaya/QSVEnc/actions/runs/36932190976/...`. This is documentation, not a functional dependency.
- **Task 3:** The negative check (`--build-arg QSVENCC_SHA256=0000...`) is a great verification step. Consider also suggesting a negative check for the revision: build with a hypothetical old .deb (if one were available) to confirm the `-ge 4634` check fires. This is impractical for this phase (no old .deb to test with in the Dockerfile context), so just the sha256 negative check is sufficient.

### Risk: LOW
The main risk (A1) is caught by the host build checkpoint. The plan is well-structured and the security improvement (xtrace fix) is a bonus.

---

## Plan 07-04: Concurrency Regression Lock

### Summary
Three tasks: (1) harness upgrades — production-faithful `qsvencc_command`, `assert_qsvencc_triad` with ANSI stripping, `qsvencc_revision()` helper, fast-tier triad tests; (2) invert the control test into `test_qsvencc_immune_at_production_jobs`, split skip fixtures; (3) adapt `scratch/gate_stress_matrix.py` for qsvencc-only stress + D-16 non-vacuity mode.

### Strengths
- **Production fidelity** — `qsvencc_command` now calls `chunk_command` directly with `hdr_flags=_fixture_hdr_flags()` (real `detect_hdr` result) and no ICQ override by default. The lock tests exactly what enpipe ships. The fast-tier equality test (`qsvencc_command(...) == chunk_command(...)`) catches future drift.
- **ANSI stripping** — `re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)` is the correct general form (catches all SGR sequences, not just `m`). The fast-tier test uses a captured log with real `\x1b[39m` / `\x1b[33m` prefixes, which is excellent.
- **Anti-false-clean triad** — 7 positive legs + fallback markers. The dual P010 check (log `^Output AV1(yuv420 10bit)` AND `output_is_10bit(obu)` ffprobe) is defense-in-depth. The `avsw:` negative is acknowledged as assumed (A3) but compensated by the VA-memory + VPP legs.
- **Split skip fixtures** — moving `ffmpeg81_available()` from the module autouse fixture into the ffmpeg test body is the correct fix for Pitfall 4. The qsvencc lock now depends only on hardware + fixture, not on ffmpeg-8.1.
- **`pytest.fail` for old revision** — the lock FAILS (not skips) on a qsvencc older than r4634. This is explicitly tested in the acceptance criteria (`grep -c "pytest.fail" >= 1`).
- **`qsvencc-nobackend` backend name** — clean way to support the D-16 r4604 run without complicating the committed test path.
- **Stress script argparse** — well-designed: `--backend`, `--jobs`, `--iters`, `--expect` (clean/corrupt), `--evidence-dir`. The `--expect corrupt` mode for D-16 is a natural fit.

### Concerns
- **MEDIUM — `_fixture_hdr_flags()` with `lru_cache`:** The plan uses `@functools.lru_cache(maxsize=1)` on `_fixture_hdr_flags()` which calls `detect_hdr(FIXTURE)`. This is a subprocess call (ffprobe) that will fail if the fixture is absent. The plan says the import must stay side-effect free (the function is called lazily), which is correct. But if a fast-tier test imports the harness and the fixture path doesn't exist, the `lru_cache` will cache the result of `detect_hdr` on a missing file. The fast-tier triad test (`test_qsvencc_triad_parse.py`) monkeypatches `_fixture_hdr_flags`, so this shouldn't be hit in practice. But the harness module's import-time safety depends on `detect_hdr` not being called at import time — only when `qsvencc_command` is first called. The plan's design (lazy call inside `qsvencc_command`) is correct, but this is a subtle invariant that could break if someone refactors `qsvencc_command` to call `_fixture_hdr_flags()` at module scope.
  - **Mitigation:** The fast-tier test monkeypatches `_fixture_hdr_flags`, so it never hits the real `detect_hdr`. The hardware test has the fixture. The risk is low but worth a one-line comment in the harness: `_fixture_hdr_flags` is called lazily inside `qsvencc_command`, not at import time.
- **MEDIUM — `assert_qsvencc_triad` fallback marker "fallback":** The marker list includes `"fallback"` as a standalone string. This could match benign log lines like `"Buffer Memory  va, 43 work buffer"` if qsvencc ever prints something like `"fallback buffer allocated"`. The plan's research-verified log doesn't contain such a line, but the marker is broad. The plan says "if the triad fails ONLY on a fallback-marker string, inspect the retained log, decide whether the marker is benign, and if so tighten the marker list" (Plan 07-05 Task 1). This is a reasonable runtime mitigation, but a false positive in the committed lock would be annoying.
  - **Mitigation:** The marker is case-insensitive and applied to the whole log. In practice, qsvencc's log format is structured enough that "fallback" only appears in actual fallback warnings. The Plan 07-05 tightening procedure handles edge cases.
- **LOW — `_run_immunity` helper factoring:** The plan factors the iteration loop into `_run_immunity(backend, tmp_path)`. This is good DRY, but the helper returns a 4-tuple `(failed, total_corrupt, triad_log, triad_obu)`. If the ffmpeg and qsvencc tests need different triad assertions (they do — `assert_triad` vs `assert_qsvencc_triad`), the helper must either take the triad function as a parameter or return the raw log/obu and let the caller assert. The plan says "capture the FIRST session's log text + obu for the triad" in the helper, and the caller does the triad assertion. This is correct.

### Suggestions
- **Task 1:** Add a comment in `_concurrency_harness.py` near `_fixture_hdr_flags`: `# Вызывается лениво внутри qsvencc_command, не при импорте модуля (фикстура может отсутствовать на fast-tier машинах)`. This locks the lazy-invariant.
- **Task 2:** The plan's `_run_immunity` helper should document that it captures the *first clean* session's log for the triad, not the first session period. If the first session fails, the triad log would be None. The plan handles this (`assert triad_log is not None`), but the helper's docstring should be explicit.
- **Task 3:** The stress script's `--expect corrupt` mode should print a clear warning at the top of its output: `WARNING: running with --expect corrupt — this mode uses the OLD qsvencc binary and expects corruption`. This prevents someone from accidentally running it in CI and panicking at the "PASS" verdict on corrupt output.

### Risk: MEDIUM
The harness changes are the most complex part of the phase, but the plan is well-designed with good fast-tier test coverage. The main execution risk is getting the ANSI stripping and triad regex right on the first try — the fast-tier test with a captured real log mitigates this.

---

## Plan 07-05: Hardware Gate Runs + Debt Closure

### Summary
Three tasks: (1) D-16 non-vacuity on r4604, then COR-02 lock + stress matrix on r4634; (2) D-18 non-concurrency regression (hardware tier + legacy parity + determinism); (3) D-19 debt closure (debug docs, PROJECT.md, STATE.md). This is the evidence-gathering and documentation plan.

### Strengths
- **D-16 runs FIRST** — non-vacuity is proven before any "clean" claims. If r4604 doesn't corrupt, the plan stops immediately. This is the correct order.
- **Explicit stop conditions** — "If it reports 0 corrupt, rerun once with `--iters 20`; if still 0, STOP the plan and report per D-16." No silent fallback.
- **Binary provenance tracking** — every run log header records `which qsvencc` + version line. The evidence is reproducible and auditable.
- **Conscious limitation note** — the plan explicitly records that only JOBS=3 is permanently locked; JOBS 5/8 stress was a one-off check. This is honest and important for future maintainers.
- **Debt closure is comprehensive** — three debug docs, PROJECT.md, STATE.md, plus the r4604/JOBS>1 outputs warning. The plan specifies exact sections and wording guidance.
- **Determinism check** (D-18) — byte-identical `movie.obu` across two runs on r4634. This catches any non-determinism introduced by the new build.

### Concerns
- **MEDIUM — Wall time:** The stress matrix (JOBS 3/5/8 × 20 iterations) is estimated at 20-25 minutes. Combined with D-16 (r4604, ~10 min), the lock pytest (~2 min), D-18 hardware tier (~5 min), and determinism check (~5 min), the total wall time is ~45-50 minutes. This is within the plan's scope but requires scheduling attention. The plan says to run the stress matrix in the background and poll — this is correct.
- **LOW — r4604 download for D-16:** The plan downloads the old r4604 .deb from the upstream release asset (not the nightly link), verifies sha256, extracts to `/tmp` scratch. This is well-designed. The only risk is network availability during the gate run.
- **LOW — Legacy oracle parity:** The plan notes that `legacy/` invokes qsvencc without `--backend`, and with a QSV device present, `auto` resolves to `qsv`, so parity is expected. If parity fails, the plan says "STOP and report (do not edit legacy/)." This is correct — `legacy/` is frozen.

### Suggestions
- **Task 1:** Consider recording the *wall time per iteration* in the evidence log, not just the total. This helps detect performance regressions in future qsvencc builds (e.g., if r4634 is significantly slower than r4604 due to the sync fix). The stress script already tracks per-iteration timing; just make sure the SUMMARY includes it.
- **Task 3:** The plan touches many documentation files. Consider creating a single "Phase 7 Resolution" summary paragraph that can be copy-pasted into all three debug docs, ensuring consistency. The plan already has detailed wording guidance, but a canonical paragraph reduces transcription errors.

### Risk: LOW
This is primarily an execution-and-documentation plan. The code is already in place from Plans 02-04. The main risk is hardware availability and wall time, both of which are manageable.

---

## Cross-Plan Concerns

### Dependency Ordering
The wave structure is correct:
- **Wave 1:** Plans 01 (mirror) and 02 (gate + backend flag) are independent. Plan 02 has no dependency on the mirror URL (it only needs the gate module and code changes).
- **Wave 2:** Plans 03 (Dockerfiles) and 04 (harness) both depend on Wave 1 outputs. Plan 03 needs the mirror URL from Plan 01. Plan 04 needs the `--backend qsv` flag from Plan 02 and the `qsvencc_version` module for the revision precondition.
- **Wave 3:** Plan 05 depends on all prior plans.

One subtle point: Plan 04's `qsvencc_command` calls `chunk_command` which now includes `--backend qsv` (from Plan 02). If Plan 04 runs before Plan 02 is merged, the harness would build commands without `--backend qsv`. The plan's `depends_on: [07-02]` correctly prevents this.

### Scope Discipline
All five plans stay tightly within the Phase 7 scope defined by CONTEXT.md. No feature creep. The ffmpeg backend is correctly parked (backlog 999.1). The `legacy/` oracle is never edited. The D-06 follow-up (switch to upstream release) is tracked as a todo, not implemented.

### Security Posture
The threat models across all five plans identify 23 threats (T-07-01 through T-07-23, plus T-07-SC). The most important mitigations:
- **Supply chain:** sha256 pin + human-verified mirror + build-time revision check
- **Downgrade:** runtime gate fail-closed, no bypass
- **Silent fallback:** `--backend qsv` + qsvencc triad assertion
- **Information disclosure:** xtrace fix around `github_token`

The security posture is strong for an internal toolchain. The main residual risk is the external binary itself (qsvencc from upstream), which is mitigated by the sha256 pin and the fact that the upstream project owner co-authored the fix.

### Missing Edge Cases
1. **LOW — `qsvencc --version` output format change:** If rigaya changes the version string format in a future build (e.g., removes the `(rNNNN)` pattern), the gate would refuse. This is the correct behavior (fail closed), but the error message should be clear enough that the user understands it's a format change, not necessarily an old build. The plan's die message includes "the raw first line" which helps with diagnosis.

2. **LOW — Multiple qsvencc on PATH:** If a user has both r4604 and r4634 installed, `shutil.which("qsvencc")` finds the first one. The gate checks that one. If it's r4634, the gate passes, but `chunk_command` also uses `"qsvencc"` (resolved by PATH at runtime), so both the gate and the encode use the same binary. This is consistent. If the user has r4604 first on PATH, the gate refuses. Correct behavior.

3. **LOW — `detect_hdr(FIXTURE)` failure in harness:** If `detect_hdr` raises (e.g., ffprobe fails on the fixture), `_fixture_hdr_flags()` would propagate the exception. The `lru_cache` would not cache the exception (Python's `lru_cache` does not cache exceptions by default). This is correct — the test would fail loudly, not silently use `[]`.

---

## Final Risk Assessment

| Plan | Risk | Justification |
|------|------|---------------|
| 07-01 | LOW | Human step with clear commands; time pressure is the only risk |
| 07-02 | MEDIUM | Most code touchpoints; autouse conftest is load-bearing; test-suite fallout if done wrong |
| 07-03 | LOW | Well-understood Dockerfile changes; A1 assumption caught by host checkpoint |
| 07-04 | MEDIUM | Complex harness changes; ANSI stripping + triad regex must be right; good fast-tier test coverage mitigates |
| 07-05 | LOW | Execution + documentation; code is in place from prior plans |

**Overall phase risk: MEDIUM.** The two medium-risk plans (02 and 04) are well-designed with explicit mitigations for the identified pitfalls. The research phase was unusually thorough (nearly everything verified on real hardware), which significantly reduces implementation risk. The main phase-level risk is the calendar pressure on Plan 01 (2026-10-15 deadline), but this is correctly prioritized as the first task.

The plans are ready for execution.

---

## Consensus Summary

Оба рецензента: план готов к выполнению, общий риск LOW-MEDIUM (OpenCode) / MEDIUM (Qwen).
Блокирующих замечаний нет; есть несколько точечных правок, которые стоит внести до исполнения.

### Agreed Strengths
- Исследование подтверждено на реальном железе (обе ревизии, позитивный и негативный контроль) — это главный де-рискер фазы.
- Autouse-заглушка `tests/unit/conftest.py` в том же плане, что и гейт (07-02) — ключевое решение последовательности.
- Fail-closed гейт без обхода, закреплённый grep-критерием (`os.environ` == 0).
- Чекпоинт загрузки в Release первым, с предварительной проверкой sha256 до необратимого шага.
- 07-04: харнесс байт-в-байт равен `chunk_command` (fast-tier тест на дрейф), FAIL а не skip на старой ревизии, разделение `_require_hardware`.
- 07-05: D-16 (непустота на r4604) строго до любых «чистых» заявлений, с жёстким STOP.
- Исправление утечки токена через xtrace (`set +x`) в 07-03.

### Agreed Concerns
1. **MEDIUM — Широкий маркер `"fallback"` в `_QSVENCC_FALLBACK_MARKERS` (07-04)** — может ложно сработать на безобидной строке лога; путь «сузить с обоснованием» в 07-05 есть, но лучше сузить заранее (контекст строки/точная фраза).
2. **LOW — Комментарий про намеренное повторение гейта в батч-режиме (07-02)** — оба просят явный русский комментарий у вызова `ensure_qsvencc_fixed()`: повтор на каждый файл — фича (7 мс), а не случайность; защищает от будущей «оптимизации».
3. **LOW — Календарный риск 07-01 (до 2026-10-15)** — оба отмечают; OpenCode предлагает явный путь эскалации при протухшем артефакте (попросить у апстрима новый прогон Actions), Qwen — заметку, что nightly.link жив до дедлайна и можно повторить загрузку.

### Divergent Views
- **Самый рискованный план:** OpenCode — 07-05 (MEDIUM: зависимость от детерминизма D-18 и ~25 мин поведения железа); Qwen — 07-02 и 07-04 (MEDIUM: число точек касания и сложность харнесса), а 07-05 считает LOW. Стоит учесть оба взгляда.
- **Только OpenCode (стоит внести):**
  - **MEDIUM — Порог `4634` размножен** (Python-константа, 2 Dockerfile RUN, post-create.sh); todo D-06 не перечисляет все места → риск частичного бампа и рассинхрона. Перечислить все 4 места + 2 пары ARG в todo и добавить grep-критерий согласованности.
  - **MEDIUM — Нет диагностики при провале детерминизма D-18 (07-05 Task 2):** при несовпадении `movie.obu` сравнить число кадров и покадровый PSNR, чтобы отличить «недетерминированно, но корректно» от регрессии.
  - LOW — явно добавить 07-02 в `depends_on` 07-05 (сейчас транзитивно).
  - LOW — в `_run_immunity` проверять ожидаемое число сессий (ITERS × JOBS); в сообщении об отказе лока выводить полную строку версии.
  - LOW — назвать остаточный риск: рантайм-гейт доверяет строке ревизии, а не дайджесту бинаря.
  - LOW — grep-критерий `'"qsvencc", "--backend", "qsv", "--avhw"'` хрупок к переформатированию.
- **Только Qwen:**
  - Тест на завершающую ANSI-последовательность в строке версии; комментарий о ленивом вызове `_fixture_hdr_flags`; предупреждение в выводе `--expect corrupt`; провенанс nightly.link в комментарии Dockerfile; время на итерацию в evidence.
