# Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock - Research

**Researched:** 2026-10-02
**Domain:** pinned external-binary adoption (qsvencc .deb in two Docker images), runtime version gate, hardware-gated concurrency regression test
**Confidence:** HIGH (almost everything below was verified by running it on this box: Arc A380, iHD 26.3.2, kernel 6.19.14-200.fc43)

<user_constraints>
## User Constraints (from 07-CONTEXT.md)

### Locked Decisions
- **D-01:** Source of the fixed build = the upstream nightly .deb that rigaya linked in issue #308 (comment 5941969693): GitHub Actions run `36932190976` of rigaya/QSVEnc, head_sha `45003f157253392016f29d6201c3b04c5107d9fa`, artifact `QSVEncC_ubuntu2004_deb` -> `qsvencc_8.31_amd64.deb`, sha256 `aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d`, size 30081716. `qsvencc --version` -> `QSVEncC (x64) 8.31 (r4634) by rigaya, Oct  1 2026 22:01:56`. No in-image source build.
- **D-02:** Pinned commit is exactly `45003f1` (r4634). Moving to later master commits only by a deliberate pin bump.
- **D-03:** Artifact expires 2026-10-15 (nightly.link URL dies). Mirror the .deb as an asset of a GitHub Release in our repo (`Tualua/enpipe`, e.g. tag `deps-qsvencc-r4634`); both Dockerfiles download from that URL and verify sha256 (build fails on mismatch). Creating the release/uploading the asset is a user (or `gh`) step - must be done before 2026-10-15; plan must include it as an explicit checkpoint. If the repo is private, reuse the optional BuildKit secret `github_token` pattern from the root `Dockerfile`.
- **D-04:** Both images switch: `.devcontainer/Dockerfile` AND root `Dockerfile`.
- **D-05:** New .deb's `Depends:` is already clean - the old dep-strip awk is no longer required (Claude's discretion: prefer remove with a Russian WHY-comment).
- **D-06:** Switching to an upstream release (8.32+ containing 45003f1) is manual, a separate quick task later. Phase 7 leaves a Russian TODO comment in both Dockerfiles + a backlog/todo entry.
- **D-07:** Post-create self-check hard-asserts revision >= 4634 (same threshold as runtime gate), mirroring Phase 6's ENV-01 hard-assert style.
- **D-08:** Criterion = revision `rNNNN` parsed from `qsvencc --version` first line, must be >= 4634. Single constant (e.g. `QSVENCC_MIN_REV = 4634`) with a comment citing 45003f1 / #308.
- **D-09:** Fail closed: unparseable version output (no `(rNNNN)`, self-built without .git, format change, non-zero exit) = unfixed build -> refuse. Russian error includes the raw version line, the required minimum revision, and why.
- **D-10:** No bypass - no env override, no "JOBS=1 allowed" exception.
- **D-11:** Gate runs in the preflight of both `run_encode` and `run_pipeline` (next to the existing `shutil.which` loop), so `enpipe run` refuses before detection. In batch/folder mode it runs once before the loop. `die()` convention on the main thread.
- **D-12:** Add `--backend qsv` to the production `chunk_command` argv. `legacy/` oracle stays frozen. Unit test for `chunk_command` argv must be updated. (UNVERIFIED part of the decision resolved below - see "Research Findings R1".)
- **D-13:** Invert `test_qsvencc_control_corrupts_same_harness` in place in `tests/integration/test_concurrency_immunity.py` -> e.g. `test_qsvencc_immune_at_production_jobs`: `total_corrupt == 0`, failed starts surfaced (never counted as clean), triad asserted on a clean run. The ffmpeg COR-01 test stays.
- **D-14:** Drive qsvencc through the production `chunk_command`. Remove deviations from production where they matter (ICQ=24 override, `hdr_flags=[]`) unless needed - Claude's discretion, but the lock must protect the flags enpipe actually ships (including `--backend qsv`).
- **D-15:** Triad assertion for qsvencc: parse qsvencc's own init/param log (HW decode `avhw`, P010/10-bit, GopRefDist/B-pyramid active, QSV backend not VA-API) - exact regex = Claude's discretion; anti-false-clean requirement identical to Phase 6 D-05.
- **D-16:** Non-vacuity proved once at gate time (not in the committed test): extract the old r4604 .deb into a scratch dir (not in any image), run the same harness + same production command (stripping `--backend`) on the same Cold Eyes fixture -> must corrupt > 0. Record in Phase 7 SUMMARY. If it does NOT reproduce, stop and report.
- **D-17:** Committed pytest JOBS=3 x IMMUNITY_ITERS=8; one-time stress matrix JOBS 3/5/8 x >=20 iterations, pass = 0 corrupt everywhere (and 0 counted failed starts as clean). Reuse/adapt `scratch/gate_stress_matrix.py`. Evidence (uname -r, iHD version, qsvencc version line, counts) -> Phase 7 SUMMARY + timestamped entry in `.planning/debug/scene-chunk-frame-mismatch.md`. Phase 6 methodology unchanged (full-file every-frame PSNR vs isolated single-session reference, corrupt = PSNR < 30 dB; fixture = real `/data` Cold Eyes remux, scenes 923/928/1129).
- **D-18:** On r4634 run the existing hardware tier (`tests/integration/test_hardware_real_media.py`), parity vs the `legacy/` oracle, and a determinism re-run (byte-identical pre-mux `movie.obu` across two runs). No byte-identity vs r4604.
- **D-19:** Close `scene-chunk-frame-mismatch.md`, `qsvenc-upstream-issue.md`, `HANDOFF-qsvencc-frame-corruption.md` with resolution = upstream 45003f1 (#308) + Phase 7 evidence; update PROJECT.md open-debt entry and STATE.md Deferred Items row.

### Claude's Discretion
- Placement of the version-parse helper (e.g. `enpipe/shared/` leaf module vs `encoding/`), its unit tests (fast tier, mocked `subprocess` via the `shared.proc` seam).
- Exact qsvencc triad-log regex.
- Whether to drop the ICQ override in the harness (D-14).
- Exact Release tag name / download URL layout (D-03).
- Removal vs retention of the dep-strip awk (D-05).

### Deferred Ideas (OUT OF SCOPE)
- Switch both images to a pinned upstream release .deb once 8.32+ ships - separate quick task (D-06).
- Permanent in-test negative control with the old r4604 binary - rejected (one-time gate run instead, D-16).
- Quality/size comparison r4634 vs r4604.
- ffmpeg `av1_qsv` backend - backlog 999.1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QSV-01 | Devcontainer installs qsvencc containing `45003f1`; post-create self-check asserts revision | R2 (.deb verified, deps clean, runs), R6 (Dockerfile pattern), R7 (post-create ENV-01 flag style) |
| QSV-02 | `enpipe encode`/`run` fail fast on qsvencc older than the fix | R3 (version output format verified), R8 (gate design), Pitfall 1 (existing tests break) |
| COR-02 | Hardware-gated regression test: 0 corrupt frames at production+stress JOBS, triad asserted | R4 (harness verified on r4634: 12 iterations JOBS=3 = 0 corrupt), R5 (log keys for triad), R9 (non-vacuity r4604 reproduces) |
</phase_requirements>

## Summary

All the load-bearing assumptions of CONTEXT.md hold on this machine. The nightly .deb downloads from nightly.link, the sha256 matches `aa10f196...743d` exactly, `Depends:` is clean (`libc6(>=2.31), libva-drm2, libva-x11-2, intel-media-va-driver-non-free | intel-media-va-driver | i965-va-driver | va-driver`), the binary links only libva/libdrm/libc/libm (no `not found` libs), and it runs from a scratch extraction (`dpkg-deb -x`) without touching the installed r4604. No upstream release contains the fix yet: latest release is 8.31 (2026-09-27, r4604); 45003f1 is master HEAD and exactly 30 commits ahead of tag 8.31 (GitHub compare API). So D-01 (nightly mirror) is the only viable path today; the pin-to-release switch stays a later quick task (D-06).

I ran the Phase 6 harness (unchanged, `qsvencc_command` + `--backend qsv` injected) against the new binary on the real Cold Eyes fixture: 12 iterations at JOBS=3 = 36 concurrent sessions, 0 corrupt frames, 0 failed starts, ~12 s/iteration. The same harness with the installed r4604: 2 corrupt frames in 4 iterations (non-vacuity reproduces). The existing hardware tier (`test_hardware_real_media.py`) passes on r4634 (4 passed, 2 skipped on missing HDR10+/DV fixtures, 76 s), including the legacy-oracle parity test.

The UNVERIFIED point in D-12 is now resolved: on r4634 `--backend vaapi --avhw` is a hard error (`--avhw is not supported with --backend vaapi.`, rc=253), and r4634 prints a `Backend        qsv` header line which the triad assertion can use. The main planning hazards are (a) the new runtime gate will break ~30 existing fast tests that mock `shutil.which` but not `qsvencc --version`, (b) the release-asset mirroring is a time-boxed human step (before 2026-10-15) that must precede any image rebuild, and (c) qsvencc stderr contains ANSI color escapes even when redirected to a file, which breaks naive regexes.

**Primary recommendation:** Land things in this order - (1) human checkpoint: upload the verified .deb as a Release asset; (2) leaf gate module + `--backend qsv` + autouse test stub; (3) Dockerfiles + post-create; (4) harness/test inversion + qsvencc triad; (5) hardware gate runs (D-16/D-17/D-18) and debt closure.

## Architectural Responsibility Map

This is a CLI/toolchain, not a tiered web app; "tiers" here = layers of the toolchain.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| qsvencc binary provisioning (pin + sha256) | Image build (`.devcontainer/Dockerfile`, root `Dockerfile`) | Release asset hosting (GitHub Release) | Binary must exist and be pinned before any code runs |
| Revision self-check at container creation | `.devcontainer/post-create.sh` | - | Dev-only early signal (ENV-01 style); not a security boundary |
| Runtime refusal on old build | Python preflight (`run_encode`, `run_pipeline`) via a leaf module in `enpipe/shared/` | `shared.proc` seam for subprocess | The only enforcement that protects users of the GHCR image and downgrades |
| Backend selection (`--backend qsv`) | `enpipe/encoding/chunk.py::chunk_command` (pure argv builder) | - | Single production argv source; harness reuses it |
| Concurrency regression lock | `tests/integration/` hardware tier | `_concurrency_harness.py` | Needs real Arc + real fixture; excluded from default/CI tier |
| One-time evidence (non-vacuity, stress matrix) | `scratch/` scripts run at gate time | `.planning/` SUMMARY + debug log | Not committed as tests (D-16/D-17) |

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| qsvencc (Rigaya QSVEnc) | 8.31 **r4634** (commit 45003f1), .deb built on Ubuntu 20.04, gcc 9.4.0 | AV1 hardware encoder | Locked by D-01/D-02; verified [VERIFIED: ran `--version`, sha256 match] |
| Python stdlib `re` + `subprocess` (via `enpipe.shared.proc`) | 3.12 | Version parse + gate | No new dependency; project's established seam |
| pytest + pytest-subprocess (`fp`) | already in `uv.lock` | Fast-tier tests for the gate | Existing project convention (`tests/subprocess/`) |
| GitHub Release asset (Tualua/enpipe) | tag e.g. `deps-qsvencc-r4634` | Durable mirror of the nightly .deb | D-03 |

### Supporting
| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `sha256sum -c` in Dockerfile RUN | Pin verification | Both images, build must fail on mismatch |
| `scratch/gate_stress_matrix.py` | One-time stress matrix | Adapt to qsvencc-only (BACKENDS = ("qsvencc",)), remove the ffmpeg-8.1 requirement, add `--backend` handling |
| ffmpeg system `ffmpeg`/`ffprobe` (6.1.1 in devcontainer) | PSNR sweep + `count_frames` | Already what `sweep_chunk` uses; ffmpeg-8.1 is NOT needed for the qsvencc lock |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Release-asset mirror | Keep nightly.link URL in Dockerfile | Dies 2026-10-15 -> unbuildable images. Rejected by D-03 |
| Release-asset mirror | Source build in image | Rejected by D-01 (slow, needs toolchain) |
| Parse `--version` | `qsvencc --check-features`/hash of binary | Revision parse is cheap (7 ms, no GPU) and decided by D-08 |

**Installation:** no pip/npm packages are added. The only new external artifact is the .deb.

**Version verification** [VERIFIED: GitHub REST API, 2026-10-02]:
- Latest rigaya/QSVEnc release = `8.31` published 2026-09-27T04:08:58Z (r4604); previous `8.30` 2026-09-11.
- master HEAD = `45003f15` committed 2026-10-01T14:22:01Z ("VAのMFX VPP出力をエンコード前に同期し…( #308 )").
- compare `8.31...45003f1`: `ahead_by = 30`. No release or tag contains the fix -> source = nightly artifact (D-01 stands).
- Old r4604 .deb (for D-16) is a stable release asset: `https://github.com/rigaya/QSVEnc/releases/download/8.31/qsvencc_8.31_amd64.deb`, sha256 `15aa733f439e12bc647cd690959a973ee476951a05bd09b9577cc52e92f2f61f`, `dpkg-deb -x` + `--version` -> `(r4604) ... Sep 27 2026 03:54:16`. Its Depends still has `intel-opencl-icd, libmfx1, libigfxcmrt7` - irrelevant for `dpkg-deb -x` into scratch (no install).

## Package Legitimacy Audit

No pip/npm/cargo packages are installed or recommended by this phase. The single new external artifact is the rigaya/QSVEnc .deb from the upstream project's own CI (author = project owner's collaborator rigaya; user co-authored the fix), pinned by sha256 and mirrored in our own repo. slopcheck is not applicable.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| qsvencc_8.31_amd64.deb (r4634 nightly) | GitHub Actions artifact -> our GitHub Release | upstream since 2012+ | n/a | github.com/rigaya/QSVEnc | n/a (not a registry package) | Approved, sha256-pinned |

