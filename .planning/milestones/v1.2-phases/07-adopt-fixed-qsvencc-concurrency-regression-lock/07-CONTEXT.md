# Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock - Context

**Gathered:** 2026-10-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the corrupting qsvencc build (8.31 r4604, 2026-09-27 — predates the fix) with one containing the upstream fix rigaya/QSVEnc `45003f1` (issue #308: missing sync of MFX VPP output before encoder submit with VA memory) in BOTH images, fail fast at runtime on any older build, and convert the Phase 6 harness's qsvencc *control* ("must corrupt") into a permanent regression lock ("must be clean") at production + stress JOBS with the HW-decode + P010 + B-pyramid triad asserted. Close the corruption debt (debug sessions + PROJECT.md). Requirements: QSV-01, QSV-02, COR-02.

Not in scope: ffmpeg `av1_qsv` backend (parked, backlog 999.1); switching to an upstream release (later quick task).
</domain>

<decisions>
## Implementation Decisions

### qsvencc build in the images (QSV-01)
- **D-01:** Source of the fixed build = the **upstream nightly .deb** that rigaya linked in issue #308 (comment 5941969693): GitHub Actions run `36932190976` of rigaya/QSVEnc, head_sha `45003f157253392016f29d6201c3b04c5107d9fa`, artifact `QSVEncC_ubuntu2004_deb` → `qsvencc_8.31_amd64.deb`, **sha256 `aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d`**, size 30081716. Verified in this session: `qsvencc --version` → `QSVEncC (x64) 8.31 (r4634) by rigaya, Oct  1 2026 22:01:56`. No in-image source build.
- **D-02:** Pinned commit is **exactly `45003f1`** (r4634). Moving to later master commits only by a deliberate pin bump.
- **D-03:** Artifact expires **2026-10-15** (nightly.link URL dies). Durability: **mirror the .deb as an asset of a GitHub Release in our repo** (`Tualua/enpipe`, e.g. tag `deps-qsvencc-r4634`); both Dockerfiles download from that URL and **verify sha256** (build fails on mismatch). Creating the release/uploading the asset is a user (or `gh`) step — must be done before 2026-10-15; plan must include it as an explicit checkpoint. If the repo is private, reuse the existing optional BuildKit secret `github_token` pattern from the root `Dockerfile`.
- **D-04:** **Both images** switch: `.devcontainer/Dockerfile` AND root `Dockerfile` (slim runtime, published to GHCR). Otherwise the production image would keep the corrupting build (QSV-02 would then just refuse to run in it).
- **D-05:** The new .deb's `Depends:` is already clean (`libc6 (>= 2.31), libva-drm2, libva-x11-2, intel-media-va-driver-non-free | … | va-driver`) — no `intel-opencl-icd`/`libmfx1`. The old dep-strip awk step is no longer required (Claude's discretion: remove or keep as harmless no-op; prefer remove with a Russian WHY-comment).
- **D-06:** Switching to an upstream release (8.32+ containing 45003f1) is **manual, a separate quick task later**. Phase 7 leaves a Russian TODO comment in both Dockerfiles + a backlog/todo entry.
- **D-07:** Post-create self-check **hard-asserts revision ≥ 4634** (same threshold as runtime gate, D-08), mirroring Phase 6's ENV-01 hard-assert style.

### Runtime version gate (QSV-02)
- **D-08:** Criterion = **revision `rNNNN` parsed from `qsvencc --version` first line, must be ≥ 4634**. Revision is the master commit count (monotonic), so future releases pass automatically. Single constant (e.g. `QSVENCC_MIN_REV = 4634`) with a comment citing 45003f1 / #308.
- **D-09:** **Fail closed**: unparseable version output (no `(rNNNN)`, self-built without .git, format change, non-zero exit) is treated as an unfixed build → refuse. Error message (Russian) includes the raw version line, the required minimum revision, and why (silent cross-session frame corruption, 45003f1).
- **D-10:** **No bypass** — no env override, no "JOBS=1 allowed" exception. Hard refusal.
- **D-11:** Gate runs in the preflight of **both `run_encode` and `run_pipeline`** (next to the existing `shutil.which` loop), so `enpipe run` refuses **before** detection. In batch/folder mode it runs once before the loop. Follows `die()` convention on the main thread.

