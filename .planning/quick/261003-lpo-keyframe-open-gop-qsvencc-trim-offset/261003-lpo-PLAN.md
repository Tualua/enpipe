---
phase: quick-261003-lpo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/enpipe/encoding/keyframes.py
  - src/enpipe/encoding/pipeline.py
  - tests/unit/encoding/test_keyframes.py
  - tests/subprocess/encoding/test_keyframes.py
  - tests/unit/encoding/test_pipeline_wiring.py
  - tests/integration/test_hardware_real_media.py
  - tests/fixtures/media/README.md
  - .planning/debug/qsvencc-open-gop-leading.md
autonomous: true
requirements: [QUICK-261003-lpo]

must_haves:
  truths:
    - "`enpipe encode` on a source where a keyframe used as a chunk seek point is followed (decode order) by packets with pts < pts(keyframe) exits via die() with a clear Russian error naming the keyframe(s) and N, BEFORE audio starts and BEFORE any qsvencc chunk runs (no chunk_*.obu written)"
    - "Closed-GOP sources and the real fixtures (Silo DV 8.1, DV P5, HDR10+ WEB-DL; N=0) are NOT refused — full hardware module stays green"
    - "No trim+N compensation exists anywhere in src/ (seek/trim math in compute_chunk_seek_trim unchanged)"
    - "test_hdr10 source is closed GOP (open-gop=0) and passes the chunk content check again"
    - "An open-GOP synthetic source is asserted to be refused (no xfail); the same mid-GOP scene layout with open-gop=0 passes the content check"
    - "The guard runs on the main thread; no worker calls die()"
  artifacts:
    - path: "src/enpipe/encoding/keyframes.py"
      provides: "count_leading_after_keyframes (pure) + probe_leading_frames (ffprobe I/O, batched read_intervals, full-scan fallback)"
      contains: "def probe_leading_frames"
    - path: "src/enpipe/encoding/pipeline.py"
      provides: "open-GOP guard in run_encode after keyframe_table, before detect_hdr/audio/chunk tasks"
      contains: "probe_leading_frames"
    - path: "tests/integration/test_hardware_real_media.py"
      provides: "test_open_gop_source_refused + test_chunk_content_closed_gop; HDR10 args with open-gop=0"
      contains: "open-gop=0"
  key_links:
    - from: "src/enpipe/encoding/pipeline.py::run_encode"
      to: "keyframes.probe_leading_frames"
      via: "set of kf_before(table, s) over the selected scenes"
      pattern: "probe_leading_frames\\("
    - from: "keyframes.probe_leading_frames"
      to: "ffprobe -read_intervals"
      via: "enpipe.shared.proc.run (single seam, mockable by pytest-subprocess fp)"
      pattern: "read_intervals"
---

<objective>
Hard refusal in enpipe for sources that have leading pictures after a keyframe
used as a chunk seek point (open-GOP: CRA + RASL, pts < pts(K) in decode order).
qsvencc (r4658, r4663 vppsync6, upstream) counts those packets into
`m_trimParam.offset` and shifts `--trim` by −N: frame counts stay correct, the
content is silently wrong (see .planning/debug/HANDOFF-qsvencc-opengop-trim-offset.md).
Loud error instead of silent corruption. NO trim+N compensation (it would invert
into the opposite shift once upstream is fixed).

Output: guard in keyframes.py + pipeline.py, unit/subprocess/wiring tests, fixed
hardware tests (closed-GOP HDR10 source, refusal test instead of xfail), green
full hardware module.
</objective>

<execution_context>
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/workflows/execute-plan.md
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/debug/HANDOFF-qsvencc-opengop-trim-offset.md
@.planning/debug/qsvencc-open-gop-leading.md
@src/enpipe/encoding/keyframes.py
@src/enpipe/encoding/pipeline.py
@tests/subprocess/encoding/test_keyframes.py
@tests/unit/encoding/test_pipeline_wiring.py

