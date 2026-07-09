#!/usr/bin/env python3
"""
encode_scenes.py — сцен-осознанное кодирование в AV1 (Arc/QSV), один файл.

Вход: видео + scene_out.log (от scene_detection.py).

Идея (всё проверено эмпирически на реальном DV-рипе):
  * Каждая сцена кодируется отдельным qsvencc-чанком, поэтому в финале
    keyframe стоит РОВНО на каждом резе (чанк начинается с IDR by construction).
  * Чанк берётся эффективно: --seek на keyframe ИСТОЧНИКА ≤ старта сцены +
    относительный --trim. Декод идёт только от ближайшего keyframe, а не от 0
    (O(N), не O(N²)). Покадрово точно: SSIM 0.9999 к trim-от-0.
  * Чанки — сырой AV1 (.obu). Склейка = cat (мгновенно). DV RPU (profile 10.1)
    и HDR10 (smpte2084 + MDCV/CLL) живут per-frame прямо в потоке и переживают
    cat. Никакого mkvextract/mkvmerge-склейки/dovi_tool в пайплайне.
  * DV в AV1 нельзя наложить пост-фактум (dovi_tool — только HEVC), поэтому
    --dolby-vision-rpu copy идёт per-chunk; это корректно: qsvencc вешает на
    каждый кадр его собственный RPU, а seek+trim выбирает правильные кадры.
  * Финальный мукс — mkvmerge: видео(.obu, с явным fps) + аудио (один энкод
    ffmpeg по правилам пресета) + сабы/главы/вложения из источника.

Правило чанка для сцены [S, E):
    K = последний keyframe источника с frame_K ≤ S
    qsvencc --seek <floor_ms(время K)> --trim (S−K):(E−1−K)
(seek приземляется на первый keyframe ≥ времени seek; floor_ms гарантирует
попадание именно на K.)

Использование:
    python3 encode_scenes.py video.mkv scene_out.log
    python3 encode_scenes.py video.mkv scene_out.log --from 100 --to 104 -o test.mkv
    JOBS=3 ICQ=25 python3 encode_scenes.py video.mkv scene_out.log
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Пресет видео (1:1 из encode_av1_opus.sh; --i-adapt/--b-adapt убраны — они
# требуют lookahead, а LA-ICQ на Alchemist не поддержан, т.е. были no-op).
# --------------------------------------------------------------------------- #
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))
DV_PROFILE = os.environ.get("DV_PROFILE", "10.1")
JOBS = int(os.environ.get("JOBS", "3"))            # параллельных qsvencc-сессий
FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")

LOSSLESS = {"pcm", "truehd", "mlp", "flac", "alac", "wavpack", "tak", "ape", "als"}


def die(msg: str) -> None:
    sys.exit(f"encode_scenes: {msg}")


def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


# --------------------------------------------------------------------------- #
# Лог и тайминги
# --------------------------------------------------------------------------- #
_START = time.monotonic()


def log(msg: str) -> None:
    """Строка лога с меткой прошедшего от старта времени (unbuffered)."""
    print(f"[{time.monotonic() - _START:8.1f}s] {msg}", flush=True)


@contextmanager
def step(name: str):
    """Обёртка операции: логирует старт и длительность (✔ печатается только
    при успехе — исключение проходит мимо, без ложного ✔)."""
    t0 = time.monotonic()
    log(f"▶ {name}…")
    yield
    log(f"✔ {name} — {time.monotonic() - t0:.1f}с")


# --------------------------------------------------------------------------- #
# Разбор входных данных
# --------------------------------------------------------------------------- #
import re

_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")


def read_scenes(path: Path) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for line in path.read_text().splitlines():
        m = _SCENE_RE.search(line)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    if not out:
        die(f"в {path} не найдено ни одной сцены")
    return out


def probe_fps(src: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=avg_frame_rate,r_frame_rate",
           "-of", "json", str(src)]
    data = json.loads(run(cmd, capture_output=True, text=True, check=True).stdout)
    st = data["streams"][0]
    for key in ("avg_frame_rate", "r_frame_rate"):
        val = st.get(key, "")
        if val and "/" in val:
            num, den = val.split("/")
            if int(den) != 0 and int(num) != 0:
                return int(num) / int(den)
    die("не удалось определить fps источника")


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
    proc = run(cmd, capture_output=True, text=True)
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


# --------------------------------------------------------------------------- #
# Определение HDR/DV источника (как в encode_av1_opus.sh)
# --------------------------------------------------------------------------- #
def detect_hdr(src: Path) -> List[str]:
    flags: List[str] = []
    transfer = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=color_transfer", "-of", "csv=p=0",
                    str(src)], capture_output=True, text=True).stdout
    transfer = transfer.split(",")[0].strip()
    side = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-read_intervals", "%+#1", "-show_frames",
                "-show_entries", "frame=side_data_list", "-of", "default=nw=1",
                str(src)], capture_output=True, text=True).stdout.lower()
    if transfer in ("smpte2084", "arib-std-b67"):
        flags += ["--master-display", "copy", "--max-cll", "copy"]
    if any(k in side for k in ("2094-40", "hdr10+", "hdr dynamic metadata")):
        flags += ["--dhdr10-info", "copy"]
    if any(k in side for k in ("dovi", "dolby vision")):
        flags += ["--dolby-vision-rpu", "copy", "--dolby-vision-profile", DV_PROFILE]
    return flags


# --------------------------------------------------------------------------- #
# Кодирование одного чанка -> сырой AV1 .obu
# --------------------------------------------------------------------------- #
def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
    cmd = [
        "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
        "--icq", str(ICQ), "--qp-max", str(QPMAX),
        "--output-depth", "10", "--profile", "main",
        "--gop-len", str(GOP_LEN), "--gop-ref-dist", "6", "--b-pyramid",
        "--tile-col", "1", "--tile-row", "1",
        "--tune", "perceptual", "--scenario-info", "archive",
        "--colorrange", "auto", "--colormatrix", "auto", "--colorprim", "auto",
        "--transfer", "auto", "--chromaloc", "auto",
        *hdr_flags,
    ]
    if metrics:                                  # PSNR/SSIM считает сам qsvencc
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd


# qsvencc печатает (в stderr):
#  ssim/psnr: SSIM YUV: <Y> (<Ydb>), <U> (..), <V> (..), All: <all> (<alldb>), (Frames: N)
#  ssim/psnr: PSNR YUV: <Y>, <U>, <V>, Avg: <avg>, (Frames: N)
_SSIM_RE = re.compile(
    r"SSIM\s+YUV:\s*([\d.]+)\s*\([\d.]+\),.*?All:\s*([\d.]+)\s*\(([\d.]+)\)", re.I)
_PSNR_RE = re.compile(r"PSNR\s+YUV:\s*([\d.]+),.*?Avg:\s*([\d.]+)", re.I)


def parse_metrics(output: str) -> dict:
    m = {"ssim_y": None, "ssim_all": None, "ssim_db": None,
         "psnr_y": None, "psnr_avg": None}
    s = _SSIM_RE.search(output)
    if s:
        m["ssim_y"], m["ssim_all"], m["ssim_db"] = (
            float(s.group(1)), float(s.group(2)), float(s.group(3)))
    p = _PSNR_RE.search(output)
    if p:
        m["psnr_y"], m["psnr_avg"] = float(p.group(1)), float(p.group(2))
    return m


def count_frames(path: Path) -> int:
    """Число видеокадров через пакеты (без декода — 1 пакет = 1 кадр в AV1)."""
    got = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
              capture_output=True, text=True).stdout.strip().rstrip(",")
    return int(got) if got.isdigit() else -1


def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    if proc.returncode != 0:
        return idx, 0, f"qsvencc rc={proc.returncode}: {(proc.stderr or '').strip()[-500:]}", elapsed, info
    got = count_frames(out)
    try:
        info["size"] = out.stat().st_size
    except OSError:
        pass
    if got != expect:
        return idx, got, f"кадров {got}, ожидалось {expect}", elapsed, info
    return idx, got, None, elapsed, info


# --------------------------------------------------------------------------- #
# Аудио (правила пресета: lossless -> FLAC, прочее -> Opus; уже в целевом -> copy)
# --------------------------------------------------------------------------- #
def encode_audio(src: Path, out_mka: Path,
                 ss: Optional[float] = None,
                 dur: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """Возвращает (произведено_ли_аудио, текст_ошибки). Ошибку НЕ бросает
    (крутится в фоновом потоке — падать через die() нельзя, всплыло бы криво)."""
    # AUDIO_COPY=1 — не транскодировать, копировать дорожки как есть (сохраняет
    # Atmos/DTS-X и т.п., но крупнее). По умолчанию — правила пресета.
    audio_copy = os.environ.get("AUDIO_COPY", "0") == "1"
    streams = json.loads(run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index,codec_name,profile,channels,channel_layout",
         "-of", "json", str(src)], capture_output=True, text=True).stdout
    ).get("streams", [])
    if not streams:
        return False, None
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if ss is not None:                       # обрезка под частичный диапазон сцен
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-map_chapters", "-1"]
    for n, st in enumerate(streams):
        cmd += ["-map", f"0:a:{n}"]
        codec = (st.get("codec_name") or "").lower()
        prof = (st.get("profile") or "")
        chans = int(st.get("channels") or 2)
        layout = (st.get("channel_layout") or "")
        lossless = (codec.startswith("pcm") or codec in LOSSLESS
                    or (codec == "dts" and "DTS-HD MA" in prof))
        if audio_copy:
            cmd += [f"-c:a:{n}", "copy"]
        elif lossless:
            if codec == "flac":
                cmd += [f"-c:a:{n}", "copy"]
            else:
                cmd += [f"-c:a:{n}", "flac", f"-compression_level:a:{n}", FLAC_LEVEL]
        else:
            if codec == "opus":
                cmd += [f"-c:a:{n}", "copy"]
            else:
                br = "128k" if chans <= 2 else "256k"
                cmd += [f"-c:a:{n}", "libopus", f"-b:a:{n}", br]
                if chans > 2:
                    # libopus не принимает layout'ы вида 5.1(side)/7.1(wide) ->
                    # нормализуем к базовому (5.1 / 7.1). Каналы те же, меняется
                    # только ярлык позиций, что для кодирования безразлично.
                    target = layout.split("(")[0] if layout else \
                        {6: "5.1", 8: "7.1"}.get(chans, "")
                    if target:
                        cmd += [f"-filter:a:{n}", f"aformat=channel_layouts={target}"]
    cmd += [str(out_mka)]
    proc = run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"ffmpeg rc={proc.returncode}: {proc.stderr.strip()[-800:]}"
    return True, None


def write_metrics_csv(path: Path, rows: Dict[int, dict]) -> dict:
    """Пишет CSV: строка на сцену + итоговая (frame-weighted среднее метрик,
    суммы кадров/времени/размера). Возвращает итоговую строку для лога."""
    fields = ["scene", "start_frame", "end_frame", "frames", "seek", "trim",
              "encode_sec", "fps", "size_mb",
              "ssim_all", "ssim_db", "psnr_avg", "ssim_y", "psnr_y"]
    ordered = [rows[i] for i in sorted(rows)]

    def wmean(key: str) -> Optional[float]:
        vals = [(r["frames"], r[key]) for r in ordered if r.get(key) is not None]
        fr = sum(f for f, _ in vals)
        return round(sum(f * v for f, v in vals) / fr, 5) if fr else None

    total = {
        "scene": "ИТОГО",
        "frames": sum(r["frames"] for r in ordered),
        "encode_sec": round(sum(r["encode_sec"] for r in ordered), 1),
        "size_mb": round(sum(r["size_mb"] for r in ordered), 1),
        "ssim_all": wmean("ssim_all"), "ssim_db": wmean("ssim_db"),
        "psnr_avg": wmean("psnr_avg"), "ssim_y": wmean("ssim_y"),
        "psnr_y": wmean("psnr_y"),
    }
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ordered:
            w.writerow(r)
        w.writerow(total)
    return total


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Сцен-осознанный AV1-энкод (Arc/QSV)")
    ap.add_argument("video", type=Path)
    ap.add_argument("scenes", type=Path, help="scene_out.log от scene_detection.py")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--from", dest="frm", type=int, default=0, help="первая сцена")
    ap.add_argument("--to", dest="to", type=int, default=None, help="последняя (искл.)")
    ap.add_argument("--workdir", type=Path, default=None, help="папка чанков")
    ap.add_argument("--keep", action="store_true", help="не удалять чанки")
    ap.add_argument("--jobs", type=int, default=JOBS)
    ap.add_argument("--no-audio", action="store_true", help="не кодировать аудио")
    ap.add_argument("--no-metrics", action="store_true",
                    help="не считать PSNR/SSIM (быстрее)")
    ap.add_argument("--csv", type=Path, default=None,
                    help="CSV с метриками (по умолчанию <out>.metrics.csv)")
    args = ap.parse_args()

    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")
    if not args.video.is_file():
        die(f"нет файла: {args.video}")

    out = args.out or args.video.with_name(args.video.stem + ".av1.mkv")
    workdir = args.workdir or out.with_name(out.stem + ".chunks")
    workdir.mkdir(parents=True, exist_ok=True)

    scenes_all = read_scenes(args.scenes)
    lo = max(0, args.frm)
    hi = args.to if args.to is not None else len(scenes_all)
    scenes = scenes_all[lo:hi]
    if not scenes:
        die("пустой диапазон сцен (--from/--to)")
    partial = (lo != 0) or (hi != len(scenes_all))

    metrics_on = not args.no_metrics
    log(f">> источник: {args.video.name}")
    log(f">> сцен: {len(scenes)} [{lo},{hi})  ICQ={ICQ} qp-max={QPMAX} "
        f"gop={GOP_LEN} jobs={args.jobs} metrics={'on' if metrics_on else 'off'}")

    fps = probe_fps(args.video)
    log(f">> fps={fps:.5f}")
    with step("чтение keyframe-таблицы источника"):
        table = keyframe_table(args.video, fps)
    log(f">> keyframe'ов в источнике: {len(table)}")
    hdr_flags = detect_hdr(args.video)
    if hdr_flags:
        log(f">> HDR/DV: {' '.join(hdr_flags)}")

    total_expect = sum(e - s for s, e in scenes)

    # --- аудио СРАЗУ, параллельно фазе чанков (CPU/ffmpeg vs GPU/qsvencc) ---
    audio = workdir / "audio.mka"
    audio_pool = ThreadPoolExecutor(max_workers=1)
    audio_future = None
    audio_t0 = time.monotonic()
    if not args.no_audio:
        a_ss = (scenes[0][0] / fps) if partial else None
        a_dur = (total_expect / fps) if partial else None
        audio_future = audio_pool.submit(encode_audio, args.video, audio, a_ss, a_dur)
        log("▶ аудио стартовало параллельно с чанками")

    # --- задания на чанки ---
    tasks = []
    chunk_paths: List[Path] = []
    meta: Dict[int, Tuple[int, int, str, str]] = {}  # idx -> (s, e, seek, trim)
    for i, (s, e) in enumerate(scenes):
        kf_frame, kf_time = kf_before(table, s)
        seek = fmt_seek(kf_time)
        trim = f"{s - kf_frame}:{e - 1 - kf_frame}"
        cp = workdir / f"chunk_{i:05d}.obu"
        chunk_paths.append(cp)
        cmd = chunk_command(args.video, seek, trim, cp, hdr_flags, metrics_on)
        tasks.append((i, cmd, cp, e - s))
        meta[i] = (s, e, seek, trim)

    # --- кодирование чанков + инкрементальная упорядоченная склейка ---
    # Чанки финишируют не по порядку (параллель), а склейка обязана быть в
    # порядке сцен -> «высокая вода»: дописываем chunk i, когда готовы i и все
    # до него. I/O склейки прячется за GPU-энкодом; чанк удаляется сразу после
    # дозаписи (пиковый диск вдвое меньше).
    log(f"▶ кодирую {len(tasks)} чанков (по {args.jobs} параллельно), "
        f"склеиваю по мере готовности…")
    phase_t0 = time.monotonic()
    movie = workdir / "movie.obu"
    movie_fh = movie.open("wb")
    next_append = 0
    ready: Dict[int, int] = {}      # idx -> кадров (готов, ждёт очереди на склейку)
    rows: Dict[int, dict] = {}      # idx -> строка метрик для CSV
    ctimes: List[float] = []
    errors: List[str] = []
    done = 0

    def flush_appends() -> None:
        nonlocal next_append
        while next_append in ready:
            cp = chunk_paths[next_append]
            with cp.open("rb") as r:
                shutil.copyfileobj(r, movie_fh, length=8 << 20)
            movie_fh.flush()
            if not args.keep:
                cp.unlink(missing_ok=True)
            next_append += 1

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(encode_chunk, t): t[0] for t in tasks}
        for fut in as_completed(futs):
            idx, got, err, el, info = fut.result()
            done += 1
            s, e, seek, trim = meta[idx]
            head = f"  [{done}/{len(tasks)}] чанк {idx+lo:>4d} сцена[{s},{e})"
            if err:
                errors.append(f"чанк {idx+lo}: {err}")
                log(f"{head} — ОШИБКА за {el:.1f}с: {err}")
                continue
            ctimes.append(el)
            ss, ps = info.get("ssim_all"), info.get("psnr_avg")
            mtxt = (f" SSIM {ss:.5f} PSNR {ps:.2f}dB"
                    if ss is not None and ps is not None else " (метрик нет)")
            log(f"{head}: {got}к/{el:.1f}с {(e-s)/el:.0f}fps{mtxt}")
            rows[idx] = {
                "scene": idx + lo, "start_frame": s, "end_frame": e,
                "frames": e - s, "seek": seek, "trim": trim,
                "encode_sec": round(el, 2), "fps": round((e - s) / el, 1),
                "size_mb": round(info.get("size", 0) / 1e6, 2),
                "ssim_all": info.get("ssim_all"), "ssim_db": info.get("ssim_db"),
                "psnr_avg": info.get("psnr_avg"),
                "ssim_y": info.get("ssim_y"), "psnr_y": info.get("psnr_y"),
            }
            ready[idx] = got
            flush_appends()          # дописать в порядке всё готовое подряд
    movie_fh.close()
    phase_wall = time.monotonic() - phase_t0
    if ctimes:
        log(f"✔ чанки+склейка — wall {phase_wall:.1f}с, сумма энкода {sum(ctimes):.1f}с "
            f"(параллелизм ×{sum(ctimes)/phase_wall:.1f}), "
            f"на чанк min/avg/max {min(ctimes):.1f}/"
            f"{sum(ctimes)/len(ctimes):.1f}/{max(ctimes):.1f}с")
    if errors:
        die("часть чанков не удалась — файл собирать нельзя:\n  "
            + "\n  ".join(errors[:10]))
    if next_append != len(tasks):
        die(f"склейка неполная: дописано {next_append} из {len(tasks)} чанков")

    # --- проверка кадров склейки ---
    with step("проверка кадров склейки"):
        got = count_frames(movie)
    if got != total_expect:
        die(f"после склейки кадров {got}, ожидалось {total_expect} — стоп")
    log(f">> склейка: {got} кадров (совпало с суммой сцен)")
    if not partial and scenes_all and got != scenes_all[-1][1]:
        log(f"   ВНИМАНИЕ: кадров {got}, а конец последней сцены "
            f"{scenes_all[-1][1]} — расхождение с исходником")

    # --- дождаться аудио (шло параллельно фазе чанков) ---
    has_audio = False
    if args.no_audio:
        log(">> аудио: пропущено (--no-audio)")
    else:
        with step("ожидание аудио (шло параллельно)"):
            has_audio, aerr = audio_future.result()
        if aerr:
            die(f"кодирование аудио упало: {aerr}")
        log(f">> аудио: {'готово' if has_audio else 'нет дорожек'} "
            f"(общее время {time.monotonic()-audio_t0:.1f}с)")
    audio_pool.shutdown(wait=True)

    # --- CSV с метриками (строка на сцену + итоговая) ---
    if rows:
        csv_path = args.csv or Path(str(out) + ".metrics.csv")
        total = write_metrics_csv(csv_path, rows)
        log(f">> метрики -> {csv_path}")
        if total.get("ssim_all") is not None:
            log(f">> ИТОГО (frame-weighted): SSIM {total['ssim_all']:.5f} "
                f"PSNR {total['psnr_avg']:.2f}dB  | {total['frames']} кадров, "
                f"{total['size_mb']:.0f} MB")

    # --- финальный мукс ---
    num, den = fps.as_integer_ratio() if isinstance(fps, float) else (fps, 1)
    # точный рациональный fps для mkvmerge (24000/1001 и т.п.)
    fps_str = f"{round(fps*1001)}/1001" if abs(fps*1001 - round(fps*1001)) < 0.5 else f"{num}/{den}"
    mux = ["mkvmerge", "-o", str(out),
           "--default-duration", f"0:{fps_str}p", str(movie)]
    if has_audio:
        mux += [str(audio)]
    if not partial:
        # сабы + главы + вложения из источника (видео/аудио источника не берём)
        mux += ["--no-video", "--no-audio", str(args.video)]
    with step("финальный мукс (mkvmerge)"):
        proc = run(mux, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # 1 = предупреждения mkvmerge
        die(f"mkvmerge упал: {proc.stdout.strip()[-800:]}")

    if not args.keep:
        for cp in chunk_paths:
            cp.unlink(missing_ok=True)
        movie.unlink(missing_ok=True)
        audio.unlink(missing_ok=True)
        try:
            workdir.rmdir()
        except OSError:
            pass

    insz = args.video.stat().st_size
    outsz = out.stat().st_size
    log(f">> ГОТОВО за {time.monotonic() - _START:.1f}с: {out}")
    log(f">>   {insz/1e9:.2f} GB -> {outsz/1e9:.2f} GB "
        f"({outsz/insz*100:.0f}% от источника)")
    if partial:
        log(">>   (частичный диапазон --from/--to: сабы/главы/вложения НЕ вмуксены)")


if __name__ == "__main__":
    main()
