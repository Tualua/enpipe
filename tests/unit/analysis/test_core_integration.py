"""Фаза 9, сквозной быстрый тест чистого ядра: MET-01..05, CND-01/02/04/05,
RPT-01 (без subprocess/hardware).

Проверяются стыки модулей: метрики кадра -> строки модели -> отчёт ->
JSON/MD/HTML, а также слияние кандидатов из всех источников. Утверждения —
диапазоны и отношения, а не точные значения шума, поэтому смена генератора
numpy тест не ломает.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Tuple

import numpy as np

from enpipe.analysis.candidates import manual_candidates, merge_candidates, vmaf_candidates
from enpipe.analysis.config import AnalyzeConfig, build_thresholds
from enpipe.analysis.metrics import analyze_frame
from enpipe.analysis.model import (
    CHROMA_OK,
    ROW_ERROR,
    ROW_OK,
    AnalysisReport,
    FrameRow,
    RunMeta,
    STATE_ENABLED,
    STATE_REJECTED,
)
from enpipe.analysis.report import render_html, render_json, render_md, summarize
from enpipe.analysis.sources import (
    csv_candidates,
    parse_frames,
    parse_vmaf,
    read_metrics_csv,
)
from enpipe.encoding.metrics import write_metrics_csv

H, W = 256, 512


def _synthetic_pair(chroma_gain: float = 0.5, seed: int = 0) -> Tuple[tuple, tuple]:
    rng = np.random.default_rng(seed)
    sy = (400 + rng.integers(-40, 41, size=(H, W))).astype(np.uint16)
    su = np.full((H // 2, W // 2), 512, dtype=np.uint16)
    sv = np.full((H // 2, W // 2), 512, dtype=np.uint16)
    eu, ev = su.copy(), sv.copy()
    # 8 насыщенных точек в каждом из 8 блоков 16x16 цветности
    for by in (1, 5):
        for bx in (1, 3, 5, 7):
            y0, x0 = by * 16, bx * 16
            for k in range(8):
                y, x = y0 + k, x0 + k
                su[y, x] = 612
                eu[y, x] = int(512 + (612 - 512) * chroma_gain)
    ey = np.clip(
        sy.astype(np.int32) + rng.integers(-2, 3, size=(H, W)), 0, 1023
    ).astype(np.uint16)
    return (sy, su, sv), (ey, eu, ev)


def _csv_row(scene, start, end, ssim_y, psnr_y):
    return {
        "scene": scene, "start_frame": start, "end_frame": end,
        "frames": end - start, "seek": 0.0, "trim": 0.0, "encode_sec": 10.0,
        "fps": 0.0, "size_mb": 5.0, "ssim_all": ssim_y, "ssim_db": None,
        "psnr_avg": psnr_y, "ssim_y": ssim_y, "psnr_y": psnr_y,
    }


def _csv_rows():
    return {
        0: _csv_row(0, 0, 300, 0.99, 45.0),
        1: _csv_row(1, 300, 600, 0.90, 38.0),
        2: _csv_row(2, 600, 1000, 0.95, 41.0),
    }


def test_synthetic_pair_metrics():
    src, enc = _synthetic_pair()
    m = analyze_frame(*src, *enc, AnalyzeConfig())

    assert m.chroma.status == CHROMA_OK
    assert 0.4 <= m.chroma.median <= 0.6
    assert np.isfinite(m.psnr_y)
    assert m.delta_e_itp_mean > 0
    assert m.delta_e_itp_p99 >= m.delta_e_itp_mean
    t = m.worst_tile_c
    assert t.x >= 0 and t.y >= 0 and t.x + t.w <= W and t.y + t.h <= H


def test_identical_pair_is_lossless():
    src, _ = _synthetic_pair()
    m = analyze_frame(*src, *src, AnalyzeConfig())

    assert m.psnr_y == m.psnr_u == m.psnr_v == float("inf")
    assert m.chroma.median == 1.0
    assert m.delta_e_itp_mean == 0.0


def _build_report(tmp_path):
    cfg = AnalyzeConfig()
    src, enc = _synthetic_pair()
    metrics = analyze_frame(*src, *enc, cfg)

    frames, st_manual = parse_frames("10, 400", cfg)
    csv_path = tmp_path / "x.metrics.csv"
    write_metrics_csv(csv_path, _csv_rows())
    scenes, _ = read_metrics_csv(csv_path)
    csv_raw, st_csv = csv_candidates(scenes, cfg)
    _, st_bad = parse_vmaf("frame_num,vmaf\n1,90\n2,91\n", 1000)
    assert st_bad.state == STATE_REJECTED
    lines = ["frame_num,vmaf"] + [f"{i},{95.0 - (i % 7)}" for i in range(1000)]
    vmaf_values, st_vmaf = parse_vmaf("\n".join(lines), 1000)
    assert st_vmaf.state == STATE_ENABLED

    raw = manual_candidates(frames) + csv_raw + vmaf_candidates(vmaf_values, cfg)
    spans = [(s.start_frame, s.end_frame) for s in scenes]
    cands = merge_candidates(raw, spans, cfg)

    rows = [
        FrameRow(frame=c.frame, status=ROW_OK, sources=c.sources, scene=c.scene, metrics=metrics)
        for c in cands
    ]
    rows.append(FrameRow(frame=999, status=ROW_ERROR, error="кадр не извлечён"))
    report = AnalysisReport(
        meta=RunMeta(src_name="src.mkv", enc_name="enc.mkv", frame_count=1000),
        thresholds=build_thresholds(cfg),
        sources=(st_manual, st_csv, st_vmaf, st_bad),
        candidates=tuple(cands),
        frames=tuple(rows),
        summary=summarize(rows),
    )
    return cfg, cands, report


def test_sources_merge_into_candidates(tmp_path):
    _, cands, _ = _build_report(tmp_path)
    by_frame = {c.frame: c for c in cands}

    assert 10 in by_frame and 400 in by_frame
    assert all(c.sources for c in cands)
    assert "manual" in by_frame[10].sources


def test_full_report_renders_all_formats(tmp_path):
    cfg, _, report = _build_report(tmp_path)

    text = render_json(report)
    assert "Infinity" not in text and "NaN" not in text
    data = json.loads(text)
    assert data["schema_version"] == 1
    assert len(data["thresholds"]) == len(dataclasses.fields(cfg))

    md = render_md(report)
    assert "provisional" in md
    assert "отвергнут" in md

    html = render_html(report)
    assert '<meta charset="utf-8">' in html
    assert "<script" not in html


def test_identical_pair_json_has_inf_and_zero():
    cfg = AnalyzeConfig()
    src, _ = _synthetic_pair()
    m = analyze_frame(*src, *src, cfg)
    rows = [FrameRow(frame=1, status=ROW_OK, metrics=m)]
    report = AnalysisReport(
        meta=RunMeta(src_name="a", enc_name="b"),
        thresholds=build_thresholds(cfg),
        sources=(),
        candidates=(),
        frames=tuple(rows),
        summary=summarize(rows),
    )
    data = json.loads(render_json(report))
    metrics = data["frames"][0]["metrics"]
    assert metrics["psnr_y"] == "inf"
    assert metrics["delta_e_itp_mean"] == 0.0
