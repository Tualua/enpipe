"""D-08: cross-validation of the isolated enpipe.mkv.ebml split against
BOTH independent oracles -- (a) legacy/encode_scenes.py's inline
keyframe_table_cues (loaded in isolation via importlib, the parity
oracle) and (b) keyframe_table_ffprobe (the trusted slow full-file scan)
-- on a real synthetic .mkv generated with ffmpeg.

Needs only ffmpeg + libx264 (no GPU/QSV), so this runs in the default
("not hardware") tier per ROADMAP/RESEARCH.md's resolved open question --
it lives under tests/integration/ (not tests/unit/) because it does a
real (if fast, <1s) subprocess call and generates a real file, unlike the
purely in-memory byte-fixture tests in tests/unit/mkv/test_ebml.py."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

import pytest

from enpipe.encoding.keyframes import keyframe_table_cues, keyframe_table_ffprobe

_LEGACY_PATH = Path(__file__).resolve().parents[2] / "legacy" / "encode_scenes.py"

_FFMPEG = shutil.which("ffmpeg")


def _probe_has_libx264() -> bool:
    if _FFMPEG is None:
        return False
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True, text=True,
    )
    return "libx264" in proc.stdout


_HAS_LIBX264 = _probe_has_libx264()

_EXPECTED_TABLE: List[Tuple[int, float]] = [(0, 0.0), (12, 0.5), (24, 1.0), (36, 1.5)]


def _load_legacy_keyframe_table_cues():
    """Loads legacy/encode_scenes.py in an ISOLATED module namespace via
    importlib.util (never imported normally -- legacy/ stays untouched as
    the frozen parity oracle, D-11). Its module-level `_START =
    time.monotonic()` and other top-level statements execute harmlessly
    in this throwaway module; the `if __name__ == "__main__":` guard
    keeps main() from running."""
    spec = importlib.util.spec_from_file_location("legacy_encode_scenes", _LEGACY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.keyframe_table_cues


@pytest.mark.skipif(not _HAS_LIBX264, reason="ffmpeg+libx264 required")
def test_cues_parser_matches_ffprobe_and_legacy(tmp_path: Path) -> None:
    mkv = tmp_path / "synthetic.mkv"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24:duration=2",
            "-c:v", "libx264", "-g", "12", "-keyint_min", "12", "-sc_threshold", "0",
            "-pix_fmt", "yuv420p", "-f", "matroska", "-cues_to_front", "1", str(mkv),
        ],
        check=True, capture_output=True,
    )

    fps = 24.0
    fast = keyframe_table_cues(mkv, fps)
    slow = keyframe_table_ffprobe(mkv, fps)
    legacy_keyframe_table_cues = _load_legacy_keyframe_table_cues()
    legacy = legacy_keyframe_table_cues(mkv, fps)

    assert fast is not None
    assert fast == slow == legacy == _EXPECTED_TABLE
