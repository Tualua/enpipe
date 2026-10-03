# External Integrations

**Analysis Date:** 2026-10-03

## Overview

This project has **no network-facing services, databases, or authentication providers at runtime**. All integrations are:
1. **External CLI binaries** invoked via subprocess (`src/enpipe/shared/proc.py`)
2. **GitHub Releases API** consumed only during container build to fetch tool binaries
3. **Hardware**: Intel Arc GPU via VA-API/QSV over `/dev/dri`

All code is local/single-user; no API keys, tokens, or credentials are present.

## APIs & External Services

**GitHub Releases API (build-time only):**
- `api.github.com/repos/Tualua/QSVEnc/releases/tag/8.32-vppsync7` - fetch qsvencc `.deb` with specific SHA256 pinning
  - Called in: `Dockerfile` (ARG QSVENCC_URL), `.devcontainer/Dockerfile` (ARG QSVENCC_URL)
  - Auth: optional BuildKit secret `github_token` (unauthenticated calls have 60 req/hour limit; with token: 5000 req/hour)
  - Provenance: pinned to fork tag `8.32-vppsync7`; sha256 297d474c…6ac6 verified against release `SHA256SUMS` and the GitHub digest
  - qsvencc --version output: "8.32 (r4665)" — minimum revision checked at runtime via `src/enpipe/shared/qsvencc_version.py` (threshold: r4665)

- `api.github.com/repos/quietvoid/dovi_tool/releases/latest` - fetch latest dovi_tool static musl binary
  - Called in: `Dockerfile` line 195, `.devcontainer/Dockerfile` line 120 (alternative: ffmpeg 8.1 build from BtbN)
  - Auth: optional BuildKit secret `github_token` (same rate-limit consideration)
  - No SHA256 verification (moving target via `:latest`)
  - Currently unused in pipeline (DEBT-04); reserved for Phase 4 DV verification

**No application-runtime network APIs.** Source code makes zero HTTP requests; only offline subprocess calls.

## External CLI Tools

All invoked via subprocess; no SDK wrappers or client libraries:

**ffmpeg / ffprobe:**
- Purpose: video decode (QSV hardware-accelerated), audio transcode, metadata probing, frame counting
- Invoked in:
  - `src/enpipe/detection/stream.py` - subprocess decode to raw BGR24 for scene detection
  - `src/enpipe/encoding/keyframes.py` - ffprobe packet scan fallback for keyframe table
  - `src/enpipe/encoding/chunk.py` - frame count verification via packet count
  - `src/enpipe/encoding/hdr.py` - HDR10/HDR10+/Dolby Vision metadata detection via side_data
  - `src/enpipe/encoding/audio.py` - audio stream probing and transcode/copy
- Requires: `LIBVA_DRIVER_NAME=iHD` + `/dev/dri/renderD128` for QSV decode path
- Package: Ubuntu 24.04 apt (system ffmpeg 6.1.1); devcontainer optionally includes ffmpeg 8.1 from BtbN
- Entry point:  via `src/enpipe/shared/proc.py::run()` wrapper

**qsvencc (Tualua/QSVEnc 8.32+vppsync7):**
- Purpose: AV1 hardware encoding per scene chunk with HDR/DV metadata preservation
- Invoked in: `src/enpipe/encoding/chunk.py::encode_chunk()`
  - Command built by `chunk_command()`: `["qsvencc", "--backend", "qsv", "--avhw", ..., "--seek", ..., "--trim", ..., "-o", ...]`
  - PSNR/SSIM metrics parsed from stderr (regex patterns in `src/enpipe/encoding/chunk.py`)
  - Frame count verification post-encode (via `count_frames()` → ffprobe)
- Requires: Intel Arc GPU, `--backend qsv --avhw` flags
- Metrics (--psnr/--ssim) depend on OpenCL/VPP: stable on r4658, same patches in r4663 and r4665 (0 failures from 640 concurrent sessions; r4634 and upstream 8.32 had VIDEOMETRIC failures in Phase 8 matrix)
- Version constraint: minimum r4665 (carries the `--seek` fix and the open-GOP `--trim` fix), enforced at runtime via `src/enpipe/shared/qsvencc_version.py`

**mkvmerge (mkvtoolnix):**
- Purpose: final container muxing (video + audio + chapters/metadata)
- Invoked in: `src/enpipe/encoding/pipeline.py::main()` after chunk concatenation
- Invokes via subprocess after all chunks are concatenated into `movie.obu`
- Package: Ubuntu 24.04 apt

**dovi_tool:**
- Status: **currently unused** (DEBT-04 in `.devcontainer/Dockerfile`)
- Notes: Installed but not called by any active pipeline code
- Purpose (reserved): Dolby Vision RPU verification for Phase 4 (TEST-04)
- Current DV handling: delegated entirely to `qsvencc --dolby-vision-rpu copy` per-chunk
- Limitation: documented to work only with HEVC bitstreams; Phase 4 must verify applicability to AV1/OBU output before use

