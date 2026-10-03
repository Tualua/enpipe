# Медиа-стек для проекта: Intel Arc A380 (Alchemist) QSV/VA-API AV1.
# База — intel/dlstreamer (Ubuntu 24.04): медиа-стек (драйвер iHD, oneVPL/vpl-gpu-rt,
# ffmpeg(QSV)) поставляется ВМЕСТЕ с образом, не собирается вручную из Debian
# non-free пакетов. Свежий iHD/oneVPL 26.2.2 под Arc AV1, меньше поверхности для
# ручного патчинга драйверов при смене базового дистрибутива. Поверх образа всё
# равно доставляем то, чего в dlstreamer нет: qsvencc (Rigaya), dovi_tool,
# mkvtoolnix, tmux. Node/Claude Code — через devcontainer features (devcontainer.json).
#
# Тег можно закрепить на конкретной еженедельной сборке ради воспроизводимости
# (пример: intel/dlstreamer:2026.2.0-YYYYMMDD-weekly-ubuntu24) вместо :latest.
FROM docker.io/intel/dlstreamer:latest
USER root
ENV IS_SANDBOX=1
ENV HTTPS_PROXY="http://10.224.30.233:20171"
ENV HTTP_PROXY="http://10.224.30.233:20171"
ENV http_proxy="http://10.224.30.233:20171"
ENV https_proxy="http://10.224.30.233:20171"
ENV DEBIAN_FRONTEND=noninteractive

# --- Инструменты, которых нет в dlstreamer ---
# Базовый медиа-стек (iHD/oneVPL/ffmpeg(QSV)) уже в dlstreamer — apt-пакеты драйвера
# и ffmpeg(QSV) здесь НЕ ставим (в отличие от старой Debian-базы). vainfo/ocl-icd-libopencl1/
# python3* ставим оборонительно (--no-install-recommends, безвредно, если уже есть):
# vainfo — диагностика VA-API в post-create; ocl-icd-libopencl1 — загрузчик OpenCL,
# который qsvencc линкует как libOpenCL.so.1 для VPP-фильтров; python3/python3-venv/
# python3-pip — Ubuntu 24.04 даёт python3 = 3.12 (нужен для uv в post-create).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg jq xz-utils \
      tmux \
      mkvtoolnix \
      vainfo ocl-icd-libopencl1 \
      python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# --- Dev/debug-утилиты (из болей сегодняшней QSV/media-отладки) ---
