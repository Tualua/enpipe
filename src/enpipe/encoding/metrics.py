"""CSV с метриками энкода: строка на сцену + frame-weighted итоговая строка
("ИТОГО"). Чистый файловый вывод, subprocess-шов не задействован.

Итог НЕ «дословно legacy» для ssim_db/psnr_avg/psnr_y. Набор и порядок колонок
CSV прежние; меняются только значения ИТОГО этих трёх метрик (на конечных данных
— на доли дБ):
 1. простое среднее дБ математически неверно и ломается на inf (inf поглощает
    всё);
 2. PSNR агрегируется через MSE (frame-weighted) — так же qsvencc сам считает
    Avg по плоскостям (inf/65.724102/inf -> 73.505614), т.е. итог согласован с
    покадровой природой метрики и с внутричанковым Avg;
 3. SSIM-дБ — монотонная функция SSIM, поэтому выводится из итогового
    взвешенного SSIM, а не усредняется;
 4. nan распространяется в итог — это сигнал битой сборки/данных, а не повод
    молча его пропустить.
csv.DictWriter пишет float inf/nan как `inf`/`nan`, отдельный формат не нужен."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, Optional


def _round(v: float) -> float:
    """Округляет только конечные значения; inf/nan остаются как есть."""
    return round(v, 5) if math.isfinite(v) else v


def _vals(ordered: list, key: str) -> list:
    return [(r["frames"], r[key]) for r in ordered if r.get(key) is not None]


def _wmean(ordered: list, key: str) -> Optional[float]:
    """Frame-weighted среднее (SSIM); nan в любом чанке -> nan."""
    vals = _vals(ordered, key)
    fr = sum(f for f, _ in vals)
    if not fr:
        return None
    if any(math.isnan(v) for _, v in vals):
        return float("nan")
    return _round(sum(f * v for f, v in vals) / fr)


def _psnr_total(ordered: list, key: str) -> Optional[float]:
    """PSNR итога через frame-weighted MSE (пик сокращается; inf -> MSE 0)."""
    vals = _vals(ordered, key)
    fr = sum(f for f, _ in vals)
    if not fr:
        return None
    if any(math.isnan(v) for _, v in vals):
        return float("nan")
    mse = sum(f * (0.0 if math.isinf(v) else 10 ** (-v / 10)) for f, v in vals) / fr
    return float("inf") if mse == 0 else _round(-10 * math.log10(mse))


def _ssim_db_total(ssim_all: Optional[float]) -> Optional[float]:
    """SSIM-дБ итога выводится из итогового SSIM: -10*log10(1 - SSIM)."""
    if ssim_all is None:
        return None
    if math.isnan(ssim_all) or ssim_all > 1:
        return float("nan")
    if ssim_all == 1:
        return float("inf")
    return _round(-10 * math.log10(1 - ssim_all))


def write_metrics_csv(path: Path, rows: Dict[int, dict]) -> dict:
    """Пишет CSV: строка на сцену + итоговая (frame-weighted среднее метрик,
    суммы кадров/времени/размера; PSNR — через MSE, ssim_db — из итогового SSIM).
    Возвращает итоговую строку для лога."""
    fields = ["scene", "start_frame", "end_frame", "frames", "seek", "trim",
              "encode_sec", "fps", "size_mb",
              "ssim_all", "ssim_db", "psnr_avg", "ssim_y", "psnr_y"]
    ordered = [rows[i] for i in sorted(rows)]

    ssim_all = _wmean(ordered, "ssim_all")
    total = {
        "scene": "ИТОГО",
        "frames": sum(r["frames"] for r in ordered),
        "encode_sec": round(sum(r["encode_sec"] for r in ordered), 1),
        "size_mb": round(sum(r["size_mb"] for r in ordered), 1),
        "ssim_all": ssim_all, "ssim_db": _ssim_db_total(ssim_all),
        "psnr_avg": _psnr_total(ordered, "psnr_avg"),
        "ssim_y": _wmean(ordered, "ssim_y"),
        "psnr_y": _psnr_total(ordered, "psnr_y"),
    }
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ordered:
            w.writerow(r)
        w.writerow(total)
    return total
