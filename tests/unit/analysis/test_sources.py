"""CND-01/02/04: ридеры источников кандидатов + сторожа совместимости с encoding/.
Без subprocess/hardware."""

from __future__ import annotations

import math
import time

import pytest

from enpipe.analysis import sources
from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import (
    STATE_ENABLED,
    STATE_NOT_REQUESTED,
    STATE_REJECTED,
    STATE_UNAVAILABLE,
)
from enpipe.analysis.sources import (
    MetricsScene,
    csv_candidates,
    parse_frames,
    parse_metrics_csv,
    parse_scenes,
    parse_vmaf,
    read_metrics_csv,
    read_scenes_file,
    read_vmaf,
)
from enpipe.encoding.metrics import write_metrics_csv
from enpipe.encoding.scenes_io import _SCENE_RE as ENC_SCENE_RE

CFG = AnalyzeConfig()


def _row(scene, start, end, *, ssim_y=None, psnr_y=None):
    frames = end - start
    return {
        "scene": scene, "start_frame": start, "end_frame": end, "frames": frames,
        "seek": 0.0, "trim": 0.0, "encode_sec": 1.0, "fps": 1.0, "size_mb": 1.0,
        "ssim_all": 0.9, "ssim_db": None, "psnr_avg": None,
        "ssim_y": ssim_y, "psnr_y": psnr_y,
    }


def _ms(i, s, e, ssim=None, psnr=None):
    return MetricsScene(i, s, e, ssim, psnr)


# ------------------------------- --frames ---------------------------------- #


def test_frames_empty_not_requested():
    for spec in ("", "  "):
        frames, st = parse_frames(spec, CFG)
        assert frames == [] and st.state == STATE_NOT_REQUESTED


def test_frames_singles_and_ranges():
    frames, st = parse_frames("100,200-203, 300", CFG)
    assert frames == [100, 200, 201, 202, 203, 300]
    assert st.state == STATE_ENABLED and st.count == 6


def test_frames_dedupe_sorted():
    assert parse_frames("5,3,5,4-6", CFG)[0] == [3, 4, 5, 6]


def test_frames_spaces_in_range():
    assert parse_frames(" 100 - 102 ,7", CFG)[0] == [7, 100, 101, 102]


@pytest.mark.parametrize("spec", ["abc", "-5", "10-5", "1,,2", "1.5", "3-"])
def test_frames_garbage_rejected(spec):
    frames, st = parse_frames(spec, CFG)
    assert frames == [] and st.state == STATE_REJECTED and st.reason


def test_frames_garbage_reason_has_fragment():
    assert "abc" in parse_frames("1,abc", CFG)[1].reason


def test_frames_huge_range_rejected_fast():
    t0 = time.monotonic()
    frames, st = parse_frames("0-999999999", CFG)
    assert time.monotonic() - t0 < 0.5
    assert frames == [] and st.state == STATE_REJECTED
    assert "max_frames_range" in st.reason


def test_frames_sum_of_ranges_over_limit():
    _, st = parse_frames("0-6000,10000-16000", CFG)
    assert st.state == STATE_REJECTED


# ------------------------------- .scenes ----------------------------------- #


def test_scenes_guard_pattern_matches_encoding():
    assert sources._SCENE_RE.pattern == ENC_SCENE_RE.pattern


def test_parse_scenes_format():
    text = (
        "scene 0000 frames [0, 100) 0.000 .. 4.170\n"
        "garbage\n"
        "scene 0001 frames [100, 250) 4.170 .. 10.4\n"
    )
    assert parse_scenes(text) == [(0, 100), (100, 250)]
    assert parse_scenes("") == []


def test_read_scenes_file_missing(tmp_path):
    assert read_scenes_file(tmp_path / "nope.scenes") == []


# ------------------------------- CSV метрик -------------------------------- #


def _write_four(tmp_path):
    rows = {
        0: _row(0, 0, 100, ssim_y=0.9, psnr_y=40.0),
        1: _row(1, 100, 250),
        2: _row(2, 250, 300, psnr_y=float("inf")),
        3: _row(3, 300, 301, ssim_y=float("nan")),
    }
    out = tmp_path / "m.csv"
    write_metrics_csv(out, rows)
    return out


def test_csv_round_trip_with_write_metrics_csv(tmp_path):
    scenes, st = read_metrics_csv(_write_four(tmp_path))
    assert st.state == STATE_ENABLED
    assert [(s.scene, s.start_frame, s.end_frame) for s in scenes] == [
        (0, 0, 100), (1, 100, 250), (2, 250, 300), (3, 300, 301)
    ]
    assert scenes[0].ssim_y == 0.9 and scenes[0].psnr_y == 40.0
    assert scenes[1].ssim_y is None and scenes[1].psnr_y is None
    assert scenes[2].psnr_y == math.inf and scenes[2].ssim_y is None
    assert math.isnan(scenes[3].ssim_y)
    assert isinstance(scenes[0].start_frame, int)


