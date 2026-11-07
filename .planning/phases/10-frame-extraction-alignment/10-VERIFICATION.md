---
phase: 10-frame-extraction-alignment
verified: 2026-11-07T19:05:00Z
status: human_needed
score: 6/7 must-haves verified
covered_files: [".planning/phases/10-frame-extraction-alignment/10-01-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-01-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-02-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-02-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-03-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-03-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-04-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-04-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-05-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-05-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-06-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-06-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-07-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-07-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-08-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-08-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-09-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-10-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-10-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-11-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-11-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-12-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-12-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-13-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-13-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-14-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-14-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-15-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-15-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-16-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-16-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-17-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-17-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-18-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-18-SUMMARY.md","src/enpipe/analysis/align.py","src/enpipe/analysis/frames.py","src/enpipe/analysis/pair.py","src/enpipe/analysis/precheck.py"]
covered_digest: "v4:sha256:d0731edf8473db53ae45c6d60b89a8d79192de18b04a678dda7d2c54a17a3d36"
behavior_unverified: 1
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/7
  gaps_closed:
    - "WR-11: конец окна частичного энкода при --offset сверяется с концами сцен (решение оператора, коммит 2c6e92c) — закрыт 10-18, коммит 6e16124"
    - "WR-12: тест битого кэша различает принятие кэша и пересчёт по keyframes — 10-18, коммит e4fa7d8"
    - "IN-22: UAT 11 получил верхнюю границу K-пакетов — 10-18, коммит 278404a"
  gaps_remaining: []
  regressions: []
behavior_unverified_items:
  - truth: "D-13/WR-10: сверка .scenes с ключевыми кадрами энкода не даёт ложного отказа на верной паре (опирается на допущение о флагах K после mkvmerge)"
    test: "UAT 11 на Arc B50 (команды в 10-HUMAN-UAT.md, тест 11)"
    expected: "число K-пакетов лежит в [число различных начал непустых сцен окна; Σ ceil(длина/GOP_LEN)] (Gravity Falls S01E01: [233; не больше 333]); keyframe_reasons и scenes_reasons пусты для полной пары (offset 0) и частичной (offset 4737)"
    why_human: "Допущение о расстановке флагов mkvmerge проверяется только на настоящем энкоде enpipe; тесты используют синтетику (Fake) и медиа-фикстуры без mkvmerge enpipe. Если флаг K стоит на каждом кадре, сверка молча пуста; если не стоит на началах сцен, WR-10 даёт ложный отказ"
human_verification:
  - test: "UAT 10 на Arc B50: полная пара с .scenes, частичный энкод без --offset, с --offset 4737"
    expected: "uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2 -> выровнено либо отказ со списком неопределённых точек; SRC.mkv ENC_PART.mkv -> отказ с подсказкой --offset 4737 (сцены 40..42); с --offset 4737 и .scenes -> выровнено либо отказ со списком точек, но никогда выровнено при незакрытой стороне склейки"
    why_human: "Нужны реальная пара и железо B50, запуск оператором. Синтетика и медиа-фикстуры не заменяют реальные HEVC/AV1 на ZFS-HDD"
  - test: "UAT 11 на Arc B50: флаги ключевых кадров энкода enpipe после mkvmerge (допущение WR-10)"
    expected: "см. behavior_unverified_items; вердикт «ВНЕ ГРАНИЦ» — сигнал оператору разобраться, а не доказательство дефекта"
    why_human: "Допущение о флагах mkvmerge не проверяется без реального энкода"
---

# Фаза 10: отчёт повторной верификации после гэп-плана 10-18

**Цель фазы:** Любой кадр N достаётся из источника и энкода точно по номеру, а пара до расчёта метрик проходит проверку выравнивания с громким отказом при любом сомнении.
**Проверено:** 2026-11-07T19:05:00Z
**Статус:** human_needed
**Повторная верификация:** да (прошлый отчёт gaps_found из-за WR-11 заменён)

## Итог

Все гэпы кода закрыты. WR-11 (решение оператора, коммит 2c6e92c) реализован в `precheck.check_offset` (коммит 6e16124) и подтверждён мной лично на живых вызовах, а не по SUMMARY. Блокеров корректности и открытых гэпов нет. Статус `human_needed`, а не `passed`, по честной причине: две проверки возможны только на реальном железе Arc B50 и ещё не выполнены оператором (UAT 10 и UAT 11). Особенно UAT 11: допущение о флагах ключевых кадров после mkvmerge, на котором стоит WR-10, на настоящем энкоде не подтверждено. Молча в `passed` я это не перевожу.

## Операторские факты (2026-11-07)

- Отклонение 1 плана 10-17 (мутацию M23 не поймал плановый тест, исполнитель добавил `test_packet_table_keyframes_decode_order_differs` и не остановился) принято оператором: остановка не требовалась.
- WR-11 решён оператором (коммит 2c6e92c), реализован планом 10-18 (коммит 6e16124).
- Железо: Intel Arc B50 (Battlemage); находки эпохи A380 ждут перепроверки (бэклог 999.7).
- UAT 10 и 11 требуют реального железа и запускаются оператором.

