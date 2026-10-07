"""MET-05, RPT-01 (чистая логика, без subprocess): модель отчёта и конфиг
анализа — frozen-ность, дефолты, имена полей (будущие ключи report.json)."""

from __future__ import annotations

import dataclasses
import re
from fractions import Fraction

import pytest

from enpipe.analysis import model as m


def _tile_y() -> m.LumaTile:
    return m.LumaTile(x=0, y=0, w=256, h=256, psnr=40.0)


def _tile_c() -> m.ChromaTile:
    return m.ChromaTile(x=0, y=0, w=128, h=128, psnr_u=40.0, psnr_v=41.0, mse_uv=1.0)


def _chroma() -> m.ChromaDetail:
    return m.ChromaDetail(status=m.CHROMA_NO_DETAILS, n_blocks=0)


def _metrics() -> m.FrameMetrics:
    return m.FrameMetrics(
        psnr_y=40.0,
        psnr_u=41.0,
        psnr_v=42.0,
        worst_tile_y=_tile_y(),
        worst_tile_c=_tile_c(),
        nits_mean=100.0,
        shadow_fraction=0.1,
        detail=None,
        worst_tile_detail=None,
        delta_e_itp_mean=1.0,
        delta_e_itp_p99=2.0,
        chroma=_chroma(),
    )


def _report() -> m.AnalysisReport:
    return m.AnalysisReport(
        meta=m.RunMeta(src_name="a.mkv", enc_name="b.mkv"),
        thresholds=(),
        sources=(),
        candidates=(),
        frames=(),
        summary=(),
    )


def _instances():
    return [
        _chroma(),
        _tile_y(),
        _tile_c(),
        m.DetailTile(x=0, y=0, w=256, h=256, detail=0.5),
        _metrics(),
        m.SourceStatus(source=m.SOURCE_CSV, state=m.STATE_ENABLED),
        m.RawCandidate(frame=1, source=m.SOURCE_MANUAL, rank=0.0),
        m.Candidate(frame=1, primary=m.SOURCE_MANUAL, sources=(m.SOURCE_MANUAL,)),
        m.ImageRef(kind="crop", path="a.png", caption="c"),
        m.FrameRow(frame=1, status=m.ROW_OK),
        m.RunMeta(src_name="a.mkv", enc_name="b.mkv"),
        m.Threshold(name="top", value=40),
        m.PercentileSummary(metric="psnr_y", n=0),
        m.StreamInfo(
            name="a.mkv", format_name="matroska", codec_name="hevc", width=3840,
            height=1600, pix_fmt="yuv420p10le", avg_frame_rate=Fraction(24000, 1001),
            start_time=0.0, color_range="tv", color_space="bt2020nc",
            color_transfer="smpte2084", color_primaries="bt2020",
        ),
        m.PairVerdict(ok=True),
        m.PointAlignment(enc_frame=0, verdict=m.ALIGN_ALIGNED),
        m.FileAlignment(verdict=m.ALIGN_ALIGNED),
        _report(),
    ]


@pytest.mark.parametrize("obj", _instances(), ids=lambda o: type(o).__name__)
def test_dataclasses_frozen(obj):
    first = dataclasses.fields(obj)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, first, getattr(obj, first))


def test_schema_version_default():
    assert _report().schema_version == 1
    assert m.SCHEMA_VERSION == 1


def test_source_priority_order():
    p = m.SOURCE_PRIORITY
    assert p[m.SOURCE_MANUAL] < p[m.SOURCE_VMAF] < p[m.SOURCE_CSV] < p[m.SOURCE_SCAN]


def test_report_new_fields_defaults():
    r = _report()
    assert r.status == m.REPORT_OK == "ok"
    assert r.refusal_reasons == () and r.alignment is None
    assert r.schema_version == 1
    assert r.meta.offset is None and r.meta.offset_source is None
    assert r.meta.notes == ()


def test_stream_info_field_order_last_default_none():
    flds = dataclasses.fields(m.StreamInfo)
    assert flds[-1].name == "field_order"
    si = [o for o in _instances() if isinstance(o, m.StreamInfo)][0]
    assert si.field_order is None and si.has_dovi is False and si.dv_profile is None


def test_error_row_without_metrics():
    row = m.FrameRow(frame=5, status=m.ROW_ERROR, error="не удалось извлечь")
    assert row.metrics is None
    assert row.error


@pytest.mark.parametrize("obj", _instances(), ids=lambda o: type(o).__name__)
def test_field_names_snake_case(obj):
    for f in dataclasses.fields(obj):
        assert re.match(r"^[a-z][a-z0-9_]*$", f.name), f.name


# --------------------------------------------------------------------------- #
# config.py
# --------------------------------------------------------------------------- #

from enpipe.analysis import config as c  # noqa: E402


