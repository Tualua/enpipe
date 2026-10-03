---
phase: 08-cor02-lock-hardening
plan: 05
subsystem: testing
tags: [metrics, stderr-tap, retry-rule, hardware-tier, legacy-parity]
requires:
  - phase: 08-03
    provides: харнесс (is_metrics_failure, HarnessError, strip_ansi)
provides:
  - install_qsvencc_tap / tap_failures / metrics_only_failure в харнессе
  - аппаратный тир с вариантами metrics=[False, True] (sdr, hdr10, legacy-parity)
  - scratch/parity_encode.py с метриками по умолчанию (PARITY_METRICS)
affects: [08-06]
tech-stack:
  added: []
  patterns: [обёртка-перехватчик qsvencc на PATH, повтор только при чистом отказе метрик]
key-files:
  created: []
  modified:
    - tests/integration/_concurrency_harness.py
    - tests/integration/test_harness_gates.py
    - tests/integration/test_hardware_real_media.py
    - scratch/parity_encode.py
key-decisions:
  - "Решение о повторе принимается по ПОЛНОМУ stderr из перехватчика, не по 500-символьному хвосту die()"
  - "Исчерпание METRICS_ATTEMPTS=5 даёт fail с пометкой METRICS_FAILED, не pass/skip"
  - "Расхождение числа кадров («ожидалось») никогда не повторяется"
requirements-completed: [D-10, D-12]
duration: 40min
completed: 2026-10-03
status: complete
---

# Phase 8 Plan 05: Метрики в аппаратном тире и паритете с legacy Summary

**Аппаратный тир и паритет с legacy умеют идти с `--psnr/--ssim`; повтор при отказе метрик решается по полному stderr qsvencc (обёртка на PATH) и никогда не маскирует расхождение кадров. На железе путь с метриками сейчас красный: это результат, а не дефект инструмента.**

## Коммиты

- 8e2964d: перехватчик stderr и правило повтора в харнессе (+5 fast-tier тестов на фейковом бинаре).
- a80dc76: `test_hardware_real_media.py` (параметризация, `METRICS_ATTEMPTS = 5`, фикстура `metrics_tap`, помощники повтора и `_assert_metrics_csv`).
- 1830ebe: `scratch/parity_encode.py` (`METRICS_ENABLED`, tap, повтор по обеим сторонам).

## Проверено (реально запущено)

- fast-tier: `.venv/bin/python -m pytest -q`: 274 passed, 12 deselected (было 269; +5 новых).
- collect-only `-m hardware`: 3 id `[metrics]` и 3 `[no-metrics]`.
- Acceptance greps: `Debian-trixie devcontainer` = 0, `D-10d scope decision` = 4, `is_metrics_failure(str(exc))` = 0, `METRICS_UNAVAILABLE` = 0, `git diff --stat src legacy` пуст.
- Аппаратно: `test_sdr[no-metrics]` PASSED. `test_sdr[metrics]` FAILED с `METRICS_FAILED x5` (см. ниже).
- Смоук `scratch/parity_encode.py` (A380): три запуска, все красные на расхождении кадров с метриками (см. ниже).

НЕ проверено: `test_hdr10[*]` и `test_sdr_legacy_oracle_parity[*]` на железе не запускались; зелёный путь варианта `[metrics]` ни разу не наблюдался.

## Находки для 08-06 (важно)

1. `test_sdr[metrics]` (синтетика 320x180, 4 чанка, `--jobs 2`): в каждой из 5 попыток падают 3 из 4 чанков с `No OBU found in packet / avout: failed to parse av1 header / encoded 0 frames`. Полный stderr через перехватчик содержит маркер `VIDEOMETRIC:`, то есть в 500-символьном хвосте маркера нет, а правило по полному stderr его видит (подтверждает необходимость перехватчика). Воспроизводится вне pytest и без перехватчика (`enpipe encode ... --jobs 2`, 3 запуска подряд): перехватчик ни при чём. Итог: METRICS_FAILED, дефект D-12 хуже ожидаемого (доля отказа около 3/4 на малом кадре вместо 1/9..6/15). По плану это СТОП и доклад пользователю.
2. `scratch/parity_encode.py` (640x360, 1 job): legacy x2 и migrated падают на `чанк 0: кадров 236, ожидалось 240` (qsvencc завершается без ошибки, но теряет 4 кадра при включённых метриках). Симметрично на legacy и enpipe. Правило повтора корректно НЕ повторяет (расхождение кадров). Это потенциально настоящая порча числа кадров при метриках, не зависящая от кода enpipe. В одном из трёх запусков отказала migrated-сторона, в двух legacy.

## Decisions

- Сужение D-10d (plan-checker W-2): по метрикам параметризованы только `test_sdr`, `test_hdr10`, `test_sdr_legacy_oracle_parity`. `test_hdr10plus`, `test_dv`, `test_run_parity_vs_two_step` остаются с `--no-metrics` (у каждого вызова комментарий «D-10d scope decision»). Обоснование: HDR10+/DV гейтятся фикстурами и их предмет не метрики; `test_run_parity_vs_two_step` добавил бы две нестабильные стороны без нового покрытия; путь `enpipe run` с метриками проверяет чекпоинт 08-02 (D-07/D-14).
- В `_assert_metrics_csv` значения SSIM/PSNR не сравниваются (D-12), проверяется наличие строки `ИТОГО` и непустых `ssim_all`/`psnr_avg`.
- В `parity_encode.py` итоговые SSIM/PSNR обеих сторон печатаются информационно; существующий эпсилон-гейт для случая недетерминизма оставлен как был.

## Deviations from Plan

### Язык файлов
Файлы `tests/integration/*` и `scratch/parity_encode.py` оставлены на английском (локальный стиль, как оговорено в плане), вопреки русскоязычному требованию CLAUDE.md.

### Auto-fixed Issues
Нет. Эпсилон-ветка `parity_encode.py` (случай «недетерминизм + метрики») сохранена в исходном виде, чтобы не расширять скоуп; информационная печать ИТОГО добавлена отдельно.

## Known Stubs
Нет.

## Self-Check: PASSED
- Файлы: все 4 изменённых файла и этот SUMMARY найдены.
- Коммиты 8e2964d, a80dc76, 1830ebe найдены.
