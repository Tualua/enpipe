"""EBML/Matroska: чтение keyframe'ов из Cues-индекса — чистое, без I/O.

Изолировано из enpipe.encoding.keyframes (D-01/DEBT-01, фаза 2). Здесь живёт
ТОЛЬКО байтовый разбор: варинты EBML, обход SeekHead/Info/Tracks для поиска
позиции Cues, обход тела Cues для построения таблицы keyframe'ов. Никаких
файловых или внешне-процессных вызовов — это то, что делает модуль
тестируемым байтовыми фикстурами в полной изоляции (без реального видео
на диске).

Чтение самих байт с диска остаётся тонкой I/O-обёрткой в
enpipe.encoding.keyframes.keyframe_table_cues, которая вызывает функции
этого модуля."""

from __future__ import annotations

from typing import List, Optional, Tuple


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


def peek_element_header(buf: bytes, pos: int) -> Tuple[int, int, int]:
    """Читает id+size одного EBML-элемента в pos, БЕЗ чтения его тела.
    Возвращает (elem_id, size, header_len) — header_len говорит вызывающей
    I/O-обёртке, сколько байт заняли id+size, т.е. где начинается тело."""
    eid, p1 = _eid(buf, pos)
    esz, p2 = _esz(buf, p1)
    return eid, esz, p2 - pos


def find_cues_position(head: bytes, total_size: int) -> Optional[Tuple[int, int, int]]:
    """Обходит EBML-заголовок + Segment + SeekHead/Info/Tracks в поисках
    Cues. Возвращает (cues_pos, timestamp_scale, video_track_number) или
    None при ЛЮБОЙ структурной аномалии (никогда не бросает исключение) --
    total_size — реальный размер файла на диске, используется чтобы отвергнуть
    указатель SeekHead за пределами EOF (обрезанный файл)."""
    try:
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
                        if typ == 1 and vtrack is None:   # 1 = видео
                            vtrack = num
                    r += esz
            q = q3 + csz

        if cues_pos is None or vtrack is None or cues_pos >= total_size:
            return None
        return cues_pos, scale, vtrack
    except (IndexError, ValueError):
        return None


def parse_cues_body(cues_body: bytes, video_track: int, scale: int,
                     fps: float) -> Optional[List[Tuple[int, float]]]:
    """Обходит тело элемента Cues (уже вырезанное I/O-обёрткой по размеру
    из peek_element_header), возвращает отсортированную таблицу keyframe'ов
    (frame, pts_time), или None при любой аномалии -- включая "форма похожа
    на валидную, но keyframe на кадре 0 отсутствует" (не рискуем). Никогда
    не бросает исключение."""
    try:
        times: List[float] = []
        p = 0
        while p < len(cues_body):
            eid, p = _eid(cues_body, p); esz, p = _esz(cues_body, p)
            if eid == 0xBB:                         # CuePoint
                body = cues_body[p:p + esz]; rr, ct, tracks = 0, None, []
                while rr < len(body):
                    bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                    v = body[rr:rr + bsz]; rr += bsz
                    if bid == 0xB3:                 # CueTime
                        ct = int.from_bytes(v, "big")
                    elif bid == 0xB7:               # CueTrackPositions -> CueTrack
                        r2 = 0
                        while r2 < len(v):
                            tid, r2 = _eid(v, r2); tsz, r2 = _esz(v, r2)
                            if tid == 0xF7 and int.from_bytes(v[r2:r2 + tsz], "big") == video_track:
                                tracks.append(video_track)
                            r2 += tsz
                if ct is not None and tracks:
                    times.append(ct * scale / 1e9)
            p += esz
    except (IndexError, ValueError):
        return None

    if not times:
        return None
    table = sorted({(round(t * fps), t) for t in times})
    if table[0][0] != 0:                            # без keyframe на кадре 0 — не рискуем
        return None
    return table
