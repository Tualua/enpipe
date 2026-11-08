---
phase: 10-frame-extraction-alignment
verified: 2026-11-08T13:00:00Z
status: passed
score: 6/6 must-haves verified
covered_files: [".planning/phases/10-frame-extraction-alignment/10-01-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-01-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-02-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-02-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-03-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-03-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-04-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-04-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-05-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-05-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-06-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-06-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-07-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-07-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-08-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-08-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-09-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-10-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-10-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-11-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-11-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-12-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-12-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-13-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-13-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-14-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-14-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-15-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-15-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-16-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-16-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-17-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-17-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-18-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-18-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-19-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-19-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-20-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-20-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-21-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-21-SUMMARY.md","src/enpipe/analysis/config.py","src/enpipe/analysis/frames.py","src/enpipe/analysis/model.py","src/enpipe/analysis/pair.py","src/enpipe/analysis/precheck.py","src/enpipe/analysis/report.py","src/enpipe/analysis/seek.py","tests/integration/test_hardware_real_media.py"]
covered_digest: "v4:sha256:49476a033467bcc450f0cc287a5eb359f24640fe5f47f4d0d58002da6dc11fbf"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 6/6
  gaps_closed:
    - "UAT 10 на реальной паре Young Sherlock на B50 выполнен оператором: pass (10-UAT.md тест 3, 10-HUMAN-UAT.md тест 10)"
    - "UAT 11 (флаги K после mkvmerge) закрыт автотестом на B50: 1 passed 2026-11-08 после WR-02"
  gaps_remaining: []
  regressions: []
---

# Фаза 10: отчёт повторной верификации после фиксов ревью

**Цель фазы:** Любой кадр N достаётся из источника и энкода точно по номеру, а пара до расчёта метрик проходит предпроверку (параметры, число кадров, `.scenes` и ключевые кадры, `--offset` по границам сцен) с громким отказом при несовпадении
**Проверено:** 2026-11-08T13:00:00Z
**Статус:** passed
**Повторная верификация:** да (после коммитов 9633450, 60e189c, b4c7fe7, 7122e87, 367d9cd, a22bc9e и завершения UAT)

## Итог

Цель достигнута. Фиксы ревью после 856b6d1 затрагивают только комментарии, docstring, ослабление верхней границы K в аппаратном тесте и зонд в `scratch/` (diff по `src`/`tests`: config.py, model.py, pair.py, precheck.py и test_hardware_real_media.py, по 2-40 строк); логика предпроверки не менялась. Единственный открытый пункт прошлого отчёта (UAT 10) закрыт оператором. Блокеров, гэпов и пунктов для человека нет.

## Прогоны, выполненные мной (не по SUMMARY)

| Проверка | Команда | Результат |
|---|---|---|
| Полный набор | `uv run pytest -q` | 808 passed, 18 deselected |
| Линтер | `uv run ruff check src tests` | All checks passed |
| Медиа-тир без GPU | `uv run pytest -q tests/integration/test_frames_media.py` | 18 passed |
| Остатки PSNR-выравнивания | grep `PointAlignment\|FileAlignment\|OFFSET_MANUAL\|align_` по `src tests scratch` | пусто; `align.py`, `test_align*` отсутствуют |
| Маркеры долга | grep `TODO\|FIXME\|XXX\|TBD` по файлам фазы | пусто |

GPU-тест `test_keyframe_flags_after_mkvmerge` лично не запускался (по условию задачи нельзя трогать GPU); принято из 10-UAT.md (тест 2: 1 passed на B50 2026-11-08, после WR-02).

## Наблюдаемые истины

