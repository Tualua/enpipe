"""ALN-02..04, D-24..D-27: предпроверка пары на подменённых frames-функциях, без ffmpeg."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytest

from enpipe.analysis import frames, pair
from enpipe.analysis.config import AnalysisError, AnalyzeConfig, build_thresholds
from enpipe.analysis.model import (
    REPORT_REFUSED,
    PairVerdict,
    RunMeta,
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
        self.fail_grab_exc: Optional[BaseException] = None
        # WR-10: индексы ключевых кадров по файлам; по умолчанию ключевой каждый кадр,
        # поэтому сверка .scenes с энкодом в тестах проходит.
        self.keyframes: Dict[Path, Tuple[int, ...]] = {}
        mp.setattr(frames, "probe_stream", self.probe)
        mp.setattr(frames, "pts_table", self.pts)
        mp.setattr(frames, "packet_table", self.packets)
        mp.setattr(frames, "grab_frames", self.grab)

    def probe(self, path):
        if path == self.fail_probe:
            raise AnalysisError("ffprobe упал")
        return self.infos.get(path) or info(path.name)

    def pts(self, path, cache_dir=None):
        return [i / 24 for i in range(len(self.films[path]))]

    def packets(self, path, cache_dir=None):
        return (
            self.pts(path),
            self.keyframes.get(path, tuple(range(len(self.films[path])))),
        )

    def grab(self, path, pts, first, count, width, height, threads=2):
        self.calls.append((path, first, count))
        if self.fail_grab_at == (path, first):
            raise self.fail_grab_exc or AnalysisError("ffmpeg упал")
        return self.films[path][first : first + count]


@pytest.fixture
def fake(monkeypatch):
    def make(films, infos=None):
        return Fake(monkeypatch, films, infos)

    return make


CFG = AnalyzeConfig()

def test_pair_ok_no_grab(fake):
    src = static_film()
    f = fake({SRC: src, ENC: src})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert chk.ok
    assert chk.reasons == ()
    assert chk.verdict.notes == ()
    assert f.calls == []  # D-24/D-27: кадры не извлекаются вообще


def test_precheck_fail_no_grab(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()}, {ENC: info("enc.mkv", width=32)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert f.calls == []
    assert any("размер различается" in r for r in chk.reasons)
    assert chk.reasons == chk.verdict.reasons


def test_probe_error_reason(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()})
    f.fail_probe = ENC
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert any(r.startswith("энкод:") for r in chk.reasons)
    assert f.calls == []


def test_partial_offset_hint_and_ok(fake):
    src = noisy_film()
    part = src[24:72]
    f = fake({SRC: src, ENC: part})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert not chk.ok
    assert any("--offset 24 (сцены 1..2)" in r for r in chk.reasons)
    assert f.calls == []
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=24, scenes=SCENES4)
    assert chk.ok
    assert chk.verdict.offset == 24
    assert f.calls == []


def test_offset_without_scenes_refused_no_grab(fake):
    """D-26: --offset без .scenes (None или []) — отказ до извлечения кадров."""
    src = noisy_film()
    f = fake({SRC: src, ENC: src[24:72]})
    for sc in (None, []):
        chk = pair.check_pair_files(SRC, ENC, CFG, offset=24, scenes=sc)
        assert not chk.ok
        assert any("без .scenes" in r for r in chk.reasons)
        assert chk.verdict.offset_source is None
        assert f.calls == []


# --- Модель Young Sherlock S01E01 (G-10-1) -------------------------------------

YS_N = 73600


def _ys_scenes():
    # 40 сцен до кадра 4737, затем 40..42 длиной 75/74/80, дальше редкие склейки
    starts = [i * 118 for i in range(39)] + [4602]
    starts += [4737, 4812, 4886, 4966]
    starts += list(range(5466, 73498, 500)) + [73498]
    return _sc(starts, n=YS_N)


def _ys_film(n):
    f = _frame(7)  # статичный/чёрный фильм: PSNR-проверка здесь давала ложный отказ
    return [f] * n


def test_young_sherlock_full_pair_ok(fake):
    sc = _ys_scenes()
    assert sc[40][0] == 4737 and (73498, YS_N) in sc
    film = _ys_film(YS_N)
    f = fake({SRC: film, ENC: film})
    f.keyframes[ENC] = tuple(sorted({s for s, _ in sc} | set(range(0, YS_N, 300))))
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=sc)
    assert chk.ok is True and chk.reasons == ()
    assert f.calls == []


def test_young_sherlock_partial_offset_scenes_ok(fake):
    sc = _ys_scenes()
    assert [e - s for s, e in sc[40:43]] == [75, 74, 80]
    f = fake({SRC: _ys_film(YS_N), ENC: _ys_film(229)})
    f.keyframes[ENC] = (0, 75, 149)
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=sc)
    assert chk.ok is False
    assert any("--offset 4737 (сцены 40..42)" in r for r in chk.reasons)
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=4737, scenes=sc)
    assert chk.ok is True and chk.reasons == ()
    assert chk.verdict.offset == 4737 and chk.verdict.offset_source == "scenes"
    assert f.calls == []


def test_young_sherlock_partial_offset_without_scenes_refused(fake):
    f = fake({SRC: _ys_film(YS_N), ENC: _ys_film(229)})
    f.keyframes[ENC] = (0, 75, 149)
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=4737, scenes=None)
    assert chk.ok is False
    assert any("без .scenes" in r for r in chk.reasons)
    assert f.calls == []


# --- grab_frame_pair (D-27) ---------------------------------------------------


def _check(src_film, enc_film, offset=0):
    n_src, n_enc = len(src_film), len(enc_film)
    return pair.PairCheck(
        verdict=PairVerdict(ok=True, offset=offset, notes=("пометка",)),
        src_info=info("src.mkv"),
        enc_info=info("enc.mkv"),
        src_pts=tuple(i / 24 for i in range(n_src)),
        enc_pts=tuple(i / 24 for i in range(n_enc)),
    )


def test_grab_frame_pair_two_frames_only(fake):
    src = noisy_film()
    enc = src[24:72]
    f = fake({SRC: src, ENC: enc})
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, enc, offset=24), 10)
    assert err is None
    assert fp.enc_frame == 10 and fp.src_frame == 34
    assert np.array_equal(fp.src_planes[0], src[34][0])
    assert np.array_equal(fp.enc_planes[0], src[34][0])
    assert f.calls == [(ENC, 10, 1), (SRC, 34, 1)]  # без соседей N±1


def test_grab_frame_pair_edge_frames(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    for n in (0, 95):
        fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), n)
        assert err is None and fp.src_frame == n
    assert all(c[2] == 1 for c in f.calls)


def test_grab_frame_pair_out_of_file(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    for n in (-1, 96):
        fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), n)
        assert fp is None and "вне файла" in err
    assert f.calls == []


def test_grab_frame_pair_error(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 10)
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 10)
    assert fp is None and "ffmpeg упал" in err


def test_grab_frame_pair_no_check(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    bad = pair.PairCheck(verdict=PairVerdict(ok=False, reasons=("x",)), reasons=("x",))
    fp, err = pair.grab_frame_pair(SRC, ENC, bad, 10)
    assert fp is None and err == "пара не прошла проверку"
    assert f.calls == []


def test_grab_frame_pair_rejected_check(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    base = _check(src, src)
    chk = pair.PairCheck(
        verdict=base.verdict, src_info=base.src_info, enc_info=base.enc_info,
        src_pts=base.src_pts, enc_pts=base.enc_pts, reasons=("pix_fmt различается",),
    )
    fp, err = pair.grab_frame_pair(SRC, ENC, chk, 10)
    assert fp is None and err == "пара не прошла проверку"
    assert f.calls == []


def test_grab_frame_pair_unexpected_exception(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 10)
    f.fail_grab_exc = TypeError("boom")
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 10)
    assert fp is None and err == "TypeError: boom"


def _meta(**kw):
    base = dict(
        src_name="a.mkv", enc_name="b.mkv", enpipe_version="1.0", created_at="t",
        width=1920, height=800, fps=24.0, frame_count=100,
    )
    base.update(kw)
    return RunMeta(**base)


def test_meta_with_check():
    src = noisy_film()
    m = pair.meta_with_check(_meta(), _check(src, src[:48], offset=24))
    assert (m.width, m.height, m.fps, m.frame_count) == (W, H, 24.0, 48)
    assert m.offset == 24 and m.notes == ("пометка",)
    assert m.src_name == "a.mkv" and m.enpipe_version == "1.0" and m.created_at == "t"


def test_meta_with_check_no_src_info():
    chk = pair.PairCheck(verdict=PairVerdict(ok=False, reasons=("x",)), reasons=("x",))
    m = pair.meta_with_check(_meta(), chk)
    assert (m.width, m.height, m.fps, m.frame_count) == (None, None, None, None)
    src = noisy_film()
    base = _check(src, src)
    no_rate = pair.PairCheck(
        verdict=base.verdict, src_info=info("s", avg_frame_rate=None), enc_pts=base.enc_pts
    )
    assert pair.meta_with_check(_meta(), no_rate).fps is None
    empty = pair.PairCheck(verdict=base.verdict, src_info=base.src_info)
    assert pair.meta_with_check(_meta(), empty).frame_count is None


def test_refused_report_model(fake):
    src = noisy_film()
    fake({SRC: src, ENC: src[24:72]})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    rep = pair.refused_report(_meta(), CFG, chk)
    assert rep.status == REPORT_REFUSED
    assert rep.refusal_reasons == chk.reasons
    assert rep.frames == () and rep.candidates == () and rep.summary == ()
    assert rep.thresholds == build_thresholds(CFG)


def test_refused_report_no_src_info(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()})
    f.fail_probe = SRC
    chk = pair.check_pair_files(SRC, ENC, CFG)
    rep = pair.refused_report(_meta(), CFG, chk)
    assert rep.status == REPORT_REFUSED
    assert (rep.meta.width, rep.meta.height, rep.meta.fps) == (None, None, None)
    assert any(r.startswith("источник:") for r in rep.refusal_reasons)


# --------------------------------------------------------------------------- #
# Общие хелперы для WR-10/WR-11
# --------------------------------------------------------------------------- #

JSTARTS = [0, 250, 500, 600, 750, 900]
POFF = 100
PN = 402
PSCENES = [(0, 100), (100, 175), (175, 249), (249, 502), (502, 600)]


def _sc(starts, n=1000):
    return list(zip(starts, list(starts[1:]) + [n]))


def _partial():
    """Частичный энкод: src на 600 кадров, enc = src[POFF:POFF+PN]."""
    src = noisy_film(600)
    return src, list(src[POFF : POFF + PN])


# --------------------------------------------------------------------------- #
# WR-10: сверка .scenes с энкодом (решение оператора 2026-11-07)
# --------------------------------------------------------------------------- #


# Полный энкод, а ключевой кадр энкода 600 отсутствует: .scenes не тот, по которому шёл
# энкод. На HEAD 68ec633 полный энкод сцены не смотрел и давал ok True.
def test_scenes_keyframe_mismatch_refused(fake):
    film = noisy_film(1000)
    f = fake({SRC: film, ENC: film})
    f.keyframes[ENC] = (0, 250, 500, 750, 900)
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is False
    assert f.calls == []
    assert any("не на ключевых кадрах энкода" in r and "600" in r for r in chk.reasons)


# Лишние ключевые кадры внутри чанков (GOP_LEN) допустимы: условие необходимое, не достаточное.
def test_scenes_gop_keyframes_ok(fake):
    film = noisy_film(1000)
    f = fake({SRC: film, ENC: film})
    f.keyframes[ENC] = (0, 100, 250, 300, 500, 600, 750, 900)
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is True


# Устаревший .scenes (на 10 кадров короче источника) на полном энкоде: раньше сцены не
# смотрелись и пара принималась.
def test_scenes_stale_full_encode_refused(fake):
    film = noisy_film(1000)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS, n=990))
    assert chk.ok is False
    assert f.calls == []
    assert any(
        ".scenes: последняя сцена кончается на кадре 990, в источнике 1000 кадров" in r
        for r in chk.reasons
    )


def test_scenes_gap_full_encode_refused(fake):
    film = noisy_film(1000)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=[(0, 250), (260, 1000)])
    assert chk.ok is False and f.calls == []
    assert any("не идут подряд" in r for r in chk.reasons)


# Частичный энкод: окно [100, 502), начало 175 -> кадр энкода 75 обязан быть ключевым.
def test_scenes_partial_keyframes_refused(fake):
    src, enc = _partial()
    f = fake({SRC: src, ENC: enc})
    f.keyframes[ENC] = (0, 149)
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=POFF, scenes=PSCENES)
    assert chk.ok is False
    assert any("не на ключевых кадрах энкода" in r and "75" in r for r in chk.reasons)
    f.keyframes[ENC] = (0, 75, 149)
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=POFF, scenes=PSCENES)
    assert chk.ok is True


# --------------------------------------------------------------------------- #
# WR-11: конец окна --offset
# --------------------------------------------------------------------------- #


# Окно энкода кончается на кадре 64 внутри сцены [48, 72): отказ до извлечения кадров.
def test_partial_window_end_refused(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src[24:64]})
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=24, scenes=SCENES4)
    assert chk.ok is False
    assert f.calls == []
    assert any("не конец ни одной сцены" in r for r in chk.reasons)
    # контроль: окно до конца сцены принимается
    fake({SRC: src, ENC: src[24:72]})
    assert pair.check_pair_files(SRC, ENC, CFG, offset=24, scenes=SCENES4).ok