### Upstream VA-API backend
- **D-12:** Add **`--backend qsv`** to the production `chunk_command` argv. Rationale: master's default `--backend auto` silently falls back to VA-API (warning only) if oneVPL finds no QSV device; per upstream docs (`QSVEncC_Options.en.md` §`--backend` @45003f1) VA-API does not support `--avhw` / MFX VPP and ignores `--b-pyramid` with a warning — i.e. a different encoder path than the one the fix and the triad were validated on. Explicit `qsv` turns a missing QSV device into a hard error. **UNVERIFIED:** what r4634 actually does with `--avhw` under VA-API (error vs warning+fallback to SW decode) is NOT documented explicitly and was not tested on hardware — researcher should confirm (e.g. `--backend vaapi --avhw` dry run on the A380). `legacy/` oracle stays frozen (no flag; with QSV available `auto` picks QSV, so output parity is expected). Unit test for `chunk_command` argv must be updated accordingly.

### Concurrency regression lock (COR-02)
- **D-13:** **Invert `test_qsvencc_control_corrupts_same_harness` in place** in `tests/integration/test_concurrency_immunity.py` → e.g. `test_qsvencc_immune_at_production_jobs`: `total_corrupt == 0`, failed starts surfaced (never counted as clean), triad asserted on a clean run. The ffmpeg COR-01 test **stays** (999.1 may return). Shared harness `_concurrency_harness.py`.
- **D-14:** Drive qsvencc through the **production `chunk_command`** (the harness already calls it). Remove deviations from production where they matter (ICQ=24 override, `hdr_flags=[]` vs real `detect_hdr`) unless needed for the content-sweep comparison — Claude's discretion, but the lock must protect the flags enpipe actually ships (including `--backend qsv`).
- **D-15:** Triad assertion for qsvencc: parse qsvencc's own init/param log (HW decode `avhw`, P010/10-bit, GopRefDist/B-pyramid active, QSV backend not VA-API) — exact keys/regex = Claude's discretion; anti-false-clean requirement identical to Phase 6 D-05.
- **D-16:** **Non-vacuity proved once at gate time** (not in the committed test): extract the old **r4604 .deb into a scratch dir** (not in any image), run the **same harness + same production command** (stripping `--backend`, which r4604 does not know) on the same Cold Eyes fixture → must corrupt > 0. Record result in the Phase 7 SUMMARY. If the production command on r4604 does NOT reproduce corruption, stop and report (the lock would be vacuous) — don't silently fall back.
- **D-17:** Intensity as Phase 6: committed pytest **JOBS=3 × IMMUNITY_ITERS=8**; one-time stress matrix **JOBS 3/5/8 × ≥20 iterations**, pass = 0 corrupt frames everywhere (and 0 counted failed starts as clean). Reuse/adapt `scratch/gate_stress_matrix.py`. Evidence (uname -r, iHD version, qsvencc version line, counts) → Phase 7 SUMMARY + timestamped entry in `.planning/debug/scene-chunk-frame-mismatch.md`. Methodology from Phase 6 carries unchanged: full-file every-frame PSNR vs isolated single-session reference, corrupt = PSNR < 30 dB (Phase 6 D-01..D-04); fixture = real `/data` Cold Eyes remux, scenes 923/928/1129 (D-06).

### Non-concurrency regression check on the new build
- **D-18:** On r4634 run the existing **hardware tier** (`tests/integration/test_hardware_real_media.py` — SDR/HDR10 frame counts + HDR metadata survival), **parity vs the `legacy/` oracle** (same binary on both sides), and a **determinism re-run** (byte-identical pre-mux `movie.obu` across two runs). **No** byte-identity requirement vs r4604 output — the fix may legitimately change bits.

