# Слим-РАНТАЙМ-образ enpipe (продовый прогон на NAS/хосте с Intel Arc).
# Это ОТДЕЛЬНЫЙ образ от `.devcontainer/Dockerfile` (там - полная dev-среда с
# node/tmux/git/AI-CLI/GSD для интерактивной разработки внутри Claude Code).
# Здесь - только то, что нужно, чтобы выполнить `enpipe run <video>` в проде:
# venv с пакетом enpipe (НЕ editable, из pinned uv.lock) + медиа-рантайм
# (iHD/oneVPL/OpenCL/ffmpeg/mkvtoolnix/qsvencc/dovi_tool).

# ==================== STAGE 1: builder ====================
# Ставим пакет enpipe в чистый /opt/venv настоящим wheel'ом (build-backend
# uv_build), а не editable-ссылкой на src/ - так финальный runtime-слой не
# зависит от исходников/build-инструментов, только от готового venv.
# База та же, что у runtime: venv хранит ссылку на интерпретатор, которым
# создан, поэтому у обеих стадий обязан быть один и тот же /usr/bin/python3.12.
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.12 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv берём готовым бинарником из официального образа astral-sh - так быстрее
# и без лишней pip-установки в builder-слое. В проде тег стоит закрепить
# дайджестом (не latest), latest допустим здесь как devcontainer-подобная
# среда с явным этим предупреждением.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV_PYTHON=/usr/bin/python3.12 + UV_PYTHON_DOWNLOADS=never - использовать
# именно системный интерпретатор (тот же путь будет в runtime), а не скачивать
# свой. UV_PROJECT_ENVIRONMENT - ставить в /opt/venv, этот путь переносится в
# runtime-стадию как есть. UV_COMPILE_BYTECODE - .pyc заранее. UV_LINK_MODE=copy -
# hardlink между слоями Docker невозможен, copy тише варнингов uv.
ENV UV_PYTHON=/usr/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Копируем ТОЛЬКО манифесты и исходники - раздельными слоями, чтобы правка
# src/ не инвалидировала кэш зависимостей (pyproject.toml/uv.lock меняются
# реже, чем код).
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# --frozen - установить строго по коммитнутому uv.lock, без пересчёта
# резолвера (никаких новых версий зависимостей исподтишка).
# --no-dev - выкинуть dev-группу (pytest/pytest-subprocess/pytest-mock/
# ruff), она в рантайме не нужна и раздувает образ.
# --no-editable - поставить enpipe как настоящий wheel в site-packages, а
# не .pth-ссылку на src/; это гарантирует, что финальному runtime-слою
# исходники src/ не нужны вовсе (копируется только /opt/venv).
RUN uv sync --frozen --no-dev --no-editable

