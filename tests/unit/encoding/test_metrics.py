"""TEST-01 (чистая логика): write_metrics_csv — итоговая строка (frame-weighted
средние + суммы) и структура CSV. Без subprocess/hardware."""

from __future__ import annotations

import csv

from enpipe.encoding.metrics import write_metrics_csv


def _row(scene, frames, ssim_all, encode_sec, size_mb):
    return {
        "scene": scene, "start_frame": 0, "end_frame": frames, "frames": frames,
        "seek": 0.0, "trim": 0.0, "encode_sec": encode_sec, "fps": 0.0,
        "size_mb": size_mb, "ssim_all": ssim_all, "ssim_db": None,
        "psnr_avg": None, "ssim_y": None, "psnr_y": None,
    }


def test_write_metrics_csv_frame_weighted_total(tmp_path):
    rows = {0: _row(0, 100, 0.9, 10.0, 5.0), 1: _row(1, 300, 0.8, 30.0, 15.0)}
    out = tmp_path / "m.csv"

    total = write_metrics_csv(out, rows)

    # frame-weighted ssim mean: (100*0.9 + 300*0.8) / 400 = 0.825
    assert total["scene"] == "ИТОГО"
    assert total["frames"] == 400
    assert total["encode_sec"] == 40.0
    assert total["size_mb"] == 20.0
    assert total["ssim_all"] == 0.825
    # all-None metric column stays None (no frames counted)
    assert total["psnr_avg"] is None


def test_write_metrics_csv_file_structure(tmp_path):
    rows = {0: _row(0, 100, 0.9, 10.0, 5.0), 1: _row(1, 300, 0.8, 30.0, 15.0)}
    out = tmp_path / "m.csv"

    write_metrics_csv(out, rows)

    with out.open(newline="") as f:
        data = list(csv.DictReader(f))
    # 2 scene rows + ИТОГО row, ordered by scene index
    assert [r["scene"] for r in data] == ["0", "1", "ИТОГО"]
    assert data[-1]["frames"] == "400"


def test_write_metrics_csv_empty_rows(tmp_path):
    out = tmp_path / "m.csv"

    total = write_metrics_csv(out, {})

    assert total["frames"] == 0
    assert total["ssim_all"] is None
