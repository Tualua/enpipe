---
phase: 09-analysis-core-readers
plan: 01
subsystem: analysis
tags: [dataclasses, config, report-model, thresholds]
pre_phase_sha: a9c249ad2c8bf670da6bffef593409e5b99cbf1f
requires: []
provides:
  - enpipe.analysis.model (frozen-модель отчёта и метрик, schema_version=1)
  - enpipe.analysis.config (AnalyzeConfig, AnalysisError, константы PQ/BT.2020/ITP, build_thresholds)
affects: [09-02, 09-03, 09-04, 09-05]
tech-stack:
  added: []
  patterns: [frozen dataclasses, thresholds из dataclasses.fields]
key-files:
  created:
    - src/enpipe/analysis/__init__.py
    - src/enpipe/analysis/model.py
    - src/enpipe/analysis/config.py
    - tests/unit/analysis/test_config_model.py
  modified: []
key-decisions:
  - "build_thresholds строится по dataclasses.fields(AnalyzeConfig): порог нельзя забыть пометить provisional"
  - "chroma_min_pts >= 1 (иначе Σ(s·s) = 0 в проекции)"
  - "ITP_STRIP_ROWS — производительная константа, не порог"
requirements-completed: [MET-05, RPT-01]
duration: 10min
completed: 2026-10-06
---

# Phase 9 Plan 01: контракты analysis Summary

Пакет `enpipe.analysis` с полной frozen-моделью отчёта (14 датаклассов, schema_version=1) и `AnalyzeConfig` с валидацией; все 15 порогов превращаются в `Threshold(provisional=True)`.

## Выполнено

1. Task 1 (commit 78afebc): `model.py` + `__init__.py`, тесты frozen-ности, приоритетов источников, snake_case имён. RED подтверждён (ошибка импорта до реализации).
2. Task 2 (commit 2d0e0e0): `config.py`: константы стандартов, `AnalysisError`, `AnalyzeConfig.__post_init__`, `build_thresholds`; тесты дефолтов, валидации, типов значений, сумм матриц, чётности `ITP_STRIP_ROWS`.

## Проверка (фактически запущено)

- `uv run pytest tests/unit/analysis -q`: 50 passed
- `uv run pytest tests/unit -q`: 298 passed
- `uv run ruff check src tests`: All checks passed
- grep-критерии: 14 `@dataclass(frozen=True)` в model.py; запрещённых импортов/`list[`/`| None` нет; `tests/unit/analysis/__init__.py` отсутствует.
- Не запускалось: ворота git diff от `pre_phase_sha` (проверяются в 09-05); код вне `src/enpipe/analysis` и `tests/unit/analysis` не менялся.

## Deviations from Plan

None - plan executed exactly as written. Мелкая деталь: в тест добавлен `noqa: E402` у импорта config в середине файла (ruff E402 не включён, на результат не влияет).

## Self-Check: PASSED
