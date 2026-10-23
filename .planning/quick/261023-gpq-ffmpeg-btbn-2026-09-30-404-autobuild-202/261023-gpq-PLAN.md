---
phase: quick-261023-gpq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - Dockerfile
  - .devcontainer/Dockerfile
  - .planning/codebase/CONCERNS.md
  - docker/README.md
autonomous: true
requirements: [QUICK-261023-gpq]

must_haves:
  truths:
    - "Сборка devcontainer и рантайм-образа скачивает ffmpeg без 404 (шаг ffmpeg проходит: sha256sum -c OK, n9.0.2, av1_qsv, libopus, dovi_rpu)"
    - "Оба Dockerfile несут одинаковые ARG FFMPEG_URL/FFMPEG_SHA256 на сборку autobuild-2026-09-30-13-08"
    - "В обоих Dockerfile нет упоминаний autobuild-2026-10-01, n9.0.2-22, g46d8f462ee, a6170faecf…"
    - "Комментарий у ARG объясняет: пиним ТОЛЬКО сборку конца месяца, ежедневные BtbN удаляет примерно через 2 недели"
  artifacts:
    - path: "Dockerfile"
      contains: "ARG FFMPEG_SHA256=68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269"
    - path: ".devcontainer/Dockerfile"
      contains: "ARG FFMPEG_SHA256=68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269"
  key_links:
    - from: "Dockerfile"
      to: ".devcontainer/Dockerfile"
      via: "идентичные строки ARG FFMPEG_URL / ARG FFMPEG_SHA256 (страж tests/unit/shared/test_ffmpeg_pin_sync.py)"
      pattern: "^ARG FFMPEG_(URL|SHA256)="
---

<objective>
Перепинить статический ffmpeg BtbN с удалённой ежедневной сборки autobuild-2026-10-01-13-06
(сейчас 404 — сборка devcontainer падает на шаге 21/25) на сохраняемую месячную сборку
autobuild-2026-09-30-13-08 в обоих Dockerfile, с комментарием о политике пина.

Purpose: восстановить сборку образов. BtbN удаляет ежедневные autobuild-* примерно через 2 недели,
но оставляет последнюю сборку каждого месяца — поэтому пинить можно только её.
Output: обновлённые ARG в Dockerfile и .devcontainer/Dockerfile, синхронные комментарии,
уточнённая запись о риске в CONCERNS.md и docker/README.md.
</objective>

<execution_context>
@/home/logovo/.claude/plugins/cache/gsd-plugin/gsd/4.0.2/workflows/execute-plan.md
@/home/logovo/.claude/plugins/cache/gsd-plugin/gsd/4.0.2/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

Новый пин (проверен оркестратором: digest из GitHub API; `podman build -f .devcontainer/Dockerfile`
с этими --build-arg прошёл полностью, проверки n9.0.2 / av1_qsv / libopus / dovi_rpu OK):
- URL: https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n9.0.2-17-g2a571b6068-linux64-gpl-9.0.tar.xz
- SHA256: 68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269

Старый пин (удалить из обоих Dockerfile):
- URL: .../autobuild-2026-10-01-13-06/ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz
- SHA256: a6170faecf757381ad0338d7a6ba26e97c2ebe2b9c1568633421e15d1ed436a9

Расположение блока ffmpeg (комментарий + ARG + RUN):
- Dockerfile: комментарий 198-215, «Точная сборка (n9.0.2-22-g46d8f462ee, autobuild 2026-10-01)» на 204, ARG на 216-217.
- .devcontainer/Dockerfile: тот же комментарий, «Точная сборка …» на 170, ОГРАНИЧЕНИЕ на 178-181, ARG на 182-183.

