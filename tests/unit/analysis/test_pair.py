"""ALN-02..04, D-14: оркестрация на подменённых frames-функциях, без ffmpeg."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytest

from enpipe.analysis import frames, pair
from enpipe.analysis.config import AnalysisError, AnalyzeConfig
from enpipe.analysis.model import (
    ALIGN_ALIGNED,
    ALIGN_SHIFT,
    ALIGN_UNDETERMINED,
    StreamInfo,
)

W, H = 64, 36
SRC = Path("src.mkv")
ENC = Path("enc.mkv")
SCENES4 = [(0, 24), (24, 48), (48, 72), (72, 96)]


def _frame(seed: int):
    rng = np.random.default_rng(seed)
    y = rng.integers(64, 940, size=(H, W), dtype=np.uint16)
    u = rng.integers(64, 960, size=(H // 2, W // 2), dtype=np.uint16)
    v = rng.integers(64, 960, size=(H // 2, W // 2), dtype=np.uint16)
    return (y, u, v)


def noisy_film(n: int = 96):
    return [_frame(i) for i in range(n)]


def static_film(n: int = 96):
    f = _frame(7)
    return [f] * n


def info(name: str, **kw) -> StreamInfo:
    base = dict(
        name=name,
        format_name="matroska,webm",
        codec_name="hevc",
        width=W,
        height=H,
        pix_fmt="yuv420p10le",
        avg_frame_rate=Fraction(24),
        start_time=0.0,
        color_range="tv",
        color_space="bt2020nc",
        color_transfer="smpte2084",
        color_primaries="bt2020",
    )
    base.update(kw)
    return StreamInfo(**base)


class Fake:
    """Подмена frames.*: словарь путь -> кадры, журнал вызовов grab."""

    def __init__(self, mp, films: Dict[Path, list], infos: Optional[Dict[Path, StreamInfo]] = None):
        self.films = films
        self.infos = infos or {}
        self.calls: List[Tuple[Path, int, int]] = []
        self.fail_grab_at: Optional[Tuple[Path, int]] = None
        self.fail_probe: Optional[Path] = None
        mp.setattr(frames, "probe_stream", self.probe)
        mp.setattr(frames, "pts_table", self.pts)
        mp.setattr(frames, "grab_frames", self.grab)

    def probe(self, path):
        if path == self.fail_probe:
            raise AnalysisError("ffprobe упал")
        return self.infos.get(path) or info(path.name)

    def pts(self, path, cache_dir=None):
        return [i / 24 for i in range(len(self.films[path]))]

    def grab(self, path, pts, first, count, width, height, threads=2):
        self.calls.append((path, first, count))
        if self.fail_grab_at == (path, first):
            raise AnalysisError("ffmpeg упал")
        return self.films[path][first : first + count]


@pytest.fixture
def fake(monkeypatch):
    def make(films, infos=None):
        return Fake(monkeypatch, films, infos)

    return make


CFG = AnalyzeConfig()


def test_aligned_pair_ok(fake):
    src = noisy_film()
    fake({SRC: src, ENC: src})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert chk.ok
    assert chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.reasons == ()
    assert chk.verdict.notes == ()


def test_shift_plus_one_refused(fake):
    src = noisy_film()
    enc = src[1:] + [src[-1]]
    fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert any("сдвиг +1" in r for r in chk.reasons)


def test_static_undetermined_with_retries(fake):
    f = fake({SRC: static_film(), ENC: static_film()})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert any("выровнено 0 из 5" in r for r in chk.reasons)
    enc_calls = [c for c in f.calls if c[0] == ENC]
    # 5 точек + повторы (не более align_retry_max на точку)
    assert len(enc_calls) > 5
    assert len(enc_calls) <= 5 * (1 + CFG.align_retry_max)


def test_precheck_fail_no_grab(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()}, {ENC: info("enc.mkv", width=32)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert f.calls == []
    assert chk.alignment is None
    assert any("размер различается" in r for r in chk.reasons)
    assert chk.reasons == chk.verdict.reasons


def test_probe_error_reason(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()})
    f.fail_probe = ENC
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment is None
    assert any(r.startswith("энкод:") for r in chk.reasons)
    assert f.calls == []


def test_point_error_reason(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 48)
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert any(r.startswith("точка 48:") for r in chk.reasons)
    # остальные точки обработаны
    assert chk.alignment.n_aligned == 4
    bad = [p for p in chk.alignment.points if p.enc_frame == 48]
    assert bad and bad[0].error


def test_partial_offset_hint_and_ok(fake):
    src = noisy_film()
    part = src[24:72]
    f = fake({SRC: src, ENC: part})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert not chk.ok
    assert chk.alignment is None
    assert any("--offset 24 (сцены 1..2)" in r for r in chk.reasons)
    assert f.calls == []
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=24, scenes=SCENES4)
    assert chk.ok
    assert chk.verdict.offset == 24


def test_window_single_grab(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    # точка 48 (середина) без scenes: одно окно 45..51 -> first 45, count 7
    assert (SRC, 45, 7) in f.calls
    assert sum(1 for c in f.calls if c == (ENC, 48, 1)) == 1

    f2 = fake({SRC: src, ENC: src})
    pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert (ENC, 23, 2) in f2.calls
    assert (SRC, 20, 8) in f2.calls


def test_jobs_deterministic(fake):
    src = noisy_film()
    enc = src[1:] + [src[-1]]
    fake({SRC: src, ENC: enc})
    a = pair.check_pair_files(SRC, ENC, CFG, jobs=1)
    b = pair.check_pair_files(SRC, ENC, CFG, jobs=2)
    assert a == b
    with pytest.raises(AnalysisError):
        pair.check_pair_files(SRC, ENC, CFG, jobs=0)