def test_config_defaults():
    cfg = c.AnalyzeConfig()
    assert (cfg.chroma_block, cfg.chroma_sat_thr) == (16, 30.0)
    assert (cfg.chroma_min_pts, cfg.chroma_max_pts, cfg.min_chroma_blocks) == (3, 20, 5)
    assert (cfg.tile_y, cfg.tile_c) == (256, 128)
    assert (cfg.shadow_nits, cfg.detail_eps) == (5.0, 1e-9)
    assert (cfg.min_gap, cfg.top, cfg.per_scene_quota) == (48, 40, 2)
    assert (cfg.csv_worst_n, cfg.vmaf_worst_n, cfg.max_frames_range) == (10, 12, 10000)
    assert (cfg.align_margin_db, cfg.align_window, cfg.align_points) == (3.0, 3, 5)
    assert (cfg.align_min_aligned, cfg.align_retry_max, cfg.align_retry_step) == (2, 3, 48)
    assert cfg.fps_rel_tol == 5e-4
    assert (cfg.vfr_gap_lo, cfg.vfr_gap_hi, cfg.vfr_gap_fraction) == (0.8, 1.25, 0.01)


def test_build_thresholds_defaults():
    cfg = c.AnalyzeConfig()
    th = c.build_thresholds(cfg)
    assert len(th) == 25
    flds = dataclasses.fields(c.AnalyzeConfig)
    assert len(th) == len(flds)
    assert [t.name for t in th] == [f.name for f in flds]
    assert all(t.provisional is True for t in th)
    assert all(t.value == getattr(cfg, t.name) for t in th)


def test_build_thresholds_reflects_args():
    th = {t.name: t.value for t in c.build_thresholds(c.AnalyzeConfig(tile_y=512, tile_c=256))}
    assert th["tile_y"] == 512 and th["tile_c"] == 256


def test_build_thresholds_distinct_values_and_types():
    cfg = c.AnalyzeConfig(
        chroma_block=8, chroma_sat_thr=31.5, chroma_min_pts=4, chroma_max_pts=19,
        min_chroma_blocks=6, tile_y=258, tile_c=130, shadow_nits=5.5,
        detail_eps=2e-9, min_gap=49, top=41, per_scene_quota=3, csv_worst_n=11,
        vmaf_worst_n=13, max_frames_range=10001, align_margin_db=3.5,
        align_window=4, align_points=6, align_min_aligned=3, align_retry_max=2,
        align_retry_step=24, fps_rel_tol=1e-3, vfr_gap_lo=0.7, vfr_gap_hi=1.3,
        vfr_gap_fraction=0.02,
    )
    for t in c.build_thresholds(cfg):
        v = getattr(cfg, t.name)
        assert t.value == v and type(t.value) is type(v), t.name


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tile_y": 255},
        {"tile_c": 0},
        {"tile_y": -2},
        {"chroma_min_pts": 10, "chroma_max_pts": 5},
        {"chroma_min_pts": 0},
        {"chroma_block": 0},
        {"min_chroma_blocks": 0},
        {"min_gap": -1},
        {"top": 0},
        {"per_scene_quota": 0},
        {"csv_worst_n": 0},
        {"vmaf_worst_n": 0},
        {"max_frames_range": 0},
        {"align_margin_db": 0.0},
        {"align_margin_db": -1.0},
        {"align_window": 0},
        {"align_window": 9},
        {"align_points": 0},
        {"align_min_aligned": 0},
        {"align_min_aligned": 6},
        {"align_retry_max": -1},
        {"align_retry_step": 0},
        {"fps_rel_tol": 0.0},
        {"fps_rel_tol": 1.0},
        {"vfr_gap_lo": 0.0},
        {"vfr_gap_lo": 1.0},
        {"vfr_gap_hi": 1.0},
        {"vfr_gap_fraction": 0.0},
        {"vfr_gap_fraction": 1.0},
    ],
)
def test_invalid_config_raises(kwargs):
    with pytest.raises(c.AnalysisError):
        c.AnalyzeConfig(**kwargs)


def test_itp_strip_rows_even_positive():
    assert isinstance(c.ITP_STRIP_ROWS, int)
    assert c.ITP_STRIP_ROWS > 0 and c.ITP_STRIP_ROWS % 2 == 0


def test_perf_constants_not_thresholds():
    assert (c.DEFAULT_JOBS, c.DECODE_THREADS, c.NICE_LEVEL) == (2, 2, 10)
    assert c.MAX_GRAB_FRAMES == 2 * c.ALIGN_WINDOW_MAX + 2 == 18
    assert c.OFFSET_HINTS_MAX == 5
    names = {f.name.lower() for f in dataclasses.fields(c.AnalyzeConfig)}
    for const in ("DEFAULT_JOBS", "DECODE_THREADS", "NICE_LEVEL",
                  "ALIGN_WINDOW_MAX", "MAX_GRAB_FRAMES", "OFFSET_HINTS_MAX"):
        assert const.lower() not in names


def test_matrix_sanity():
    assert all(sum(row) == 4096 for row in c.RGB_TO_LMS)
    assert c.LMS_TO_ICTCP[0] == (2048, 2048, 0)
    assert sum(c.LMS_TO_ICTCP[1]) == 0 and sum(c.LMS_TO_ICTCP[2]) == 0