## Достижение цели

### Наблюдаемые истины

| # | Истина | Статус | Доказательство |
|---|--------|--------|----------------|
| 1 | SC1/ALN-01: кадр N по номеру, 10-бит без потерь (таблица pts, seek на полкадра раньше) | ✓ VERIFIED | `frames.py`; `tests/subprocess/analysis/test_frames.py` и медиа-тир зелёные (по ревью и 10-18: 22 passed); полный прогон 932 passed |
| 2 | SC2/ALN-02: размер, fps, число кадров, теги, не-PQ — отказ до метрик | ✓ VERIFIED | `precheck.check_pair` возвращает причины; `check_pair_files` отдаёт отказ до извлечения кадров; якоря в `test_precheck.py` зелёные |
| 3 | SC3/ALN-03: несколько точек, склейки, три исхода; сдвиг -> отказ; обе стороны склейки закрыты до «выровнено» | ✓ VERIFIED (код и тесты); реальная пара — UAT 10 | якоря CR-02 в `test_pair.py` зелёные в полном прогоне; повторов и замен хватает по D-13 |
| 4 | SC4/ALN-04: частичный энкод без `--offset` -> отказ с подсказкой; с `--offset` — сравнение по окну | ✓ VERIFIED | живой вызов `check_offset(96,40,None,S4)` -> отказ «ни один непрерывный диапазон сцен…»; `(96,48,None,S4)` -> подсказки «--offset 0 (сцены 0..1), --offset 24 (сцены 1..2), --offset 48 (сцены 2..3)»; `(96,96,None,S4)` -> `(0, None, [], [])` |
| 5 | SC5/ANL-03: без GPU, не мешает кодированию | ✓ VERIFIED | `frames.py` — программный декод без QSV (nice/threads); `test_frames.py` зелёный |
| 6 | D-13/WR-10: `.scenes` сверяются со структурой и ключевыми кадрами энкода (отказ D-20), в том числе при полном энкоде | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Код есть и подключён: `precheck.scenes_reasons`/`keyframe_reasons`, вызов из `check_pair_files`; якоря на Fake проверяют `f.calls == []`. Но допущение о флагах K после mkvmerge на реальном энкоде enpipe не подтверждено, см. UAT 11 |
| 7 | D-13/WR-11 (решение оператора): при `--offset` K + n_enc — конец какой-либо сцены, иначе отказ D-20 | ✓ VERIFIED | `precheck.py:172-184`; мои живые вызовы ниже |

**Счёт:** 6/7 (истины 1-5 и 7 VERIFIED, истина 6 присутствует и подключена, поведение на реальном энкоде не подтверждено). `behavior_unverified: 1`.

### Живая проверка WR-11 (S4 = [(0,24),(24,48),(48,72),(72,96)], n_src = 96)

| Вызов `check_offset(96, n_enc, offset, S4)` | Результат | Ожидание |
|---|---|---|
| offset=24, n_enc=40 | отказ: «энкод кончается на кадре источника 64, это не конец ни одной сцены…» | отказ ✓ |
| offset=24, n_enc=30 | отказ (конец 54) | отказ ✓ |
| offset=0, n_enc=90 | отказ (конец 90) | отказ ✓ |
| offset=24, n_enc=48 | `(24, 'scenes', [], [])` | ok ✓ |
| offset=24, n_enc=72 | `(24, 'scenes', [], [])` | ok ✓ |
| offset=0, n_enc=96 | `(0, 'scenes', [], [])` | ok ✓ |
| offset=30, n_enc=40 | две причины, начало первой (D-20) | ✓ |
| offset=24, n_enc=40, без .scenes | `(24, 'manual', [], ['сдвиг задан вручную, по .scenes не проверен'])` | D-08 не изменён ✓ |
| scenes [(0,24),(24,24),(24,96)], offset=0, n_enc=24 | ok (сцена нулевой длины) | ✓ |

Асимметрия между путями с `--offset` и без него устранена: несогласованный энкод отвергается на обоих путях. Пути без `--offset` и без `.scenes` не изменились (сверено с таблицей выше).

### Закрепление WR-12

`test_pts_cache_corrupt_recomputed` (`tests/subprocess/analysis/test_frames.py:346-358`) параметризован 10 вариантами, кэш пишется с `(0,)`, пересчёт отдаёт `(0, 1)`, проверка идёт через `frames.packet_table`: принятый битый кэш виден. Остаточная слабость IN-26 (вариант `[1, 0]` после «починки» сортировкой даёт тот же ответ) — Info, не блокер: кэш пишет сам enpipe, ключ по пути, размеру и mtime.

### Артефакты и связи

