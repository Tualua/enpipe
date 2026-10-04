#!/usr/bin/env bash
# Перекодировка в AV1 (Arc/QSV) + аудио в Opus.
# Пресет: ICQ + qp-max, 10-бит, B-пирамида, tune perceptual,
# сохранение сабов/глав/метаданных/вложений, авто-HDR/DV.
#
# Использование:
#   ./encode_av1_opus.sh <видеофайл | папка> [out_dir] [ICQ]
#
#   первый аргумент — ОДИН видеофайл (mkv/mp4/mov/...) ЛИБО папка с видео (тогда обходит все)
#   out_dir         — куда складывать (по умолч. <папка>/av1 или <dir файла>/av1)
#   ICQ             — значение качества (по умолч. 23; 25 = меньше файл)
#
# Переменные окружения:
#   QPMAX=100        потолок QP (на ICQ25+ это главный рычаг качества; меньше = лучше/больше)
#   DV_PROFILE=10.1  профиль Dolby Vision для AV1-выхода (только если в источнике есть DV)

set -euo pipefail

SRC="${1:?укажи видеофайл или папку с видео}"
QPMAX="${QPMAX:-100}"
DV_PROFILE="${DV_PROFILE:-10.1}"
ICQ="${3:-23}"

# Кодеки, которые Arc/QSV умеет декодировать аппаратно (имена как у ffprobe codec_name).
# Список под Arc A380 (Alchemist): VC-1 у Alchemist убран из HW-декодера, поэтому его тут нет.
# Всё, чего тут нет (vc1, mpeg4/divx, prores, ffv1, theora, ...), сразу идёт на --avsw.
# Переопределяется: HW_CODECS="h264 hevc av1" ./encode_av1_opus.sh ...
HW_CODECS="${HW_CODECS:-h264 hevc vp9 av1 mpeg2video}"

# Копировать ли data-треки в результат (1 = да, как раньше; 0 = отбросить).
# 0 полезно, чтобы не тащить RTP hint-треки (GPAC) и прочий мусор из MP4.
# COPY_DATA=0 ./encode_av1_opus.sh ...
COPY_DATA="${COPY_DATA:-1}"
data_flags=()
[ "$COPY_DATA" = "1" ] && data_flags+=(--data-copy)

# Уровень сжатия FLAC (0-8) для lossless-дорожек. Все уровни без потерь, 8 = минимальный
# размер. FLAC_LEVEL=5 ./encode_av1_opus.sh ...
FLAC_LEVEL="${FLAC_LEVEL:-8}"

# расширения видео, которые обходим в папке (регистр не важен благодаря nocaseglob)
VIDEO_EXTS=(mkv mp4 m4v mov avi ts m2ts webm wmv flv mpg mpeg)

shopt -s nullglob nocaseglob