**Packages removed:** none. **Packages flagged [SUS]:** none.

## Architecture Patterns

### Data flow (what changes)

```
image build                      container start               every `enpipe encode|run`
-----------                      ---------------               -------------------------
GitHub Release asset  --curl-->  post-create.sh                 which-loop (qsvencc/ffprobe/ffmpeg/mkvmerge)
  + sha256sum -c                   qsvencc --version             -> ensure_qsvencc_fixed()   [NEW]
  + apt-get install ./deb          -> rev >= 4634? hard-assert        qsvencc --version -> parse (rNNNN)
  (both Dockerfiles)               (QSV01_OK flag + summary)          rev < 4634 / unparseable / rc!=0 / OSError -> die(RU)
                                                                 -> (run only) detect stage
                                                                 -> encode: chunk_command(... "--backend","qsv" ...)
                                                                      -> qsvencc per scene, JOBS threads

hardware tier (manual / self-hosted)
  precondition: ensure revision >= MIN (fail, not skip)
  build_isolated_reference("qsvencc")  -> N x run_concurrent(JOBS) -> sweep_chunk (PSNR<30dB = corrupt)
  -> total_corrupt == 0, failed == [] -> assert_qsvencc_triad(log) on one clean session
```

### Recommended file touch list
```
src/enpipe/shared/qsvencc_version.py   # NEW leaf: QSVENCC_MIN_REV, parse_revision(), ensure_qsvencc_fixed()
src/enpipe/encoding/chunk.py           # add "--backend","qsv" to chunk_command
src/enpipe/encoding/pipeline.py        # import + call gate after the which-loop
src/enpipe/cli/main.py                 # import + call gate after the which-loop (before detect)
tests/unit/conftest.py                 # NEW autouse stub of the gate in both namespaces (see Pitfall 1)
tests/unit/shared/test_qsvencc_version.py   # NEW: parser + gate (fp fixture)
tests/unit/encoding/test_chunk.py      # assert --backend qsv present, adjacent value "qsv"
tests/unit/encoding/ + tests/unit/cli/ # tests that run_encode/run_pipeline die on old build, before detect
tests/integration/_concurrency_harness.py   # qsvencc triad assert, production-faithful command
tests/integration/test_concurrency_immunity.py  # invert control test
scratch/gate_stress_matrix.py          # qsvencc-only stress + (copy) non-vacuity runner for r4604
.devcontainer/Dockerfile, Dockerfile, .devcontainer/post-create.sh
.planning/debug/*.md (3), PROJECT.md, STATE.md  # debt closure (D-19)
```
Placement decision: `enpipe/shared/` leaf module (alongside `proc.py`, `logging.py`): it is used by both `cli/main.py` and `encoding/pipeline.py`; putting it in `encoding/` would make `cli.main` import from a sibling just for a version check. It may import `enpipe.shared.proc` and `enpipe.shared.logging.die`.

