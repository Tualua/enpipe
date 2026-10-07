"""ALN-01, ALN-02, ANL-03: argv ffprobe/ffmpeg через pytest-subprocess fp.

Фикстуры _P5/_P7/_P8_PROBE_JSON — дословный вывод ffprobe n9.0.2 по реальным
файлам оператора (строка ENTRIES с field_order через V:0).
"""

from __future__ import annotations

import os
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from enpipe.analysis import frames
from enpipe.analysis.config import AnalysisError, MAX_GRAB_FRAMES

_NICE = ["nice", "-n", "10"]


@pytest.fixture(autouse=True)
def _nice(monkeypatch):
    monkeypatch.setattr(frames.shutil, "which", lambda name: "/usr/bin/nice")


def _probe_argv(path):
    return _NICE + [
        "ffprobe", "-v", "error", "-select_streams", "V:0",
        "-show_entries", frames._PROBE_ENTRIES, "-of", "json", "-i", str(path),
    ]


def _pts_argv(path):
    return _NICE + [
        "ffprobe", "-v", "error", "-select_streams", "V:0",
        "-show_entries", "packet=pts_time", "-of", "csv=p=0", "-i", str(path),
    ]


_P5_PROBE_JSON = """\
{
    "programs": [

    ],
    "stream_groups": [

    ],
    "streams": [
        {
            "codec_name": "hevc",
            "width": 3840,
            "height": 1920,
            "pix_fmt": "yuv420p10le",
            "color_range": "tv",
            "avg_frame_rate": "24000/1001",
            "start_time": "0.000000",
            "side_data_list": [
                {
                    "side_data_type": "DOVI configuration record",
                    "dv_profile": 5
                }
            ]
        }
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2"
    }
}
"""


_P7_PROBE_JSON = """\
{
    "programs": [

    ],
    "stream_groups": [

    ],
    "streams": [
        {
            "codec_name": "hevc",
            "width": 3840,
            "height": 2160,
            "pix_fmt": "yuv420p10le",
            "color_range": "tv",
            "color_space": "bt2020nc",
            "color_transfer": "smpte2084",
            "color_primaries": "bt2020",
            "avg_frame_rate": "24000/1001",
            "start_time": "0.000000",
            "side_data_list": [
                {
                    "side_data_type": "DOVI configuration record",
                    "dv_profile": 7
                },
                {
                    "side_data_type": "HEVC enhancement-layer decoder configuration"
                }
            ]
        }
    ],
    "format": {
        "format_name": "matroska,webm"
    }
}
"""


_P8_PROBE_JSON = """\
{
    "programs": [

    ],
    "stream_groups": [

    ],
    "streams": [
        {
            "codec_name": "hevc",
            "width": 3582,
            "height": 2160,
            "pix_fmt": "yuv420p10le",
            "color_range": "tv",
            "color_space": "bt2020nc",
            "color_transfer": "smpte2084",
            "color_primaries": "bt2020",
            "avg_frame_rate": "24/1",
            "start_time": "0.000000",
            "side_data_list": [
                {
                    "side_data_type": "DOVI configuration record",
                    "dv_profile": 8
                }
            ]
        }
    ],
    "format": {
        "format_name": "matroska,webm"
    }
}
"""


_PQ_JSON = (
    '{"streams":[{"codec_name":"hevc","width":3840,"height":1600,'
    '"pix_fmt":"yuv420p10le","avg_frame_rate":"24000/1001","start_time":"2.500000",'
    '"color_range":"tv","color_space":"bt2020nc","color_transfer":"smpte2084",'
    '"color_primaries":"bt2020"}],"format":{"format_name":"matroska,webm"}}'
)


def _probe(fp, name, js):
    p = Path(name)
    fp.register(_probe_argv(p), stdout=js)
    return frames.probe_stream(p)


def test_nice_prefix(monkeypatch):
    assert frames.nice_prefix() == ["nice", "-n", "10"]
    monkeypatch.setattr(frames.shutil, "which", lambda name: None)
    assert frames.nice_prefix() == []


def test_no_nice_argv_without_prefix(fp, monkeypatch):
    monkeypatch.setattr(frames.shutil, "which", lambda name: None)
    p = Path("src.mkv")
    fp.register(_probe_argv(p)[3:], stdout=_PQ_JSON)
    assert frames.probe_stream(p).name == "src.mkv"


