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

# --- 2) AI-CLI через npm (все три одной командой) ---
# Claude Code ставится ЗДЕСЬ, а не devcontainer-фичей
# `ghcr.io/anthropics/devcontainer-features/claude-code`. Фича делала ровно то же
# (npm-пакет @anthropic-ai/claude-code в nvm-префикс), но тянула лишний pin в
# devcontainer-lock.json и завязывала сборку на доступность ghcr. Версии не
# пинятся сознательно — как и у opencode/qwen; нужен pin, пиши `@<version>`.
echo "-- npm: claude-code + opencode + qwen-code --"
npm install -g @anthropic-ai/claude-code opencode-ai @qwen-code/qwen-code

# --- 2a) Персистентность авторизаций AI-CLI между ребилдами ---
# Креды лежат на named volume'ах (см. mounts в devcontainer.json), поэтому сами
# по себе ребилд переживают. Здесь остаётся ОДНА вещь, которую томом не решить:
# claude хранит часть состояния в ОТДЕЛЬНОМ файле ~/.claude.json, а том
# монтируется только на каталог. Решение — CLAUDE_CONFIG_DIR (задан в
# containerEnv), который переносит .claude.json ВНУТРЬ каталога-тома.
# Symlink тут не годится: claude пишет конфиг через temp+rename(), а rename
# заменил бы симлинк обычным файлом — персистентность сломалась бы молча.
#
# Ниже — разовая миграция старого $HOME/.claude.json на новое место. Она
# идемпотентна и НИКОГДА не перезаписывает уже персистентный конфиг: если
# приёмник есть, исходник оставляется на месте с предупреждением (затереть
# рабочую авторизацию хуже, чем оставить мусорный файл).
echo "-- персистентность авторизаций: claude/.claude.json --"
CC_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
if [ "$(readlink -f "$CC_DIR" 2>/dev/null)" = "$(readlink -f "$HOME" 2>/dev/null)" ]; then
    # CLAUDE_CONFIG_DIR указывает на сам $HOME -> .claude.json и так на старом
    # месте, миграция не нужна и не имеет смысла.
    echo "   CLAUDE_CONFIG_DIR == \$HOME — миграция не требуется"
elif [ -f "$HOME/.claude.json" ]; then
    mkdir -p "$CC_DIR"
    if [ -e "$CC_DIR/.claude.json" ]; then
        echo "   ВНИМАНИЕ: $CC_DIR/.claude.json уже существует — $HOME/.claude.json"
        echo "            НЕ перенесён (не затираем рабочую авторизацию). Лишний файл"
        echo "            можно удалить вручную, если он устарел."
    else
        mv "$HOME/.claude.json" "$CC_DIR/.claude.json"
        echo "   перенесён: \$HOME/.claude.json -> $CC_DIR/.claude.json"
    fi
else
    echo "   нечего переносить (\$HOME/.claude.json отсутствует)"
