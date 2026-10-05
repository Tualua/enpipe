---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
plan: 05
subsystem: testing
tags: [qsvencc, hardware-gate, stress-matrix, non-vacuity, debt-closure]
requires:
  - phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
    provides: "07-03 образ с r4634, 07-04 замок и gate_stress_matrix.py"
provides:
  - "Аппаратные доказательства: не-вакуумность на r4604, 0 порченых кадров на r4634 при JOBS 3/5/8"
  - "Закрытый долг порчи кадров (debug-доки, PROJECT.md, STATE.md)"
affects: []
key-files:
  created: []
  modified:
    - .planning/debug/scene-chunk-frame-mismatch.md
    - .planning/debug/qsvenc-upstream-issue.md
    - .planning/debug/HANDOFF-qsvencc-frame-corruption.md
    - .planning/PROJECT.md
    - .planning/STATE.md
key-decisions:
  - "Долг порчи кадров закрыт: резолюция = апстрим 45003f1 (#308), сборка r4634, замок JOBS=3 x 8"
requirements-completed: [COR-02, QSV-01, QSV-02]
duration: 75min
completed: 2026-10-02
---

# Phase 7 Plan 05: Аппаратный гейт и закрытие долга Summary

Не-вакуумность доказана на r4604 (3 порченых кадра), r4634 чистая на 320 сессиях при JOBS 3/5/8 с целой триадой; регрессий вне конкуренции нет; долг порчи кадров закрыт с резолюцией 45003f1.

## Окружение (реально записано)

- `uname -r`: 6.19.14-200.fc43.x86_64; iHD: Intel iHD driver 26.3.2; GPU Arc A380 (`/dev/dri/renderD128`).
- Фиксированный бинарь: `/usr/bin/qsvencc`, `QSVEncC (x64) 8.31 (r4634) by rigaya, Oct 1 2026 22:01:56` - из канонического образа (side-load не понадобился, остаточного риска «внешний бинарь» нет).
- Старый бинарь (только D-16): `QSVEncC (x64) 8.31 (r4604)`, `.deb` проверен `sha256sum -c` (15aa733f...f61f), распакован `dpkg-deb -x` в `/tmp/enpipe-phase7/r4604`, не установлен.
- Фикстура: `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` (сцены 923/928/1129).

## Результаты

### Task 1: D-16, замок, матрица

- **D-16 (r4604, `--backend qsvencc-nobackend --jobs 3 --iters 8 --expect corrupt`):** 24 сессии, **3 порченых кадра**, 0 SESSION_FAILED, 0 пропусков; wall 123 s; вердикт PASS (корупция воспроизведена). Повтор с `--iters 20` не потребовался. Лог: `scratch/gate_stress_matrix_20261002T153231Z.log` (триада на r4604 нарушена по `Backend qsv not confirmed` - ожидаемо, информативно).
- **Замок на r4634:** `pytest -m hardware tests/integration/test_concurrency_immunity.py -v`: **2 passed** (ffmpeg-тест тоже прошёл, не skip - ffmpeg-8.1 в образе есть, и qsvencc-тест), 207.78 s.
- **Матрица r4634 (`--jobs 3,5,8 --iters 20 --expect clean`), лог `scratch/gate_stress_matrix_20261002T153827Z.log`, вердикт PASS:**

| JOBS | ok | порченых | SESSION_FAILED | пропущено | wall | на итерацию mean/max |
|------|----|----------|----------------|-----------|------|----------------------|
| 3 | 60 | 0 | 0 | 0 | 294 s | 14.7 / 29.1 s |
| 5 | 100 | 0 | 0 | 0 | 325 s | 16.3 / 18.6 s |
| 8 | 160 | 0 | 0 | 0 | 575 s | 28.7 / 57.2 s |

Итого 320 сессий, 0 порченых, триада INTACT на всех уровнях; суммарный wall 1194 s. Паттерны fallback в harness не менялись.

### Task 2: D-18 на r4634

- `pytest -m hardware tests/integration/test_hardware_real_media.py -v`: **4 passed, 2 skipped** (test_sdr, test_hdr10, test_sdr_legacy_oracle_parity, test_run_parity_vs_two_step passed; HDR10+ и DV пропущены - нет операторских фикстур, это не провал).
- Детерминизм: синтетический 4-сценный SDR-клип, `enpipe detect` один раз, два `enpipe encode --keep --no-audio --no-metrics --jobs 2` в разные workdir. `movie.obu` оба 70014 байт, sha256 `fd1e5bc41f71ea2c889392b1de6940b25b79a36b74fa4b8005a433b64fdbb8b6` - **идентичны** (диагностика расхождений не понадобилась).

### Task 3: закрытие долга

Три debug-документа (в `scene-chunk-frame-mismatch.md` `status: resolved` + раздел «ФАЗА 7»), PROJECT.md (открытый долг -> resolved, Key Decision -> Resolved, футер) и две строки Deferred Items в STATE.md (`resolved (Phase 7, 45003f1 r4634)`) обновлены. Verify-команда задачи напечатала OK. `legacy/` и `cannot-write-data-mounts.md` не тронуты.

## Осознанное ограничение (D-17)

Постоянным коммитнутым тестом охраняется только JOBS=3 x 8 (production-уровень). Уровни JOBS 5/8 x 20 проверены один раз в этой фазе и НЕ охраняются постоянно. При любом обновлении qsvencc/iHD/ядра перезапускать вручную: `scratch/gate_stress_matrix.py --jobs 3,5,8 --iters 20 --expect clean`.

## Принятый остаточный риск (T-07-24)

Рантайм-гейт `enpipe.shared.qsvencc_version` доверяет строке ревизии, которую сообщает сам бинарь, а не его дайджесту; целостность по sha256 обеспечивается только при сборке образа.

## Deviations from Plan

None - план выполнен как написан. Заметка: логи `scratch/gate_stress_matrix_*.log` игнорируются git (не закоммичены), остаются на диске как доказательства. Для Task 1 и 2 репозиторных изменений нет, поэтому отдельных коммитов у них нет; единственный коммит кода/доков - feb005e.

## Self-Check: PASSED

Коммит feb005e, логи `scratch/gate_stress_matrix_20261002T153231Z.log` и `..._20261002T153827Z.log` существуют.
