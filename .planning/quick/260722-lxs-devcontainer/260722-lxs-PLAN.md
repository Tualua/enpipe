---
phase: quick-260722-lxs
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .devcontainer/Dockerfile
  - .devcontainer/post-create.sh
autonomous: true
requirements: [DEV-TOOLS]
must_haves:
  truths:
    - "После пересборки devcontainer в образе доступны: skopeo, strace, rg, xxd, mediainfo, intel_gpu_top, hyperfine, 7z"
    - "Новые утилиты стоят в ОТДЕЛЬНОМ RUN-слое, не инвалидирующем кэш медиа-tools-слоя"
    - "У каждого пакета — русский WHY-комментарий, привязанный к сегодняшней QSV/media-отладке"
    - "post-create самопроверка терсно рапортует наличие новых утилит"
  artifacts:
    - path: ".devcontainer/Dockerfile"
      provides: "Отдельный apt-слой dev/debug-утилит"
      contains: "skopeo"
    - path: ".devcontainer/post-create.sh"
      provides: "Строки самопроверки новых утилит"
  key_links:
    - from: ".devcontainer/Dockerfile"
      to: "apt-get install --no-install-recommends"
      via: "единый RUN-слой + rm -rf /var/lib/apt/lists/*"
      pattern: "skopeo"
---

<objective>
Добавить в devcontainer (база intel/dlstreamer, Ubuntu 24.04) курируемый набор
dev/debug-утилит из конкретных болей сегодняшней глубокой QSV/media-отладки:
skopeo, strace, ripgrep(rg), xxd, mediainfo, intel-gpu-tools(intel_gpu_top),
hyperfine, p7zip-full(7z). Все — apt-пакеты Ubuntu 24.04 (main/universe).

Purpose: убрать «command not found» и слепые зоны, всплывшие в отладке
(инспекция OCI-образов, syscall/dlopen-трейс, hex-инспекция VMAF CSV,
видимость загрузки Arc GPU, воспроизводимый бенчмаркинг).
Output: новый выделенный RUN-слой в Dockerfile + компактный блок самопроверки
в post-create.sh.

ВАЖНО: собрать/проверить образ ЗДЕСЬ нельзя (нет docker/GPU). Проверка —
статическая (grep Dockerfile, `bash -n` post-create.sh). Пользователь ДОЛЖЕН
пересобрать devcontainer на хосте, чтобы утилиты появились.
</objective>

<execution_context>
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.2.0/workflows/execute-plan.md
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.2.0/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.devcontainer/Dockerfile
@.devcontainer/post-create.sh
</context>

<tasks>

<task type="auto">
  <name>Task 1: Отдельный apt-слой dev/debug-утилит в Dockerfile</name>
  <files>.devcontainer/Dockerfile</files>
  <action>
Добавить НОВЫЙ выделенный RUN-слой в секции инструментов Dockerfile (после
media-tools-блока строк 26-32 «Инструменты, которых нет в dlstreamer» и ПЕРЕД
блоком установки qsvencc на строке 44 — так изменение списка утилит не
инвалидирует кэш ни media-tools-слоя выше, ни тяжёлого qsvencc-слоя ниже).

Слой — ОДИН `RUN apt-get update && apt-get install -y --no-install-recommends \
... && rm -rf /var/lib/apt/lists/*`, ставящий РОВНО эти 8 пакетов:
skopeo, strace, ripgrep, xxd, mediainfo, intel-gpu-tools, hyperfine, p7zip-full.

Заголовок-баннер блока в существующем стиле (`# --- ... ---`), назвать как
dev/debug-утилиты (напр. «Dev/debug-утилиты (из болей QSV/media-отладки)»).
Русские WHY-комментарии в стиле файла — по одному на КАЖДЫЙ пакет, привязанные
к сегодняшней работе:
  - skopeo — инспекция/копирование OCI-образов без docker-демона (сегодня:
    вручную дёргали registry-API GHCR/DockerHub/Launchpad, чтобы осмотреть
    dlstreamer-образ и вытащить .deb драйверов).
  - strace — трейс syscall/dlopen (сегодня: смотрели, какой libmfx-gen
    рантайм грузит qsvencc; откатывались на LD_DEBUG).
  - ripgrep — быстрый рекурсивный поиск по исходникам/логам, бинарь `rg`
    (сегодня: тяжёлый grep/awk по C++-дереву QSVEnc и PSNR-логам).
  - xxd — hex/бинарная инспекция (сегодня: буквально `xxd: command not found`
    при разборе байтов tab/десятичная-запятая VMAF CSV).
  - mediainfo — богатая инспекция контейнера/потоков/HDR/DV-метаданных
    (media-transcode проект; дополняет ffprobe).
  - intel-gpu-tools — даёт `intel_gpu_top` для наблюдения загрузки движков Arc
    (сегодня: НОЛЬ видимости загрузки GPU в стресс-тестах конкурентного
    энкода). Отметить: может требовать root/CAP_PERFMON — здесь remoteUser root,
    ОК.
  - hyperfine — воспроизводимый бенчмаркинг (сегодня: fps энкода / wall-time
    3-way мерили руками).
  - p7zip-full — `7z` (собственный CI QSVEnc использует `7z h` для хеширования;
    общая работа с архивами).

