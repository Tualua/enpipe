#!/usr/bin/env bash
# Финальная настройка devcontainer'а: права на GPU, npm-агенты (opencode/qwen),
# Python-зависимости проекта, самопроверка окружения. Идемпотентно.
set -euo pipefail

echo "==================================================================="
echo "== post-create: GPU / npm-агенты / python-deps / проверки =="
echo "==================================================================="

# --- 1) Доступ к Intel Arc: добавить пользователя в группу render-узла ---
# GID группы, владеющей /dev/dri/renderD128, зависит от хоста -> определяем на лету.
echo "-- GPU: /dev/dri --"
if [ -e /dev/dri/renderD128 ]; then
    RGID="$(stat -c '%g' /dev/dri/renderD128)"
    if ! getent group "$RGID" >/dev/null 2>&1; then
        sudo groupadd -g "$RGID" render-host || true
    fi
    sudo usermod -aG "$RGID" "$(id -un)" || true
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
printf "  qsvencc:   "; command -v qsvencc >/dev/null && qsvencc --version 2>/dev/null | head -1 || echo "НЕТ"
printf "  dovi_tool: "; command -v dovi_tool >/dev/null && dovi_tool --version 2>/dev/null || echo "НЕТ"
printf "  mkvmerge:  "; command -v mkvmerge >/dev/null && mkvmerge --version 2>/dev/null | head -1 || echo "НЕТ"
printf "  tmux:      "; command -v tmux >/dev/null && tmux -V || echo "НЕТ"
printf "  scenedetect: "; python3 -c "import scenedetect; print(scenedetect.__version__)" 2>/dev/null || echo "НЕТ"
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
