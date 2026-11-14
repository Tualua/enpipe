"""Синхронизация звука и видео в выходе `enpipe run` против полной серии (WR-01, 10.1-15).

Зачем: вырезка VC-1 с открытым GOP в начале теряет начальный B-кадр на декоде.
Если выход enpipe при этом сдвигает картинку относительно звука, это отдельная
находка. Скрипт только ЧИТАЕТ файлы и измеряет сдвиг, ничего не исправляет.

Эталон -- полная серия: кадр j показывается в `v0_full + j / fps`, где v0_full --
best_effort_timestamp_time первого кадра декода полной серии, fps -- avg_frame_rate.
Звук полной серии стоит на своих метках. Метки пакетов VC-1 в mkv идут в порядке
кодирования, поэтому момент кадра определяется по СОДЕРЖИМОМУ, через номер кадра
полной серии.

a) Звук: моно 8 кГц f32le, нормированная взаимная корреляция (БПФ numpy) первых
   20 с файла с окном полной серии cut_start ± 10 с -> T_a; D_a = T_a - a0_file.
b) Видео: первые 5 кадров файла и кадры полной серии round(cut_start*fps) ± 60
   (160x90 gray), минимум средней абсолютной разности -> j(0); требуется
   j(k) = j(0) + k и отношение лучшего ко второму лучшему < 0.5;
   D_v = (v0_full + j(0)/fps) - v0_file.
c) shift = D_v - D_a: положительный -- картинка в файле стоит РАНЬШЕ звука.
Строки `[sync] <файл>: …` и итог `[sync] ИТОГ: …`. Код возврата 0, если замер
выполнен (итог любой).

Запуск:
  uv run python scratch/open_gop_av_sync.py --full FULL --cut CUT --out OUT --cut-start SEC
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from enpipe.shared import proc as _proc

AR = 8000
W, H = 160, 90


def ffprobe_json(args: List[str]) -> dict:
    r = _proc.run(["ffprobe", "-v", "error", *args, "-of", "json"],
                  capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe: {r.stderr[:200]}")
    return json.loads(r.stdout)


def start_time(path: Path, sel: str) -> float:
    d = ffprobe_json(["-select_streams", sel, "-show_entries", "stream=start_time", str(path)])
    return float(d["streams"][0]["start_time"])


def first_frame_time(path: Path) -> float:
    d = ffprobe_json(["-select_streams", "v:0", "-read_intervals", "%+#8", "-show_frames",
                      "-show_entries", "frame=best_effort_timestamp_time", str(path)])
    # при чтении одного пакета декодер кадр не отдаёт (метка N/A) -- читаем 8 пакетов
    # и берём метку именно первого кадра декода
    return float(d["frames"][0]["best_effort_timestamp_time"])


def audio(path: Path, seconds: float) -> np.ndarray:
    r = _proc.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0:a:0",
                   "-t", f"{seconds}", "-ac", "1", "-af", f"aresample={AR}", "-f", "f32le", "-"],
                  capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"ffmpeg audio {path.name}: rc={r.returncode} {r.stderr[-200:]!r}")
    return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)


def frames_gray(path: Path, vf_head: str, count: int) -> np.ndarray:
    """count кадров 160x90 gray; vf_head -- фильтр отбора (может быть пустым)."""
    vf = (vf_head + "," if vf_head else "") + f"scale={W}:{H},format=gray"
    r = _proc.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0:v:0",
                   "-vf", vf, "-fps_mode", "passthrough", "-frames:v", str(count),
                   "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg video {path.name}: rc={r.returncode} {r.stderr[-200:]!r}")
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (W * H)
    return a[: n * W * H].reshape(n, H, W).astype(np.float64)


def ncc_lag(seg: np.ndarray, tpl: np.ndarray) -> Tuple[int, float, float]:
    """Нормированная корреляция шаблона по сегменту: (лаг, пик, отношение к 2-му максимуму)."""
    n = 1 << int(np.ceil(np.log2(seg.size + tpl.size)))
    cc = np.fft.irfft(np.fft.rfft(seg, n) * np.conj(np.fft.rfft(tpl, n)), n)[: seg.size - tpl.size + 1]
    cs = np.concatenate(([0.0], np.cumsum(seg * seg)))
    energy = cs[tpl.size:] - cs[: seg.size - tpl.size + 1]
    ncc = cc / np.sqrt(np.maximum(energy, 1e-12) * float(np.sum(tpl * tpl)))
    lag = int(np.argmax(ncc))
    peak = float(ncc[lag])
    mask = np.ones(ncc.size, dtype=bool)
    mask[max(0, lag - 40): lag + 41] = False  # ±5 мс при 8 кГц
    second = float(np.max(ncc[mask])) if mask.any() else 0.0
    return lag, peak, (peak / second if second > 1e-9 else float("inf"))


def measure(name: str, path: Path, fps: Fraction, v0_full: float, a0_full: float,
            full_audio: np.ndarray, full_frames: np.ndarray, first_j: int,
            cut_start: float) -> Tuple[Optional[float], str]:
    """Возвращает (shift в мс или None, причина inconclusive)."""
    reasons: List[str] = []
    # --- звук ---
    a0_file = start_time(path, "a:0")
    tpl = audio(path, 20.0)[: 20 * AR]
    lo = int((cut_start - 10 - a0_full) * AR)
    hi = int((cut_start + 10 - a0_full) * AR) + tpl.size
    lo = max(lo, 0)
    seg = full_audio[lo:hi]
    lag, peak, ratio = ncc_lag(seg, tpl)
    t_a = a0_full + (lo + lag) / AR
    d_a = t_a - a0_file
    print(f"[sync] {name}: звук: a0_file {a0_file:.6f}, T_a {t_a:.6f}, пик корреляции "
          f"{peak:.3f}, отношение ко 2-му максимуму {ratio:.1f}")
    if peak < 0.9 or ratio < 2:
        reasons.append(f"звук: пик {peak:.3f}, отношение {ratio:.1f}")
    # --- видео ---
    v0_file = first_frame_time(path)
    got = frames_gray(path, "", 5)
    if got.shape[0] < 5:
        raise RuntimeError(f"{name}: декодировано кадров {got.shape[0]} < 5")
    cost = np.array([[np.mean(np.abs(g - f)) for f in full_frames] for g in got])  # [k][j]
    js, ratios = [], []
    for k in range(5):
        order = np.argsort(cost[k])
        js.append(int(order[0]))
        ratios.append(float(cost[k][order[0]] / max(cost[k][order[1]], 1e-9)))
    j0 = js[0]
    consistent = all(js[k] == j0 + k for k in range(5))
    comb = np.array([sum(cost[k][j0 + k - 0] if 0 <= j0 + k < cost.shape[1] else 1e9
                         for k in range(5)) for j0 in range(cost.shape[1])])
    co = np.argsort(comb)
    comb_ratio = float(comb[co[0]] / max(comb[co[1]], 1e-9))
    print(f"[sync] {name}: видео: j(k) в окне {js}, отношения лучший/второй "
          f"{[round(x, 2) for x in ratios]}, согласованно j(k)=j(0)+k: "
          f"{'да' if consistent else 'нет'}, сводное отношение по 5 кадрам {comb_ratio:.2f}")
    if not consistent or max(ratios) >= 0.5:
        reasons.append(f"видео: согласованность {consistent}, макс. отношение {max(ratios):.2f}")
    frame_no = first_j + j0
    d_v = (v0_full + frame_no / float(fps)) - v0_file
    shift = d_v - d_a
    frame_ms = 1000.0 / float(fps)
    print(f"[sync] {name}: D_a {d_a * 1000:.1f} мс, D_v {d_v * 1000:.1f} мс, j0 {frame_no} "
          f"(кадр полной серии), v0_file {v0_file:.6f}, сдвиг видео относительно звука "
          f"{shift * 1000:.1f} мс ({shift * 1000 / frame_ms:.2f} кадра)")
    return (None if reasons else shift * 1000.0), "; ".join(reasons)


def main() -> int:
    ap = argparse.ArgumentParser(description="сдвиг звука относительно видео в выходе enpipe")
    ap.add_argument("--full", required=True, type=Path)
    ap.add_argument("--cut", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cut-start", required=True, type=float)
    ap.add_argument("--window", type=int, default=60)
    a = ap.parse_args()

    d = ffprobe_json(["-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", str(a.full)])
    fps = Fraction(d["streams"][0]["avg_frame_rate"])
    v0_full = first_frame_time(a.full)
    a0_full = start_time(a.full, "a:0")
    n0 = round(a.cut_start * float(fps))
    first_j = max(0, n0 - a.window)
    print(f"[sync] полная серия: fps {fps} ({float(fps):.5f}), v0_full {v0_full:.6f}, "
          f"a0_full {a0_full:.6f}, окно кадров [{first_j}, {n0 + a.window}]")
    full_audio = audio(a.full, a.cut_start + 40)
    full_frames = frames_gray(a.full, f"select=between(n\\,{first_j}\\,{n0 + a.window})",
                              2 * a.window + 1)
    print(f"[sync] полная серия: звук {full_audio.size / AR:.1f} с, кадров в окне {full_frames.shape[0]}")

    results = {}
    for tag, path in (("OUT", a.out), ("CUT", a.cut)):
        try:
            results[tag] = measure(f"{tag} {path.name}", path, fps, v0_full, a0_full,
                                   full_audio, full_frames, first_j, a.cut_start)
        except Exception as ex:
            results[tag] = (None, f"ошибка замера: {type(ex).__name__}: {ex}")
            print(f"[sync] {tag} {path.name}: ОШИБКА {type(ex).__name__}: {ex}")
    out_shift, out_why = results["OUT"]
    cut_shift, cut_why = results["CUT"]
    half = 500.0 / float(fps)
    if out_shift is None:
        print(f"[sync] ИТОГ: inconclusive ({out_why})")
    elif abs(out_shift) <= half:
        print(f"[sync] ИТОГ: сдвига нет (|сдвиг выхода| {abs(out_shift):.1f} мс ≤ половины "
              f"кадра, {half:.1f} мс)")
    else:
        print(f"[sync] ИТОГ: СДВИГ {out_shift:.1f} мс в выходе enpipe")
    cut_txt = f"{cut_shift:.1f} мс" if cut_shift is not None else f"inconclusive ({cut_why})"
    print(f"[sync] справка: сдвиг самой вырезки-источника {cut_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
