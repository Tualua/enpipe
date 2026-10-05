"""Юнит-тесты чистых функций сборки argv аудио: правила выбора кодека
(включая Atmos -> copy), команда одной дорожки и команда склейки."""

from __future__ import annotations

from pathlib import Path

from enpipe.encoding import audio
from enpipe.encoding.audio import (
    _merge_command, _part_path, _track_codec_args, _track_command,
)

COPY = ["-c:a", "copy"]


def _st(codec, ch=2, layout="", prof=""):
    return {"codec_name": codec, "channels": ch, "channel_layout": layout,
            "profile": prof}


def test_aac_stereo_to_opus():
    assert _track_codec_args(_st("aac"), False) == \
        ["-c:a", "libopus", "-b:a", "128k"]


def test_ac3_51_side_normalised():
    assert _track_codec_args(_st("ac3", 6, "5.1(side)"), False) == [
        "-c:a", "libopus", "-b:a", "256k",
        "-filter:a", "aformat=channel_layouts=5.1"]


def test_71_wide_and_no_layout_fallbacks():
    assert _track_codec_args(_st("ac3", 8, "7.1(wide)"), False)[-1] == \
        "aformat=channel_layouts=7.1"
    assert _track_codec_args(_st("ac3", 6), False)[-1] == \
        "aformat=channel_layouts=5.1"
    assert "-filter:a" not in _track_codec_args(_st("ac3", 3), False)


def test_flac_and_opus_copy():
    assert _track_codec_args(_st("flac"), False) == COPY
    assert _track_codec_args(_st("opus"), False) == COPY


def test_lossless_to_flac():
    exp = ["-c:a", "flac", "-compression_level", audio.FLAC_LEVEL]
    assert _track_codec_args(_st("truehd"), False) == exp
    assert _track_codec_args(_st("pcm_s24le"), False) == exp
    assert _track_codec_args(_st("dts", 6, prof="DTS-HD MA"), False) == exp


def test_dts_core_to_opus():
    assert _track_codec_args(_st("dts", 2, prof="DTS"), False)[1] == "libopus"


def test_atmos_eac3_copy():
    st = _st("eac3", 6, prof="Dolby Digital Plus + Dolby Atmos")
    assert _track_codec_args(st, False) == COPY


def test_atmos_truehd_copy_beats_lossless():
    st = _st("truehd", 8, prof="Dolby TrueHD + Dolby Atmos")
    assert _track_codec_args(st, False) == COPY


def test_atmos_case_insensitive():
    assert _track_codec_args(_st("eac3", 6, prof="dolby atmos"), False) == COPY


def test_audio_copy_flag():
    assert _track_codec_args(_st("aac"), True) == COPY


def test_missing_fields_do_not_fail():
    assert _track_codec_args({"codec_name": "aac", "channels": None,
                              "profile": None}, False) == \
        ["-c:a", "libopus", "-b:a", "128k"]


def test_part_path():
    assert _part_path(Path("w/audio.mka"), 3) == Path("w/audio.a03.mka")


def test_track_command_full_and_range():
    st = _st("aac")
    assert _track_command(Path("in.mkv"), 1, st, Path("p.mka"), None, None,
                          False) == [
        "ffmpeg", "-y", "-v", "error", "-i", "in.mkv", "-map_chapters", "-1",
        "-map", "0:a:1", "-c:a", "libopus", "-b:a", "128k", "p.mka"]
    assert _track_command(Path("in.mkv"), 0, st, Path("p.mka"), 12.5, 30.0,
                          True) == [
        "ffmpeg", "-y", "-v", "error", "-ss", "0.000", "-i", "in.mkv",
        "-ss", "12.500", "-t", "30.000", "-map_chapters", "-1", "-map", "0:a:0",
        "-c:a", "copy", "p.mka"]


def _cmd(st, ss, dur, copy=False):
    return _track_command(Path("in.mkv"), 2, st, Path("p.mka"), ss, dur, copy)


ATMOS = _st("eac3", 6, prof="Dolby Digital Plus + Dolby Atmos")


def test_copy_partial_two_step_seek():
    cmd = _cmd(ATMOS, 600.0, 60.0)
    assert cmd == [
        "ffmpeg", "-y", "-v", "error", "-ss", "570.000", "-i", "in.mkv",
        "-ss", "30.000", "-t", "60.000", "-map_chapters", "-1", "-map", "0:a:2",
        "-c:a", "copy", "p.mka"]
    ss1, ss2 = [i for i, a in enumerate(cmd) if a == "-ss"]
    assert ss1 < cmd.index("-i") < ss2 < cmd.index("-t")


def test_copy_partial_without_dur():
    cmd = _cmd(ATMOS, 600.0, None)
    assert cmd.count("-ss") == 2 and "-t" not in cmd


def test_copy_dur_without_ss_unchanged():
    assert _cmd(ATMOS, None, 30.0) == [
        "ffmpeg", "-y", "-v", "error", "-i", "in.mkv", "-t", "30.000",
        "-map_chapters", "-1", "-map", "0:a:2", "-c:a", "copy", "p.mka"]


def test_transcoded_partial_argv_unchanged():
    assert _cmd(_st("aac"), 12.5, 30.0) == [
        "ffmpeg", "-y", "-v", "error", "-ss", "12.500", "-i", "in.mkv",
        "-t", "30.000", "-map_chapters", "-1", "-map", "0:a:2",
        "-c:a", "libopus", "-b:a", "128k", "p.mka"]
    assert _cmd(_st("truehd", 8), 12.5, 30.0) == [
        "ffmpeg", "-y", "-v", "error", "-ss", "12.500", "-i", "in.mkv",
        "-t", "30.000", "-map_chapters", "-1", "-map", "0:a:2",
        "-c:a", "flac", "-compression_level", audio.FLAC_LEVEL, "p.mka"]


def test_full_mode_no_ss_no_t():
    for st, copy in ((ATMOS, False), (_st("aac"), False), (_st("aac"), True)):
        cmd = _cmd(st, None, None, copy)
        assert "-ss" not in cmd and "-t" not in cmd


def test_audio_copy_flag_partial_two_step():
    assert _cmd(_st("aac"), 600.0, 60.0, True).count("-ss") == 2


def test_merge_command_two_parts():
    streams = [
        {"tags": {"language": "eng"}, "disposition": {"default": 1, "forced": 0}},
        {"tags": {"language": "rus", "title": "Дубляж"},
         "disposition": {"default": 0, "forced": 1}},
    ]
    assert _merge_command([Path("a0.mka"), Path("a1.mka")], streams,
                          Path("out.mka")) == [
        "ffmpeg", "-y", "-v", "error", "-i", "a0.mka", "-i", "a1.mka",
        "-map", "0:a", "-map", "1:a", "-map_chapters", "-1", "-c", "copy",
        "-default_mode", "passthrough",
        "-disposition:a:0", "default", "-metadata:s:a:0", "language=eng",
        "-disposition:a:1", "forced", "-metadata:s:a:1", "language=rus",
        "-metadata:s:a:1", "title=Дубляж",
        "out.mka"]


def test_merge_command_no_default_and_both_flags():
    streams = [{}, {"disposition": {"default": 1, "forced": 1}}]
    cmd = _merge_command([Path("a"), Path("b")], streams, Path("o"))
    assert "-disposition:a:0" in cmd and cmd[cmd.index("-disposition:a:0") + 1] == "0"
    assert cmd[cmd.index("-disposition:a:1") + 1] == "default+forced"
