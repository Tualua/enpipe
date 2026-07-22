# Quick Task 260722-lxs: Dev/debug apt-utilities layer Summary

Added a curated, dedicated apt layer to the devcontainer image
(`skopeo`, `strace`, `ripgrep`, `xxd`, `mediainfo`, `intel-gpu-tools`,
`hyperfine`, `p7zip-full`), each justified by a specific pain point from
today's Intel Arc QSV/media debugging session, plus a terse presence
self-check for each tool's binary in `post-create.sh`.

## What Was Done

### Task 1: Dedicated apt-layer for dev/debug utilities (Dockerfile)

- Added one new `RUN apt-get update && apt-get install -y
  --no-install-recommends ... && rm -rf /var/lib/apt/lists/*` layer in
  `.devcontainer/Dockerfile`, placed between the existing "Инструменты,
  которых нет в dlstreamer" (media-tools) block and the qsvencc install
  block — so changing this utility list invalidates neither the
  media-tools layer above nor the heavy qsvencc build layer below.
- Installed exactly the 8 planned packages: `skopeo`, `strace`,
  `ripgrep`, `xxd`, `mediainfo`, `intel-gpu-tools`, `hyperfine`,
  `p7zip-full`.
- Added a Russian banner comment (`# --- Dev/debug-утилиты ... ---`)
  and one Russian WHY-comment per package, each tied to a concrete pain
  point from today's debugging (OCI image inspection via skopeo instead
  of manual registry-API calls, `strace`/`LD_DEBUG` dlopen tracing of
  `libmfx-gen`, `rg` vs slow grep/awk over the QSVEnc C++ tree, `xxd`
  for hex-inspecting a malformed VMAF CSV, `mediainfo` complementing
  `ffprobe`, `intel_gpu_top` for GPU-engine load visibility during
  concurrent-encode stress tests, `hyperfine` for reproducible
  fps/wall-time benchmarking, `7z` matching QSVEnc's own CI hashing
  usage).
- Added a defensive note that all 8 packages are in Ubuntu 24.04
  main/universe, universe is enabled by default on this base image, and
  the fallback if it's ever disabled is `add-apt-repository universe`
  (explicitly not adding `software-properties-common` preemptively).
- Left the media-tools, qsvencc, dovi_tool, and podman-fix blocks
  untouched.

### Task 2: Terse self-check block (post-create.sh)

- Extended the "4) Самопроверка окружения" section in
  `.devcontainer/post-create.sh` with a one-line-per-tool presence
  report for the 8 new binaries: `rg`, `skopeo`, `strace`, `mediainfo`,
  `intel_gpu_top`, `hyperfine`, `xxd`, `7z`.
- Matched the existing check style: `printf "  name:  "; command -v X
  >/dev/null && ... || echo "НЕТ"`, using `--version`/`-V` output
  (`head -1`) where a cheap version flag exists, and a plain
  "установлен" for `xxd`, `intel_gpu_top`, `7z` where it doesn't.
- Inserted the block after the `scenedetect` check and before the
  `node/npm` check, with a short Russian subheading ("dev/debug-утилиты:").
- Did not touch the GPU-permission logic, `uv sync`, or npm/Claude-plugin
  blocks.

## Deviations from Plan

None — plan executed exactly as written. Both files changed exactly as
specified; no other files were modified or staged.

## Verification Performed

- `bash -n .devcontainer/post-create.sh` → passed (no output, exit 0).
- `grep -nE 'skopeo|strace|ripgrep|xxd|mediainfo|intel-gpu-tools|hyperfine|p7zip-full' .devcontainer/Dockerfile`
  → all 8 packages found in the single new RUN block (lines 43-69 of the
  new layer), each with its WHY-comment line above the RUN command.
- `grep -nE 'rg|skopeo|strace|mediainfo|intel_gpu_top|hyperfine|xxd|7z' .devcontainer/post-create.sh`
  → all 8 new self-check lines present.
- `git diff` reviewed manually to confirm placement (new layer sits
  between the media-tools block and the qsvencc block) and that no
  other blocks were altered.

**What was NOT verified (cannot be, in this environment):** the image
was NOT built and the tools were NOT actually confirmed present/working
at runtime — there is no Docker/Podman or GPU access in this execution
environment. **The user must rebuild the devcontainer on the host** for
`skopeo`, `strace`, `rg`, `xxd`, `mediainfo`, `intel_gpu_top`,
`hyperfine`, and `7z` to actually become available, and should run
`post-create.sh` (or just open the rebuilt devcontainer, which runs it
automatically) to see the new self-check block report each tool's
presence.

## Self-Check: PASSED

- FOUND: `.devcontainer/Dockerfile` (modified, new RUN layer present)
- FOUND: `.devcontainer/post-create.sh` (modified, new self-check lines present)
- FOUND commit `e1c9322` (`feat(devcontainer): add curated dev/debug apt-utilities layer`) in `git log --oneline`
