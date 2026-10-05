---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Concurrent-encode correctness
status: Awaiting next milestone
stopped_at: Milestone v1.2 complete and archived
last_updated: "2026-10-04T17:06:54.306Z"
last_activity: "2026-10-05 - quick 261005-4uz: --avoid-idle-clock off в чанке qsvencc"
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 14
  completed_plans: 14
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-04)

**Core value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.
**Current focus:** Planning next milestone (/gsd:new-milestone)

## Current Position

Phase: Milestone v1.2 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-10-05 - Completed quick task 261005-4uz: --avoid-idle-clock off в чанке qsvencc

## Performance Metrics

Per-phase/plan metrics for v1.0–v1.2 archived in `.planning/milestones/v1.2-STATE.md` (snapshot at v1.2 close). Reset for the next milestone.

## Accumulated Context

### Decisions

Milestone-level decisions: `.planning/PROJECT.md` → Key Decisions. Full per-phase decision log up to v1.2: `.planning/milestones/v1.2-STATE.md`.

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
| 261003-c1b | Строка ИТОГО в `run_encode` не падает с TypeError при `psnr_avg=None` (SSIM есть, PSNR нет): `format_total_line`, «н/д» для отсутствующей метрики | 2026-10-03 | 6775d35 | [261003-c1b-psnr-avg-pipeline-py-319](./quick/261003-c1b-psnr-avg-pipeline-py-319/) |
| 261003-hph | DV-тесты: подсчёт `Dolby Vision Metadata` (ffmpeg 9/libdav1d), `ENPIPE_TEST_FFPROBE` для проверочного ffprobe, проверка DV-конфига выхода, новый `test_dv_profile5` (P5→10.0) | 2026-10-03 | cc02840 | [261003-hph-dv-test-dv-dolby-vision-metadata-ffmpeg-](./quick/261003-hph-dv-test-dv-dolby-vision-metadata-ffmpeg-/) |
| 261003-j55 | Аппаратная проверка содержимого чанков (PSNR первого кадра vs кадр источника S, негативный контроль S+Δ); xfail(strict) на баг qsvencc firstpkt-seek и test_dv_profile5; test_hdr10 падает на open-GOP | 2026-10-03 | 22a81a4 | [261003-j55-md5-vs-keyframe](./quick/261003-j55-md5-vs-keyframe/) |
| 261003-l9x | qsvencc → 8.32+vppsync6 (r4663, фикс --seek firstpkt): пин URL+sha256 в обоих Dockerfile, минимальная ревизия 4663 (и для метрик), test_dv_profile5 без xfail, синтетика → test_chunk_content_open_gop (xfail open-GOP) | 2026-10-03 | c134df0 | [261003-l9x-qsvencc-8-32-vppsync6-r4663-url-sha256-d](./quick/261003-l9x-qsvencc-8-32-vppsync6-r4663-url-sha256-d/) |
| 261003-lpo | Защита от open-GOP: `run_encode` отказывает (die) на источниках с ведущими кадрами после используемых keyframe (баг qsvencc trim-offset); test_hdr10 → closed GOP; test_open_gop_source_refused, test_chunk_content_closed_gop | 2026-10-03 | b164776 | [261003-lpo-keyframe-open-gop-qsvencc-trim-offset](./quick/261003-lpo-keyframe-open-gop-qsvencc-trim-offset/) |
| 261003-mj7 | qsvencc → 8.32+vppsync7 (r4665, фикс open-GOP trim): пин, минимальная ревизия 4665, снят отказ на open-GOP и проба ведущих кадров; test_chunk_content_open_gop[rasl,radl], test_hdr10 снова open-GOP | 2026-10-03 | 0b769b4 | [261003-mj7-qsvencc-8-32-vppsync7-r4665-open-gop-tri](./quick/261003-mj7-qsvencc-8-32-vppsync7-r4665-open-gop-tri/) |
| 261004-h8e | ffmpeg 9 (BtbN n9.0.2, autobuild-2026-10-01, пин URL+sha256) — основной ffmpeg/ffprobe в devcontainer и рантайм-образе; apt ffmpeg убран из рантайма; opt-in ffmpeg-8.1 удалён; ENV-01 и harness на ffmpeg 9 | 2026-10-04 | e5ea12c | [261004-h8e-ffmpeg-9-btbn-static-n9-0-2-url-sha256-d](./quick/261004-h8e-ffmpeg-9-btbn-static-n9-0-2-url-sha256-d/) |
| 261004-mse | Хвост 261004-h8e: `scratch/gate_stress_matrix.py --backend ffmpeg` на `ffmpeg_av1qsv_available()`; страж ffmpeg-8.1 покрывает stress-скрипт и харнесс (гэп UAT 06, п.2) | 2026-10-04 | be62b4c | [261004-mse-gate-stress-matrix-py-ffmpeg-9-ffmpeg81-](./quick/261004-mse-gate-stress-matrix-py-ffmpeg-9-ffmpeg81-/) |
| 261005-4uz | `--avoid-idle-clock off` в argv чанка qsvencc: старт сессии ~5.6 → ~1.6 с, выход побайтно тот же (замок COR-02 + parity на A380 зелёные) | 2026-10-05 | 2c59b83 | [261005-4uz-qsvencc-avoid-idle-clock-off-3x](./quick/261005-4uz-qsvencc-avoid-idle-clock-off-3x/) |
| fast | devcontainer → хостовый rootless podman: проброс сокета, CONTAINER_HOST, podman-remote 5.8.2 (пин sha256), label=disable, статус в post-create | 2026-10-04 | f724ad5 | — |
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
| 261003-8fs | Парсер метрик qsvencc принимает inf/nan; ИТОГО PSNR через взвешенное MSE, nan не маскируется | 2026-10-03 | 2a2b4c1 | [261003-8fs-parser-inf-nan-metrics](./quick/261003-8fs-parser-inf-nan-metrics/) |
| 261003-8qq | qsvencc → 8.32+vppsync4 (форк Tualua/QSVEnc, r4658): пин URL+sha256 в обоих Dockerfile, порог 4634 без изменений; на A380 с --psnr/--ssim 240/240 кадров, rc=0. Образы не пересобраны здесь | 2026-10-03 | 97be1a3 | [261003-8qq-qsvencc-vppsync4-tualua](./quick/261003-8qq-qsvencc-vppsync4-tualua/) |