<design_decisions>
Detection strategy (chosen: precise per-used-K check, batched; full-scan only as fallback):
- (b) "first few GOPs only" rejected: correctness is non-negotiable, a source can switch GOP structure (concatenated/edited releases).
- (c) "compute N from the ffprobe full scan" alone rejected: the common path is the mkv Cues fast path (no per-packet pts order), and a full scan of a 60 GB file on spinning ZFS is exactly what Cues avoids. It IS used as the fallback (see below), so the slow cost is only paid when the cheap probe cannot locate a keyframe.
- (a) chosen: probe only the DISTINCT keyframes actually used as seek points = { kf_before(table, s) for (s, e) in selected scenes } (includes K=0 when the first scene starts there — qsvencc applies the same offset logic without --seek). ONE ffprobe process with all intervals comma-joined in `-read_intervals`, each `"{t + 0.5/fps:.6f}%+#{LEADING_PROBE_PACKETS}"`. Cost ∝ number of chunks; the region read is the keyframe + a few packets that qsvencc reads anyway for that chunk.
- Interval start = kf_time + half a frame, verified empirically in this session (ffprobe 7.x, x265 open-gop synthetic): mkv and mp4 both seek BACKWARD to the keyframe ≤ target, so start = K+0.5 frame lands exactly on K; start = floor_ms(K) on mkv landed on the PREVIOUS keyframe (wrong); MPEG-TS lands on non-keyframes (unreliable) — hence the fallback.
- LEADING_PROBE_PACKETS = 24 (module constant, Russian comment): HEVC requires all leading pictures of an IRAP to precede its trailing pictures in decode order, so leading packets are immediately after K; x265 bframes ≤ 16 bounds N; 24 covers K + 23 following packets for an exact N in the message. Observed: 320x180 og1 → N=2, 1280x720 og1 → N=4.
- Fallback: if any wanted K is not found as a K-flagged packet in the interval output, log a Russian warning and run a full packet scan (same argv shape as keyframe_table_ffprobe but `packet=pts_time,flags` over the whole file, no read_intervals) and recompute with the same pure parser. If still not found → die (fail closed: "не удалось проверить ведущие кадры после keyframe ...").
- ffprobe non-zero rc → die on the main thread (same style as keyframe_table_ffprobe).

Env override (ENPIPE_ALLOW_OPEN_GOP): NOT added. User did not ask for it; a bypass would re-enable silent corruption. When qsvencc is fixed, the guard should be keyed to a qsvencc revision (alongside QSVENCC_MIN_REV in shared/qsvencc_version.py) in a separate task — note this in the error message comment / SUMMARY only.

test_chunk_content_open_gop (strict xfail) is REPLACED, not kept: without a bypass the content path on an open-GOP source is unreachable through enpipe, so an xfail content test would just fail on the guard (SystemExit) — meaningless. The repro lives in the HANDOFF (§3). Replacement: test_open_gop_source_refused (the guard) + test_chunk_content_closed_gop (same mid-GOP 1280x720 HEVC layout with open-gop=0 → content check passes; keeps coverage of the qsvencc r4663 seek fix on mid-GOP cuts).

Other synthetic sources: test_sdr / test_sdr_legacy_oracle_parity / test_run_parity_vs_two_step use libx264 ultrafast (x264 default is closed GOP and ultrafast has bframes=0) → no change, mention in SUMMARY. Only x265 users (_HDR10_CODEC_ARGS, _make_open_gop_source) need explicit open-gop.
</design_decisions>

<interfaces>
Existing (src/enpipe/encoding/keyframes.py):
- keyframe_table(src: Path, fps: float) -> List[Tuple[int, float]]   # (frame, pts_time), sorted, frame = round(t*fps)
- keyframe_table_ffprobe(src, fps) — argv: ffprobe -v error -select_streams v:0 -show_packets -show_entries packet=flags,pts_time -of csv=p=0 <src>; lines "<pts_time>,<flags>" e.g. "2.002000,K__"
- kf_before(table, frame) -> Tuple[int, float]
- compute_chunk_seek_trim(table, s, e) -> Tuple[str, str]   # MUST stay unchanged
- imports: from enpipe.shared import proc as _proc; from enpipe.shared.logging import die, log
- die(msg) == sys.exit(f"encode_scenes: {msg}") → SystemExit whose str contains msg