# ==================== STAGE 2: runtime ====================
# Без "AS" - финальная стадия. Та же база ubuntu:24.04, что и у builder: тот же
# /usr/bin/python3.12, поэтому venv-copy из builder переносится как есть.
#
# Почему ubuntu:24.04: ради Intel graphics PPA (kobuk-team) с intel-opencl-icd.
# Без OpenCL-рантайма VPP-фильтры qsvencc (--psnr/--ssim) не работают, а они
# включены в пути по умолчанию. glibc 2.39 заодно удовлетворяет .deb qsvencc.
# Метрики qsvencc на этом стеке нестабильны (VIDEOMETRIC: Failed to copy input
# surface, известный дефект D-12 в бэклоге) - это не дефект образа.
# Почему не devcontainer-база: она несёт VS Code Server и dev-обвязку, а в проде
# нужен только голый Python + медиа-стек.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- Intel graphics PPA + медиа/OpenCL-стек ---
# Тот же PPA, что в девконтейнере (сам девконтейнер на базе intel/dlstreamer,
# а не на голом ubuntu:24.04). PPA подключается deb822-файлом .sources, а ключ
# скачивается по закреплённому отпечатку и сверяется с ним до записи в keyring:
# так нет обращения к Launchpad API, нет лишних пакетов (software-properties-
# common, gpg-agent), а подмена ключа на сервере роняет сборку. PPA плавающая
# (не версионируется), поэтому версии стека фиксируются в доказательствах (D-11).
# intel-media-va-driver-non-free = iHD для Arc; libvpl2 = oneVPL-диспетчер;
# libmfx-gen1.2 = GPU-рантайм oneVPL; intel-opencl-icd + ocl-icd-libopencl1 =
# OpenCL для VPP-фильтров qsvencc; clinfo - диагностика видимости устройства.
ARG INTEL_PPA_KEY_FPR=0C0E6AF955CE463C03FC51574D098D70AFBE5E1F
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    export GNUPGHOME="$(mktemp -d)"; \
    curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x${INTEL_PPA_KEY_FPR}" \
         -o /tmp/intel-ppa.asc; \
    gpg --show-keys --with-colons /tmp/intel-ppa.asc | grep -q "^fpr:::::::::${INTEL_PPA_KEY_FPR}:"; \
    install -d -m 0755 /etc/apt/keyrings; \
    gpg --dearmor -o /etc/apt/keyrings/kobuk-team-intel-graphics.gpg /tmp/intel-ppa.asc; \
    rm -rf /tmp/intel-ppa.asc "$GNUPGHOME"; \
    printf '%s\n' \
        'Types: deb' \
        'URIs: https://ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/' \
        'Suites: noble' \
        'Components: main' \
        'Signed-By: /etc/apt/keyrings/kobuk-team-intel-graphics.gpg' \
        > /etc/apt/sources.list.d/kobuk-team-ubuntu-intel-graphics-noble.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      jq xz-utils \
      intel-media-va-driver-non-free libmfx-gen1.2 libvpl2 \
      libva2 libva-drm2 vainfo \
      intel-opencl-icd ocl-icd-libopencl1 clinfo \
      ffmpeg \
      mkvtoolnix \
      python3.12; \
    rm -rf /var/lib/apt/lists/*

# --- qsvencc 8.32+vppsync4 (форк Tualua/QSVEnc) — пин по sha256 ---
# Почему форк, а не rigaya releases/latest: апстрим 8.32 уже содержит фикс
# межсессионной порчи кадров (rigaya/QSVEnc 45003f1, issue #308), но с
# --psnr/--ssim на Linux/VA он всё ещё ломается: метрика читает VPP-поверхность
# до завершения VPP (обрывы "Failed to copy input surface before video metric",
# неверные значения), а сбой задачи при flush молча обрезает выход (236 из 240
# кадров при rc=0 — блокер фазы 08). Форк = тег 8.32 + три патча, предложенные
# в апстрим (#319, #320, SSIM > 1.0 при плоскости не кратной 4).
# Provenance: релиз https://github.com/Tualua/QSVEnc/releases/tag/8.32-vppsync4,
# коммит 94d6f7b851843d5fa1bd0ea116bc1d65f15753b0; sha256 сверен с SHA256SUMS
# релиза. Пакет `8.32+vppsync4`, `--version` даёт `8.32 (r4658)`.
# Зависимости .deb ослаблены (libc6>=2.31, libva-drm2, libva-x11-2, iHD|va-driver)
# — intel-opencl-icd/libmfx1 не объявлены, вырезать ничего не нужно (D-05).
# Официальный 8.33+ (с этими патчами) заменит форк — тогда сменить URL/SHA256.
ARG QSVENCC_URL=https://github.com/Tualua/QSVEnc/releases/download/8.32-vppsync4/qsvencc_8.32%2Bvppsync4_amd64_ubuntu2004.deb
ARG QSVENCC_SHA256=d2aa8412591d49f4b1febac8561301a8d97a654d42188cc4d2dee6c1775e6cb6
# Токен github_token опционален (репозиторий публичный): нужен только для
# приватных форков / лимитов загрузки с github.com. xtrace отключён вокруг чтения
# секрета и авторизованного curl — иначе токен печатается в лог сборки.
# apt-get update должен стоять непосредственно перед установкой .deb в том же RUN —
# зависимости .deb резолвятся по свежим спискам; не выносить в другой слой.
# Литерал 4634 должен равняться QSVENCC_MIN_REV (проверяет
# tests/unit/shared/test_qsvencc_threshold_sync.py); `--version` GPU не требует.
RUN --mount=type=secret,id=github_token,required=false set -eu; \
    set +x; \
    if [ -s /run/secrets/github_token ]; then \
        set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; \
    else \
        set --; \
    fi; \
    curl -fsSL "$@" -o /tmp/qsvencc.deb "$QSVENCC_URL"; \
    set -x; \
    echo "$QSVENCC_SHA256  /tmp/qsvencc.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/qsvencc.deb; \
    command -v qsvencc; \
    ver="$(qsvencc --version)"; \
    printf '%s\n' "$ver" | head -1; \
    rev="$(printf '%s\n' "$ver" | sed -n '1s/.*(r\([0-9]*\)).*/\1/p')"; \
    test "${rev:-0}" -ge 4634; \
    rm -f /tmp/qsvencc.deb; rm -rf /var/lib/apt/lists/*

