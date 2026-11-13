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

Перенумерация по выводу декодера (фаза 10.1, план 09). У VC-1 блоки в mkv идут
в порядке декодирования, поэтому `round(время Cues * fps)` расходится с позицией
I-кадра в выводе декодера на ±1 (handoff §3.1, эксперимент 10.1-08). Детект
нумерует кадры по выводу декодера, и qsvencc `--trim` считает свои выходные
кадры так же. Для выбранных кодеков номер ключевого кадра берётся из вывода
декодера, а время seek остаётся из Cues: эксперимент показал, что qsvencc
приземляется на нужный I-кадр. Любая неясность — громкий отказ, не догадка."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.mkv import ebml as _ebml
from enpipe.shared import proc as _proc
from enpipe.shared.logging import die, log

# Решение оператора (10.1-09, Task 1): `vc1-family` — только семейство VC-1 по
# codec_name, на любом пути декода. Остальные кодеки проходят без лишнего декода.
DECODER_ORDER_CODECS = frozenset({"vc1", "wmv3", "vc1image"})
# Окно поиска I-кадра вокруг номера Cues; не расширять (расхождение ≤ ±1).
RENUMBER_WINDOW = 2


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
    проход ffprobe по пакетам (без декода). Медленно (I/O по всему файлу).

    Ключевой пакет без pts -- отказ, а не пропуск: пропуск молча давал
    неполную таблицу (10.1-13). Неключевые пакеты без pts таблицу не портят."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_packets", "-show_entries", "packet=flags,pts_time",
           "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (keyframes) упал: {proc.stderr.strip()}")
    table: List[Tuple[int, float]] = []
    key_total = 0
    key_no_pts = 0
    for line in proc.stdout.splitlines():
        # формат: "<pts_time>,<flags>", напр. "627.544000,K__"
        parts = line.split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        key_total += 1
        try:
            t = float(parts[0])
        except ValueError:
            key_no_pts += 1
            continue
        table.append((round(t * fps), t))
    if key_no_pts:
        die(f"{src.name}: у {key_no_pts} из {key_total} ключевых кадров нет pts "
            "(pts_time=N/A): таблица ключевых кадров по пакетам неполная, "
            "нарезка по сценам остановлена (источники без pts -- одночанковый "
            "режим; сценовая нарезка -- бэклог 999.8)")
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


# --- нумерация по выводу декодера (10.1-09) ----------------------------------- #


def needs_decoder_order(codec: str) -> bool:
    """Нужна ли перенумерация ключевых кадров по выводу декодера (решение
    оператора Task 1: семейство VC-1)."""
    return codec in DECODER_ORDER_CODECS


def decoded_i_frames(src: Path) -> Tuple[List[int], int]:
    """Позиции I-кадров в выводе декодера и общее число кадров.

    Решение оператора Task 2: отдельный проход `ffprobe -show_frames`
    (полный программный декод; ~86 к/с)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_frames", "-show_entries", "frame=pict_type",
           "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = proc.stderr.strip()[-500:]
        die(f"ffprobe (позиции I-кадров) упал: {tail}")
    types = [ln.strip().rstrip(",") for ln in proc.stdout.splitlines()
             if ln.strip()]
    if not types:
        die("ffprobe (позиции I-кадров) не вернул ни одного кадра")
    return [i for i, t in enumerate(types) if t == "I"], len(types)


def renumber_to_decoder_order(
    table: List[Tuple[int, float]],
    i_positions: List[int],
    window: int = RENUMBER_WINDOW,
) -> List[Tuple[int, float]]:
    """Номера ключевых кадров Cues -> позиции I-кадров в выводе декодера.

    Время (Cues) не меняется, меняется только номер. ValueError: нет I-кадра
    в ±window, ничья, нестрогое возрастание, кадр 0 не отображается в 0."""
    out: List[Tuple[int, float]] = []
    for k, t in table:
        near = [q for q in i_positions if abs(q - k) <= window]
        if not near:
            raise ValueError(
                f"нет I-кадра в пределах ±{window} от ключевого кадра Cues {k}")
        best = min(abs(q - k) for q in near)
        tied = sorted({q for q in near if abs(q - k) == best})
        if len(tied) > 1:
            raise ValueError(
                f"неоднозначный I-кадр для ключевого кадра Cues {k}: {tied}")
        out.append((tied[0], t))
    for (a, _), (b, _) in zip(out, out[1:]):
        if b <= a:
            raise ValueError(
                f"перенумерованные ключевые кадры не строго возрастают: {a} -> {b}")
    if not out or out[0][0] != 0:
        raise ValueError(
            "ключевой кадр 0 не отображается в позицию 0 "
            f"(получено {out[0][0] if out else 'пусто'})")
    return out


def keyframe_table_decoder_order(
    src: Path, table: List[Tuple[int, float]],
) -> Tuple[List[Tuple[int, float]], int, int]:
    """(новая таблица, кадров декода, сколько номеров изменилось)."""
    i_pos, decoded = decoded_i_frames(src)
    try:
        new = renumber_to_decoder_order(table, i_pos)
    except ValueError as ex:
        die(f"{src.name}: нумерация ключевых кадров по выводу декодера "
            f"неоднозначна: {ex}; кодирование остановлено")
    shifted = sum(1 for (a, _), (b, _) in zip(table, new) if a != b)
    return new, decoded, shifted
