# External Integrations

**Analysis Date:** 2026-07-08

## Overview

This project has **no network-facing external services, no database, no
authentication provider, and no webhooks**. All "integrations" are local
**external binaries/CLI tools** invoked via `subprocess`, plus **GitHub
Releases** consumed only at devcontainer *build* time to fetch tool binaries.
There is a clear split between what's already wired up in `legacy/` and what
`PIPELINE_DESIGN.md` proposes but doesn't implement (noted inline).

## APIs & External Services

**GitHub Releases API (build-time only, not runtime):**
- `api.github.com/repos/rigaya/QSVEnc/releases/latest` - fetches latest `qsvencc` `.deb` asset URL - `.devcontainer/Dockerfile` (via `curl`+`jq`)
- `api.github.com/repos/quietvoid/dovi_tool/releases/latest` - fetches latest `dovi_tool` static musl binary - `.devcontainer/Dockerfile`
- Auth: none (unauthenticated public API calls, subject to GitHub's anonymous rate limits)
- These calls happen only during `docker build` of the devcontainer image; no runtime dependency on GitHub.

**None at application runtime.** `legacy/scene_detection.py` and
`legacy/encode_scenes.py` never make HTTP requests, use no HTTP client
library, and have no API keys or tokens anywhere in the code.

## External CLI Tools (process-level integrations)

These are the actual "integrations" of this codebase — all invoked via
`subprocess.run`/`subprocess.Popen`, no SDK/client library wrappers:

- **ffmpeg / ffprobe** - video decode (QSV hardware-accelerated), downscale (`vpp_qsv` GPU filter), audio transcode, metadata probing
  - Invoked in: `legacy/scene_detection.py::probe_source`, `QsvPipeStream._build_command`, `keyframes_in_window`; `legacy/encode_scenes.py::probe_fps`, `keyframe_table_ffprobe`, `detect_hdr`, `encode_audio`, `count_frames`
  - Requires: `LIBVA_DRIVER_NAME=iHD` env var + `/dev/dri` GPU device access for QSV path
- **qsvencc** (Rigaya QSVEnc) - AV1 hardware encode per scene chunk, HDR10/Dolby Vision metadata passthrough (`--master-display copy`, `--dhdr10-info copy`, `--dolby-vision-rpu copy`)
  - Invoked in: `legacy/encode_scenes.py::chunk_command`, `encode_chunk`
  - Requires: Intel Arc GPU (`--avhw --va` flags select hardware accel)
- **mkvmerge** (mkvtoolnix) - final container mux (video + audio + subs/chapters/attachments carried over from source)
  - Invoked in: `legacy/encode_scenes.py::main`
- **dovi_tool** - installed in the devcontainer image but **not called by any code in `legacy/`** — Dolby Vision RPU handling is instead delegated entirely to `qsvencc`'s built-in `--dolby-vision-rpu copy` flag. This tool is effectively a dead/unused dependency in the current implementation.
- All tool availability is verified defensively at script start: `legacy/encode_scenes.py::main` checks `shutil.which()` for `qsvencc`, `ffprobe`, `ffmpeg`, `mkvmerge` and calls `die()` if any are missing.

## Data Storage

**Databases:**
- None. No ORM, no DB client, no connection strings anywhere in the codebase.

**File Storage:**
- Local filesystem only. Two host directories are bind-mounted into the devcontainer (`.devcontainer/devcontainer.json`):
  - `/data/media` (source: `/data/media` on host)
  - `/data/downloads` (source: `/data/downloads` on host)
- Working/intermediate files (scene chunks `.obu`, concatenated `movie.obu`, `audio.mka`, metrics `.csv`) are written to a per-run `<output>.chunks/` directory next to the output file (`legacy/encode_scenes.py::main`), cleaned up after successful mux unless `--keep` is passed.
- Scene detection output is a plain text file (`<video>.scenes` by default), parsed via regex (`legacy/encode_scenes.py::read_scenes`, pattern `frames \[(\d+), (\d+)\)`) — this text file is the sole interchange format between the two pipeline stages.

**Caching:**
- None explicit in code. `PIPELINE_DESIGN.md` discusses relying on the **host OS/ZFS page cache (ARC)** being warmed by a sequential full-file read during scene detection so the subsequent encode stage can read from RAM instead of disk — this is an *operational* effect of the OS/filesystem, not an integration the code manages.

## Authentication & Identity

**Auth Provider:**
- None. No login, no user accounts, no API keys for the pipeline itself. This is a local single-user CLI toolchain.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Bugsnag/etc.). Errors surface as Python exceptions (`SceneDetectionError` in `legacy/scene_detection.py`) or via `die()` → `sys.exit(msg)` in `legacy/encode_scenes.py`.

**Logs:**
- Plain `print()`-based logging to stdout with elapsed-time-since-start prefixes: `legacy/encode_scenes.py::log()` (`[{elapsed:8.1f}s] {msg}`) and a `step()` context manager that logs start/success of named operations.
- No structured logging, no log files, no log shipping.

## CI/CD & Deployment

**Hosting:**
- None — not a deployed service. Runs on a local/NAS machine with Intel Arc GPU hardware, invoked manually or by external scheduling (not part of this repo).

**CI Pipeline:**
- None detected. No `.github/workflows/`, no other CI config files anywhere in the repository.

## Environment Configuration

**Required env vars (all optional, with defaults — see STACK.md Configuration section for full list):**
- `ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY` - `legacy/encode_scenes.py` encode tuning knobs
- `LIBVA_DRIVER_NAME` - set at container level (`.devcontainer/devcontainer.json`), selects the `iHD` VA-API driver for the Intel Arc GPU

**Secrets location:**
- None present in the repo. `.gitignore` proactively excludes `.env*`, `.envrc`, and Python virtualenv directories, but no secret-bearing files currently exist. No API keys, tokens, or credentials are used anywhere in this codebase.

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None.

---

## Planned / Not Implemented (per `PIPELINE_DESIGN.md`)

No new external integrations are proposed by the design document. The
proposed streaming pipeline is purely an **in-process** restructuring
(`queue.Queue` between a detection thread and an encode thread pool within
the same Python process) — it introduces no new external service, API, or
data store. It does rely more explicitly on OS/ZFS page-cache behavior as
an implicit "integration" with the storage layer, discussed at length in the
design doc's contention analysis (sequential disk read pattern vs. seek-heavy
concurrent read pattern).

---

*Integration audit: 2026-07-08*