def test_probe_parses_pq_stream(fp):
    si = _probe(fp, "src.mkv", _PQ_JSON)
    assert si.format_name == "matroska,webm"
    assert si.avg_frame_rate == Fraction(24000, 1001)
    assert si.start_time == 2.5
    assert (si.width, si.height, si.pix_fmt) == (3840, 1600, "yuv420p10le")
    assert (si.color_space, si.color_transfer, si.color_primaries) == (
        "bt2020nc", "smpte2084", "bt2020")
    assert not si.has_dovi and si.dv_profile is None and si.field_order is None


def test_probe_normalizes_unknown_tags(fp):
    js = (
        '{"streams":[{"codec_name":"hevc","width":64,"height":36,"pix_fmt":"yuv420p10le",'
        '"avg_frame_rate":"0/0","start_time":"N/A","color_range":"unknown",'
        '"color_space":"unspecified","color_transfer":"N/A"}],'
        '"format":{"format_name":"matroska,webm"}}'
    )
    si = _probe(fp, "a.mkv", js)
    assert si.avg_frame_rate is None and si.start_time is None
    assert si.color_range is None and si.color_space is None
    assert si.color_transfer is None and si.color_primaries is None


def test_probe_dovi_profile(fp):
    base = '{"streams":[{"width":64,"height":36,"side_data_list":[%s]}],"format":{}}'
    si = _probe(fp, "a.mkv", base % '{"side_data_type":"DOVI configuration record"}')
    assert si.has_dovi and si.dv_profile is None
    si = _probe(fp, "b.mkv", base % '{"side_data_type":"DOVI configuration record","dv_profile":8}')
    assert si.has_dovi and si.dv_profile == 8
    si = _probe(fp, "c.mkv", '{"streams":[{"width":64,"height":36}],"format":{}}')
    assert not si.has_dovi and si.dv_profile is None


def test_probe_real_p5_verbatim(fp):
    """Реальный P5 оператора (ffprobe n9.0.2); теги цвета отсутствуют -> None."""
    si = _probe(fp, "p5.mp4", _P5_PROBE_JSON)
    assert si == frames.StreamInfo(
        name="p5.mp4", format_name="mov,mp4,m4a,3gp,3g2,mj2", codec_name="hevc",
        width=3840, height=1920, pix_fmt="yuv420p10le",
        avg_frame_rate=Fraction(24000, 1001), start_time=0.0, color_range="tv",
        color_space=None, color_transfer=None, color_primaries=None,
        has_dovi=True, dv_profile=5, field_order=None)


def test_probe_real_p8_verbatim(fp):
    """Реальный DV P8.1 (Poor Things); field_order в выводе нет -> None."""
    si = _probe(fp, "p8.mkv", _P8_PROBE_JSON)
    assert si == frames.StreamInfo(
        name="p8.mkv", format_name="matroska,webm", codec_name="hevc",
        width=3582, height=2160, pix_fmt="yuv420p10le",
        avg_frame_rate=Fraction(24, 1), start_time=0.0, color_range="tv",
        color_space="bt2020nc", color_transfer="smpte2084",
        color_primaries="bt2020", has_dovi=True, dv_profile=8, field_order=None)


def test_probe_real_p7_verbatim(fp):
    si = _probe(fp, "p7.mkv", _P7_PROBE_JSON)
    assert si == frames.StreamInfo(
        name="p7.mkv", format_name="matroska,webm", codec_name="hevc",
        width=3840, height=2160, pix_fmt="yuv420p10le",
        avg_frame_rate=Fraction(24000, 1001), start_time=0.0, color_range="tv",
        color_space="bt2020nc", color_transfer="smpte2084",
        color_primaries="bt2020", has_dovi=True, dv_profile=7, field_order=None)


def test_probe_dovi_second_side_data_keeps_profile(fp):
    js = (
        '{"streams":[{"width":64,"height":36,"side_data_list":['
        '{"side_data_type":"HEVC enhancement-layer decoder configuration"},'
        '{"side_data_type":"DOVI configuration record","dv_profile":7}]}],"format":{}}'
    )
    assert _probe(fp, "r.mkv", js).dv_profile == 7


@pytest.mark.parametrize("raw,exp", [
    ('"field_order":"tt"', "tt"), ('"field_order":"progressive"', "progressive"),
    ('"field_order":"unknown"', None), ('"x":1', None)])
def test_probe_field_order(fp, raw, exp):
    js = '{"streams":[{"width":64,"height":36,%s}],"format":{}}' % raw
    assert _probe(fp, "f.mkv", js).field_order == exp


