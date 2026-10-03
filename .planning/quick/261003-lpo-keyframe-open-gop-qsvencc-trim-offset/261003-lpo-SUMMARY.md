# Quick 261003-lpo: жёсткий отказ на open-GOP источниках (qsvencc trim-offset −N)

## Итог

`enpipe encode` теперь завершается через `die()` до аудио и до любого чанка, если после keyframe, с которого режется чанк (seek-точка), в порядке декодирования идут пакеты с pts раньше keyframe (open-GOP: CRA + RASL). qsvencc на таких источниках сдвигает `--trim` на −N, и содержимое чанков тихо смещается при верном числе кадров. Компенсации trim+N нет (`compute_chunk_seek_trim` не менялась), обхода через env нет (намеренно).

## Коммиты

- b164776 fix: `count_leading_after_keyframes` (чистый парсер) + `probe_leading_frames` (один ffprobe с пачкой `-read_intervals`, откат на полный скан, fail closed) в `keyframes.py`
- 2fdcee7 fix: защита в `run_encode` после keyframe-таблицы, до `detect_hdr`/аудио/чанков, на главном потоке; wiring-тесты
- 6163321 test: HDR10 источник с `open-gop=0`; `test_open_gop_source_refused` и `test_chunk_content_closed_gop` вместо strict-xfail; README фикстур; debug-файл -> resolved-guarded

## Проверки (реально выполнены)

- `uv run pytest tests/unit tests/subprocess -q`: 235 passed (0.66 s)
- `uv run ruff check src tests`: All checks passed
- Полный hardware-модуль (PATH=/opt/qsvencc-vppsync6/usr/bin, ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures, ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe): **12 passed, 0 failed, 0 skipped, 0 xfail** за 1399 s (23:19). Лог: scratchpad/hw.log. METRICS_FAILED не встречалось.

Длительности: test_dv_profile5 593 s, test_dv 443 s, test_hdr10plus 190 s, test_run_parity_vs_two_step 28 s, test_sdr_legacy_oracle_parity 27 s x2, test_chunk_content_closed_gop 21 s, test_hdr10 16 s x2, test_sdr 15 s x2, test_open_gop_source_refused 7 s.

Реальные фикстуры (DV 8.1, DV P5, HDR10+) защитой не отклонены (N=0). Оба варианта test_hdr10 снова проходят проверку содержимого на closed-GOP источнике.

## Решения

- Проверяются только реально используемые seek-keyframe'ы (`kf_before` по выбранным сценам, включая K=0): стоимость пропорциональна числу чанков.
- Старт интервала = время K + пол-кадра (mkv/mp4 откатываются назад к K; floor_ms попадал на предыдущий K в mkv); `LEADING_PROBE_PACKETS = 24`.
- Откат: если какой-то K не найден — полный скан пакетов; если и там нет — die.
- Синтетические источники test_sdr / oracle parity / run parity на libx264 ultrafast (bframes=0, closed GOP) не менялись.
- Когда qsvencc починят, защиту стоит привязать к ревизии qsvencc (рядом с QSVENCC_MIN_REV) отдельной задачей.

## Отклонения от плана

- TDD: тесты и реализация Task 1 написаны вместе, отдельного RED-прогона не было (в Task 1 и Task 2 тесты прошли с первого запуска). Отдельных test()/feat() коммитов нет.
- Хелпер `_prepare_mid_gop_source` вынесен в hardware-тестах, чтобы не дублировать предусловия двух тестов.

## Self-Check: PASSED

Коммиты b164776, 2fdcee7, 6163321 существуют; `.claude/`, `HANDOFF.json`, `legacy/encode_av1_opus.sh` не закоммичены; `_OPEN_GOP_LEADING` в tests не найден.
