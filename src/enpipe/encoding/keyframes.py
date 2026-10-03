"""Keyframe-таблица источника: EBML/Cues-парсер mkv (быстрый путь) и
ffprobe-скан пакетов (медленный fallback), плюс бинарный поиск ближайшего
keyframe и floor-to-ms форматирование seek-времени. Перенесено дословно из
legacy/encode_scenes.py:130-326 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08) и `die()`/`log()` на `enpipe.shared.logging`.

EBML/Cues-парсер вынесен в изолированный, чистый (без I/O) модуль
enpipe.mkv.ebml (D-01/D-02, фаза 2, DEBT-01): keyframe_table_cues здесь —
тонкая I/O-обёртка (stat/open/seek/read), которая вызывает ebml.
find_cues_position/peek_element_header/parse_cues_body для самого байтового
разбора.

Защита от open-GOP. qsvencc (r4658, r4663 vppsync6 и апстрим) считает пакеты с
pts раньше keyframe (ведущие кадры CRA/RASL, идут после keyframe в порядке
декодирования) в m_trimParam.offset и сдвигает --trim на −N кадров: число кадров
в чанке сходится, а содержимое тихо смещено (см.
.planning/debug/HANDOFF-qsvencc-opengop-trim-offset.md). Поэтому
probe_leading_frames проверяет только keyframe'ы, реально используемые как
seek-точки чанков (стоимость пропорциональна числу чанков, а не размеру файла —
полный скан 60 ГБ на HDD-ZFS ровно то, чего избегает Cues): один ffprobe с
пачкой -read_intervals. Старт интервала = время keyframe + пол-кадра: и mkv, и
mp4 откатываются назад к keyframe <= цели, поэтому K+0.5 кадра попадает точно на
K; floor_ms(K) в mkv попадал на ПРЕДЫДУЩИЙ keyframe, а MPEG-TS ненадёжен вовсе —
для него (и любого промаха) есть откат на полный скан пакетов."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from enpipe.mkv import ebml as _ebml
from enpipe.shared import proc as _proc
from enpipe.shared.logging import die, log


def keyframe_table_cues(src: Path, fps: float) -> Optional[List[Tuple[int, float]]]:
    """keyframe'ы видеотрека из Cues mkv. None, если Cues/структуры нет —
    тогда вызывающий откатывается на ffprobe-скан."""
    try:
        sz = src.stat().st_size
        with src.open("rb") as f:
            head = f.read(16_000_000)
        located = _ebml.find_cues_position(head, sz)
        if located is None:
            return None
        cues_pos, scale, vtrack = located

        # читаем ровно тело Cues по его размеру
        with src.open("rb") as f:
            f.seek(cues_pos)
            hdr = f.read(12)
            cid, csz, hlen = _ebml.peek_element_header(hdr, 0)
            if cid != 0x1C53BB6B:
                return None
            f.seek(cues_pos + hlen)
            cb = f.read(csz)
    except (IndexError, OSError, ValueError):
        return None

    return _ebml.parse_cues_body(cb, vtrack, scale, fps)


def keyframe_table_ffprobe(src: Path, fps: float) -> List[Tuple[int, float]]:
    """Фолбэк: отсортированный список (frame, pts_time) keyframe'ов через полный
    проход ffprobe по пакетам (без декода). Медленно (I/O по всему файлу)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_packets", "-show_entries", "packet=flags,pts_time",
           "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (keyframes) упал: {proc.stderr.strip()}")
    table: List[Tuple[int, float]] = []
    for line in proc.stdout.splitlines():
        # формат: "<pts_time>,<flags>", напр. "627.544000,K__"
        parts = line.split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        table.append((round(t * fps), t))
    table.sort()
    if not table or table[0][0] != 0:
        die("у источника нет keyframe на кадре 0 — неожиданно, прерываю")
    return table


def keyframe_table(src: Path, fps: float) -> List[Tuple[int, float]]:
    """keyframe-таблица источника: сперва мгновенное чтение Cues-индекса mkv,
    иначе — полный ffprobe-скан пакетов."""
    if src.suffix.lower() in (".mkv", ".mka", ".webm"):
        table = keyframe_table_cues(src, fps)
        if table is not None:
            log(">> keyframe'ы прочитаны из Cues-индекса mkv (быстро)")
            return table
        log(">> Cues в mkv нет/непарсимы — полный ffprobe-скан (медленно)")
    return keyframe_table_ffprobe(src, fps)


