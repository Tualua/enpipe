"""Keyframe-таблица источника: EBML/Cues-парсер mkv (быстрый путь) и
ffprobe-скан пакетов (медленный fallback), плюс бинарный поиск ближайшего
keyframe и floor-to-ms форматирование seek-времени. Перенесено дословно из
legacy/encode_scenes.py:130-326 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08) и `die()`/`log()` на `enpipe.shared.logging`.

EBML/Cues-парсер (_ebml_num/_eid/_esz, keyframe_table_cues) остаётся здесь
INLINE — вынос в отдельный изолированный EBML-модуль (в подпакете mkv,
файл ebml точка py) сознательно отложен до фазы 2 (D-07, DEBT-01); в этой
фазе меняется только точка вызова subprocess, не структура парсера."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.shared import proc as _proc
from enpipe.shared.logging import die, log


# --- EBML/Matroska: чтение keyframe'ов из Cues-индекса (мс вместо ~90с) --- #
# Matroska хранит Cues — индекс перемотки с таймкодами keyframe'ов видеотрека.
# Прочитать его из хвоста файла (позиция берётся из SeekHead у начала) —
# миллисекунды, вместо полного ffprobe-скана всех пакетов (I/O по всему файлу).

def _ebml_num(b: bytes, p: int, keep_marker: bool) -> Tuple[int, int]:
    first = b[p]
    mask, length = 0x80, 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if keep_marker:
        return int.from_bytes(b[p:p + length], "big"), p + length
    val = first & (mask - 1)
    for i in range(1, length):
        val = (val << 8) | b[p + i]
    return val, p + length


def _eid(b, p):
    return _ebml_num(b, p, True)


def _esz(b, p):
    return _ebml_num(b, p, False)


def keyframe_table_cues(src: Path, fps: float) -> Optional[List[Tuple[int, float]]]:
    """keyframe'ы видеотрека из Cues mkv. None, если Cues/структуры нет —
    тогда вызывающий откатывается на ffprobe-скан."""
    try:
        sz = src.stat().st_size
        with src.open("rb") as f:
            head = f.read(16_000_000)
        idv, p = _eid(head, 0)
        if idv != 0x1A45DFA3:                       # EBML header
            return None
        s, p = _esz(head, p); p += s
        idv, p = _eid(head, p)
        if idv != 0x18538067:                       # Segment
            return None
        _, p = _esz(head, p)
        seg = p

        cues_pos = None
        scale = 1_000_000
        vtrack = None
        q = seg
        while q < len(head) - 8:
            cid, q2 = _eid(head, q)
            csz, q3 = _esz(head, q2)
            if cid == 0x1F43B675:                   # Cluster — Info/Tracks/Cues уже позади
                break
            if cid == 0x114D9B74:                   # SeekHead -> позиция Cues
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    body = head[r:r + esz]; r += esz
                    if eid == 0x4DBB:               # Seek
                        rr, sid, spos = 0, None, None
                        while rr < len(body):
                            bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                            v = body[rr:rr + bsz]; rr += bsz
                            if bid == 0x53AB:
                                sid = int.from_bytes(v, "big")
                            elif bid == 0x53AC:
                                spos = int.from_bytes(v, "big")
                        if sid == 0x1C53BB6B and spos is not None:
                            cues_pos = seg + spos
            elif cid == 0x1549A966:                 # Info -> TimestampScale
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    if eid == 0x2AD7B1:
                        scale = int.from_bytes(head[r:r + esz], "big")
                    r += esz
            elif cid == 0x1654AE6B:                 # Tracks -> номер видеотрека
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    if eid == 0xAE:                 # TrackEntry
                        body = head[r:r + esz]; rr, num, typ = 0, None, None
                        while rr < len(body):
                            bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                            v = body[rr:rr + bsz]; rr += bsz
                            if bid == 0xD7:
                                num = int.from_bytes(v, "big")
                            elif bid == 0x83:
                                typ = int.from_bytes(v, "big")
                        if typ == 1 and vtrack is None:   # 1 = video
                            vtrack = num
                    r += esz
            q = q3 + csz

        if cues_pos is None or vtrack is None or cues_pos >= sz:
            return None

        # читаем ровно тело Cues по его размеру
        with src.open("rb") as f:
            f.seek(cues_pos)
            hdr = f.read(12)
            cid, hp = _eid(hdr, 0)
            if cid != 0x1C53BB6B:
                return None
            csz, hp = _esz(hdr, hp)
            f.seek(cues_pos + hp)
            cb = f.read(csz)

        times: List[float] = []
        p = 0
        while p < len(cb):
            eid, p = _eid(cb, p); esz, p = _esz(cb, p)
            if eid == 0xBB:                         # CuePoint
                body = cb[p:p + esz]; rr, ct, tracks = 0, None, []
                while rr < len(body):
                    bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                    v = body[rr:rr + bsz]; rr += bsz
                    if bid == 0xB3:                 # CueTime
                        ct = int.from_bytes(v, "big")
                    elif bid == 0xB7:               # CueTrackPositions -> CueTrack
                        r2 = 0
                        while r2 < len(v):
                            tid, r2 = _eid(v, r2); tsz, r2 = _esz(v, r2)
                            if tid == 0xF7 and int.from_bytes(v[r2:r2 + tsz], "big") == vtrack:
                                tracks.append(vtrack)
                            r2 += tsz
                if ct is not None and tracks:
                    times.append(ct * scale / 1e9)
            p += esz
    except (IndexError, OSError, ValueError):
        return None

    if not times:
        return None
    table = sorted({(round(t * fps), t) for t in times})
    if table[0][0] != 0:                            # без keyframe на кадре 0 — не рискуем
        return None
    return table


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
