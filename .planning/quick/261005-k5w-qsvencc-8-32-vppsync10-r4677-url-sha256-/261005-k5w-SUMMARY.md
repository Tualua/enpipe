# Quick 261005-k5w: qsvencc 8.32-vppsync10 (r4677) + патченный vpl-gpu-rt Summary

**Итог:** qsvencc закреплён на форке Tualua 8.32-vppsync10 (r4677) в обоих Dockerfile, гейт и post-create требуют r4677; ставится патченный vpl-gpu-rt 26.3.2-av1auxdata (`/opt/vpl-gpu-rt-av1auxdata`, `ONEVPL_PRIORITY_PATH` в обоих образах и в containerEnv). Блокеров нет: без опции вывод побайтно как у стокового.

## Коммиты

- `de15134` feat: пин qsvencc vppsync10, порог 4677 (гейт, оба Dockerfile, post-create), тесты (FIXED r4677, отказ r4665 и r4669)
- `810945c` feat: блок vpl-gpu-rt 26.3.2-av1auxdata с защитой версии libmfx-gen1.2, ENV/containerEnv, страж `test_vpl_runtime_pin_sync.py`
- `25f4d5a` docs: PROJECT.md, CLAUDE.md, docker/README.md, .planning/codebase/*, проза тестов

## Реально выполненные проверки

- sha256 локальных .deb (5f42839f…1060) и tar (054b7887…0a35) сверены до установки.
- Локально: `qsvencc --version` -> `8.32 (r4677)`, dpkg `8.32+vppsync10`; `/opt/vpl-gpu-rt-av1auxdata/lib/libmfx-gen.so.1.2` существует; системный libmfx-gen1.2 = `26.3.2-1~24.04~ppa1`.
- Гейт: `ensure_qsvencc_fixed()` на r4677 возвращает 4677; живой отказ на r4669 (`/opt/qsvencc-vppsync9`), rc=1, текст называет r4677.
- Быстрый тир: `uv run pytest -q` -> 359 passed, 17 deselected (22 с); `uv run ruff check src tests` -> All checks passed. `tests/unit/shared` -> 66 passed (включая sync-тест порога и новый страж runtime-пина). RED подтверждён: 7 тестов гейта и 6 тестов стража падали до правок.
- A380 п.4а (источник: testsrc2 1280x720@24, 4 с, libx265 yuv420p10le; команда `qsvencc --avhw -i src.mkv -c av1 --icq 23 -o OUT.obu`): sha256 stock1 = stock2 = patched = `0c45fb9c…600ef`; `cmp` stock1==stock2 и stock1==patched. Загрузка патченного runtime подтверждена `strace -e openat`: с priority path открывается `/opt/vpl-gpu-rt-av1auxdata/lib/libmfx-gen.so.1.2.17`, без него — `/usr/lib/x86_64-linux-gnu/libmfx-gen.so.1.2.17`. Условие СТОП не сработало.
- A380 п.4б: с `ONEVPL_PRIORITY_PATH` и `--av1-chroma-delta-q -32` rc=0, в логе `AV1 Chroma dQ  dc -32, ac -32 (experimental)`, trace_headers показывает `delta_q_u_dc/ac.delta_q = -32` в кадрах; без priority path rc=241 и сообщение «requires a vpl-gpu-rt runtime patched to accept MFX_EXTBUFF_AV1_AUXDATA».
- Аппаратный тир с `ONEVPL_PRIORITY_PATH`, qsvencc r4677: `tests/integration/test_hardware_real_media.py` — 13 passed за 1142 с (19:02; включая sdr/hdr10 с метриками и без, dv, dv_profile5, hdr10plus, chunk_content rasl/radl/closed); `test_concurrency_immunity.py -k qsvencc_immune` — 2 passed за 241 с.

## Не проверено

- Образы Docker не собирались (решение оператора): RUN-блоки vpl-gpu-rt, защита версии `case "$v" in 26.3.2-*)` и ENV проверены только чтением и стражем, не сборкой.
- containerEnv `ONEVPL_PRIORITY_PATH` подействует только после пересборки контейнера; в этой сессии переменная выставлялась явно в каждой команде.

## Stale-grep (4665 / vppsync7 / 297d474c) — остались только исторические ссылки

- литерал r4665 (vppsync7) в отказе гейта и его докстринге/комментарии (`qsvencc_version.py:15,56,118`) и в `test_qsvencc_version.py` (отказы vppsync6/vppsync7);
- происхождение open-GOP-фикса: `pipeline.py:195-196`, `_chunk_content.py:7`, `tests/fixtures/media/README.md:113`, `test_hardware_real_media.py:32,411,1135`;
- замер `chunk.py:39`; цепочка порогов `PROJECT.md:122`; запись о патчах в `INTEGRATIONS.md:55`.

## Отклонения от плана

Нет. Мелкое уточнение: `-c av1` вместо `--codec` для qsvencc (как в `chunk_command`). Дрейфа допущений нет.

## Решения

- Открытая проверка версии libmfx-gen1.2 сделана через `case` с префиксом, чтобы не задеть regex `-ge/-lt` стража порога.
- Литерал r4665 в тексте отказа сохранён намеренно (атрибуция open-GOP-дефекта), остальные пороги интерполируются из `QSVENCC_MIN_REV`.
- `--av1-chroma-delta-q` enpipe не использует (CAL-02, v1.3); `src/` не упоминает `ONEVPL_PRIORITY_PATH`.

## Self-Check: PASSED

Коммиты de15134, 810945c, 25f4d5a существуют; файлы `tests/unit/shared/test_vpl_runtime_pin_sync.py` и этот SUMMARY созданы.
