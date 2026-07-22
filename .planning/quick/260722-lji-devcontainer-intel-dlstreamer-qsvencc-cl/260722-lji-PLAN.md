---
phase: quick-260722-lji
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .devcontainer/Dockerfile
  - .devcontainer/devcontainer.json
  - .devcontainer/post-create.sh
autonomous: true
requirements: [DEVENV-BASE-MIGRATION]
must_haves:
  truths:
    - "Dockerfile builds FROM intel/dlstreamer (Ubuntu 24.04), not the Debian trixie python image"
    - "The manual Intel media-driver stack and ffmpeg apt install are gone (provided by dlstreamer)"
    - "qsvencc (Rigaya, ubuntu-24.04 amd64 .deb) installs via the dep-strip approach (libmfx1 + intel-opencl-icd removed from control)"
    - "dovi_tool, mkvtoolnix, tmux, vainfo, ocl-icd-libopencl1, python3+venv+pip are present (defensively installed where dlstreamer may not guarantee them)"
    - "Proxy ENV block, DEBIAN_FRONTEND, and the apt-sandbox fix are preserved verbatim"
    - "devcontainer.json keeps features, runArgs (incl. commented --userns=keep-id fallback), /data mounts, LIBVA_DRIVER_NAME=iHD, postCreate, remoteUser:root"
  artifacts:
    - path: ".devcontainer/Dockerfile"
      provides: "dlstreamer-based image recipe with qsvencc/dovi_tool/mkvtoolnix/tmux"
      contains: "intel/dlstreamer"
    - path: ".devcontainer/devcontainer.json"
      provides: "devcontainer config referencing the rebuilt Dockerfile"
      contains: "\"dockerfile\": \"Dockerfile\""
  key_links:
    - from: ".devcontainer/devcontainer.json"
      to: ".devcontainer/Dockerfile"
      via: "build.dockerfile reference"
      pattern: "dockerfile"
    - from: ".devcontainer/devcontainer.json"
      to: ".devcontainer/post-create.sh"
      via: "postCreateCommand"
      pattern: "post-create.sh"
---

<objective>
Migrate the enpipe devcontainer base image from `mcr.microsoft.com/devcontainers/python:3-3.12-trixie`
(Debian 13 + hand-built Intel media stack) to `intel/dlstreamer` (Ubuntu 24.04), which ships a fresh
Intel media stack (iHD 26.2.2 + oneVPL/vpl-gpu-rt + ffmpeg-with-QSV) with the image. All current dev
capabilities are preserved: qsvencc (Rigaya), dovi_tool, mkvmerge, tmux, vainfo, Python 3.12 + uv,
node, claude-code, opencode, qwen, and the GSD plugin.

Purpose: Get a fresher, better-supported Arc AV1 media stack (media comes WITH the base image instead
of being reconstructed from Debian non-free packages), reducing the driver-patching surface.

Output: Rewritten `.devcontainer/Dockerfile`, updated `.devcontainer/devcontainer.json` header/comments,
and a reviewed (likely unchanged) `.devcontainer/post-create.sh`.

CANNOT be runtime-verified here: this config cannot be built or GPU-tested inside the current running
container. `docker`/`podman` are not available in this environment. All `verify` steps below are STATIC
(grep/lint of the authored files). Runtime success is confirmed ONLY by the host rebuild checklist at
the bottom, which the USER runs on the NAS.
</objective>

<execution_context>
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.2.0/workflows/execute-plan.md
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.2.0/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.devcontainer/Dockerfile
@.devcontainer/devcontainer.json
@.devcontainer/post-create.sh
@CLAUDE.md

<notes>
- In-code prose (comments) stay RUSSIAN, matching the existing Dockerfile/post-create.sh style — they
  explain WHY, not WHAT. Code/identifiers stay English.
- The current Dockerfile qsvencc dep-strip awk block and the dovi_tool install RUN block already work
  and are base-agnostic; carry them over essentially unchanged (only the surrounding rationale comment
  and the .deb asset selection note change).
- devcontainer.json is JSONC (contains `//` comments) — do NOT run a strict JSON parser over it; verify
  with grep for preserved keys/comments instead.
</notes>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite the Dockerfile onto intel/dlstreamer</name>
  <files>.devcontainer/Dockerfile</files>
  <action>
Rewrite `.devcontainer/Dockerfile` to base on Intel DL Streamer instead of the Debian python image.
Keep all Russian rationale comments in the existing WHY-not-WHAT style.

