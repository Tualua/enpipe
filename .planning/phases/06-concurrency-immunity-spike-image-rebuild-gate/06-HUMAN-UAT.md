---
status: diagnosed
phase: 06-concurrency-immunity-spike-image-rebuild-gate
source: [06-VERIFICATION.md]
started: 2026-07-23T00:00:00Z
updated: 2026-10-04T16:45:00Z
---

## Current Test

[testing complete]

## Tests

<!-- 2026-10-04: пункты переведены на текущее окружение по решению оператора.
     Исходные формулировки (ffmpeg-8.1 side-load; контроль qsvencc с порчей)
     устарели: образы на BtbN ffmpeg n9.0.2 (quick 261004-h8e), qsvencc r4665
     исправлен (фаза 7), непустота замка доказана на r4604 в 08-06, а тест
     test_qsvencc_control_corrupts_same_harness удалён. -->

### 1. ENV-01 самопроверка на текущем образе (ffmpeg n9.0.2)
expected: ffmpeg/ffprobe на PATH резолвятся в /opt/ffmpeg-9/bin; версия n9.0.2; av1_qsv и libopus в -encoders; av1_metadata и dovi_rpu в -bsfs; dovi_rpu перечисляет av1; ENV01_OK=1, ноль строк «ОШИБКА:».
supersedes: "Canonical devcontainer rebuild then ENV-01 self-check (ffmpeg-8.1)"
result: pass
evidence: "оператор 2026-10-04: readlink → /opt/ffmpeg-9/bin/{ffmpeg,ffprobe}; n9.0.2-22-g46d8f462ee; av1_qsv, libopus, av1_metadata, dovi_rpu; dovi_rpu Supported codecs: hevc av1. Блок ENV-01 из post-create: ENV01_OK=1"

### 2. COR-01: ffmpeg av1_qsv без порчи при параллельном кодировании на A380
expected: `pytest tests/integration/test_concurrency_immunity.py -m hardware -k ffmpeg` PASSED (0 испорченных кадров при JOBS=3, 0 сессий, не стартовавших, триада intact); стресс-матрица `scratch/gate_stress_matrix.py --backend ffmpeg` даёт 0 порченых кадров на JOBS 3/5/8, 0 SESSION_FAILED, вердикт PASS.
supersedes: "Re-run hardware gate (ffmpeg immune + qsvencc control corrupts)"
result: issue
reported: "pytest: test_ffmpeg_av1qsv_immune_at_production_jobs PASSED, 1 passed in 111.73s. gate_stress_matrix.py --backend ffmpeg: AttributeError: module '_concurrency_harness' has no attribute 'ffmpeg81_available'. Did you mean: 'ffmpeg_av1qsv_available'?"
severity: blocker

## Summary

total: 2
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Стресс-матрица scratch/gate_stress_matrix.py --backend ffmpeg отрабатывает на JOBS 3/5/8 и выдаёт вердикт (0 порченых кадров, 0 SESSION_FAILED, PASS)"
  status: failed
  reason: "User reported: AttributeError: module '_concurrency_harness' has no attribute 'ffmpeg81_available'. Did you mean: 'ffmpeg_av1qsv_available'? (pytest-часть COR-01 при этом PASSED)"
  severity: blocker
  test: 2
  root_cause: "quick 261004-h8e (c912e6b) переименовал в tests/integration/_concurrency_harness.py ffmpeg81_available() → ffmpeg_av1qsv_available() (гейт по av1_qsv на основном ffmpeg 9), но не обновил потребителя в scratch/. test_ffmpeg_pin_sync.py ищет следы ffmpeg-8.1 только в отслеживаемых им файлах и scratch/ не покрывает, поэтому хвост не пойман."
  artifacts:
    - path: "scratch/gate_stress_matrix.py"
      issue: "строка 164 вызывает harness.ffmpeg81_available(); строка 165 печатает SKIP про ffmpeg-8.1; docstring строка 55 упоминает ffmpeg-8.1"
    - path: "tests/unit/shared/test_ffmpeg_pin_sync.py"
      issue: "test_no_stale_ffmpeg_81 не включает scratch/gate_stress_matrix.py"
  missing:
    - "Заменить вызов на harness.ffmpeg_av1qsv_available() и тексты SKIP/docstring на ffmpeg с av1_qsv (n9.0.2)"
    - "Добавить scratch/gate_stress_matrix.py в список файлов test_no_stale_ffmpeg_81"
    - "Перепрогнать python scratch/gate_stress_matrix.py --backend ffmpeg на A380 и закрыть пункт 2"
  debug_session: ""
