---
phase: 08-cor02-lock-hardening
plan: 06
subsystem: testing
tags: [qsvencc, r4658, r4604, hardware, stress-matrix, byte-identity, metrics, arc-a380]
requires:
  - phase: 08-04
    provides: замок и матрица с побайтным критерием
  - phase: 08-05
    provides: метрики в аппаратном тире и паритете
provides:
  - Аппаратные доказательства усиленного замка COR-02 на r4658
  - Непустота замка на r4604 (3 побайтных расхождения)
  - Бэклог 999.4 (надёжность метрик qsvencc)
affects: [phase-08-verification]
key-files:
  created: [.planning/phases/999.4-qsvencc-metrics-reliability/.gitkeep]
  modified: [.planning/debug/scene-chunk-frame-mismatch.md, .planning/ROADMAP.md, .planning/STATE.md]
key-decisions:
  - "Бинарь под тестом r4658 (8.32-vppsync4), не r4634: замена после quick 261003-8qq"
requirements-completed: [D-05, D-10, D-11, D-12]
duration: 75min
completed: 2026-10-03
status: complete
---

# Phase 8 Plan 06: Аппаратный прогон усиленного замка Summary

**На A380 с qsvencc r4658 (8.32-vppsync4) замок и матрица на 640 сессий дают 0 побайтных расхождений, 0 нарушений триады и 0 METRICS_FAILED; тот же харнесс на r4604 ловит порчу (3 расхождения), то есть замок не вакуумен.**

## Окружение

uname -r 6.19.14-200.fc43.x86_64; iHD 26.3.2; intel-opencl-icd 26.31.39395.13-1~24.04~ppa1; libmfx-gen1.2 26.3.2-1~24.04~ppa1; ffmpeg 6.1.1-3ubuntu5; clinfo: Intel Arc A380; `qsvencc --version`: `QSVEncC (x64) 8.32 (r4658)`.

## Результаты (все реально запущены)

| Шаг | Результат | Время |
|-----|-----------|-------|
| D-10c, r4604 | .deb скачан с GitHub (кэша не было), `sha256sum -c: OK` до распаковки; `dpkg-deb -x` в /tmp/enpipe-phase8/r4604, симлинк в oldbin, не установлен. Шапка `(r4604)`, баннер `WARNING: --expect corrupt`, byte mismatches 3 > 0, PASS. Лог `scratch/gate_stress_matrix_20261003T062807Z.log` | 211 с |
| D-10a, замок r4658 | `2 passed`: `[no-metrics]` и `[metrics]`: sessions=24 ok=24 METRICS_FAILED=0 byte_mismatch=0 triad_violations=0 failed=0 (обе строки) | 332 с |
| D-10b, матрица r4658 | PASS, 640 сессий, без HARNESS ERROR. Лог `scratch/gate_stress_matrix_20261003T063808Z.log` (+ `*_m{0,1}_jobs{3,5,8}.verbose.log`) | 3372 с |
| D-10d, аппаратный тир | `7 passed, 2 skipped` (HDR10+, DV без фикстур). Попытки метрик: test_sdr 1, test_hdr10 1, legacy-parity enpipe=1 legacy=1 | 128 с |
| Паритет `scratch/parity_encode.py` | PARITY OK, movie.obu побайтно идентичен, кадры 240/240, попытки legacy1=1 legacy2=1 migrated=1, ИТОГО SSIM 0.99899 PSNR 54.76 обеих сторон | 20 с |

Таблица D-10b (20 итераций):

| metrics | JOBS | ok | byte_mismatch | triad | SESSION_FAILED | METRICS_FAILED | skipped | wall | mean/max |
|---------|------|----|---------------|-------|----------------|----------------|---------|------|----------|
| off | 3 | 60 | 0 | 0 | 0 | 0 | 0 | 395 с | 19.8/26.9 с |
| off | 5 | 100 | 0 | 0 | 0 | 0 | 0 | 498 с | 24.9/29.4 с |
| off | 8 | 160 | 0 | 0 | 0 | 0 | 0 | 762 с | 38.1/58.8 с |
| on | 3 | 60 | 0 | 0 | 0 | 0 | 0 | 371 с | 18.5/26.5 с |
| on | 5 | 100 | 0 | 0 | 0 | 0 | 0 | 519 с | 26.0/39.7 с |
| on | 8 | 160 | 0 | 0 | 0 | 0 | 0 | 771 с | 38.6/57.0 с |

