---
phase: 10-frame-extraction-alignment
verified: 2026-11-07T18:20:00Z
status: gaps_found
score: 6/7 must-haves verified
has_blocking_gaps: false
covered_files: [".planning/phases/10-frame-extraction-alignment/10-01-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-01-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-02-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-02-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-03-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-03-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-04-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-04-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-05-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-05-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-06-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-06-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-07-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-07-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-08-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-08-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-09-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-10-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-10-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-11-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-11-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-12-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-12-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-13-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-13-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-14-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-14-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-15-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-15-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-16-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-16-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-17-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-17-SUMMARY.md","src/enpipe/analysis/align.py","src/enpipe/analysis/frames.py","src/enpipe/analysis/pair.py","src/enpipe/analysis/precheck.py"]
covered_digest: "v4:sha256:801b0052c6313bc68a591e9ddbac8d1f7c31182e96b0dd1c0f22447b88986210"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "CR-02: каждую сторону склейки (start-1 и start) закрывает своя сцена — закрыт 10-16"
    - "WR-10: .scenes сверяются со структурой источника и ключевыми кадрами энкода (вариант B), в том числе при полном энкоде — закрыт 10-17"
    - "IN-21, IN-20: инвариант pick_points закреплён тестом, формулировка исправлена — 10-16"
  gaps_remaining:
    - "WR-11: конец окна частичного энкода при --offset не сверяется с границей сцены (решение оператора принято, не реализовано)"
  regressions: []
gaps:
  - truth: "D-13 подпункт WR-11 (решение оператора 2026-11-07, коммит 2c6e92c): при --offset и непустых .scenes K + n_enc обязан быть концом какой-либо сцены, иначе отказ D-20"
    status: failed
    reason: "check_offset (precheck.py:156-168) проверяет только начало окна. Воспроизведено мной лично на S4=[(0,24),(24,48),(48,72),(72,96)], n_src=96: offset=24,n_enc=40 -> ok (окно кончается на 64 внутри сцены); offset=24,n_enc=30 -> ok; offset=0,n_enc=90 -> ok; тот же n_enc=40 без --offset -> отказ. Асимметрия: несогласованность .scenes с энкодом отвергается без --offset и молча принимается с ним."
    artifacts:
      - path: "src/enpipe/analysis/precheck.py"
        issue: "check_offset: ветка с заданным offset не проверяет offset + n_enc in {e for _, e in scenes}"
    missing:
      - "Проверка конца окна в check_offset с причиной D-20 (текст в 10-REVIEW.md WR-11)"
      - "Якоря: offset=24,n_enc=40 -> отказ; offset=24,n_enc=48 -> ok; мутация, убирающая именно проверку конца"
      - "Закрыть новым гэп-планом 10-18"
    severity_note: "Ложного «выровнено» сам по себе не даёт: сверка ключевых кадров (10-17) остаётся главным барьером, независимая проверка CR-02/CR-01 держится. Поэтому не блокер корректности вывода, но реализация решения оператора ещё не сделана."
warnings:
  - id: WR-12
    note: "Тест битого кэша T-10-44 (варианты keyframes) не различает принятие кэша и пересчёт; мутация «без проверки keyframes в _read_cache» оставляет тесты зелёными. Кэш с [True] даст {True}=={1}. Заявленная защита не закреплена тестом (10-REVIEW.md WR-12)."
  - id: IN-22
    note: "UAT 11 не отличит верные флаги mkvmerge от флага K на каждом кадре (тогда сверка WR-10 молча пуста); нужна верхняя граница в UAT 11."
deferred: []
human_verification:
  - test: "UAT 10 на Arc B50: полная пара с .scenes, частичный энкод без --offset, с --offset 4737"
    expected: "uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2 -> выровнено либо отказ со списком неопределённых точек; SRC.mkv ENC_PART.mkv -> отказ с подсказкой --offset 4737; с --offset 4737 и .scenes -> выровнено 5/5 или отказ, но не выровнено при незакрытой стороне склейки"
    why_human: "Нужна реальная пара и железо B50; запускает оператор. Синтетика (Fake) реальных HEVC/AV1 на ZFS-HDD не заменяет"
  - test: "UAT 11 на B50: флаги ключевых кадров энкода enpipe после mkvmerge (допущение WR-10)"
    expected: "scenes_reasons и keyframe_reasons пусты для полной пары (offset 0) и частичной (offset 4737); число K-пакетов не меньше числа сцен, но и заметно меньше числа кадров (IN-22)"
    why_human: "Допущение о флагах mkvmerge проверяется только на настоящем энкоде; при непустом keyframe_reasons на верной паре WR-10 даёт ложный отказ"
---

# Фаза 10: отчёт повторной верификации после гэп-планов 10-16 и 10-17

