# Technology Stack

**Analysis Date:** 2026-10-03

## Languages

**Primary:**
- Python 3.12 - `src/enpipe/` (refactored package), `legacy/` (historical scripts for reference), all encoding/detection logic

**Secondary:**
- Bash/Shell - `.devcontainer/post-create.sh` (dev environment provisioning), Dockerfile RUN blocks
- Dockerfile - `Dockerfile` (production runtime image), `.devcontainer/Dockerfile` (development environment)
- JSON - `.devcontainer/devcontainer.json`, `.devcontainer/devcontainer-lock.json` (devcontainer config/lockfile)
- TOML - `pyproject.toml` (project manifest)

## Runtime

**Environment:**

Production:
- Python 3.12 on Ubuntu 24.04 (from `ubuntu:24.04` base in `Dockerfile`)
- glibc 2.39+ (required by qsvencc .deb)

Development:
- Python 3.12 on intel/dlstreamer base (Ubuntu 24.04 with Intel media stack pre-installed, in `.devcontainer/Dockerfile`)
- Node.js LTS (installed via devcontainer feature `ghcr.io/devcontainers/features/node:2`, used only for AI CLI agents; not part of application code)

**Package Manager:**
- uv (Astral) - modern, fast Python package manager and resolver (https://github.com/astral-sh/uv)
- Lockfile: `uv.lock` (present, revision 3, requires Python >= 3.12)

## Frameworks

**Core Application:**
- PySceneDetect 0.7 (with `opencv-headless` extra) - scene-cut detection via `AdaptiveDetector`, `SceneManager`; imported in `src/enpipe/detection/`
- NumPy 2.5.1 - frame buffer reshaping via `np.frombuffer` for raw BGR24 stream processing from ffmpeg

**Testing:**
- pytest 9.1.1 - test runner with markers; test files in `tests/unit/`, `tests/subprocess/`, `tests/integration/`
- pytest-subprocess 1.6.0 - subprocess mocking via fixtures for isolating external binary calls
- pytest-mock 3.15.1 - `mocker` fixture for patching functions and objects

**Linting:**
- ruff 0.15.20 - fast Python linter/formatter; checks `src tests` with pyflakes-only rules (F, E9xx) — no style rules (E/W) to avoid conflicts with dense binary-parsing code in `src/enpipe/mkv/ebml.py`

**Build/Deployment:**
- uv_build (>=0.11.28, <0.12) - PEP 517 build backend for wheel building in `Dockerfile` builder stage
- Docker / Podman - container orchestration for devcontainer and slim production runtime image
- VS Code Dev Containers - devcontainer CLI support

## Key Dependencies

**Production (from `pyproject.toml`):**
- scenedetect[opencv-headless] == 0.7 - PyOpenCV-based scene-cut detection engine
- numpy == 2.5.1 - numerical array operations for frame buffers

**External Binaries (subprocess invocations):**
- ffmpeg / ffprobe (Ubuntu 24.04 apt packages) - QSV-accelerated decode, audio transcode, metadata probing via `src/enpipe/shared/proc.py`
- qsvencc 8.32+vppsync7 (r4665, tag 8.32-vppsync7, sha256 297d474c…; Tualua/QSVEnc fork, GitHub releases, pinned by SHA256 in both `Dockerfile` and `.devcontainer/Dockerfile`) - Intel Arc AV1 hardware encoder; invoked with `--backend qsv --avhw` in `src/enpipe/encoding/chunk.py`
- mkvmerge (mkvtoolnix apt package) - final `.mkv` muxing via `src/enpipe/encoding/pipeline.py`
- dovi_tool (x86_64-unknown-linux-musl static binary, GitHub releases) - Dolby Vision RPU extraction; currently unused (DEBT-04, reserved for Phase 4)

**GPU/Media Stack (environment dependencies, not Python imports):**
- Intel Media driver (iHD, from Intel PPA `kobuk-team/intel-graphics`) - VA-API for Intel Arc A380
- oneVPL (libvpl2, libmfx-gen1.2 from Ubuntu 24.04 + Intel PPA) - GPU dispatcher and runtime
- OpenCL (intel-opencl-icd, ocl-icd-libopencl1) - qsvencc VPP metrics (--psnr/--ssim stable, measured on r4658: 0 failures from 640 sessions)
- vainfo (libva-utils) - VA-API diagnostics

## Configuration

**Environment Variables (read via `os.environ.get()` throughout `src/enpipe/`):**
- `ICQ` (default "23") - qsvencc quality (lower = better)
- `QPMAX` (default "100") - max quantization parameter
- `GOP_LEN` (default "300") - GOP length in frames
- `DV_PROFILE` (default "10.1") - Dolby Vision profile
- `JOBS` (default "3") - concurrent qsvencc encoding sessions in `src/enpipe/encoding/pipeline.py`
- `FLAC_LEVEL` (default "8") - FLAC compression level in `src/enpipe/encoding/audio.py`
- `AUDIO_COPY` ("0" or "1", default "0") - bypass audio re-encode flag in `src/enpipe/encoding/audio.py`
- `LIBVA_DRIVER_NAME=iHD` (set in `.devcontainer/devcontainer.json` `containerEnv` and `Dockerfile` `ENV`)
- `PATH=/opt/venv/bin:$PATH` (production `Dockerfile` only, for `enpipe` CLI entry point)

**Build Configuration Files:**
- `pyproject.toml` - project metadata, dependencies, dev groups (pytest, ruff), pytest config, ruff settings
- `uv.lock` - pinned dependency versions with hashes and source URLs
- `.devcontainer/devcontainer.json` - devcontainer spec, Node.js feature, GPU passthrough (`--device=/dev/dri`), volume mounts, `containerEnv`
- `.dockerignore` - production build context (excludes `.git`, `tests/`, `legacy/`, `.planning/`, dev files to minimize image size)

## Platform Requirements

**Development:**
- Docker or Podman with devcontainer CLI support
- Intel Arc GPU on host exposing `/dev/dri/renderD128` (Alchemist, e.g., A380)
- Host directories: `/data/media` (input videos), `/data/downloads` (scratch/output) as per `.devcontainer/devcontainer.json` `mounts`
- Named volumes for credential persistence: `enpipe-claude`, `enpipe-qwen`, `enpipe-opencode-data`, `enpipe-opencode-config`
- Podman rootless: `--group-add keep-groups` required for render-group membership

**Production (slim runtime container):**
- Docker or Podman with `--device /dev/dri` for GPU access
- Ubuntu 24.04 (glibc 2.39+) or compatible distro with Intel PPA for intel-opencl-icd
- No dev tools, tests, or source code in final image (multi-stage build; only `src/enpipe` + `.venv` shipped)

**Deployment Target:**
- Local machine or NAS with Intel Arc GPU
- No cloud deployment; runs interactively or via cron as standalone pipeline
- Output: `.mkv` with AV1 video, HDR10/HDR10+/Dolby Vision metadata, audio (FLAC/Opus/copied), scene chapters

---

*Stack analysis: 2026-10-03*