Добавить оборонительный комментарий: universe включён по умолчанию на
официальной базе Ubuntu 24.04; если пакет из universe и репозиторий вдруг
выключен — сборка упадёт, фолбэк `add-apt-repository universe` (НЕ добавлять
software-properties-common без нужды).

НЕ трогать media-tools-блок (строки 26-32), qsvencc-, dovi_tool- и
podman-fix-блоки. Стиль форматирования — как в существующих RUN-слоях
(бэкслеш-перенос, пакеты с отступом).
  </action>
  <verify>
grep -nE 'skopeo|strace|ripgrep|xxd|mediainfo|intel-gpu-tools|hyperfine|p7zip-full' .devcontainer/Dockerfile — все 8 присутствуют в одном новом RUN-блоке; docker недоступен, сборку проверяет пользователь на хосте
  </verify>
  <done>
Новый RUN-слой с ровно 8 пакетами и rm -rf /var/lib/apt/lists/* добавлен между
media-tools- и qsvencc-блоками; у каждого пакета русский WHY-комментарий;
оборонительная заметка про universe присутствует; прочие блоки не тронуты.
  </done>
</task>

<task type="auto">
  <name>Task 2: Терсный блок самопроверки новых утилит в post-create.sh</name>
  <files>.devcontainer/post-create.sh</files>
  <action>
Расширить секцию «4) Самопроверка окружения» (строки 55-81) компактным
одна-строка-на-утилиту рапортом наличия новых утилит, в ТОМ ЖЕ стиле, что
существующие проверки (`printf "  name:  "; command -v X >/dev/null && ... ||
echo "НЕТ"`).

Проверить бинарями (не именами пакетов): rg, skopeo, strace, mediainfo,
intel_gpu_top, hyperfine, xxd, 7z. Держать терсно — версия/наличие в одну
строку каждая (для тех, у кого есть дешёвый `--version`, можно head -1; для
xxd/7z/intel_gpu_top достаточно «установлен»). Вставить логичным местом
(напр. после блока tmux/scenedetect, до node/npm), с коротким русским
баннером-подзаголовком.

`set -euo pipefail` уже в шапке — все проверки должны быть безопасны при
отсутствии бинаря (`command -v ... || echo "НЕТ"` не должен ронять скрипт).
Не менять существующие проверки, GPU-логику, uv-sync, npm-блоки.
  </action>
  <verify>
`bash -n .devcontainer/post-create.sh` — синтаксис ок; grep -nE 'rg|skopeo|strace|mediainfo|intel_gpu_top|hyperfine|xxd|7z' .devcontainer/post-create.sh показывает новые строки самопроверки
  </verify>
  <done>
Компактный блок самопроверки для 8 новых утилит добавлен в секцию проверок в
существующем стиле; `bash -n` проходит; остальные части скрипта не тронуты.
  </done>
</task>

</tasks>

<verification>
- grep подтверждает все 8 пакетов в одном новом RUN-слое Dockerfile
- Новый слой физически между media-tools- и qsvencc-блоками (кэш не ломается)
- `bash -n .devcontainer/post-create.sh` — синтаксис валиден
- У каждого пакета русский WHY-комментарий (ручная вычитка)
- Образ ЗДЕСЬ не собирается (нет docker/GPU) — финальную сборку и GPU-прогон
  выполняет пользователь на хосте (пересборка devcontainer)
</verification>

<success_criteria>
- .devcontainer/Dockerfile: новый выделенный apt-слой с ровно 8 dev/debug-
  утилитами (skopeo, strace, ripgrep, xxd, mediainfo, intel-gpu-tools,
  hyperfine, p7zip-full), каждый с русским WHY-комментарием, один RUN +
  rm -rf /var/lib/apt/lists/*, между media-tools- и qsvencc-блоками
- .devcontainer/post-create.sh: терсный блок самопроверки новых утилит
- Оба файла проходят статическую проверку (grep / bash -n)
- SUMMARY фиксирует: пользователь ДОЛЖЕН пересобрать devcontainer на хосте
</success_criteria>

<output>
Create `.planning/quick/260722-lxs-devcontainer/260722-lxs-SUMMARY.md` when done
</output>
