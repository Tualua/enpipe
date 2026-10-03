---
title: Перейти с зеркала qsvencc r4634 на закреплённый апстрим-релиз 8.32+
created: 2026-10-02
area: devcontainer/docker
source: phase-07 D-06
---

Сейчас оба образа ставят nightly-сборку r4634 (rigaya/QSVEnc 45003f1) из зеркала
Release `deps-qsvencc-r4634`. Когда апстрим опубликует релиз 8.32+ с фиксом
45003f1, нужно перейти на него отдельной quick-задачей.

## Триггер

Проверить `https://api.github.com/repos/rigaya/QSVEnc/releases/latest`: у нового
тега `compare/<tag>...45003f1` должен давать `behind_by` = 0 (фикс уже в релизе).

## Чек-лист обновления (ВСЕ места)

1. `ARG QSVENCC_URL` в `.devcontainer/Dockerfile`.
2. `ARG QSVENCC_SHA256` в `.devcontainer/Dockerfile`.
3. `ARG QSVENCC_URL` в `Dockerfile`.
4. `ARG QSVENCC_SHA256` в `Dockerfile` — sha256 пересчитать по скачанному ассету релиза.
5. Порог ревизии `-ge 4634` в RUN `.devcontainer/Dockerfile`.
6. Порог `-ge 4634` в RUN `Dockerfile`.
7. `-lt 4634` и текст сводки `r4634` в `.devcontainer/post-create.sh`.
8. `QSVENCC_MIN_REV` в `src/enpipe/shared/qsvencc_version.py`.
   Пункты 5-8 меняются только если меняется сама минимальная требуемая ревизия;
   переход на релиз новее r4634 их поднимать НЕ требует.
9. Запустить `.venv/bin/python -m pytest tests/unit/shared/test_qsvencc_threshold_sync.py`
   — он падает при любом частичном обновлении.
10. Убедиться, что `--version` нового ассета даёт rNNNN >= порога; пересобрать оба
    образа на хосте.
11. Опционально удалить релиз-зеркало `deps-qsvencc-r4634`.
