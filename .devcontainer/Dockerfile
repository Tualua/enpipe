# Медиа-стек для проекта: Intel Arc A380 (Alchemist) QSV/VA-API AV1.
# База — intel/dlstreamer (Ubuntu 24.04): медиа-стек (драйвер iHD, oneVPL/vpl-gpu-rt,
# ffmpeg 6.1.1) поставляется ВМЕСТЕ с образом, не собирается вручную из Debian
# non-free пакетов. Свежий iHD/oneVPL 26.2.2 под Arc AV1, меньше поверхности для
# ручного патчинга драйверов при смене базового дистрибутива. Поверх образа всё
# равно доставляем то, чего в dlstreamer нет: qsvencc (Rigaya), dovi_tool,
# mkvtoolnix, tmux и основной ffmpeg 9 (BtbN static, пин по sha256) поверх базового 6.1.1. Node/Claude Code — через devcontainer features (devcontainer.json).
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
# Базовый медиа-стек (iHD/oneVPL) уже в dlstreamer — apt-пакеты драйвера
# и ffmpeg здесь НЕ ставим (основной ffmpeg 9 — отдельным блоком ниже) (в отличие от старой Debian-базы). vainfo/ocl-icd-libopencl1/
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

# --- qsvencc 8.32+vppsync10 (форк Tualua/QSVEnc) — пин по sha256 ---
# Почему форк, а не rigaya releases/latest: форк несёт фикс `--trim` после
# `--seek` на open-GOP HEVC и экспериментальный `--av1-chroma-delta-q`.
# Provenance: релиз https://github.com/Tualua/QSVEnc/releases/tag/8.32-vppsync10
# (target 3552334); sha256 сверен с SHA256SUMS релиза и с digest на GitHub.
# Пакет `8.32+vppsync10`, `--version` даёт `8.32 (r4677)`. Состав: rigaya master
# 864a688 (после 8.32) с фиксами #319, #320, #322, #326, #328, #330, #332 и #333
# (VA decode-error останавливал OpenCL-путь и терял последние кадры; для enpipe
# важно, т.к. метрики --psnr/--ssim включены по умолчанию) + фикс форка: `--trim`
# после `--seek` на open-GOP HEVC (RASL не входят в trim offset), RADL для
# `--avsw` + экспериментальный `--av1-chroma-delta-q`, которому нужен патченный
# vpl-gpu-rt (ставится отдельным блоком ниже); enpipe опцию пока не использует.
# Зависимости .deb ослаблены (libc6>=2.31, libva-drm2, libva-x11-2, iHD|va-driver)
# — intel-opencl-icd/libmfx1 не объявлены, вырезать ничего не нужно (D-05).
# Официальный 8.33+ (с этими патчами) заменит форк — тогда сменить URL/SHA256.
ARG QSVENCC_URL=https://github.com/Tualua/QSVEnc/releases/download/8.32-vppsync10/qsvencc_8.32%2Bvppsync10_amd64_ubuntu2004.deb
ARG QSVENCC_SHA256=5f42839fc6cade05945d3b48f86bae8de8546fca60c9e7711a0863035edf1060
# apt-get update должен стоять непосредственно перед установкой .deb в том же RUN —
# зависимости .deb резолвятся по свежим спискам; не выносить в другой слой.
# Литерал 4677 должен равняться QSVENCC_MIN_REV (проверяет
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
    test "${rev:-0}" -ge 4677; \
    rm -f /tmp/qsvencc.deb; rm -rf /var/lib/apt/lists/*

# --- vpl-gpu-rt 26.3.2-av1auxdata (патченный oneVPL GPU-runtime) — пин по sha256 ---
# Provenance: тот же релиз 8.32-vppsync10 форка Tualua/QSVEnc, ассет
# vpl-gpu-rt-26.3.2-av1auxdata.tar.gz; sha256 сверен с SHA256SUMS.runtime релиза
# и с digest на GitHub. Содержимое: libmfx-gen.so.1.2.17 + симлинк
# libmfx-gen.so.1.2, av1-auxdata-accept.patch, LICENSE (MIT); собран на Ubuntu
# 24.04 (glibc 2.39), зависит только от libva, libva-drm, libdrm.
# Зачем: даёт qsvencc `--av1-chroma-delta-q` (enpipe её пока не использует,
# CAL-02). Почему /opt + ONEVPL_PRIORITY_PATH, а не подмена системной
# библиотеки: так рекомендует README форка; ONEVPL_SEARCH_PATH недостаточен —
# диспетчер всё равно берёт системный runtime. Без опции вывод энкодера
# побайтно как у стокового (проверено на A380).
# Защита версии: патченный runtime собран под libmfx-gen1.2 26.3.2, а системный
# пакет приходит из непинованного PPA — при другой версии ABI не гарантирован,
# сборка падает. Сравнение через case, а не -ge/-lt: тот шаблон ловит тест порога
# qsvencc.
ARG VPL_RT_URL=https://github.com/Tualua/QSVEnc/releases/download/8.32-vppsync10/vpl-gpu-rt-26.3.2-av1auxdata.tar.gz
ARG VPL_RT_SHA256=054b7887dfa88711bfcf9290536b9676b9d0d801b8fd39f2eb39b747a2de0a35
RUN set -eux; \
    v="$(dpkg-query -W -f='${Version}' libmfx-gen1.2)"; \
    case "$v" in \
        26.3.2-*) ;; \
        *) echo "ОШИБКА: системный libmfx-gen1.2 $v не совпадает с патченным vpl-gpu-rt 26.3.2 — возьмите tar под эту версию из релиза форка Tualua/QSVEnc и обновите ARG VPL_RT_URL/VPL_RT_SHA256" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/vpl-rt.tar.gz "$VPL_RT_URL"; \
    echo "$VPL_RT_SHA256  /tmp/vpl-rt.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/vpl-gpu-rt-av1auxdata; \
    tar -xzf /tmp/vpl-rt.tar.gz -C /opt/vpl-gpu-rt-av1auxdata --strip-components=1; \
    test -e /opt/vpl-gpu-rt-av1auxdata/lib/libmfx-gen.so.1.2; \
    rm -f /tmp/vpl-rt.tar.gz

# Патченный runtime выбирается диспетчером раньше системного (qsvencc и ffmpeg QSV).
ENV ONEVPL_PRIORITY_PATH=/opt/vpl-gpu-rt-av1auxdata/lib

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

# --- FFmpeg 9.0.2 (BtbN static GPL) — ОСНОВНОЙ ffmpeg/ffprobe, пин по URL + sha256 ---
# Системный ffmpeg 6.1.1 из dlstreamer-базы (/usr/bin/ffmpeg) остаётся на диске
# (часть базы, может использоваться dlstreamer/gstreamer), но затенён: /usr/local/bin
# стоит на PATH раньше /usr/bin.
# Почему BtbN static: в сборке есть bitstream-фильтр `dovi_rpu` с поддержкой AV1 и
# libdav1d с метаданными Dolby Vision (проверка DV в AV1-выходе), av1_qsv/hevc_qsv/
# vpp_qsv/scale_qsv, libopus/flac. Системный ffmpeg 6.1 AV1 DV проверить не умеет.
# Точная сборка (n9.0.2-22-g46d8f462ee, autobuild 2026-10-01) проверена на A380:
# `enpipe detect` даёт побайтно идентичные .scenes с ffmpeg 6.1 (dv-p81, hdr10plus).
# Пин — неизменяемый тег autobuild + sha256 (проверка ДО распаковки): сборка
# детерминирована, подмена архива роняет сборку образа. Оба Dockerfile обязаны нести
# одинаковые ARG FFMPEG_URL/FFMPEG_SHA256 (страж: tests/unit/shared/test_ffmpeg_pin_sync.py).
# Ставятся только ffmpeg и ffprobe в /opt/ffmpeg-9/bin; симлинки в /usr/local/bin
# (он на PATH раньше /usr/bin) делают их основными. Побочный довод: ffmpeg av1_qsv
# держит пулы поверхностей per-process и иммунен к межпроцессной порче кадров
# qsvencc (backlog 999.1).
# ОГРАНИЧЕНИЕ: BtbN чистит старые autobuild-релизы, URL РАНО ИЛИ ПОЗДНО даст 404 —
# сборка упадёт громко, а не молча. План: зеркалировать архив ассетом GitHub Release
# проекта (прецедент: deps-qsvencc-r4634) и сменить FFMPEG_URL; sha256 остаётся прежним.
ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-01-13-06/ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz
ARG FFMPEG_SHA256=a6170faecf757381ad0338d7a6ba26e97c2ebe2b9c1568633421e15d1ed436a9
RUN set -eux; \
    curl -fsSL -o /tmp/ffmpeg.tar.xz "$FFMPEG_URL"; \
    echo "$FFMPEG_SHA256  /tmp/ffmpeg.tar.xz" | sha256sum -c -; \
    tmpd="$(mktemp -d)"; \
    tar -xJf /tmp/ffmpeg.tar.xz -C "$tmpd"; \
    mkdir -p /opt/ffmpeg-9/bin; \
    install -m0755 "$(find "$tmpd" -type f -name ffmpeg | head -1)" /opt/ffmpeg-9/bin/ffmpeg; \
    install -m0755 "$(find "$tmpd" -type f -name ffprobe | head -1)" /opt/ffmpeg-9/bin/ffprobe; \
    ln -sf /opt/ffmpeg-9/bin/ffmpeg /usr/local/bin/ffmpeg; \
    ln -sf /opt/ffmpeg-9/bin/ffprobe /usr/local/bin/ffprobe; \
    test "$(command -v ffmpeg)" = /usr/local/bin/ffmpeg; \
    test "$(command -v ffprobe)" = /usr/local/bin/ffprobe; \
    ver="$(ffmpeg -hide_banner -version | head -1)"; \
    printf '%s\n' "$ver"; \
    case "$ver" in *n9.0.2*) ;; *) echo "ожидался ffmpeg n9.0.2" >&2; exit 1;; esac; \
    enc="$(ffmpeg -hide_banner -encoders)"; \
    bsf="$(ffmpeg -hide_banner -bsfs)"; \
    case "$enc" in *av1_qsv*) ;; *) echo "нет av1_qsv" >&2; exit 1;; esac; \
    case "$enc" in *libopus*) ;; *) echo "нет libopus" >&2; exit 1;; esac; \
    case "$bsf" in *dovi_rpu*) ;; *) echo "нет dovi_rpu" >&2; exit 1;; esac; \
    rm -rf "$tmpd" /tmp/ffmpeg.tar.xz

# --- podman-remote 5.8.2 (статический) — клиент к ХОСТОВОМУ rootless podman ---
# Сам podman в devcontainer не запускается: podman-remote ходит в сокет хоста,
# проброшенный в devcontainer.json (CONTAINER_HOST). Так рантайм-образ enpipe
# собирается и проверяется на GPU прямо из devcontainer. Версия = podman хоста
# (5.8.2 на NAS) — remote-API совместим в пределах мажора. Репозиторий переехал
# в podman-container-tools/podman; sha256 сверен с digest ассета релиза v5.8.2.
# Ссылка podman -> podman-remote: привычные команды из docker/README.md работают
# как есть. ВНИМАНИЕ: пути в `podman run -v` — это пути ХОСТА, не контейнера
# (общие для обоих — только /data/media и /data/downloads).
ARG PODMAN_REMOTE_URL=https://github.com/podman-container-tools/podman/releases/download/v5.8.2/podman-remote-static-linux_amd64.tar.gz
ARG PODMAN_REMOTE_SHA256=88f7c21e8399a8f5edd1ef7b5c2e12b29706d0a4f24463f264a0e88d887ebbbf
RUN set -eux; \
    curl -fsSL -o /tmp/podman-remote.tgz "$PODMAN_REMOTE_URL"; \
    echo "$PODMAN_REMOTE_SHA256  /tmp/podman-remote.tgz" | sha256sum -c -; \
    tmpd="$(mktemp -d)"; \
    tar -xzf /tmp/podman-remote.tgz -C "$tmpd"; \
    install -m0755 "$tmpd/bin/podman-remote-static-linux_amd64" /usr/local/bin/podman-remote; \
    ln -sf podman-remote /usr/local/bin/podman; \
    rm -rf "$tmpd" /tmp/podman-remote.tgz; \
    podman-remote --version | grep -q 'version 5.8.2'

# --- Фикс сборки под podman/buildah ---
# Devcontainer-фичи (node) запускают apt-get; apt роняет привилегии на непривилегированного
# пользователя _apt для apt-key, а тот не может писать в /tmp в этом окружении сборки
# ("Couldn't create temporary file /tmp/apt.conf.* for passing config to apt-key" →
# репозитории "не подписаны" → фича node падает). Отключаем apt-песочницу (apt от root)
# и чиним биты /tmp. Слой последний — кэш ранних слоёв не инвалидируется, а конфиг
# наследуется установкой фич поверх образа.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/00-no-apt-sandbox \
    && chmod 1777 /tmp