def test_csv_missing_column_rejected():
    _, st = parse_metrics_csv("scene,start_frame,end_frame,psnr_y\n0,0,10,40\n")
    assert st.state == STATE_REJECTED and "ssim_y" in st.reason
    _, st = parse_metrics_csv("scene,end_frame,ssim_y,psnr_y\n")
    assert st.state == STATE_REJECTED and "start_frame" in st.reason


def test_csv_bad_value_line_numbers():
    head = "scene,start_frame,end_frame,ssim_y,psnr_y\n"
    _, st = parse_metrics_csv(head + "0,0,10,,\n1,xx,20,,\n")
    assert st.state == STATE_REJECTED and "строка 3" in st.reason
    body = "0,0,10,,\n" * 4 + "9,zz,5,,\n"
    _, st = parse_metrics_csv(head + body)
    assert "строка 6" in st.reason


def test_csv_missing_file_and_bom(tmp_path):
    scenes, st = read_metrics_csv(tmp_path / "no.csv")
    assert scenes == [] and st.state == STATE_UNAVAILABLE
    p = tmp_path / "b.csv"
    p.write_bytes(
        b"\xef\xbb\xbfscene,start_frame,end_frame,ssim_y,psnr_y\n0,0,10,0.5,30\n"
    )
    scenes, st = read_metrics_csv(p)
    assert st.state == STATE_ENABLED and len(scenes) == 1


def test_csv_candidates_middle_and_tags():
    scenes = [
        _ms(0, 0, 100, 0.5, 30.0),
        _ms(1, 100, 101, 0.9, 40.0),
        _ms(2, 200, 300, 0.7, 20.0),
    ]
    raw, st = csv_candidates(scenes, AnalyzeConfig(csv_worst_n=2))
    assert st.state == STATE_ENABLED
    by_frame = {c.frame: c for c in raw}
    assert set(by_frame) == {50, 250}
    assert by_frame[50].tags == ("psnr_y", "ssim_y")
    assert by_frame[250].tags == ("psnr_y", "ssim_y")
    assert by_frame[50].rank == 0.0 and by_frame[250].rank == 0.0
    assert [c.frame for c in raw] == [50, 250]  # сортировка по (rank, frame)


def test_csv_candidates_one_frame_scene_uses_start():
    raw, _ = csv_candidates([_ms(0, 7, 8, 0.1, 10.0)], CFG)
    assert [c.frame for c in raw] == [7]


def test_csv_candidates_tie_by_start_frame():
    scenes = [_ms(0, 500, 510, 0.5, None), _ms(1, 0, 10, 0.5, None)]
    raw, _ = csv_candidates(scenes, AnalyzeConfig(csv_worst_n=1))
    assert [c.frame for c in raw] == [5]


def test_csv_candidates_excludes_nonfinite():
    scenes = [
        _ms(0, 0, 10, None, 20.0),
        _ms(1, 10, 20, math.nan, 25.0),
        _ms(2, 20, 30, 0.9, math.inf),
        _ms(3, 30, 40, 0.8, -math.inf),
        _ms(4, 40, 50, math.inf, 30.0),
    ]
    raw, st = csv_candidates(scenes, AnalyzeConfig(csv_worst_n=10))
    ssim_scenes = {c.frame for c in raw if "ssim_y" in c.tags}
    assert ssim_scenes == {25, 35}  # только конечные 0.9 и 0.8
    psnr_scenes = {c.frame for c in raw if "psnr_y" in c.tags}
    assert psnr_scenes == {5, 15, 45}  # inf не попадают, ровно 3 конечных


def test_csv_candidates_mixed_inf_and_finite_top_short():
    scenes = [_ms(0, 0, 10, None, 1.0), _ms(1, 10, 20, None, 2.0)] + [
        _ms(i, i * 10, i * 10 + 10, None, math.inf) for i in range(2, 5)
    ]
    raw, st = csv_candidates(scenes, AnalyzeConfig(csv_worst_n=10))
    assert sum(1 for c in raw if "psnr_y" in c.tags) == 2
    assert st.state == STATE_ENABLED
    assert any("нет конечных значений" in n for n in st.notes)  # колонка ssim_y


def test_csv_candidates_all_inf_psnr_is_empty_column():
    scenes = [_ms(0, 0, 10, 0.5, math.inf), _ms(1, 10, 20, 0.6, math.inf)]
    raw, st = csv_candidates(scenes, CFG)
    assert st.state == STATE_ENABLED
    assert all("psnr_y" not in c.tags for c in raw)
    assert any("колонка psnr_y: нет конечных значений" in n for n in st.notes)