# Отдельный слой (не media-tools- и не qsvencc-блок): список утилит меняется
# чаще, чем медиа-стек, а вынос в свой RUN не инвалидирует кэш ни блока выше
# (mkvtoolnix/vainfo/python3), ни тяжёлого qsvencc-слоя ниже.
# Все 8 пакетов — из main/universe официальной Ubuntu 24.04; universe включён
# по умолчанию на этой базе. Если пакет из universe и репозиторий вдруг
# выключен — сборка упадёт на apt-get install; фолбэк — `add-apt-repository
# universe` (software-properties-common НЕ добавляем без реальной нужды).
#
# skopeo — инспекция/копирование OCI-образов без docker-демона (сегодня:
#   вручную дёргали registry-API GHCR/DockerHub/Launchpad, чтобы осмотреть
#   dlstreamer-образ и вытащить .deb драйверов).
# strace — трейс syscall/dlopen (сегодня: смотрели, какой libmfx-gen рантайм
#   грузит qsvencc; откатывались на LD_DEBUG).
# ripgrep — быстрый рекурсивный поиск по исходникам/логам, бинарь `rg`
#   (сегодня: тяжёлый grep/awk по C++-дереву QSVEnc и PSNR-логам).
# xxd — hex/бинарная инспекция (сегодня: буквально `xxd: command not found`
#   при разборе байтов tab/десятичная-запятая VMAF CSV).
# mediainfo — богатая инспекция контейнера/потоков/HDR/DV-метаданных
#   (media-transcode проект; дополняет ffprobe).
# intel-gpu-tools — даёт `intel_gpu_top` для наблюдения загрузки движков Arc
#   (сегодня: НОЛЬ видимости загрузки GPU в стресс-тестах конкурентного
#   энкода). Может требовать root/CAP_PERFMON — здесь remoteUser root, ОК.
# hyperfine — воспроизводимый бенчмаркинг (сегодня: fps энкода / wall-time
#   3-way мерили руками).
# p7zip-full — `7z` (собственный CI QSVEnc использует `7z h` для хеширования;
#   общая работа с архивами).
RUN apt-get update && apt-get install -y --no-install-recommends \
      skopeo \
      strace \
      ripgrep \
      xxd \
      mediainfo \
      intel-gpu-tools \
      hyperfine \
      p7zip-full \
    && rm -rf /var/lib/apt/lists/*

# --- qsvencc 8.32+vppsync6 (форк Tualua/QSVEnc) — пин по sha256 ---
# Почему форк, а не rigaya releases/latest: апстрим 8.32 уже содержит фикс
# межсессионной порчи кадров (rigaya/QSVEnc 45003f1, issue #308), но с
# --psnr/--ssim на Linux/VA он всё ещё ломается: метрика читает VPP-поверхность
# до завершения VPP (обрывы "Failed to copy input surface before video metric",
# неверные значения), а сбой задачи при flush молча обрезает выход (236 из 240
# кадров при rc=0 — блокер фазы 08). Кроме того, `--seek` в апстриме и в
# предыдущем пине (r4658) стартует на один GOP позже на TS/M2TS/MP4 (rc=255 "No video
# packets found!" в последней GOP).
# Provenance: релиз https://github.com/Tualua/QSVEnc/releases/tag/8.32-vppsync6;
# sha256 сверен с SHA256SUMS релиза и с digest на GitHub. Пакет
# `8.32+vppsync6`, `--version` даёт `8.32 (r4663)`. Состав: rigaya 8.32 +
# патчи #319, #320, #322 + исправление `--seek` (старт с первого keyframe на
# или после цели для любого контейнера) + исправление `--seekto` на TS/M2TS
# и для аудио.
# Зависимости .deb ослаблены (libc6>=2.31, libva-drm2, libva-x11-2, iHD|va-driver)
# — intel-opencl-icd/libmfx1 не объявлены, вырезать ничего не нужно (D-05).
# Официальный 8.33+ (с этими патчами) заменит форк — тогда сменить URL/SHA256.
ARG QSVENCC_URL=https://github.com/Tualua/QSVEnc/releases/download/8.32-vppsync6/qsvencc_8.32%2Bvppsync6_amd64_ubuntu2004.deb
ARG QSVENCC_SHA256=f7be83b667c801dd86e8a5b42fd4e11e2e60255aab0ee5dbff85dab03e0d6024
# apt-get update должен стоять непосредственно перед установкой .deb в том же RUN —
# зависимости .deb резолвятся по свежим спискам; не выносить в другой слой.
# Литерал 4663 должен равняться QSVENCC_MIN_REV (проверяет
# tests/unit/shared/test_qsvencc_threshold_sync.py); `--version` GPU не требует.
RUN set -eux; \
    curl -fsSL -o /tmp/qsvencc.deb "$QSVENCC_URL"; \
    echo "$QSVENCC_SHA256  /tmp/qsvencc.deb" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/qsvencc.deb; \
    command -v qsvencc; \
    ver="$(qsvencc --version)"; \
    printf '%s\n' "$ver" | head -1; \
    rev="$(printf '%s\n' "$ver" | sed -n '1s/.*(r\([0-9]*\)).*/\1/p')"; \
    test "${rev:-0}" -ge 4663; \
    rm -f /tmp/qsvencc.deb; rm -rf /var/lib/apt/lists/*

# --- dovi_tool (quietvoid) — статический musl-бинарь, дистрибутиво-независим ---
# DEBT-04: сейчас dovi_tool НЕ используется ни одним путём пайплайна (текущий
# DV-путь — qsvencc --dolby-vision-rpu copy, per-chunk, без dovi_tool). Держим
# его установленным ЦЕЛЕНАПРАВЛЕННО ради запланированной Phase-4 проверки
# точности DV RPU (TEST-04): сейчас пайплайн проверяет только агрегатный
# счётчик видео-кадров, а RPU-профиль/frame-count DV-проверка — цель Phase 4.
# ВАЖНО (не переоценивать): команда `dovi_tool extract-rpu` документирована
# только для HEVC-битстрима (см. legacy/encode_scenes.py:15-16 — "DV в AV1
# нельзя наложить пост-фактум, dovi_tool — только HEVC"), а выход этого
# пайплайна — AV1. Готового подтверждения, что dovi_tool умеет работать с
# AV1/OBU-выходом, НЕТ — Phase 4 должна сначала исследовать правильный
# способ DV-верификации для AV1 (C-API/OBU-поддержка dovi_tool новее версий,
# другой инструмент, или самодельная проверка наличия RPU), а не просто
# вызвать extract-rpu на .obu-файле.
RUN set -eux; \
    url="$(curl -fsSL https://api.github.com/repos/quietvoid/dovi_tool/releases/latest \
          | jq -r '.assets[].browser_download_url | select(test("x86_64-unknown-linux-musl.tar.gz$"))' | head -1)"; \
    test -n "$url"; \
    curl -fsSL -o /tmp/dovi.tgz "$url"; \
    tmpd="$(mktemp -d)"; \
    tar -xzf /tmp/dovi.tgz -C "$tmpd"; \
    install -m0755 "$(find "$tmpd" -type f -name dovi_tool | head -1)" /usr/local/bin/dovi_tool; \
    rm -rf "$tmpd" /tmp/dovi.tgz

