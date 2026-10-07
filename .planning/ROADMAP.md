# Roadmap: enpipe

## Milestones

- ✅ **v1.0 Productionization** — Phases 1–4 (shipped 2026-07-08)
- ✅ **v1.1 Single-command pipeline entry point** — Phase 5 (shipped 2026-07-23)
- ✅ **v1.2 Concurrent-encode correctness** — Phases 6–8 (shipped 2026-10-04)
- 🚧 **v1.3 Анализ качества энкода** — Phases 9–13 (in progress)

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

## Phases (v1.3)

- [x] **Phase 9: Чистое ядро анализа и ридеры** - метрики кадра, пороги-константы, ридеры источников кандидатов, слияние кандидатов, единая модель отчёта (без subprocess) (completed 2026-10-06)
- [ ] **Phase 10: Извлечение кадров и выравнивание** - точное извлечение кадра N, предпроверка пары, вердикт выравнивания, `--offset`, программный декод без GPU
- [ ] **Phase 11: Анализ одной пары: кандидаты, кропы, отчёт, CLI** - `enpipe analyze <src> <enc>` выдаёт `report.md`/`index.html`/`report.json` с кропами и флагом «VMAF хорош, цвет плох»
- [ ] **Phase 12: Скан цвета по сценам и батч по папке** - точка внутри каждой сцены из `.scenes`, режим папки с парами и сводкой сирот
- [ ] **Phase 13: Калибровка, сравнение двух энкодов, приёмка** - пороги проверены на ≥ 3 материалах и синтетике, режим сравнения, приёмка на известных данных

## Phase Details (v1.3)

### Phase 9: Чистое ядро анализа и ридеры

**Goal**: Метрики кадра, пороги, ридеры источников кандидатов и модель отчёта существуют как чистые функции без subprocess и проверяются быстрым тиром тестов на фикстурах
**Depends on**: Nothing (first phase of v1.3; encode path untouched)
**Requirements**: MET-01, MET-02, MET-03, MET-04, MET-05, CND-01, CND-02, CND-04, CND-05, RPT-01
**Success Criteria** (what must be TRUE):

  1. Для пары 10-битных YUV-массивов считаются сохранность цвета мелких насыщенных деталей (медиана, p10, число блоков; при недостатке блоков результат «нет мелких цветных деталей», а не число), PSNR Y/U/V с худшим тайлом, яркость в нитах (PQ EOTF) с долей теней и сохранностью детали по Y, ΔE ITP (среднее и p99) — табличные тесты PQ и тайлинга (включая неполные края) зелёные
  2. Все пороги лежат в одной конфигурации как именованные константы, и отчёт помечает их «provisional»
  3. Кандидаты читаются из ручного списка `--frames`, из CSV метрик qsvencc (худшие сцены по `ssim_y`/`psnr_y`) и из внешнего VMAF (tsv/csv, десятичная запятая); при несовпадении длины или базы индекса VMAF-файл отвергается с объяснением
  4. Кандидаты из всех источников сливаются с разносом `--min-gap` и квотой на сцену, у каждого указан источник
  5. Из одной модели данных строятся `report.md`, `index.html` и `report.json`; `report.json` стабилен (golden-тест схемы)

**Plans**: 5 plans

Plans:
**Wave 1**