def test_probe_errors(fp):
    p = Path("bad.mkv")
    fp.register(_probe_argv(p), returncode=1, stderr="boom happened\n")
    with pytest.raises(AnalysisError, match="boom happened"):
        frames.probe_stream(p)
    q = Path("junk.mkv")
    fp.register(_probe_argv(q), stdout="not json")
    with pytest.raises(AnalysisError):
        frames.probe_stream(q)
    r = Path("empty.mkv")
    fp.register(_probe_argv(r), stdout='{"streams":[],"format":{}}')
    with pytest.raises(AnalysisError):
        frames.probe_stream(r)


# --------------------------------------------------------------------------- #
# pts_table
# --------------------------------------------------------------------------- #


def _video(tmp_path):
    p = tmp_path / "src.mkv"
    p.write_bytes(b"x" * 100)
    return p


def test_pts_sorted(fp, tmp_path):
    p = _video(tmp_path)
    fp.register(_pts_argv(p), stdout="0.000000\n0.208000\n0.125000,\n0.041667\n")
    assert frames.pts_table(p) == [0.0, 0.041667, 0.125, 0.208]


def test_pts_na_refused(fp, tmp_path):
    p = _video(tmp_path)
    fp.register(_pts_argv(p), stdout="N/A\nN/A\n")
    with pytest.raises(AnalysisError, match="нет pts") as ei:
        frames.pts_table(p)
    assert ".mkv/контейнер" in str(ei.value)


def test_pts_empty_refused(fp, tmp_path):
    p = _video(tmp_path)
    fp.register(_pts_argv(p), stdout="")
    with pytest.raises(AnalysisError):
        frames.pts_table(p)


def test_pts_cache_hit_skips_ffprobe(fp, tmp_path):
    p = _video(tmp_path)
    cache = tmp_path / "rep"
    fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
    assert frames.pts_table(p, cache) == [0.0, 0.5]
    assert len(list(cache.glob("*.pts.json"))) == 1
    # второй вызов: argv не зарегистрирован — ffprobe запускаться не должен
    assert frames.pts_table(p, cache) == [0.0, 0.5]


def test_pts_cache_invalidated_by_mtime(fp, tmp_path):
    p = _video(tmp_path)
    cache = tmp_path / "rep"
    fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
    frames.pts_table(p, cache)
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
    fp.register(_pts_argv(p), stdout="0.0\n0.25\n0.5\n")
    assert frames.pts_table(p, cache) == [0.0, 0.25, 0.5]


def test_pts_cache_corrupt_recomputed(fp, tmp_path):
    import json
    p = _video(tmp_path)
    cache = tmp_path / "rep"
    fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
    frames.pts_table(p, cache)
    f = next(cache.glob("*.pts.json"))
    good = json.loads(f.read_text())
    variants = [
        "{broken",
        json.dumps({**good, "v": 2}),
        json.dumps({**good, "key": {**good["key"], "path": "/elsewhere"}}),
        json.dumps({**good, "pts": ["a", "b"]}),
        json.dumps({**good, "pts": []}),
    ]
    for v in variants:
        f.write_text(v)
        fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
        assert frames.pts_table(p, cache) == [0.0, 0.5]


def test_pts_no_cache_dir_no_files(fp, tmp_path):
    p = _video(tmp_path)
    fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
    frames.pts_table(p)
    assert list(tmp_path.glob("*.pts.json")) == []


def test_pts_unwritable_cache_still_returns(fp, tmp_path):
    p = _video(tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    fp.register(_pts_argv(p), stdout="0.0\n0.5\n")
    assert frames.pts_table(p, blocker / "sub") == [0.0, 0.5]


def test_no_hw_flags(fp, tmp_path):
    p = _video(tmp_path)
    fp.register(_pts_argv(p), stdout="0.0\n")
    frames.pts_table(p)
    fp.register(_probe_argv(p), stdout=_PQ_JSON)
    frames.probe_stream(p)
    for call in fp.calls:
        argv = list(call)
        assert argv[:3] == _NICE
        assert not {"-hwaccel", "qsv", "vaapi"} & set(argv)


# --------------------------------------------------------------------------- #
# grab_frames
# --------------------------------------------------------------------------- #

_PTS = [i * 1001 / 24000 for i in range(96)]


def _raw(count, w, h, fill=1):
    n = count * w * h * 3 // 2
    return (np.full(n, fill, dtype="<u2")).tobytes()


def _grab_argv(path, first, count, w=64, h=36, threads=2):
    ss = []
    if first:
        t = _PTS[first] - (_PTS[first] - _PTS[first - 1]) / 2
        ss = ["-seek_timestamp", "1", "-ss", f"{t:.6f}"]
    return _NICE + (
        ["ffmpeg", "-v", "error", "-nostdin"] + ss
        + ["-threads", str(threads), "-i", str(path), "-map", "0:V:0",
           "-pix_fmt", "yuv420p10le", "-fps_mode", "passthrough",
           "-frames:v", str(count), "-f", "rawvideo", "pipe:1"]
    )


def test_grab_first_frame_no_ss(fp):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 0, 1), stdout=_raw(1, 64, 36))
    frames.grab_frames(p, _PTS, 0, 1, 64, 36)
    argv = list(fp.calls[0])
    assert "-ss" not in argv and "-seek_timestamp" not in argv
    assert "-nostdin" in argv


