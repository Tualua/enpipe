---
phase: quick-261004-mse
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scratch/gate_stress_matrix.py
  - tests/unit/shared/test_ffmpeg_pin_sync.py
autonomous: true
requirements: [UAT-06-GAP-2]

must_haves:
  truths:
    - "`python scratch/gate_stress_matrix.py --backend ffmpeg` no longer raises AttributeError on the backend gate; it calls harness.ffmpeg_av1qsv_available()"
    - "The SKIP message and module docstring of gate_stress_matrix.py describe the av1_qsv capability of the main ffmpeg 9 (n9.0.2), not ffmpeg-8.1"
    - "test_no_stale_ffmpeg_81 also covers scratch/gate_stress_matrix.py and tests/integration/_concurrency_harness.py, without imposing the n9.0.2 literal on them"
  artifacts:
    - path: "scratch/gate_stress_matrix.py"
      provides: "ffmpeg backend gate on ffmpeg_av1qsv_available"
      contains: "harness.ffmpeg_av1qsv_available()"
    - path: "tests/unit/shared/test_ffmpeg_pin_sync.py"
      provides: "stale ffmpeg-8.1 guard over scripts"
      contains: "STALE_SCAN_FILES"
  key_links:
    - from: "scratch/gate_stress_matrix.py"
      to: "tests/integration/_concurrency_harness.py:ffmpeg_av1qsv_available"
      via: "module attribute call through sys.path shim"
      pattern: "harness\\.ffmpeg_av1qsv_available\\(\\)"
---

<objective>
Fix scratch/gate_stress_matrix.py after quick 261004-h8e (commit c912e6b renamed
`ffmpeg81_available()` -> `ffmpeg_av1qsv_available()` in the harness but not in the
script), and extend the stale-ffmpeg-8.1 guard so such a leftover fails CI next time.

Purpose: closes Phase 06 UAT gap, item 2 (.planning/phases/06-concurrency-immunity-spike-image-rebuild-gate/06-HUMAN-UAT.md, Gaps section).
Diagnosis is complete — do NOT re-investigate.
Output: patched script + extended unit guard.
</objective>

<execution_context>
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/workflows/execute-plan.md
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<interfaces>
From tests/integration/_concurrency_harness.py (line 85) — the ONLY valid name now:
  def ffmpeg_av1qsv_available() -> bool:
      True when PATH carries ffmpeg+ffprobe and ffmpeg lists the av1_qsv encoder (capability-based).
The harness contains no "ffmpeg-8.1"/"ffprobe-8.1" literals (only historical "ffmpeg 8.1" with a space at lines ~587/623 — those are fine, leave them).

Current stale spots in scratch/gate_stress_matrix.py (English text — keep English, match surrounding code):
  line 55:  "ffmpeg-8.1 for --backend ffmpeg) it prints a loud SKIP and exits 0."
  line 164: if backend == "ffmpeg" and not harness.ffmpeg81_available():
  line 165:     print("SKIP: ffmpeg-8.1 not on PATH (rebuild the devcontainer image)")

Current tests/unit/shared/test_ffmpeg_pin_sync.py:
  DOCKERFILES = ["Dockerfile", ".devcontainer/Dockerfile"]
  ALL_FILES = DOCKERFILES + [".devcontainer/post-create.sh"]
  test_version_literal_present parametrized over ALL_FILES (requires "n9.0.2")
  test_no_stale_ffmpeg_81 parametrized over ALL_FILES (forbids "ffmpeg-8.1"/"ffprobe-8.1")
  Module docstring is Russian; last sentence mentions checking images and post-create for ffmpeg-8.1 leftovers.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Point gate_stress_matrix.py at ffmpeg_av1qsv_available</name>
  <files>scratch/gate_stress_matrix.py</files>
  <action>
