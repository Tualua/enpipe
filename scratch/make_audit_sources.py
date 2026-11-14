"""Синтетические источники и отрицательные контроли для аудита пакетов/кадров (10.1-15).

Зачем: реальные образцы оператора портить и копировать нельзя, а проверку
«сверка пакетов и кадров ловит порчу» (WR-01) нужно проверить на деле. Скрипт
делает в OUTDIR синтетику всех нужных видов (H.264 с B-кадрами и без, open-gop,
HEVC closed/open/radl, mpeg4/msmpeg4v3 в AVI, mpeg2 с открытым GOP в TS) и
отрицательные контроли -- копии с ИСПОРЧЕННЫМ пакетом.

Нужна именно порча, а не удаление: удалённый из файла пакет уменьшает и число
пакетов, и число кадров, расхождения не будет. Способы порчи пробуются по
порядку, до первого, который дал ПРОПАЖУ кадра (кадров < пакетов):
  1) bsf noise на выбранном пакете (`-c copy -bsf:v noise=amount=not(n-IDX)`);
  2) обнуление всей полезной нагрузки пакета в копии файла;
  3) обнуление только первых 8 байт полезной нагрузки (заголовок кадра).
Исход каждого контроля печатается: `[make] <файл>: способ N, исход …`.

Читает только --vc1-closed (вырезка VC-1 с закрытым началом); переменные
окружения не читает; под /data писать отказывается.

Запуск:
  uv run python scratch/make_audit_sources.py OUTDIR --vc1-closed PATH
"""
from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pkt_frame_audit import parse_compact, pkey  # noqa: E402
from enpipe.shared import proc as _proc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SIZE = "1280x720"
RATE = "24"
DUR = "20"
_NO = ["--no-audio", "--no-subtitles", "--no-chapters", "--no-attachments", "--no-global-tags"]
_PROBE_SHOW = ("packet=pos,size,flags,pts_time,dts_time:"
               "frame=pkt_pos,pkt_size,pict_type,best_effort_timestamp_time")


def say(msg: str) -> None:
    print(f"[make] {msg}", flush=True)


def run(cmd: List[str]) -> Tuple[int, str]:
    r = _proc.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stderr or "")[-400:]


def ffmpeg_src(out: Path, vargs: List[str], extra_in: Optional[List[str]] = None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
           f"testsrc2=size={SIZE}:rate={RATE}:duration={DUR}", *vargs, "-an", str(out)]
    rc, err = run(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg для {out.name}: rc={rc} {err}")


def probe(path: Path):
    """(пакеты, кадры, байт stderr) -- та же команда, что в аудите."""
    r = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_packets",
                   "-show_frames", "-show_entries", _PROBE_SHOW, "-of", "compact",
                   str(path)], capture_output=True, text=True)
    pk, fr = parse_compact(r.stdout)
    return pk, fr, len(r.stderr.encode())


def payload_span(data: bytes, pos: int, size: int) -> Optional[Tuple[int, int]]:
    """[начало, конец) полезной нагрузки пакета в файле по pos/size из ffprobe.

    mkv: pos указывает на содержимое блока -- номер дорожки (vint), затем время
    2 байта и флаги 1 байт, дальше полезная нагрузка (проверено по дампу байт);
    AVI: pos рядом с заголовком чанка 00dc/00db, полезная нагрузка после 8 байт."""
    for tag in (b"00dc", b"00db"):
        pat = tag + struct.pack("<I", size)
        i = data.find(pat, max(0, pos - 16), pos + 32)
        if i >= 0:
            return (i + 8, i + 8 + size)
    if data[:4] == b"\x1a\x45\xdf\xa3":
        track_len = 1
        while track_len <= 8 and not (data[pos] & (0x80 >> (track_len - 1))):
            track_len += 1
        start = pos + track_len + 3
        return (start, start + size)
    return None


def classify(src_p: int, pk, fr, nerr: int) -> Tuple[str, str]:
    """Ровно один исход: пропажа кадра / скрыта декодером / видна только в stderr."""
    if len(fr) < len(pk):
        return "пропажа", f"порча привела к пропаже кадра (P {len(pk)}, F {len(fr)}, stderr {nerr} байт)"
    if nerr > 0:
        return "stderr", f"видна только в stderr (P {len(pk)}, F {len(fr)}, stderr {nerr} байт)"
    return "скрыта", f"скрыта декодером (P {len(pk)}, F {len(fr)}, stderr пуст)"


