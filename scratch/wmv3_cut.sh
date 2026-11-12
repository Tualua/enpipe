#!/usr/bin/env bash
# Нарезает кусок wmv3 (ASF) без перекодирования для замера краёв чанков --avsw.
#
# Использование:
#   scratch/wmv3_cut.sh ИСТОЧНИК [ДЛИТЕЛЬНОСТЬ_С=100]
#
# Режет с НАЧАЛА файла (ffmpeg -c copy), чтобы первый ключевой кадр имел
# pts 0: иначе production-фолбэк keyframe_table_ffprobe отказывает
# «нет keyframe на кадре 0». Выход пишется в mktemp -d (вне /data), источник
# только читается. Печатает сводку ffprobe и готовую команду прогона теста.
# Ненулевой код, если кусок не годится для замера.
set -u

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "использование: $0 ИСТОЧНИК [ДЛИТЕЛЬНОСТЬ_С=100]" >&2
  exit 2
fi
SRC="$1"
DUR="${2:-100}"
if [ ! -r "$SRC" ]; then
  echo "не читается источник: $SRC" >&2
  exit 2
fi

DIR=$(mktemp -d)
NAME=$(basename "${SRC%.*}")
OUT="$DIR/${NAME}_cut.wmv"

ffmpeg -hide_banner -loglevel error -i "$SRC" -map 0:v:0 -an -sn -t "$DUR" \
  -c copy -f asf "$OUT" || { echo "ffmpeg не смог нарезать кусок" >&2; exit 1; }

probe() { ffprobe -v error "$@" "$OUT"; }

STREAM=$(probe -select_streams v:0 -show_entries \
  stream=codec_name,profile,width,height,avg_frame_rate,r_frame_rate,has_b_frames,start_time,duration \
  -of default=nw=1)
echo "$STREAM"

CODEC=$(echo "$STREAM" | sed -n 's/^codec_name=//p')
BF=$(echo "$STREAM" | sed -n 's/^has_b_frames=//p')
AVG=$(echo "$STREAM" | sed -n 's/^avg_frame_rate=//p')

PKTS=$(probe -select_streams v:0 -show_entries packet=pts_time,dts_time,flags -of csv=p=0)
N_PKT=$(echo "$PKTS" | grep -c .)
N_K=$(echo "$PKTS" | awk -F, '$3 ~ /K/' | grep -c .)
N_REORDER=$(echo "$PKTS" | awk -F, '$1 != $2' | grep -c .)
FIRST_K=$(echo "$PKTS" | awk -F, '$3 ~ /K/ {print $1; exit}')
FIRST_K_DTS=$(echo "$PKTS" | awk -F, '$3 ~ /K/ {print $2; exit}')
N_PTS_NA=$(echo "$PKTS" | awk -F, '$1 == "N/A"' | grep -c .)
echo "пакетов с pts_time=N/A: $N_PTS_NA (в ASF у пакетов часто только dts)"
echo "dts_time первого K-пакета: $FIRST_K_DTS"
echo "пакетов видео: $N_PKT"
echo "пакетов с флагом K: $N_K"
echo "пакетов с pts != dts: $N_REORDER"
echo "pts_time первого K-пакета: $FIRST_K"

FRAMES=$(probe -select_streams v:0 -show_entries frame=pict_type -of csv=p=0)
echo "кадров декода: $(echo "$FRAMES" | grep -c .)"
echo "кадров pict_type I: $(echo "$FRAMES" | grep -c '^I')"

FAIL=0
[ "$CODEC" = "wmv3" ] || { echo "ОШИБКА: кодек $CODEC, нужен wmv3" >&2; FAIL=1; }
[ "${BF:-0}" -gt 0 ] 2>/dev/null || { echo "ОШИБКА: has_b_frames=$BF, нужны B-кадры" >&2; FAIL=1; }
# pts может быть N/A (ASF): тогда ПРЕДУПРЕЖДАЕМ (production-фолбэк по pts в этом
# случае не построит таблицу — это и есть результат замера), а проверку первого
# K-пакета делаем по dts, а не пропускаем молча.
if [ "$N_PTS_NA" -gt 0 ]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: у $N_PTS_NA пакетов pts_time=N/A; keyframe_table_ffprobe их пропускает" >&2
fi
CHECK_T="$FIRST_K"
[ "$CHECK_T" = "N/A" ] && CHECK_T="$FIRST_K_DTS"
case "$CHECK_T" in ''|N/A) echo "ОШИБКА: нет времени первого K-пакета" >&2; FAIL=1; CHECK_T=1;; esac
FIRST_FRAME=$(awk -v t="$CHECK_T" -v f="$AVG" 'BEGIN{split(f,a,"/"); fps=a[1]/(a[2]?a[2]:1); printf "%d", t*fps+0.5}')
[ "$FIRST_FRAME" = "0" ] || { echo "ОШИБКА: первый K-пакет на кадре $FIRST_FRAME, нужен 0" >&2; FAIL=1; }
[ "$N_K" -ge 6 ] || { echo "ОШИБКА: K-пакетов $N_K < 6" >&2; FAIL=1; }
[ "$FAIL" = "0" ] || exit 1

echo
echo "кусок: $OUT"
echo "прогон:"
echo "ENPIPE_TEST_WMV3=\"$OUT\" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k wmv3 -s"