1. Header comment: replace the "почему trixie/glibc" rationale with a "почему dlstreamer" rationale —
   media-стек (iHD 26.2.2 + oneVPL/vpl-gpu-rt + ffmpeg с QSV) поставляется ВМЕСТЕ с образом, свежий
   iHD/oneVPL для Arc AV1, меньше ручного патчинга драйверов. Note that qsvencc/dovi_tool/mkvtoolnix/tmux
   are still added on top because dlstreamer does not ship them.

2. Base image: `FROM intel/dlstreamer:latest`. Add a Russian comment above it noting the tag can be
   pinned to a specific weekly build (пример: `2026.2.0-YYYYMMDD-weekly-ubuntu24`) for reproducibility.

3. PRESERVE VERBATIM immediately after FROM: the proxy ENV block
   (`ENV IS_SANDBOX=1`, `HTTPS_PROXY`/`HTTP_PROXY`/`http_proxy`/`https_proxy` = http://10.224.30.233:20171)
   and `ENV DEBIAN_FRONTEND=noninteractive`.

4. REMOVE the Debian non-free/contrib sources-enable RUN block (deb822 sed) — Ubuntu 24.04 base, not
   needed; the Intel media packages it enabled now come from the base image.

5. REPLACE the "Intel Media + ffmpeg + mkvtoolnix" apt RUN: drop `intel-media-va-driver-non-free`,
   `libva2`, `libva-drm2`, `libvpl2`, `ffmpeg`, and the `libmfx-gen*` name-probe loop entirely
   (all provided by dlstreamer). Keep a single defensive `apt-get install -y --no-install-recommends`
   for the tools dlstreamer may not guarantee: `ca-certificates curl gnupg jq xz-utils tmux
   mkvtoolnix vainfo ocl-icd-libopencl1 python3 python3-venv python3-pip`. Add a Russian comment:
   базовый медиа-стек (iHD/oneVPL/ffmpeg-QSV) уже в dlstreamer — тут только то, чего в нём нет;
   `vainfo`/`ocl-icd-libopencl1`/`python3*` ставим оборонительно (`--no-install-recommends`, безвредно
   если уже есть). Note ocl-icd-libopencl1 is the OpenCL loader qsvencc links (libOpenCL.so.1 for VPP)
   and Ubuntu 24.04 python3 = 3.12 (needed by uv in post-create). End with `rm -rf /var/lib/apt/lists/*`.

6. KEEP the qsvencc RUN block (dep-strip approach) essentially as-is. Update its Russian comment to say
   the base is now Ubuntu 24.04 so the ubuntu-24.04 .deb is a native match (no glibc-cross-distro note
   needed). Confirm the asset selector still picks the ubuntu-24.04 `_amd64.deb` — the existing
   `select(test("_amd64.deb$")) | head -1` already targets the amd64 .deb; add a Russian comment that if
   Rigaya ships multiple distro .debs we want the Ubuntu 24.04 one (tighten the jq filter to
   `select(test("Ubuntu24.04_amd64.deb$"))` if the release has per-distro assets, else fall back to the
   generic `_amd64.deb$` match). Keep stripping BOTH `libmfx1` and `intel-opencl-icd` from control so
   apt resolves real deps; the OpenCL loader is installed separately in step 5.

7. KEEP the dovi_tool RUN block (static musl binary) UNCHANGED including its full DEBT-04 rationale
   comment (still valid — dovi_tool retained for planned Phase-4 DV RPU work, AV1 extract-rpu not
   confirmed).

8. KEEP the apt-sandbox fix as the LAST RUN block VERBATIM
   (`echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/00-no-apt-sandbox && chmod 1777 /tmp`) —
   devcontainer features (node) run apt during image finalization and need it. Its Russian comment stays.
  </action>
  <verify>
Static checks only (no build here). All must pass:
`grep -q '^FROM intel/dlstreamer' .devcontainer/Dockerfile`
`grep -qi 'weekly-ubuntu24' .devcontainer/Dockerfile` (pin-note present)
`! grep -q 'intel-media-va-driver-non-free' .devcontainer/Dockerfile` (removed)
`! grep -Eq 'libmfx-gen1' .devcontainer/Dockerfile` (name-probe loop removed)
`! grep -Eq '(^| )ffmpeg( |$)' .devcontainer/Dockerfile` (ffmpeg install removed)
`grep -q 'IS_SANDBOX=1' .devcontainer/Dockerfile && grep -q '10.224.30.233:20171' .devcontainer/Dockerfile` (proxy preserved)
`grep -q 'DEBIAN_FRONTEND=noninteractive' .devcontainer/Dockerfile`
`grep -q 'APT::Sandbox::User' .devcontainer/Dockerfile && grep -q 'chmod 1777 /tmp' .devcontainer/Dockerfile` (apt-sandbox fix preserved)
`grep -q 'ocl-icd-libopencl1' .devcontainer/Dockerfile && grep -q 'vainfo' .devcontainer/Dockerfile && grep -q 'mkvtoolnix' .devcontainer/Dockerfile && grep -q 'tmux' .devcontainer/Dockerfile && grep -q 'python3-venv' .devcontainer/Dockerfile` (kept tools)
`grep -q 'intel-opencl-icd' .devcontainer/Dockerfile && grep -q 'libmfx1' .devcontainer/Dockerfile` (both still stripped in qsvencc control edit)
`grep -q 'dovi_tool' .devcontainer/Dockerfile && grep -q 'DEBT-04' .devcontainer/Dockerfile` (dovi_tool + rationale kept)
  </verify>
  <done>
Dockerfile builds FROM intel/dlstreamer with a weekly-tag pin note; the manual Intel media driver stack
and ffmpeg install are removed; qsvencc dep-strip (both libmfx1 + intel-opencl-icd) and dovi_tool blocks
are retained; defensive installs cover vainfo/ocl-icd/python3*/mkvtoolnix/tmux; proxy ENV, DEBIAN_FRONTEND,
and the apt-sandbox fix are preserved verbatim; all Russian rationale comments updated/kept. All static
grep checks pass.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update devcontainer.json header + confirm post-create.sh is base-agnostic</name>
  <files>.devcontainer/devcontainer.json, .devcontainer/post-create.sh</files>
  <action>
devcontainer.json — make ONLY cosmetic/header changes; preserve all functional config:
1. Update the top `name` and any base-referencing comments to reflect the dlstreamer/Ubuntu 24.04 base
   (e.g. name → "encode-scripts — Arc QSV AV1 (dlstreamer/Ubuntu 24.04)"). Update the Russian comment
   under `features` that currently says "уже в базовом python-образе" — on Ubuntu 24.04 base the
   node/claude-code features still apply, and there is NO default `vscode` user, but `remoteUser` is
   `root` and nothing depends on a `vscode` user, so no user-creation is needed. Note this in a short
   Russian comment so a future reader does not add a user-creation feature.
2. PRESERVE UNCHANGED: `"build": { "dockerfile": "Dockerfile" }`; both `features`
   (node:2 lts, claude-code:1); all `runArgs` INCLUDING the commented `--userns=keep-id` fallback block
   and its full Russian explanation; the two `/data` `mounts`; `containerEnv.LIBVA_DRIVER_NAME=iHD`;
   `postCreateCommand`; the vscode extensions; `remoteUser: root`.

post-create.sh — review, expect no functional change:
3. Confirm every step is base-agnostic (GPU render-group via stat/getent/usermod, npm globals,
   claude gsd plugin, uv sync --locked, self-checks). All use tools present on the new base or
   installed by it. `sudo` is used in the GPU step — Ubuntu 24.04 + running as root means `sudo` may
   be absent; since `remoteUser` is `root`, prefer to keep the script working under root. If `sudo` is
   not guaranteed, make the three GPU-group commands tolerate its absence (e.g. run them directly when
   already root / `command -v sudo`). Add a short Russian comment explaining the root/sudo guard. Make
   NO other changes — the self-checks (vainfo AV1 profiles, ffmpeg av1_qsv, qsvencc/dovi_tool/mkvmerge/
   tmux/node/claude/opencode/qwen/GSD, /data write) remain valid and useful on the new base.
  </action>
  <verify>
Static checks only:
`grep -q '"dockerfile": "Dockerfile"' .devcontainer/devcontainer.json` (build ref preserved)
`grep -q 'userns=keep-id' .devcontainer/devcontainer.json` (commented fallback preserved)
`grep -q 'LIBVA_DRIVER_NAME' .devcontainer/devcontainer.json && grep -q 'iHD' .devcontainer/devcontainer.json`
`grep -q 'keep-groups' .devcontainer/devcontainer.json && grep -q '/data/media' .devcontainer/devcontainer.json && grep -q '/data/downloads' .devcontainer/devcontainer.json`
`grep -q '"remoteUser": "root"' .devcontainer/devcontainer.json`
`grep -q 'post-create.sh' .devcontainer/devcontainer.json`
JSONC comment-strip parse (tolerates // comments):
`python3 -c "import json,re,sys; s=open('.devcontainer/devcontainer.json').read(); s=re.sub(r'(?m)^\s*//.*$','',s); s=re.sub(r'(?<=[\s,{\[])//.*$','',s,flags=re.M); json.loads(s); print('json-ok')"`
Shell syntax check: `bash -n .devcontainer/post-create.sh`
  </verify>
  <done>
devcontainer.json name/comments reflect the dlstreamer base and note no vscode-user dependency; all
functional config (build ref, features, runArgs incl. commented userns fallback, /data mounts,
LIBVA_DRIVER_NAME=iHD, postCreate, remoteUser:root) preserved and parses as JSONC; post-create.sh
reviewed, sudo/root-guarded on the GPU step if needed, self-checks intact, `bash -n` clean.
  </done>
</task>

</tasks>

<verification>
All verification here is STATIC (file lint/grep + JSONC parse + `bash -n`). This environment has no
`docker`/`podman` and no `/dev/dri` build capability, so image build and GPU function CANNOT be
verified here. Runtime correctness is confirmed exclusively by the host rebuild checklist below.
</verification>

<success_criteria>
- Dockerfile: `FROM intel/dlstreamer` with weekly-tag pin note; media-driver stack + ffmpeg removed;
  qsvencc dep-strip (libmfx1 + intel-opencl-icd) and dovi_tool blocks retained; defensive tool installs
  present; proxy ENV / DEBIAN_FRONTEND / apt-sandbox fix preserved verbatim; Russian rationale updated.
- devcontainer.json: header updated; all functional config preserved; parses as JSONC.
- post-create.sh: base-agnostic, root/sudo-guarded, `bash -n` clean, self-checks intact.
- No claim of runtime success — host must rebuild and run the checklist.
</success_criteria>

## Host rebuild & verify checklist (USER runs on the NAS — CANNOT be done here)

This config change is only truly verified by rebuilding the devcontainer on the Arc host. After merging,
on the NAS host:

1. Rebuild the devcontainer (fresh image, no cache):
   `devcontainer up --workspace-folder . --remove-existing-container`
   (or VS Code: "Dev Containers: Rebuild Without Cache"). Confirm the image pulls `intel/dlstreamer`
   and the build reaches the apt-sandbox-fix layer without the node feature failing on unsigned repos.
2. Inside the rebuilt container, confirm the media stack (now from dlstreamer):
   - `vainfo` → shows Driver version (iHD, expect ~26.2.x) and lists `VAProfileAV1Profile0` (AV1) and
     `VAProfileHEVCMain10`.
   - `ffmpeg -hide_banner -encoders | grep -iE 'av1_qsv|hevc_qsv'` → both present.
3. Confirm the tools added on top of dlstreamer:
   - `qsvencc --version` → prints a version (QSVEnc, Rigaya) and it actually runs (glibc OK on Ubuntu 24.04).
   - `dovi_tool --version`, `mkvmerge --version`, `tmux -V` → all present.
4. Confirm the dev-agent toolchain (features + post-create):
   - `node -v` / `npm -v`; `claude --version`; `opencode --version`; `qwen --version`.
   - `claude plugin list | grep -i gsd` → GSD plugin installed.
5. Confirm Python + project deps:
   - `python3 --version` → 3.12.x; `uv --version`; `uv sync --locked` succeeds; `python3 -c "import scenedetect; print(scenedetect.__version__)"`.
6. Confirm GPU + /data access (the runArgs/mount concern):
   - `ls -l /dev/dri/renderD128` visible; post-create GPU-group step ran without fatal error.
   - `/data/media` and `/data/downloads` mounted; write test:
     `touch /data/media/.enpipe-write-test && rm /data/media/.enpipe-write-test` succeeds. If EACCES,
     apply the commented `--userns=keep-id` runArgs fallback and rebuild (see devcontainer.json).
7. Optional end-to-end smoke: run a short `enpipe run` (or `qsvencc`) AV1 encode on a small clip and
   confirm it completes and the frame-count guard passes — this is the real proof the Arc AV1 path works
   on the new base.

If any of steps 2–3 fail (missing AV1 profile, no av1_qsv, qsvencc won't run), the dlstreamer base media
stack or the qsvencc .deb asset selection needs revisiting before relying on this container for encodes.

<output>
Create `.planning/quick/260722-lji-devcontainer-intel-dlstreamer-qsvencc-cl/260722-lji-SUMMARY.md` when done.
</output>