- [x] 09-01-PLAN.md — контракты: AnalyzeConfig (все пороги, provisional), константы PQ/BT.2020/ITP, frozen-модель отчёта (волна 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — метрики кадра: тайлы с неполными краями, PSNR Y/U/V, ниты/тени/деталь, сохранность цвета мелких деталей, ΔE ITP, analyze_frame (волна 2)
- [x] 09-03-PLAN.md — ридеры --frames/.scenes/CSV qsvencc/VMAF со статусами источников и слияние кандидатов (волна 2)
- [x] 09-04-PLAN.md — report.json (golden v1, inf/nan), report.md, index.html с экранированием, сводка перцентилей (волна 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 09-05-PLAN.md — сквозной тест ядра, AST-сторож изоляции, ворота фазы (волна 3)

### Phase 10: Извлечение кадров и выравнивание

**Goal**: Любой кадр N достаётся из источника и энкода точно по номеру, а пара до расчёта метрик проходит проверку выравнивания с громким отказом при любом сомнении
**Depends on**: Phase 9
**Requirements**: ALN-01, ALN-02, ALN-03, ALN-04, ANL-03
**Success Criteria** (what must be TRUE):

  1. Кадр N извлекается из источника и энкода как 10-битный YUV без потерь (таблица pts, seek на полкадра раньше) и совпадает с `framemd5` последовательного декода на синтетике, в том числе на VFR и ненулевом `start_time`
  2. Пара с несовпадением размера, частоты кадров, числа кадров или тегов диапазона/матрицы/transfer, либо с не-PQ источником, получает громкий отказ с объяснением до расчёта метрик
  3. Выравнивание проверяется в нескольких точках, включая склейки сцен, и даёт один из трёх исходов «выровнено / сдвиг N / неопределённо (статика)»; при сдвиге метрики не строятся
  4. Для энкода частичного диапазона (`--from/--to`) без `--offset` сдвиг обнаруживается и приводит к отказу, а с `--offset` пара сравнивается корректно
  5. Извлечение работает без GPU и `/dev/dri` (программный декод по умолчанию) и не мешает идущему кодированию

**Plans**: 5 plans

Plans:
**Wave 1**

- [x] 10-01-PLAN.md — контракты: provisional-пороги выравнивания, производительные константы, типы пары/вердикта в модели, рендер отказа, seek_time_for_frame, allow-list сторожа (волна 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-02-PLAN.md — чистое ядро: вердикт точки/склейки/кадра/файла, выбор точек, предпроверка пары и правила --offset (волна 2)
- [x] 10-03-PLAN.md — I/O-слой frames.py: probe, таблица pts с кэшем, точный grab 10-бит, nice/threads (волна 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 10-04-PLAN.md — оркестратор pair.py и медиа-тест без GPU: framemd5, VFR, start_time, сдвиг, статика, частичный энкод (волна 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 10-05-PLAN.md — UAT на реальной паре с ZFS-HDD: замер jobs, теги энкода (A8), DV P5, помеха кодированию (волна 4, чекпоинт)

### Phase 11: Анализ одной пары: кандидаты, кропы, отчёт, CLI

**Goal**: Пользователь запускает `enpipe analyze <src> <enc>` и получает отчёт с ранжированными проблемными кадрами, кропами «источник | энкод» и сводкой
**Depends on**: Phase 10
**Requirements**: ANL-01, ANL-04, RPT-02, RPT-03, RPT-04, CND-06
**Success Criteria** (what must be TRUE):

  1. `enpipe analyze <src> <enc> --out DIR` создаёт `report.md`, `index.html`, `report.json` по заданным кадрам и кандидатам из CSV qsvencc / внешнего VMAF
  2. Для каждого кадра в `index.html` есть кропы 1:1 худшего тайла и ×2 худшего цветного блока «источник | энкод», полный кадр и карта разницы (PNG без потерь, тонмаппинг PQ→SDR только для просмотра, с подписью)
  3. Сводка показывает перцентили метрик (min, p1/p5/p10, медиана) и таблицу кандидатов по убыванию серьёзности; кадры «VMAF высокий, цвет мелких деталей потерян» отмечены флагом «VMAF хорош, цвет плох»
  4. Упавшее извлечение кадра видно в отчёте строкой ошибки, остальные кадры обрабатываются
  5. В отчёте записаны версии ffmpeg/qsvencc (если известны), пороги и источники кандидатов

**Plans**: TBD
**UI hint**: yes

### Phase 12: Скан цвета по сценам и батч по папке

**Goal**: Анализ находит проблемные места без подсказок: скан цвета по сценам и обработка целой папки пар
**Depends on**: Phase 11
**Requirements**: CND-03, ANL-02
**Success Criteria** (what must be TRUE):

  1. Скан берёт по одной точке внутри каждой сцены из `.scenes` (не первый кадр сцены), и худшие по сохранности цвета сцены попадают в кандидаты со ссылкой на скан как источник
  2. Сцена 66489–66663 с кадром 66490 попадает в кандидаты скана на материале handoff
  3. `enpipe analyze <папка>` находит пары по `<stem>.Encoded.*` и строит отчёт на каждую
  4. Источники без энкода и неоднозначные пары перечислены в сводке, код выхода ненулевой

**Plans**: TBD

### Phase 13: Калибровка, сравнение двух энкодов, приёмка

**Goal**: Пороги проверены на разных материалах и известных данных, а два энкода одного источника сравниваются рядом
**Depends on**: Phase 12
**Requirements**: CMP-01, CAL-01, CAL-02
**Success Criteria** (what must be TRUE):

  1. `--compare <enc2>` (или дельта двух `report.json`) показывает на одних и тех же кадрах сохранность цвета мелких деталей (медиана/p10), PSNR U/V, ΔE ITP и битрейт обоих энкодов рядом
  2. Пороги проверены минимум на трёх материалах (тёмный, светлый, зернистый/анимация) и на синтетике с известной потерей; контроль «энкод против себя» даёт 100 %, `--icq 1` задаёт пол шума
  3. Синтетика handoff даёт 71 % → 88 % при `--av1-chroma-delta-q -32` (vppsync9)
  4. E01 кадр 66490 и участок 3:56–4:48 попадают в отчёт

**Plans**: TBD

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
| 9. Чистое ядро анализа и ридеры                       | v1.3      | 5/5 | Complete   | 2026-10-06 |
| 10. Извлечение кадров и выравнивание                  | v1.3      | 3/5 | In Progress|  |
| 11. Анализ одной пары: кандидаты, кропы, отчёт, CLI   | v1.3      | 0/0            | Not started | -          |
| 12. Скан цвета по сценам и батч по папке              | v1.3      | 0/0            | Not started | -          |
| 13. Калибровка, сравнение двух энкодов, приёмка       | v1.3      | 0/0            | Not started | -          |

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
