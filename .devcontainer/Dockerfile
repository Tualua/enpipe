# Медиа-стек для проекта: Intel Arc A380 (Alchemist) QSV/VA-API AV1.
# База — официальный Python devcontainer-образ (Debian 13 trixie): Python уже внутри,
# ставить python-фичей не нужно. Сюда добавляем только медиа-часть, которую фичами
# не поставить: драйверы Intel Media (iHD), ffmpeg с QSV, qsvencc (Rigaya),
# mkvtoolnix, dovi_tool. Node/Claude Code — через devcontainer features (devcontainer.json).
#
# Почему trixie, а не bookworm: prebuilt .deb qsvencc собран под Ubuntu 24.04 (glibc 2.39),
# а на bookworm (glibc 2.36) он не запустится. Trixie (glibc 2.41) его тянет, плюс более
# свежий iHD/oneVPL для Arc AV1.
FROM mcr.microsoft.com/devcontainers/python:3-3.12-trixie

ENV DEBIAN_FRONTEND=noninteractive

# --- Включить non-free/contrib: там лежит intel-media-va-driver-non-free (iHD для Arc) ---
# Trixie использует deb822-формат (/etc/apt/sources.list.d/debian.sources); на всякий
# случай поддерживаем и старый однострочный /etc/apt/sources.list.
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i -E 's/^(Components:.*)/\1 contrib non-free non-free-firmware/' \
            /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i -E 's/^(deb .*)/\1 contrib non-free non-free-firmware/' /etc/apt/sources.list; \
    fi

# --- Intel Media (VA-API/oneVPL) + ffmpeg(QSV) + mkvtoolnix ---
# intel-media-va-driver-non-free = драйвер iHD для Arc; libvpl2 = oneVPL-диспетчер;
# ocl-icd-libopencl1 = загрузчик OpenCL (qsvencc линкует libOpenCL.so.1 для VPP-фильтров).
# GPU-рантайм oneVPL в Debian называется libmfx-gen1.2 (в Ubuntu так же); держим перебор
# имён на случай смены базы. ПРИМЕЧАНИЕ: intel-opencl-icd (Intel NEO OpenCL) в trixie нет —
# OpenCL-фильтры qsvencc работать не будут, но базовый AV1-энкод через oneVPL — да.
# Если Arc-драйвер из дистрибутива подведёт — подложить свежий iHD/oneVPL вручную.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg jq xz-utils \
      tmux \
      intel-media-va-driver-non-free libva2 libva-drm2 vainfo \
      libvpl2 ocl-icd-libopencl1 \
      ffmpeg \
      mkvtoolnix \
    && ( for pkg in libmfx-gen1.2 libmfxgen1 libmfx-gen1; do \
             apt-get install -y --no-install-recommends "$pkg" && break || true; \
         done ) \
    && rm -rf /var/lib/apt/lists/*

# --- qsvencc (Rigaya) — последняя Ubuntu 24.04 .deb с GitHub Releases ---
# На trixie (glibc 2.41) ubuntu-24.04-сборка (glibc 2.39) запускается. НО .deb объявляет
# Depends: intel-opencl-icd, libmfx1 — обоих в Debian trixie нет (libmfx1 = мёртвый MSDK,
# Arc его не использует; intel-opencl-icd убран из trixie). Поэтому распаковываем .deb,
# вырезаем эти две зависимости из control, пересобираем и ставим через apt — так реальные
# зависимости (libc/libstdc++/…) резолвятся штатно. Рантайм oneVPL/OpenCL уже стоит выше.
RUN set -eux; \
    url="$(curl -fsSL https://api.github.com/repos/rigaya/QSVEnc/releases/latest \
          | jq -r '.assets[].browser_download_url | select(test("_amd64.deb$"))' | head -1)"; \
    test -n "$url"; \
    curl -fsSL -o /tmp/qsvencc.deb "$url"; \
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

# --- Фикс сборки под podman/buildah ---
# Devcontainer-фичи (node) запускают apt-get; apt роняет привилегии на непривилегированного
# пользователя _apt для apt-key, а тот не может писать в /tmp в этом окружении сборки
# ("Couldn't create temporary file /tmp/apt.conf.* for passing config to apt-key" →
# репозитории "не подписаны" → фича node падает). Отключаем apt-песочницу (apt от root)
# и чиним биты /tmp. Слой последний — кэш ранних слоёв не инвалидируется, а конфиг
# наследуется установкой фич поверх образа.
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/00-no-apt-sandbox \
    && chmod 1777 /tmp
