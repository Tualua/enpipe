---
phase: quick-260709-6jo-live-tqdm
plan: 01
subsystem: detection
tags: [tqdm, scenedetect, cli, ux, threadpoolexecutor, testing]

# Dependency graph
requires:
  - phase: 03-01 (DEBT-03 ThreadPoolExecutor decision)
    provides: detect_scenes_parallel's ThreadPoolExecutor-based segment step (parallel.py)
  - phase: 04-01 (unified CLI entry point)
    provides: src/enpipe/detection/pipeline.py::run_detect(args)
provides:
  - "show_progress пробрасывается через detect_scenes/_detect_relative/detect_scenes_parallel (дефолт False, байт-идентичное прежнее поведение)"
  - "run_detect печатает СТАРТ/ФИНИШ-строки в stderr и включает show_progress=True"
  - "Параллельный путь при show_progress=True рисует один агрегированный tqdm-бар, results собираются в исходном порядке futures — cut-математика не тронута"
  - "Юнит-тесты show_progress: последовательный проброс + параллель==последовательно при обоих режимах"
affects: [detection, cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Агрегированный tqdm-бар поверх ThreadPoolExecutor.submit + as_completed для UI-прогресса, при этом результаты собираются отдельно, В ИСХОДНОМ ПОРЯДКЕ futures (не по as_completed) — разделение 'порядок для UI' и 'порядок для корректности склейки'"
    - "СТАРТ/ФИНИШ-строки CLI-этапа в stderr (time.monotonic() для длительности), финальная парсибельная строка остаётся в stdout без изменений"

key-files:
  created: [tests/unit/detection/test_show_progress.py]
  modified: [src/enpipe/detection/detect.py, src/enpipe/detection/parallel.py, src/enpipe/detection/pipeline.py, tests/unit/cli/test_run_detect_roundtrip.py]

key-decisions:
  - "tqdm импортирован из scenedetect.platform (транзитивная зависимость, уже установлена) — новый прямой пакет не добавлен"
  - "Ветка show_progress=False в detect_scenes_parallel оставлена буквально нетронутой (ex.map), чтобы гарантировать байт-идентичность с прежним поведением; ветвление добавлено ТОЛЬКО для show_progress=True"
  - "results параллельного сегмент-шага при show_progress=True собираются как [f.result() for f in futures] (по futures[i], не по as_completed) — прогресс-бар обновляется по факту завершения (as_completed), но порядок для склейки сцен строго исходный"

patterns-established:
  - "Разделение UI-порядка (as_completed для живого прогресса) и логического порядка (futures[i] для корректности) при параллельной обработке с ThreadPoolExecutor"

requirements-completed: [QUICK-TQDM-01]

# Metrics
duration: ~25min
completed: 2026-07-09
---

# Quick Task 260709-6jo: Live tqdm progress Summary

**Детекция сцен в CLI теперь показывает СТАРТ-строку, живой tqdm-прогресс-бар (штатный на последовательном пути, один агрегированный на параллельном) и ФИНИШ-строку в stderr, без изменения cut-математики, порядка результатов или stdout-вывода.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-09T04:28Z
- **Completed:** 2026-07-09T04:53Z
- **Tasks:** 3 completed
- **Files modified:** 5 (3 modified source, 1 modified test, 1 new test)

## Accomplishments
- `show_progress: bool = False` проброшен через `_detect_relative` → `SceneManager.detect_scenes`, через `detect_scenes(jobs=1|jobs>1)` → `_detect_relative`/`detect_scenes_parallel`, и через оба fallback-return'а `detect_scenes_parallel` (`total is None`, `len(bnds) < 3`)
- `detect_scenes_parallel` при `show_progress=True` открывает сегмент-шаг через `ex.submit` (не `ex.map`), крутит один `tqdm(total=total, unit="frame", ...)` бар через `as_completed`, но собирает `results` строго по `futures[i]` (исходный порядок сегментов) — cut-математика шагов 3-4 (offset-накопление, non-cut-merge) осталась байт-идентичной
- `run_detect` печатает `"Детекция сцен: {input} (jobs={jobs}, {режим})"` в stderr до вызова `detect_scenes(..., show_progress=True)` и `"Готово: {N} сцен за {t:.1f}с"` после; итоговая stdout-строка `"{N} сцен -> {out_path}"` не изменилась
- Новый файл `tests/unit/detection/test_show_progress.py`: 4 теста (последовательный проброс True/дефолт False; параллель show_progress=True==False по результату; tqdm-бар получает `total`, `update` и `close` вызваны)
- Существующие стабы `detect_scenes` в `test_run_detect_roundtrip.py` обновлены принимать `show_progress=False` именованным kwarg без изменения логики ассертов

## Task Commits

Each task was committed atomically:

1. **Task 1: Проброс show_progress через слой детекции (detect.py + parallel.py)** - `3bf51fc` (feat)
2. **Task 2: СТАРТ/ФИНИШ строки + включение прогресса в run_detect (+ фикс стабов round-trip)** - `e475d5d` (feat)
3. **Task 3: Юнит-тесты проброса show_progress и сохранения порядка/поведения** - `b39d1c9` (test)

**Plan metadata:** committed separately by orchestrator (docs)

## Files Created/Modified
- `src/enpipe/detection/detect.py` - `_detect_relative`/`detect_scenes` принимают `show_progress: bool = False`, пробрасывают в `SceneManager.detect_scenes`/`detect_scenes_parallel`
- `src/enpipe/detection/parallel.py` - импорт `as_completed` и `from scenedetect.platform import tqdm`; `detect_scenes_parallel` принимает `show_progress`, оба fallback-return'а пробрасывают его; сегмент-шаг ветвится: `ex.map` при False (не тронут), `submit`+`as_completed`+агрегированный tqdm-бар при True, `results` всегда собираются по `futures[i]`
- `src/enpipe/detection/pipeline.py` - `import sys, time`; `run_detect` печатает СТАРТ/ФИНИШ в stderr вокруг `detect_scenes(..., show_progress=True)`; stdout-строка не тронута
- `tests/unit/cli/test_run_detect_roundtrip.py` - все стабы/лямбды `detect_scenes` принимают `show_progress=False` (иначе `TypeError` на новом именованном kwarg)
- `tests/unit/detection/test_show_progress.py` (новый) - 4 юнит-теста show_progress-проброса и параллель==последовательно-регресса

## Decisions Made
- tqdm импортирован из `scenedetect.platform` (уже транзитивная зависимость через `scenedetect`) — новый прямой пакет не добавлен, T-6jo-SC (accept) подтверждён
- `results` при `show_progress=True` собираются `[f.result() for f in futures]` (по исходному порядку сабмита), а не по `as_completed` — прогресс-бар обновляется по факту завершения любого сегмента (UX), но склейка сцен (шаги 3-4, non-cut-merge) остаётся зависящей только от порядка сегментов, а не от порядка их фактического завершения
- Ветка `show_progress=False` буквально не тронута (`ex.map`) — гарантия байт-идентичности с прежним поведением, подтверждённая всей регресс-сюитой `-k parallel`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Изменение самодостаточно; UX-улучшение не блокирует и не требует ничего от других частей пайплайна
- Ручная HW-проверка живого бара (`enpipe detect <clip>`) вне автоверификации — не выполнялась в рамках этой задачи (нет media/GPU-доступа в текущей сессии verify-шага)
- `uv run pytest -m "not hardware" -q` — 111 passed (было 107 до задачи), `uv run pytest -m "not hardware" -k parallel -q` — 11 passed, `uv run ruff check src tests` — чисто

---
*Phase: quick-260709-6jo-live-tqdm*
*Completed: 2026-07-09*

## Self-Check: PASSED

- FOUND: src/enpipe/detection/detect.py
- FOUND: src/enpipe/detection/parallel.py
- FOUND: src/enpipe/detection/pipeline.py
- FOUND: tests/unit/cli/test_run_detect_roundtrip.py
- FOUND: tests/unit/detection/test_show_progress.py
- FOUND: .planning/quick/260709-6jo-live-tqdm/260709-6jo-SUMMARY.md
- FOUND commit: 3bf51fc
- FOUND commit: e475d5d
- FOUND commit: b39d1c9