# --- FFmpeg 8.1 (BtbN static GPL) — OPT-IN, side-by-side, НЕ заменяет системный ffmpeg ---
# Это ОТДЕЛЬНАЯ, параллельная сборка FFmpeg 8.1: ставится в /opt/ffmpeg-8.1 и
# выставляется на PATH как ffmpeg-8.1/ffprobe-8.1. Системный ffmpeg 6.1.1 из
# dlstreamer-базы НЕ трогается (никаких /usr/local/bin/ffmpeg-симлинков) — весь
# проверенный медиа-стек остаётся как есть, 8.1 доступен строго по явному вызову.
#
# ЗАЧЕМ это важно:
#  1) ffmpeg `av1_qsv` (и `hevc_qsv`) — путь энкода, ИММУННЫЙ к порче кадров:
#     конкурентный qsvencc при 10-bit + B-кадрах алиасит reference-surface'ы
#     между процессами (пересечение пулов поверхностей), что даёт рассинхрон
#     счётчика кадров — см. `.planning/debug/scene-chunk-frame-mismatch.md`.
#     У ffmpeg покомпонентные пулы поверхностей на процесс, поэтому этот класс
#     порчи ему не грозит. Это опорная причина держать 8.1 наготове.
#  2) 8.1 дополнительно приносит bitstream-фильтр `dovi_rpu` для проброса Dolby
#     Vision RPU, которого системный ffmpeg 6.1.1 НЕ умеет.
#
# КОМПРОМИСС ПО ПИНУ (осознанно принят, вариант «a»):
# BtbN публикует ПОДВИЖНЫЙ rolling-тег `latest` — ИМЯ ассета стабильно
# (ffmpeg-n8.1-latest-linux64-gpl-8.1.tar.xz), но его СОДЕРЖИМОЕ меняется ежедневно
# (сейчас резолвится в n8.1.2). Значит, сборки НЕ детерминированы. Мы сознательно
# принимаем это ради единообразия с тем, как qsvencc/dovi_tool выше уже тянут
# "последний GitHub-релиз". SHA256-верификация НЕ добавляется намеренно: у
# подвижного тега нет стабильной опубликованной контрольной суммы, к которой можно
# было бы привязаться (фиксируем это явно, а не умалчиваем). Ассет — public,
# тянется по HTTPS с GitHub, ставится в изолированный /opt-путь (не затеняет
# системный ffmpeg).
RUN set -eux; \
    curl -fsSL -o /tmp/ffmpeg-8.1.tar.xz \
      https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-linux64-gpl-8.1.tar.xz; \
    tmpd="$(mktemp -d)"; \
    tar -xJf /tmp/ffmpeg-8.1.tar.xz -C "$tmpd"; \
    mkdir -p /opt/ffmpeg-8.1/bin; \
    install -m0755 "$(find "$tmpd" -type f -name ffmpeg | head -1)" /opt/ffmpeg-8.1/bin/ffmpeg; \
    install -m0755 "$(find "$tmpd" -type f -name ffprobe | head -1)" /opt/ffmpeg-8.1/bin/ffprobe; \
    ln -sf /opt/ffmpeg-8.1/bin/ffmpeg /usr/local/bin/ffmpeg-8.1; \
    ln -sf /opt/ffmpeg-8.1/bin/ffprobe /usr/local/bin/ffprobe-8.1; \
    /usr/local/bin/ffmpeg-8.1 -hide_banner -version | head -1; \
    rm -rf "$tmpd" /tmp/ffmpeg-8.1.tar.xz

# --- Фикс сборки под podman/buildah ---
# Devcontainer-фичи (node) запускают apt-get; apt роняет привилегии на непривилегированного
# пользователя _apt для apt-key, а тот не может писать в /tmp в этом окружении сборки
# ("Couldn't create temporary file /tmp/apt.conf.* for passing config to apt-key" →
# репозитории "не подписаны" → фича node падает). Отключаем apt-песочницу (apt от root)
# и чиним биты /tmp. Слой последний — кэш ранних слоёв не инвалидируется, а конфиг
# наследуется установкой фич поверх образа.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/00-no-apt-sandbox \
    && chmod 1777 /tmp