pipeline.py run_encode order today: tool preflight → ensure_qsvencc_fixed → ... → read_scenes → probe_fps → `with step("чтение keyframe-таблицы источника"): table = keyframe_table(...)` → detect_hdr → total_expect → audio submit → chunk tasks (compute_chunk_seek_trim per scene).
pipeline imports: `from .keyframes import compute_chunk_seek_trim, keyframe_table`

Empirical ffprobe output (og1.mkv, open-gop x265, `-read_intervals "2.002%+#6"`): 2.002000,K__ / 1.960000,___ / 1.919000,___ / 2.169000,___ ... → K at 2.002 has N=2.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Leading-picture probe in keyframes.py (pure parser + batched ffprobe, full-scan fallback)</name>
  <files>src/enpipe/encoding/keyframes.py, tests/unit/encoding/test_keyframes.py, tests/subprocess/encoding/test_keyframes.py</files>
  <behavior>
    Pure `count_leading_after_keyframes(lines, wanted_frames, fps) -> Dict[int, int]` (lines = csv "<pts_time>,<flags>"):
    - closed GOP (B-frames BEFORE the K packet, e.g. "1.960,___","2.002,K__","2.169,___") → {48: 0}
    - open GOP ("2.002,K__","1.960,___","1.919,___","2.169,___") at fps 24000/1001 → {48: 2}
    - K packet not in wanted_frames resets tracking: its leading packets are NOT counted for any wanted K
    - two concatenated intervals (K1 block then K2 block) → each K gets its own count; a K seen twice (overlapping intervals) → max of the occurrence counts
    - wanted K absent from lines → absent from the result dict (caller decides fallback)
    - "N/A" pts and malformed lines skipped
    I/O `probe_leading_frames(src, fps, keyframes: List[Tuple[int, float]]) -> Dict[int, int]` (subprocess tests via `fp`):
    - one ffprobe call with comma-joined `-read_intervals` "{t+0.5/fps:.6f}%+#24" for every given keyframe, sorted ascending by time, deduplicated
    - all K found → no second call
    - one K missing → second call = full scan (no -read_intervals) and result computed from it
    - still missing after full scan → SystemExit
    - ffprobe rc≠0 → SystemExit
  </behavior>
  <action>
    Write the tests first (RED), then implement (GREEN). In keyframes.py add, with Russian docstrings/comments following the module's "why" style:
    - constant LEADING_PROBE_PACKETS = 24 with a comment explaining the HEVC decode-order rule and the bframes ≤ 16 bound (see design_decisions).
    - count_leading_after_keyframes: walk lines in order; on a K-flagged packet compute frame = round(pts*fps); if frame in wanted_frames start a new occurrence counter for it (store max into result at the end of the occurrence / on each increment), else set "current" to None; on a non-K packet, if current is set and pts < current_pts - 1e-6 → increment. Keep typing-module generics (Dict, List, Set, Tuple) per CLAUDE.md.
    - probe_leading_frames: build the batched argv ["ffprobe","-v","error","-select_streams","v:0","-read_intervals",<joined>,"-show_packets","-show_entries","packet=pts_time,flags","-of","csv=p=0",str(src)] via _proc.run(capture_output=True, text=True); rc≠0 → die(f"ffprobe (ведущие кадры) упал: ..."). If some wanted frames are missing: log(">> ведущие кадры: часть keyframe'ов не найдена выборочным ffprobe — полный скан пакетов (медленно)") and run the full scan (same argv without -read_intervals), recompute; still missing → die listing up to 10 missing frames ("не удалось проверить ведущие кадры после keyframe ... — отказ, чтобы не испортить чанки тихо"). Return {frame: N} for every wanted frame.
    - Do NOT touch keyframe_table / keyframe_table_ffprobe / kf_before / fmt_seek / compute_chunk_seek_trim (seek/trim math is a load-bearing invariant; no trim+N compensation).
    Document in the module docstring (append a paragraph): why the guard exists (qsvencc trim-offset −N on RASL after CRA, link .planning/debug/HANDOFF-qsvencc-opengop-trim-offset.md), why per-used-K batched probe (cost on spinning ZFS), why start = K + half frame (mkv backward seek; floor_ms landed on previous K in mkv; TS unreliable → fallback).
    Subprocess tests: register exact argv with fp (compute the expected -read_intervals string in the test from the same formula/constant imported from the module) — English test prose, match file style.
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && uv run pytest tests/unit/encoding/test_keyframes.py tests/subprocess/encoding/test_keyframes.py -q</automated>
  </verify>
  <done>All behavior cases pass; existing keyframe tests unchanged and green; compute_chunk_seek_trim byte-identical (git diff shows no change inside it).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fail-fast guard in run_encode + wiring tests</name>
  <files>src/enpipe/encoding/pipeline.py, tests/unit/encoding/test_pipeline_wiring.py</files>
  <behavior>
    - New wiring test: probe_leading_frames mocked to return {48: 4} for a scene starting mid-GOP after K=48 → run_encode raises SystemExit; message contains "open-GOP" and "48" and "4"; chunk_command, encode_chunk and encode_audio mocks were never called; no chunk_*.obu in workdir.
    - New wiring test: probe mocked to return all zeros → encode proceeds (existing assertions hold); the probe was called with exactly the distinct seek keyframes { kf_before(_TABLE, s) } for the selected scenes (for _TABLE/_SCENES: [(0, 0.0), (48, 2.0)]).
    - Existing three wiring tests stay green after adding `monkeypatch.setattr(p, "probe_leading_frames", lambda src, fps, kfs: {f: 0 for f, _ in kfs})` (they mock _proc.run globally, so the real probe must not run there).
  </behavior>
  <action>
    In pipeline.py import probe_leading_frames and kf_before from .keyframes. Right after the keyframe-table step and its log line, BEFORE detect_hdr, the audio submit and chunk-task construction (main thread only): compute the sorted distinct list of seek keyframes = kf_before(table, s) for (s, e) in scenes (selected range only); run `with step("проверка ведущих кадров (open-GOP) после keyframe'ов сцен")` → probe_leading_frames(args.video, fps, used_kfs); collect offenders (N > 0). If any: die with a Russian message, e.g. "источник с open-GOP: после keyframe'ов, с которых режутся чанки, идут ведущие кадры (pts раньше keyframe) — кадр K: N ведущих [первые 10 через запятую, «… и ещё M»]. qsvencc сдвигает --trim на −N кадров на таких источниках (offset считает отброшенные RASL): число кадров совпало бы, а содержимое чанков было бы тихо сдвинуто. Кодирование отменено. Перекодируйте источник с закрытым GOP или дождитесь исправления qsvencc." — must contain the literal "open-GOP". Otherwise log(f">> ведущих кадров после {len(used_kfs)} keyframe'ов нет — open-GOP-защита пройдена"). Add a Russian "why" comment above the block: loud refusal instead of silent corruption; no trim+N compensation (would invert after upstream fix); no env bypass by design; guard runs per file in batch mode like ensure_qsvencc_fixed. Do not change anything else in run_encode. Update existing wiring tests with the monkeypatch noted in behavior and add the two new tests.
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && uv run pytest tests/unit tests/subprocess -q</automated>
  </verify>
  <done>Whole non-hardware suite green; refusal happens before any audio/chunk work; probe receives only used seek keyframes.</done>