| Артефакт / связь | Статус | Детали |
|---|---|---|
| `precheck.check_offset` | ✓ VERIFIED, WIRED | обе причины собираются вместе, причина начала первая |
| `check_pair_files` -> `precheck.check_pair` -> `check_offset` | WIRED | причины `--offset` идут в reasons и отключают сверку ключевых кадров; tracer `test_partial_window_end_refused` |
| `align.py`, `pair.py`, `frames.py` | ✓ VERIFIED, WIRED | не менялись после прошлой проверки в `src/` кроме `precheck.py` |
| `10-HUMAN-UAT.md` тест 11 | ✓ обновлён | границы [нижняя; верхняя], готовые команды, «ВНЕ ГРАНИЦ» как сигнал оператору |

Data-flow (уровень 4): точки идут из реального извлечения кадров `frames.grab`, статических заглушек нет. Debt-маркеры (TBD/FIXME/XXX) в `src/enpipe/analysis` не найдены.

### Поведенческие проверки

| Поведение | Команда | Результат | Статус |
|---|---|---|---|
| Весь набор | `uv run pytest -q` | 932 passed, 17 deselected | ✓ PASS |
| Линтер | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| WR-11, 12 вызовов | прямой вызов `check_offset` | таблица выше | ✓ PASS |

Пробы (Step 7c): `probe-*.sh` у фазы нет, шаг пропущен. Медиа-тир (`-m ""`) я не запускал, опираюсь на 22 passed из 10-18-SUMMARY и ревью. Рабочее дерево `src/` и `tests/` чистое; `/data` не трогал.

### Покрытие требований

| Требование | Статус | Доказательство |
|---|---|---|
| ALN-01 | ✓ SATISFIED | истина 1; кэш закреплён тестом (WR-12) |
| ALN-02 | ✓ SATISFIED | истина 2 |
| ALN-03 | ✓ SATISFIED в коде; реальная пара — UAT 10 | истины 3, 6 |
| ALN-04 | ✓ SATISFIED | истины 4 и 7, оба края окна проверяются |
| ANL-03 | ✓ SATISFIED | истина 5 |

Все 5 ID фазы есть в REQUIREMENTS.md (строки 14, 19-22; трассировка 91-95, Complete) и заявлены планами (10-18: ALN-01, ALN-03, ALN-04). Осиротевших требований нет.

### Антипаттерны и открытые замечания

Ревью после 10-18: 0 critical, 0 warning, 15 info; все открыты в 10-REVIEW-DISPOSITION.md (не решены оператором, не блокеры).

| Пункт | Серьёзность | Заметка |
|---|---|---|
| IN-26 | Info | тест битого кэша не ловит «починку вместо отказа» (`[1, 0]`); мутация даёт 54/54 зелёных |
| IN-03 (шире) | Info | `offset_hints` теряет окно после сцены нулевой длины; после WR-11 подсказки расходятся с явным `--offset` (328 из 20 000 раскладок). Влияет на подсказку, не на ложное «выровнено» |
| IN-23 | Info | нечитаемый `.scenes` становится «без .scenes» (фаза 11) |
| IN-24, IN-25 и др. | Info | читаемость, робастность текста |

## Что нужно человеку

### 1. UAT 10: повторный прогон на Arc B50 после CR-02 и WR-10

**Test:** три команды из 10-HUMAN-UAT.md (тест 10): полная пара `--jobs 1,2`; частичный энкод без `--offset`; с `--offset 4737`.
**Expected:** «выровнено» или отказ со списком точек; без `--offset` отказ с подсказкой «--offset 4737 (сцены 40..42)»; никогда «выровнено» при незакрытой стороне склейки.
**Why human:** реальная пара и железо.

### 2. UAT 11: флаги ключевых кадров после mkvmerge (допущение WR-10)

**Test:** готовые команды из 10-HUMAN-UAT.md (тест 11) для Gravity Falls S01E01 (offset 0) и частичной пары (offset 4737).
**Expected:** число K-пакетов в [233; не больше 333] для полной пары; `scenes_reasons` и `keyframe_reasons` пусты на верных парах. «ВНЕ ГРАНИЦ» — повод разобраться (все кадры K или флаги не на началах сцен), а не доказательство дефекта.
**Why human:** допущение о mkvmerge проверяется только на реальном энкоде; при провале WR-10 даёт ложный отказ на верной паре (громко, не тихо) либо сверка пуста.

## Резюме

Цель достигнута в коде: кадр по номеру, предпроверка с отказом, три исхода, обе стороны склейки, сверка `.scenes` и теперь оба края окна `--offset`. Открытых гэпов нет. Статус `human_needed` из-за двух непроведённых UAT на B50; их результат решает, станет ли фаза `passed`. До результата UAT 11 истина 6 числится «присутствует, поведение не подтверждено».

---

_Verified: 2026-11-07T19:05:00Z_
_Verifier: Claude (gsd-verifier)_
