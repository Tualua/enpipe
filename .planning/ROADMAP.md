# Roadmap: enpipe

## Milestones

- ✅ **v1.0 Productionization** — Phases 1–4 (shipped 2026-07-08)
- ✅ **v1.1 Single-command pipeline entry point** — Phase 5 (shipped 2026-07-23)
- ✅ **v1.2 Concurrent-encode correctness** — Phases 6–8 (shipped 2026-10-04)
- 📋 **Next milestone** — not yet defined (`/gsd:new-milestone`)

Full phase detail is archived per milestone under `.planning/milestones/`:
- `.planning/milestones/v1.1-ROADMAP.md` (cumulative — captures Phases 1–5, the repo's first milestone archive)
- `.planning/milestones/v1.1-REQUIREMENTS.md`
- `.planning/milestones/v1.2-ROADMAP.md`
- `.planning/milestones/v1.2-REQUIREMENTS.md`

## Phases

<details>
<summary>✅ v1.0 Productionization (Phases 1–4) — SHIPPED 2026-07-08</summary>

- [x] Phase 1: Package Foundation, Migration & Fast Test Tier (3/3 plans) — completed 2026-07-08
- [x] Phase 2: Correctness-Critical Extraction (2/2 plans) — completed 2026-07-08
- [x] Phase 3: Concurrency Resolution + Regression Baseline + CI (3/3 plans) — completed 2026-07-08
- [x] Phase 4: Unified CLI + Hardware-Gated Real-Media Validation (2/2 plans) — completed 2026-07-08

</details>

<details>
<summary>✅ v1.1 Single-command pipeline entry point (Phase 5) — SHIPPED 2026-07-23</summary>

- [x] Phase 5: Single-Command Pipeline Entry Point (1/1 plan) — completed 2026-07-09

`enpipe run <video>` composes detect → `.scenes` → encode sequentially in one invocation, byte/frame-identical to the manual two-step and to the `legacy/` oracle on real Arc hardware.

</details>

<details>
<summary>✅ v1.2 Concurrent-encode correctness (Phases 6–8) — SHIPPED 2026-10-04</summary>

- [x] Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE) (3/3 plans) — completed 2026-07-23
- [x] Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock (5/5 plans) — completed 2026-10-02
- [x] Phase 8: Усиление замка COR-02: триада на каждой сессии, сверка кадров, путь с метриками (6/6 plans) — completed 2026-10-03

Silent cross-session frame corruption of concurrent `qsvencc` eliminated: fixed upstream (`45003f1`), adopted behind a fail-closed revision gate (now r4665, Tualua fork 8.32+vppsync7) and locked by a hardware byte-identity regression test (640 sessions, 0 mismatches). ffmpeg `av1_qsv` migration parked as 999.1.

</details>

## Progress

| Phase                                                 | Milestone | Plans Complete | Status      | Completed  |
| ----------------------------------------------------- | --------- | -------------- | ----------- | ---------- |
| 1. Package Foundation, Migration & Fast Test Tier     | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 2. Correctness-Critical Extraction                    | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 3. Concurrency Resolution + Regression Baseline + CI  | v1.0      | 3/3            | Complete    | 2026-07-08 |
| 4. Unified CLI + Hardware-Gated Real-Media Validation | v1.0      | 2/2            | Complete    | 2026-07-08 |
| 5. Single-Command Pipeline Entry Point                | v1.1      | 1/1            | Complete    | 2026-07-09 |
| 6. Concurrency-Immunity Spike + Image Rebuild (GATE)  | v1.2      | 3/3            | Complete    | 2026-07-23 |
| 7. Adopt Fixed qsvencc + Regression Lock              | v1.2      | 5/5            | Complete    | 2026-10-02 |
| 8. Усиление замка COR-02                              | v1.2      | 6/6            | Complete    | 2026-10-03 |

## Backlog

### Phase 999.1: ffmpeg av1_qsv backend (BACKLOG)

**Goal:** [Captured for future planning] Бывшие фазы 7–10 v1.2: слой `backends/` без изменения поведения, ffmpeg `av1_qsv` для SDR, HDR10 через ffmpeg, решение по DV/HDR10+. Отложено 2026-10-02: тихая порча кадров qsvencc при параллельном кодировании исправлена в апстриме (rigaya/QSVEnc `45003f1`, issue #308) и проверена на Arc A380, поэтому главного довода за переход на ffmpeg больше нет. Артефакты планирования бывшей фазы 7 (CONTEXT/RESEARCH/PATTERNS/REVIEWS + 4 PLAN) лежат в каталоге этого пункта; результаты GATE фазы 6 и `research/` остаются на месте для возможного возврата.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)

### Phase 999.3: Гейт версии qsvencc в legacy/encode_scenes.py (BACKLOG)

**Goal:** [Captured for future planning] Пробел верификации фазы 7 (07-REVIEW.md WR-04), некритичный: `legacy/encode_scenes.py` запускает параллельный qsvencc без проверки ревизии >= 4634 и без `--backend qsv`; docstring `qsvencc_version` утверждает покрытие «каждого запуска». Либо подключить гейт в legacy, либо сузить формулировку docstring.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)