## Deferred Items

Items acknowledged and deferred at the v1.2 milestone close on 2026-10-04 (pre-close artifact audit — 8 open, 5 resolved in place, 3 deferred):

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| debug | cannot-write-data-mounts — `/data` bind-mount EACCES (rootless Podman userns) | fix-applied-pending-rebuild (writable as root 2026-10-04; not re-checked as `vscode`) | v1.2 close 2026-10-04 |
| uat_gap | `milestones/v1.1-phases/03-concurrency-resolution-regression-baseline-ci/03-HUMAN-UAT.md` (v1.0) | partial (0 pending scenarios) | v1.2 close 2026-10-04 |
| verification_gap | `milestones/v1.1-phases/03-concurrency-resolution-regression-baseline-ci/03-VERIFICATION.md` (v1.0) | human_needed | v1.2 close 2026-10-04 |

Resolved in place at v1.2 close: 07-VERIFICATION gaps WR-01..03 (closed by the COR-02 hardening work → status passed); debug handoffs HANDOFF-qsvencc-{frame-corruption,seek-firstpkt,opengop-trim-offset} and qsvenc-upstream-issue (fixed in r4665 → status resolved).

Deferred items from the v1.1 close: still-open ones are carried in the table above; full history in `.planning/milestones/v1.2-STATE.md`.

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | OBS-01 (stdlib logging) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | CFG-01 (typed config layer) | Deferred to v2 | Roadmap creation 2026-07-08 |
| v2 | QUAL-01/02/03, CI-02 (ruff+pyright in CI, golden-file EBML fixtures, coverage/hypothesis, image parity+Renovate) | Deferred to v2 | Roadmap creation 2026-07-08 |
| Out of scope | Overlapped/streaming orchestrator (`queue.Queue` producer/consumer) | Deferred until source moves to SSD/NVMe | v1.1 scoping 2026-07-08 |

## Session Continuity

Last session: 2026-10-04
Stopped at: Milestone v1.2 complete and archived
Resume file: none

## Operator Next Steps

- Start the next milestone with /gsd:new-milestone
