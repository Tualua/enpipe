"""Тесты ΔE ITP (BT.2124) и конвейера YCbCr -> ITP (MET-04, D-12)."""

from __future__ import annotations

import numpy as np
import pytest

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.metrics import delta_e_itp, ycbcr_to_itp


def _gray(h, w, y):
    return (
        np.full((h, w), y, dtype=np.uint16),
        np.full((h // 2, w // 2), 512, dtype=np.uint16),
        np.full((h // 2, w // 2), 512, dtype=np.uint16),
    )


def _random_frame(h, w, seed):
    r = np.random.default_rng(seed)
    return (
        r.integers(100, 900, (h, w), dtype=np.uint16),
        r.integers(400, 620, (h // 2, w // 2), dtype=np.uint16),
        r.integers(400, 620, (h // 2, w // 2), dtype=np.uint16),
    )


@pytest.mark.parametrize("y", [64, 200, 500, 769, 940])
def test_gray_has_zero_chroma_and_linear_i(y):
    a = np.array([[y]], dtype=np.uint16)
    c = np.array([[512]], dtype=np.uint16)
    i, t, p = ycbcr_to_itp(a, c, c)
    assert t[0, 0] == pytest.approx(0.0, abs=1e-9)
    assert p[0, 0] == pytest.approx(0.0, abs=1e-9)
    assert i[0, 0] == pytest.approx((y - 64) / 876, abs=1e-6)


def test_peak_white_is_unit_intensity():
    a = np.array([[940]], dtype=np.uint16)
    c = np.array([[512]], dtype=np.uint16)
    assert ycbcr_to_itp(a, c, c)[0][0, 0] == pytest.approx(1.0, abs=1e-9)


def test_identical_frames_zero():
    f = _random_frame(64, 64, 1)
    assert delta_e_itp(*f, *f, AnalyzeConfig()) == (0.0, 0.0)


def test_gray_500_vs_501():
    mean, p99 = delta_e_itp(*_gray(64, 64, 500), *_gray(64, 64, 501), AnalyzeConfig())
    assert mean == pytest.approx(720 / 876, abs=1e-6)
    assert p99 == pytest.approx(720 / 876, abs=1e-6)


def test_symmetric():
    a, b = _random_frame(64, 64, 1), _random_frame(64, 64, 2)
    cfg = AnalyzeConfig()
    ab = delta_e_itp(*a, *b, cfg)
    ba = delta_e_itp(*b, *a, cfg)
    assert ab == pytest.approx(ba, rel=1e-6, abs=1e-9)


def test_p99_not_below_mean_with_local_damage():
    a = _random_frame(128, 128, 3)
    sy, su, sv = a
    ey, eu, ev = sy.copy(), su.copy(), sv.copy()
    ey[:16, :16] = 900
    mean, p99 = delta_e_itp(sy, su, sv, ey, eu, ev, AnalyzeConfig())
    assert p99 >= mean > 0


def test_strips_match_full_frame_reference():
    """Высота 300 не кратна полосе: результат равен расчёту без полос."""
    h, w = 300, 256
    s, e = _random_frame(h, w, 4), _random_frame(h, w, 5)
    up = lambda c: np.repeat(np.repeat(c, 2, axis=0), 2, axis=1)  # noqa: E731
    si, st, sp = ycbcr_to_itp(s[0], up(s[1]), up(s[2]))
    ei, et, ep = ycbcr_to_itp(e[0], up(e[1]), up(e[2]))
    de = 720.0 * np.sqrt((si - ei) ** 2 + (st - et) ** 2 + (sp - ep) ** 2)
    mean, p99 = delta_e_itp(*s, *e, AnalyzeConfig())
    assert mean == pytest.approx(float(de.mean()), rel=1e-6, abs=1e-6)
    assert p99 == pytest.approx(float(np.percentile(de, 99)), rel=1e-6, abs=1e-6)