### Pattern 1: Version gate (fail closed)
**What:** pure parser + one function that runs `qsvencc --version` through the `_proc.run` seam.
**Verified facts for the parser** [VERIFIED: ran both binaries]:
- First stdout line, no ANSI, exact bytes: `QSVEncC (x64) 8.31 (r4604) by rigaya, Sep 27 2026 03:54:16 (gcc 9.4.0/Linux)` / `... (r4634) by rigaya, Oct  1 2026 22:01:56 (gcc 9.4.0/Linux)` (note double space before `1` in the date).
- Goes to **stdout**, rc=0, ~7 ms, needs no GPU/`/dev/dri` (also works with `LIBVA_DRIVER_NAME=bogus`) -> safe in the preflight and in `docker build`/post-create without devices.
- `8.31` is identical for broken and fixed builds; only `rNNNN` differs.
```python
# src/enpipe/shared/qsvencc_version.py  (Russian prose in the real file)
_REV_RE = re.compile(r"^QSVEncC\b[^\n]*?\(r(\d+)\)")   # first line only
QSVENCC_MIN_REV = 4634   # rigaya/QSVEnc 45003f1 (issue #308): sync MFX VPP output before encode

def parse_revision(text: str) -> Optional[int]:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = _REV_RE.match(first.strip())
    return int(m.group(1)) if m else None

def ensure_qsvencc_fixed() -> None:          # main thread only; uses die()
    try:
        cp = _proc.run(["qsvencc", "--version"], capture_output=True, text=True, timeout=10)
        out, rc = (cp.stdout or "") + (cp.stderr or ""), cp.returncode
    except (OSError, subprocess.TimeoutExpired) as ex:
        out, rc = f"{type(ex).__name__}: {ex}", -1
    rev = parse_revision(out) if rc == 0 else None
    if rev is None or rev < QSVENCC_MIN_REV:
        die("qsvencc ... (RU message: raw first line, required >= r4634, why: silent cross-session frame corruption, 45003f1 / #308)")
```
`die()` prefixes `encode_scenes: ` (existing behavior); keep.