def test_grab_seek_args_before_input(fp):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 10, 1), stdout=_raw(1, 64, 36))
    frames.grab_frames(p, _PTS, 10, 1, 64, 36)
    argv = list(fp.calls[0])
    i = argv.index("-i")
    ss = f"{_PTS[10] - (_PTS[10] - _PTS[9]) / 2:.6f}"
    k = argv.index("-seek_timestamp")
    assert argv[k:k + 4] == ["-seek_timestamp", "1", "-ss", ss] and k + 3 < i
    assert argv[argv.index("-threads") + 1] == "2" and argv.index("-threads") < i
    assert argv[i + 2:i + 4] == ["-map", "0:V:0"]


def test_grab_threads_param(fp):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 0, 1, threads=4), stdout=_raw(1, 64, 36))
    frames.grab_frames(p, _PTS, 0, 1, 64, 36, threads=4)


def test_grab_no_filters_no_hw(fp):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 5, 1), stdout=_raw(1, 64, 36))
    frames.grab_frames(p, _PTS, 5, 1, 64, 36)
    argv = list(fp.calls[0])
    for bad in ("-vsync", "select", "-vf", "-hwaccel", "qsv"):
        assert bad not in argv
    assert not any(a.startswith("fps=") for a in argv)


def test_grab_planes_shapes_and_le(fp):
    p = Path("s.mkv")
    w, h = 64, 36
    luma, ch = w * h, w * h // 4
    f1 = np.concatenate([np.full(luma, 513), np.full(ch, 2), np.full(ch, 3)])
    f2 = np.concatenate([np.full(luma, 7), np.full(ch, 8), np.full(ch, 9)])
    raw = np.concatenate([f1, f2]).astype("<u2").tobytes()
    assert raw[:2] == b"\x01\x02"
    fp.register(_grab_argv(p, 0, 2), stdout=raw)
    out = frames.grab_frames(p, _PTS, 0, 2, w, h)
    assert len(out) == 2
    for (y, u, v), (ey, eu, ev) in zip(out, [(513, 2, 3), (7, 8, 9)]):
        assert y.shape == (36, 64) and u.shape == v.shape == (18, 32)
        assert y.dtype == u.dtype == v.dtype == np.uint16
        assert (y == ey).all() and (u == eu).all() and (v == ev).all()


@pytest.mark.parametrize("delta", [-2, 2])
def test_grab_short_output_error(fp, delta):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 0, 1), stdout=_raw(1, 64, 36)[:-2] if delta < 0 else _raw(1, 64, 36) + b"\0\0")
    with pytest.raises(AnalysisError, match="ожидалось"):
        frames.grab_frames(p, _PTS, 0, 1, 64, 36)


def test_grab_rc_error(fp):
    p = Path("s.mkv")
    fp.register(_grab_argv(p, 0, 1), returncode=1, stderr="decode failed\n")
    with pytest.raises(AnalysisError, match="decode failed"):
        frames.grab_frames(p, _PTS, 0, 1, 64, 36)


def test_grab_odd_size_rejected_before_run(fp):
    p = Path("s.mkv")
    with pytest.raises(AnalysisError):
        frames.grab_frames(p, _PTS, 0, 1, 63, 36)
    with pytest.raises(AnalysisError):
        frames.grab_frames(p, _PTS, 0, 1, 64, 35)
    assert not fp.calls


def test_grab_count_limits(fp):
    p = Path("s.mkv")
    for first, count in [(0, 0), (0, MAX_GRAB_FRAMES + 1), (-1, 1), (90, 10)]:
        with pytest.raises(AnalysisError):
            frames.grab_frames(p, _PTS, first, count, 64, 36)
    assert not fp.calls
