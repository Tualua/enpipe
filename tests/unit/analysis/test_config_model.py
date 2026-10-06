"""MET-05, RPT-01 (чистая логика, без subprocess): модель отчёта и конфиг
анализа — frozen-ность, дефолты, имена полей (будущие ключи report.json)."""

from __future__ import annotations

import dataclasses
import re

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


def test_error_row_without_metrics():
    row = m.FrameRow(frame=5, status=m.ROW_ERROR, error="не удалось извлечь")
    assert row.metrics is None
    assert row.error


@pytest.mark.parametrize("obj", _instances(), ids=lambda o: type(o).__name__)
def test_field_names_snake_case(obj):
    for f in dataclasses.fields(obj):
        assert re.match(r"^[a-z][a-z0-9_]*$", f.name), f.name
