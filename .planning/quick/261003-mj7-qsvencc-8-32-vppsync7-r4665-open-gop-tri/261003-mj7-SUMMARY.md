# Quick 261003-mj7: переход на qsvencc 8.32+vppsync7 (r4665), снятие защиты от open-GOP

Оба Dockerfile закреплены на 8.32-vppsync7 (URL + sha256 297d474c…6ac6), рантайм-гейт и порог в post-create подняты до r4665. Отказ для open-GOP источников и зонд ведущих кадров удалены: open-GOP защищает только глобальный fail-closed гейт. Open-GOP (RASL и RADL) вернулись в аппаратные тесты как положительная проверка содержимого.

## Коммиты
- 0b769b4 fix: пин, гейт r4665, post-create, docker/README, .planning/codebase/*
- 882fbae fix: удалены защита от open-GOP, probe_leading_frames, count_leading_after_keyframes, LEADING_PROBE_PACKETS и их тесты (seek/trim-математика не тронута)
- 8f19f11 test: test_chunk_content_open_gop[rasl|radl], test_chunk_content_closed_gop, test_hdr10 на open-GOP по умолчанию, README фикстур
- 7d285bf docs: HANDOFF помечен решённым, debug-сессия перенесена в resolved/ (status: resolved)

## Реально выполненные проверки
- Быстрый тир `uv run pytest`: 315 passed, 16 deselected; `uv run ruff check src tests`: чисто.
- `tests/unit/shared`: 47 passed (включая sync-тест порогов и новый test_gate_refuses_vppsync6_r4663).
- Живой гейт: `/opt/qsvencc-vppsync6` (r4663) отказан, rc=1, сообщение называет r4665, `--seek` и open-GOP `--trim`; `/opt/qsvencc-vppsync7` возвращает 4665.
- grep: символов зонда в src/, tests/unit, tests/subprocess нет; diff keyframes.py не затрагивает compute_chunk_seek_trim/kf_before/fmt_seek/keyframe_table.
- Полный аппаратный модуль (PATH=/opt/qsvencc-vppsync7/usr/bin, ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures, ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe, лог в scratchpad/hw.log): **13 passed, 0 failed, 0 skipped, 0 xfail за 1499.79 с (24:59)**.
  - test_dv_profile5 664.18 с, test_dv 441.30 с, test_hdr10plus 187.31 с, test_run_parity_vs_two_step 27.91 с
  - test_sdr_legacy_oracle_parity[metrics] 27.15 с / [no-metrics] 26.68 с
  - test_chunk_content_open_gop[rasl] 21.00 с, [radl] 20.71 с, test_chunk_content_closed_gop 20.82 с
  - test_hdr10[metrics] 16.72 с / [no-metrics] 16.02 с (теперь на open-GOP x265 по умолчанию), test_sdr[metrics] 14.96 с / [no-metrics] 14.66 с
- Не проверялось: сборка образов Docker (нет в окружении); sha256/URL сверены только с значениями из плана и sync-тестом.

## Решения
- Зонд удалён целиком (D-A); предусловие «у ключевого кадра есть ведущие кадры» живёт в тесте (`_leading_counts`, полный ffprobe-скан).
- Раскладка сцен 70/74/76/68: срезы 70 (mid-GOP), 144 (ровно на keyframe с ведущими), 220 (mid-GOP); предусловия через pytest.fail.

## Отклонения
- План ожидал 14 passed; фактически 13: было 12, минус test_open_gop_source_refused, плюс два параметра test_chunk_content_open_gop (12-1+2=13). Ошибка в арифметике плана, не пропуск теста; skip/xfail отсутствуют.
- Коммит 882fbae (удаление защиты) оставляет tests/integration/test_hardware_real_media.py с битым импортом до следующего коммита 8f19f11 (Rule 3, порядок задач); быстрый тир его не собирает (маркер hardware).
- CLAUDE.md не менялся (по условию): в нём остаются ссылки на vppsync6/r4663, его регенерирует оркестратор.

## Self-Check: PASSED
Коммиты 0b769b4, 882fbae, 8f19f11, 7d285bf есть в git log; debug-файл существует в resolved/, старого пути нет.
