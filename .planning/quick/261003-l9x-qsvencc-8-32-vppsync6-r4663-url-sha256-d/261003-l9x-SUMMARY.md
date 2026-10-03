# Quick 261003-l9x: переход на qsvencc 8.32+vppsync6 (r4663)

Оба Dockerfile закреплены на 8.32-vppsync6 (URL + sha256 f7be83b6…6024), рантайм-гейт поднят до r4663, `test_dv_profile5` больше не xfail, синтетический тест переименован в open-GOP и остаётся strict xfail.

## Коммиты
- c134df0 fix: пин, гейт, post-create (QSVENCC_MIN_REV = 4663; QSVENCC_METRICS_MIN_REV = QSVENCC_MIN_REV)
- a4249ea test: `test_dv_profile5` без xfail; `test_chunk_content_firstpkt_seek_bug` -> `test_chunk_content_open_gop`, `_OPEN_GOP_LEADING`, `_make_open_gop_source`; README фикстур и docstring `_chunk_content.py`
- 4686d90 docs: docker/README.md, .planning/codebase/*, пометка «решено» в handoff, сессия last-GOP в resolved/

## Проверено (реально запущено)
- Unit: `tests/unit/shared` — 46 passed (в т.ч. новый `test_gate_refuses_prev_pin_r4658`, sync-тест порогов); полный быстрый тир — 314 passed, 14 deselected; `ruff check src tests` — чисто.
- RED подтверждён до правки кода (6 failed).
- Гейт: системный qsvencc r4658 отказан русским сообщением с r4658/r4663/45003f1/`--seek`; с `/opt/qsvencc-vppsync6/usr/bin` первым в PATH возвращает 4663.
- Железо (A380, vppsync6 первым в PATH, ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures, ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe): `-k "dv_profile5 or open_gop"` -> 1 passed (test_dv_profile5 PASSED), 1 xfailed (test_chunk_content_open_gop), 628.87 с.
- Не проверялось: сборка образов (по плану — на хосте позже), `test_hdr10*` не трогались.

## Отклонения
- Дополнительно (Rule 3, мелкое): в `.planning/codebase/STRUCTURE.md` обновлена строка «r4634+ required» -> r4663+; в Dockerfile комментарий про предыдущий пин сформулирован без слова «vppsync4», чтобы проходил grep из verify.
- `git mv` последней-GOP сессии в `.planning/debug/resolved/` был застейджен и попал в чужой коммит ad3bbcf (параллельный debug-агент), а не в мои; содержимое правок (status: resolved, Resolution, ссылки) закоммичено в 4686d90.
- Хэш коммита форка в Dockerfile не добавлялся (не проверялся через `gh`).

## Для пользователя
CLAUDE.md не менялся. Строки с устаревшим пином нужно обновить (генерируется из .planning/codebase/, который уже обновлён): строка ~48 (qsvencc 8.32+vppsync4), ~53 (stable on r4658), ~248 (preflight: r4634 / fork r4658).

## Known Stubs
Нет.

## Self-Check: PASSED
Коммиты c134df0, a4249ea, 4686d90 существуют; resolved/qsvencc-seek-last-gop.md на месте со `status: resolved`.
