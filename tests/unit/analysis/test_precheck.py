"""ALN-02, ALN-04 (чистая логика, без subprocess): предпроверка пары и --offset."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import StreamInfo
from enpipe.analysis.precheck import (
    check_offset,
    check_pair,
    detect_vfr,
    fps_equal,
    keyframe_reasons,
    offset_hints,
    pts_reasons,
    scenes_reasons,
)

CFG = AnalyzeConfig()
S4 = [(0, 24), (24, 48), (48, 72), (72, 96)]


def _info(**over) -> StreamInfo:
    base = StreamInfo(
        name="a.mkv",
        format_name="matroska,webm",
        codec_name="hevc",
        width=3840,
        height=1600,
        pix_fmt="yuv420p10le",
        avg_frame_rate=Fraction(24000, 1001),
        start_time=0.0,
        color_range="tv",
        color_space="bt2020nc",
        color_transfer="smpte2084",
        color_primaries="bt2020",
    )
    return replace(base, **over)


def _cfr(n: int, fps: float = 24.0, start: float = 0.0):
    return [start + i / fps for i in range(n)]


def _pair(src=None, enc=None, n_src=96, n_enc=96, offset=None, scenes=None, **kw):
    enc_pts = kw.get("enc_pts", _cfr(n_enc))
    # WR-10: по умолчанию ключевой каждый кадр энкода; явный None передаётся как None.
    keyframes = kw["enc_keyframes"] if "enc_keyframes" in kw else tuple(range(len(enc_pts)))
    return check_pair(
        src or _info(), enc or _info(), kw.get("src_pts", _cfr(n_src)),
        enc_pts, offset, scenes, CFG, enc_keyframes=keyframes,
    )


def _has(v, text):
    return any(text in r for r in v.reasons)


def test_identical_pair_ok():
    v = _pair()
    assert v.ok and v.reasons == () and v.notes == () and not v.vfr


def test_all_reasons_collected():
    v = _pair(
        src=_info(color_transfer="bt709"),
        enc=_info(width=3840, height=1608, avg_frame_rate=Fraction(24), color_space=None),
    )
    assert not v.ok
    for text in ("размер различается", "частота различается", "тег color_space", "источник не PQ"):
        assert _has(v, text), text


def test_unknown_tag_one_side():
    assert _pair(enc=_info(color_range=None)).ok is False
    both = _pair(src=_info(color_range=None), enc=_info(color_range=None))
    assert not _has(both, "color_range")
    assert _has(_pair(enc=_info(color_range=None)), "color_range: источник tv, энкод unknown")


def test_pix_fmt_and_odd_width():
    assert _has(_pair(enc=_info(pix_fmt="yuv420p")), "pix_fmt")
    assert _has(_pair(src=_info(width=3839), enc=_info(width=3839)), "нечётный")


def test_dv_profile5_refused():
    v = _pair(src=_info(has_dovi=True, dv_profile=5))
    assert not v.ok and "profile 5" in v.reasons[0]


def test_dv_unknown_profile_refused():
    assert _has(_pair(src=_info(has_dovi=True)), "профиль Dolby Vision не определён")


def test_dv_profile8_not_a_reason():
    v = _pair(src=_info(has_dovi=True, dv_profile=8))
    assert v.ok and not _has(v, "Dolby Vision")


def test_obu_refused():
    assert _has(_pair(enc=_info(format_name="obu")), "контейнер с pts")
    assert _has(_pair(enc=_info(format_name=None, name="movie.obu")), "контейнер с pts")


def test_start_time_note():
    assert "start_time источника 2.5 с" in _pair(src=_info(start_time=2.5)).notes
    assert _pair(src=_info(start_time=None)).notes == ()


def test_vfr_note():
    pts = _cfr(48, 24.0)
    pts += [pts[-1] + (i + 1) / 12 for i in range(48)]
    v = _pair(src_pts=pts, enc_pts=_cfr(96))
    assert v.vfr and "VFR-источник, сверка по индексу" in v.notes
    assert not detect_vfr(_cfr(96), CFG)


def test_negative_pts_refused():
    assert any("отрицательные pts" in r for r in pts_reasons("энкод", [-0.042, 0.0, 0.042]))


def test_pts_reasons_other():
    assert "пустая таблица pts" in pts_reasons("энкод", [])[0]
    assert "неоднозначная" in pts_reasons("энкод", [0.0, 0.0, 0.1])[0]
    assert pts_reasons("энкод", [0.0, float("nan")])


@pytest.mark.parametrize("field", ["tt", "bb"])
def test_interlaced_refused(field):
    assert _has(_pair(src=_info(field_order=field)), f"источник чересстрочный (field_order={field})")
    assert _has(_pair(enc=_info(field_order=field)), "энкод чересстрочный")
    assert _pair(src=_info(field_order="progressive"), enc=_info(field_order=None)).ok


def test_fps_equal():
    assert fps_equal(Fraction(24000, 1001), Fraction(24000, 1001), 5e-4)
    assert not fps_equal(Fraction(24), Fraction(24000, 1001), 5e-4)
    assert not fps_equal(None, Fraction(24), 5e-4)


def test_real_p5_dv_reason_first():
    src = StreamInfo(
        name="p5.mp4", format_name="mov,mp4,m4a,3gp,3g2,mj2", codec_name="hevc",
        width=3840, height=1920, pix_fmt="yuv420p10le", avg_frame_rate=Fraction(24000, 1001),
        start_time=0.0, color_range="tv", color_space=None, color_transfer=None,
        color_primaries=None, has_dovi=True, dv_profile=5,
    )
    enc = _info(width=3840, height=1920)
    v = _pair(src=src, enc=enc)
    assert not v.ok and "profile 5" in v.reasons[0]
    for name in ("color_space", "color_transfer", "color_primaries"):
        assert _has(v, f"тег {name}")
    assert _has(v, "источник не PQ")


def test_real_p8_passes_as_pq():
    p8 = StreamInfo(
        name="p8.mkv", format_name="matroska,webm", codec_name="hevc", width=3582,
        height=2160, pix_fmt="yuv420p10le", avg_frame_rate=Fraction(24, 1), start_time=0.0,
        color_range="tv", color_space="bt2020nc", color_transfer="smpte2084",
        color_primaries="bt2020", has_dovi=True, dv_profile=8,
    )
    v = _pair(src=p8, enc=p8)
    assert v.ok and v.reasons == () and not _has(v, "Dolby Vision")


def test_real_p7_passes_as_pq():
    p7 = StreamInfo(
        name="p7.mkv", format_name="matroska,webm", codec_name="hevc", width=3840,
        height=2160, pix_fmt="yuv420p10le", avg_frame_rate=Fraction(24000, 1001),
        start_time=0.0, color_range="tv", color_space="bt2020nc",
        color_transfer="smpte2084", color_primaries="bt2020", has_dovi=True, dv_profile=7,
    )
    v = _pair(src=p7, enc=p7)
    assert v.ok and v.reasons == () and not _has(v, "Dolby Vision")


# --------------------------------------------------------------------------- #
# --offset
# --------------------------------------------------------------------------- #


def test_offset_hints_partial():
    assert offset_hints(S4, 48) == ([(0, 0, 1), (24, 1, 2), (48, 2, 3)], 0)
    hints, more = offset_hints(S4, 48, limit=2)
    assert len(hints) == 2 and more == 1
    assert offset_hints(S4, 50) == ([], 0)


def test_offset_missing_count_mismatch():
    _, _, reasons, _ = check_offset(96, 48, None, S4)
    assert "--offset 24 (сцены 1..2)" in reasons[0]
    _, _, reasons, _ = check_offset(96, 48, None, None)
    assert "start_frame" in reasons[0] and "--offset 0" not in reasons[0]
    assert check_offset(96, 96, None, S4) == (0, None, [], [])


def test_offset_not_on_scene_start():
    _, _, reasons, _ = check_offset(96, 48, 30, S4)
    assert "не совпадает с началом ни одной сцены" in reasons[0]
    assert check_offset(96, 48, 24, S4) == (24, "scenes", [], [])


def test_offset_manual_note():
    k, src, reasons, notes = check_offset(96, 48, 24, None)
    assert (k, src, reasons) == (24, "manual", [])
    assert notes == ["сдвиг задан вручную, по .scenes не проверен"]


def test_offset_exceeds_source():
    assert "60 + 48 > 96" in check_offset(96, 48, 60, None)[2][0]
    assert check_offset(96, 48, -1, None)[2]


def test_check_pair_applies_offset():
    v = _pair(n_enc=48, offset=24, scenes=S4)
    assert v.ok and v.offset == 24 and v.offset_source == "scenes"
    assert not _pair(n_enc=48).ok


# --------------------------------------------------------------------------- #
# WR-10: сверка .scenes (решение оператора 2026-11-07)
# --------------------------------------------------------------------------- #


def test_scenes_reasons_valid():
    assert scenes_reasons(S4, 96) == []
    # сцены нулевой длины допустимы
    assert scenes_reasons([(0, 24), (24, 24), (24, 96)], 96) == []


def test_scenes_reasons_unsorted():
    r = scenes_reasons([(24, 48), (0, 24), (48, 96)], 96)
    assert any("не отсортированы" in x for x in r)


def test_scenes_reasons_gap():
    r = scenes_reasons([(0, 24), (30, 96)], 96)
    assert any("не идут подряд" in x and "24" in x and "30" in x for x in r)


def test_scenes_reasons_first_not_zero():
    r = scenes_reasons([(10, 96)], 96)
    assert any("первая сцена начинается с кадра 10" in x for x in r)


def test_scenes_reasons_last_end():
    r = scenes_reasons([(0, 24), (24, 90)], 96)
    assert any("кончается на кадре 90, в источнике 96 кадров" in x for x in r)


def test_keyframe_reasons_full():
    r = keyframe_reasons(S4, 0, 96, (0, 24, 48))
    assert len(r) == 1 and "72" in r[0]
    assert keyframe_reasons(S4, 0, 96, (0, 24, 48, 72)) == []


def test_keyframe_reasons_partial():
    # окно энкода [24, 72): начала 24 и 48 -> кадры энкода 0 и 24; начало 72 вне окна
    assert keyframe_reasons(S4, 24, 48, (0, 24)) == []
    r = keyframe_reasons(S4, 24, 48, (0,))
    assert len(r) == 1 and "24" in r[0]


def test_keyframe_reasons_cap():
    scenes = [(i * 10, i * 10 + 10) for i in range(15)]
    r = keyframe_reasons(scenes, 0, 150, (0,))
    assert len(r) == 1
    assert "… и ещё 4" in r[0]
    # 14 начал не ключевые, показано 10: 10, 20, …, 100
    assert "100" in r[0] and "110" not in r[0]
    assert "без .scenes" in r[0]


# На HEAD (до 10-17) check_offset при полном энкоде возвращался до сцен, поэтому
# разрывный .scenes принимался молча.
def test_check_pair_full_encode_scenes_checked():
    v = _pair(scenes=[(0, 24), (30, 96)])
    assert not v.ok and _has(v, "не идут подряд")


def test_check_pair_keyframes_missing():
    v = _pair(scenes=S4, enc_keyframes=None)
    assert not v.ok and _has(v, "нет флагов ключевых кадров энкода")
    # без .scenes флаги не нужны
    assert _pair(enc_keyframes=None).ok


def test_check_pair_scenes_collects_all():
    v = _pair(enc=_info(width=1920), scenes=[(0, 24), (30, 96)])
    assert _has(v, "размер различается") and _has(v, "не идут подряд")


def test_check_pair_offset_error_skips_keyframes():
    v = _pair(n_enc=48, offset=30, scenes=S4, enc_keyframes=(0,))
    assert _has(v, "не совпадает с началом ни одной сцены")
    assert not _has(v, "не на ключевых кадрах")