</task>

<task type="auto">
  <name>Task 3: Hardware tests — closed-GOP HDR10 source, refusal test replaces xfail, full real-media run</name>
  <files>tests/integration/test_hardware_real_media.py, tests/fixtures/media/README.md, .planning/debug/qsvencc-open-gop-leading.md</files>
  <action>
    In tests/integration/test_hardware_real_media.py (English prose):
    - _HDR10_CODEC_ARGS: append ":open-gop=0" to the x265-params string, with a comment: x265 defaults to open-gop=1; enpipe now refuses open-GOP sources (qsvencc trim-offset bug), and test_hdr10 is about the HDR10 path, so its source must be closed GOP.
    - _make_open_gop_source(dst, *, open_gop: bool): add the parameter; x265-params gets ":open-gop=1" or ":open-gop=0" explicitly (never rely on the default). Update its docstring.
    - Delete the strict-xfail test_chunk_content_open_gop and the _OPEN_GOP_LEADING constant. Add test_open_gop_source_refused: build the source with open_gop=True, run detect via _run_cli, precondition (pytest.fail, not assert) that ffprobe packets show ≥1 leading packet after some used seek keyframe (use probe_leading_frames on the used Ks); then call _enpipe_main(["encode", ... same args as the old test incl. --from 0 --to len-1 ...]) inside pytest.raises(SystemExit) and assert "open-GOP" in str(excinfo.value) and that no chunk_*.obu exists in the workdir. Add test_chunk_content_closed_gop: same layout with open_gop=False, same preconditions (≥3 scenes, some scene mid-GOP, included scenes end ≤ last keyframe) and the old body (frame counts + _verify_chunk_first_frames, disc > 0) but with no xfail — it must PASS.
    - Update the module docstring's "Chunk CONTENT check" paragraph: open-GOP sources are now refused by enpipe (guard) instead of being an xfail; point to HANDOFF-qsvencc-opengop-trim-offset.md. Also update _verify_chunk_first_frames' failure hint text if it still says the open-GOP case is "under investigation".
    - tests/fixtures/media/README.md (~line 104): replace the xfail/XPASS note with: open-GOP synthetic is refused by the guard; closed-GOP variant checks content.
    - .planning/debug/qsvencc-open-gop-leading.md: set status to resolved-guarded (frontmatter) and fill Resolution `fix:` with "enpipe: hard refusal (quick 261003-lpo), no trim compensation; upstream handoff pending".
    Then run the FULL real-media hardware module (≈25 min, run in background and poll) with: PATH=/opt/qsvencc-vppsync6/usr/bin:$PATH ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware tests/integration/test_hardware_real_media.py -v (system qsvencc r4658 is refused by the version gate — the PATH prefix is mandatory). Expect all passed except legitimately skipped (missing fixtures); in particular test_dv, test_dv_profile5, test_hdr10plus (real fixtures, N=0) must NOT be refused, both test_hdr10 variants pass the content check, test_open_gop_source_refused and test_chunk_content_closed_gop pass. If a real fixture is refused, STOP and report the offending keyframes/N (do not weaken the guard). Record timings and any METRICS_FAILED retries in the SUMMARY.
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && PATH=/opt/qsvencc-vppsync6/usr/bin:$PATH ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware tests/integration/test_hardware_real_media.py -v</automated>
  </verify>
  <done>Hardware module: 0 failed, 0 xfailed for open-GOP; test_hdr10[no-metrics|metrics], test_open_gop_source_refused, test_chunk_content_closed_gop, real-fixture DV/HDR10+ tests pass; non-hardware suite still green; grep finds no "_OPEN_GOP_LEADING" in tests.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| source file → ffprobe → parser | untrusted media metadata (pts/flags) parsed from ffprobe csv |
