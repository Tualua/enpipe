#!/usr/bin/env bash
# UAT D-10 фазы 10.1: сквозной `enpipe run` на источнике VC-1 по пути --avsw
# с самопроверкой всех ожиданий.
#
# Использование:
#   bash scratch/uat_d10_run.sh <источник> <существующая папка вывода>
#
# Правило: выход пишется только в указанную папку, и она не может лежать
# под /data (используйте `mktemp -d`). Скрипт ничего не удаляет.
#
# Проверки копятся (нет `set -e`): каждая печатает `[uat] ok: …` или
# `[uat] FAIL: …`, в конце — `[uat] ИТОГ: OK` (rc 0) или `[uat] ИТОГ: FAIL`
# (rc 1). Отказ по аргументам — rc 2, до любой записи.
set -u

if [ $# -ne 2 ]; then
  echo "использование: bash $0 <источник> <существующая папка вывода>" >&2
  exit 2
fi

SRC="$1"
if [ ! -f "$SRC" ]; then
  echo "[uat] отказ: источник не найден: $SRC" >&2
  exit 2
fi
SRC=$(realpath "$SRC")

if [ ! -d "$2" ]; then
  echo "[uat] отказ: папки вывода нет: $2" >&2
  exit 2
fi
OUTD=$(realpath "$2")
case "$OUTD" in
  /data|/data/*)
    echo "[uat] отказ: папка вывода под /data запрещена: $OUTD (возьмите mktemp -d)" >&2
    exit 2
    ;;
esac

BASE=$(basename "$SRC")
STEM="${BASE%.*}"
EXT="${BASE##*.}"
OUT="$OUTD/$STEM.Encoded.$EXT"
SCENES="$OUTD/$STEM.scenes"
LOG="$OUTD/$STEM.log"

if [ -e "$OUT" ]; then
  echo "[uat] отказ: выходной файл уже есть: $OUT" >&2
  exit 2
fi

REPO=$(realpath "$(dirname "$0")/..")
FAILS=0
ok()   { echo "[uat] ok: $*"; }
fail() { echo "[uat] FAIL: $*"; FAILS=$((FAILS + 1)); }

# --- прогон ---------------------------------------------------------------
cd "$REPO" || { echo "[uat] отказ: нет каталога репозитория $REPO" >&2; exit 2; }
uv run enpipe run "$SRC" --out-dir "$OUTD" --scenes "$SCENES" 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}

# --- проверки -------------------------------------------------------------
if [ "$RC" -eq 0 ]; then ok "код возврата enpipe run = 0"; else fail "код возврата enpipe run = $RC"; fi

DECODE_LINE=$(grep -m1 "декод:" "$LOG")
echo "[uat] строка декода: ${DECODE_LINE:-<нет>}"
case "$DECODE_LINE" in
  *"декод: sw"*) ok "декод: sw" ;;
  *) fail "в первой строке «декод:» нет «декод: sw»" ;;
esac

KF_LINE=$(grep -m1 "ключевые кадры по выводу декодера" "$LOG")
if [ -n "$KF_LINE" ]; then
  ok "есть строка перенумерации ключевых кадров"
  echo "[uat] $KF_LINE"
  echo "[uat] шаг перенумерации: $(grep -m1 "✔ номера ключевых кадров" "$LOG")"
else
  fail "нет строки «ключевые кадры по выводу декодера»"
fi

ERRS=$(grep -c "ОШИБКА" "$LOG")
if [ "$ERRS" -eq 0 ]; then ok "строк с ОШИБКА: 0"; else fail "строк с ОШИБКА: $ERRS"; fi
if grep -q "encode_scenes:" "$LOG"; then
  fail "в логе есть строка die(): $(grep -m1 "encode_scenes:" "$LOG")"
else
  ok "строк die() (encode_scenes:) нет"
fi

N=$(sed -n 's/.*склейка: \([0-9][0-9]*\) кадров (совпало с суммой сцен).*/\1/p' "$LOG" | tail -1)
if [ -n "$N" ]; then ok "склейка: $N кадров (совпало с суммой сцен)"; else fail "нет строки «склейка: N кадров (совпало с суммой сцен)»"; fi

LAST_END=""
if [ -f "$SCENES" ]; then
  # формат: `scene    0  frames [       0,       84)  T0 .. T1` (с выравниванием пробелами)
  LAST_END=$(sed -n 's/^scene *[0-9][0-9]* *frames \[ *[0-9][0-9]*, *\([0-9][0-9]*\)).*/\1/p' "$SCENES" | tail -1)
fi
if [ -z "$LAST_END" ]; then
  fail "не удалось прочитать конец последней сцены из $SCENES"
elif [ "$N" = "$LAST_END" ]; then
  ok "N = конец последней сцены ($LAST_END)"
else
  fail "N=${N:-<нет>}, конец последней сцены $LAST_END"
fi

PACKETS=""
if [ -f "$OUT" ]; then
  PACKETS=$(ffprobe -v error -select_streams v:0 -count_packets \
              -show_entries stream=nb_read_packets -of csv=p=0 "$OUT")
fi
if [ -n "$N" ] && [ "$PACKETS" = "$N" ]; then
  ok "видеопакетов в выходном mkv: $PACKETS = N"
else
  fail "видеопакетов в выходном mkv: ${PACKETS:-<нет файла>}, ожидалось ${N:-N}"
fi

# --- справочно, без вердикта ---------------------------------------------
if [ -f "$OUT" ]; then
  echo "[uat] длительность, с: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")"
  echo "[uat] mkvmerge --identify:"
  mkvmerge --identify "$OUT"
fi

# --- итог -----------------------------------------------------------------
if [ "$FAILS" -eq 0 ]; then
  echo "[uat] ИТОГ: OK"
  RESULT=0
else
  echo "[uat] ИТОГ: FAIL ($FAILS проверок)"
  RESULT=1
fi
echo "[uat] лог: $LOG"
echo "[uat] выход: $OUT"
exit "$RESULT"
