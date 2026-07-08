"""CSV с метриками энкода: строка на сцену + frame-weighted итоговая строка
("ИТОГО"). Перенесено дословно из legacy/encode_scenes.py:481-509
(D-13/D-15) — чистый файловый вывод, subprocess-шов не задействован."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Optional


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