**Цель фазы:** Любой кадр N достаётся из источника и энкода точно по номеру, а пара до расчёта метрик проходит проверку выравнивания с громким отказом при любом сомнении.
**Проверено:** 2026-11-07T18:20:00Z
**Статус:** gaps_found
**Повторная верификация:** да (прошлый отчёт gaps_found из-за CR-02 и WR-10 заменён)

## Итог

CR-02 и WR-10 закрыты в коде, а не только в SUMMARY. Блокеров корректности нет: ложного «выровнено» на сдвинутом чанке я не нашёл. Остаётся один открытый пункт с решением оператора, которое ещё не реализовано: WR-11 (конец окна при `--offset`). Из-за него статус `gaps_found`: его закроет новый гэп-план 10-18. Это не блокер вердикта выравнивания, но и не «passed»: решение оператора по D-13 в коде отсутствует. Два теста UAT (10, 11) ждут оператора на B50.

## Достижение цели

### Наблюдаемые истины

| # | Истина | Статус | Доказательство |
|---|--------|--------|----------------|
| 1 | SC1/ALN-01: кадр N по номеру, 10-бит без потерь, совпадает с framemd5 (VFR, ненулевой start_time) | ✓ VERIFIED | `frames.py` (таблица pts, seek на полкадра раньше); медиа-тир `test_frames_media.py` 22 passed по ревью; полный pytest 917 passed |
| 2 | SC2/ALN-02: размер, fps, число кадров, теги, не-PQ — громкий отказ до метрик | ✓ VERIFIED | `precheck.check_pair` возвращает причины, `check_pair_files` отдаёт `_refused` до извлечения кадров (`pair.py`, ветка `if verdict.reasons`); якоря в `test_precheck.py` зелёные |
| 3 | SC3/ALN-03: несколько точек, склейки, три исхода; сдвиг -> отказ; «выровнено» не при сомнении, включая обе стороны склейки | ✓ VERIFIED | `_point_worker` (`pair.py:272-360`): сторона открыта, пока половина не «выровнено»; цель закрыта, только когда закрыты все открытые стороны; «сдвиг» на любой стороне — итог. Якоря `test_junction_prev_side_refused/_shift/_no_room`, `test_junction_start_side_only_refused`, `test_junction_both_sides_start_closed_refused` проходят (32 passed в моём прогоне по фильтру junction/scenes/keyframes). Фаззер ревью: 12 000 прогонов, 743 `ok True`, 0 нарушений |
| 4 | SC4/ALN-04: частичный энкод без `--offset` -> отказ с подсказкой; с `--offset` сравнение по началу окна | ✓ VERIFIED (по формулировке SC), см. гэп WR-11 | Лично: n_enc=40 без offset -> отказ «ни один непрерывный диапазон…»; offset=24,n_enc=48 -> ok. Конец окна не сверяется — отдельная истина 6 |
| 5 | SC5/ANL-03: без GPU и /dev/dri, не мешает кодированию | ✓ VERIFIED | `frames.py:8-30` — программный декод, nice/threads, без QSV; тесты `tests/subprocess/analysis/test_frames.py` зелёные |
| 6 | D-13/WR-10: `.scenes` сверяются со структурой и ключевыми кадрами энкода (отказ D-20), в том числе при полном энкоде | ✓ VERIFIED | `precheck.scenes_reasons`/`keyframe_reasons` (`precheck.py:176-231`), вызов `pair.py:409-427` до извлечения кадров; якоря проверяют `f.calls == []` |
| 7 | D-13/WR-11 (решение оператора 2026-11-07): при `--offset` K + n_enc — конец какой-либо сцены, иначе отказ D-20 | ✗ FAILED (не реализовано) | Лично воспроизведено: `check_offset(96, 40, 24, S4)` -> `(24, 'scenes', [], [])`, то есть ok; то же для n_enc=30 и для offset=0,n_enc=90. Код `precheck.py:158-168` проверяет только `offset in {s for s,_}`. В истории нет коммита реализации (HEAD 2c6e92c — только CONTEXT) |

**Счёт:** 6/7 (истины 1-6 VERIFIED, истина 7 FAILED).

### Классификация WR-11 (честно)

- В 10-REVIEW.md это WARNING: ложного «выровнено» не даёт, сверка ключевых кадров остаётся главным барьером.
- Решения оператора нет в 10-CONTEXT.md до 2c6e92c, теперь есть (D-13 подпункт WR-11), реализации нет. Поэтому это открытый гэп, а не принятое отклонение. Overrides не применялись, обходом это не закрываю.
- Асимметрия реальна: без `--offset` несогласованный энкод отказывается, с `--offset` принимается.

## Операторские факты (2026-11-07)

