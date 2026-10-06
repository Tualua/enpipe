"""RPT-01, MET-05 (чистая логика): report.json, сводка, md/html из одной модели.

Без subprocess/hardware. Golden-файл фиксирует схему report.json v1 побайтно.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from pathlib import Path

import numpy as np
import pytest

from enpipe.analysis.config import AnalyzeConfig, build_thresholds
from enpipe.analysis.model import (
    CHROMA_NO_DETAILS,
    CHROMA_OK,
    ROW_ERROR,
    ROW_OK,
    SOURCE_CSV,
    SOURCE_MANUAL,
    SOURCE_SCAN,
    SOURCE_VMAF,
    STATE_ENABLED,
    STATE_NOT_REQUESTED,
    STATE_REJECTED,
    AnalysisReport,
    Candidate,
    ChromaDetail,
    ImageRef,
    ChromaTile,
    DetailTile,
    FrameMetrics,
    FrameRow,
    LumaTile,
    RunMeta,
    SourceStatus,
)
from enpipe.analysis.report import (
    SUMMARY_METRICS,
    render_html,
    render_json,
    render_md,
    summarize,
    to_jsonable,
    write_report,
)

GOLDEN = Path(__file__).parent / "golden" / "report_v1.json"


def _metrics(
    *,
    psnr_u: float = 41.0,
    p99: float = 3.5,
    chroma: ChromaDetail = None,
) -> FrameMetrics:
    if chroma is None:
        chroma = ChromaDetail(
            status=CHROMA_OK,
            n_blocks=12,
            median=0.88,
            p10=0.71,
            ratio=0.8,
            worst_value=0.5,
            worst_x=64,
            worst_y=128,
        )
    return FrameMetrics(
        psnr_y=40.5,
        psnr_u=psnr_u,
        psnr_v=42.25,
        worst_tile_y=LumaTile(x=0, y=256, w=256, h=256, psnr=35.5),
        worst_tile_c=ChromaTile(x=512, y=0, w=256, h=256, psnr_u=38.0, psnr_v=39.0, mse_uv=9.5),
        nits_mean=120.5,
        shadow_fraction=0.25,
        detail=0.9,
        worst_tile_detail=DetailTile(x=0, y=0, w=256, h=256, detail=0.75),
        delta_e_itp_mean=1.5,
        delta_e_itp_p99=p99,
        chroma=chroma,
    )


def _fixture_report() -> AnalysisReport:
    frames = (
        FrameRow(
            frame=100,
            status=ROW_OK,
            sources=(SOURCE_MANUAL, SOURCE_VMAF),
            scene=1,
            scene_pos=10,
            time_sec=4.171,
            vmaf=91.5,
            metrics=_metrics(psnr_u=float("inf")),
        ),
        FrameRow(
            frame=500,
            status=ROW_OK,
            sources=(SOURCE_CSV,),
            scene=2,
            scene_pos=5,
            time_sec=20.855,
            vmaf=95.0,
            metrics=_metrics(
                p99=float("nan"),
                chroma=ChromaDetail(status=CHROMA_NO_DETAILS, n_blocks=2),
            ),
        ),
        FrameRow(
            frame=900,
            status=ROW_ERROR,
            sources=(SOURCE_MANUAL,),
            error="ffmpeg: кадр 900 не извлечён",
        ),
    )
    return AnalysisReport(
        meta=RunMeta(
            src_name="src.mkv",
            enc_name="src.Encoded.mkv",
            width=3840,
            height=2160,
            fps=23.976,
            frame_count=1000,
        ),
        thresholds=build_thresholds(AnalyzeConfig()),
        sources=(
            SourceStatus(SOURCE_MANUAL, STATE_ENABLED, count=1),
            SourceStatus(
                SOURCE_VMAF,
                STATE_REJECTED,
                reason="VMAF отвергнут: база индекса 1, длина 3 ≠ 4",
            ),
            SourceStatus(
                SOURCE_CSV,
                STATE_ENABLED,
                notes=("колонка psnr_y пуста",),
                count=2,
            ),
            SourceStatus(SOURCE_SCAN, STATE_NOT_REQUESTED),
        ),
        candidates=(
            Candidate(frame=100, primary=SOURCE_MANUAL, sources=(SOURCE_MANUAL, SOURCE_VMAF), scene=1),
            Candidate(frame=500, primary=SOURCE_CSV, sources=(SOURCE_CSV,), tags=("psnr_y",), scene=2),
        ),
        frames=frames,
        summary=summarize(frames),
    )


# --------------------------------------------------------------------------- #
# to_jsonable
# --------------------------------------------------------------------------- #


def test_to_jsonable_inf_nan():
    assert to_jsonable(float("inf")) == "inf"
    assert to_jsonable(float("-inf")) == "-inf"
    assert to_jsonable(float("nan")) is None


def test_to_jsonable_numpy_scalars():
    f = to_jsonable(np.float32(1.5))
    assert f == 1.5 and type(f) is float
    i = to_jsonable(np.int64(3))
    assert i == 3 and type(i) is int
    assert to_jsonable(np.bool_(True)) is True


def test_to_jsonable_tuple_and_nested_dataclass():
    tile = LumaTile(x=0, y=0, w=256, h=256, psnr=float("inf"))
    assert to_jsonable(tile) == {"x": 0, "y": 0, "w": 256, "h": 256, "psnr": "inf"}
    assert to_jsonable((1, (2, 3))) == [1, [2, 3]]


def test_to_jsonable_numpy_in_dataclass_field():
    out = to_jsonable(FrameRow(frame=1, status=ROW_OK, vmaf=np.float64(90.5)))
    assert out["vmaf"] == 90.5 and type(out["vmaf"]) is float


def test_threshold_value_types_preserved():
    data = json.loads(render_json(_fixture_report()))
    by_name = {t["name"]: t["value"] for t in data["thresholds"]}
    assert by_name["chroma_block"] == 16 and type(by_name["chroma_block"]) is int
    assert by_name["shadow_nits"] == 5.0 and type(by_name["shadow_nits"]) is float
    assert re.search(r'"value": 5\.0\b', render_json(_fixture_report()))


# --------------------------------------------------------------------------- #
# render_json
# --------------------------------------------------------------------------- #


def test_render_json_strict():
    text = render_json(_fixture_report())
    data = json.loads(text)
    assert "Infinity" not in text and "NaN" not in text
    assert data["schema_version"] == 1
    assert text.endswith("\n")
    assert "база индекса" in text


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


def test_render_json_keys_snake_case():
    data = json.loads(render_json(_fixture_report()))
    for k in _all_keys(data):
        assert re.fullmatch(r"[a-z][a-z0-9_]*", k), k


def test_render_json_schema_keys_literal():
    data = json.loads(render_json(_fixture_report()))
    assert set(data) == {
        "schema_version",
        "meta",
        "thresholds",
        "sources",
        "candidates",
        "frames",
        "summary",
    }
    metrics_keys = {
        "psnr_y",
        "psnr_u",
        "psnr_v",
        "worst_tile_y",
        "worst_tile_c",
        "nits_mean",
        "shadow_fraction",
        "detail",
        "worst_tile_detail",
        "delta_e_itp_mean",
        "delta_e_itp_p99",
        "chroma",
    }
    frame_keys = {
        "frame",
        "status",
        "sources",
        "scene",
        "scene_pos",
        "time_sec",
        "vmaf",
        "metrics",
        "error",
        "alignment",
        "alignment_shift",
        "flags",
        "severity",
        "images",
    }
    for row in data["frames"]:
        assert set(row) == frame_keys
        if row["metrics"] is not None:
            assert set(row["metrics"]) == metrics_keys


# Число "provisional": true в golden = числу полей AnalyzeConfig (15);
# добавление/переименование порога — осознанное обновление golden через
# ENPIPE_UPDATE_GOLDEN=1.
def test_golden_report_v1():
    text = render_json(_fixture_report())
    if os.environ.get("ENPIPE_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_bytes(text.encode("utf-8"))
        pytest.skip("golden обновлён")
    assert GOLDEN.read_bytes() == text.encode("utf-8")


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #


def _row(frame=0, *, status=ROW_OK, p10=None, psnr_y=40.0, vmaf=None, chroma=None, metrics=True):
    if status == ROW_ERROR:
        return FrameRow(frame=frame, status=status, vmaf=vmaf, error="x")
    if not metrics:
        return FrameRow(frame=frame, status=status, vmaf=vmaf)
    if chroma is None:
        chroma = ChromaDetail(status=CHROMA_OK, n_blocks=9, median=p10, p10=p10, ratio=1.0)
    m = _metrics(chroma=chroma)
    m = dataclasses.replace(m, psnr_y=psnr_y)
    return FrameRow(frame=frame, status=status, vmaf=vmaf, metrics=m)


def _by(summary, name):
    return next(s for s in summary if s.metric == name)


def test_summarize_chroma_p10_skips_errors_and_no_details():
    frames = [
        _row(1, p10=0.5),
        _row(2, p10=0.7),
        _row(3, p10=0.9),
        _row(4, status=ROW_ERROR),
        _row(5, chroma=ChromaDetail(status=CHROMA_NO_DETAILS, n_blocks=1)),
    ]
    s = _by(summarize(frames), "chroma_p10")
    assert s.n == 3
    assert s.minimum == 0.5 and s.median == 0.7
    assert s.p10 == round(float(np.percentile([0.5, 0.7, 0.9], 10)), 6)
    assert _by(summarize(frames), "chroma_median").n == 3


def test_summarize_excludes_non_finite():
    frames = [
        _row(1, psnr_y=float("inf")),
        _row(2, psnr_y=40.0),
        _row(3, psnr_y=42.0),
        _row(4, psnr_y=float("-inf")),
    ]
    s = _by(summarize(frames), "psnr_y")
    assert s.n == 2 and s.minimum == 40.0


def test_summarize_empty_metric():
    s = _by(summarize([_row(1, psnr_y=float("inf"))]), "psnr_y")
    assert s.n == 0
    assert (s.minimum, s.p1, s.p5, s.p10, s.median) == (None,) * 5


def test_summarize_vmaf_needs_no_metrics():
    frames = [
        _row(1, metrics=False, vmaf=90.0),
        _row(2, status=ROW_ERROR, vmaf=50.0),
    ]
    s = _by(summarize(frames), "vmaf")
    assert s.n == 1 and s.minimum == 90.0


def test_summarize_order_and_count():
    assert tuple(s.metric for s in summarize([])) == SUMMARY_METRICS


# --------------------------------------------------------------------------- #
# render_md
# --------------------------------------------------------------------------- #


def _unescaped_pipes(line: str) -> int:
    return len(re.findall(r"(?<!\\)\|", line))


def test_md_structure():
    md = render_md(_fixture_report())
    assert "# Разбор кадров энкода" in md
    assert "src.mkv" in md and "src.Encoded.mkv" in md
    assert "## Пороги (provisional, не откалиброваны)" in md
    for t in build_thresholds(AnalyzeConfig()):
        assert t.name in md
    assert "отвергнут" in md and "база индекса" in md
    assert "## Кадры" in md and "## Сводка" in md


def test_md_chroma_no_details_and_percent():
    md = render_md(_fixture_report())
    assert "нет мелких цветных деталей" in md
    assert "88 % / 71 %" in md
    assert "inf" in md and "н/д" in md


def test_md_error_row_visible_and_padded():
    md = render_md(_fixture_report())
    lines = md.splitlines()
    header = next(ln for ln in lines if ln.startswith("| кадр | время"))
    err = next(ln for ln in lines if "ошибка: ffmpeg: кадр 900 не извлечён" in ln)
    assert _unescaped_pipes(err) == _unescaped_pipes(header)


def test_md_escapes_pipes_and_newlines():
    base = _fixture_report()
    rep = dataclasses.replace(
        base,
        meta=dataclasses.replace(base.meta, src_name="a|b.mkv"),
        sources=(
            SourceStatus(
                SOURCE_VMAF,
                STATE_REJECTED,
                reason="база индекса 1 | длина 3 ≠ 4\nвторая строка",
            ),
        ),
    )
    md = render_md(rep)
    assert "a\\|b.mkv" in md
    assert "база индекса 1 \\| длина 3 ≠ 4 вторая строка" in md
    src_header = next(ln for ln in md.splitlines() if ln.startswith("| источник |"))
    src_row = next(ln for ln in md.splitlines() if "вторая строка" in ln)
    assert _unescaped_pipes(src_row) == _unescaped_pipes(src_header)


def _empty_report() -> AnalysisReport:
    return AnalysisReport(
        meta=RunMeta(src_name="a.mkv", enc_name="b.mkv"),
        thresholds=(),
        sources=(),
        candidates=(),
        frames=(),
        summary=(),
    )


def test_empty_report_md_and_html():
    for text in (render_md(_empty_report()), render_html(_empty_report())):
        assert "None" not in text
        assert "нет" in text


# --------------------------------------------------------------------------- #
# render_html
# --------------------------------------------------------------------------- #


def test_html_structure():
    h = render_html(_fixture_report())
    assert h.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in h
    assert "Пороги (provisional, не откалиброваны)" in h
    assert "<script" not in h
    assert "нет мелких цветных деталей" in h
    assert "ошибка: ffmpeg: кадр 900 не извлечён" in h


def test_html_escapes_untrusted_strings():
    base = _fixture_report()
    row = dataclasses.replace(
        base.frames[0],
        flags=("<b>f</b>",),
        images=(ImageRef(kind="k", path='x" onerror="y', caption="<u>c</u>"),),
    )
    err_row = dataclasses.replace(base.frames[2], error="<i>boom</i>")
    rep = dataclasses.replace(
        base,
        meta=dataclasses.replace(base.meta, src_name='a&b "x" <i>.mkv'),
        sources=(
            SourceStatus(
                SOURCE_VMAF,
                STATE_REJECTED,
                reason="<img src=x onerror=alert(1)>",
                notes=("<s>n</s>",),
            ),
        ),
        candidates=(
            Candidate(frame=1, primary=SOURCE_MANUAL, sources=("<m>",), tags=("<t>",)),
        ),
        frames=(row, err_row),
    )
    h = render_html(rep)
    assert "a&amp;b &quot;x&quot; &lt;i&gt;.mkv" in h
    assert "&lt;img src=x onerror=alert(1)&gt;" in h
    for raw in ("<i>", "<img src=x", "<b>f", "<u>c", "<s>n", "<m>", "<t>", "<i>boom"):
        assert raw not in h
    assert 'src="x&quot; onerror=&quot;y"' in h


# --------------------------------------------------------------------------- #
# write_report
# --------------------------------------------------------------------------- #


def test_write_report_three_files(tmp_path):
    out = tmp_path / "out"
    rep = _fixture_report()
    write_report(rep, out)
    assert (out / "report.json").read_bytes() == render_json(rep).encode("utf-8")
    assert (out / "report.md").read_text(encoding="utf-8") == render_md(rep)
    assert (out / "index.html").read_text(encoding="utf-8") == render_html(rep)
