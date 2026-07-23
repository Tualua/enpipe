#!/usr/bin/env bash
# Финальная настройка devcontainer'а: права на GPU, npm-агенты (opencode/qwen),
# Python-зависимости проекта, самопроверка окружения. Идемпотентно.
set -euo pipefail

echo "==================================================================="
echo "== post-create: GPU / npm-агенты / python-deps / проверки =="
echo "==================================================================="

# --- 1) Доступ к Intel Arc: добавить пользователя в группу render-узла ---
# GID группы, владеющей /dev/dri/renderD128, зависит от хоста -> определяем на лету.
# remoteUser здесь root, а в базе intel/dlstreamer sudo может отсутствовать
# (старый python-образ его гарантированно ставил вместе с vscode-юзером) —
# запускаем groupadd/usermod напрямую, если уже root, и через sudo только
# если он реально есть; так скрипт работает на обеих базах без правки.
echo "-- GPU: /dev/dri --"
if [ "$(id -u)" -eq 0 ]; then
    AS_ROOT=()
elif command -v sudo >/dev/null 2>&1; then
    AS_ROOT=(sudo)
else
    AS_ROOT=()
fi
if [ -e /dev/dri/renderD128 ]; then
    RGID="$(stat -c '%g' /dev/dri/renderD128)"
    if ! getent group "$RGID" >/dev/null 2>&1; then
        "${AS_ROOT[@]}" groupadd -g "$RGID" render-host || true
    fi
    "${AS_ROOT[@]}" usermod -aG "$RGID" "$(id -un)" || true
    echo "   renderD128 GID=$RGID -> пользователь добавлен (перелогинь терминал, если GPU не виден сразу)"
else
    echo "   ВНИМАНИЕ: /dev/dri/renderD128 не проброшен — QSV/VA-API работать не будет."
    echo "            Проверь runArgs --device=/dev/dri и наличие Arc на хосте."
fi

# --- 2) AI-CLI через npm (Claude Code уже поставлен devcontainer-фичей) ---
echo "-- npm: opencode + qwen-code --"
npm install -g opencode-ai @qwen-code/qwen-code

# --- 2b) Claude Code: плагин GSD (маркетплейс gsd-plugin, плагин gsd) ---
echo "-- claude plugin: jnuyens/gsd-plugin --"
claude plugin marketplace add jnuyens/gsd-plugin || echo "   marketplace add не удался (сеть?)"
claude plugin install gsd@gsd-plugin || echo "   install gsd@gsd-plugin не удался"

# --- 3) Python-зависимости проекта (uv + committed uv.lock) ---
# Зависимости зафиксированы в pyproject.toml/uv.lock; окружение ставится
# командой `uv sync --locked`, а не разовым unpinned `pip install`.
echo "-- uv: sync --locked --"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv sync --locked

# --- 4) Самопроверка окружения ---
echo "-- проверки --"
echo "  VA-API:"
vainfo 2>/dev/null | grep -iE 'Driver version|VAProfileAV1|VAProfileHEVCMain10' | sed 's/^/    /' \
    || echo "    vainfo не отдал профили (GPU/драйвер?)"
echo "  ffmpeg QSV-энкодеры:"
ffmpeg -hide_banner -encoders 2>/dev/null | grep -iE 'av1_qsv|hevc_qsv' | sed 's/^/    /' \
    || echo "    QSV-энкодеров нет"
# ffmpeg-8.1 — opt-in параллельная сборка (BtbN static), не заменяет системный
# ffmpeg. Информационно, НИКОГДА не роняет скрипт под set -euo pipefail:
# каждая под-команда прикрыта `|| echo ...` / `2>/dev/null`.
echo "  ffmpeg-8.1 (opt-in, BtbN static):"
if command -v ffmpeg-8.1 >/dev/null 2>&1; then
    ffmpeg-8.1 -hide_banner -version 2>/dev/null | head -1 | sed 's/^/    /' \
        || echo "    версию получить не удалось"
    ffmpeg-8.1 -hide_banner -encoders 2>/dev/null | grep -iE 'av1_qsv|hevc_qsv' | sed 's/^/    /' \
        || echo "    QSV-энкодеров нет"
    ffmpeg-8.1 -hide_banner -bsfs 2>/dev/null | grep -i 'dovi_rpu' | sed 's/^/    /' \
        || echo "    dovi_rpu BSF нет"
else
    echo "    не установлен (пересобери образ)"
fi
printf "  qsvencc:   "; command -v qsvencc >/dev/null && qsvencc --version 2>/dev/null | head -1 || echo "НЕТ"
# dovi_tool: пока нигде в пайплайне не вызывается — держим ради Phase-4 DV RPU
# проверки (TEST-04, DEBT-04); AV1-совместимость extract-rpu НЕ подтверждена,
# см. комментарий у RUN-блока установки в Dockerfile.
printf "  dovi_tool: "; command -v dovi_tool >/dev/null && dovi_tool --version 2>/dev/null || echo "НЕТ"
printf "  mkvmerge:  "; command -v mkvmerge >/dev/null && mkvmerge --version 2>/dev/null | head -1 || echo "НЕТ"
printf "  tmux:      "; command -v tmux >/dev/null && tmux -V || echo "НЕТ"
printf "  scenedetect: "; python3 -c "import scenedetect; print(scenedetect.__version__)" 2>/dev/null || echo "НЕТ"
echo "  dev/debug-утилиты:"
printf "    rg:            "; command -v rg >/dev/null && rg --version 2>/dev/null | head -1 || echo "НЕТ"
printf "    skopeo:        "; command -v skopeo >/dev/null && skopeo --version 2>/dev/null | head -1 || echo "НЕТ"
printf "    strace:        "; command -v strace >/dev/null && strace -V 2>/dev/null | head -1 || echo "НЕТ"
printf "    mediainfo:     "; command -v mediainfo >/dev/null && mediainfo --version 2>/dev/null | head -1 || echo "НЕТ"
printf "    intel_gpu_top: "; command -v intel_gpu_top >/dev/null && echo "установлен" || echo "НЕТ"
printf "    hyperfine:     "; command -v hyperfine >/dev/null && hyperfine --version 2>/dev/null | head -1 || echo "НЕТ"
printf "    xxd:           "; command -v xxd >/dev/null && echo "установлен" || echo "НЕТ"
printf "    7z:            "; command -v 7z >/dev/null && echo "установлен" || echo "НЕТ"
printf "  node/npm:  "; echo "$(node -v 2>/dev/null) / $(npm -v 2>/dev/null)"
for c in claude opencode qwen; do
    printf "  %-9s " "$c:"
    command -v "$c" >/dev/null && ( "$c" --version 2>/dev/null | head -1 || echo "установлен" ) || echo "НЕТ"
done
printf "  GSD-плагин: "; claude plugin list 2>/dev/null | grep -qi gsd && echo "установлен" || echo "не найден"
echo "  медиапапки:"
for d in /data/media /data/downloads; do
    printf "    %-16s " "$d"
    [ -d "$d" ] && echo "смонтирована ($(ls -1 "$d" 2>/dev/null | wc -l) элементов)" || echo "НЕ смонтирована"
done

echo "== post-create завершён =="
