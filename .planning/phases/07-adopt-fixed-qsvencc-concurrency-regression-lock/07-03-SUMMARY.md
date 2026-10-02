---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
plan: 03
subsystem: infra
tags: [qsvencc, dockerfile, sha256-pin, post-create, QSV-01]
requires: [07-01, 07-02]
provides:
  - "Оба образа ставят qsvencc r4634 из зеркала deps-qsvencc-r4634, sha256sum -c + проверка ревизии >= 4634"
  - "post-create: строка QSV-01 по флагу QSV01_OK"
  - "Быстрый тест синхронности порогов/пинов (test_qsvencc_threshold_sync.py)"
affects: [07-05]
tech-stack:
  added: []
  patterns: ["ARG URL + ARG SHA256 + sha256sum -c для внешних .deb", "drift-guard тест для литералов, продублированных в shell и Python"]
key-files:
  created:
    - tests/unit/shared/test_qsvencc_threshold_sync.py
    - .planning/todos/pending/2026-10-02-qsvencc-pin-upstream-release.md
  modified:
    - .devcontainer/Dockerfile
    - Dockerfile
    - .devcontainer/post-create.sh
key-decisions:
  - "Плавающий releases/latest для qsvencc убран из обоих образов; бамп только явной правкой ARG (D-02)"
  - "Вырезание зависимостей (dpkg-deb -R + awk) удалено — новый .deb не тянет intel-opencl-icd/libmfx1"
requirements-completed: [QSV-01]
duration: 30min
completed: 2026-10-02
---

# Phase 7 Plan 03: Пин qsvencc r4634 в образах и самопроверка QSV-01 Summary

Оба образа (devcontainer и корневой GHCR) устанавливают qsvencc r4634 (45003f1) из зеркала по sha256-пину; сборка падает при несовпадении дайджеста или ревизии < 4634; post-create громко сообщает QSV-01.

## Tasks

| Task | Commit | Результат |
|------|--------|-----------|
| 1. Пин r4634 в обоих Dockerfile | b1b68a8 | статические grep-проверки прошли |
| 2. QSV-01 в post-create + тест синхронности + todo D-06 | 8210755 | test_qsvencc_threshold_sync: 6 passed |
| 3. Проверка на хосте (checkpoint:human-verify) | — | approved пользователем |

## Проверено (реально запущено)

- `pytest tests/unit/shared/test_qsvencc_threshold_sync.py`: 6 passed.
- Хост (пользователь): корневой образ собран, devcontainer пересобран; post-create вывел `QSV-01 (qsvencc >= r4634 / 45003f1): OK`. Допущение A1 (slim-trixie разрешает `libva-x11-2`) подтверждено успешной сборкой.
- В пересобранном devcontainer: `qsvencc --version` → `QSVEncC (x64) 8.31 (r4634)`.
- Не проверялось мной лично: негативная сборка с нулевым `QSVENCC_SHA256` (шаг 4 был необязательным).

## Остаточный риск (T-07-26, принят)

Сборки образов (локальная и `docker-publish.yml`) теперь зависят от анонимной доступности ассета Release `deps-qsvencc-r4634`. При его удалении/переименовании репо/rate-limit сборка падает (fail closed), тихого отката на другую версию нет. Для rate-limit в корневом образе оставлен опциональный BuildKit-секрет `github_token`.

## Deviations from Plan

None - план выполнен как написан. SUMMARY дописан при возобновлении сессии после одобрения checkpoint.

## Self-Check: PASSED
