# Quick 261005-4uz: qsvencc --avoid-idle-clock off Summary

`chunk_command` теперь передаёт qsvencc `--avoid-idle-clock off` (после `--scenario-info archive`, до `*hdr_flags`), убирая ~4 с постоянных накладных на сессию; битстрим не меняется.

## Commits
- 2c59b83: perf(quick-261005-4uz): отключить --avoid-idle-clock в argv чанка qsvencc

## Files
- src/enpipe/encoding/chunk.py: флаг и русский комментарий с цифрами замера 2026-10-05
- tests/unit/encoding/test_chunk.py: test_chunk_command_disables_avoid_idle_clock

## Verification (observed)
- RED: новый тест падал до правки (1 failed, 13 passed).
- ruff check src tests: All checks passed.
- pytest tests/unit tests/subprocess: 235 passed.
- pytest test_qsvencc_triad_parse.py + test_harness_gates.py -m "not hardware": 74 passed.
- grep -c '"--avoid-idle-clock", "off"' chunk.py == 1.
- Аппаратные проверки (COR-02 lock, scratch/parity_encode.py) НЕ запускались: их выполняет оркестратор.

## Deviations from Plan
None - plan executed exactly as written.

## Известные риски
Одноразовый D-16 прогон непустоты через `qsvencc-nobackend` / `strip_backend=True` на старом r4604 может упасть на неизвестном `--avoid-idle-clock` (не проверено — нет бинаря). При таком прогоне потребуется аналогичное удаление пары в харнессе. Код харнесса не менялся.

## Self-Check: PASSED
Commit 2c59b83 и изменённые файлы существуют.

## Аппаратная пост-проверка оркестратора (2026-10-05, A380, r4665)

- Замер до правки (продакшен-argv, E01 Young Sherlock, сцена [30543,30622), 79 кадров): 1 сессия 5.55 → 1.64 с; 3 параллельно 5.63 → 2.51 с; 10/10 выходов sha256 `52872645…` идентичны с флагом и без.
- COR-02 lock `pytest tests/integration/test_concurrency_immunity.py -m hardware -k qsvencc`: `[no-metrics]` PASSED, `[metrics]` PASSED (2 passed, 240.75 s).
- `scratch/parity_encode.py`: byte-identical movie.obu legacy (без флага) ↔ migrated (с флагом) = True, metrics attempts 1/1/1, PARITY OK.