In scratch/gate_stress_matrix.py (keep English, as the rest of the file):
- Line 164: replace `harness.ffmpeg81_available()` with `harness.ffmpeg_av1qsv_available()`.
- Line 165: replace the SKIP text with one describing the real gate, e.g. `"SKIP: ffmpeg/ffprobe without av1_qsv on PATH (expected ffmpeg n9.0.2 from /opt/ffmpeg-9; rebuild the devcontainer image)"`.
- Docstring line ~55: replace "ffmpeg-8.1 for --backend ffmpeg" with wording like "an av1_qsv-capable ffmpeg (n9.0.2) for --backend ffmpeg", keeping the sentence grammatical and the paragraph wrap consistent.
- Grep the file once more for `ffmpeg81`, `ffmpeg-8.1`, `ffprobe-8.1`, `8.1` and fix any other leftover that refers to the old opt-in binary (no other logic changes).
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && ! grep -nE "ffmpeg81|ffmpeg-8\.1|ffprobe-8\.1" scratch/gate_stress_matrix.py && grep -c "harness.ffmpeg_av1qsv_available()" scratch/gate_stress_matrix.py && uv run ruff check src tests scratch/gate_stress_matrix.py && uv run python scratch/gate_stress_matrix.py --help >/dev/null</automated>
  </verify>
  <done>No ffmpeg81/ffmpeg-8.1/ffprobe-8.1 left in the script; gate calls ffmpeg_av1qsv_available(); ruff clean; --help exits 0.</done>
</task>

<task type="auto">
  <name>Task 2: Extend the stale ffmpeg-8.1 guard to scripts</name>
  <files>tests/unit/shared/test_ffmpeg_pin_sync.py</files>
  <action>
In tests/unit/shared/test_ffmpeg_pin_sync.py:
- Leave ALL_FILES and test_version_literal_present unchanged (scripts must NOT be forced to carry the "n9.0.2" literal).
- Add a module constant `STALE_SCAN_FILES = ALL_FILES + ["scratch/gate_stress_matrix.py", "tests/integration/_concurrency_harness.py"]` (list[str] literal, no new imports) with a short Russian inline comment why: scripts touching the ffmpeg backend must not reference the old opt-in binary, but the n9.0.2 literal is not required of them.
- Re-parametrize test_no_stale_ffmpeg_81 over STALE_SCAN_FILES; additionally assert `"ffmpeg81_available" not in text` (the stale harness symbol that caused this gap).
- Update the module docstring's last sentence (Russian) to say the ffmpeg-8.1 leftover check also covers the stress-matrix script and the concurrency harness (the ffmpeg backend users).
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && uv run ruff check src tests scratch/gate_stress_matrix.py && uv run pytest tests/unit -q && uv run pytest tests/unit/shared/test_ffmpeg_pin_sync.py -q -v 2>&1 | grep -c "test_no_stale_ffmpeg_81\[scratch/gate_stress_matrix.py\] PASSED"</automated>
  </verify>
  <done>test_no_stale_ffmpeg_81 runs over 5 files incl. scratch/gate_stress_matrix.py and _concurrency_harness.py, all pass; test_version_literal_present still over the 3 original files; whole tests/unit suite green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| none | Local dev script + unit test; no untrusted input, no new subprocess or dependency |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mse-01 | Tampering | gate_stress_matrix ffmpeg backend gate | mitigate | capability-based gate (av1_qsv in `ffmpeg -encoders`) via existing harness helper; unit guard blocks reintroduction of stale symbol/binary names |
</threat_model>

<verification>
- `uv run ruff check src tests scratch/gate_stress_matrix.py` clean
- `uv run pytest tests/unit -q` green
- `python scratch/gate_stress_matrix.py --help` exits 0

POST-CHECK BY ORCHESTRATOR (not an executor task — long hardware run on A380):
`python scratch/gate_stress_matrix.py --backend ffmpeg` (Bash run_in_background, timeout 7200000, output redirected to a file) must get past the backend gate and produce a verdict; result feeds the 06-HUMAN-UAT.md gap item 2 closure.
</verification>

<success_criteria>
- AttributeError on `--backend ffmpeg` eliminated (gate uses ffmpeg_av1qsv_available)
- No ffmpeg-8.1 wording left in the script
- Stale guard covers the script and harness; would have caught c912e6b's leftover
</success_criteria>

<output>
Create `.planning/quick/261004-mse-gate-stress-matrix-py-ffmpeg-9-ffmpeg81-/261004-mse-SUMMARY.md` when done
</output>
