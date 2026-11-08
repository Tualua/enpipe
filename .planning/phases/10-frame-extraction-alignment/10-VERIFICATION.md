---
phase: 10-frame-extraction-alignment
verified: 2026-11-08T12:00:00Z
status: human_needed
score: 6/6 must-haves verified
covered_files: [".planning/phases/10-frame-extraction-alignment/10-01-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-01-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-02-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-02-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-03-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-03-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-04-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-04-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-05-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-05-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-06-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-06-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-07-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-07-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-08-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-08-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-09-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-10-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-10-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-11-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-11-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-12-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-12-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-13-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-13-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-14-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-14-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-15-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-15-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-16-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-16-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-17-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-17-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-18-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-18-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-19-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-19-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-20-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-20-SUMMARY.md",".planning/phases/10-frame-extraction-alignment/10-21-PLAN.md",".planning/phases/10-frame-extraction-alignment/10-21-SUMMARY.md","src/enpipe/analysis/config.py","src/enpipe/analysis/frames.py","src/enpipe/analysis/model.py","src/enpipe/analysis/pair.py","src/enpipe/analysis/precheck.py","src/enpipe/analysis/report.py","src/enpipe/analysis/seek.py","tests/integration/test_hardware_real_media.py"]
covered_digest: "v4:sha256:a5495ad10cf70371ac0793d5ff02504e3939e7a638afa0bee677a491a0807900"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 6/7
  gaps_closed:
    - "G-10-1: ложный отказ PSNR-выравнивания на верной паре — проверка убрана целиком (D-24..D-27), планы 10-19, 10-20"
    - "G-10-2: допущение WR-10 о флагах K после mkvmerge проверяется автотестом на B50 (D-28), план 10-21"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "UAT 10 (10-HUMAN-UAT.md, тест 10): реальная пара Young Sherlock S01E01 на B50"
    expected: "полная пара со .scenes: ok True, причин нет; частичный энкод без --offset: отказ с подсказкой «--offset 4737 (сцены 40..42)»; с --offset 4737 и .scenes: ok True, источник offset=scenes; с --offset 4737 и --no-scenes: ok False с причиной «задан без .scenes» (D-26); нигде нет причины «.scenes не совпадают с энкодом»"
    commands: |
      uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --check-only
      uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only
      uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737
      uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737 --no-scenes
    why_human: "Нужны реальные файлы оператора (HEVC/AV1 на ZFS-HDD), в репозитории их нет; синтетика и медиа-фикстуры воспроизводят модель Young Sherlock, но не сами файлы"
---

# Фаза 10: отчёт повторной верификации после гэп-планов 10-19, 10-20, 10-21

**Цель фазы:** Любой кадр N достаётся из источника и энкода точно по номеру, а пара до расчёта метрик проходит предпроверку (параметры, число кадров, `.scenes` и ключевые кадры, `--offset` по границам сцен) с громким отказом при несовпадении
**Проверено:** 2026-11-08T12:00:00Z
**Статус:** human_needed
**Повторная верификация:** да (предыдущий отчёт от 2026-11-07 заменён)

## Итог

Цель достигнута в коде. Решения оператора D-24..D-28 реализованы: PSNR-выравнивание удалено из рабочего пути (`align.py` и `test_align.py` отсутствуют, в `src/`, `tests/`, `scratch/` нет ссылок на `PointAlignment`, `FileAlignment`, `OFFSET_MANUAL`, `align_*`). Предпроверка работает без извлечения кадров. Блокеров и открытых гэпов нет. Статус `human_needed` остаётся по одной причине: UAT 10 на реальной паре Young Sherlock ещё не выполнен оператором. Допущение WR-10 (UAT 11) закрыто автотестом, который я перезапустил лично.

## Проверенные мной прогоны (не по SUMMARY)

| Проверка | Команда | Результат |
|---|---|---|
| Полный набор | `uv run pytest -q` | 808 passed, 18 deselected |
| Линтер | `uv run ruff check src tests` | All checks passed |
| Медиа-тир без GPU (ALN-01, ANL-03) | `uv run pytest -q tests/integration/test_frames_media.py` | 18 passed |
| Допущение WR-10 на B50 (G-10-2) | `uv run pytest -q -rs -m hardware tests/integration/test_hardware_real_media.py -k keyframe_flags` | 1 passed, без SKIPPED (4.55 с) |

## Достижение цели

### Наблюдаемые истины

