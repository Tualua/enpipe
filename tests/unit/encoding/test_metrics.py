"""TEST-01 (чистая логика): write_metrics_csv — итоговая строка (frame-weighted
средние + суммы) и структура CSV. Без subprocess/hardware."""

from __future__ import annotations

import csv
import math

from enpipe.encoding.metrics import format_total_line, write_metrics_csv


def _row(scene, frames, ssim_all, encode_sec, size_mb, *, psnr_avg=None,
         psnr_y=None, ssim_db=None, ssim_y=None):
    return {
        "scene": scene, "start_frame": 0, "end_frame": frames, "frames": frames,
        "seek": 0.0, "trim": 0.0, "encode_sec": encode_sec, "fps": 0.0,
        "size_mb": size_mb, "ssim_all": ssim_all, "ssim_db": ssim_db,
        "psnr_avg": psnr_avg, "ssim_y": ssim_y, "psnr_y": psnr_y,
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


def _total(tmp_path, rows):
    return write_metrics_csv(tmp_path / "m.csv", {i: r for i, r in enumerate(rows)})


def test_psnr_total_is_mse_weighted(tmp_path):
    t = _total(tmp_path, [_row(0, 100, 1.0, 1, 1, psnr_avg=40.0, psnr_y=40.0),
                          _row(1, 300, 1.0, 1, 1, psnr_avg=50.0, psnr_y=50.0)])
    expect = -10 * math.log10((100 * 1e-4 + 300 * 1e-5) / 400)
    assert abs(t["psnr_avg"] - expect) < 1e-4
    assert abs(t["psnr_y"] - 44.88117) < 1e-4


def test_psnr_total_inf_chunk_and_all_inf(tmp_path):
    t = _total(tmp_path, [_row(0, 100, 1.0, 1, 1, psnr_avg=math.inf),
                          _row(1, 300, 1.0, 1, 1, psnr_avg=50.0)])
    expect = -10 * math.log10(300 * 1e-5 / 400)
    assert abs(t["psnr_avg"] - expect) < 1e-4
    t = _total(tmp_path, [_row(0, 100, 1.0, 1, 1, psnr_avg=math.inf),
                          _row(1, 300, 1.0, 1, 1, psnr_avg=math.inf)])
    assert math.isinf(t["psnr_avg"])


def test_nan_propagates(tmp_path):
    t = _total(tmp_path, [_row(0, 100, math.nan, 1, 1, psnr_avg=math.nan),
                          _row(1, 300, 0.9, 1, 1, psnr_avg=50.0)])
    assert math.isnan(t["psnr_avg"])
    assert math.isnan(t["ssim_all"])
    assert math.isnan(t["ssim_db"])


def test_ssim_db_derived_from_total_ssim(tmp_path):
    t = _total(tmp_path, [_row(0, 100, 0.9, 1, 1), _row(1, 300, 0.8, 1, 1)])
    assert abs(t["ssim_db"] - 7.56962) < 1e-4
    t = _total(tmp_path, [_row(0, 100, 1.0, 1, 1), _row(1, 300, 1.0, 1, 1)])
    assert math.isinf(t["ssim_db"])
    t = _total(tmp_path, [_row(0, 100, 1.05, 1, 1)])
    assert math.isnan(t["ssim_db"])
    t = _total(tmp_path, [_row(0, 100, None, 1, 1)])
    assert t["ssim_db"] is None


def test_csv_writes_inf_nan_as_text(tmp_path):
    out = tmp_path / "m.csv"
    write_metrics_csv(out, {0: _row(0, 100, 1.0, 1, 1, psnr_avg=math.inf,
                                    ssim_db=math.inf),
                            1: _row(1, 100, 1.0, 1, 1, psnr_avg=math.nan)})
    with out.open(newline="") as f:
        data = list(csv.DictReader(f))
    assert data[0]["psnr_avg"] == "inf" and data[0]["ssim_db"] == "inf"
    assert data[1]["psnr_avg"] == "nan"
    assert data[2]["psnr_avg"] == "nan" and data[2]["ssim_db"] == "inf"


def test_ssim_db_total_uses_unrounded_ssim(tmp_path):
    # WR-01: SSIM 0.999996 округляется до 1.0, но ssim_db итога обязан быть
    # конечным (сжатие с потерями), а не ложным inf.
    t = _total(tmp_path, [_row(0, 100, 0.999996, 1, 1)])
    assert math.isfinite(t["ssim_db"])
    assert abs(t["ssim_db"] - (-10 * math.log10(1 - 0.999996))) < 1e-3
    # одна сцена: ИТОГО ssim_db совпадает со значением из сцены
    t = _total(tmp_path, [_row(0, 100, 0.998990, 1, 1)])
    assert abs(t["ssim_db"] - (-10 * math.log10(1 - 0.998990))) < 1e-4


def test_partial_metric_coverage_total_is_nan(tmp_path):
    # IN-07: метрика есть не у всех сцен - итог nan, а не среднее по
    # подмножеству при frames по всем сценам.
    t = _total(tmp_path, [_row(0, 100, 0.9, 1, 1, psnr_avg=40.0, psnr_y=40.0,
                               ssim_y=0.9),
                          _row(1, 300, None, 1, 1)])
    assert t["frames"] == 400
    for key in ("ssim_all", "ssim_db", "psnr_avg", "ssim_y", "psnr_y"):
        assert math.isnan(t[key]), key


def test_full_metric_coverage_total_is_finite(tmp_path):
    t = _total(tmp_path, [_row(0, 100, 0.9, 1, 1, psnr_avg=40.0),
                          _row(1, 300, 0.8, 1, 1, psnr_avg=50.0)])
    assert math.isfinite(t["ssim_all"]) and math.isfinite(t["psnr_avg"])


# --- format_total_line: строка ИТОГО не должна падать ни при каких метриках --- #


def test_format_total_line_full():
    line = format_total_line({"ssim_all": 0.98765, "psnr_avg": 42.1,
                              "frames": 74, "size_mb": 12.3})
    assert "SSIM 0.98765" in line
    assert "PSNR 42.10dB" in line
    assert "74 кадров" in line
    assert "12 MB" in line


def test_format_total_line_psnr_missing():
    line = format_total_line({"ssim_all": 0.99, "psnr_avg": None,
                              "frames": 10, "size_mb": 1.0})
    assert "SSIM 0.99000" in line
    assert "PSNR н/д" in line
    assert "н/дdB" not in line


def test_format_total_line_ssim_missing():
    line = format_total_line({"ssim_all": None, "psnr_avg": 40.0,
                              "frames": 10, "size_mb": 1.0})
    assert line is not None
    assert "SSIM н/д" in line
    assert "PSNR 40.00dB" in line


def test_format_total_line_no_metrics_returns_none():
    assert format_total_line({"ssim_all": None, "psnr_avg": None,
                              "frames": 10, "size_mb": 1.0}) is None


def test_format_total_line_nan_inf():
    line = format_total_line({"ssim_all": math.nan, "psnr_avg": math.inf,
                              "frames": 10, "size_mb": 1.0})
    assert "nan" in line
    assert "inf" in line


def test_format_total_line_missing_keys():
    line = format_total_line({"ssim_all": 0.5})
    assert "SSIM 0.50000" in line
    assert "н/д" in line
    assert format_total_line({}) is None
