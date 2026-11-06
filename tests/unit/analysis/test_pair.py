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
    # 401 кадр, без .scenes: цели [0, 100, 200, 300, 400]. Повторы вперёд
    # сдвигаются за окрестность ±24 (а), у последней цели идут назад (общий
    # лимит align_retry_max = 3 на точку): 5 · (1 + 3) = 20 декодов.
    f = fake({SRC: static_film(401), ENC: static_film(401)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert any("выровнено 0 из 5" in r for r in chk.reasons)
    assert any(
        "неопределённые точки (кадры энкода): 0, 100, 200, 300, 400" in r
        for r in chk.reasons
    )
    enc_calls = [c for c in f.calls if c[0] == ENC]
    assert len(enc_calls) == 5 * (1 + CFG.align_retry_max)
    assert sorted(c[1] for c in enc_calls) == [
        0, 48, 100, 125, 148, 173, 175, 200, 225, 227, 248, 252, 273, 275, 300, 325,
        348, 352, 373, 400,
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


# (а), вариант 1 WR-06: повтор 48 попадает в taken и сдвигается на 49, дальше шаг
# отсчитывается от сдвинутого кадра: 97, 145 (дрейф сетки).
def test_retry_shifts_past_taken(fake):
    f = fake({SRC: static_film(200), ENC: static_film(200)})
    task = (
        SRC, ENC,
        [i / 24 for i in range(200)], [i / 24 for i in range(200)],
        align.AlignTarget(0), 0, W, H, CFG, frozenset({0, 47, 48}), (),
    )
    pts, err = pair._point_worker(task)
    assert err is None and len(pts) == 1
    point = pts[0]
    assert point.enc_frame == 0
    assert point.verdict == ALIGN_UNDETERMINED
    assert (ENC, 48, 1) not in f.calls
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 49, 97, 145]


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


def _moving(film, *ranges):
    """Копия плёнки, где кадры заданных диапазонов (включительно) подвижны."""
    out = list(film)
    for lo, hi in ranges:
        for i in range(lo, hi + 1):
            out[i] = _frame(1000 + i)
    return out


# (в) + (а): пять разных мест файла, все цели получают определённый вердикт
# через повторы вперёд и назад: выровнено.
def test_retries_far_apart_aligned(fake):
    film = _moving(static_film(401), (45, 51), (145, 151), (245, 251), (345, 351), (394, 400))
    fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is True
    assert chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 5
    assert [p.enc_frame for p in chk.alignment.points] == [48, 148, 248, 348, 400]


# Раньше этот файл был «выровнено» (2 голоса при 3 «неопределённо»): по (в)
# оставшиеся точки 200, 300, 400 блокируют «выровнено».
def test_two_places_not_enough(fake):
    film = _moving(static_film(401), (45, 51), (145, 151))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 2
    assert any("неопределённые точки (кадры энкода): 200, 300, 400" in r for r in chk.reasons)
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 48, 100, 148, 175, 200, 227, 248, 252, 275, 300, 325, 348, 352, 373, 400
    ]


def test_retries_same_flash_one_vote(fake):
    # Движение 122..151: повторы 125 (цель 0 после сдвига) и 148 (цель 100) — одна
    # вспышка, разнос 23 <= 24, один голос.
    film = _moving(static_film(401), (122, 151))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=None)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 1
    pts = {(p.enc_frame, p.verdict) for p in chk.alignment.points}
    assert (125, ALIGN_ALIGNED) in pts and (148, ALIGN_ALIGNED) in pts
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 48, 100, 125, 148, 175, 200, 227, 248, 252, 275, 300, 325, 348, 352, 373, 400
    ]


