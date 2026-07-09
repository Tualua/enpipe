"""Fast, hardware-free proof of дискавери-видео и батч-оркестрации
(QUICK-260709-89t): iter_input_videos (одиночный файл / директория /
recursive / исключение собственных выходов / пустая папка) и run_batch
(collect-then-report: продолжает при SystemExit/Exception одного файла,
should_skip, итоговый die с ненулевым кодом при наличии упавших)."""

from __future__ import annotations

from pathlib import Path

import pytest

from enpipe.shared.batch import iter_input_videos, run_batch
from enpipe.shared.logging import die


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy")
    return path


# --- iter_input_videos --- #

def test_single_file_returns_itself_regardless_of_suffix(tmp_path):
    f = _touch(tmp_path / "movie.mkv")
    assert iter_input_videos(f, recursive=False) == [f]

    weird = _touch(tmp_path / "movie.weird_ext")
    assert iter_input_videos(weird, recursive=False) == [weird]


def test_directory_top_level_only_direct_children(tmp_path):
    a = _touch(tmp_path / "a.mkv")
    b = _touch(tmp_path / "b.mp4")
    _touch(tmp_path / "nested" / "c.mkv")

    result = iter_input_videos(tmp_path, recursive=False)
    assert result == sorted([a, b])


def test_directory_recursive_includes_nested(tmp_path):
    a = _touch(tmp_path / "a.mkv")
    c = _touch(tmp_path / "nested" / "c.mkv")

    result = iter_input_videos(tmp_path, recursive=True)
    assert result == sorted([a, c])


def test_excludes_own_outputs_encoded_and_av1(tmp_path):
    src = _touch(tmp_path / "movie.mkv")
    _touch(tmp_path / "movie.Encoded.mkv")
    _touch(tmp_path / "movie.av1.mkv")
    _touch(tmp_path / "movie.encoded.mp4")  # регистронезависимо

    result = iter_input_videos(tmp_path, recursive=False)
    assert result == [src]


def test_non_video_suffix_filtered_out(tmp_path):
    _touch(tmp_path / "movie.mkv.scenes")
    src = _touch(tmp_path / "movie.mkv")

    result = iter_input_videos(tmp_path, recursive=False)
    assert result == [src]


def test_directory_result_is_sorted(tmp_path):
    _touch(tmp_path / "zeta.mkv")
    _touch(tmp_path / "alpha.mkv")
    _touch(tmp_path / "mid.mkv")

    result = iter_input_videos(tmp_path, recursive=False)
    assert result == sorted(result)
    assert [p.name for p in result] == ["alpha.mkv", "mid.mkv", "zeta.mkv"]


def test_empty_directory_returns_empty_list(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert iter_input_videos(empty, recursive=False) == []


def test_directory_with_only_non_video_files_returns_empty_list(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    _touch(d / "readme.txt")
    assert iter_input_videos(d, recursive=False) == []


def test_nonexistent_path_returns_empty_list(tmp_path):
    assert iter_input_videos(tmp_path / "nope", recursive=False) == []


# --- run_batch --- #

def test_run_batch_all_ok_no_die():
    videos = [Path("a.mkv"), Path("b.mkv")]
    processed = []
    run_batch(videos, processed.append, "test")
    assert processed == videos


def test_run_batch_one_raises_others_still_processed_then_dies():
    videos = [Path("a.mkv"), Path("b.mkv"), Path("c.mkv")]
    processed = []

    def process_one(v: Path) -> None:
        if v.name == "b.mkv":
            raise RuntimeError("boom")
        processed.append(v)

    with pytest.raises(SystemExit):
        run_batch(videos, process_one, "test")

    assert processed == [Path("a.mkv"), Path("c.mkv")]


def test_run_batch_one_calls_die_systemexit_others_still_processed():
    videos = [Path("a.mkv"), Path("b.mkv"), Path("c.mkv")]
    processed = []

    def process_one(v: Path) -> None:
        if v.name == "b.mkv":
            die("упало")
        processed.append(v)

    with pytest.raises(SystemExit):
        run_batch(videos, process_one, "test")

    assert processed == [Path("a.mkv"), Path("c.mkv")]


def test_run_batch_should_skip_prevents_process_one_call():
    videos = [Path("a.mkv"), Path("b.mkv")]
    processed = []

    def should_skip(v: Path):
        return "уже готов" if v.name == "a.mkv" else None

    run_batch(videos, processed.append, "test", should_skip=should_skip)

    assert processed == [Path("b.mkv")]
