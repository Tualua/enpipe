"""TEST-02: mocked subprocess-boundary test for enpipe.encoding.audio.
encode_audio — proves the worker-thread (bool, Optional[str]) tuple-return
regime survives migration (never raises), using pytest-subprocess's `fp`
fixture (D-09). Один ffmpeg на дорожку + склейка."""

from __future__ import annotations

import json
from pathlib import Path

from enpipe.encoding.audio import encode_audio

_SHOW = ("stream=index,codec_name,profile,channels,channel_layout"
         ":stream_tags=language,title:stream_disposition=default,forced")


def _probe(src):
    return ["ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", _SHOW, "-of", "json", str(src)]


def _aac():
    return {"index": 0, "codec_name": "aac", "profile": "LC", "channels": 2,
            "channel_layout": "stereo", "tags": {"language": "eng"},
            "disposition": {"default": 1, "forced": 0}}


def _atmos():
    return {"index": 1, "codec_name": "eac3", "channels": 6,
            "profile": "Dolby Digital Plus + Dolby Atmos",
            "tags": {"language": "rus", "title": "Atmos"},
            "disposition": {"default": 0, "forced": 0}}


def _track(src, n, codec, part, extra=()):
    return ["ffmpeg", "-y", "-v", "error", *extra, "-i", str(src), "-map_chapters",
            "-1", "-map", f"0:a:{n}", *codec, str(part)]


def _merge(parts, out):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for p in parts:
        cmd += ["-i", str(p)]
    for i in range(len(parts)):
        cmd += ["-map", f"{i}:a"]
    cmd += ["-map_chapters", "-1", "-c", "copy", "-default_mode", "passthrough",
            "-disposition:a:0", "default", "-metadata:s:a:0", "language=eng",
            "-disposition:a:1", "0", "-metadata:s:a:1", "language=rus",
            "-metadata:s:a:1", "title=Atmos", str(out)]
    return cmd


def test_encode_audio_returns_false_none_when_no_audio_streams(fp):
    fp.register(_probe("in.mkv"), stdout='{"streams": []}')
    ok, err = encode_audio(Path("in.mkv"), Path("out.mka"))
    assert (ok, err) == (False, None)


def test_two_tracks_parallel_then_merge_and_cleanup(fp, tmp_path):
    src, out = tmp_path / "in.mkv", tmp_path / "audio.mka"
    parts = [tmp_path / "audio.a00.mka", tmp_path / "audio.a01.mka"]
    for p in parts:
        p.write_bytes(b"x")
    fp.register(_probe(src), stdout=json.dumps({"streams": [_aac(), _atmos()]}))
    fp.register(_track(src, 0, ["-c:a", "libopus", "-b:a", "128k"], parts[0]))
    fp.register(_track(src, 1, ["-c:a", "copy"], parts[1]))
    fp.register(_merge(parts, out))
    assert encode_audio(src, out) == (True, None)
    assert not any(p.exists() for p in parts)


def test_track_failure_reports_track_number_no_merge_and_cleanup(fp, tmp_path):
    src, out = tmp_path / "in.mkv", tmp_path / "audio.mka"
    parts = [tmp_path / "audio.a00.mka", tmp_path / "audio.a01.mka"]
    for p in parts:
        p.write_bytes(b"x")
    fp.register(_probe(src), stdout=json.dumps({"streams": [_aac(), _atmos()]}))
    fp.register(_track(src, 0, ["-c:a", "libopus", "-b:a", "128k"], parts[0]))
    fp.register(_track(src, 1, ["-c:a", "copy"], parts[1]),
                returncode=1, stderr="boom\n")
    ok, err = encode_audio(src, out)
    assert ok is False
    assert err is not None and "дорожка 1" in err and "boom" in err
    assert not any(p.exists() for p in parts)
    assert ["ffmpeg", "-y", "-v", "error", "-i", str(parts[0]), "-i",
            str(parts[1])] not in [c[:8] for c in map(list, fp.calls)]


def test_merge_failure_reports_and_cleans(fp, tmp_path):
    src, out = tmp_path / "in.mkv", tmp_path / "audio.mka"
    parts = [tmp_path / "audio.a00.mka", tmp_path / "audio.a01.mka"]
    for p in parts:
        p.write_bytes(b"x")
    fp.register(_probe(src), stdout=json.dumps({"streams": [_aac(), _atmos()]}))
    fp.register(_track(src, 0, ["-c:a", "libopus", "-b:a", "128k"], parts[0]))
    fp.register(_track(src, 1, ["-c:a", "copy"], parts[1]))
    fp.register(_merge(parts, out), returncode=1, stderr="mux bad\n")
    ok, err = encode_audio(src, out)
    assert ok is False
    assert err is not None and "склейка" in err and "mux bad" in err
    assert not any(p.exists() for p in parts)


def test_ss_dur_passed_to_every_track_command(fp, tmp_path):
    src, out = tmp_path / "in.mkv", tmp_path / "audio.mka"
    parts = [tmp_path / "audio.a00.mka", tmp_path / "audio.a01.mka"]

    def trk(n, codec, part):
        return ["ffmpeg", "-y", "-v", "error", "-ss", "12.500", "-i", str(src),
                "-t", "30.000", "-map_chapters", "-1", "-map", f"0:a:{n}",
                *codec, str(part)]

    fp.register(_probe(src), stdout=json.dumps({"streams": [_aac(), _atmos()]}))
    fp.register(trk(0, ["-c:a", "libopus", "-b:a", "128k"], parts[0]))
    fp.register(trk(1, ["-c:a", "copy"], parts[1]))
    fp.register(_merge(parts, out))
    assert encode_audio(src, out, ss=12.5, dur=30.0) == (True, None)