# WR-06 (решение оператора 2026-10-24): повтор (а) сдвигается за окрестность чужих
# целей, при нехватке кадров вперёд идут повторы назад, общий лимит
# align_retry_max на точку. Повторные декоды одного кадра разными точками
# ожидаемы (воркеры параллельны), голоса считает aggregate по уникальным кадрам.
# Числа покрытия закреплены test_taken_coverage_numbers.
@pytest.mark.parametrize(
    "n, enc",
    [
        (48, [0, 12, 24, 35, 47]),
        (197, [0, 49, 98, 147, 196]),
        (198, [0, 49, 74, 74, 74, 99, 148, 197]),
        (225, [0, 31, 31, 31, 56, 81, 87, 87, 112, 137, 137, 143, 168, 193, 193, 193, 224]),
        (226, [0, 31, 31, 31, 56, 81, 88, 88, 113, 138, 138, 144, 169, 194, 194, 194, 225]),
        (241, [0, 35, 35, 35, 60, 85, 95, 95, 120, 145, 145, 155, 180, 205, 205, 205, 240]),
        (289, [0, 47, 47, 47, 72, 97, 119, 119, 144, 169, 169, 191, 216, 241, 241, 241, 288]),
    ],
)
def test_retries_via_worker(fake, n, enc):
    f = fake({SRC: static_film(n), ENC: static_film(n)})
    pair.check_pair_files(SRC, ENC, CFG)
    targets = align.pick_points(n, None, 0, CFG)
    taken = pair._taken_frames(targets, CFG)
    got = sorted(c[1] for c in f.calls if c[0] == ENC)
    assert got == enc
    expect = [t.enc_frame for t in targets]
    for t in targets:
        expect += align.retry_frames(t.enc_frame, n, CFG, taken)
    assert got == sorted(expect)
    if n == 48:
        # повторов нет вообще, а не «отпали»: свободных кадров нет
        assert all(not align.retry_frames(t.enc_frame, 48, CFG, taken) for t in targets)


def _free(n):
    taken = pair._taken_frames(align.pick_points(n, None, 0, CFG), CFG)
    return sum(1 for f in range(n) if f not in taken)


# Решение оператора (IN-15 + 198..225, 2026-10-23): без .scenes при n <= 197
# окрестности покрывают весь файл, на 198..225 свободные кадры есть при каждой
# длине (на 225 их 28), на 241 их 44, на 289 — 92.
def test_taken_coverage_numbers():
    assert all(_free(n) == 0 for n in range(1, 198))
    assert all(_free(n) > 0 for n in range(198, 226))
    assert (_free(225), _free(241), _free(289)) == (28, 44, 92)


def _retries_of(n):
    targets = align.pick_points(n, None, 0, CFG)
    taken = pair._taken_frames(targets, CFG)
    return [align.retry_frames(t.enc_frame, n, CFG, taken) for t in targets]


def test_retries_absent_up_to_197():
    for n in range(1, 198):
        assert all(r == [] for r in _retries_of(n)), n


def test_retries_present_from_198():
    for n in range(198, 601):
        assert any(r for r in _retries_of(n)), n


# Со .scenes: цель 48 получает повтор 96, цели 143 и 191 — повторы назад 95 и 118;
# склейки 0 и 152 замен не получают (единственный другой кандидат в taken).
# Склейка 0 получает повтор 73 в своей сцене [0, 152). У склейки 152 повторов нет:
# вперёд кадров нет, а повтор назад 104 лежит в предыдущей сцене и отбрасывается
# (CR-01: сцена — чанк, чужой чанк сдвиг склейки не покажет).
def test_retries_with_scenes_example(fake):
    f = fake({SRC: static_film(192), ENC: static_film(192)})
    pair.check_pair_files(SRC, ENC, CFG, scenes=[(0, 152), (152, 192)])
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 48, 73, 95, 96, 118, 143, 151, 191
    ]


# Нет свободных кадров: повторов нет ни вперёд, ни назад.
def test_static_121_no_free_frames(fake):
    f = fake({SRC: static_film(121), ENC: static_film(121)})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert any("выровнено 0 из 5" in r for r in chk.reasons)
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 30, 60, 90, 120]


# Контрпример (в): цели 0/56/112 «выровнено», 168/224 «неопределённо», сдвиг виден
# только на непроверенных кадрах 186..200. На HEAD 5a2abae давало ok True.
def test_hidden_shift_not_aligned_225(fake):
    src = static_film(225)
    for c in (0, 56, 112):
        for i in range(max(0, c - 4), c + 5):
            src[i] = _frame(c * 10 + i + 1)
    for i in range(186, 201):
        src[i] = _frame(5000 + i)
    enc = list(src)
    for i in range(186, 201):
        enc[i] = src[i + 1]
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 3
    assert any("неопределённые точки (кадры энкода): 168, 224" in r for r in chk.reasons)
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 31, 31, 56, 87, 87, 112, 143, 168, 224
    ]


