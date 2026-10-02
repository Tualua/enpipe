---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Concurrent-encode correctness
status: Ready to discuss
stopped_at: Phase 7 context gathered
last_updated: "2026-10-02T09:36:23.781Z"
last_activity: "2026-10-02 -- v1.2 re-scoped: qsvencc corruption fixed upstream (45003f1); ffmpeg migration parked as backlog 999.1"
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 12
  completed_plans: 3
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-23)

**Core value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.
**Current focus:** Phase 7 — adopt fixed qsvencc + concurrency regression lock

## Current Position

Phase: 7
Plan: Not started
Status: Ready to discuss
Last activity: 2026-10-02 -- v1.2 re-scoped: qsvencc corruption fixed upstream (45003f1); ffmpeg migration parked as backlog 999.1

## Performance Metrics

**Velocity:**

- Total plans completed: 17
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 2 | - | - |
| 3 | 3 | - | - |
| 4 | 2 | - | - |
| 5 | 1 | - | - |
| 06 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 20min | 2 tasks | 10 files |
| Phase 01 P02 | 20min | 3 tasks | 7 files |
| Phase 01 P03 | 50min | 3 tasks | 16 files |
| Phase 02 P01 | 7min | 3 tasks | 8 files |
| Phase 02 P02 | 5min | 3 tasks | 5 files |
| Phase 03 P01 | 6min | 3 tasks | 5 files |
| Phase 03 P02 | 14min | 3 tasks | 3 files |
| Phase 03 P03 | 6min | 2 tasks | 3 files |
| Phase 04 P01 | 12min | 3 tasks | 6 files |
| Phase 04 P02 | 15min | 4 tasks | 4 files |
| Phase 05 P01 | 9min | 3 tasks | 3 files |
| Phase 06 P02 | 25min | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Package scaffold + dependency pinning (Phase 1) must precede everything else — nearly all other deliverables require stable import paths
- Roadmap: Fast test tier + `shared.proc` seam (Phase 1) must exist before any refactor of correctness-critical code (EBML isolation, seek/trim extraction — Phase 2)
- Roadmap: ThreadPool-vs-ProcessPool resolution (DEBT-03) must land before the parallel==sequential regression baseline (TEST-03) is captured — both placed in Phase 3
- Roadmap: Unified CLI entry point (PKG-01) deliberately deferred to Phase 4, after both detect and encode stages are independently verified
- Roadmap (v1.1): Phase numbering continues from v1.0 (starts at Phase 5, not reset to 1)
- Roadmap (v1.1): All 4 RUN-* requirements collapsed into a single Phase 5 — coarse granularity + this is a thin sequential wrapper over already-verified v1.0 stages, not a multi-capability milestone; no natural sub-boundary to split on
- Roadmap (v1.1): Phase 5 depends only on Phase 4 (needs `run_detect`/`run_encode` + the unified CLI dispatcher to exist and be hardware-verified before wrapping them)
- Roadmap (v1.2): Phase numbering continues from v1.1 (starts at Phase 6, not reset to 1); v1.0/v1.1 groupings preserved in ROADMAP.md, v1.2 appended
- Roadmap (v1.2): Risk-first 5-phase shape from research SUMMARY adopted under coarse granularity — Phase 6 (ENV-01+COR-01) is a GATE proving ffmpeg av1_qsv immunity at production+stress JOBS with per-frame content verification BEFORE any backend code; if it fails the migration premise is invalid
- Roadmap (v1.2, 2026-10-02): RE-SCOPE — qsvencc concurrent-encode corruption fixed upstream (rigaya/QSVEnc 45003f1, issue #308: missing MFX VPP output sync before encode with VA memory), verified on our Arc A380 by the user (co-author of the fix). ffmpeg migration (former Phases 7–10, BK/FF/HDR reqs) parked as backlog 999.1; new Phase 7 = adopt fixed qsvencc + concurrency regression lock (QSV-01, QSV-02, COR-02). Decisions below about Phases 7–10 are superseded.
- Roadmap (v1.2): Refactor-before-feature — Phase 7 (BK-02) lands the `backends/` seam validated byte-identical vs the legacy oracle (qsvencc-only) before Phase 8 adds ffmpeg encode code
- Roadmap (v1.2): SDR→HDR→DV ordering — Phase 8 (FF-01/02/03 + BK-01 default flip) carries the load-bearing invariants; Phase 9 (HDR-01) is solved-but-relocated (encoder→mkvmerge tags); Phase 10 (HDR-03+HDR-02) is the POC-gated highest-risk DV/HDR10+ decision, deferred last so it cannot block core value
- Roadmap (v1.2): BK-01 maps to Phase 8 (requirement = ffmpeg default realized), though its `--backend` flag scaffold is stubbed in Phase 7
- Roadmap (v1.2): v1.2 correctness basis is per-frame CONTENT parity (PSNR/VMAF) + quality/size band, NOT byte-identity to qsvencc (ICQ-23 ≠ av1_qsv "23"); `legacy/` stays the frozen parity oracle throughout
- Roadmap (v1.2): Phases 6 (concurrency methodology) and 10 (DV/HDR10+) flagged for deeper per-phase research at plan time; Phases 7/8/9 are standard patterns
- [Phase 01-01]: Confirmed scenedetect exact pin ==0.7 matches installed/working version (PEP 440 0.7.0); no other 0.7.x exists on PyPI
- [Phase 01-01]: Ran uv lock immediately after writing pyproject.toml deps (fail-fast) before scaffolding source files, per plan instruction
- [Phase 01-02]: jobs=1 used on both sides of the D-14 detection parity check (oracle CLI and migrated detect_scenes) for a deterministic comparison, isolating mechanical-migration correctness from the separately-verified parallel-jobs circular-import path
- [Phase 01-02]: use_qsv probed once via Path('/dev/dri/renderD128').exists() (True in this devcontainer) and applied explicitly/identically to both the legacy oracle CLI and DetectionConfig(use_qsv=...) for the parity check
- [Phase 01-03]: Preflight (shutil.which + video.is_file()) retained in run_encode as the sanctioned minimal structural change while stripping argparse - D-13 zero-logic-change contract stays explicit
- [Phase 01-03]: Switched pytest to --import-mode=importlib to resolve test_chunk.py/test_keyframes.py basename collision between tests/unit/encoding and tests/subprocess/encoding
- [Phase 01-03]: Determinism pre-check confirmed qsvencc deterministic on this box - byte-identical pre-mux movie.obu used as the primary D-14 parity gate
- [Phase 01-03]: qsvencc --psnr/--ssim require OpenCL, unavailable in this devcontainer (pre-existing) - Task 3 parity gate runs with metrics disabled symmetrically on both oracle and migrated sides
- [Phase 02-01]: Used exact RESEARCH.md hex blobs for Cases A-D rather than re-deriving them with the builder (avoids transcription-error risk on nested SeekHead/Tracks/Cues structures)
- [Phase 02-01]: Reworded mkv/ebml.py module docstring to avoid tripping the Task 1 purity check's naive substring search on the literal word 'subprocess'
- [Phase 02-02]: Used the 2-tuple (seek, trim) return for compute_chunk_seek_trim per D-04's minimal-diff allowance
- [Phase 02-02]: contiguous_run annotated Union[Dict[int,int], Set[int]] using typing generics (D-11), not PEP 604 |
- [Phase 02-02]: chunk_command wrapped (not stubbed) in the wiring test so real command-building logic runs while recording seek/trim args
- [Phase 03-01]: DEBT-03: measured Layer-1 (0.67x-0.80x speedup) and Layer-2 (1.43x ratio) both fall short of the quantified switch thresholds -- kept ThreadPoolExecutor, rewrote the contradictory comment with measured rationale
- [Phase 03-01]: DEBT-04: kept dovi_tool installed in devcontainer, documented retention for planned Phase-4 TEST-04 DV RPU work without overclaiming AV1 support (extract-rpu is HEVC-only)
- [Phase 03-02]: TEST-03 clip recipe (four ~55s color/smptebars segments, 220s@24fps) verified via ffprobe to clear the jobs*min_span gate for jobs=[2,3] with margin
- [Phase 03-02]: Engagement proof primary target is enpipe.detection.detect.detect_scenes (deferred fallback), call_count==0, executor-agnostic; _segment_worker call_count>1 refinement gated on active executor to avoid PicklingError under ProcessPoolExecutor
- [Phase 03-03]: ruff pinned exactly (==0.15.20) to match project's exact-pin convention, rather than uv add's default >= constraint
- [Phase 03-03]: select = ["F", "E9"] only for ruff — fuller E/W set fires 15x E702 on the deliberately dense mkv/ebml.py parser
- [Phase 03-03]: mkvtoolnix install kept as a separate continue-on-error CI step so an unavailable mkvmerge package cannot block the ffmpeg-only TEST-03 regression test
- [Phase 03-03]: Comment-only hardware-tier exclusion in ci.yml (no stub self-hosted job) per RESEARCH Open Question 3 discretion
- [Phase 04-01]: run_detect docstring documents the intentionally-absent shutil.which preflight as a sanctioned deviation, mirroring run_encode's docstring style but for the opposite deviation
- [Phase 04-01]: cli/main.py uses typing.Optional[Sequence[str]] for main(argv=...), not RESEARCH.md's draft PEP 604 syntax, per typing-generics requirement
- [Phase 04-01]: uv sync used (not uv pip install -e .) since the lockfile still resolved cleanly for the console_script wiring
- [Phase 04-02]: Empirical correction: HDR10 mastering-display/max-CLL survival is checked via ffprobe FRAME-level side data (frame=side_data_list), not STREAM-level -- this pipeline's mkvmerge-muxed raw-OBU AV1 output has no stream-level side_data_list at all
- [Phase 04-02]: Multi-scene synthetic clips (SDR + HDR10) reuse test_parallel_regression.py's 4-segment color=/smptebars= lavfi cut recipe, shortened to 10s/segment (40s total, 3 cuts) for fast real-hardware wall time
- [Phase 05]: run_pipeline additive shutil.which preflight before run_detect; run_encode keeps its own preflight unchanged (D-02 zero-behavior-change invariant)
- [Phase 05]: Detect-jobs and encode-jobs flags resolve the jobs collision; no bare jobs flag on enpipe run (D-03)
- [Phase 05]: Optional scenes-path override implemented (Claude's discretion, D-04), routing to both detect output and encode scenes
- [Phase 06-02]: run_concurrent takes an explicit refs: Dict[int, Path] param (not a same-workdir naming convention) so isolated references can be built once and reused across many ephemeral per-iteration stress-matrix workdirs
- [Phase 06-02]: IMMUNITY_ITERS defaults to 8 (env-tunable) -- survival-probability math (0.35^8..0.65^8 ~= 2e-4..3e-2) justifies a modest, fast-rerun iteration count distinct from the one-time 20-iter stress tier

### Pending Todos

None yet.

### Blockers/Concerns

- Carried from v1.0: self-hosted GitHub Actions runner with `/dev/dri` passthrough remains a nontrivial, security-sensitive setup for hardware-gated CI; real DV/HDR10+ source material sourcing remains manual

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260709-4h8 | `-o` accepts a directory → `<stem>.Encoded<suffix>` inside it (fixes chunks-workdir PermissionError) | 2026-07-09 | cb49cc7 | [260709-4h8-o-accepts-a-directory-output-filename-be](./quick/260709-4h8-o-accepts-a-directory-output-filename-be/) |
| 260709-629 | Тихий выход по Ctrl-C (SIGINT): перехват `KeyboardInterrupt` в `main()` → `SystemExit(130)`, без трейсбеков | 2026-07-09 | c942e05 | [260709-629-ctrl-c-sigint](./quick/260709-629-ctrl-c-sigint/) |
| 260709-6jo | Живой tqdm-прогресс детекции сцен: СТАРТ/ФИНИШ-строки в stderr, штатный бар (последовательно) / агрегированный бар (параллельно); cut-математика и порядок результатов не изменились | 2026-07-09 | b39d1c9 | [260709-6jo-live-tqdm](./quick/260709-6jo-live-tqdm/) |
| 260709-711 | Плавный ПОКАДРОВЫЙ прогресс-бар в параллельном режиме: `progress_cb`-хук в `QsvPipeStream.read()` двигает общий бар из всех сегмент-потоков (было: скачки по завершении целого сегмента, висело на 0%). Ветка `show_progress=False`, cut-математика и порядок `results` не тронуты | 2026-07-09 | 05c8ab6 | [260709-711-smooth-per-frame-progress-bar](./quick/260709-711-smooth-per-frame-progress-bar/) |
| 260709-89t | `enpipe run/detect/encode <папка>` — новый leaf-модуль `shared/batch.py` (дискавери + collect-then-report оркестратор), `--recursive`, skip-existing, guard'ы схлопывания выходов (-o-файл/--workdir/--csv/--scenes -> die). Одиночный файл byte-identical | 2026-07-09 | f7f8fb7 | [260709-89t-folder-batch-input-enpipe-run-detect-enc](./quick/260709-89t-folder-batch-input-enpipe-run-detect-enc/) |
| 260709-gs0 | Слим-рантайм-образ enpipe (multi-stage `Dockerfile` + `.dockerignore` + `docker/README.md`); builder: `uv sync --frozen --no-dev --no-editable`; runtime: медиа-стек дословно из `.devcontainer/Dockerfile` (без tmux) + venv-copy. Образ здесь не собран (нет docker) — сборку/GPU-прогон проверяет пользователь на хосте | 2026-07-09 | cbae949 | [260709-gs0-compact-slim-runtime-container-image-for](./quick/260709-gs0-compact-slim-runtime-container-image-for/) |
| 260709-hq2 | GHCR build-and-publish воркфлоу (`.github/workflows/docker-publish.yml`, тег `v*`/`workflow_dispatch`, все `docker/*` action'ы запиннены по реально резолвленному commit-SHA); опциональный BuildKit-секрет `github_token` (`required=false`, POSIX `set --`/`"$@"`) для двух GitHub-release curl-блоков в `Dockerfile` (qsvencc, dovi_tool). Воркфлоу здесь не запускался, образ не собирался — пользователь проверяет пушем тега `vX.Y.Z` | 2026-07-09 | 6b5057e | [260709-hq2-github-actions-workflow-to-build-and-pub](./quick/260709-hq2-github-actions-workflow-to-build-and-pub/) |
| 260722-2rq | Новый флаг `--out-dir DIR` (кодирование в папку): папка создаётся при необходимости (`mkdir -p`), выход кладётся внутрь как `<стем>.Encoded<суффикс>`. Работает на `encode`/`run`/батч-ветках; `--out` без изменений (строго файл), `--out`/`--out-dir` взаимоисключающи (die). `resolve_output_path` остался чистым; mkdir в `_ensure_out_dir` обёрнут в `except OSError -> die()` (PermissionError на /data / существующий файл). WR-01: mkdir после проверки на пустоту, чтобы не плодить осиротевшие папки. 166 fast-тестов зелёные, ruff чист | 2026-07-22 | 6d2b55a | [260722-2rq-out-encoded](./quick/260722-2rq-out-encoded/) |
| 260722-4oz | При `--no-metrics` не создавать `.metrics.csv`: гейт `if rows:` -> `if metrics_on and rows:` в `encoding/pipeline.py` (метрический артефакт пишется только когда метрики считались; `rows` копится ради size/time, но файл не нужен). `write_metrics_csv` остался чистым/нетронутым. Тест `test_pipeline_wiring.py` доказывает обе ветки (no_metrics -> не вызывается + нет файла; metrics on -> вызывается). 167 fast-тестов зелёные, ruff чист | 2026-07-22 | 61a38ab | [260722-4oz-skip-metrics-csv](./quick/260722-4oz-skip-metrics-csv/) |
| 260722-lxs | В devcontainer (dlstreamer-база) добавлен слой dev/debug-утилит из болей сегодняшней отладки: `skopeo` (инспекция OCI-образов без docker), `strace`, `ripgrep`, `xxd`, `mediainfo`, `intel-gpu-tools` (`intel_gpu_top` — загрузка Arc), `hyperfine`, `p7zip-full` — отдельный RUN-слой (не бьёт кэш media/qsvencc), Russian WHY-коммент на каждый; post-create.sh проверяет наличие. НЕ собран здесь — хост пересобирает | 2026-07-22 | e1c9322 | [260722-lxs-devcontainer](./quick/260722-lxs-devcontainer/) |
| 260723-36w | Opt-in FFmpeg 8.1 (BtbN static GPL) side-by-side в devcontainer: отдельный RUN-слой тянет `ffmpeg-n8.1-latest-linux64-gpl-8.1.tar.xz` в `/opt/ffmpeg-8.1`, на PATH как `ffmpeg-8.1`/`ffprobe-8.1`; системный ffmpeg 6.1.1 НЕ трогается. ЗАЧЕМ: `av1_qsv` — иммунный к межпроцессной порче кадров путь энкода (см. debug scene-chunk-frame-mismatch), плюс `dovi_rpu` BSF (DV-проброс), которого нет в 6.1.1. Пин: осознанно подвижный `latest`-тег (без SHA256), единообразно с qsvencc/dovi_tool. Слой перед podman apt-фиксом (кэш media/qsvencc не бьётся); non-fatal self-check в post-create.sh (version + av1_qsv/hevc_qsv + dovi_rpu). НЕ собран здесь — хост пересобирает (чек-лист в SUMMARY) | 2026-07-23 | 885a578 | [260723-36w-add-future-ready-ffmpeg-8-1-btbn-static-](./quick/260723-36w-add-future-ready-ffmpeg-8-1-btbn-static-/) |
| 261001-lq0 | claude-code ставится npm'ом (`@anthropic-ai/claude-code`), а не фичей `ghcr.io/anthropics/devcontainer-features/claude-code` — фича делала то же самое (тот же npm-пакет в nvm-префиксе), минус pin в lock и минус зависимость сборки от ghcr. Авторизации claude/opencode/qwen переживают ребилд через 4 named volume'а (`/root/.claude`, `/root/.qwen`, `/root/.local/share/opencode`, `/root/.config/opencode`). Ключевое: `~/.claude.json` — отдельный ФАЙЛ, томом не прикрыть, а symlink — ловушка (claude пишет через temp+`rename()`, rename сносит симлинк → молчаливая поломка), поэтому `CLAUDE_CONFIG_DIR=/root/.claude` в containerEnv (эмпирически проверено, что переносит и `.claude.json`) + идемпотентная миграция в post-create.sh, которая НЕ перезаписывает уже персистентный конфиг. Самопроверка `PERSIST_OK`: `findmnt` на каждый путь + наличие кредов. НЕ собран здесь (нет docker) — хост пересобирает; чек-лист в PLAN | 2026-10-01 | 1554162 | [261001-lq0-devcontainer-claude-code-via-npm-persist](./quick/261001-lq0-devcontainer-claude-code-via-npm-persist/) |
| 260722-lji | Devcontainer переведён на базу `intel/dlstreamer` (Ubuntu 24.04): медиа-стек (iHD 26.2.2/oneVPL/ffmpeg-QSV) теперь ИЗ образа, из Dockerfile убран ручной apt-стек драйверов+ffmpeg. Сохранены qsvencc (Rigaya, ubuntu24.04-ассет + dep-strip libmfx1/opencl-icd), dovi_tool, mkvtoolnix, tmux, proxy-ENV+IS_SANDBOX, apt-sandbox fix; devcontainer.json — фичи node+claude-code, /data-фикс (keep-groups + userns-фолбэк), LIBVA_DRIVER_NAME=iHD, remoteUser root. post-create.sh: sudo->AS_ROOT-guard. НЕ собран/не проверен здесь (нет docker/GPU) — хост пересобирает; чек-лист в SUMMARY | 2026-07-22 | 4ff3c36 | [260722-lji-devcontainer-intel-dlstreamer-qsvencc-cl](./quick/260722-lji-devcontainer-intel-dlstreamer-qsvencc-cl/) |

## Deferred Items

Items acknowledged and deferred at the v1.1 milestone close on 2026-07-23 (pre-close artifact audit — 5 open items):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| debug | scene-chunk-frame-mismatch — single corrupt frames (VMAF≈0) in scene-chunk encode; **silent output corruption**, strikes at core value | fixed upstream (rigaya/QSVEnc 45003f1, verified on A380 2026-10-02); adoption = v1.2 Phase 7 | v1.1 close 2026-07-23 |
| debug | qsvenc-upstream-issue — iHD/media-driver cross-process 10-bit reference-surface aliasing (upstream bug report draft) | unknown/draft | v1.1 close 2026-07-23 |
| debug | cannot-write-data-mounts — devcontainer `/data` bind-mount EACCES (rootless Podman userns mapping) | fix-applied-pending-rebuild | v1.1 close 2026-07-23 |
| uat_gap | Phase 03 — 03-HUMAN-UAT.md | partial (0 pending scenarios) | v1.1 close 2026-07-23 |
| verification_gap | Phase 03 — 03-VERIFICATION.md | human_needed | v1.1 close 2026-07-23 |

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | OBS-01 (stdlib logging) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | CFG-01 (typed config layer) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | QUAL-01/02/03, CI-02 (ruff+pyright in CI, golden-file EBML fixtures, coverage/hypothesis, image parity+Renovate) | Deferred to v2 | Roadmap creation 2026-07-08 |
| Out of scope | Overlapped/streaming orchestrator (`queue.Queue` producer/consumer) | Deferred until source moves to SSD/NVMe | v1.1 scoping 2026-07-08 |

## Session Continuity

Last session: 2026-10-02T03:07:46.046Z
Stopped at: Phase 7 context gathered
Resume file: .planning/phases/07-adopt-fixed-qsvencc-concurrency-regression-lock/07-CONTEXT.md
</content>

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