- Отклонение 1 плана 10-17 (мутация M23 не поймана плановым тестом; исполнитель добавил `test_packet_table_keyframes_decode_order_differs`, а не остановился) — оператор подтвердил: допустимо, остановка не требовалась.
- WR-11 — решение оператора: проверять конец окна, отказ D-20; записано в 10-CONTEXT.md (коммит 2c6e92c); не реализовано; закрывать планом 10-18.
- Железо — Intel Arc B50; находки эпохи A380 ждут перепроверки; UAT 10 и 11 требуют реального железа, запускает оператор.

## Артефакты и связи

| Артефакт / связь | Статус | Детали |
|---|---|---|
| `align.py` (`junction_prev_retry_frames`, `junction_retry_frames`, `pick_points`) | ✓ VERIFIED, WIRED | вызываются из `_point_worker`; `n_enc` в `junction_prev_retry_frames` не используется (IN-25, информационно) |
| `pair.py` (`_measure_target`, `_point_worker`, `check_pair_files`) | ✓ VERIFIED, WIRED | половины склейки из одного grab; предпроверка до кадров |
| `precheck.py` (`scenes_reasons`, `keyframe_reasons`, `check_offset`) | ✓ кроме конца окна | `check_offset` без проверки конца — WR-11 |
| `frames.py` (`packet_table`, кэш версии с keyframes) | ✓ VERIFIED | валидация кэша не закреплена тестом (WR-12) |
| `check_pair_files` -> `precheck.check_pair(enc_keyframes=…)` | WIRED | `pair.py:409-427` |

Data-flow (уровень 4): точки идут из реального извлечения кадров через `frames.grab`; заглушек нет. Debt-маркеры TBD/FIXME/XXX в изменённых файлах не искались как блокеры: ruff чист, ревью упоминаний не отмечает.

## Поведенческие проверки

| Поведение | Команда | Результат | Статус |
|---|---|---|---|
| Весь набор | `uv run pytest -q` | 917 passed, 17 deselected | ✓ PASS |
| Линтер | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| Якоря склейки/WR-10 | `pytest tests/unit/analysis/test_pair.py -k "junction or pick_points_ordinary or scenes_ or keyframes"` | 32 passed | ✓ PASS |
| WR-11 | `precheck.check_offset(96, 40, 24, S4)` | ok без причин | ✗ FAIL (ожидался отказ) |

Пробы (Step 7c): документированных probe-*.sh у фазы нет, шаг пропущен.

## Покрытие требований

| Требование | Статус | Доказательство |
|---|---|---|
| ALN-01 | ✓ SATISFIED | истина 1 |
| ALN-02 | ✓ SATISFIED | истина 2 |
| ALN-03 | ✓ SATISFIED | истины 3 и 6; CR-02/WR-10 закрыты |
| ALN-04 | ✓ SATISFIED по SC4 / частично по D-13 WR-11 | начало окна проверяется, конец — гэп |
| ANL-03 | ✓ SATISFIED | истина 5 |

Все 5 ID фазы присутствуют в REQUIREMENTS.md (строки 14, 19-22; трассировка 91-95, Complete). Осиротевших требований нет.

## Антипаттерны и оставшиеся замечания

| Пункт | Серьёзность | Заметка |
|---|---|---|
| WR-11 | Warning (гэп по решению оператора) | см. выше |
| WR-12 | Warning | тест кэша ничего не различает; зелёный при мутации |
| IN-22 | Info | верхняя граница K-пакетов в UAT 11 |
| IN-23 | Info | нечитаемый `.scenes` превращается в «без .scenes» — для фазы 11 |
| IN-24 | Info | `_point_worker` ~90 строк |
| IN-02..IN-09, IN-16..IN-19, IN-25 | Info | текст/робастность, поведение цели не затрагивают |

Расписание ревью 10-REVIEW-DISPOSITION.md: все 17 находок `open`.

## Что нужно человеку

1. Гэп-план 10-18 по WR-11 (решение принято): проверка конца окна + якоря `offset=24,n_enc=40` отказ / `n_enc=48` ok + мутация на проверку конца. Желательно в том же плане закрыть WR-12 (по решению оператора отдельным вопросом).
2. UAT 10 и UAT 11 на B50 (команды в 10-HUMAN-UAT.md); для UAT 11 добавить верхнюю границу K-пакетов (IN-22).
3. Если оператор хочет не ждать 10-18, он может принять WR-11 через override; сам я его не предлагаю: решение оператора — реализовать.

## Резюме гэпов

Ядро цели достигнуто: извлечение по номеру, предпроверка, три исхода, обе стороны склейки, сверка `.scenes`. Единственный реальный разрыв — зеркальная сторона окна `--offset` (WR-11), по которому решение уже есть, а кода нет.

---

_Verified: 2026-11-07T18:20:00Z_
_Verifier: Claude (gsd-verifier)_