| # | Истина (критерий ROADMAP) | Статус | Доказательство |
|---|---|---|---|
| 1 | SC1/ALN-01: кадр N по номеру, 10-бит без потерь, совпадает с framemd5 на синтетике, VFR, ненулевой start_time | ✓ VERIFIED | `seek.py::seek_time_for_frame` (полкадра раньше по таблице pts), `frames.py`; `test_frames_media.py` 18 passed; `test_seek.py` в полном прогоне |
| 2 | SC2/ALN-02: размер, fps, число кадров, теги, не-PQ — отказ до метрик | ✓ VERIFIED | `precheck.check_pair` собирает все причины (DV, .obu, pts, размер, pix_fmt, fps, теги, PQ, field_order); `check_pair_files` не извлекает кадры; тесты `test_precheck.py` зелёные |
| 3 | SC3/ALN-03 (пересмотр D-24): `.scenes` сверяется с энкодом (порядок, непрерывность, ключевые кадры), на верной паре энкода enpipe ложных отказов нет | ✓ VERIFIED (код и автотест); реальная пара — UAT 10 | `precheck.scenes_reasons`, `keyframe_reasons`, fail-closed при `enc_keyframes is None`; вызов из `check_pair` и `pair.check_pair_files`; аппаратный тест на настоящем qsvencc+mkvmerge прошёл: `keyframe_reasons` пуст, `check_pair_files` ok на полной и частичной паре |
| 4 | SC4/ALN-04 (D-26): частичный энкод без `--offset` — отказ с подсказкой; `--offset` только со `.scenes` и только на границах сцен | ✓ VERIFIED | `precheck.check_offset` (прочитано): без offset и без `.scenes` отказ; `offset_hints` даёт «--offset K (сцены A..B)»; offset без `.scenes` — отказ D-26; K не начало сцены или K+n_enc не конец сцены (WR-11) — отказ, обе причины вместе; тот же аппаратный тест подтверждает подсказку на реальном энкоде |
| 5 | SC5/ANL-03: без GPU и `/dev/dri`, не мешает кодированию | ✓ VERIFIED | `frames.py` — программный декод, nice/threads; `test_frames_media.py` и `test_isolation.py` зелёные |
| 6 | D-24 полнота удаления: PSNR-выравнивания в рабочем пути нет | ✓ VERIFIED | `pair.py` (214 строк): только probe, packet_table, precheck, `grab_frame_pair` с ровно двумя кадрами (энкод N, источник N+K, D-27); в `report.py` нет раздела выравнивания, `test_no_alignment_section` есть; grep по `src tests scratch` на удалённые имена пуст |

**Счёт:** 6/6 (`behavior_unverified: 0`: истина про флаги K после mkvmerge, раньше PRESENT_BEHAVIOR_UNVERIFIED, теперь подтверждена выполненным аппаратным тестом).

### Покрытие требований (PLAN frontmatter против REQUIREMENTS.md)

| Требование | Статус кода | Evidence | Замечание |
|---|---|---|---|
| ALN-01 | ✓ SATISFIED | `seek.py`, `frames.py`, медиа-тир | в REQUIREMENTS: Complete |
| ALN-02 | ✓ SATISFIED | `precheck.check_pair` | в REQUIREMENTS: Complete |
| ALN-03 | ✓ SATISFIED (с оговоркой UAT 10) | `scenes_reasons`, `keyframe_reasons`, аппаратный тест | в REQUIREMENTS стоит `[ ]` и «Pending (пересмотр D-24)»; после UAT 10 отметка меняется на Complete |
| ALN-04 | ✓ SATISFIED (с оговоркой UAT 10) | `check_offset`, D-26, WR-11 | в REQUIREMENTS: `[ ]` и «Pending (D-26)» |
| ANL-03 | ✓ SATISFIED | программный декод | в REQUIREMENTS: Complete |

Осиротевших требований нет: все пять ID фазы заявлены планами и присутствуют в REQUIREMENTS.md.

### Anti-patterns

Маркеров TBD/FIXME/XXX в `src/enpipe/analysis/`, `scratch/analysis_pair_probe.py` и аппаратном тесте нет (grep пуст); ruff чист. Ревью 10-REVIEW.md: 0 критичных, два предупреждения, оба не блокируют цель.

| Находка | Серьёзность | Влияние |
|---|---|---|
| WR-01: `DEFAULT_JOBS` и комментарий в `config.py:51-60` описывают несуществующий API (подтверждено: `DEFAULT_JOBS` читается только в строке 157 как перечень) | Warning | Вводит читателя в заблуждение, поведение не затронуто |
| WR-02: верхняя граница `Σ ceil(len/GOP_LEN)` в аппаратном тесте K-флагов может дать ложное падение при смене железа/драйвера | Warning | Тест жёсткий (без skip, D-28); нижняя граница и `keyframe_reasons == []` — настоящий инвариант; на B50 проходит |
| IN-01..IN-04, IN-06, IN-18, IN-23..IN-26 | Info | Оформление, наблюдаемость; IN-23 (нечитаемый `.scenes` молча становится «без .scenes») отнесён к фазе 11 |

### Отложенное и замечания о рабочем дереве

- `.planning/ROADMAP.md` содержит незакоммиченные правки (переписанная цель фазы 10 и вставка фазы 10.1 без плана). Я их прочитал, не менял и не коммитил. Цель фазы 10 в этом отчёте взята из рабочего дерева, как вы указали; фаза 10.1 на достижение цели фазы 10 не влияет.
- `.planning/STATE.md` не трогал.

## Требуется проверка человеком

### 1. UAT 10: реальная пара Young Sherlock S01E01 (`10-HUMAN-UAT.md`, тест 10)

**Test:** выполнить четыре команды (SRC.mkv, ENC.mkv, ENC_PART.mkv заменить своими путями):

```
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --check-only
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737 --no-scenes
```

**Expected:** 1) ok True, причин нет; 2) отказ с подсказкой «--offset 4737 (сцены 40..42)»; 3) ok True, источник offset=scenes; 4) ok False, причина «--offset 4737 задан без .scenes …». Причины «.scenes не совпадают с энкодом» нигде нет.
**Why human:** нужны реальные файлы оператора; именно на них раньше был ложный отказ G-10-1.

UAT 11 в список не входит: он выполнен автотестом, который я перезапустил (1 passed).

## Резюме гэпов

Гэпов нет. После UAT 10 оператору останется отметить ALN-03 и ALN-04 как Complete в `.planning/REQUIREMENTS.md` (сейчас `Pending`); я этот файл не менял.

---

_Проверено: 2026-11-08T12:00:00Z_
_Верификатор: Claude (gsd-verifier)_
