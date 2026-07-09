---
phase: 260709-hq2
plan: 01
subsystem: infra
tags: [github-actions, docker, ghcr, buildkit, ci-cd]

# Dependency graph
requires:
  - phase: 260709-gs0
    provides: "Slim multi-stage runtime Dockerfile (root Dockerfile) that this workflow now builds and publishes"
provides:
  - "GHCR build-and-publish GitHub Actions workflow (.github/workflows/docker-publish.yml) triggered on v* tags + workflow_dispatch"
  - "Optional BuildKit-secret GitHub API auth in the Dockerfile's two GitHub-release download RUN blocks (qsvencc, dovi_tool)"
  - "docker/README.md CI/publication documentation + local --secret usage note"
affects: [docker-image-release-process]

# Tech tracking
tech-stack:
  added: [docker/setup-buildx-action, docker/login-action, docker/metadata-action, docker/build-push-action]
  patterns: ["Digest-pinned third-party GitHub Actions with a trailing # vX.Y.Z comment (mirrors ci.yml's astral-sh/setup-uv pin)", "POSIX set --/\"$@\" positional-param pattern for optional CLI flags under /bin/sh (no bash arrays)", "BuildKit --mount=type=secret,required=false for optional build-time credentials that must not land in ARG/ENV or image layers"]

key-files:
  created:
    - .github/workflows/docker-publish.yml
  modified:
    - Dockerfile
    - docker/README.md

key-decisions:
  - "Resolved all four docker/* action commit SHAs live via https://api.github.com (curl worked in this environment, gh CLI unavailable/unauthenticated) rather than fabricating pins: setup-buildx-action@bb05f3f v4.2.0, login-action@af1e73f v4.4.0, metadata-action@dc80280 v6.2.0, build-push-action@53b7df9 v7.3.0"
  - "platforms: linux/amd64 only in build-push-action — qsvencc/Intel Arc media stack has no arm64 build upstream"
  - "actions/checkout kept on @v7 tag (first-party, unpinned by digest) to exactly mirror ci.yml/hardware-integration.yml convention"
  - "metadata-action tags include type=sha alongside semver/latest so a tagless workflow_dispatch run still produces an identifiable, pushable tag"

patterns-established:
  - "Optional BuildKit secret + POSIX conditional auth header pattern for any future Dockerfile RUN block that hits a rate-limited external API"

requirements-completed: [QUICK-260709-hq2]

# Metrics
duration: 15min
completed: 2026-07-09
---

# Quick Task 260709-hq2: GitHub Actions GHCR Build & Publish Workflow Summary

**New `.github/workflows/docker-publish.yml` builds and pushes the slim runtime image to `ghcr.io/tualua/enpipe` on `v*` tags / manual dispatch, with all four `docker/*` actions pinned by live-resolved commit SHA and an optional `required=false` BuildKit secret carrying GitHub-API auth into the Dockerfile's two release-download RUN blocks.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-09T12:37:00Z (approx.)
- **Completed:** 2026-07-09T12:53:20Z
- **Tasks:** 3/3
- **Files modified:** 3 (1 created, 2 edited)

## Accomplishments
- New GHCR publish workflow: `push: tags: v*` + `workflow_dispatch`, `permissions: contents: read, packages: write`, no extra secrets beyond built-in `GITHUB_TOKEN`.
- All four `docker/*` actions (`setup-buildx-action`, `login-action`, `metadata-action`, `build-push-action`) pinned by real, freshly-resolved 40-hex commit SHA (not guessed) — verified each against `api.github.com/repos/<owner>/<repo>/git/ref/tags/<tag>`.
- Dockerfile's qsvencc and dovi_tool GitHub-release download blocks now accept an optional `--mount=type=secret,id=github_token,required=false`, feeding an `Authorization: Bearer` header into both curls per block via POSIX `set --`/`"$@"` (no bash arrays — RUN shell is dash). Token-less builds are behaviorally unchanged.
- `docker/README.md` documents the GHCR publish flow, `docker pull` example, and the local `--secret id=github_token` BuildKit invocation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the GHCR build-and-publish workflow** - `667703b` (feat)
2. **Task 2: Add optional BuildKit-secret GitHub API auth to the two release-download RUN blocks** - `7297a3c` (feat)
3. **Task 3: Document CI publication + local BuildKit-secret usage in docker/README.md** - `6b5057e` (docs)

**Plan metadata:** (this commit, made separately per protocol — see final commit below)

## Files Created/Modified
- `.github/workflows/docker-publish.yml` - New workflow: checkout, setup-buildx, GHCR login, metadata (semver/major.minor/latest/sha tags), build-push (linux/amd64, gha cache, `secrets: github_token`)
- `Dockerfile` - Two RUN blocks (qsvencc `.deb` download, dovi_tool musl tarball download) gained `--mount=type=secret,id=github_token,required=false` + POSIX conditional `Authorization: Bearer` header on both curls per block; all other logic (jq select, dpkg-deb repack, install, cleanup) untouched
- `docker/README.md` - New "## CI / публикация" section: GHCR image path, pull example, GITHUB_TOKEN note, local `--secret id=github_token` BuildKit usage

