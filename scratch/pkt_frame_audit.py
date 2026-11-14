"""Сверка «пакеты видео контейнера <-> кадры полного программного декода» (WR-01, 10.1-15).

Зачем: после перенумерации ключевых кадров (10.1-14) счёт кадров на путях
--avsw всё ещё не сверяется с пакетами контейнера: пропущенный декодером кадр
сдвигает все последующие номера. Скрипт только ЧИТАЕТ источник и измеряет, что
увидит будущая production-проверка (10.1-16): одна команда ffprobe
`-show_packets -show_frames` на файл, ключ сопоставления (pos, size).

Независимая реализация правила а–д (в src её нет, импортов из src тоже):
  P[0..n-1] -- пакеты в порядке контейнера, ключ = (pos, size), флаг K.
  M = мультимножество ключей пакетов минус мультимножество ключей кадров, N = |M|.
  Допустимо тогда и только тогда, когда:
  (а) кадров не больше, чем пакетов, по каждому ключу;
  (б) P[0] ключевой и его ключ не в M;
  (в) P[1..N] не ключевые и мультимножество их ключей равно M;
  (г) ключи из M не встречаются среди пакетов вне P[1..N];
  (д) P[N+1] существует и все кадры с его ключом имеют pict_type I или P.
Печатает по каждому файлу строки `[audit] <имя>: …`: P, F, повторы pos и
(pos, size), N/A, лишние кадры, пропавшие пакеты, крошечные пакеты, темп,
времена вокруг пропажи, кандидаты-различители К1–К6, вердикт.

Флаг --vc1-headers дополнительно разбирает заголовки кадров VC-1 (осуществимость
различителя «начальный B-кадр / пропавший P») и для h264/hevc/mpeg2 проверяет
вывод bsf trace_headers.

Запуск:
  uv run python scratch/pkt_frame_audit.py [--vc1-headers] ФАЙЛ…
Код возврата: 0, если все файлы измерены (вердикт любой); 1, если была ОШИБКА.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enpipe.shared import proc as _proc

Key = Tuple[Optional[int], Optional[int]]

_SHOW = ("packet=pos,size,flags,pts_time,dts_time:"
         "frame=pkt_pos,pkt_size,pict_type,best_effort_timestamp_time")


def _num(s: Optional[str]) -> Optional[float]:
    if s is None or s == "N/A":
        return None
    return float(s)


def _int(s: Optional[str]) -> Optional[int]:
    if s is None or s == "N/A":
        return None
    return int(s)


def _fmt(v: Optional[float]) -> str:
    return "N/A" if v is None else f"{v:.3f}"


def parse_compact(text: str) -> Tuple[List[dict], List[dict]]:
    """Разбор compact-вывода: секция — префикс строки, поля — пары key=value."""
    packets: List[dict] = []
    frames: List[dict] = []
    for line in text.splitlines():
        parts = line.split("|")
        sect = parts[0]
        if sect not in ("packet", "frame"):
            continue
        kv = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
        if sect == "packet":
            packets.append({
                "pos": _int(kv.get("pos")), "size": _int(kv.get("size")),
                "flags": kv.get("flags", ""), "pts": _num(kv.get("pts_time")),
                "dts": _num(kv.get("dts_time")),
            })
        else:
            frames.append({
                "pos": _int(kv.get("pkt_pos")), "size": _int(kv.get("pkt_size")),
                "type": kv.get("pict_type", "?"),
                "be": _num(kv.get("best_effort_timestamp_time")),
            })
    return packets, frames


def pkey(x: dict) -> Key:
    return (x["pos"], x["size"])


def missing_packets(packets: List[dict], mp: Counter, mf: Counter) -> List[Tuple[int, bool]]:
    """Пропавшие пакеты (индекс, неоднозначен ли): берутся первые вхождения ключа."""
    rem = mp - mf
    out: List[Tuple[int, bool]] = []
    for i, p in enumerate(packets):
        k = pkey(p)
        if rem.get(k, 0) > 0:
            rem[k] -= 1
            out.append((i, mp[k] > (mp - mf)[k]))
    return out


def verdict(packets: List[dict], frames: List[dict]) -> Tuple[str, int]:
    """Правило а–д. Возвращает (текст вердикта, N)."""
    mp = Counter(pkey(p) for p in packets)
    mf = Counter(pkey(f) for f in frames)
    extra = mf - mp
    if extra:
        return f"отказ: (а) кадров больше пакетов по {len(extra)} ключам", 0
    m = mp - mf
    n = sum(m.values())
    if n == 0:
        return "совпадает", 0
    if not packets or "K" not in packets[0]["flags"]:
        return "отказ: (б) P[0] не ключевой", n
    if m.get(pkey(packets[0]), 0) > 0:
        return "отказ: (б) ключ P[0] пропал", n
    if len(packets) < n + 2:
        return "отказ: (в)/(д) пакетов меньше N+2", n
    window = packets[1:n + 1]
    if any("K" in p["flags"] for p in window):
        return "отказ: (в) в P[1..N] есть ключевой пакет", n
    if Counter(pkey(p) for p in window) != m:
        return "отказ: (в) ключи P[1..N] не равны M", n
    outside = packets[:1] + packets[n + 1:]
    if any(m.get(pkey(p), 0) > 0 for p in outside):
        return "отказ: (г) ключ из M встречается вне P[1..N]", n
    nxt = pkey(packets[n + 1])
    types = [f["type"] for f in frames if pkey(f) == nxt]
    if not types or any(t not in ("I", "P") for t in types):
        return f"отказ: (д) за пропавшими идёт кадр типа {types}", n
    return f"начальные B-кадры открытого GOP: {n}", n


def _agg(vals: List[Optional[bool]]) -> str:
    defined = [v for v in vals if v is not None]
    if not defined:
        return "не применимо"
    return "да" if all(defined) else "нет"


def _lt(a: Optional[float], b: Optional[float]) -> Optional[bool]:
    if a is None or b is None:
        return None
    return a < b


def candidates(packets: List[dict], frames: List[dict], n: int,
               miss: List[Tuple[int, bool]], name: str) -> None:
    """Различитель «начальный B-кадр открытого GOP» против «пропавший P» (W2)."""
    p0 = packets[0]
    print(f"[audit] {name}: ключевой №0: pts {_fmt(p0['pts'])} dts {_fmt(p0['dts'])} "
          f"flags {p0['flags']}")
    nxt = packets[n + 1] if len(packets) > n + 1 else None
    for off in (1, 2):
        i = n + off
        if i < len(packets):
            p = packets[i]
            types = [f["type"] for f in frames if pkey(f) == pkey(p)]
            print(f"[audit] {name}: пакет №{i}: pts {_fmt(p['pts'])} dts {_fmt(p['dts'])} "
                  f"тип кадра {types}")
    key0_frames = [f for f in frames if pkey(f) == pkey(p0)]
    be0 = key0_frames[0]["be"] if key0_frames else None
    print(f"[audit] {name}: best_effort кадра ключевого пакета: {_fmt(be0)}")
    bes = [f["be"] for f in frames if f["be"] is not None]
    min_be = min(bes) if bes else None
    print(f"[audit] {name}: минимум best_effort по всем кадрам: {_fmt(min_be)}")
    k: Dict[str, List[Optional[bool]]] = {c: [] for c in ("К1", "К2", "К3", "К4", "К5", "К6")}
    for i, _amb in miss:
        m = packets[i]
        row = {
            "К1": _lt(m["pts"], p0["pts"]),
            "К2": _lt(m["pts"], be0),
            "К3": _lt(m["pts"], nxt["pts"]) if nxt else None,
            "К4": _lt(m["dts"], nxt["dts"]) if nxt else None,
            "К5": ("D" in m["flags"] or "C" in m["flags"]),
            "К6": _lt(m["pts"], min_be),
        }
        for c, v in row.items():
            k[c].append(v)
        print(f"[audit] {name}: пропавший №{i}: " + " ".join(
            f"{c}={'N/A' if v is None else ('да' if v else 'нет')}" for c, v in row.items()))
    defs = {"К1": "pts(пропавшего) < pts(ключевого P[0])",
            "К2": "pts(пропавшего) < best_effort кадра ключевого",
            "К3": "pts(пропавшего) < pts(P[N+1])",
            "К4": "dts(пропавшего) < dts(P[N+1])",
            "К5": "flags пропавшего содержат D или C",
            "К6": "pts(пропавшего) < минимума best_effort всех кадров"}
    for c, vals in k.items():
        print(f"[audit] {name}: {c} ({defs[c]}): верно для всех {len(miss)}: {_agg(vals)}")


def timing_line(packets: List[dict], name: str) -> None:
    both = [p for p in packets if p["pts"] is not None and p["dts"] is not None]
    differ = sum(1 for p in both if abs(p["pts"] - p["dts"]) > 1e-6)
    share = differ / len(both) if both else 0.0
    pts = [p["pts"] for p in packets if p["pts"] is not None]
    mono = all(a <= b for a, b in zip(pts, pts[1:]))
    print(f"[audit] {name}: времена пакетов: раздельные pts/dts: "
          f"{'да' if share > 0.01 else 'нет'} (pts≠dts у {share * 100:.1f}% из {len(both)}); "
          f"pts монотонны в порядке контейнера: {'да' if mono else 'нет'} "
          f"(при B-кадрах «да» означает времена в порядке кодирования, «нет» -- "
          f"pts в порядке показа); "
          f"пакетов без pts: {len(packets) - len(pts)}")


def probe_info(path: str) -> dict:
    r = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=codec_name,r_frame_rate,avg_frame_rate,duration:"
                   "format=duration,format_name", "-of", "json", path],
                  capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe info rc={r.returncode}: {r.stderr[:200]}")
    d = json.loads(r.stdout)
    st = (d.get("streams") or [{}])[0]
    fm = d.get("format", {})
    return {"codec": st.get("codec_name", "?"), "container": fm.get("format_name", "?"),
            "r": st.get("r_frame_rate", "0/1"), "a": st.get("avg_frame_rate", "0/1"),
            "dur": float(st.get("duration") or fm.get("duration") or 0.0)}


def _ratio(s: str) -> float:
    a, _, b = s.partition("/")
    return float(a) / float(b) if b and float(b) else float(a)


def audit(path: str, vc1_headers: bool) -> None:
    name = Path(path).name
    info = probe_info(path)
    t0 = time.monotonic()
    r = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_packets",
                   "-show_frames", "-show_entries", _SHOW, "-of", "compact", path],
                  capture_output=True, text=True)
    took = time.monotonic() - t0
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe rc={r.returncode}: {r.stderr[:200]}")
    packets, frames = parse_compact(r.stdout)
    err = r.stderr.strip()
    nbytes = len(r.stderr.encode())
    print(f"[audit] {name}: кодек {info['codec']}, контейнер {info['container']}, "
          f"пакетов P {len(packets)}, кадров F {len(frames)}, время {took:.1f} с, "
          f"rc {r.returncode}, stderr: {nbytes} байт")
    if nbytes:
        print(f"[audit] {name}: stderr (первые 300 символов): {err[:300]!r}")
    mp = Counter(pkey(p) for p in packets)
    mf = Counter(pkey(f) for f in frames)
    dup_pos = sum(c - 1 for c in Counter(p["pos"] for p in packets if p["pos"] is not None).values() if c > 1)
    dup_key = sum(c - 1 for c in mp.values() if c > 1)
    na_p = sum(1 for p in packets if p["pos"] is None)
    na_f = sum(1 for f in frames if f["pos"] is None)
    print(f"[audit] {name}: повторов pos: {dup_pos}; повторов (pos, size): {dup_key}; "
          f"пакетов с pos N/A: {na_p}; кадров с pkt_pos N/A: {na_f}")
    extra = sum((mf - mp).values())
    miss = missing_packets(packets, mp, mf)
    print(f"[audit] {name}: лишних кадров: {extra}; пропавших пакетов: {len(miss)}")
    for i, amb in miss[:10]:
        p = packets[i]
        print(f"[audit] {name}:   №{i} pos {p['pos']} size {p['size']} flags {p['flags']} "
              f"pts {_fmt(p['pts'])} dts {_fmt(p['dts'])} неоднозначен: {'да' if amb else 'нет'}")
    tiny = [p for p in packets if p["size"] is not None and p["size"] <= 16]
    miss_idx = {i for i, _ in miss}
    t0n = sum(1 for i, p in enumerate(packets) if p["size"] is not None and p["size"] <= 16 and i in miss_idx)
    sizes = [p["size"] for p in tiny]
    rng = f"{min(sizes)}–{max(sizes)} байт" if sizes else "-"
    print(f"[audit] {name}: крошечных пакетов (size ≤ 16): {len(tiny)}; из них с кадром "
          f"декода по ключу (pos, size): {len(tiny) - t0n}; без кадра: {t0n}; размеры: {rng}")
    ra, rr = _ratio(info["a"]), _ratio(info["r"])
    print(f"[audit] {name}: r_frame_rate {info['r']}, avg_frame_rate {info['a']}, "
          f"длительность {info['dur']:.3f} с, D·A ≈ {info['dur'] * ra:.1f}, "
          f"D·R ≈ {info['dur'] * rr:.1f}, кадров {len(frames)}")
    timing_line(packets, name)
    v, n = verdict(packets, frames)
    if miss and packets:
        candidates(packets, frames, len(miss), miss, name)
    print(f"[audit] {name}: вердикт: {v}")
    if vc1_headers:
        extra_headers(path, name, info["codec"], packets, miss_idx)


# ---------------------------------------------------------------------------
# Осуществимость различителя по заголовку кадра (только измерение)
# ---------------------------------------------------------------------------

_HEXLINE = re.compile(r"^[0-9a-f]{8}: ")


def _bits(data: bytes, bit: int, n: int) -> int:
    v = 0
    for i in range(n):
        byte = data[(bit + i) // 8]
        v = (v << 1) | ((byte >> (7 - (bit + i) % 8)) & 1)
    return v


def _interlace_flag(path: str) -> Optional[int]:
    """INTERLACE из sequence header Advanced profile (extradata): бит 41 после 0x0F."""
    r = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                   "-show_data", "-show_entries", "stream=extradata", path],
                  capture_output=True, text=True)
    raw = bytearray()
    for line in r.stdout.splitlines():
        if _HEXLINE.match(line):
            raw += bytes.fromhex("".join(line[10:50].split()))
    i = bytes(raw).find(b"\x00\x00\x01\x0f")
    if i < 0 or len(raw) < i + 4 + 7:
        return None
    return _bits(bytes(raw[i + 4:]), 41, 1)


def _ptype(head: bytes, interlace: int) -> Optional[str]:
    """Тип кадра по заголовку Advanced profile: FCM (если interlace), затем PTYPE."""
    j = head.find(b"\x00\x00\x01\x0d")
    body = head[j + 4:] if 0 <= j < 400 else head
    if len(body) < 2:
        return None
    pos = 0
    if interlace:
        if _bits(body, 0, 1) != 0:
            return None  # чересстрочный кадр/поля: структура иная, не разбирается
        pos = 1
    b = _bits(body, pos, 1)
    if b == 0:
        return "P"
    if _bits(body, pos, 2) == 0b10:
        return "B"
    if _bits(body, pos, 3) == 0b110:
        return "I"
    if _bits(body, pos, 4) == 0b1110:
        return "BI"
    return "P"  # skipped: у ffmpeg pict_type P


def vc1_headers(path: str, name: str, miss_idx: set) -> None:
    il = _interlace_flag(path)
    if il is None:
        print(f"[audit] заголовки vc1 {name}: sequence header не найден в extradata")
        return
    proc = _proc.popen(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-read_intervals", "%+#200", "-show_packets", "-show_frames",
                        "-show_data", "-show_entries",
                        "packet=pos,size,flags,data:frame=pkt_pos,pkt_size,pict_type",
                        "-of", "default", path],
                       stdout=_proc.subprocess.PIPE, stderr=_proc.subprocess.DEVNULL, text=True)
    pkts: List[dict] = []
    frs: List[dict] = []
    cur: Optional[dict] = None
    sect = ""
    in_data = False
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line in ("[PACKET]", "[FRAME]"):
            sect, cur, in_data = line[1:-1], {"head": bytearray()}, False
            continue
        if line in ("[/PACKET]", "[/FRAME]"):
            (pkts if sect == "PACKET" else frs).append(cur or {})
            cur, in_data = None, False
            continue
        if cur is None:
            continue
        if in_data and _HEXLINE.match(line):
            if len(cur["head"]) < 512:
                cur["head"] += bytes.fromhex("".join(line[10:50].split()))
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            cur[k] = v
            in_data = (k == "data")
    proc.wait()
    ftype = {(_int(f.get("pkt_pos")), _int(f.get("pkt_size"))): f.get("pict_type", "?") for f in frs}
    ok = total = 0
    bad: List[str] = []
    missing_types: List[str] = []
    for i, p in enumerate(pkts):
        t = _ptype(bytes(p["head"]), il)
        k = (_int(p.get("pos")), _int(p.get("size")))
        if i in miss_idx:
            missing_types.append(f"№{i}: по заголовку {t}")
        if k in ftype and t is not None:
            total += 1
            if t == ftype[k] or (t == "BI" and ftype[k] == "B"):  # ffmpeg метит BI как B
                ok += 1
            elif len(bad) < 5:
                bad.append(f"№{i}: заголовок {t} против декодера {ftype[k]}")
    print(f"[audit] заголовки vc1 {name}: INTERLACE={il}; совпало {ok} из {total} "
          f"(первых пакетов с кадром декода)")
    if bad:
        print(f"[audit] заголовки vc1 {name}: расхождения: {'; '.join(bad)}")
    if missing_types:
        print(f"[audit] заголовки vc1 {name}: тип пропавших пакетов: {'; '.join(missing_types)}")


def extra_headers(path: str, name: str, codec: str, packets: List[dict], miss_idx: set) -> None:
    if codec == "vc1":
        vc1_headers(path, name, miss_idx)
        return
    want = {"h264": "slice_type", "hevc": "slice_type", "mpeg2video": "picture_coding_type"}
    if codec not in want:
        return
    r = _proc.run(["ffmpeg", "-hide_banner", "-v", "info", "-i", path, "-an", "-sn",
                   "-c:v", "copy", "-bsf:v", "trace_headers", "-frames:v", "4",
                   "-f", "null", "-"], capture_output=True, text=True)
    found = want[codec] in r.stderr
    print(f"[audit] trace_headers {name} ({codec}): поле {want[codec]} в выводе: "
          f"{'да' if found else 'нет'} (rc {r.returncode})")


def main() -> int:
    args = sys.argv[1:]
    hdr = "--vc1-headers" in args
    files = [a for a in args if a != "--vc1-headers"]
    if not files:
        print("использование: uv run python scratch/pkt_frame_audit.py [--vc1-headers] ФАЙЛ…",
              file=sys.stderr)
        return 2
    failed = 0
    for f in files:
        try:
            audit(f, hdr)
        except Exception as ex:  # один сбойный файл не прерывает остальные замеры
            failed += 1
            print(f"[audit] {Path(f).name}: ОШИБКА {type(ex).__name__}: {ex}")
        sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
