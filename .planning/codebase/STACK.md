# Technology Stack

**Analysis Date:** 2026-07-08

## Project Status Note

This repository is early-stage. There is no application entry point, package
manifest, or test suite at the repository root. What exists:

- `legacy/scene_detection.py`, `legacy/encode_scenes.py` — a working (per
  in-code documentation) but standalone pair of CLI scripts implementing a
  two-stage video re-encode pipeline (scene detection → scene-aware AV1
  encode). Not wired together, not packaged, no `__init__.py`/module structure.
- `PIPELINE_DESIGN.md` — a Russian-language design document proposing a
  **planned, not-yet-implemented** streaming/pipelined orchestrator that would
  overlap scene detection and encoding via an in-process `queue.Queue`
  producer/consumer. Its own stated verdict is **"do not build"** on the
  current (spinning-disk ZFS) hardware; implementation is deferred until the
  source moves to SSD/NVMe. Everything under "Planned / Not Implemented"
  below comes from this doc.
- `.devcontainer/` — a fully specified Docker-based dev environment for the
  actual runtime target (Intel Arc GPU transcoding host).

Distinguish carefully: **Existing** = present in `legacy/` and runnable today
(assuming the devcontainer environment). **Planned** = only described in
`PIPELINE_DESIGN.md`, no code written.

## Languages

**Primary:**
- Python 3.12 - `legacy/scene_detection.py`, `legacy/encode_scenes.py` (base image `mcr.microsoft.com/devcontainers/python:3-3.12-trixie`, pinned in `.devcontainer/Dockerfile`)

**Secondary:**
- Bash - `.devcontainer/post-create.sh` (devcontainer provisioning/self-check script)
- Dockerfile - `.devcontainer/Dockerfile` (image build recipe)
- JSON - `.devcontainer/devcontainer.json`, `.devcontainer/devcontainer-lock.json` (devcontainer config/lockfile)
- Markdown (Russian) - `PIPELINE_DESIGN.md` (design/decision doc, not code)

## Runtime

**Environment:**
- Python 3.12 on Debian 13 "trixie" (chosen specifically because prebuilt `qsvencc` .deb requires glibc ≥2.39, unavailable on Debian 12 "bookworm" — see `.devcontainer/Dockerfile` comments)
- Runs inside a VS Code / Claude Code **devcontainer** (Docker or Podman); GPU access requires `/dev/dri` passthrough (Intel Arc A380 "Alchemist")
- Node.js LTS - installed via devcontainer feature `ghcr.io/devcontainers/features/node:2` (used only to host npm-installed AI CLI agents, not for application code)