# HEVC требует, чтобы все ведущие кадры IRAP шли в порядке декодирования сразу
# после него, до trailing-кадров; число B-кадров x265 <= 16, значит ведущих не
# больше 16. 24 пакета (keyframe + 23 следующих) дают точное N в сообщении.
LEADING_PROBE_PACKETS = 24


def count_leading_after_keyframes(
    lines: List[str], wanted_frames: Set[int], fps: float
) -> Dict[int, int]:
    """По строкам ffprobe csv "<pts_time>,<flags>" считает для каждого нужного
    keyframe число ведущих пакетов (pts < pts keyframe, идут после него в порядке
    декодирования). Чистая функция. Keyframe вне wanted_frames сбрасывает
    отслеживание; повторно встреченный keyframe (перекрытие интервалов) даёт
    максимум из вхождений; отсутствующий keyframe в результат не попадает."""
    result: Dict[int, int] = {}
    cur_frame: Optional[int] = None
    cur_pts = 0.0
    cur_n = 0
    for line in lines:
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue  # "N/A" и мусор
        if "K" in parts[1]:
            frame = round(t * fps)
            if frame in wanted_frames:
                cur_frame, cur_pts, cur_n = frame, t, 0
                result[frame] = max(result.get(frame, 0), 0)
            else:
                cur_frame = None
        elif cur_frame is not None and t < cur_pts - 1e-6:
            cur_n += 1
            result[cur_frame] = max(result.get(cur_frame, 0), cur_n)
    return result


def _ffprobe_packet_lines(src: Path, read_intervals: Optional[str]) -> List[str]:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if read_intervals is not None:
        cmd += ["-read_intervals", read_intervals]
    cmd += ["-show_packets", "-show_entries", "packet=pts_time,flags",
            "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (ведущие кадры) упал: {proc.stderr.strip()}")
    return proc.stdout.splitlines()


def probe_leading_frames(
    src: Path, fps: float, keyframes: List[Tuple[int, float]]
) -> Dict[int, int]:
    """{frame: N} — число ведущих кадров после каждого из keyframes. Один
    ffprobe с пачкой интервалов; если какой-то keyframe не найден — полный скан
    пакетов; если и он не найден — die (fail closed, чтобы не испортить чанки
    тихо)."""
    uniq = sorted(set(keyframes), key=lambda kt: (kt[1], kt[0]))
    wanted = {f for f, _ in uniq}
    intervals = ",".join(
        f"{t + 0.5 / fps:.6f}%+#{LEADING_PROBE_PACKETS}" for _, t in uniq
    )
    res = count_leading_after_keyframes(
        _ffprobe_packet_lines(src, intervals), wanted, fps)
    if not wanted <= set(res):
        log(">> ведущие кадры: часть keyframe'ов не найдена выборочным ffprobe — "
            "полный скан пакетов (медленно)")
        res = count_leading_after_keyframes(
            _ffprobe_packet_lines(src, None), wanted, fps)
    missing = sorted(wanted - set(res))
    if missing:
        shown = ", ".join(str(f) for f in missing[:10])
        die(f"не удалось проверить ведущие кадры после keyframe {shown} — "
            f"отказ, чтобы не испортить чанки тихо")
    return {f: res[f] for f in wanted}


def kf_before(table: List[Tuple[int, float]], frame: int) -> Tuple[int, float]:
    """Последний keyframe с frame ≤ target (бинарный поиск)."""
    lo, hi, best = 0, len(table) - 1, table[0]
    while lo <= hi:
        mid = (lo + hi) // 2
        if table[mid][0] <= frame:
            best = table[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def fmt_seek(t: float) -> str:
    """Секунды -> HH:MM:SS.mmm, ОКРУГЛЯЯ ВНИЗ до мс.

    floor гарантирует seek_time ≤ времени keyframe, поэтому seek (который
    приземляется на первый keyframe ≥ времени seek) попадёт именно на него.
    """
    ms = int(t * 1000)  # floor
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def compute_chunk_seek_trim(table: List[Tuple[int, float]], s: int, e: int) -> Tuple[str, str]:
    """seek/trim-строки для сцены [s, e) по keyframe-таблице источника.
    Вынесено дословно из pipeline.py:108-110 (D-04, фаза 2, DEBT-02) — без
    изменения логики. K = последний keyframe источника с frame_K <= S;
    qsvencc --seek floor_ms(K) --trim (S-K):(E-1-K)."""
    kf_frame, kf_time = kf_before(table, s)
    seek = fmt_seek(kf_time)
    trim = f"{s - kf_frame}:{e - 1 - kf_frame}"
    return seek, trim