Страж tests/unit/shared/test_ffmpeg_pin_sync.py проверяет только равенство ARG в двух файлах
и наличие «n9.0.2» — конкретный хеш/тег в тестах не захардкожен, тесты менять не нужно.
CLAUDE.md упоминает только «BtbN static n9.0.2, pinned URL+SHA256» — не менять.
Исторические записи (.planning/STATE.md таблица quick-задач, .planning/quick/261004-h8e-*,
.planning/milestones/*, .planning/research/STACK.md «проверено на n9.0.2-22…») — это журнал
фактов прошлого, НЕ переписывать.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Перепин ARG FFMPEG_URL/FFMPEG_SHA256 и комментарий в обоих Dockerfile</name>
  <files>Dockerfile, .devcontainer/Dockerfile</files>
  <action>
В обоих файлах одинаково:
1. Заменить строку `ARG FFMPEG_URL=…autobuild-2026-10-01-13-06/ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz`
   на `ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n9.0.2-17-g2a571b6068-linux64-gpl-9.0.tar.xz`
   и `ARG FFMPEG_SHA256=a6170f…a9` на `ARG FFMPEG_SHA256=68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269`.
   Строки ARG — ровно по одной на файл, без хвостовых пробелов (страж парсит `^ARG FFMPEG_URL=(\S+)$`).
2. Строку комментария «# Точная сборка (n9.0.2-22-g46d8f462ee, autobuild 2026-10-01) проверена на A380:»
   переписать честно: побайтная идентичность .scenes с ffmpeg 6.1 (dv-p81, hdr10plus) проверялась на A380
   на сборке n9.0.2-22 (autobuild 2026-10-01, ныне удалена); текущий пин — n9.0.2-17-g2a571b6068
   (autobuild 2026-09-30), та же ветка релиза n9.0.2. Не утверждать, что 09-30 прогонялась на A380 через enpipe detect.
3. Абзац «# ОГРАНИЧЕНИЕ: BtbN чистит старые autobuild-релизы…» дополнить/переформулировать по-русски:
   пиним ТОЛЬКО сборку конца месяца (autobuild-ГГГГ-ММ-<последний день>), ежедневные autobuild-* BtbN
   удаляет примерно через 2 недели (так умер пин 2026-10-01), месячные пока сохраняет; зеркалирование
   ассетом GitHub Release проекта остаётся планом на случай удаления и месячных. Комментарий короткий (2-4 строки).
Тексты комментариев в двух файлах должны совпадать для этого блока. Остальной RUN-блок (curl, sha256sum -c,
проверки n9.0.2/av1_qsv/libopus/dovi_rpu), dovi_tool, qsvencc, vpl-gpu-rt — НЕ трогать.
  </action>
  <verify>
    <automated>cd /home/logovo/enpipe && ! grep -nE 'autobuild-2026-10-01|n9\.0\.2-22|g46d8f462ee|a6170faecf' Dockerfile .devcontainer/Dockerfile && test "$(grep -c '^ARG FFMPEG_SHA256=68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269$' Dockerfile .devcontainer/Dockerfile | awk -F: '{s+=$2} END {print s}')" = 2 && test "$(grep -c '^ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n9.0.2-17-g2a571b6068-linux64-gpl-9.0.tar.xz$' Dockerfile .devcontainer/Dockerfile | awk -F: '{s+=$2} END {print s}')" = 2 && uv run pytest -q tests/unit/shared/test_ffmpeg_pin_sync.py</automated>
  </verify>
  <done>Оба Dockerfile несут новый URL+SHA256, старых тега/хеша нет, комментарий объясняет политику «только сборка конца месяца», страж синхронности зелёный.</done>
</task>

<task type="auto">
  <name>Task 2: Уточнить запись о риске URL в CONCERNS.md и docker/README.md; проверить рантайм-сборку</name>
  <files>.planning/codebase/CONCERNS.md, docker/README.md</files>
  <action>
1. .planning/codebase/CONCERNS.md (~строки 250-254, раздел ffmpeg, английский как в файле): в «Residual risk (URL longevity)»
   отметить, что ежедневные autobuild-* удаляются ~через 2 недели (пин 2026-10-01 дал 404 на 2026-10-23),
   поэтому пин переведён на сохраняемую месячную сборку autobuild-2026-09-30-13-08 (n9.0.2-17-g2a571b6068);
   месячные тоже не гарантированы навсегда — Follow-up с зеркалированием остаётся, но фразу «SHA256 stays unchanged»
   оставить (верна для зеркала текущего архива). Status RESOLVED не менять.
2. docker/README.md, абзац «URL longevity» (~строка 77-79, русский): добавить одно предложение — пиним только
   последнюю сборку месяца, ежедневные BtbN удаляет примерно через 2 недели.
3. Проверка рантайм-образа: `podman build -f Dockerfile -t enpipe-gpq-check .` из /home/logovo/enpipe
   (run_in_background при необходимости, таймаут сборки большой). Нужно, чтобы прошёл шаг RUN с ffmpeg
   (в логе строка «ffmpeg version n9.0.2-17-g2a571b6068…» и `sha256sum` «OK»). Если сборка падает на шаге ПОСЛЕ
   ffmpeg по причине, не связанной с пином (сеть, секрет github_token), — зафиксировать это в SUMMARY,
   шаг ffmpeg считается подтверждённым. После проверки удалить тестовый образ (`podman rmi enpipe-gpq-check`).
   Пересборку devcontainer не повторять — оркестратор уже прогнал её с этими build-arg.
  </action>
  <verify>
    <automated>cd /home/logovo/enpipe && grep -q 'autobuild-2026-09-30-13-08' .planning/codebase/CONCERNS.md && grep -q 'сборк.* месяц\|месячн' docker/README.md && uv run pytest -q tests/unit/shared</automated>
  </verify>
  <done>CONCERNS.md и docker/README.md отражают политику месячного пина; `podman build -f Dockerfile .` проходит шаг ffmpeg (sha256 OK, n9.0.2-17); unit-тесты shared зелёные.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Releases (BtbN) → сборка образа | скачиваемый бинарный архив ffmpeg — недоверенные данные |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gpq-01 | Tampering | загрузка ffmpeg tarball в обоих Dockerfile | mitigate | неизменённый `sha256sum -c` по ARG FFMPEG_SHA256 ДО распаковки; новый digest взят из GitHub API и подтверждён успешной сборкой; несовпадение роняет сборку |
| T-gpq-02 | Denial of Service | доступность URL BtbN | accept | пин на месячную сборку, которую BtbN сохраняет; при удалении сборка падает громко; зеркалирование остаётся follow-up в CONCERNS.md |
</threat_model>

<verification>
- grep старого тега/хеша (autobuild-2026-10-01, n9.0.2-22, g46d8f462ee, a6170faecf) в Dockerfile и .devcontainer/Dockerfile пуст.
- tests/unit/shared/test_ffmpeg_pin_sync.py зелёный.
- `podman build -f Dockerfile .` проходит шаг ffmpeg.
</verification>

<success_criteria>
Оба образа собираются с ffmpeg n9.0.2-17-g2a571b6068 (autobuild-2026-09-30-13-08, sha256 68ee6468…6269);
пины синхронны; комментарий у ARG фиксирует политику «только сборка конца месяца».
</success_criteria>

<output>
Create `.planning/quick/261023-gpq-ffmpeg-btbn-2026-09-30-404-autobuild-202/261023-gpq-SUMMARY.md` when done
</output>
