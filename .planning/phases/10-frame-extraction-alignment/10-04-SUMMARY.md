---
phase: 10-frame-extraction-alignment
plan: 04
subsystem: analysis
tags: [analysis, alignment, orchestration, media-test, framemd5]
requires: ["10-02", "10-03"]
provides:
  - "pair.py: PairCheck, FramePair, check_pair_files, grab_frame_pair, meta_with_check, refused_report"
  - "медиа-тест на реальном ffmpeg без GPU: seek == framemd5, вердикты сдвига/статики/частичного энкода"
affects: [10-05, 11]
tech-stack:
  added: []
  patterns: ["ThreadPoolExecutor с module-level воркерами (result, err)", "отказ данными, без завершения процесса"]
key-files:
  created:
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_pair.py
    - tests/integration/test_frames_media.py
  modified: []
key-decisions:
  - "Ошибка извлечения в точке — причина отказа «точка N: …», а не «неопределённо»"
  - "Повтор неопределённой точки решается только в _point_worker (не junction); при неудаче повторов возвращается исходная точка"
  - "Запас фикстуры сдвига измеряется только в точках, где в окне есть d=+1 (клон последнего кадра у конца файла сдвига не имеет)"
  - "Медиа-тест остаётся в дефолтном тире (маркер не добавлен, pyproject.toml не менялся)"
metrics:
  tasks: 3
  files: 3
  completed: 2026-10-07
---

# Phase 10 Plan 04: оркестратор пары и медиа-тест Summary

`pair.py` собирает probe, таблицы pts, предпроверку и вердикт выравнивания по точкам в `PairCheck` (отказ только данными), даёт пару кадров с локальным вердиктом для фазы 11 и модель отказа; медиа-тест на реальном ffmpeg доказывает совпадение seek с framemd5 и поведение вердикта.

## Выполнено

| Задача | Коммит |
|--------|--------|
| 1. check_pair_files, PairCheck, воркер точек | c9067d1 |
| 2. grab_frame_pair, meta_with_check, refused_report | 40baf1b |
| 3. медиа-тест на реальном ffmpeg | 56da429 |

## Проверка (запущено, результат наблюдался)

- `uv run pytest tests/unit/analysis/test_pair.py tests/unit/analysis/test_isolation.py -q`: 88 passed (в test_pair.py 18 тестов, `-k no_src_info` 2)
- `uv run pytest tests/integration/test_frames_media.py -q --durations=10`: 16 passed, 0 skipped, реальный ffmpeg n9.0.2 (libx265, libsvtav1, декод AV1 через libdav1d), без GPU
- `uv run pytest -q` (весь дефолтный тир): 804 passed, 17 deselected; `uv run ruff check src tests`: чисто
- grep-критерии: запрещённые импорты/вызовы в pair.py вне комментариев 0; `hardware` в медиа-тесте 0; снижений `align_margin_db` 0; `git diff --stat` по encoding/detection/mkv/shared/cli/pyproject/uv.lock пуст

## Медиа-тест: время и фикстура сдвига

- Время модуля: 15,5 с (бюджет 60 с, сокращений не потребовалось); весь модуль идёт в дефолтном `pytest -q`.
- Вариант фикстуры сдвига: основной (crf 35); запасной не строился. Запасы PSNR(+1) над вторым кандидатом по точкам (кадр: дБ): 0: 21,8; 24: 19,1; 48: 21,3; 71: 16,7. Требуется ≥ 4 дБ (порог D-03 3 дБ + 1 дБ страховки); порог в тестах не менялся.
- Критерии: 1 (CFR, start_time 2,5, VFR, видео start 2,5 при аудио 0, AV1: md5 кадров 0,1,2,13,47,48,49,95 и окна 45..51 == framemd5), 3 (сдвиг +1 — отказ, статика — «неопределённо»), 4 (частичный энкод: без --offset отказ с «--offset 24 (сцены 1..2)», с 24 — выровнено, 48 и 30 — отказ), 5 (нет `-hwaccel`/qsv/vaapi//dev/dri, `nice -n 10`, `-threads 2`).

## Deviations from Plan

**1. [Rule 1 - уточнение] Измерение запаса сдвига пропускает последнюю точку (кадр 95).** У фикстуры сдвига последний кадр энкода — клон последнего кадра источника, d=+1 там вне окна и сдвига по построению нет; запас считается по точкам, где d=+1 присутствует, и требуется ≥ 3 таких точки. В данных выше таких точек 4 из 5.

**2. [Rule 1 - формулировка] Слово `die()` в docstring pair.py заменено**, чтобы grep-критерий (без исключения docstring) давал 0; поведение не менялось.

В остальном план выполнен как написан; фикстуры не выносились в `_frames_fixtures.py` (контекста хватило, модуль с `--import-mode=importlib` всё равно не импортируется соседним файлом без правок).

## Известные ограничения

1. Склейки без повторных точек: при ≥ 3 малоподвижных склейках возможен ложный отказ «неопределённо»; место для повтора — ветка `target.junction` в `_point_worker`, кандидат фазы 13.
2. RASL после CRA (RESEARCH Pitfall 10) не воспроизведён и не проверен; страховка — проверка длины вывода `grab_frames` и вердикт выравнивания.
3. Допущение «framemd5 == md5 упакованных плоскостей» проверено только на ffmpeg n9.0.2.
4. Память пула (T-10-15): `ru_maxrss` на реальном разрешении не замерялся — это в 10-05.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности сверх threat_model плана (T-10-14 — `test_precheck_fail_no_grab`; T-10-16 — `test_point_error_reason`; T-10-20 — `test_shift_fixture_margin` и grep-гейт; T-10-17 — `test_no_gpu_needed`).

## Self-Check: PASSED

Файлы pair.py, test_pair.py, test_frames_media.py существуют; коммиты c9067d1, 40baf1b, 56da429 есть в git log.