# --- определяем список входных файлов и каталог вывода ---
if [ -d "$SRC" ]; then
    files=()
    for ext in "${VIDEO_EXTS[@]}"; do
        files+=( "$SRC"/*."$ext" )
    done
    OUT_DIR="${2:-$SRC/av1}"
elif [ -f "$SRC" ]; then
    files=( "$SRC" )
    OUT_DIR="${2:-$(dirname "$SRC")/av1}"
else
    echo "Не найдено: $SRC (нужен видеофайл или папка с видео)" >&2
    exit 1
fi

if [ ${#files[@]} -eq 0 ]; then
    echo "Нет видеофайлов (${VIDEO_EXTS[*]}) в: $SRC" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

# лог неудачных попыток (фолбэк HW->SW и полные провалы). Переопределяется через LOG=...
LOG="${LOG:-$OUT_DIR/encode_errors.log}"

# запись строки в лог с меткой времени
log_fail() {
    printf '%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

# число аудиодорожек в файле (0, если их нет)
count_audio() {
    ffprobe -v error -select_streams a -show_entries stream=index \
        -of csv=p=0 "$1" 2>/dev/null | wc -l
}

# --- кодирование одного файла ---
encode_one() {
    local f="$1"
    local base out
    base="$(basename "$f")"
    base="${base%.*}"                 # отрезаем последнее расширение
    out="$OUT_DIR/${base}.av1.mkv"
    if [ -f "$out" ]; then
        echo ">> SKIP (уже есть): $out"
        return 0
    fi
    echo ">> Кодирую: $base  (ICQ $ICQ, qp-max $QPMAX)"
    echo "OUT: $out"
    # кодек видеодорожки — решаем, пробовать ли аппаратный декодер
    local vcodec
    vcodec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name \
               -of csv=p=0 "$f" 2>/dev/null || true)
    # csv=p=0 добавляет хвостовую запятую, если в файле есть второй видеопоток
    # (обложка attached_pic, напр. mjpeg-cover) -> "hevc," ломает поиск по HW_CODECS.
    # Оставляем только имя кодека до первой запятой и убираем пробелы/переводы строк.
    vcodec="${vcodec%%,*}"; vcodec="${vcodec//[[:space:]]/}"

    # число аудиодорожек в источнике — потом сверим с результатом
    local src_audio
    src_audio=$(count_audio "$f")

    # аудио-план по каждой дорожке: lossless -> FLAC (уровень $FLAC_LEVEL), прочее -> Opus.
    # Дорожка, уже в целевом кодеке, копируется (см. --audio-encode-other-codec-only).
    # Номер дорожки у QSVEncC — 1-based в порядке аудиопотоков (совпадает с ffprobe -select a).
    local audio_flags=() atracks=()
    mapfile -t atracks < <(ffprobe -v error -select_streams a \
        -show_entries stream=codec_name,profile -of csv=p=0 "$f" 2>/dev/null)
    local ai=0 aline acodec aprof
    local lossless_set=" truehd mlp flac alac wavpack tak ape als "
    for aline in "${atracks[@]}"; do
        ai=$((ai + 1))
        acodec="${aline%%,*}"
        aprof="${aline#*,}"
        if [[ "$acodec" == pcm_* ]] || [[ " $lossless_set " == *" $acodec "* ]] \
           || { [ "$acodec" = "dts" ] && [[ "$aprof" == *"DTS-HD MA"* ]]; }; then
            audio_flags+=(--audio-codec "${ai}?flac" --audio-quality "${ai}?${FLAC_LEVEL}")
        else
            audio_flags+=(--audio-codec "${ai}?libopus" --audio-bitrate "${ai}?stereo:128,5.1:256")
        fi
    done

    # авто-определение HDR/DV: копируем метаданные только когда они реально есть
    local hdr_flags=()
    local transfer sidedata
    transfer=$(ffprobe -v error -select_streams v:0 -show_entries stream=color_transfer \
                 -of csv=p=0 "$f" 2>/dev/null || true)
    # тот же артефакт csv=p=0, что и с codec_name: второй видеопоток (обложка) даёт
    # "smpte2084," с хвостовой запятой -> условие HDR10 не срабатывало и
    # --max-cll/--master-display молча не передавались. Чистим до первой запятой.
    transfer="${transfer%%,*}"; transfer="${transfer//[[:space:]]/}"
    sidedata=$(ffprobe -v error -select_streams v:0 -read_intervals "%+#1" -show_frames \
                 -show_entries frame=side_data_list -of default=nw=1 "$f" 2>/dev/null || true)
    if [[ "$transfer" == "smpte2084" || "$transfer" == "arib-std-b67" ]]; then
        hdr_flags+=(--max-cll copy --master-display copy)            # статический HDR10 / HLG
    fi
    if echo "$sidedata" | grep -qiE "2094-40|HDR10\+|HDR Dynamic Metadata"; then
        hdr_flags+=(--dhdr10-info copy)   # HDR10+ динамика. ВНИМАНИЕ: на Arc/Linux бывает зависание (issue #216)
    fi
    if echo "$sidedata" | grep -qiE "DOVI|Dolby Vision"; then
        hdr_flags+=(--dolby-vision-rpu copy --dolby-vision-profile "$DV_PROFILE")
    fi
    [ ${#hdr_flags[@]} -gt 0 ] && echo ">>   HDR/DV: ${hdr_flags[*]}"

    # запускает qsvencc с заданным режимом декодера ($1 = --avhw | --avsw)
    run_qsvencc() {
        local decode="$1"; shift
        qsvencc "$decode" --va -i "$f" -c av1 \
            --icq "$ICQ" --qp-max "$QPMAX" \
	    --extbrc --adapt-ref --adapt-ltr \
            -u best --output-depth 10 --profile main \
            --gop-len 300 --gop-ref-dist 6 --b-pyramid --i-adapt --b-adapt \
            --tile-col 1 --tile-row 1 \
            --tune perceptual --scenario-info archive \
            --colorrange auto --colormatrix auto --colorprim auto --transfer auto --chromaloc auto \
            "${audio_flags[@]}" --audio-encode-other-codec-only \
            --sub-copy --chapter-copy --attachment-copy "${data_flags[@]}" \
            --audio-disposition copy --sub-disposition copy \
            --audio-metadata copy --sub-metadata copy --video-metadata copy --metadata copy \
            --psnr --ssim \
            "${hdr_flags[@]}" \
            -o "$out"
    }

    # выбор декодера по кодеку: HW-поддерживаемые пробуем аппаратно (с фолбэком),
    # остальные сразу декодируем софтварно. ok=0 — успех.
    local ok=1
    if [[ -n "$vcodec" && " $HW_CODECS " == *" $vcodec "* ]]; then
        echo ">>   Кодек '$vcodec' поддерживается HW — пробую --avhw"
        # 1) аппаратное декодирование; 2) при провале — софтварное (--avsw)
        if run_qsvencc --avhw; then
            ok=0
        else
            log_fail "HW-декод не удался (codec=$vcodec), фолбэк на --avsw: $f"
            echo ">>   HW-декодер не справился — повтор на софтварном (--avsw)"
            rm -f "$out"                   # чистим возможный битый/частичный вывод
            if run_qsvencc --avsw; then ok=0; fi
        fi
    else
        echo ">>   Кодек '${vcodec:-неизвестен}' не в списке HW — сразу --avsw"
        if run_qsvencc --avsw; then ok=0; fi
    fi

    # полный провал: не удалось закодировать даже софтварно
    if [ "$ok" -ne 0 ]; then
        log_fail "ПРОВАЛ кодирования (codec=${vcodec:-?}): $f"
        echo ">>   ОШИБКА: не удалось закодировать '$base' — см. лог: $LOG" >&2
        rm -f "$out"                       # убираем битый/частичный вывод
        return 1
    fi

    # сверка аудиодорожек: экзотический аудиокодек мог не перекодироваться/выпасть
    local out_audio
    out_audio=$(count_audio "$out")
    if [ "$out_audio" -ne "$src_audio" ]; then
        log_fail "Число аудиодорожек изменилось ($src_audio -> $out_audio), возможно экзотический аудиокодек: $f"
        echo ">>   ОШИБКА: аудиодорожек было $src_audio, стало $out_audio — удаляю '$base', см. лог: $LOG" >&2
        rm -f "$out"
        return 1
    fi

    local insz outsz insz_b outsz_b
    insz_b=$(stat -c %s "$f")
    outsz_b=$(stat -c %s "$out")
    insz=$(du -h "$f"   | cut -f1)
    outsz=$(du -h "$out" | cut -f1)
    echo ">>   $base: $insz -> $outsz"

    # результат должен быть меньше источника; иначе смысла в перекодировании нет
    if [ "$outsz_b" -ge "$insz_b" ]; then
        log_fail "Результат не меньше источника (${insz_b} -> ${outsz_b} байт): $out"
        echo ">>   ВНИМАНИЕ: результат ($outsz) не меньше источника ($insz) — записано в лог: $LOG" >&2
    fi
}

failed=0
for f in "${files[@]}"; do
    # провал одного файла не должен прерывать весь пакет
    encode_one "$f" || failed=$((failed + 1))
done

echo ">> Готово. Результаты в: $OUT_DIR"
if [ "$failed" -gt 0 ]; then
    echo ">> Неудачных файлов: $failed — подробности в логе: $LOG" >&2
    exit 1
fi

