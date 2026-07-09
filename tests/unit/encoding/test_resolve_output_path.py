"""Fast pure-logic tests for enpipe.encoding.pipeline.resolve_output_path
(quick task 260709-4h8): covers the three branches — existing directory
(new `.Encoded` naming), explicit file path (unchanged), and omitted `out`
(unchanged default `<video>.av1.mkv`). No hardware, no subprocess."""

from __future__ import annotations

from enpipe.encoding.pipeline import resolve_output_path


def test_resolve_output_path_existing_dir_uses_encoded_suffix(tmp_path):
    video = tmp_path / "movie.mkv"
    assert resolve_output_path(video, tmp_path) == tmp_path / "movie.Encoded.mkv"


def test_resolve_output_path_explicit_file_unchanged(tmp_path):
    video = tmp_path / "movie.mkv"
    out = tmp_path / "custom" / "out.mkv"
    assert resolve_output_path(video, out) == out


def test_resolve_output_path_none_uses_default(tmp_path):
    video = tmp_path / "movie.mkv"
    assert resolve_output_path(video, None) == tmp_path / "movie.av1.mkv"


def test_resolve_output_path_multidot_name_in_dir(tmp_path):
    video = tmp_path / "A.B.C.mkv"
    assert resolve_output_path(video, tmp_path) == tmp_path / "A.B.C.Encoded.mkv"