def corrupt(src: Path, out: Path, idx: int, label: str) -> None:
    """Портит пакет №idx источника тремя способами по очереди, пишет результат в out."""
    pk0, _fr0, _ = probe(src)
    p = pk0[idx]
    last = ""
    for method in (1, 2, 3):
        if out.exists():
            out.unlink()
        if method == 1:
            rc, err = run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(src),
                           "-map", "0:v:0", "-c", "copy", "-bsf:v",
                           f"noise=amount=not(n-{idx})", str(out)])
            if rc != 0:
                say(f"{label}: способ 1 недоступен: rc={rc} {err.strip()[:200]}")
                continue
        else:
            shutil.copyfile(src, out)
            data = bytearray(out.read_bytes())
            span = payload_span(bytes(data), p["pos"], p["size"])
            if span is None:
                say(f"{label}: способ {method}: полезная нагрузка не найдена (pos {p['pos']})")
                continue
            a, b = span
            if method == 3:
                b = min(b, a + 8)
            data[a:b] = b"\x00" * (b - a)
            out.write_bytes(bytes(data))
        pk, fr, nerr = probe(out)
        kind, text = classify(idx, pk, fr, nerr)
        mp = {}
        for q in pk:
            mp[pkey(q)] = mp.get(pkey(q), 0) + 1
        for f in fr:
            mp[pkey(f)] = mp.get(pkey(f), 0) - 1
        gone = [i for i, q in enumerate(pk) if mp.get(pkey(q), 0) > 0]
        last = f"способ {method}, исход {text}; пропавшие пакеты: {gone[:5]}"
        if kind == "пропажа":
            say(f"{label}: {last}")
            return
    say(f"{label}: ни один способ не дал пропажи кадра; {last or 'способы недоступны'}")


def pick_packet(path: Path, mode: str) -> Tuple[int, str]:
    """Номер пакета и описание: mid -- неключевой около середины; p1 -- №1;
    first_p -- №1, а если не P, то первый P-пакет после ключевого."""
    pk, fr, _ = probe(path)
    types = {pkey(f): f["type"] for f in fr}
    if mode == "mid":
        i = len(pk) // 2
        while i < len(pk) and "K" in pk[i]["flags"]:
            i += 1
    elif mode == "p1":
        i = 1
    else:
        i = 1
        while i < len(pk) and (types.get(pkey(pk[i])) != "P" or "K" in pk[i]["flags"]):
            i += 1
    p = pk[i]
    return i, f"№{i} pos {p['pos']} size {p['size']} pict_type {types.get(pkey(p), '?')}"


def hevc_sources(out: Path) -> None:
    """HEVC Main10 closed/open/radl: _make_mid_gop_source из аппаратных тестов."""
    sys.path.insert(0, str(ROOT))
    try:
        from tests.integration.test_hardware_real_media import _make_mid_gop_source
        how = "импорт _make_mid_gop_source из tests/integration/test_hardware_real_media.py"
    except Exception as ex:  # повторяем её аргументы ffmpeg дословно
        _make_mid_gop_source = None
        how = f"импорт невозможен ({type(ex).__name__}), аргументы ffmpeg повторены дословно"
    for gop in ("closed", "open", "radl"):
        dst = out / f"hevc_{gop}.mp4"
        if _make_mid_gop_source is not None:
            _make_mid_gop_source(dst, gop=gop)
        else:
            _hevc_verbatim(dst, gop)
        say(f"{dst.name}: {how}, gop={gop}")