def test_csv_candidates_all_empty_unavailable():
    scenes = [_ms(0, 0, 10, None, math.inf), _ms(1, 10, 20, None, None)]
    raw, st = csv_candidates(scenes, CFG)
    assert raw == [] and st.state == STATE_UNAVAILABLE
    assert "метрики не считались" in st.reason


# --------------------------------- VMAF ------------------------------------ #


def test_vmaf_tsv_decimal_comma():
    vals, st = parse_vmaf("frame\tvmaf\n0\t93,5\n1\t88,25\n2\t90\n", 3)
    assert vals == [93.5, 88.25, 90.0]
    assert st.state == STATE_ENABLED and st.count == 3


def test_vmaf_csv_header_case():
    vals, _ = parse_vmaf("Frame,VMAF\n0,93.5\n1,88.0\n", 2)
    assert vals == [93.5, 88.0]


def test_vmaf_csv_quoted_decimal_comma():
    vals, _ = parse_vmaf('frame,vmaf\n0,"93,5"\n1,"88,0"\n', 2)
    assert vals == [93.5, 88.0]


def test_vmaf_base_index_one():
    vals, st = parse_vmaf("frame,vmaf\n1,90\n2,91\n3,92\n", 3)
    assert vals is None and st.state == STATE_REJECTED
    assert "база индекса 1" in st.reason


def test_vmaf_base_one_and_length():
    _, st = parse_vmaf("frame,vmaf\n1,90\n2,91\n3,92\n", 4)
    assert "база индекса 1, длина 3 ≠ 4" in st.reason


def test_vmaf_length_mismatch_without_frame_column():
    vals, st = parse_vmaf("vmaf\n90\n91\n92\n", 4)
    assert vals is None and "длина 3 ≠ 4" in st.reason


def test_vmaf_frames_not_consecutive():
    _, st = parse_vmaf("frame,vmaf\n0,90\n1,91\n3,92\n", 3)
    assert st.state == STATE_REJECTED and "номера кадров не подряд" in st.reason


def test_vmaf_no_frame_column_ok_with_note():
    vals, st = parse_vmaf("vmaf\n90\n91\n", 2)
    assert vals == [90.0, 91.0] and st.state == STATE_ENABLED
    assert "колонка кадра отсутствует, база индекса не проверена" in st.notes


def test_vmaf_no_vmaf_column_and_empty():
    _, st = parse_vmaf("frame,score\n0,1\n", 1)
    assert st.state == STATE_REJECTED and "нет колонки vmaf" in st.reason
    _, st = parse_vmaf("", 1)
    assert st.state == STATE_REJECTED


@pytest.mark.parametrize("bad", ["nan", "", "abc"])
def test_vmaf_bad_value_line_4(bad):
    vals, st = parse_vmaf(f"frame,vmaf\n0,90\n1,91\n2,{bad}\n", 3)
    assert vals is None and "строка 4" in st.reason


def test_vmaf_trailing_blank_lines_ignored():
    vals, _ = parse_vmaf("frame,vmaf\n0,90\n1,91\n\n\n", 2)
    assert vals == [90.0, 91.0]


def test_vmaf_field_count_mismatch_unquoted_decimal_comma():
    vals, st = parse_vmaf("frame,vmaf\n0,93,5\n", 1)
    assert vals is None
    assert "строка 2" in st.reason and "число полей 3 ≠ 2" in st.reason


def test_vmaf_crlf():
    vals, st = parse_vmaf("frame,vmaf\r\n0,90\r\n1,91\r\n", 2)
    assert vals == [90.0, 91.0] and st.state == STATE_ENABLED


@pytest.mark.parametrize("n", [0, -1])
def test_vmaf_expected_nonpositive(n):
    vals, st = parse_vmaf("frame,vmaf\n0,90\n", n)
    assert vals is None and st.state == STATE_REJECTED
    assert "ожидаемое число кадров" in st.reason and "≤ 0" in st.reason


def test_vmaf_read_missing_and_bom(tmp_path):
    vals, st = read_vmaf(tmp_path / "x.tsv", 3)
    assert vals is None and st.state == STATE_UNAVAILABLE
    p = tmp_path / "v.csv"
    p.write_bytes(b"\xef\xbb\xbfframe,vmaf\n0,90\n1,91\n")
    vals, st = read_vmaf(p, 2)
    assert vals == [90.0, 91.0] and st.state == STATE_ENABLED


@pytest.mark.parametrize("name", ["frame", "Frame_Num", "framenum", "frame_index", "N"])
def test_vmaf_frame_column_names(name):
    vals, st = parse_vmaf(f"{name},vmaf\n1,90\n2,91\n", 2)
    assert vals is None and "база индекса 1" in st.reason
