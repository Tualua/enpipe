# Слим-РАНТАЙМ-образ enpipe (продовый прогон на NAS/хосте с Intel Arc).
# Это ОТДЕЛЬНЫЙ образ от `.devcontainer/Dockerfile` (там — полная dev-среда с
# node/tmux/git/AI-CLI/GSD для интерактивной разработки внутри Claude Code).
# Здесь — только то, что нужно, чтобы выполнить `enpipe run <video>` в проде:
# venv с пакетом enpipe (НЕ editable, из pinned uv.lock) + медиа-рантайм
# (iHD/oneVPL/ffmpeg/mkvtoolnix/qsvencc/dovi_tool). Медиа-рецепты ниже
# переиспользованы ДОСЛОВНО из .devcontainer/Dockerfile — тот же проверенный
# набор пакетов/трюков, без изменений логики.

# ==================== STAGE 1: builder ====================
# Ставим пакет enpipe в чистый /opt/venv настоящим wheel'ом (build-backend
# uv_build), а не editable-ссылкой на src/ — так финальный runtime-слой не
# зависит от исходников/build-инструментов, только от готового venv.
FROM python:3.12-slim-trixie AS builder

# uv берём готовым бинарником из официального образа astral-sh — так быстрее
# и без лишней pip-установки в builder-слое. В проде тег стоит закрепить
# дайджестом (не latest), latest допустим здесь как devcontainer-подобная
# среда с явным этим предупреждением.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV_PROJECT_ENVIRONMENT — ставить именно в /opt/venv (а не в проектный
# .venv), т.к. этот путь потом переносится в runtime-стадию как есть.
# UV_COMPILE_BYTECODE — .pyc заранее, чтобы рантайм не тратил время на
# компиляцию при первом импорте. UV_LINK_MODE=copy — hardlink между слоями
# Docker невозможен (разные ФС-слои), copy тише варнингов uv.
ENV UV_PYTHON=python3.12 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Копируем ТОЛЬКО манифесты и исходники — раздельными слоями, чтобы правка
# src/ не инвалидировала кэш зависимостей (pyproject.toml/uv.lock меняются
# реже, чем код).
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# --frozen — установить строго по коммитнутому uv.lock, без пересчёта
# резолвера (никаких новых версий зависимостей исподтишка).
# --no-dev — выкинуть dev-группу (pytest/pytest-subprocess/pytest-mock/
# ruff), она в рантайме не нужна и раздувает образ.
# --no-editable — поставить enpipe как настоящий wheel в site-packages, а
# не .pth-ссылку на src/; это гарантирует, что финальному runtime-слою
# исходники src/ не нужны вовсе (копируется только /opt/venv).
RUN uv sync --frozen --no-dev --no-editable

# ==================== STAGE 2: runtime ====================
# Без "AS" — финальная стадия. Та же база python:3.12-slim-trixie, что и у
# builder: одна и та же ФС-раскладка/glibc/python-путь, поэтому venv-copy
# из builder переносится как есть, без пересборки нативных расширений.
#
# Почему trixie: prebuilt .deb qsvencc собран под glibc >= 2.39 (см. ниже),
# на bookworm (glibc 2.36) он не запустится — тот же довод, что и в
# .devcontainer/Dockerfile.
# Почему slim, а не devcontainer-база (mcr.microsoft.com/devcontainers/...):
# devcontainer-база несёt VS Code Server, python-фичи и прочую dev-обвязку,
# которая в проде не нужна — здесь нужен только голый Python + медиа-стек.
# ВАЖНО: OpenCL-VPP-фильтры qsvencc (--psnr/--ssim) в этом образе НЕ
# работают — в Debian trixie нет пакета intel-opencl-icd (Intel NEO OpenCL),
# ровно как и в .devcontainer/Dockerfile. Базовый AV1-энкод через oneVPL
# при этом работает штатно; для прод-энкода использовать --no-metrics.
FROM python:3.12-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive

# --- Включить non-free/contrib: там лежит intel-media-va-driver-non-free (iHD для Arc) ---
# ДОСЛОВНО как .devcontainer/Dockerfile: trixie использует deb822-формат
# (/etc/apt/sources.list.d/debian.sources), на всякий случай поддерживаем и
# старый однострочный /etc/apt/sources.list.
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i -E 's/^(Components:.*)/\1 contrib non-free non-free-firmware/' \
            /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i -E 's/^(deb .*)/\1 contrib non-free non-free-firmware/' /etc/apt/sources.list; \
    fi