### Debt closure (SC#4)
- **D-19:** Close `.planning/debug/scene-chunk-frame-mismatch.md`, `qsvenc-upstream-issue.md`, `HANDOFF-qsvencc-frame-corruption.md` with resolution = upstream 45003f1 (#308) + Phase 7 evidence; update PROJECT.md open-debt entry and STATE.md Deferred Items row. Wording/format = Claude's discretion.

### Claude's Discretion
- Placement of the version-parse helper (e.g. `enpipe/shared/` leaf module vs `encoding/`), its unit tests (fast tier, mocked `subprocess` via the `shared.proc` seam).
- Exact qsvencc triad-log regex.
- Whether to drop the ICQ override in the harness (D-14).
- Exact Release tag name / download URL layout (D-03).
- Removal vs retention of the dep-strip awk (D-05).
</decisions>

<specifics>
## Specific Ideas

- User pointed to rigaya's comment in issue #308 (https://github.com/rigaya/QSVEnc/issues/308#issuecomment-5941969693) with nightly builds: `https://nightly.link/rigaya/QSVEnc/actions/runs/36932190976/QSVEncC_ubuntu2004_deb.zip` (also a fedora41 rpm). rigaya: the workaround forces a sync point of VPP output when VA + VPP + ENC are used together. The user co-authored a parallel patch (#316); rigaya's 45003f1 was merged instead.
- 45003f1 is currently master HEAD and 30 commits ahead of release 8.31 (aa53363); those 30 include the new Linux VA-API backend (`--backend auto|qsv|vaapi`), unified Ubuntu20.04-built .deb with relaxed deps, AYUV/packed-YUV444 fixes, `--icq` auto-disables `--la-depth` (#315).
- Current image: `QSVEncC (x64) 8.31 (r4604) by rigaya, Sep 27 2026` — `--version` shows `8.31` for both broken and fixed builds; only `rNNNN` distinguishes them.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope & requirements
- `.planning/ROADMAP.md` §"Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock" — goal + 4 success criteria
- `.planning/REQUIREMENTS.md` — QSV-01, QSV-02, COR-02
- `.planning/PROJECT.md` — correctness-debt paragraph (to be closed), v1.2 re-scope

### Phase 6 harness & methodology (reused)
- `.planning/phases/06-concurrency-immunity-spike-image-rebuild-gate/06-CONTEXT.md` — D-01..D-13 sweep methodology, triad, fixture, intensity split
- `.planning/phases/06-concurrency-immunity-spike-image-rebuild-gate/06-03-SUMMARY.md` — gate evidence format, stress-matrix results
- `tests/integration/_concurrency_harness.py` — `run_concurrent`, `build_isolated_reference`, `sweep_chunk`, `assert_triad`, `qsvencc_command`
- `tests/integration/test_concurrency_immunity.py` — test to invert
- `scratch/gate_stress_matrix.py` — one-time stress matrix script

### Corruption debug history (to close)
- `.planning/debug/scene-chunk-frame-mismatch.md`
- `.planning/debug/HANDOFF-qsvencc-frame-corruption.md`
- `.planning/debug/qsvenc-upstream-issue.md`

### Code touchpoints
- `src/enpipe/encoding/chunk.py` — `chunk_command` (add `--backend qsv`)
- `src/enpipe/encoding/pipeline.py` — `run_encode` preflight (~line 108)
- `src/enpipe/cli/main.py` — `run_pipeline` preflight (~line 76–89)
- `.devcontainer/Dockerfile` (qsvencc RUN block ~line 73–100), `.devcontainer/post-create.sh` (~line 138)
- `Dockerfile` (root, runtime/GHCR; qsvencc block ~line 99–131), `.github/workflows/docker-publish.yml`
- `tests/integration/test_hardware_real_media.py` — hardware tier for D-18

### Upstream
- rigaya/QSVEnc commit 45003f1, issue #308 (+ comment 5941969693), `QSVEncC_Options.en.md` §`--backend` at 45003f1
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_concurrency_harness.qsvencc_command` already wraps production `chunk_command` (only overrides `--icq` to 24, `hdr_flags=[]`).
- `run_concurrent` / `build_isolated_reference` / `sweep_chunk` / `corrupt_frame_count` — full per-frame PSNR machinery, backend-agnostic.
- `assert_triad` — ffmpeg-log specific; needs a qsvencc-log counterpart.
- Existing `shutil.which` preflight loops in `run_encode` and `run_pipeline` — natural slot for the revision gate.
- Root `Dockerfile` optional BuildKit secret `github_token` (`"$@"` curl pattern) for GitHub downloads.

### Established Patterns
- Hardware-gated tests in `tests/integration/` skip without `/dev/dri/renderD128`/fixture; excluded from default/CI tier.
- Env-tunable module constants (`IMMUNITY_ITERS`), Russian messages/comments, `die()` only on main thread, frozen dataclasses, `typing` generics.
- Post-create hard-assert style from Phase 6 (ENV-01).
- `legacy/` is a frozen oracle — never edited.

### Integration Points
- `chunk_command` argv change touches `tests/unit/encoding/test_chunk.py` and any golden argv assertions.
- Gate must be mockable in fast tests (no qsvencc in CI).
</code_context>

<deferred>
## Deferred Ideas

- Switch both images to a pinned upstream **release** .deb once 8.32+ (containing 45003f1) ships — separate quick task (D-06).
- Permanent in-test negative control with the old r4604 binary — rejected for now (corrupting binary would live in the image); one-time gate run instead (D-16).
- Quality/size comparison r4634 vs r4604 — not required (D-18).
- ffmpeg `av1_qsv` backend — backlog 999.1.
</deferred>

---

*Phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock*
*Context gathered: 2026-10-02*
