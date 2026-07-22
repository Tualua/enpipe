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
FROM intel/dlstreamer:latest
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

# --- qsvencc (Rigaya) — последняя Ubuntu 24.04 .deb с GitHub Releases ---
# База теперь сама Ubuntu 24.04 — .deb под ubuntu-24.04 нативно подходит (никакого
# междистрибутивного glibc-подбора, как было на Debian trixie). .deb объявляет
# Depends: intel-opencl-icd, libmfx1 — libmfx1 (мёртвый MSDK) Arc не использует,
# а Intel NEO OpenCL (intel-opencl-icd) на этой базе не устанавливаем; OpenCL-загрузчик
# для VPP уже стоит выше (ocl-icd-libopencl1). Поэтому распаковываем .deb, вырезаем
# эти две зависимости из control, пересобираем и ставим через apt — так реальные
# зависимости (libc/libstdc++/…) резолвятся штатно. Rigaya публикует .deb ПОДИСТРИБУТИВНО
# (Ubuntu20.04/22.04/24.04); база теперь Ubuntu 24.04 — берём именно Ubuntu24.04-ассет,
# с фолбэком на первый `_amd64.deb`, если схема именования сменится.
RUN set -eux; \
    assets="$(curl -fsSL https://api.github.com/repos/rigaya/QSVEnc/releases/latest \
              | jq -r '.assets[].browser_download_url | select(test("_amd64[.]deb$"))')"; \
    url="$(printf '%s\n' "$assets" | grep -iE 'ubuntu[._]?24[._]04' | head -1)"; \
    [ -n "$url" ] || url="$(printf '%s\n' "$assets" | head -1)"; \
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