# --- Intel Media (VA-API/oneVPL) + ffmpeg(QSV) + mkvtoolnix ---
# ДОСЛОВНО как .devcontainer/Dockerfile, но БЕЗ tmux (интерактивный
# dev-инструмент, в рантайм-образе не нужен). intel-media-va-driver-non-free
# = драйвер iHD для Arc; libvpl2 = oneVPL-диспетчер; ocl-icd-libopencl1 =
# загрузчик OpenCL (qsvencc линкует libOpenCL.so.1 для VPP-фильтров, но
# см. предупреждение выше про intel-opencl-icd). GPU-рантайм oneVPL в Debian
# называется libmfx-gen1.2 (в Ubuntu так же); держим перебор имён на случай
# смены базы.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg jq xz-utils \
      intel-media-va-driver-non-free libva2 libva-drm2 vainfo \
      libvpl2 ocl-icd-libopencl1 \
      ffmpeg \
      mkvtoolnix \
    && ( for pkg in libmfx-gen1.2 libmfxgen1 libmfx-gen1; do \
             apt-get install -y --no-install-recommends "$pkg" && break || true; \
         done ) \
    && rm -rf /var/lib/apt/lists/*

# --- qsvencc (Rigaya) — последняя Ubuntu 24.04 .deb с GitHub Releases ---
# ДОСЛОВНО как .devcontainer/Dockerfile: на trixie (glibc 2.41) сборка под
# Ubuntu 24.04 (glibc 2.39) запускается, но .deb объявляет Depends:
# intel-opencl-icd, libmfx1 — обоих в Debian trixie нет (libmfx1 = мёртвый
# MSDK, Arc его не использует; intel-opencl-icd убран из trixie). Поэтому
# распаковываем .deb, вырезаем эти две зависимости из control, пересобираем
# и ставим через apt — так реальные зависимости (libc/libstdc++/…)
# резолвятся штатно. Рантайм oneVPL/OpenCL уже стоит выше.
#
# Опциональная авторизация к api.github.com: неавторизованный лимит —
# 60 запросов/час НА ОБЩИЙ IP раннера (флаки-403 на shared CI-раннерах);
# секрет опционален (required=false), локальная сборка без него ведёт
# себя как раньше; с токеном лимит поднимается до 5000/час.
RUN --mount=type=secret,id=github_token,required=false set -eux; \
    if [ -s /run/secrets/github_token ]; then \
        set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; \
    else \
        set --; \
    fi; \
    url="$(curl -fsSL "$@" https://api.github.com/repos/rigaya/QSVEnc/releases/latest \
          | jq -r '.assets[].browser_download_url | select(test("_amd64.deb$"))' | head -1)"; \
    test -n "$url"; \
    curl -fsSL "$@" -o /tmp/qsvencc.deb "$url"; \
    tmpd="$(mktemp -d)"; \
    dpkg-deb -R /tmp/qsvencc.deb "$tmpd"; \
    awk 'BEGIN{FS=OFS=": "} /^Depends:/{n=split($2,a,","); s=""; for(i=1;i<=n;i++){t=a[i]; gsub(/^[ \t]+|[ \t]+$/,"",t); g=t; sub(/[ (|].*/,"",g); if(g!="intel-opencl-icd" && g!="libmfx1"){s=(s==""?t:s","t)}} $0="Depends: " s} {print}' \
        "$tmpd/DEBIAN/control" > "$tmpd/DEBIAN/control.new"; \
    mv "$tmpd/DEBIAN/control.new" "$tmpd/DEBIAN/control"; \
    grep '^Depends:' "$tmpd/DEBIAN/control"; \
    dpkg-deb -b "$tmpd" /tmp/qsvencc-fixed.deb; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/qsvencc-fixed.deb; \
    command -v qsvencc; \
    rm -rf "$tmpd" /tmp/qsvencc.deb /tmp/qsvencc-fixed.deb; rm -rf /var/lib/apt/lists/*

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
RUN --mount=type=secret,id=github_token,required=false set -eux; \
    if [ -s /run/secrets/github_token ]; then \
        set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; \
    else \
        set --; \
    fi; \
    url="$(curl -fsSL "$@" https://api.github.com/repos/quietvoid/dovi_tool/releases/latest \
          | jq -r '.assets[].browser_download_url | select(test("x86_64-unknown-linux-musl.tar.gz$"))' | head -1)"; \
    test -n "$url"; \
    curl -fsSL "$@" -o /tmp/dovi.tgz "$url"; \
    tmpd="$(mktemp -d)"; \
    tar -xzf /tmp/dovi.tgz -C "$tmpd"; \
    install -m0755 "$(find "$tmpd" -type f -name dovi_tool | head -1)" /usr/local/bin/dovi_tool; \
    rm -rf "$tmpd" /tmp/dovi.tgz

# Переносим готовый venv из builder-стадии целиком — никаких исходников
# src/, build-инструментов или dev-зависимостей в этом слое нет.
COPY --from=builder /opt/venv /opt/venv

# PATH — чтобы `enpipe` резолвился из venv без активации.
# LIBVA_DRIVER_NAME=iHD — выбор Intel Media-драйвера для VA-API, тот же
# containerEnv, что задан в .devcontainer/devcontainer.json.
ENV PATH="/opt/venv/bin:$PATH" \
    LIBVA_DRIVER_NAME=iHD

ENTRYPOINT ["enpipe"]
CMD ["--help"]