# Контрпример (а): цель 72 статична, её повтор 97 после сдвига за окрестность
# попадает в сдвинутую зону 85..110.
def test_shift_found_by_shifted_retry_289(fake):
    src = noisy_film(289)
    for i in range(4):
        src[i] = _frame(7)
    enc = list(src)
    for i in range(85, 111):
        enc[i] = src[i + 1]
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is False
    assert chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert (97, ALIGN_SHIFT) in {(p.enc_frame, p.verdict) for p in chk.alignment.points}
    assert any("сдвиг +1" in r for r in chk.reasons)
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 72, 97, 144, 216, 288]


# --- крайние точки: повтор назад ------------------------------------------------


def _static_tail(n, k):
    film = noisy_film(n)
    for i in range(n - k, n):
        film[i] = _frame(7)
    return film


def _static_head(n, k):
    film = noisy_film(n)
    for i in range(k):
        film[i] = _frame(7)
    return film


def test_edge_tail_30_backward_retry(fake):
    film = _static_tail(401, 30)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 5
    assert [p.enc_frame for p in chk.alignment.points] == [0, 100, 200, 300, 352]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 100, 200, 300, 352, 400]


def test_edge_tail_120_aligned(fake):
    film = _static_tail(2401, 120)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert [p.enc_frame for p in chk.alignment.points] == [0, 600, 1200, 1800, 2256]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 600, 1200, 1800, 2256, 2304, 2352, 2400
    ]


def test_edge_tail_200_refused(fake):
    film = _static_tail(2401, 200)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 4
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 2400")
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 600, 1200, 1800, 2256, 2304, 2352, 2400
    ]


def test_edge_head_200_refused(fake):
    film = _static_head(2401, 200)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG)
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 0")
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 48, 96, 144, 600, 1200, 1800, 2400
    ]


# --- замены склеек (решения оператора 2026-10-24: 1б, 2б, 3а) ----------------------

JSTARTS = [0, 250, 500, 600, 750, 900]


def _sc(starts, n=1000):
    return list(zip(starts, list(starts[1:]) + [n]))


def _static_ranges(film, *ranges):
    out = list(film)
    for lo, hi in ranges:
        for i in range(lo, hi + 1):
            out[i] = _frame(7)
    return out


def test_junction_all_noisy(fake):
    film = noisy_film(1000)
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is True
    assert [p.enc_frame for p in chk.alignment.points] == [0, 250, 500, 750, 900]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 749, 899]


# Статичная склейка 500: замена 600 «выровнено» — только голос (WR-09), цель
# закрывает повтор 548 внутри её сцены [500, 600).
def test_junction_replaced_by_next(fake):
    film = _static_ranges(noisy_film(1000), (490, 510))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 6
    assert [p.enc_frame for p in chk.alignment.points] == [0, 250, 548, 600, 750, 900]
    assert [p.scene for p in chk.alignment.points][3] == 3
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 548, 599, 749, 899]


# Последняя склейка 900 статична, следующих нет: замена назад на 600 — голос (WR-09),
# цель закрывает повтор 948 в её сцене [900, 1000).
def test_junction_replaced_backward(fake):
    film = _static_ranges(noisy_film(1000), (890, 910))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert [p.enc_frame for p in chk.alignment.points] == [0, 250, 500, 600, 750, 948]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 599, 749, 899, 948]


# Статичны 500 и 600: замена 600 «неопределённо», остаток лимита 2 -> повторы 548 и 596
# (оба статичны), третий повтор 644 не берётся; отказ с точкой 500.
def test_junction_candidates_exhausted(fake):
    film = _static_ranges(noisy_film(1000), (490, 610))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 4
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 548, 596, 599, 749, 899]


# Без замены склеек файл был бы «выровнено» (4 A + 1 U до (в)) или отказом без
# сдвига: сдвиг виден только на замене 600.
def test_junction_replacement_shift(fake):
    src = _static_ranges(noisy_film(1000), (490, 510))
    enc = list(src)
    for i in range(590, 611):
        enc[i] = src[i + 1]
    fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert any("сдвиг +1" in r and "в точке энкода 600" in r for r in chk.reasons)


# 2б: кандидат 610 отстоит от замены 600 на 10 <= 24 и не проверяется.
def test_junction_replacement_spacing(fake):
    starts = [0, 250, 500, 600, 610, 750, 900]
    film = _static_ranges(noisy_film(1000), (490, 615))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(starts))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 548, 596, 599, 749, 899]