**Tool availability verification:**
- Preflight check at CLI entry point (`src/enpipe/cli/main.py::main()`) via `shutil.which()` for qsvencc/ffprobe/ffmpeg/mkvmerge
- Minimum qsvencc revision enforced via `src/enpipe/shared/qsvencc_version.py::check_qsvencc_version()` (compares parsed --version output revision against threshold r4665)

## Data Storage

**Databases:**
- None. No ORM, no DB client, no connection strings.

**File Storage:**
- Local filesystem only
- Devcontainer mounts (`.devcontainer/devcontainer.json`):
  - `/data/media` (input videos)
  - `/data/downloads` (scratch/output)
- Runtime working directory: temporary chunks/metrics/audio files written to `<output>.chunks/` directory adjacent to final `.mkv`, cleaned up after successful mux unless `--keep-work` is passed
- Scene list interchange: text file `<video>.scenes` (regex pattern: `frames \[(\d+), (\d+)\)`)

**Caching:**
- None explicit in code
- Relies on host OS page cache (ZFS ARC on NAS systems) as an operational effect of sequential full-file read during detection warming the cache for subsequent encode

## Authentication & Identity

**Auth Provider:**
- None. No login, accounts, or API keys. Single-user CLI toolchain.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Bugsnag/etc.)
- Errors surface as Python exceptions or `sys.exit()` via `src/enpipe/shared/logging.py::die()`

**Logs:**
- Plain stdout with elapsed-time prefixes via `src/enpipe/shared/logging.py::log()` and `step()` context manager
- Format: `[{elapsed:8.1f}s] {msg}`
- No structured logging, file writes, or log shipping

## CI/CD & Deployment

**Hosting:**
- None. Not a deployed service. Runs on local machine or NAS with Intel Arc GPU, invoked manually or by external scheduling.

**CI Pipeline:**
- `.github/workflows/ci.yml` - linting + unit/mocked/regression tests on hosted ubuntu-latest (no GPU, no hardware tests)
- `.github/workflows/docker-publish.yml` - build + push slim runtime image to GHCR on git tags (`v*`) or manual dispatch
- `.github/workflows/hardware-integration.yml` - planned; hardware tests on self-hosted Arc-equipped runner (not yet wired to any gate)
- All workflows use GitHub Actions standard `GITHUB_TOKEN` for container registry push/pull; no additional secrets required

**Docker image publishing:**
- GHCR: `ghcr.io/tualua/enpipe:<version>`, `:latest`
- Authenticated via `secrets.GITHUB_TOKEN` in `.github/workflows/docker-publish.yml`
- Multi-stage build (builder + slim runtime); final image contains only `/opt/venv` + system libraries + external binaries, no source code

## Environment Configuration

**Runtime environment variables (all with defaults, read via `os.environ.get()`):**
- `ICQ` (default "23") - qsvencc quality parameter
- `QPMAX` (default "100") - max quantization
- `GOP_LEN` (default "300") - GOP length frames
- `DV_PROFILE` (default "10.1") - Dolby Vision profile
- `JOBS` (default "3") - concurrent qsvencc encoding sessions
- `FLAC_LEVEL` (default "8") - FLAC compression level
- `AUDIO_COPY` ("0" or "1", default "0") - bypass audio transcode flag
- `LIBVA_DRIVER_NAME=iHD` - set at container level (`.devcontainer/devcontainer.json`, `Dockerfile`)

**Build-time configuration:**
- `.dockerignore` - context minimization for slim runtime image
- `pyproject.toml` - pytest markers (hardware tests excluded by default)
- Dockerfile ARG: `INTEL_PPA_KEY_FPR=0C0E6AF955CE463C03FC51574D098D70AFBE5E1F` - Intel PPA key fingerprint, verified before importing GPG keyring
- Dockerfile ARG: `QSVENCC_URL`, `QSVENCC_SHA256` - pinned qsvencc release URL and checksum

**Secrets location:**
- None present. `.gitignore` proactively excludes `.env*`, `.envrc`, virtualenv directories
- No API keys, tokens, or credentials checked in
- BuildKit secrets are optional and temporary: `github_token` (for higher GitHub API rate limits during build)

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None.

## Hardware Integration

**Intel Arc A380 (Alchemist):**
- GPU device: `/dev/dri/renderD128` (or `/dev/dri/card*` for display output)
- Drivers required: iHD (Intel Media driver), oneVPL dispatcher, GPU runtime (libmfx-gen1.2)
- OpenCL: intel-opencl-icd (required for qsvencc VPP metrics)
- VA-API: `LIBVA_DRIVER_NAME=iHD` environment variable selects Intel Media driver

**Environment variables for GPU access:**
- `LIBVA_DRIVER_NAME=iHD` - VA-API driver selection
- Devcontainer: `--device=/dev/dri:/dev/dri` passthrough in `.devcontainer/devcontainer.json` `runArgs`
- Production container: `--device /dev/dri` at runtime via `docker run` or `podman run`

---

*Integration audit: 2026-10-03*