**Package Manager:**
- **Python:** plain `pip` (no venv — base image's Python is not "externally managed"), invoked directly in `.devcontainer/post-create.sh`:
  `python3 -m pip install --no-warn-script-location "scenedetect[opencv-headless]" numpy`
  - **No `requirements.txt`, `pyproject.toml`, or lockfile exists.** Dependency versions are unpinned; whatever is "latest" from PyPI at container build time.
- **Node:** `npm` (global installs only, no `package.json` in repo): `npm install -g opencode-ai @qwen-code/qwen-code`
- **System packages:** `apt-get` inside `.devcontainer/Dockerfile` (Debian trixie, non-free/contrib enabled for `intel-media-va-driver-non-free`)
- Lockfile: present only for devcontainer features (`.devcontainer/devcontainer-lock.json`, pins `claude-code` feature 1.0.5 and `node` feature 2.1.0 by digest). No lockfile for Python or npm dependencies.

## Frameworks

**Core:**
- None (no web framework, no application framework). The codebase is a pair of standalone CLI scripts orchestrating external binaries via `subprocess`.
- `scenedetect` (PySceneDetect) 0.7.x - `legacy/scene_detection.py` - scene-cut detection library (`SceneManager`, `AdaptiveDetector`, `VideoStream` custom backend). Version constraint noted only in a docstring ("Проверено против PySceneDetect 0.7") — not pinned in any manifest.
- `numpy` - `legacy/scene_detection.py` - frame buffer handling (`np.frombuffer` on raw BGR24 pipe output)

**Testing:**
- None detected. No test framework, no test files, no CI config (`.github/` absent, no `*.yml`/`*.yaml` workflow files anywhere in the repo).

**Build/Dev:**
- Docker/Podman (devcontainer build) - `.devcontainer/Dockerfile`
- VS Code Dev Containers - `.devcontainer/devcontainer.json`
- Claude Code CLI (+ GSD plugin) - installed via devcontainer feature and `claude plugin install gsd@gsd-plugin` in `post-create.sh`; used for AI-assisted development, not part of the runtime pipeline
- opencode / qwen-code - additional AI CLI agents installed globally via npm in `post-create.sh`, dev-tooling only

## Key Dependencies

**Critical (existing, `legacy/`):**
- `scenedetect[opencv-headless]` (PySceneDetect) - unpinned - core scene-boundary detection engine
- `numpy` - unpinned - raw frame buffer reshaping from ffmpeg pipe output
- `qsvencc` (Rigaya QSVEnc) - latest GitHub release .deb, installed in `.devcontainer/Dockerfile` with dependency patching (strips `intel-opencl-icd`/`libmfx1` deps not available on Debian trixie) - AV1 hardware encoder driving Intel Arc QSV; invoked via `subprocess` in `legacy/encode_scenes.py::chunk_command`
- `ffmpeg` / `ffprobe` (Debian trixie apt package) - QSV-accelerated decode/downscale pipe for scene detection (`legacy/scene_detection.py::QsvPipeStream`), audio transcode (`legacy/encode_scenes.py::encode_audio`), and metadata probing throughout
- `mkvmerge` (mkvtoolnix, apt) - final muxing of encoded video/audio/subs/chapters (`legacy/encode_scenes.py::main`)

**Infrastructure:**
- `intel-media-va-driver-non-free` (iHD driver), `libva2`/`libva-drm2`/`vainfo`, `libvpl2` (oneVPL dispatcher), `libmfx-gen1.2`/`libmfxgen1`/`libmfx-gen1` (oneVPL GPU runtime, package name varies by distro release — Dockerfile tries all three), `ocl-icd-libopencl1` (OpenCL loader, required by qsvencc for VPP filters though Intel's own OpenCL ICD is unavailable on trixie, so OpenCL-based VPP filters are noted as non-functional) - all installed in `.devcontainer/Dockerfile`
- `dovi_tool` (quietvoid, static musl binary from GitHub releases) - installed in `.devcontainer/Dockerfile` but **not referenced anywhere in `legacy/*.py`** — Dolby Vision RPU handling is done per-chunk by `qsvencc --dolby-vision-rpu copy` instead, making this dependency currently unused/vestigial in the existing code
- `tmux` - apt package, interactive session persistence tool, not invoked by any script

## Configuration

**Environment:**
- No `.env` file support; configuration is via **plain OS environment variables read directly with `os.environ.get`** in `legacy/encode_scenes.py`:
  - `ICQ` (default `"23"`) - qsvencc quality target
  - `QPMAX` (default `"100"`) - qsvencc max QP
  - `GOP_LEN` (default `"300"`) - GOP length
  - `DV_PROFILE` (default `"10.1"`) - Dolby Vision profile
  - `JOBS` (default `"3"`) - parallel `qsvencc` sessions
  - `FLAC_LEVEL` (default `"8"`) - FLAC compression level for lossless audio
  - `AUDIO_COPY` (default `"0"`) - `"1"` skips audio transcoding, copies tracks as-is
- `legacy/scene_detection.py` config is via a frozen dataclass `DetectionConfig` (analysis width, QSV on/off, detector thresholds, ffmpeg/ffprobe binary paths) constructed programmatically or via CLI flags — no env-var or file-based config for this stage.
- `LIBVA_DRIVER_NAME=iHD` set as `containerEnv` in `.devcontainer/devcontainer.json` (selects Intel Media driver for VA-API)
- `.gitignore` explicitly excludes `.env`, `.envrc`, `.venv`/`venv/`/`env/` — standard Python secret/venv hygiene, though no such files currently exist in the repo.

**Build:**
- `.devcontainer/Dockerfile` - full image build (Python base + Intel media stack + qsvencc + dovi_tool)
- `.devcontainer/devcontainer.json` - devcontainer features, GPU device passthrough (`--device=/dev/dri:/dev/dri`), host media directory bind mounts, `postCreateCommand`
- `.devcontainer/post-create.sh` - post-build provisioning: GPU render-group permissions, npm AI-CLI installs, Claude Code GSD plugin install, Python pip installs, environment self-check (`vainfo`, ffmpeg QSV encoder list, `qsvencc --version`, etc.)
- No `tsconfig.json`, `eslintrc`, `pyproject.toml`, `setup.py`, or similar build/lint config exists at the repo root.

## Platform Requirements

**Development:**
- Docker or Podman with devcontainer support (VS Code Dev Containers extension or `devcontainer` CLI)
- Host machine with an Intel Arc GPU exposing `/dev/dri/renderD128` (Alchemist architecture, e.g. Arc A380) for QSV/VA-API hardware decode+encode
- Host bind-mount paths expected at `/data/media` and `/data/downloads` (hardcoded in `.devcontainer/devcontainer.json` `mounts`)
- Podman-specific build fix present in Dockerfile (disables apt sandboxing, fixes `/tmp` permissions, needed because devcontainer features run apt-get as a non-root user that fails under Podman's build environment)

**Production:**
- No deployment target defined — this is a local/NAS transcoding toolchain run interactively or via cron/manual invocation, not a deployed service. `PIPELINE_DESIGN.md` refers to running on a "NAS" with a "spindle ZFS" disk array and Intel Arc A380.

---

## Planned / Not Implemented (per `PIPELINE_DESIGN.md`)

The following stack elements are **designed but have no code** — included here for completeness since the task requested documented-but-unbuilt stack:

- **In-process streaming orchestrator**: Python `threading` + `queue.Queue(maxsize=8)` bridging a producer thread (`detect_scenes_streaming()`, new function planned for `legacy/scene_detection.py`) and a consumer (refactored `main()` in `legacy/encode_scenes.py`, lines 542-645) to overlap scene detection and encoding via backpressure.
- No new external dependency would be introduced — same `scenedetect`, `ffmpeg`, `qsvencc` stack, just restructured control flow (`ThreadPoolExecutor` usage expands, ordered "high-water mark" flush logic generalized).
- Explicit regression-test requirement documented but not written: `list(detect_scenes_streaming(f)) == detect_scenes(f, jobs=1)`.
- **Decision:** implementation is gated on migrating source storage to SSD/NVMe (or a separate need for an orchestrator); not to be built on the current spinning-disk ZFS array.

---

*Stack analysis: 2026-07-08*