# Одна склейка-замена у двух целей (250 и 500): запрошена у обеих, голос один (WR-09:
# замена — голос, цели закрывают повторы в своих сценах: 298 в [250, 500), 548 в [500, 560)).
def test_junction_shared_replacement(fake):
    starts = [0, 250, 500, 560, 620, 680, 700, 750, 900]
    film = _static_ranges(noisy_film(1000), (240, 260), (490, 510))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(starts))
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 5
    assert [p.enc_frame for p in chk.alignment.points] == [0, 298, 548, 560, 560, 750, 900]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [
        0, 249, 298, 499, 548, 559, 559, 749, 899
    ]


# 3а: две склейки с одним кадром (600, 600) схлопываются, 599 запрошен один раз;
# замена 600 — голос (WR-09), цель 500 закрывает повтор 548 в сцене [500, 600).
def test_junction_duplicate_start(fake):
    sc = [(0, 250), (250, 500), (500, 600), (600, 600), (600, 750), (750, 900), (900, 1000)]
    film = _static_ranges(noisy_film(1000), (490, 510))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=sc)
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert [p.enc_frame for p in chk.alignment.points] == [0, 250, 548, 600, 750, 900]
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == [0, 249, 499, 548, 599, 749, 899]


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


# --- WR-08: повторы склеек после замен, общий лимит (решение оператора 2026-11-05) ---

POFF = 100
PN = 402
PSCENES = [(0, 100), (100, 175), (175, 249), (249, 502), (502, 600)]


def _partial(*static, shift=None):
    """Частичный энкод: src на 600 кадров, enc = src[POFF:POFF+PN]."""
    rng = [(lo + POFF, hi + POFF) for lo, hi in static]
    src = _static_ranges(noisy_film(600), *rng)
    enc = list(src[POFF : POFF + PN])
    if shift is not None:
        for i in range(shift[0], shift[1] + 1):
            enc[i] = src[POFF + i + 1]
    return src, enc


def _enc_calls(f):
    return sorted((c[1], c[2]) for c in f.calls if c[0] == ENC)


# Синтетика повторяет UAT тест 9 (Young Sherlock S01E01, сцены 40..42, --offset 4737).
# Склейки 75 и 149 «неопределённо», замен нет: все склейки энкода уже цели.
def test_partial_junctions_retried_aligned(fake):
    src, enc = _partial((70, 80), (144, 154))
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=POFF, scenes=PSCENES)
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.n_aligned == 5
    assert [p.enc_frame for p in chk.alignment.points] == [0, 123, 197, 301, 401]
    assert _enc_calls(f) == [
        (0, 1), (74, 2), (123, 1), (148, 2), (197, 1), (301, 1), (401, 1)
    ]


# Повтор склейки со сдвигом даёт вердикт файла «сдвиг», а не потерянное «выровнено».
def test_partial_junction_retry_shift(fake):
    src, enc = _partial((70, 80), (144, 154), shift=(190, 205))
    fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=POFF, scenes=PSCENES)
    assert chk.ok is False and chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert any("сдвиг +1" in r and "в точке энкода 197" in r for r in chk.reasons)


# Все повторы склеек «неопределённо»: отказ. CR-01: повторы только в своей сцене —
# у склейки 75 один повтор 123 (сцена [75, 149)), у склейки 149 три (197, 245, 326).
# Повторы 174 и 222 склейки 75 лежат за концом её сцены и не запрашиваются; статичные
# диапазоны (171, 177), (219, 225) защищают от возврата этих кадров (М9).
def test_partial_junction_retries_all_undetermined(fake):
    src, enc = _partial(
        (70, 80), (120, 126), (144, 154), (171, 177), (194, 200), (219, 225),
        (242, 248), (323, 329),
    )
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, offset=POFF, scenes=PSCENES)
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 3
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 75, 149")
    assert _enc_calls(f) == [
        (0, 1), (74, 2), (123, 1), (148, 2), (197, 1),
        (245, 1), (301, 1), (326, 1), (401, 1),
    ]


# WR-08 из 10-REVIEW.md: склейка на кадре 0 статична; до правки с .scenes был отказ
# «неопределённые точки (кадры энкода): 0». Повтор склейки меряется одиночным кадром
# (count всегда 1), поэтому достаточно сравнивать first.
@pytest.mark.parametrize(
    "scenes,expected",
    [
        pytest.param(None, [0, 48, 250, 500, 749, 999], id="no_scenes"),
        pytest.param([(0, 1000)], [0, 48, 250, 500, 749, 999], id="one_scene"),
        pytest.param(
            [(0, 500), (500, 1000)], [0, 48, 250, 499, 749, 999], id="two_scenes"
        ),
    ],
)
def test_junction_zero_retry(fake, scenes, expected):
    film = _static_ranges(noisy_film(1000), (0, 29))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=scenes)
    assert chk.ok is True and chk.alignment.verdict == ALIGN_ALIGNED
    assert chk.alignment.points[0].enc_frame == 48
    assert sorted(c[1] for c in f.calls if c[0] == ENC) == expected