## Decisions Made
- Digest resolution done via direct `curl https://api.github.com/...` (network reachable in this environment) rather than `gh` (not installed/authenticated) or WebFetch (no such tool available to this executor) — every SHA cross-checked against the tag's `git/ref` endpoint before use, per the plan's "do not fabricate" constraint.
- Chose the exact tag names encountered at resolution time (v4.2.0 buildx, v4.4.0 login, v6.2.0 metadata, v7.3.0 build-push) rather than the plan's approximate majors (~v3/~v3/~v5/~v6) since actual current majors were higher; SHAs are real and verified regardless of major-version drift from the plan's rough estimate.
- Kept the auth rationale comment (unauthenticated 60 req/hour, 5000/hour with token) in Russian directly above each RUN block, matching the file's existing Russian "why"-comment convention.

## Deviations from Plan

None - plan executed exactly as written. The plan's approximate action-version guesses (~v3/~v5/~v6) were superseded by the actual current majors found during live SHA resolution (v4.2.0/v4.4.0/v6.2.0/v7.3.0); this is expected/anticipated by the plan's own "confirm before pinning" instruction, not a deviation from process.

## Issues Encountered
None. `gh` CLI was not installed/authenticated in this environment, but direct `curl` to `api.github.com` worked, satisfying the plan's documented fallback path (WebFetch was listed as an alternative fallback but was unavailable as a tool to this executor; `curl` achieved the same verified-SHA outcome).

## User Setup Required

None - no external service configuration required. GHCR publication uses the repository's built-in `GITHUB_TOKEN`; no new secret needs to be added in repo settings.

## HONEST VERIFICATION NOTE

**The workflow was NOT run in this environment and the Docker image was NOT built.** There is no `docker`/`podman`/Actions runner here (consistent with quick task 260709-gs0's Dockerfile). What WAS verified locally:

1. `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))"` → `yaml ok`.
2. Static greps: all `docker/*` actions pinned `@<40-hex>`; `packages: write` present; `on:` has `tags: - 'v*'` and `workflow_dispatch`; Dockerfile has `--mount=type=secret,id=github_token,required=false` twice; no `auth=(` (no bash arrays).
3. Builder-stage regression: `UV_PROJECT_ENVIRONMENT=$(mktemp -d)/venv uv sync --frozen --no-dev --no-editable` into a fresh temp venv, then `enpipe --help` → exit 0. Proves the Dockerfile edits did not touch the builder stage / package install path.
4. Full existing test suite: `uv run pytest -m "not hardware" -q` → **153 passed, 6 deselected** (no source code touched, expected green).

**All four `docker/*` third-party action pins are full 40-hex commit SHAs (digest-pinned), not moving version tags** — resolved live against `api.github.com` and cross-verified via each tag's `git/ref` endpoint (`type: "commit"` confirms lightweight tag = direct commit SHA, not an annotated-tag object requiring dereference). `actions/checkout@v7` is intentionally left on a tag (first-party action, matches existing `ci.yml`/`hardware-integration.yml` convention).

**What the user must verify by pushing a real `vX.Y.Z` tag:**
- The workflow actually triggers and runs to completion on GitHub-hosted `ubuntu-latest`.
- The `docker/build-push-action` build of the root `Dockerfile` succeeds (all apt/curl/qsvencc/dovi_tool steps complete under a real BuildKit builder, not just parsed).
- The image pushes successfully to `ghcr.io/tualua/enpipe` and the `metadata-action`-generated tags (`vX.Y.Z`, `X.Y`, `latest`, `sha-<short>`) resolve as expected.
- GHCR package visibility/permissions are configured as the user wants (this workflow only pushes; it does not manage package visibility settings, which default to the repo owner's org/GHCR defaults).

## Next Phase Readiness
- Publication pipeline is code-complete and statically verified; ready for the user to push a `vX.Y.Z` tag to exercise it end-to-end on a real GitHub-hosted runner.
- No blockers. Milestone v1.1 was already complete before this quick task; this task adds a standalone CI/CD capability on top without touching pipeline code, tests, or the devcontainer.

---
*Phase: 260709-hq2*
*Completed: 2026-07-09*

## Self-Check: PASSED

- FOUND: `.github/workflows/docker-publish.yml`
- FOUND: `Dockerfile` (mount=type=secret,id=github_token present x2)
- FOUND: `docker/README.md` (ghcr.io/tualua/enpipe present)
- FOUND: `.planning/quick/260709-hq2-github-actions-workflow-to-build-and-pub/260709-hq2-SUMMARY.md`
- FOUND commit: `667703b`
- FOUND commit: `7297a3c`
- FOUND commit: `6b5057e`
