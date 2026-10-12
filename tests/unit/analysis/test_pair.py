"""ALN-02..04, D-14: оркестрация на подменённых frames-функциях, без ffmpeg."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytest

from enpipe.analysis import align, frames, pair
from enpipe.analysis.config import AnalysisError, AnalyzeConfig, build_thresholds
from enpipe.analysis.model import (
    ALIGN_ALIGNED,
    ALIGN_SHIFT,
    ALIGN_UNDETERMINED,
    REPORT_REFUSED,
    FileAlignment,
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
            raise self.fail_grab_exc or AnalysisError("ffmpeg упал")
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
    # 401 кадр: цели [0, 100, 200, 300, 400], окрестность ±24. Повторы 96/196/
    # 296/396 рядом с целями пропущены, 444/448 за концом; остаются 48, 144, 148
    # и т.д.
    f = fake({SRC: static_film(401), ENC: static_film(401)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert any("выровнено 0 из 5" in r for r in chk.reasons)
    enc_calls = [c for c in f.calls if c[0] == ENC]
    assert len(enc_calls) > 5
    assert len(enc_calls) <= 5 * (1 + CFG.align_retry_max)
    assert sorted(c[1] for c in enc_calls) == [
        0, 48, 100, 144, 148, 200, 244, 248, 300, 344, 348, 400
    ]


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
    # остальные точки обработаны: выровнены 0, 24, 71, 95; засчитаны 0 и 71
    # (24 − 0 и 95 − 71 не больше sep = 24)
    assert chk.alignment.n_aligned == 2
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


# --------------------------------------------------------------------------- #
# Кадровый уровень и модель отказа
# --------------------------------------------------------------------------- #


def _check(src_film, enc_film, offset=0):
    n_src, n_enc = len(src_film), len(enc_film)
    return pair.PairCheck(
        verdict=PairVerdict(ok=True, offset=offset, notes=("пометка",)),
        src_info=info("src.mkv"),
        enc_info=info("enc.mkv"),
        src_pts=tuple(i / 24 for i in range(n_src)),
        enc_pts=tuple(i / 24 for i in range(n_enc)),
        alignment=FileAlignment(verdict=ALIGN_ALIGNED, offset=offset),
    )


def test_grab_frame_pair_aligned(fake):
    src = noisy_film()
    fake({SRC: src, ENC: src})
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 10, CFG)
    assert err is None
    assert fp.enc_frame == 10 and fp.src_frame == 10
    assert fp.alignment.verdict == ALIGN_ALIGNED
    assert np.array_equal(fp.src_planes[0], src[10][0])
    assert np.array_equal(fp.enc_planes[0], src[10][0])


def test_grab_frame_pair_local_shift(fake):
    src = noisy_film()
    enc = src[1:] + [src[-1]]
    fake({SRC: src, ENC: enc})
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, enc), 10, CFG)
    assert err is None
    assert fp.alignment.verdict == ALIGN_SHIFT and fp.alignment.shift == 1
    kind, shift, text = align.row_alignment(fp.alignment)
    assert kind == ALIGN_SHIFT and shift == 1 and text


def test_grab_frame_pair_edge_window(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 0, CFG)
    assert err is None
    assert (SRC, 0, 2) in f.calls
    assert fp.alignment.verdict == ALIGN_ALIGNED


def test_grab_frame_pair_error(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 10)
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 10, CFG)
    assert fp is None and "ffmpeg упал" in err


def test_grab_frame_pair_no_check(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    bad = pair.PairCheck(verdict=PairVerdict(ok=False, reasons=("x",)), reasons=("x",))
    fp, err = pair.grab_frame_pair(SRC, ENC, bad, 10, CFG)
    assert fp is None and err == "пара не прошла проверку"
    assert f.calls == []


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
    assert rep.alignment == chk.alignment


def test_refused_report_no_src_info(fake):
    f = fake({SRC: noisy_film(), ENC: noisy_film()})
    f.fail_probe = SRC
    chk = pair.check_pair_files(SRC, ENC, CFG)
    rep = pair.refused_report(_meta(), CFG, chk)
    assert rep.status == REPORT_REFUSED
    assert (rep.meta.width, rep.meta.height, rep.meta.fps) == (None, None, None)
    assert any(r.startswith("источник:") for r in rep.refusal_reasons)


# --------------------------------------------------------------------------- #
# Регрессии ревью: CR-01, WR-01, IN-01, WR-03
# --------------------------------------------------------------------------- #


def test_retry_does_not_double_count(fake):
    film = static_film(96)
    for i in range(44, 53):
        film[i] = _frame(1000 + i)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 1
    assert any("выровнено 1 из 5" in r for r in chk.reasons)
    assert sum(1 for c in f.calls if c == (ENC, 48, 1)) == 1


def test_retry_skips_junction_frames(fake):
    f = fake({SRC: static_film(200), ENC: static_film(200)})
    task = (
        SRC, ENC,
        [i / 24 for i in range(200)], [i / 24 for i in range(200)],
        align.AlignTarget(0), 0, W, H, CFG, frozenset({0, 47, 48}),
    )
    point, err = pair._point_worker(task)
    assert err is None and point.enc_frame == 0
    assert point.verdict == ALIGN_UNDETERMINED
    assert (ENC, 48, 1) not in f.calls
    assert (ENC, 96, 1) in f.calls and (ENC, 144, 1) in f.calls


def _full_check(**kw):
    src = noisy_film()
    base = _check(src, src)
    fields = dict(
        verdict=base.verdict, src_info=base.src_info, enc_info=base.enc_info,
        src_pts=base.src_pts, enc_pts=base.enc_pts, alignment=base.alignment,
    )
    fields.update(kw)
    return pair.PairCheck(**fields)


def test_grab_frame_pair_rejected_check(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    chk = _full_check(reasons=("pix_fmt различается",))
    fp, err = pair.grab_frame_pair(SRC, ENC, chk, 10, CFG)
    assert fp is None and err == "пара не прошла проверку"
    assert f.calls == []


def test_grab_frame_pair_not_aligned(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    for al in (FileAlignment(verdict=ALIGN_UNDETERMINED), None):
        fp, err = pair.grab_frame_pair(SRC, ENC, _full_check(alignment=al), 10, CFG)
        assert fp is None and err == "пара не прошла проверку"
    assert f.calls == []


def test_alignment_refusal_marks_verdict(fake):
    src = noisy_film()
    ok = fake({SRC: src, ENC: src})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=SCENES4)
    assert chk.ok and chk.verdict.ok is True
    enc = src[1:] + [src[-1]]
    ok.films[ENC] = enc
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.verdict.ok is False and chk.ok is False and chk.reasons


@pytest.mark.parametrize(
    "exc, text",
    [(TypeError("boom"), "TypeError: boom"), (MemoryError("oom"), "MemoryError: oom")],
)
def test_point_unexpected_exception(fake, exc, text):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 48)
    f.fail_grab_exc = exc
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert any(r.startswith(f"точка 48: {text}") for r in chk.reasons)
    # выровнены 0, 24, 71, 95; засчитаны 0 и 71 (разнос 24 не больше sep)
    assert chk.alignment.n_aligned == 2


def test_grab_frame_pair_unexpected_exception(fake):
    src = noisy_film()
    f = fake({SRC: src, ENC: src})
    f.fail_grab_at = (ENC, 10)
    f.fail_grab_exc = TypeError("boom")
    fp, err = pair.grab_frame_pair(SRC, ENC, _check(src, src), 10, CFG)
    assert fp is None and err == "TypeError: boom"


def test_retry_neighbour_not_independent(fake):
    film = static_film(189)
    for i in range(44, 53):
        film[i] = _frame(1000 + i)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert [p.enc_frame for p in chk.alignment.points] == [0, 47, 94, 141, 188]
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 1
    assert any("выровнено 1 из 5" in r for r in chk.reasons)
    assert (ENC, 48, 1) not in f.calls


def test_taken_neighbourhood():
    # занятые 23 и 24, окрестность ±24, отрицательные отброшены
    got = pair._taken_frames([align.AlignTarget(24, 1, True)], CFG)
    assert got == frozenset(range(0, 49))
    got = pair._taken_frames([align.AlignTarget(0), align.AlignTarget(47)], CFG)
    assert got == frozenset(range(0, 72))
    # sep = 16 (2W доминирует): 47 ± 16
    c2 = AnalyzeConfig(align_window=8, align_retry_step=17)
    assert pair._taken_frames([align.AlignTarget(47)], c2) == frozenset(range(31, 64))


# --- регрессии ревью: WR-05 (вспышка движения — одно место файла) -----------


@pytest.mark.parametrize("lo, hi, n_al", [(41, 50, 1), (41, 49, 1), (89, 97, 0)])
def test_flash_is_one_place(fake, lo, hi, n_al):
    # n=165: цели [0, 41, 82, 123, 164], окрестность ±24 закрывает повторы
    # 48, 89, 96; вспышка движения не даёт второго голоса.
    film = static_film(165)
    for i in range(lo, hi):
        film[i] = _frame(1000 + i)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == n_al
    assert any(f"выровнено {n_al} из 5" in r for r in chk.reasons)
    assert [p.enc_frame for p in chk.alignment.points] == [0, 41, 82, 123, 164]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 41, 82, 123, 164]


def test_retries_far_apart_aligned(fake):
    # n=401: повтор цели 0 на 48 (движение 45..51) и повтор цели 100 на 148
    # (движение 145..151) — разные места, D-11 работает.
    film = static_film(401)
    for i in list(range(45, 52)) + list(range(145, 152)):
        film[i] = _frame(1000 + i)
    fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is True
    assert chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 2
    assert [p.enc_frame for p in chk.alignment.points][:2] == [48, 148]


def test_retries_same_flash_one_vote(fake):
    # n=401, движение 140..152: повторы 144 (цель 0 после 48 и пропущенного 96)
    # и 148 (цель 100) — одна вспышка, разнос 4 <= 24, один голос.
    film = static_film(401)
    for i in range(140, 153):
        film[i] = _frame(1000 + i)
    fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 1
    assert any("выровнено 1 из 5" in r for r in chk.reasons)
    pts = {(p.enc_frame, p.verdict) for p in chk.alignment.points}
    assert (144, ALIGN_ALIGNED) in pts and (148, ALIGN_ALIGNED) in pts


def test_static_121_retries_skipped(fake):
    # Известное следствие (IN-08): на 121 кадре все повторы в окрестности ±24
    # чужих целей и пропускаются; вердикт «неопределённо» без повторов.
    f = fake({SRC: static_film(121), ENC: static_film(121)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert any("выровнено 0 из 5" in r for r in chk.reasons)
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 30, 60, 90, 120]


def test_short_encode_undetermined(fake):
    film = noisy_film(7)
    fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.alignment is not None
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 1
    assert any("выровнено 1 из 5" in r for r in chk.reasons)
    assert [p.enc_frame for p in chk.alignment.points] == [0, 2, 3, 5, 6]
