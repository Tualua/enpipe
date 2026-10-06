---
phase: 09-analysis-core-readers
plan: 05
subsystem: analysis
tags: [integration, isolation, ast-guard, phase-gate]
requires: [09-02, 09-03, 09-04]
provides:
  - сквозной тест чистого ядра фазы 9
  - AST-сторож изоляции пакета analysis (прямой и обратный)
affects: [10, 11]
tech-stack:
  added: []
  patterns: [AST-сторож с резолвом относительных импортов и алиасов, самопроверка чекера на фрагментах]
key-files:
  created:
    - tests/unit/analysis/test_core_integration.py
    - tests/unit/analysis/test_isolation.py
  modified: []
key-decisions:
  - "Обратный сторож включает cli/; в фазе 11 cli осознанно исключается при подключении команды analyze"
requirements-completed: [MET-01, MET-02, MET-03, MET-04, MET-05, CND-01, CND-02, CND-04, CND-05, RPT-01]
duration: 15min
completed: 2026-10-06
---

# Phase 9 Plan 05: сквозной тест и изоляция analysis Summary

Синтетическая 10-битная пара проходит `analyze_frame` -> `FrameRow` -> `AnalysisReport` -> `render_json/md/html` без subprocess; AST-сторож (резолв `ImportFrom.module`, алиасов и относительных импортов) закрепляет изоляцию `enpipe.analysis` от encode-пути в обе стороны.

## Выполнено

1. Task 1 (commit 4361595): `test_core_integration.py` (метрики синтетики, пара src==enc с inf/0.0, слияние manual/CSV из настоящего `write_metrics_csv`/VMAF с отвергнутым VMAF, полный отчёт во всех трёх форматах) и `test_isolation.py` (`_package_of`, `_resolve`, `_violations`, 16 запрещённых и 10 разрешённых фрагментов, проверка по файлам analysis, обратный сторож).
2. Task 2: ворота фазы, правок кода не потребовалось.

## Проверка (фактически запущено)

- `uv run pytest tests/unit/analysis/test_isolation.py tests/unit/analysis/test_core_integration.py -q`: 65 passed; test_isolation собирает 60 тестов (требовалось >= 25).
- Негативная самопроверка: строка `import subprocess` в `candidates.py` -> `test_analysis_module_is_isolated[candidates.py]` упал; после отката `git diff --quiet` = 0.
- `uv run pytest -q` (весь быстрый тир): 633 passed, 17 deselected (hardware).
- `uv run ruff check src tests`: All checks passed.
- База ворот: `pre_phase_sha` a9c249ad2c8bf670da6bffef593409e5b99cbf1f из 09-01-SUMMARY (предок HEAD подтверждён).
- `git diff --stat BASE -- src/enpipe/{encoding,detection,mkv,shared,cli} pyproject.toml uv.lock`: пусто.
- `git diff --stat BASE -- tests ':(exclude)tests/unit/analysis'`: пусто.
- Число собранных тестов вне analysis: 359 (17 deselected).
- Импорт `enpipe.analysis` и всех 6 модулей: ok.
- Трассировка D-01..D-21 в src/enpipe/analysis и tests/unit/analysis: все найдены.

## Deviations from Plan

Правок модулей волны 2 не было; «резервная база» не использовалась. Мелкое: хелпер CSV в тесте принимает `tmp_path` (фикстура pytest) вместо временного каталога внутри теста.

## Self-Check: PASSED