fi

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
# ENV-01: основной ffmpeg/ffprobe — BtbN static n9.0.2 (/opt/ffmpeg-9/bin,
# симлинки в /usr/local/bin затеняют ffmpeg 6.1.1 из dlstreamer-базы). Это
# load-bearing предпосылка: DV-проверки AV1 (dovi_rpu для av1) и COR-01 (ffmpeg
# av1_qsv — иммунный к межпроцессной порче кадров путь энкода), поэтому проверка
# ниже ТРЕКАЕТ pass/fail через ENV01_OK, а не просто печатает grep — сломанная
# пересборка не должна молча выглядеть как успех. Сам скрипт остаётся best-effort
# под set -euo pipefail: ни одна ОШИБКА здесь не делает mid-script `exit 1` —
# итог печатается одной сводной строкой в конце скрипта.
echo "  ffmpeg (основной, BtbN static n9.0.2):"
ENV01_OK=1
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    for _env01_bin in ffmpeg ffprobe; do
        case "$(readlink -f "$(command -v "$_env01_bin")")" in
            /opt/ffmpeg-9/bin/*) ;;
            *) echo "    ОШИБКА: $_env01_bin на PATH не из /opt/ffmpeg-9/bin (затенён другим ffmpeg?)"; ENV01_OK=0 ;;
        esac
    done
    _env01_ver=$(ffmpeg -hide_banner -version 2>/dev/null | head -1 || true)
    echo "    ${_env01_ver:-версию получить не удалось}"
    if ! grep -qF 'n9.0.2' <<<"$_env01_ver"; then
        echo "    ОШИБКА: версия ffmpeg не n9.0.2"; ENV01_OK=0
    fi
    # Вывод -encoders/-bsfs/-h захватываем СНАЧАЛА в переменную, потом grep по
    # here-string. Прямое `ffmpeg ... | grep -qi` под `set -o pipefail` даёт
    # ГОНКУ: grep -q закрывает читающий конец пайпа на первом совпадении, ffmpeg
    # (ещё пишущий остаток -encoders) ловит SIGPIPE→141, pipefail роняет пайплайн,
    # и `if !` печатает ЛОЖНЫЙ «не найден» на КОРРЕКТНОМ образе. Command
    # substitution дожидается полного вывода ffmpeg — гонки нет.
    _env01_enc=$(ffmpeg -hide_banner -encoders 2>/dev/null || true)
    _env01_bsfs=$(ffmpeg -hide_banner -bsfs 2>/dev/null || true)
    _env01_dovi=$(ffmpeg -hide_banner -h bsf=dovi_rpu 2>&1 || true)
    if ! grep -qi 'av1_qsv' <<<"$_env01_enc"; then
        echo "    ОШИБКА: av1_qsv кодер не найден"; ENV01_OK=0
    fi
    if ! grep -qi 'libopus' <<<"$_env01_enc"; then
        echo "    ОШИБКА: libopus кодер не найден"; ENV01_OK=0
    fi
    if ! grep -qi 'av1_metadata' <<<"$_env01_bsfs"; then
        echo "    ОШИБКА: av1_metadata BSF не найден"; ENV01_OK=0
    fi
    if ! grep -qi 'dovi_rpu' <<<"$_env01_bsfs"; then
        echo "    ОШИБКА: dovi_rpu BSF не найден"; ENV01_OK=0
    fi
    if ! grep -qi 'av1' <<<"$_env01_dovi"; then
        echo "    ОШИБКА: dovi_rpu не перечисляет av1 среди кодеков"; ENV01_OK=0
    fi
else
    echo "    ОШИБКА: ffmpeg/ffprobe не найдены на PATH (пересобери образ)"; ENV01_OK=0
fi
# QSV-01: порог 4665 совпадает с рантайм-гейтом enpipe.shared.qsvencc_version.
# QSVENCC_MIN_REV (синхронность проверяет tests/unit/shared/
# test_qsvencc_threshold_sync.py). Это ранний сигнал при создании контейнера,
# реальное принуждение — рантайм-гейт (QSV-02); аварийный выход не используем — стиль
# скрипта (ENV-01): флаг + громкая сводка.
QSV01_OK=1
if command -v qsvencc >/dev/null 2>&1; then
    _qsv_ver="$(qsvencc --version 2>/dev/null || true)"
    printf "  qsvencc:   %s\n" "$(printf '%s\n' "$_qsv_ver" | sed -n 1p)"
    _qsv_rev="$(printf '%s\n' "$_qsv_ver" | sed -n '1s/.*(r\([0-9]*\)).*/\1/p')"
    if [ -z "$_qsv_rev" ] || [ "$_qsv_rev" -lt 4665 ]; then
        echo "    ОШИБКА: qsvencc r${_qsv_rev:-?} старше r4665 (нет фикса 45003f1, исправления --seek из 8.32-vppsync6 и/или исправления open-GOP --trim из 8.32-vppsync7 — тихая порча/сдвиг содержимого чанков); пересобери образ"; QSV01_OK=0
    fi
else
    echo "    ОШИБКА: qsvencc не найден на PATH"; QSV01_OK=0
    echo "  qsvencc:   НЕТ"