### Pattern 2: harness triad for qsvencc
Real r4634 init log (stderr, ANSI stripped) for the production command [VERIFIED]:
```
Backend        qsv
Media SDK      QuickSyncVideo API v2.17, FF, 1st(d) GPU
Buffer Memory  va, 43 work buffer
Input Info     avqsv: H.264/AVC, 1920x1080, 24/1 fps
VPP            ColorFmtConvertion: nv12 -> p010
Output         AV1(yuv420 10bit) main @ Level 4
GopRefDist     6, B-pyramid: on
Max GOP Length 300 frames
```
Suggested regexes (apply to ANSI-stripped log, `re.M`):
- HW decode: `^Input Info\s+avqsv:` (software decode would print `avsw:`) [avqsv leg verified; the `avsw:` negative is ASSUMED from upstream naming]
- P010/10-bit: `^Output\s+AV1\(yuv420 10bit\)` plus keep the existing `output_is_10bit(obu)` ffprobe check (ground truth) - two independent legs
- Pyramid: `^GopRefDist\s+6,\s*B-pyramid:\s*on`
- Backend: `^Backend\s+qsv\b` (line exists only in r4634-era builds; absent in r4604 - fine, the lock runs on r4634+)
- VPP present: `^VPP\s+ColorFmtConvertion:\s*nv12\s*->\s*p010` (this is the exact VPP+VA-memory+ENC path the fix is about; also `Buffer Memory  va`)
- Fallback markers: keep a qsvencc-specific list (case-insensitive): `falling back`, `fallback`, `is not supported with`, `unable to decode by qsv`.
**Prerequisite:** `run_session` writes `proc.stderr` to `stderr_path` - the harness already persists it, so `session_paths(...)[1]` log exists for qsvencc sessions too (today it is only read for ffmpeg).

### Anti-Patterns to Avoid
- **Skipping instead of failing when the lock's preconditions are wrong.** The module-level `_require_hardware` fixture currently also requires `ffmpeg-8.1`; a qsvencc lock must not silently skip in an image without ffmpeg-8.1 (e.g. the slim root image). Split: qsvencc tests need only `/dev/dri/renderD128` + `qsvencc` + fixture; the ffmpeg test keeps its ffmpeg-8.1 skip. Missing hardware/fixture = loud skip (existing convention); **old revision = FAIL** (call the gate/`parse_revision` in the test and `pytest.fail`).
- **Counting failed starts as clean** (D-13): keep the `failed` list + assert, as in the ffmpeg test.
- **Regexing raw stderr**: qsvencc emits ANSI SGR (`\x1b[39m`, `[33m`, `[31m`) even when redirected to a file - strip with `re.sub(r"\x1b\[[0-9;]*m", "", log)` first.
- **Editing `legacy/`** (frozen oracle).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-frame corruption detection | A new comparer | Existing `sweep_chunk` / `corrupt_frame_count` (ffmpeg `psnr` stats, <30 dB) | Locked methodology, already validated; frame-count parity cannot detect the bug |
| Concurrent launch/accounting | New thread pool | `run_concurrent` (SESSION_OK/FAILED/SWEEP_SKIPPED) | Already enforces "failed start != clean" |
| Download integrity | Custom python checker | `sha256sum -c` in the Dockerfile RUN | Build fails on mismatch, standard |
| .deb dependency resolution | awk control-file surgery | `apt-get install -y --no-install-recommends /tmp/x.deb` | New .deb deps are satisfiable on both bases |
| Subprocess mocking | monkeypatching `subprocess` | `shared.proc` seam + `fp` fixture | Project convention |

## Runtime State Inventory

