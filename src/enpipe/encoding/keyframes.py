"""Keyframe-таблица источника: EBML/Cues-парсер mkv (быстрый путь) и
ffprobe-скан пакетов (медленный fallback), плюс бинарный поиск ближайшего
keyframe и floor-to-ms форматирование seek-времени. Перенесено дословно из
legacy/encode_scenes.py:130-326 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08) и `die()`/`log()` на `enpipe.shared.logging`.

EBML/Cues-парсер вынесен в изолированный, чистый (без I/O) модуль
enpipe.mkv.ebml (D-01/D-02, фаза 2, DEBT-01): keyframe_table_cues здесь —
тонкая I/O-обёртка (stat/open/seek/read), которая вызывает ebml.
find_cues_position/peek_element_header/parse_cues_body для самого байтового
разбора."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

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