Итого 640 сессий (2 x 20 x (3+5+8)).

**D-05:** эталоны metrics off и on в этом прогоне совпадают побайтно: 923 `8004166d00e8f4b1ca4b9b44df1d1fd4608e3b4270ebd040524b3c588b9371f2`, 928 `faaf7231732d9e97578d9fd568e78edebb4aeb697271a2785912defd0fd5e0e6`, 1129 `a32e08fad3e917abbf407827f0f3c456758de26614fb075c6e561f08b87ddad3`.

**Сужение D-10d:** с метриками проверены test_sdr, test_hdr10, test_sdr_legacy_oracle_parity и parity_encode.py; test_hdr10plus, test_dv и test_run_parity_vs_two_step идут без метрик (обоснование в 08-05-SUMMARY).

Проверка PATH: после D-10c `qsvencc` на PATH остался r4658.

## Commits

- Task 1/2: репозиторий не менялся (только прогоны).
- Task 3 и SUMMARY: коммит `docs(08-06)` (хеш в финальном отчёте).

## Deviations from Plan

**1. [Подмена бинаря] r4634 -> r4658.** План писал под r4634; перед выполнением quick 261003-8qq (97be1a3, 6f54fe9) перевёл оба Dockerfile и установленный бинарь на форк Tualua/QSVEnc 8.32-vppsync4 (r4658, deb sha256 d2aa8412...e6cb6). Предусловие «(r4634) или выше» выполнено, r4634 не переустанавливался. Везде, где в плане «r4634» для бинаря под тестом (D-10a, D-10b, D-10d, текст 999.4 и дебаг-раздела), сняты данные на r4658. Эталоны фаз 07/08-01 сняты на r4634; харнесс строит изолированные эталоны сам, D-05 сравнивает on/off этого прогона. Критерии не ослаблялись.

**2. [Текст 999.4] Измеренные доли вместо предписанных.** Предписанные в плане VIDEOMETRIC-отказы, недостоверные 33.9/48.2 дБ и потери чанков при JOBS=3 описывают r4634 и записаны как история; на r4658 METRICS_FAILED = 0 из 640+48 сессий, поэтому пункт 999.4 сформулирован как трекинг попадания #319/#320 в официальный апстрим (8.33+) и возврат с форка плюс остаточные 500-символьное усечение stderr и отсутствие retry. Долей отказа не выдумывал.

**3. [Проверка git diff src/legacy] Не пуста по независимой причине.** `git diff --stat 7bc5e49..HEAD -- src/ legacy/` показывает `src/enpipe/encoding/chunk.py` и `metrics.py` (парсер inf/nan, quick 261003-8fs, 2a2b4c1). Этот план src/ и legacy/ не менял; legacy/ без изменений.

**4. Ожидание.** Foreground-ожидание режется на 10 минут, поэтому ожидание шло через фоновые until-циклы; один из них был убит по лимиту, на прогоны не влияет.

## Assumption Drift (advisory)

- Планировалось: метрики qsvencc падают (VIDEOMETRIC) и это измеряется долей отказа. Факт: на r4658 отказов 0. Причина: патчи #319/#320 в форке (quick 261003-8qq).

## Known Stubs

Нет.

## Self-Check: PASSED

Проверено существование: .gitkeep 999.4, раздел `## ФАЗА 8` в debug-документе (содержит `(r4658)`, `(r4604)`, `intel-opencl-icd`, `METRICS_FAILED`, `D-05`), `### Phase 999.4` в ROADMAP, запись `[Phase 08]` в STATE.