| enpipe → qsvencc | encoder behavior on open-GOP input is known-defective (silent −N trim shift) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-lpo-01 | Tampering (output integrity) | run_encode chunk trim on open-GOP | mitigate | probe_leading_frames on every used seek K; die before any encode if N>0 |
| T-lpo-02 | Tampering (false negative) | probe misses a K (seek lands elsewhere, TS) | mitigate | fail-closed: full-scan fallback, then die if K still unverified |
| T-lpo-03 | Denial of Service | malformed ffprobe lines / N/A pts | mitigate | parser skips malformed lines; rc≠0 → die with message |
| T-lpo-04 | Elevation (bypass) | env override re-enabling corruption | accept | no override implemented by design |
</threat_model>

<verification>
- uv run pytest tests/unit tests/subprocess -q → green
- Full hardware module (Task 3 command) → 0 failed
- git diff shows compute_chunk_seek_trim and legacy/ untouched; no "trim" arithmetic with N in src/
</verification>

<success_criteria>
Open-GOP sources (leading packets after a used seek keyframe) are refused loudly before any work; closed-GOP and real fixtures encode as before; test_hdr10 passes the content check on a closed-GOP source; refusal and closed-GOP content are covered by hardware tests; no compensation, no bypass.
</success_criteria>

<output>
Create `.planning/quick/261003-lpo-keyframe-open-gop-qsvencc-trim-offset/261003-lpo-SUMMARY.md` when done
</output>
