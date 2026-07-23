---
status: fix-applied-pending-rebuild
trigger: "не могу создавать файлы и папки в /data/{downloads,media} из devcontainer"
created: 2026-07-21
updated: 2026-07-21
---

# Debug: cannot create files/dirs in /data/{downloads,media} from devcontainer

## Symptoms
- Expected: `vscode` user inside the devcontainer can create files/dirs under `/data/downloads` and `/data/media` (host bind mounts).
- Actual: `touch` and `mkdir` fail with `Permission denied` (EACCES) in both directories.
- Reproduction: `touch /data/downloads/x` or `mkdir /data/media/y` from inside the running devcontainer.

## Current Focus
- hypothesis: Rootless Podman user-namespace ID mapping — the host-side owner of the ZFS
  datasets does not map to the container `vscode` user, and Podman does not honor the
  container's supplementary `nogroup` membership on the host, so group-write is not applied.
- next_action: Choose host-side fix (keep-groups / chown / userns keep-id) and rebuild.

## Evidence
- timestamp 2026-07-21: `id` → container user `vscode` uid=1010 gid=1011, supplementary groups incl. 65534(nogroup).
- timestamp 2026-07-21: `/data/downloads` = `drwxrwsr-x.` owner 65534 group 65534; `/data/media` = `drwxrwsr-x+` owner 65534 group 65534 (setgid bit set; media has a POSIX ACL `+`).
- timestamp 2026-07-21: write tests → `touch`/`mkdir` in both dirs return `Permission denied` (EACCES, not EROFS).
- timestamp 2026-07-21: mount is read-write ZFS: `/proc/self/mountinfo` → `zfs data/downloads rw,...posixacl` and `zfs data/media rw,...posixacl`. Rules out read-only mount.
- timestamp 2026-07-21: runtime is rootless Podman — `container=podman`, `/run/.containerenv` exists, `/.dockerenv` absent.
- timestamp 2026-07-21: `/proc/self/uid_map` = `0 1 1010 / 1010 0 1 / 1011 1011 64526` → container uid 1010 (vscode) maps to host uid 0. gid_map similarly maps container gid 1011 → host gid 0.
- timestamp 2026-07-21: dirs owned by inside-id 65534 = overflow/unmapped id → host owner is not represented in the container's mapping as vscode.
- timestamp 2026-07-21: existing `.parts` files under downloads owned by inside-uid 1010 (= host root), i.e. created by a host-root/NAS process, not by this vscode user.

## Eliminated
- hypothesis: read-only bind mount. Eliminated — mountinfo shows `rw`, and the error is EACCES not EROFS.
- hypothesis: simple missing group-write bit. Eliminated — dirs already grant group `rwx` and
  vscode is in group 65534; the real gap is Podman not passing supplementary groups to the host.

## Resolution (root cause; fix pending user choice — requires host-side action + rebuild)
- root_cause: Rootless Podman user-namespace ID mapping. The host-owned ZFS datasets
  (`/data/downloads`, `/data/media`) are owned by a host UID/GID that does not map to the
  container `vscode` user (inside uid 1010 → host uid 0), so the kernel denies writes with
  EACCES. The directories' group-write bit does not help because rootless Podman does not, by
  default, carry the container's supplementary group (`nogroup`/65534) into the host-side
  process credentials.
- candidate fixes:
  1. Podman `--group-add keep-groups` (crun annotation `run.oci.keep_original_groups=1`) via
     devcontainer.json `runArgs` — most surgical; makes the existing group-`rwx` bit apply.
  2. `--userns=keep-id[:uid=<n>,gid=<n>]` in `runArgs` so vscode maps to the data-owning host user.
  3. Host-side `chown`/`setfacl` on the ZFS datasets to grant the container-mapped uid/gid write.
- chosen fix: option 1 — `--group-add keep-groups` added to `.devcontainer/devcontainer.json` runArgs.
- OPEN DISCREPANCY: user believes /data is owned by host user `dsp` (uid 1000), but inside the
  container /data/* shows owner `65534:65534`, which per the gid_map maps to HOST 65534 =
  `nobody:nogroup` — NOT dsp. If /data were dsp-owned (host 1000:1000) it would appear as 999:999
  inside. So keep-groups only grants write if host user `dsp` is a MEMBER of the owning group
  (host gid 65534 / `nogroup`). Must verify on host: `id dsp` → look for group 65534/nogroup.
  If absent: `sudo usermod -aG nogroup dsp` (or chown the datasets to a dsp-writable group).
- verification (pending): rebuild container, re-run `touch`/`mkdir` in both `/data/downloads`
  and `/data/media` → expect success.
- files_changed: .devcontainer/devcontainer.json (added "--group-add", "keep-groups" to runArgs;
  documented `--userns=keep-id` / `keep-id:uid=1010,gid=1011` fallback as an in-place comment).