# --- Самопроверка стека (D-07) ---
# При сборке GPU нет, поэтому проверяются только файлы; видимость устройства
# проверяет `clinfo -l` на хосте. Путь библиотеки берётся из ICD-файла, а не
# хардкодится: проверка переживёт смену раскладки пакета.
RUN set -eux; \
    test -s /etc/OpenCL/vendors/intel.icd; \
    lib="$(head -n1 /etc/OpenCL/vendors/intel.icd)"; \
    test -n "$lib"; \
    test -e "$lib"; \
    command -v clinfo; \
    qsvencc --version | head -1

# --- dovi_tool (quietvoid) — статический musl-бинарь, дистрибутиво-независим ---
# ДОСЛОВНО как .devcontainer/Dockerfile. Сейчас dovi_tool НЕ используется ни
# одним путём пайплайна (текущий DV-путь — qsvencc --dolby-vision-rpu copy,
# per-chunk, без dovi_tool); держим его установленным ЦЕЛЕНАПРАВЛЕННО ради
# запланированной точной DV RPU-проверки (см. DEBT-04 в .devcontainer/
# Dockerfile) — по решению пользователя оставить и в рантайм-образе.
#
# Опциональная авторизация к api.github.com: неавторизованный лимит —
# 60 запросов/час НА ОБЩИЙ IP раннера (флаки-403 на shared CI-раннерах);
# секрет опционален (required=false), локальная сборка без него ведёт
# себя как раньше; с токеном лимит поднимается до 5000/час.
# xtrace отключён вокруг чтения секрета и обоих авторизованных curl (как в блоке
# qsvencc выше): при `set -x` оболочка печатает уже раскрытый
# `set -- -H 'Authorization: Bearer ...'` и curl-строки, т.е. токен попал бы в
# лог сборки (WR-04). `set --` в конце сбрасывает заголовок из позиционных
# параметров до включения xtrace обратно.
RUN --mount=type=secret,id=github_token,required=false set -eu; \
    set +x; \
    if [ -s /run/secrets/github_token ]; then \
        set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; \
    else \
        set --; \
    fi; \
    url="$(curl -fsSL "$@" https://api.github.com/repos/quietvoid/dovi_tool/releases/latest \
          | jq -r '.assets[].browser_download_url | select(test("x86_64-unknown-linux-musl.tar.gz$"))' | head -1)"; \
    test -n "$url"; \
    curl -fsSL "$@" -o /tmp/dovi.tgz "$url"; \
    set --; \
    set -x; \
    tmpd="$(mktemp -d)"; \
    tar -xzf /tmp/dovi.tgz -C "$tmpd"; \
    install -m0755 "$(find "$tmpd" -type f -name dovi_tool | head -1)" /usr/local/bin/dovi_tool; \
    rm -rf "$tmpd" /tmp/dovi.tgz

# Переносим готовый venv из builder-стадии целиком - никаких исходников
# src/, build-инструментов или dev-зависимостей в этом слое нет.
COPY --from=builder /opt/venv /opt/venv

# PATH - чтобы `enpipe` резолвился из venv без активации.
# LIBVA_DRIVER_NAME=iHD - выбор Intel Media-драйвера для VA-API, тот же
# containerEnv, что задан в .devcontainer/devcontainer.json.
ENV PATH="/opt/venv/bin:$PATH" \
    LIBVA_DRIVER_NAME=iHD

RUN enpipe --help >/dev/null

ENTRYPOINT ["enpipe"]
CMD ["--help"]
