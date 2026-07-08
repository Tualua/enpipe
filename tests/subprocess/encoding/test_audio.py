"""TEST-02: mocked subprocess-boundary test for enpipe.encoding.audio.
encode_audio — proves the worker-thread (bool, Optional[str]) tuple-return
regime survives migration (never raises), using pytest-subprocess's `fp`
fixture (D-09)."""

from __future__ import annotations

from pathlib import Path

from enpipe.encoding.audio import encode_audio

_PROBE_ARGV = [
    "ffprobe", "-v", "error", "-select_streams", "a",
    "-show_entries", "stream=index,codec_name,profile,channels,channel_layout",
    "-of", "json", "in.mkv",
]


def test_encode_audio_returns_false_none_when_no_audio_streams(fp):
    fp.register(_PROBE_ARGV, stdout='{"streams": []}')
    ok, err = encode_audio(Path("in.mkv"), Path("out.mka"))
    assert (ok, err) == (False, None)


def test_encode_audio_returns_false_msg_tuple_on_ffmpeg_failure_never_raises(fp):
    fp.register(_PROBE_ARGV, stdout='{"streams": [{"index": 0, "codec_name": "aac", '
                                     '"profile": "LC", "channels": 2, '
                                     '"channel_layout": "stereo"}]}')
    fp.register(
        ["ffmpeg", "-y", "-v", "error", "-i", "in.mkv", "-map_chapters", "-1",
         "-map", "0:a:0", "-c:a:0", "libopus", "-b:a:0", "128k", "out.mka"],
        returncode=1, stderr="ffmpeg: invalid data\n",
    )
    ok, err = encode_audio(Path("in.mkv"), Path("out.mka"))
    assert ok is False
    assert err is not None and "invalid data" in err


def test_encode_audio_copies_flac_lossless_track_and_succeeds(fp):
    fp.register(_PROBE_ARGV, stdout='{"streams": [{"index": 0, "codec_name": "flac", '
                                     '"profile": "", "channels": 2, '
                                     '"channel_layout": "stereo"}]}')
    fp.register(
        ["ffmpeg", "-y", "-v", "error", "-i", "in.mkv", "-map_chapters", "-1",
         "-map", "0:a:0", "-c:a:0", "copy", "out.mka"],
        stdout="", stderr="",
    )
    ok, err = encode_audio(Path("in.mkv"), Path("out.mka"))
    assert (ok, err) == (True, None)