### Phase 999.4: Надёжность метрик qsvencc (--psnr/--ssim) при параллельных чанках (BACKLOG)

**Goal:** [Captured for future planning] Факты фазы 8. История на r4634 + PPA (intel-opencl-icd 26.31.39395.13): подсистема метрик падала (`VIDEOMETRIC: Failed to copy input surface`, `allocVA`, `Decoded frame count does not match`, rc=255), на синтетике 320x180 JOBS=2 отказывали 3 из 4 чанков в каждой из 5 попыток, в 08-01 на сцене 1129 2 отказа из 3; при rc=0 терялись кадры (236/240); `encode_chunk` при rc!=0 теряет чанк, а значения PSNR/SSIM были недостоверны (33.9 против 48.2 дБ на побайтно одинаковом выходе). Измерено в 08-06 на r4658 (8.32-vppsync4, форк Tualua: патчи #319 и #320): METRICS_FAILED = 0 из 640 сессий матрицы (JOBS 3/5/8, оба варианта метрик), 0 из 24+24 в замке, число попыток метрик в аппаратном тире и паритете везде 1; qsvencc SSIM совпадает с ffmpeg до 1e-6, PSNR = PSNR от среднего MSE (quick 261003-8fs/8qq). Дефект на r4658 не воспроизведён, остаётся: (1) исправления #319/#320 лежат только в форке, нужно отследить попадание в официальный апстрим (8.33+) и вернуться на официальный релиз; (2) сообщение об ошибке чанка в `encode_chunk` обрезано до 500 символов stderr, маркер `VIDEOMETRIC` может не попасть; (3) retry в `encode_chunk` отсутствует. Варианты (без решения): retry при маркерах VIDEOMETRIC, внешний ffmpeg-PSNR, issue/PR в апстрим.
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)

### Phase 999.5: Конвертация Dolby Vision profile 5 → HDR10 через libplacebo (BACKLOG)

**Goal:** [Captured for future planning] Решейпинг базового слоя DV profile 5 (IPTPQc2) по RPU в BT.2020 PQ, чтобы у таких источников был HDR10-фолбэк. Сейчас (проверено на A380 2026-10-03) P5 корректно уходит в AV1 DV 10.0 (bl_compat 0), HDR-фолбэка нет; P8.1 → 10.1. Варианты: ffmpeg `vf_libplacebo` (`apply_dolbyvision=1`, есть в ffmpeg 6.1; нужен Vulkan — для Arc `mesa-vulkan-drivers`/ANV, в контейнере сейчас `VK_ERROR_INCOMPATIBLE_DRIVER`) или `qsvencc --vpp-libplacebo-tonemapping` (в сборке r4658 libplacebo disabled). Открытые вопросы: предпроход в промежуточный файл vs пайп в qsvencc (потеря `--avhw`), статические HDR10-метаданные из RPU L6 (`dovi_tool`), скорость и качество на A380 (фрагмент: `/data/downloads/enpipe-fixtures/dv-p5.mkv`).
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)

### Phase 999.6: Источники с ненулевым start_time (MPEG-TS/m2ts) в enpipe (BACKLOG)

**Goal:** [Captured for future planning] Найдено планировщиком quick 261003-j55 (2026-10-03, A380): у HEVC в MPEG-TS `start_time`≈0.083 с, `keyframe_table_ffprobe` считает первый keyframe кадром 2 и encode падает через `die` до кодирования; кроме того enpipe передаёт в `qsvencc --seek` абсолютный pts, а qsvencc трактует `--seek` относительно начала потока. Нужно: нормализовать keyframe-таблицу и seek к началу потока (start_time/первый kf), покрыть тестом на TS/m2ts. Связано с апстрим-багом qsvencc firstpkt-seek (`.planning/debug/HANDOFF-qsvencc-seek-firstpkt.md`): TS-источники затронуты им сильнее всего (сдвиг 0.25 с на синтетике).
**Requirements:** TBD
**Plans:** 0 plans

Plans:
- [ ] TBD (promote with /gsd:review-backlog when ready)
