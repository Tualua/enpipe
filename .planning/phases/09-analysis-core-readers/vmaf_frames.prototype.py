#!/usr/bin/env python3
"""Разбор худших по VMAF кадров: вырезает кадры источника и энкода, проверяет
выравнивание, считает диагностику и кладёт картинки для просмотра.

Что делает для каждого из N худших кадров (с разносом не ближе --min-gap):
  * точно вырезает кадр K из энкода и кадры K-1..K+1 из источника (accurate
    seek по времени K/fps) и выбирает лучший по PSNR — это проверка, что VMAF
    считался по выровненной паре (сдвиг на кадр дал бы ложные провалы);
  * по 10-битной яркости (Y) считает: PSNR кадра, сетку 8x4 тайлов (где именно
    хуже всего), средний уровень в нитах (PQ EOTF) и долю теней < 5 нит —
    стандартные модели VMAF обучены на SDR, на тёмном PQ они калиброваны хуже;
    «сохранность детали» = энергия лапласиана энкода / источника (<1 — энкодер
    сгладил зерно/текстуру, >1 — добавил шум/блоки);
  * PNG для глаз: тонмаппинг PQ->SDR (zscale + tonemap=hable), 1:1 кроп худшего
    тайла источник|энкод и карта разницы (|src-enc| по Y, усиление x8).
Итог: report.md + index.html в --out.

Только stdlib + numpy; ffmpeg/ffprobe на PATH.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

GRID_X, GRID_Y = 8, 4


# ---------------------------------------------------------------- ввод -----
def read_vmaf(path: Path) -> List[float]:
    with path.open(newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = "\t" if "\t" in sample else ","
        rd = csv.reader(f, delimiter=delim)
        hdr = next(rd)
        col = [h.strip().lower() for h in hdr].index("vmaf")
        out = []
        for row in rd:
            if row:
                out.append(float(row[col].replace(",", ".")))
    return out


def read_scenes(path: Optional[Path]) -> List[Tuple[int, int]]:
    if not path or not path.exists():
        return []
    rx = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")
    return [(int(a), int(b)) for a, b in rx.findall(path.read_text())]


def probe(src: Path) -> Tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    num, den = out[2].split("/")
    return int(out[0]), int(out[1]), float(num) / float(den)


def pick_worst(v: List[float], n: int, gap: int) -> List[int]:
    chosen: List[int] = []
    for k in sorted(range(len(v)), key=v.__getitem__):
        if all(abs(k - c) >= gap for c in chosen):
            chosen.append(k)
            if len(chosen) == n:
                break
    return sorted(chosen)


# ---------------------------------------------------------- извлечение -----
def _seek(frame: int, fps: float) -> str:
    # середина между кадрами: pts в mkv округлены до мс, и -ss ровно K/fps может
    # оказаться чуть позже округлённой метки кадра K и попасть на K+1
    return f"{max(frame - 0.5, 0) / fps:.6f}"


def _split(raw: bytes, w: int, h: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = np.frombuffer(raw[: w * h * 3], dtype="<u2")
    return (a[: w * h].reshape(h, w), a[w * h: w * h * 5 // 4].reshape(h // 2, w // 2),
            a[w * h * 5 // 4:].reshape(h // 2, w // 2))


def grab_yuv(video: Path, frame: int, fps: float, w: int, h: int
             ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Плоскости Y, U, V кадра `frame` как uint16 (10-битные коды)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", _seek(frame, fps), "-i", str(video),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-"],
        capture_output=True, check=True).stdout
    return _split(raw, w, h)


def grab_y(video: Path, frame: int, fps: float, w: int, h: int) -> np.ndarray:
    return grab_yuv(video, frame, fps, w, h)[0]


def scan_frames(video: Path, step: int, w: int, h: int):
    """Каждый step-й кадр подряд (аппаратный декод QSV, отбор до hwdownload)."""
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
           "-i", str(video), "-vf", f"select=not(mod(n\\,{step})),hwdownload,format=p010le",
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-"]
    fs = w * h * 3
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as pr:
        i = 0
        while True:
            raw = pr.stdout.read(fs)
            if len(raw) < fs:
                break
            yield i * step, _split(raw, w, h)
            i += 1


def tonemap_png(video: Path, frame: int, fps: float, out: Path,
                crop: Optional[str] = None) -> None:
    vf = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
          "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=rgb24")
    if crop:
        vf = f"crop={crop}," + vf
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", _seek(frame, fps),
                    "-i", str(video), "-frames:v", "1", "-vf", vf, str(out)],
                   check=True)


def diff_png(a: np.ndarray, b: np.ndarray, out: Path, scale: int = 8) -> None:
    d = np.clip(np.abs(a.astype(np.int32) - b.astype(np.int32)) * scale // 4,
                0, 255).astype(np.uint8)            # 10 бит -> 8 бит, усиление
    h, w = d.shape
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo",
                    "-pix_fmt", "gray", "-s", f"{w}x{h}", "-i", "-",
                    "-vf", "scale=iw/2:-1", str(out)],
                   input=d.tobytes(), check=True)


# ------------------------------------------------------------ метрики ------
def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * math.log10(1023.0 ** 2 / mse)


def pq_nits(code: np.ndarray) -> np.ndarray:
    """10-битный limited-range код -> нит по SMPTE ST 2084."""
    e = np.clip((code.astype(np.float64) - 64) / 876.0, 0, 1)
    m1, m2, c1, c2, c3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875
    p = e ** (1 / m2)
    return 10000 * (np.maximum(p - c1, 0) / (c2 - c3 * p)) ** (1 / m1)


def lap_energy(y: np.ndarray) -> float:
    f = y.astype(np.float64)
    lap = (4 * f[1:-1, 1:-1] - f[:-2, 1:-1] - f[2:, 1:-1]
           - f[1:-1, :-2] - f[1:-1, 2:])
    return float(np.mean(np.abs(lap)))


CHROMA_B = 16          # блок в отсчётах цветности (= 32x32 пикселя при 4:2:0)


def small_chroma(su: np.ndarray, sv: np.ndarray, eu: np.ndarray, ev: np.ndarray
                 ) -> Tuple[float, float, int, int, int]:
    """Сохранность цвета МЕЛКИХ насыщенных деталей любого оттенка.

    VMAF и PSNR по кадру этого не видят: VMAF считается только по Y, а средний
    PSNR U/V тонет в фоне. Берём блоки 16x16 отсчётов цветности, где у источника
    3..20 точек с насыщенностью |(Cb,Cr)-512| > 30 (мелкая цветная деталь, не
    заливка), и считаем проекцию цвета энкода на цвет источника:
    1.0 — цвет сохранён, 0 — деталь посерела. Возвращает (медиана, p10,
    число блоков, x, y худшего блока в пикселях)."""
    cs = np.stack([su.astype(np.float64) - 512, sv.astype(np.float64) - 512])
    ce = np.stack([eu.astype(np.float64) - 512, ev.astype(np.float64) - 512])
    sat = np.hypot(cs[0], cs[1])
    B = CHROMA_B
    keep: List[Tuple[float, int, int]] = []
    for y in range(0, sat.shape[0] - B + 1, B):
        for x in range(0, sat.shape[1] - B + 1, B):
            m = sat[y:y + B, x:x + B] > 30
            if 3 <= m.sum() <= 20:
                s = cs[:, y:y + B, x:x + B][:, m]
                e = ce[:, y:y + B, x:x + B][:, m]
                keep.append((float((s * e).sum() / (s * s).sum()), x * 2, y * 2))
    if not keep:
        return float("nan"), float("nan"), 0, 0, 0
    vals = np.array([k[0] for k in keep])
    worst = min(keep)
    return (float(np.median(vals)), float(np.percentile(vals, 10)), len(keep),
            worst[1], worst[2])


def tile_psnr(a: np.ndarray, b: np.ndarray) -> Tuple[float, int, int]:
    h, w = a.shape
    th, tw = h // GRID_Y, w // GRID_X
    worst = (float("inf"), 0, 0)
    for ty in range(GRID_Y):
        for tx in range(GRID_X):
            sa = a[ty * th:(ty + 1) * th, tx * tw:(tx + 1) * tw]
            sb = b[ty * th:(ty + 1) * th, tx * tw:(tx + 1) * tw]
            p = psnr(sa, sb)
            if p < worst[0]:
                worst = (p, tx, ty)
    return worst


# --------------------------------------------------------------- main ------
def chroma_scan(a, w: int, h: int, step: int, top: int, gap: int) -> List[int]:
    """Пройти оба файла каждые step кадров и вернуть top кадров с худшей
    сохранностью цвета мелких деталей (p10 по блокам)."""
    res: List[Tuple[float, int]] = []
    for (ks, (_, su, sv)), (ke, (_, eu, ev)) in zip(scan_frames(a.src, step, w, h),
                                                    scan_frames(a.enc, step, w, h)):
        med, p10, n, _, _ = small_chroma(su, sv, eu, ev)
        if n >= 5:
            res.append((p10, ks))
    print(f"скан цвета: {len(res)} кадров с мелкими цветными деталями", flush=True)
    chosen: List[int] = []
    for _, k in sorted(res):
        if all(abs(k - c) >= gap for c in chosen):
            chosen.append(k)
            if len(chosen) == top:
                break
    return chosen


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--enc", type=Path, required=True)
    ap.add_argument("--vmaf", type=Path, help="покадровый VMAF (tsv/csv с колонкой vmaf)")
    ap.add_argument("--scenes", type=Path, help="по умолчанию <src>.scenes")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top", type=int, default=12, help="худших по VMAF")
    ap.add_argument("--min-gap", type=int, default=48, help="кадров между выбранными")
    ap.add_argument("--frames", default="", help="доп. кадры через запятую")
    ap.add_argument("--chroma-scan", type=int, default=0, metavar="STEP",
                    help="скан цвета мелких деталей каждые STEP кадров (0 = выкл)")
    ap.add_argument("--chroma-top", type=int, default=8)
    a = ap.parse_args(argv)

    a.out.mkdir(parents=True, exist_ok=True)
    scenes = read_scenes(a.scenes or Path(str(a.src) + ".scenes"))
    w, h, fps = probe(a.src)
    ew, eh, efps = probe(a.enc)
    if (ew, eh) != (w, h) or abs(efps - fps) > 1e-3:
        print(f"ОШИБКА: размер/fps различаются: {w}x{h}@{fps} vs {ew}x{eh}@{efps}")
        return 1
    v = read_vmaf(a.vmaf) if a.vmaf else []
    why: Dict[int, List[str]] = {}
    for k in (pick_worst(v, a.top, a.min_gap) if v else []):
        why.setdefault(k, []).append("VMAF")
    for k in (int(x) for x in a.frames.split(",") if x.strip()):
        why.setdefault(k, []).append("вручную")
    if a.chroma_scan:
        for k in chroma_scan(a, w, h, a.chroma_scan, a.chroma_top, a.min_gap):
            why.setdefault(k, []).append("цвет")
    frames = sorted(why)
    print(f"разбираю {len(frames)} кадров: {frames}", flush=True)

    rows: List[Dict] = []
    for k in frames:
        ey, eu, ev = grab_yuv(a.enc, k, fps, w, h)
        sy, su, sv = grab_yuv(a.src, k, fps, w, h)
        cands = {0: sy}
        cands.update({d: grab_y(a.src, k + d, fps, w, h) for d in (-1, 1) if k + d >= 0})
        scores = {d: psnr(s, ey) for d, s in cands.items()}
        p = scores[0]
        # Сдвиг на кадр в движении даёт разницу в десятки дБ (на склейках
        # E01: 47 против 18-23 дБ). Если сосед лучше всего на 1-3 дБ — кадр
        # почти статичен, зерно сглажено энкодом и «лучший сосед» случайно
        # скачет ±1: это шум сравнения, а не сдвиг.
        rival_d = max((d for d in scores if d != 0), key=scores.get, default=None)
        rival = scores[rival_d] if rival_d is not None else float("-inf")
        if p >= rival:
            align = "OK"
        elif rival - p < 3.0:
            align = "неразличимо (статика)"
        else:
            align = f"СДВИГ {rival_d:+d}"
        tp, tx, ty = tile_psnr(sy, ey)
        cmed, cp10, cn, cx, cy = small_chroma(su, sv, eu, ev)
        nits = pq_nits(sy)
        tw, th = w // GRID_X, h // GRID_Y
        stem = f"f{k:06d}"
        tonemap_png(a.src, k, fps, a.out / f"{stem}_src.png")
        tonemap_png(a.enc, k, fps, a.out / f"{stem}_enc.png")
        crop = f"{tw}:{th}:{tx * tw}:{ty * th}"
        tonemap_png(a.src, k, fps, a.out / f"{stem}_crop_src.png", crop)
        tonemap_png(a.enc, k, fps, a.out / f"{stem}_crop_enc.png", crop)
        if cn:
            S = 256                               # кроп вокруг худшего цветного блока
            ox, oy = min(max(cx + 16 - S // 2, 0), w - S), min(max(cy + 16 - S // 2, 0), h - S)
            cc = f"{S}:{S}:{ox}:{oy}"
            tonemap_png(a.src, k, fps, a.out / f"{stem}_chroma_src.png", cc + ",scale=iw*2:-1:flags=neighbor")
            tonemap_png(a.enc, k, fps, a.out / f"{stem}_chroma_enc.png", cc + ",scale=iw*2:-1:flags=neighbor")
        diff_png(sy, ey, a.out / f"{stem}_diff.png")
        sc = next((i for i, (s, e) in enumerate(scenes) if s <= k < e), None)
        row = dict(
            frame=k, t=f"{int(k / fps // 60)}:{k / fps % 60:05.2f}",
            vmaf=v[k] if k < len(v) else float("nan"), why="+".join(why[k]),
            scene=sc, pos=(k - scenes[sc][0]) if sc is not None else None,
            align=align, psnr=p, tile=f"({tx},{ty}) {tp:.1f}",
            nits_mean=float(nits.mean()), dark=float((nits < 5).mean()),
            detail=lap_energy(ey) / max(lap_energy(sy), 1e-9),
            cmed=cmed, cp10=cp10, cn=cn, cxy=f"({cx},{cy})", stem=stem)
        rows.append(row)
        print(f"  {k:>6} t={row['t']} [{row['why']}] vmaf {row['vmaf']:.2f} {align} "
              f"PSNR_Y {p:.2f} тайл {row['tile']} {row['nits_mean']:.1f} нит, "
              f"теней {row['dark']:.0%}, деталь {row['detail']:.2f}, "
              f"цвет мелк. {cmed:.0%}/{cp10:.0%} ({cn} бл., худший {row['cxy']})", flush=True)

    # --- отчёт ---
    head = [f"src: `{a.src.name}`  ", f"enc: `{a.enc.name}`  "]
    if v:
        head.append(f"VMAF кадров: {len(v)}, среднее {np.mean(v):.2f}, p1 "
                    f"{np.percentile(v, 1):.2f}, min {min(v):.2f}")
    md = ["# Разбор кадров энкода", ""] + head + ["",
          "Цвет мелк. = сохранность цвета мелких насыщенных деталей (медиана / p10 по блокам; "
          "1.0 — сохранён, 0 — посерел). VMAF считается только по яркости и этого не видит.", "",
          "| кадр | время | причина | VMAF | сцена/поз. | выравн. | PSNR Y | худший тайл | ср. нит | тени <5 нит | деталь | цвет мелк. |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['frame']} | {r['t']} | {r['why']} | {r['vmaf']:.2f} | {r['scene']}/{r['pos']} | "
                  f"{r['align']} | {r['psnr']:.2f} | {r['tile']} | {r['nits_mean']:.1f} | "
                  f"{r['dark']:.0%} | {r['detail']:.2f} | {r['cmed']:.0%} / {r['cp10']:.0%} |")
    (a.out / "report.md").write_text("\n".join(md) + "\n")

    def fig(src: str, cap: str) -> str:
        return f"<figure><img src='{src}'><figcaption>{cap}</figcaption></figure>"
    cards = []
    for r in rows:
        s = r["stem"]
        chroma = ""
        if r["cn"]:
            chroma = ("<div class=row>" + fig(f"{s}_chroma_src.png", f"источник, худший цветной блок {r['cxy']}, ×2")
                      + fig(f"{s}_chroma_enc.png", "энкод, тот же блок, ×2") + "</div>")
        cards.append(
            f"<section><h2>кадр {r['frame']} — {r['t']} — [{html.escape(r['why'])}] — VMAF {r['vmaf']:.2f} — "
            f"{html.escape(r['align'])}</h2><p>PSNR Y {r['psnr']:.2f} дБ · худший тайл "
            f"{r['tile']} · {r['nits_mean']:.1f} нит · теней {r['dark']:.0%} · деталь "
            f"{r['detail']:.2f} · <b>цвет мелких деталей {r['cmed']:.0%} / {r['cp10']:.0%}</b> ({r['cn']} блоков)</p>"
            + chroma
            + "<div class=row>" + fig(f"{s}_crop_src.png", "источник, худший по Y тайл 1:1")
            + fig(f"{s}_crop_enc.png", "энкод, тот же тайл") + "</div><div class=row>"
            + fig(f"{s}_src.png", "источник") + fig(f"{s}_enc.png", "энкод")
            + fig(f"{s}_diff.png", "|разница| Y ×8") + "</div></section>")
    (a.out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Разбор кадров</title><style>"
        "body{font:14px sans-serif;background:#111;color:#ddd;margin:16px}"
        ".row{display:flex;gap:8px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:300px}"
        "img{width:100%;height:auto;display:block;image-rendering:pixelated}section{margin-bottom:32px}</style>"
        "<h1>Разбор кадров энкода</h1><p>PNG тонмаплены PQ→SDR (hable) только для "
        "просмотра; метрики посчитаны по исходному 10-битному PQ.</p>"
        + "".join(cards))
    print(f"готово: {a.out / 'report.md'}, {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