# Лимит общий: при 3 заменах «неопределённо» повторов нет. М7 (раздельный лимит)
# ловится только по списку вызовов ENC: лишние повторы 548, 596, 644 статичны,
# вердикт тот же «неопределённо».
def test_junction_budget_shared(fake):
    starts = [0, 250, 500, 560, 620, 680, 700, 750, 900]
    film = _static_ranges(noisy_film(1000), (490, 690))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(starts))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert _enc_calls(f) == [
        (0, 1), (249, 2), (499, 2), (559, 2), (619, 2), (679, 2), (749, 2), (899, 2)
    ]


# --------------------------------------------------------------------------- #
# CR-01 / WR-09: склейка закрывается только своей сценой (решения оператора 2026-11-06)
# --------------------------------------------------------------------------- #


def _shift_in(static, shift):
    """src со статикой static; enc = src, но кадры shift[0]..shift[1] взяты на +1."""
    src = _static_ranges(noisy_film(1000), static)
    enc = list(src)
    for i in range(shift[0], shift[1] + 1):
        enc[i] = src[i + 1]
    return src, enc


# Зонд CR-01: сцена 500..519 сдвинута на +1, соседние чанки исправны. На HEAD повтор
# 548 лежал в чужой сцене и давал ложное «выровнено» (ok True). Теперь повтор вне сцены
# [500, 520) отброшен, замен нет, склейка остаётся «неопределённо» -> отказ.
def test_junction_retry_in_scene_refused(fake):
    src, enc = _shift_in((490, 510), (500, 519))
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc([0, 250, 500, 520, 750, 900]))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert _enc_calls(f) == [(0, 1), (249, 2), (499, 2), (749, 2), (899, 2)]


# Зонд WR-09: замена 560 «выровнено» (чужой чанк) — голос, но цель 500 не закрывает.
# На HEAD замена закрывала цель, и файл был «выровнено» при сдвиге в сцене 500..519.
def test_junction_replacement_not_closing(fake):
    src, enc = _shift_in((490, 510), (500, 519))
    f = fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(
        SRC, ENC, CFG, scenes=_sc([0, 250, 500, 520, 560, 750, 900])
    )
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 5
    assert [p.enc_frame for p in chk.alignment.points] == [0, 250, 500, 560, 750, 900]
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert _enc_calls(f) == [(0, 1), (249, 2), (499, 2), (559, 2), (749, 2), (899, 2)]


# Сдвиг +1 внутри сцены [500, 600) при статичном начале: замена 600 «выровнено» (голос),
# повтор 548 в сцене видит сдвиг -> вердикт файла «сдвиг». На HEAD замена 600 закрывала
# цель и давала ложное «выровнено».
def test_junction_in_scene_shift(fake):
    src, enc = _shift_in((490, 510), (530, 560))
    fake({SRC: src, ENC: enc})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc(JSTARTS))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert any("сдвиг +1" in r and "в точке энкода 548" in r for r in chk.reasons)


# Общий лимит: замена 700 «выровнено» (голос) тратит 1 из 3, на повторы остаётся 2
# (548, 596 статичны); третий повтор 644 не берётся, склейка 500 не закрыта -> отказ.
def test_junction_replacement_vote_budget(fake):
    film = _static_ranges(noisy_film(1000), (490, 600))
    f = fake({SRC: film, ENC: film})
    chk = pair.check_pair_files(SRC, ENC, CFG, scenes=_sc([0, 250, 500, 700, 750, 900]))
    assert chk.ok is False and chk.alignment.verdict == ALIGN_UNDETERMINED
    assert chk.alignment.n_aligned == 5
    assert chk.reasons[-1].endswith("неопределённые точки (кадры энкода): 500")
    assert _enc_calls(f) == [
        (0, 1), (249, 2), (499, 2), (548, 1), (596, 1), (699, 2), (749, 2), (899, 2)
    ]
