# Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE) - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the v1.2 milestone's load-bearing premise — that ffmpeg `av1_qsv` is corruption-free under concurrent `JOBS` with **per-frame content verification** — and rebuild the devcontainer to ffmpeg-8.1, **before any backend code is written**. Requirements: **ENV-01** (ffmpeg-8.1 on PATH with `av1_qsv` encode + `av1_metadata`/`dovi_rpu` BSFs, post-create self-check) and **COR-01** (a non-vacuous concurrent-encode corruption regression test with per-frame content verification).

If immunity does not hold at production JOBS on this exact kernel, the entire migration premise is invalid and the milestone must pivot. Building the ffmpeg backend, seam refactor, seek/trim, and HDR/DV carriage are LATER phases (7–10), explicitly out of scope here.
</domain>

<decisions>
## Implementation Decisions

### Corruption sweep methodology
- **D-01:** The GATE immunity proof uses a **full-file, every-frame** PSNR sweep of each concurrent ffmpeg `av1_qsv` chunk — not hotspot-only. ffmpeg's per-component surface pools could migrate the defect off the known qsvencc hotspot (off=299), so coverage must be total. (Matches roadmap SC#2 "full-file sweep.")
- **D-02:** Metric is **PSNR only**. Corrupt frame ≈ 15.74 dB vs clean ≈ 41.5 dB (often bit-identical → very high) is an unambiguous margin for detecting a whole-frame content swap. VMAF is explicitly excluded — slower, adds the ru-locale CSV-parsing fragility (HANDOFF §9), no added discrimination for a gross swap.
- **D-03:** Each concurrent frame is compared against an **isolated single-session encode** of the same chunk (the reproducer's proven approach). This isolates the concurrency defect specifically and is tolerant of encoder-quality differences; a clean concurrent frame should be near-identical to (or bit-identical with) its isolated reference.
- **D-04:** Corruption threshold: a frame with **PSNR < 30 dB** vs its isolated reference is corrupt. It sits far inside the ~15 dB↔~41 dB gap, so it is a safe, proven midpoint. Any corrupt frame fails the sweep.

### Triad integrity (anti-false-clean, SC#3)
- **D-05:** SC#3 is satisfied by **parsing ffmpeg's `-v verbose` init log** to assert — on the very run that came back clean — that QSV **HW decode** initialized, pixel format is **P010/10-bit**, and **B-frames / `gop-ref-dist`** are active. Missing any leg fails the gate, so a silent SW-decode fallback cannot yield a false "clean."

### COR-01 deliverable & fixture
- **D-06:** Fixture is the **real `/data` Cold Eyes remux** + scenes 923/928/1129 (the handed-off reproducer). Proven to corrupt qsvencc 33–65% per run, which **guarantees SC#4 is non-vacuous**. No synthetic clip for the gate (corruption is content-sensitive; a synthetic clip risks a vacuous qsvencc control).
- **D-07:** The durable artifact is a **hardware-gated pytest in `tests/integration/`**, named-out of the default/CI tier exactly like `test_hardware_real_media.py`. This is what COR-01 ("regression test") calls for.
- **D-08:** Intensity split — the **committed pytest** runs the full-file sweep at **production JOBS=3** with a modest iteration count (fast enough to rerun on the hardware tier). The **heavy stress matrix** (JOBS 5 & 8 × ≥20 iters) runs **once at gate time**, its result recorded, not rerun on every invocation.
- **D-09:** Gate **evidence** (`uname -r`, i915/Xe driver, iHD version, clean-vs-corrupt counts, PSNR signature) is recorded in the **Phase 6 SUMMARY** and appended as a **timestamped entry to `.planning/debug/scene-chunk-frame-mismatch.md`** (handoff DoD §10.4). No separate standalone report doc.

### Immunity confidence bar
- **D-10:** One-time gate JOBS ladder: **3** (production), **5** (mid-stress), **8** (high-stress — a margin beyond any realistic A380 concurrency).
- **D-11:** **≥20 iterations per JOBS level.** Pass bar: **zero corrupt frames** across every iteration at every level, **AND** the qsvencc control corrupts in the same harness (proves the trigger engaged). At the observed 33–65% per-run corruption rate, 20 clean runs drives a non-immune encoder's survival probability to ~10⁻³ or less; matches the ~35-run prior evidence (ffmpeg 35/35 clean).

### Gate-fail pivot
- **D-12:** Pivot boundary (Claude's discretion, **tiered**): corruption at **production JOBS=3 → hard pivot** — migration premise invalid, halt the milestone. **Clean at 3 but corruption at 5/8 → NOT a full pivot**: proceed to Phase 7 but **cap/document the default JOBS** at the highest proven-clean level. This distinguishes "premise invalid" from "concurrency has a ceiling."
- **D-13:** Documented **Plan B** on a production-JOBS hard-fail: qsvencc **`--jobs 1` serialization** (empirically 0% corrupt = isolation, minimal change, 1/3 throughput). Broader workaround evaluation (HANDOFF §7 A/`--avsw` etc.) is deferred to the pivot effort itself, not pre-committed here.

### ENV-01 (carried forward — mostly mechanical)
- ffmpeg-8.1 is **already staged side-by-side** in `.devcontainer/Dockerfile` (`/opt/ffmpeg-8.1`, `ffmpeg-8.1`/`ffprobe-8.1` symlinks; system ffmpeg 6.1.1 untouched). Phase 6 **verifies** `ffmpeg-8.1`/`ffprobe-8.1` on PATH with `av1_qsv` encode + `av1_metadata` + `dovi_rpu` BSFs via the **post-create self-check** (extend `.devcontainer/post-create.sh`).

### Claude's Discretion
- Exact triad-assertion log-parsing (regex/keys) against the ffmpeg 8.1 verbose init dump.
- The "modest" iteration count for the committed production-JOBS test.
- The JOBS-cap value if stress-only corruption occurs (highest proven-clean level).
- Per-frame extraction mechanism (ffmpeg `select`/`-vsync 0` per HANDOFF §4) and the isolated-reference workdir plumbing (writable workdir, never `/data`).
</decisions>

<specifics>
## Specific Ideas

- The whole spike is a **reproduction of the handed-off recipe** (HANDOFF §4), re-run on ffmpeg instead of qsvencc: isolated reference → 3/5/8-way concurrent runs → per-frame PSNR vs reference. The qsvencc control **must** corrupt in the same harness or the gate is vacuous.
- ffmpeg av1_qsv control combo from the debug work: HW `h264_qsv` decode + `vpp_qsv=format=p010le` + `GopRefDist:6 BRefType:pyramid` (prior result: 35/35 clean under 3-way/5-way).
- Correctness is non-negotiable: `count_frames` passing is exactly the false-clean this per-frame content check exists to defeat.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Reproducer & root cause (load-bearing)
- `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` — the reproducer recipe (§4: fixture, scenes 923/928/1129, exact chunk command, PSNR protocol), the corruption triad (§2), the workaround table (§7), and the DoD (§10). **Primary spec for this phase.**
- `.planning/debug/scene-chunk-frame-mismatch.md` — full debug history, root-cause chain, signature (~15.74 dB); the gate evidence entry is appended here (D-09).
- `.planning/debug/qsvenc-upstream-issue.md` — upstream-report draft (context for the kernel-level root cause).

### Requirements & scope
- `.planning/REQUIREMENTS.md` — ENV-01 and COR-01 definitions (and the P6→P10 traceability).
- `.planning/ROADMAP.md` §"Phase 6" — the four Success Criteria this gate must make TRUE.

### Code touched / mirrored
- `src/enpipe/encoding/chunk.py` — `chunk_command` (the exact qsvencc control command) + `count_frames`; pure argv builder.
- `src/enpipe/encoding/pipeline.py` — `JOBS` env default (line ~41) and `ThreadPoolExecutor(max_workers=jobs)` (line ~240), the concurrency origin the harness reproduces.
- `tests/integration/test_hardware_real_media.py` — the `@pytest.mark.hardware` named-out tier pattern the COR-01 test mirrors.
- `scratch/parity_encode.py` — existing isolated-encode hardware-parity harness (pattern for the isolated reference run).

### Environment (ENV-01)
- `.devcontainer/Dockerfile` §"FFmpeg 8.1" (lines ~126–163) — the side-by-side ffmpeg-8.1 staging already in place.
- `.devcontainer/post-create.sh` — the self-check to extend with the ffmpeg-8.1 + BSF assertions.

### Frozen oracle (do not modify)
- `legacy/encode_av1_opus.sh`, `legacy/encode_scenes.py` — single-pass parity oracle (matched the corruption-free control frame-for-frame).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `chunk_command` (`src/enpipe/encoding/chunk.py`): pure qsvencc argv builder — reuse verbatim for the qsvencc control run; the ffmpeg control command is built alongside, not through it (that seam is Phase 7/8).
- `count_frames` + `enpipe.shared.proc.run`: subprocess seam for frame counting / running encodes.
- `scratch/parity_encode.py`: existing isolated-encode-on-real-hardware pattern to base the isolated reference + concurrent-run harness on.
- `tests/integration/test_hardware_real_media.py` + its synthetic-clip lavfi recipe: the hardware-tier marker convention and clip-building idiom (though the gate itself uses the real /data fixture per D-06).

### Established Patterns
- `@pytest.mark.hardware` named-out tier — CI runs `pytest -m "not hardware"`; the COR-01 test joins the hardware tier (D-07).
- Env-var tunables (`JOBS`, `ICQ`, `GOP_LEN`) read at module scope — the harness parameterizes JOBS the same way.
- Worker functions return `(success, error)`, never call `die()` (CLAUDE.md) — applies to any harness worker code.

### Integration Points
- `.devcontainer/post-create.sh` self-check — add ffmpeg-8.1 / BSF assertions here for ENV-01.
- New hardware-gated test file under `tests/integration/` for COR-01.
- The gate-evidence append target is `.planning/debug/scene-chunk-frame-mismatch.md` (D-09).
</code_context>

<deferred>
## Deferred Ideas

- **Broader workaround evaluation** (HANDOFF §7: A `--avsw`, D `--output-depth 8`, E `--gop-ref-dist 1`, or host-side i915→Xe levers) — only relevant if the gate hard-fails; `--jobs 1` is the pre-committed Plan B (D-13), the rest is the pivot effort's problem.
- **Correct re-encode of the corrupted shipped Cold Eyes frames** (39121/61365/73734/110079/110992/136249) — post-fix cleanup, the user's call (HANDOFF §0.4). Not this phase.
- **Cleanup of the failed `Tualua/QSVEnc@{p010-fix,p010-hint-enc,p010-hint-roles}` fork branches** (HANDOFF §9) — housekeeping, out of scope.
- **Defense-in-depth per-frame content-verification on the production `movie.obu` concat** (HANDOFF §7 addendum) — a real hardening idea, but a pipeline feature for a later phase, not the gate.

</deferred>

---

*Phase: 06-concurrency-immunity-spike-image-rebuild-gate*
*Context gathered: 2026-07-23*