fi
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
# Персистентность авторизаций: проверяем ДВЕ независимые вещи по каждому пути.
#   mount — реально ли путь отдельная точка монтирования. Если нет, значит том из
#           devcontainer.json не подхватился (контейнер ещё не пересобран после
#           правки mounts) и креды СНОВА потеряются при следующем ребилде. Это
#           молчаливый отказ, который без проверки заметен только по повторному
#           запросу /login — поэтому он трекается флагом, а не просто печатается.
#   cred  — лежит ли на этом пути сам файл креда. Его отсутствие НЕ ошибка
#           (свежий том = просто ещё не логинились), отсюда "нет (нужен логин)".
# Как и ENV-01 выше, блок best-effort: не делает mid-script exit, итог — одной
# сводной строкой в конце скрипта.
echo "  персистентность авторизаций (named volumes):"
PERSIST_OK=1
_check_persist() {
    local path="$1" cred="$2" label="$3"
    printf "    %-26s " "$label"
    if findmnt -no TARGET "$path" >/dev/null 2>&1; then
        printf "том: OK   "
    else
        printf "том: НЕТ  "; PERSIST_OK=0
    fi
    if [ -f "$cred" ]; then
        echo "креды: есть"
    else
        echo "креды: нет (нужен логин)"
    fi
}
_check_persist "$CC_DIR"                     "$CC_DIR/.credentials.json"              "claude ($CC_DIR)"
_check_persist "$HOME/.qwen"                 "$HOME/.qwen/settings.json"              "qwen (~/.qwen)"
_check_persist "$HOME/.local/share/opencode" "$HOME/.local/share/opencode/auth.json"  "opencode (share)"
_check_persist "$HOME/.config/opencode"      "$HOME/.config/opencode/opencode.jsonc"  "opencode (config)"
# .claude.json должен лежать ВНУТРИ тома; файл в $HOME означает, что
# CLAUDE_CONFIG_DIR не применился и этот конфиг ребилд не переживёт.
if [ -f "$HOME/.claude.json" ] && [ "$CC_DIR" != "$HOME" ]; then
    echo "    ВНИМАНИЕ: $HOME/.claude.json вне тома (CLAUDE_CONFIG_DIR не применился?)"
    PERSIST_OK=0
fi
# Хостовый podman через проброшенный сокет (devcontainer.json: mounts +
# CONTAINER_HOST). Best-effort: недоступность не роняет скрипт, только печатает
# причину — обычно на хосте не включён `systemctl --user enable --now podman.socket`.
printf "  podman (хост, remote): "
if ! command -v podman-remote >/dev/null 2>&1; then
    echo "НЕТ podman-remote (пересобери образ)"
elif [ ! -S /run/podman/podman.sock ]; then
    echo "НЕТ сокета /run/podman/podman.sock (на хосте: systemctl --user enable --now podman.socket)"
elif _pr_ver=$(podman-remote version --format '{{.Server.Version}}' 2>&1); then
    echo "OK, сервер $_pr_ver, клиент $(podman-remote --version | awk '{print $NF}')"
else
    echo "ОШИБКА подключения: $(printf '%s' "$_pr_ver" | tail -1)"
fi
echo "  медиапапки:"
for d in /data/media /data/downloads; do
    printf "    %-16s " "$d"
    [ -d "$d" ] && echo "смонтирована ($(ls -1 "$d" 2>/dev/null | wc -l) элементов)" || echo "НЕ смонтирована"
done

# ENV-01 сводка: единая pass/fail строка по флагу ENV01_OK, накопленному в
# блоке ffmpeg выше. Не роняет скрипт — только сигнализирует состояние.
if [ "${ENV01_OK:-0}" -eq 1 ]; then
    echo "ENV-01 (ffmpeg n9.0.2 primary + ffprobe + av1_qsv/libopus + av1_metadata/dovi_rpu(av1)): OK"
else
    echo "ENV-01 (ffmpeg n9.0.2 primary + ffprobe + av1_qsv/libopus + av1_metadata/dovi_rpu(av1)): ПРОВАЛЕН — см. ОШИБКА выше"
fi

# QSV-01 сводка по флагу QSV01_OK (см. блок qsvencc выше).
if [ "${QSV01_OK:-0}" -eq 1 ]; then
    echo "QSV-01 (qsvencc >= r4665 / 45003f1 + --seek + open-GOP --trim): OK"
else
    echo "QSV-01 (qsvencc >= r4665 / 45003f1 + --seek + open-GOP --trim): ПРОВАЛЕН — см. ОШИБКА выше"
fi

# Сводка персистентности по флагу PERSIST_OK (см. блок проверок выше).
if [ "${PERSIST_OK:-0}" -eq 1 ]; then
    echo "ПЕРСИСТЕНТНОСТЬ авторизаций (claude/opencode/qwen на named volumes): OK"
else
    echo "ПЕРСИСТЕНТНОСТЬ авторизаций (claude/opencode/qwen на named volumes): ПРОВАЛЕНА"
    echo "   -> тома из .devcontainer/devcontainer.json не подхвачены: пересобери"
    echo "      контейнер (Dev Containers: Rebuild Container). Иначе авторизации"
    echo "      снова потеряются при следующем ребилде."
fi

echo "== post-create завершён =="