Not a rename/refactor phase; but the binary swap has stateful aspects:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None - chunk `.obu` workdirs are transient; no DB | None. Note: existing `*.chunks` dirs encoded with r4604 may contain corrupt frames; they are not auto-detected. Recommend README/SUMMARY note: re-encode anything produced with r4604 at JOBS>1 |
| Live service config | None | None |
| OS-registered state | Installed `/usr/bin/qsvencc` is r4604 in the current devcontainer (sha256 `e9c63226...caef`, differs from both .debs' payloads only by build) | Image rebuild required; for in-place dev testing without rebuild, use a PATH-prefixed scratch dir (verified approach) |
| Secrets/env vars | `github_token` BuildKit secret (optional) in root Dockerfile and `docker-publish.yml` | Not needed for a public repo (see R6); keep pattern for private forks |
| Build artifacts | GHCR images previously published contain r4604 | After release, publish new tag; old tags keep the bug (the runtime gate will make them refuse - that is the intent) |

## Research Findings (answers to the open items)

**R1 - D-12 resolved (VA-API backend).** On the A380 with r4634 and the exact production flags:
- `--backend qsv`: rc=0, 111 frames, log shows `Backend qsv`, `Buffer Memory va`, `VPP ColorFmtConvertion: nv12 -> p010`.
- `--backend vaapi --avhw`: rc=253, stderr: `avqsv: codec h264(yuv420p) unable to decode by qsv.` / `failed to initialize file reader(s).` / `--avhw is not supported with --backend vaapi.` -> hard error, no silent SW-decode fallback.
- `--backend auto` on a box *with* a QSV device resolves to qsv (hardware tier incl. legacy-parity test passed on r4634 with legacy argv lacking the flag). Behaviour of `auto` on a box *without* a QSV device was not testable here -> remains the motivation for explicit `qsv` [ASSUMED that explicit `qsv` then errors rather than falls back; consistent with upstream docs cited in D-12].
- r4604 does not know `--backend` (D-16 must strip it; r4604 has no `Backend` header line).
- Argv placement: insert right after the binary, e.g. `["qsvencc", "--backend", "qsv", "--avhw", "--va", ...]`; tests should assert pair adjacency (`cmd[cmd.index("--backend")+1] == "qsv"`), not absolute index.

**R2 - Package verification.** Verified in scratch (`dpkg-deb -x`, never installed): sha256 `aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d` (match), size 30081716 (match), `Package: qsvencc`, `Version: 8.31`, content = single `./usr/bin/qsvencc` (82.6 MB), `ldd` shows only libva-drm.so.2, libva.so.2, libdrm.so.2, libgcc_s, libm, libmvec, libc (no unresolved). oneVPL is dlopen'd at runtime (already provided by `libvpl2`/`libmfx-gen1.2` in root image and by the dlstreamer base). Because the .deb's Version is `8.31` for both builds, `dpkg -l` cannot distinguish - only `--version` rNNNN does (reason for D-08).

**R3 - Fix detection at runtime.** See Pattern 1. Fail-closed cases to unit-test: r4603 (refuse), r4634 (pass), r9999 (pass), `8.31` without `(r...)` (refuse), empty output, rc!=0, `FileNotFoundError`, `TimeoutExpired`, garbage first line, ANSI-prefixed line (parser should receive text as-is; first line anchor `^QSVEncC` makes a leading escape fail closed - acceptable, but do not silently strip).

**R4 - Harness feasibility on new build** [VERIFIED]: probe = unmodified harness + `--backend qsv` prepended to argv, PATH-prefixed scratch dir with a symlink to the extracted r4634 binary. Reference build 16 s; 12 iterations JOBS=3 = 12 s each, 0 corrupt / 0 failed. Same harness on r4604: reference 17 s, iterations 12-23 s, corrupt 0,0,... totals 2/4 iterations affected (1 frame each, scenes 1129 and 923) - per-iteration corruption probability ~0.5 here, so P(8 clean iterations | still broken) ~ 0.4% for the committed test; stress tier (>=20 iterations) ~1e-6. Estimated stress-matrix wall time qsvencc-only: JOBS 3/5/8 x 20 ~ 20-25 min [estimate from 12 s @ JOBS=3, scaling with load].

**R5 - ICQ/hdr_flags deviations (D-14, discretion).** Recommendation: drop the `--icq 24` override (production ICQ is 23; the reference and test runs use the same binary and command so PSNR comparison is unaffected) and use real production `chunk_command` with `hdr_flags=[]` only for the Cold Eyes SDR fixture (it is an SDR 1080p H.264 remux; `detect_hdr` would return `[]` anyway - better to call `detect_hdr(FIXTURE)` once for fidelity, it is a cheap ffprobe). `metrics=False` must stay: `--psnr/--ssim` need OpenCL (this devcontainer now shows `VA-API OpenCL: Intel(R) Arc(TM) A380` so it may work, but root slim image has no Intel ICD) and would change the pipeline under test. Keep `ICQ` argument in `qsvencc_command` signature optional to avoid churn for `scratch/gate_stress_matrix.py`.

**R6 - Dockerfile mechanics.**
- Repo `Tualua/enpipe` is **public** (unauthenticated `api.github.com/repos/Tualua/enpipe` -> 200) and has **zero releases** today -> asset download needs no token; keep the optional `github_token` secret in the root Dockerfile for private forks (`"$@"` pattern); in `.devcontainer/Dockerfile` plain `curl -fsSL`.
- Use ARGs for pin bumps: `ARG QSVENCC_URL=...`, `ARG QSVENCC_SHA256=aa10f196...743d`, then `curl -fsSL -o /tmp/qsvencc.deb "$QSVENCC_URL" && echo "$QSVENCC_SHA256  /tmp/qsvencc.deb" | sha256sum -c - && apt-get install -y --no-install-recommends /tmp/qsvencc.deb`. Remove the awk/dpkg-deb -R/-b dance and the `api.github.com/.../releases/latest` + jq lookup (both images; `jq` stays used by dovi_tool).
- Suggested asset name: `qsvencc_8.31-r4634_amd64.deb` (distinct from upstream's `qsvencc_8.31_amd64.deb`, which is r4604) to avoid mixing the two files; internal dpkg Version remains 8.31 (cosmetic). Tag e.g. `deps-qsvencc-r4634`; mark as pre-release so it does not become "latest" for the repo.
- Root image (python:3.12-slim-trixie): `apt-get install ./deb` will add `libva-x11-2` (declared dependency, pulls libx11 chain; small). Binary is built against glibc 2.31 -> fine on trixie. Not testable here (no docker/podman in this devcontainer) - [ASSUMED] works; the image build/run smoke (`qsvencc --version` in a RUN, which needs no GPU) is the verification and also acts as a build-time gate: add `RUN qsvencc --version | head -1 | grep -E '\(r(4[6-9][0-9]{2}|[5-9][0-9]{3})\)'`-style check or simply call a tiny shell comparison; simplest robust option: `rev=$(qsvencc --version | sed -n '1s/.*(r\([0-9]*\)).*/\1/p'); test "${rev:-0}" -ge 4634`.
- The CLAUDE.md/PROJECT.md text "Debian trixie required" is stale for the devcontainer (it is `intel/dlstreamer` Ubuntu 24.04 since quick 260722-lji) - the root image is still trixie. Do not "fix" base images in this phase.
- Pre-build smoke without rebuilding the dev container is possible: PATH-prefixed scratch binary (done for all verification here).

**R7 - post-create.sh.** Existing style: best-effort script under `set -euo pipefail`, no mid-script `exit 1`; ENV-01 tracks `ENV01_OK` and prints a summary line near the end (lines ~203-209). Mirror: compute `QSV01_OK` from `qsvencc --version` first line (`sed -n '1s/.*(r\([0-9]*\)).*/\1/p'`), print the version line, and add a summary `QSV-01 (qsvencc >= r4634 / 45003f1): OK|ПРОВАЛЕН`. The current line 138 `printf "  qsvencc:   "; ... | head -1` is replaced/augmented (mind `pipefail` with `head -1` - qsvencc writes few lines so SIGPIPE risk is low, but capture to a variable first like ENV-01 does). "Hard-assert" in this script means flag + loud summary, consistent with ENV-01; do not introduce `exit 1` unless the user wants it (flag as small discretion item).

**R8 - Gate placement & test-suite fallout (see Pitfall 1).** `run_encode` batch recursion (`process_one` -> `run_encode`) and `run_pipeline` batch (`process_one` -> run_detect+run_encode) re-enter the preflight per file, so the 7 ms check runs per file as well as once up front. This satisfies "refuse before the loop" (the top-level call gates first); do not add state to suppress repeats.

**R9 - Non-vacuity (D-16) recipe** [VERIFIED approach]: `dpkg-deb -x old.deb $SCRATCH/oldx`; symlink `$SCRATCH/oldbin/qsvencc -> $SCRATCH/oldx/usr/bin/qsvencc`; run the stress/probe runner with `PATH=$SCRATCH/oldbin:$PATH` and a harness command with `--backend qsv` removed (e.g. runner monkeypatches `qsvencc_command` to drop the pair, or the harness accepts a `strip_backend` kwarg that the committed test never sets). Do not run the committed pytest with the old binary (it must fail the revision precondition by design). Note `qsvencc` is resolved via PATH inside `chunk_command` output (`"qsvencc"`), so PATH override is sufficient.

## Common Pitfalls

### Pitfall 1: The new gate breaks ~30 existing fast tests
**What goes wrong:** Tests in `tests/unit/cli/{test_cli_run,test_batch_run,test_cli_dispatch}.py`, `tests/unit/encoding/{test_batch_dispatch,test_pipeline_wiring}.py` stub only `shutil.which`. A real `qsvencc --version` -> `FileNotFoundError` on CI (no qsvencc) or, in `test_pipeline_wiring`, `_proc.run` is globally replaced by a Mock returning `stdout=""` -> unparseable -> fail-closed `die()`.
**How to avoid:** Add `tests/unit/conftest.py` (none exists today anywhere in `tests/`) with an autouse fixture that `monkeypatch.setattr`s `ensure_qsvencc_fixed` to a no-op in BOTH namespaces (`enpipe.encoding.pipeline` and `enpipe.cli.main`, i.e. import the function by name into each module so patch targets exist). Gate-specific tests restore the real function via `monkeypatch.setattr(mod, "ensure_qsvencc_fixed", real)` or call the leaf module directly with `fp`. Add explicit tests: `run_encode`/`run_pipeline` die on an old build, and `run_pipeline` dies before `run_detect` (mirror `test_preflight_fails_before_run_detect`).
**Warning signs:** CI red with FileNotFoundError or `die` in unrelated tests.

### Pitfall 2: ANSI escapes in qsvencc stderr
**What goes wrong:** `re.search(r"^GopRefDist...", log, re.M)` fails because lines start with `\x1b[39m`; or, worse, a negative marker check passes vacuously.
**How to avoid:** Strip SGR sequences first; unit-test the triad function against a captured real log (commit a trimmed fixture string in the test, ~12 lines as in Pattern 2 including the escape bytes).

### Pitfall 3: Release asset not uploaded before rebuild / before 2026-10-15
**What goes wrong:** Dockerfile points at a URL that 404s; or the nightly artifact expires and the .deb is lost (only the user can download via nightly.link; today it is reachable: `https://nightly.link/rigaya/QSVEnc/actions/runs/36932190976/QSVEncC_ubuntu2004_deb.zip`, zip ~30.09 MB, contains `qsvencc_8.31_amd64.deb`; no `unzip` in the devcontainer - use `python3 -c "zipfile..."` or `bsdtar`).
**How to avoid:** Make the upload the FIRST plan task, as a `checkpoint:human-action` with exact commands (`gh` is NOT installed in the devcontainer; use host `gh release create deps-qsvencc-r4634 --prerelease ... qsvencc_8.31-r4634_amd64.deb` or the web UI, or `curl` with a token against the REST API). Verify with `curl -fsSL -o /tmp/x URL && sha256sum` before touching Dockerfiles.

### Pitfall 4: Lock test silently skipping
See Anti-Patterns. The module-level autouse fixture skips the whole module if `ffmpeg-8.1` is absent. Restructure so the qsvencc test depends only on its own prerequisites.

### Pitfall 5: Harness `qsvencc_command` still strips production fidelity
It currently forces `--icq 24` and `hdr_flags=[]` (R5). A lock that tests a different argv than production can go stale silently (e.g. a future flag in `chunk_command`). Test also that the harness command equals `chunk_command(...)` modulo the declared deviations (cheap unit assertion in the fast tier is possible since the harness is import-safe - but the harness lives under `tests/integration/`; keep that assertion inside the hardware test file or a small fast test that imports the harness via the same `sys.path` shim).

### Pitfall 6: Evidence mixing binaries
The harness resolves `qsvencc` from PATH; ensure the run records `qsvencc --version` first line in the evidence block, and for the old-binary run, that PATH really pointed to the old one (print `shutil.which("qsvencc")` + version in the runner header).

### Pitfall 7: Fixture/hardware dependence
Lock needs `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` (21.4 GB, present here) - skip loudly otherwise (existing convention, keep message "NOT a failure"). The hardware workflow `hardware-integration.yml` is a manual self-hosted stub - no CI change needed.

## Code Examples

### Hardware-gated lock test skeleton (inversion of the control test)
```python
# tests/integration/test_concurrency_immunity.py -- RU comments in the real file
def test_qsvencc_immune_at_production_jobs(tmp_path):
    rev = harness.qsvencc_revision()                       # parse_revision(first line)
    assert rev is not None and rev >= QSVENCC_MIN_REV, (...)   # FAIL, not skip (lock precondition)
    refs = harness.build_isolated_reference("qsvencc", tmp_path)
    failed, total_corrupt, triad_log, triad_obu = [], 0, None, None
    for iteration in range(IMMUNITY_ITERS):
        outcomes = harness.run_concurrent("qsvencc", JOBS, tmp_path, iteration, refs)
        ... # identical accounting to the ffmpeg test (SESSION_FAILED -> failed, never clean)
        # capture first clean session's .verbose.log + obu for the triad
    assert not failed
    assert total_corrupt == 0
    assert harness.assert_qsvencc_triad(triad_log, triad_obu) == []
```
Source pattern: existing `test_ffmpeg_av1qsv_immune_at_production_jobs` (same file) - reuse by factoring the loop into a helper `_run_immunity(backend)` to avoid duplication.

### Release + verify commands for the human checkpoint
```bash
# on a machine with gh and the downloaded zip extracted
sha256sum qsvencc_8.31_amd64.deb   # must be aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d
cp qsvencc_8.31_amd64.deb qsvencc_8.31-r4634_amd64.deb
gh release create deps-qsvencc-r4634 --repo Tualua/enpipe --prerelease \
  --title "qsvencc r4634 (45003f1) mirror" --notes "Mirror of rigaya/QSVEnc Actions run 36932190976 ..." \
  qsvencc_8.31-r4634_amd64.deb
curl -fsSL https://github.com/Tualua/enpipe/releases/download/deps-qsvencc-r4634/qsvencc_8.31-r4634_amd64.deb | sha256sum
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hypothesis: iHD/kernel 10-bit surface aliasing; ffmpeg av1_qsv as escape | Real cause = missing MFX VPP output sync before encoder submit with VA memory, fixed in qsvencc 45003f1 | 2026-10-01 | Debug docs' root-cause sections are superseded; close with the upstream resolution (D-19) |
| qsvencc `.deb` per distro (Ubuntu24.04 asset + dep-strip) | unified Ubuntu20.04-built .deb with relaxed deps (libc6>=2.31) | master after 8.31 (verified in this .deb) | Dep-strip awk obsolete; trixie glibc constraint comment is stale |
| Implicit `--backend` | `--backend auto|qsv|vaapi` (new Linux VA-API backend) | between 8.31 and 45003f1 | Pass `--backend qsv` explicitly (R1) |

**Deprecated/outdated in repo text:** CLAUDE.md/PROJECT.md "Debian trixie required for qsvencc glibc>=2.39" (devcontainer is Ubuntu 24.04 dlstreamer; new .deb needs only glibc 2.31); `Dockerfile` header comments about intel-opencl-icd/libmfx1 dependency stripping; `.devcontainer/Dockerfile` "latest Ubuntu24.04 asset" block comment.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Root slim-trixie image installs and runs the r4634 .deb via `apt-get install ./deb` (libva-x11-2 resolvable, glibc 2.31 ABI fine) | R6 | Root image build fails; mitigated by the build-time `qsvencc --version` check - discovered at first image build (not testable in this devcontainer: no docker/podman) |
| A2 | `--backend qsv` with no QSV device errors instead of falling back | R1 | Low: only weakens the rationale for the flag, not correctness of the lock |
| A3 | `Input Info avsw:` is printed for software decode (so `avqsv:` positive match suffices) | Pattern 2 | Triad HW-decode leg could be weaker than thought; mitigate by also keeping the `Buffer Memory va` + `VPP` legs |
| A4 | Upstream will ship an 8.32+ release containing r4634+ soon | D-06 | None for this phase; the TODO/backlog item covers it |
| A5 | Stress-matrix wall time ~20-25 min qsvencc-only | R4 | Scheduling only |

## Open Questions (RESOLVED)

1. **Should the post-create revision check `exit 1` (true hard-assert) or only flag like ENV-01?**
   - Known: ENV-01 style is flag + summary, never mid-script exit; D-07 says "hard-asserts ... mirroring ENV-01 style".
   - Recommendation: follow ENV-01 (flag + `ПРОВАЛЕН` summary); the runtime gate is the real enforcement.
   - RESOLVED: ENV-01 style adopted (flag + `ПРОВАЛЕН` in summary, no mid-script `exit 1`); runtime gate is the enforcement — Plan 07-03 Task 2 (D-07).
2. **Release asset name/tag** (discretion): recommend `deps-qsvencc-r4634` + asset `qsvencc_8.31-r4634_amd64.deb`, prerelease flag.
   - RESOLVED: tag `deps-qsvencc-r4634`, asset `qsvencc_8.31-r4634_amd64.deb`, pinned by sha256 — Plan 07-01.
3. **Does the user want the first plan task to be the upload checkpoint?** Strongly recommended (time-boxed to 2026-10-15; blocks Dockerfile verification).
   - RESOLVED: yes — the mirror-upload checkpoint is Plan 07-01 Task 1, ahead of all Dockerfile work.
4. **Where is the old `.chunks`/outputs risk documented?** Suggest one line in the Phase 7 SUMMARY/README that outputs produced with r4604 at JOBS>1 may contain isolated corrupt frames.
   - RESOLVED: one-line r4604/JOBS>1 outputs warning recorded in the ФАЗА 7 debt-closure section of scene-chunk-frame-mismatch.md — Plan 07-05 Task 3 (D-19).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Intel Arc A380 `/dev/dri/renderD128` | COR-02 hardware gate, D-16/17/18 | yes | iHD 26.3.2, kernel 6.19.14-200.fc43.x86_64 | - (hardware tests skip loudly elsewhere) |
| Cold Eyes fixture `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` | COR-02 | yes | 21.4 GB | - |
| qsvencc installed | harness | yes (r4604 now) | r4604 | PATH-prefixed r4634 scratch extraction (verified) |
| ffmpeg/ffprobe (system) | PSNR sweep, count_frames | yes | 6.1.1 | - |
| ffmpeg-8.1 | ffmpeg COR-01 test only | yes | /usr/local/bin/ffmpeg-8.1 | not needed for the qsvencc lock |
| uv / `.venv` pytest | tests | yes (`.venv/bin/python -m pytest`; system python3 has no pytest) | - | - |
| gh CLI | creating the Release | **no** | - | host `gh`, web UI, or REST via curl+token |
| unzip | opening nightly artifact | no | - | `python3 -m zipfile`/`zipfile` module |
| docker/podman | building images | no (not in this devcontainer) | - | host rebuild (existing project practice); image builds can't be verified in-session |
| Network to github.com / nightly.link | downloads | yes | - | - |

**Missing with no fallback:** none for planning. **Image rebuild verification** must happen on the host (same as quick tasks 260722-lji / 260723-36w) - plan a human-verify checkpoint after the Dockerfile edits.

## Validation Architecture

Skipped: `workflow.nyquist_validation` is `false` in `.planning/config.json`. (Test mapping for reference: fast tier = parser/gate/chunk_command/preflight tests via `.venv/bin/python -m pytest -m "not hardware"`; hardware tier = `... -m hardware tests/integration/test_concurrency_immunity.py tests/integration/test_hardware_real_media.py` on this box; both run in < 3 min here.)

Wave 0 gaps: `tests/unit/conftest.py` (autouse gate stub - must land in the same plan as the gate or the suite goes red), `tests/unit/shared/test_qsvencc_version.py`, qsvencc triad unit test with a captured-log fixture.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes (small) | Version string parsed with an anchored regex; subprocess argv as list (no shell) - existing convention |
| V6 Cryptography | no (integrity only) | `sha256sum -c` against pinned digest; never hand-roll |
| V10 Malicious code / supply chain | yes | Pin by sha256, mirror in own Release, verify in build; the artifact originates from upstream CI run 36932190976 for head_sha 45003f1 (digest matches the one recorded in CONTEXT.md, computed independently here) |
| V2/V3/V4 | no | CLI tool, no auth/session |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Tampered/substituted .deb via release asset or MITM | Tampering | sha256 pin in Dockerfile, https `curl -f`, build fails on mismatch |
| Downgrade to corrupting build via PATH | Tampering/Integrity | runtime gate fail-closed, no bypass (D-09/D-10) |
| Unverified bypass env var | Elevation | none provided by design (D-10) |

## Sources

### Primary (HIGH confidence)
- Local verification on this host (2026-10-02): extracted/ran r4634 and r4604 binaries; sha256 checks; harness runs; hardware tier run.
- GitHub REST API (rigaya/QSVEnc releases, commits, compare 8.31...45003f1; Tualua/enpipe repo + releases).
- Repository code: `src/enpipe/encoding/{chunk,pipeline}.py`, `src/enpipe/cli/main.py`, `src/enpipe/shared/proc.py`, `tests/integration/_concurrency_harness.py`, `test_concurrency_immunity.py`, `scratch/gate_stress_matrix.py`, `.devcontainer/{Dockerfile,post-create.sh}`, `Dockerfile`, `pyproject.toml`, `.github/workflows/*`.
- Phase 6 / 07-CONTEXT.md for decisions and methodology.

### Secondary (MEDIUM)
- Upstream `QSVEncC_Options.en.md` `--backend` section as cited in CONTEXT.md (not re-fetched; behavior of explicit options re-verified empirically).

### Tertiary (LOW)
- None relied upon.

## Metadata

**Confidence breakdown:**
- Standard stack / artifact: HIGH - digest, version, deps, run all verified locally.
- Gate design / version format: HIGH - real output captured from both builds.
- Harness/lock feasibility: HIGH - ran on the real fixture; both positive (r4634 clean) and negative (r4604 corrupts) observed.
- Root-image install on trixie: MEDIUM - not buildable here (A1).
- Test-suite fallout: HIGH - read the affected tests; fix is mechanical.

**Research date:** 2026-10-02
**Valid until:** nightly artifact URL until 2026-10-15; otherwise ~30 days, or until rigaya publishes 8.32+ (re-check releases then for D-06).