def _hevc_verbatim(dst: Path, gop: str) -> None:
    params = {"closed": "open-gop=0", "open": "open-gop=1", "radl": "open-gop=0:radl=2"}[gop]
    rate, size = "24000/1001", SIZE
    srcs = [f"testsrc2=size={size}:rate={rate}", f"mandelbrot=size={size}:rate={rate}",
            f"gradients=size={size}:rate={rate}:speed=0.05",
            f"life=size={size}:rate={rate}:mold=10:ratio=0.1:death_color=#C83232:life_color=#00ff00"]
    lens = [70, 74, 76, 68]
    inputs: List[str] = []
    fc = ""
    for i, (s, n) in enumerate(zip(srcs, lens)):
        inputs += ["-f", "lavfi", "-i", s]
        fc += f"[{i}:v]trim=end_frame={n},setpts=PTS-STARTPTS,format=yuv420p10le[v{i}];"
    fc += "".join(f"[v{i}]" for i in range(4)) + "concat=n=4:v=1[v]"
    rc, err = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                   "-filter_complex", fc, "-map", "[v]", "-c:v", "libx265", "-preset",
                   "ultrafast", "-x265-params",
                   f"keyint=48:min-keyint=48:scenecut=0:bframes=4:log-level=error:{params}",
                   str(dst)])
    if rc != 0:
        raise RuntimeError(f"hevc {gop}: rc={rc} {err}")


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 3 or args[1] != "--vc1-closed":
        print("использование: uv run python scratch/make_audit_sources.py OUTDIR "
              "--vc1-closed PATH", file=sys.stderr)
        return 2
    out = Path(args[0]).resolve()
    vc1 = Path(args[2]).resolve()
    if out.parts[:2] == ("/", "data"):
        print("make_audit_sources: писать под /data запрещено", file=sys.stderr)
        return 2
    if not vc1.is_file():
        print(f"make_audit_sources: нет файла --vc1-closed: {vc1}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    ok = True

    def make(name: str, how: str, vargs: List[str]) -> None:
        nonlocal ok
        try:
            ffmpeg_src(out / name, vargs)
            say(f"{name}: {how}")
        except Exception as ex:
            ok = False
            say(f"{name}: ОШИБКА {ex}")

    x264 = ["-c:v", "libx264", "-preset", "veryfast"]
    make("h264_10bit_bf3.mkv", "libx264 yuv420p10le, -bf 3, -g 48",
         [*x264, "-pix_fmt", "yuv420p10le", "-bf", "3", "-g", "48"])
    make("h264_10bit_bf3.mp4", "libx264 yuv420p10le, -bf 3, -g 48, mp4",
         [*x264, "-pix_fmt", "yuv420p10le", "-bf", "3", "-g", "48"])
    make("h264_bf3.ts", "libx264 8 бит, -bf 3, -g 48, MPEG-TS",
         [*x264, "-pix_fmt", "yuv420p", "-bf", "3", "-g", "48", "-f", "mpegts"])
    make("h264_ippp.mkv", "libx264 8 бит, -bf 0, -g 48 (IPPP)",
         [*x264, "-pix_fmt", "yuv420p", "-bf", "0", "-g", "48"])
    make("h264_opengop.mkv", "libx264 8 бит, -bf 3, open-gop=1:keyint=48",
         [*x264, "-pix_fmt", "yuv420p", "-bf", "3", "-x264-params", "open-gop=1:keyint=48"])
    rc, err = run(["mkvmerge", "-q", "-o", str(out / "h264_opengop_cut.mkv"), *_NO, "--split",
                   "parts:00:00:05.000-00:00:15.000", str(out / "h264_opengop.mkv")])
    if rc in (0, 1):
        say("h264_opengop_cut.mkv: mkvmerge --split parts:00:00:05.000-00:00:15.000 от h264_opengop.mkv")
    else:
        ok = False
        say(f"h264_opengop_cut.mkv: ОШИБКА mkvmerge rc={rc} {err}")
    try:
        hevc_sources(out)
    except Exception as ex:
        ok = False
        say(f"hevc: ОШИБКА {ex}")
    make("mpeg4_bf2.avi", "mpeg4, -bf 2, -g 48, AVI",
         ["-c:v", "mpeg4", "-q:v", "4", "-bf", "2", "-g", "48"])
    make("msmpeg4v3.avi", "msmpeg4 (msmpeg4v3), -g 48, AVI",
         ["-c:v", "msmpeg4", "-q:v", "4", "-g", "48"])
    make("mpeg2_open.ts", "mpeg2video, -bf 2, -g 15, без +cgop, MPEG-TS",
         ["-c:v", "mpeg2video", "-q:v", "4", "-bf", "2", "-g", "15", "-f", "mpegts"])
    rc, err = run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", "5", "-i",
                   str(out / "mpeg2_open.ts"), "-c", "copy", "-t", "10",
                   str(out / "mpeg2_open_cut.ts")])
    if rc == 0:
        say("mpeg2_open_cut.ts: ffmpeg -ss 5 -i mpeg2_open.ts -c copy -t 10")
    else:
        ok = False
        say(f"mpeg2_open_cut.ts: ОШИБКА rc={rc} {err}")

    # --- отрицательные контроли ---
    vc1_copy = out / "vc1_closed_src.mkv"  # копия вырезки: порча делается над копией
    shutil.copyfile(vc1, vc1_copy)
    plan = [
        ("neg_h264_mid.mkv", out / "h264_10bit_bf3.mkv", "mid"),
        ("neg_vc1_mid.mkv", vc1_copy, "mid"),
        ("neg_vc1_p_after_key.mkv", vc1_copy, "first_p"),
        ("neg_h264_ippp_p1.mkv", out / "h264_ippp.mkv", "p1"),
        ("neg_msmpeg4_ippp_p1.avi", out / "msmpeg4v3.avi", "p1"),
    ]
    for name, src, mode in plan:
        try:
            idx, desc = pick_packet(src, mode)
            say(f"{name}: порча пакета {desc} источника {src.name}")
            corrupt(src, out / name, idx, name)
        except Exception as ex:
            ok = False
            say(f"{name}: ОШИБКА {type(ex).__name__}: {ex}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