| # | Истина (критерий ROADMAP) | Статус | Доказательство |
|---|---|---|---|
| 1 | SC1/ALN-01: кадр N по номеру, 10-бит без потерь, совпадает с framemd5 на синтетике, VFR, ненулевом start_time | VERIFIED | `seek.py::seek_time_for_frame`: `pts[n] - (pts[n]-pts[n-1])/2`, None при n=0; `frames.py` сверяет pts кадров через showinfo, `-copyts` для n=0; test_frames_media.py 18 passed |
| 2 | SC2/ALN-02: размер, fps, число кадров, теги, не-PQ — громкий отказ до метрик | VERIFIED | `precheck.check_pair` собирает все причины (DV P5, .obu, pts, размер, нечётный размер, pix_fmt, fps, теги, не-PQ, field_order, число кадров через check_offset); `check_pair_files` кадры не извлекает; `grab_frame_pair` отказывает при `not check.ok` |
| 3 | SC3/ALN-03 (пересмотр D-24): `.scenes` сверяется с энкодом, на верной паре ложных отказов нет | VERIFIED | `scenes_reasons` + `keyframe_reasons`; fail-closed при `enc_keyframes is None`; проводка `packet_table` -> `check_pair` в `pair.check_pair_files`; аппаратный автотест на реальных qsvencc+mkvmerge прошёл; UAT 10 на реальной паре Young Sherlock: pass |
| 4 | SC4/ALN-04 (D-26): частичный энкод без `--offset` — отказ с подсказкой; `--offset` только со `.scenes` и на границах сцен | VERIFIED | `check_offset` прочитан: без offset и без .scenes — отказ; `offset_hints` даёт «--offset K (сцены A..B)»; offset без .scenes — отказ; K не начало сцены / K+n_enc не конец сцены — отказ, обе причины вместе; UAT 10: подсказка «--offset 4737 (сцены 40..42)», с --offset 4737 ok, с --no-scenes отказ |
| 5 | SC5/ANL-03: без GPU и /dev/dri, не мешает кодированию | VERIFIED | программный декод в frames.py, префикс `nice -n 10`, лимит `-threads`; test_frames_media.py и test_isolation.py зелёные |
| 6 | D-24..D-27 полнота удаления PSNR-выравнивания | VERIFIED | `pair.py` 214 строк, `grab_frame_pair` берёт ровно два кадра (энкод N, источник N+K); grep на удалённые имена пуст |

**Счёт:** 6/6 истин подтверждено, 0 behavior-unverified.

## Покрытие требований

| Требование | План | Статус | Доказательство |
|---|---|---|---|
| ALN-01 | 10-01..10-04, 10-07 | SATISFIED | истина 1 |
| ALN-02 | 10-02, 10-03, 10-04 | SATISFIED | истина 2 |
| ALN-03 | 10-19..10-21 | SATISFIED кодом (в REQUIREMENTS.md стоит Pending, пересмотр D-24) | истина 3; формулировка в REQUIREMENTS.md уже переписана под сверку `.scenes`/ключевых кадров/числа кадров, код ей соответствует |
| ALN-04 | 10-19..10-21 | SATISFIED кодом (в REQUIREMENTS.md стоит Pending, D-26) | истина 4; соответствует переписанной формулировке |
| ANL-03 | 10-03, 10-04 | SATISFIED | истина 5 |

Осиротевших требований нет: все пять ID фазы заявлены планами. Рекомендация оператору (файл не правился): перевести ALN-03 и ALN-04 в Complete в REQUIREMENTS.md и в таблице трассировки.

## Антипаттерны

Маркеров TODO/FIXME/XXX/TBD и заглушек в файлах фазы нет. Ревью 3e1d064: 0 critical, 0 warning, 2 info (приняты в 10-REVIEW-DISPOSITION.md).

## Человеческая проверка

Не требуется: 10-UAT.md и 10-HUMAN-UAT.md в статусе complete, тесты 1-8 закрыты гэп-планами, тесты 10 и 11 pass.

## Резюме гэпов

Гэпов нет.

---

_Проверено: 2026-11-08T13:00:00Z_
_Верификатор: Claude (gsd-verifier)_
