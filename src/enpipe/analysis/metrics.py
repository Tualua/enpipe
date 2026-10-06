"""Метрики кадра для офлайн-анализа качества энкода: чистые функции.

Порт метрик прототипа ``vmaf_frames.py`` (PSNR, тайлы, ниты PQ, энергия
лапласиана, цвет мелких деталей) плюс то, чего в прототипе нет: пиксельная
сетка тайлов с неполными краями, худший тайл по цветности, минимум сохранности
детали по тайлам, ΔE ITP и сборка ``FrameMetrics``.

Модуль только numpy + math: ни subprocess, ни die/log, ни I/O. Вход — uint16-
плоскости 10-битного limited-range PQ (Y полного размера, U/V в 4:2:0); выход —
Python-числа и frozen-датаклассы из model.py. numpy-скаляры и view на входные
буферы в результатах не хранятся: иначе отчёт держал бы в памяти плоскости
целых кадров, а json не умел бы их сериализовать.

Точность важнее скорости: вычисления во float64 (либо точно в целых), но без
полноразмерных float64-копий плоскости Y. Всё, что идёт по целому Y, считается
полосами ITP_STRIP_ROWS строк с точным целочисленным накоплением: на 4K одна
float64-копия Y — 66 МБ, а их понадобилось бы несколько одновременно.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from enpipe.analysis.config import (
    AnalysisError,
    AnalyzeConfig,
    CHROMA_MID,
    ITP_STRIP_ROWS,
    LUMA_BLACK,
    LUMA_RANGE,
    PEAK_10BIT,
    PQ_C1,
    PQ_C2,
    PQ_C3,
    PQ_M1,
    PQ_M2,
    PQ_PEAK_NITS,
)
from enpipe.analysis.model import (
    CHROMA_NO_DETAILS,
    CHROMA_OK,
    ChromaDetail,
    ChromaTile,
    DetailTile,
    LumaTile,
)

# --------------------------------------------------------------------------- #
# Тайлинг и полосы
# --------------------------------------------------------------------------- #


def tile_edges(n: int, tile: int) -> List[Tuple[int, int]]:
    """Границы тайлов фиксированного размера вдоль оси длиной n (D-07, D-08).

    Остаток меньше половины тайла приклеивается к последнему полному тайлу
    (тайл растягивается до n); остаток не меньше половины — отдельный тайл.
    Ни один пиксель не теряется: тайлы смежны и покрывают [0, n).
    """
    if n <= 0 or tile <= 0:
        raise AnalysisError(f"tile_edges: n и tile должны быть > 0, получено {n}, {tile}")
    full, rem = divmod(n, tile)
    if full == 0:
        return [(0, n)]
    edges = [(i * tile, (i + 1) * tile) for i in range(full)]
    if rem == 0:
        return edges
    if rem < tile / 2:
        edges[-1] = (edges[-1][0], n)
    else:
        edges.append((full * tile, n))
    return edges


def _strips(n: int, rows: int) -> List[Tuple[int, int]]:
    """Полосы по `rows` строк; единственный нарезчик полос модуля."""
    return [(r, min(r + rows, n)) for r in range(0, n, rows)]


# --------------------------------------------------------------------------- #
# PSNR / MSE
# --------------------------------------------------------------------------- #


def mse(a: np.ndarray, b: np.ndarray) -> float:
    """Среднеквадратичная ошибка двух плоскостей, точная (целочисленная).

    Разность берётся в int64: вычитание uint16 заворачивалось бы (100 - 101 =
    65535). Сумма квадратов копится в Python int полосами, поэтому переполнения
    нет и пик памяти ограничен полосой, а не плоскостью. int32 не годится:
    квадрат разности uint16 вне 10-битного диапазона его переполняет.
    """
    h, w = a.shape
    total = 0
    for r0, r1 in _strips(h, ITP_STRIP_ROWS):
        d = a[r0:r1].astype(np.int64) - b[r0:r1].astype(np.int64)
        total += int((d * d).sum())
    return total / (h * w)


def _psnr_from_mse(m: float) -> float:
    return float("inf") if m == 0 else 10 * math.log10(PEAK_10BIT**2 / m)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR 10-битных плоскостей, дБ; идентичные плоскости дают inf."""
    return _psnr_from_mse(mse(a, b))


# --------------------------------------------------------------------------- #
# Яркость в нитах
# --------------------------------------------------------------------------- #


def pq_nits(code: np.ndarray) -> np.ndarray:
    """10-битный limited-range код -> нит по SMPTE ST 2084 (D-11).

    Коды ниже чёрного дают 0, выше пика — PQ_PEAK_NITS (клип нормированного
    сигнала).
    """
    e = np.clip((code.astype(np.float64) - LUMA_BLACK) / LUMA_RANGE, 0, 1)
    p = e ** (1 / PQ_M2)
    return PQ_PEAK_NITS * (np.maximum(p - PQ_C1, 0) / (PQ_C2 - PQ_C3 * p)) ** (1 / PQ_M1)


def luminance_stats(sy: np.ndarray, cfg: AnalyzeConfig) -> Tuple[float, float]:
    """(средняя яркость в нитах, доля пикселей темнее cfg.shadow_nits).

    Считается по полосам: pq_nits на целом Y держал бы несколько float64-копий
    плоскости. Метрика определена только для 10-битного PQ HDR; для SDR
    значения не имеют смысла (вне рамок milestone).
    """
    h, w = sy.shape
    nits_sum = 0.0
    shadows = 0
    for r0, r1 in _strips(h, ITP_STRIP_ROWS):
        nits = pq_nits(sy[r0:r1])
        nits_sum += float(nits.sum())
        shadows += int((nits < cfg.shadow_nits).sum())
    n = h * w
    return nits_sum / n, shadows / n


# --------------------------------------------------------------------------- #
# Энергия лапласиана и сохранность детали
# --------------------------------------------------------------------------- #


def lap_energy(y: np.ndarray) -> Optional[float]:
    """Средний |лапласиан| внутренней области; None, если плоскость < 3x3.

    Считается полосами внутренних строк [1, H-1) с ореолом в одну строку
    сверху и снизу, в int64: лапласиан целых кодов точен, сумма модулей копится
    в Python int, деление один раз в конце.
    """
    h, w = y.shape
    if h < 3 or w < 3:
        return None
    total = 0
    for r0, r1 in _strips(h - 2, ITP_STRIP_ROWS):
        # внутренние строки полосы: r0+1 .. r1+1 (не включая), ореол ±1
        f = y[r0:r1 + 2].astype(np.int64)
        lap = 4 * f[1:-1, 1:-1] - f[:-2, 1:-1] - f[2:, 1:-1] - f[1:-1, :-2] - f[1:-1, 2:]
        total += int(np.abs(lap).sum())
    return total / ((h - 2) * (w - 2))


def detail_preservation(
    sy: np.ndarray, ey: np.ndarray, cfg: AnalyzeConfig
) -> Tuple[Optional[float], Optional[DetailTile]]:
    """Сохранность детали по Y: энергия лапласиана энкода / источника.

    < 1 — энкодер сгладил зерно/текстуру, > 1 — добавил шум/блоки. Плоский
    источник (энергия < detail_eps или плоскость < 3x3) — сохранять нечего:
    глобальное значение None, а не деление на ~0 (D-10). Худший тайл — минимум
    отношения только среди годных (не плоских) тайлов; ничья — растровый
    порядок. Нет годных тайлов — None.
    """
    ls = lap_energy(sy)
    le = lap_energy(ey)
    if ls is None or le is None or ls < cfg.detail_eps:
        return None, None
    glob = le / ls

    worst: Optional[DetailTile] = None
    for y0, y1 in tile_edges(sy.shape[0], cfg.tile_y):
        for x0, x1 in tile_edges(sy.shape[1], cfg.tile_y):
            ts = lap_energy(sy[y0:y1, x0:x1])
            te = lap_energy(ey[y0:y1, x0:x1])
            if ts is None or te is None or ts < cfg.detail_eps:
                continue
            d = te / ts
            if worst is None or d < worst.detail:
                worst = DetailTile(x=x0, y=y0, w=x1 - x0, h=y1 - y0, detail=d)
    return glob, worst


# --------------------------------------------------------------------------- #
# Худшие тайлы по PSNR
# --------------------------------------------------------------------------- #


def luma_tiles(sy: np.ndarray, ey: np.ndarray, cfg: AnalyzeConfig) -> LumaTile:
    """Худший тайл по Y (минимальный PSNR, максимальный MSE); ничья — растр."""
    best: Optional[Tuple[float, int, int, int, int]] = None
    for y0, y1 in tile_edges(sy.shape[0], cfg.tile_y):
        for x0, x1 in tile_edges(sy.shape[1], cfg.tile_y):
            m = mse(sy[y0:y1, x0:x1], ey[y0:y1, x0:x1])
            if best is None or m > best[0]:
                best = (m, x0, y0, x1, y1)
    m, x0, y0, x1, y1 = best  # type: ignore[misc]
    return LumaTile(x=x0, y=y0, w=x1 - x0, h=y1 - y0, psnr=_psnr_from_mse(m))


def chroma_tiles(
    su: np.ndarray, sv: np.ndarray, eu: np.ndarray, ev: np.ndarray, cfg: AnalyzeConfig
) -> ChromaTile:
    """Худший тайл по цветности: максимум MSE_U + MSE_V (D-09).

    Сетка считается по плоскости цветности независимо от Y (tile_c), а не
    делением границ Y пополам: иначе неполные края не совпали бы. Координаты и
    размеры возвращаются в пикселях Y (цветность x2).
    """
    best: Optional[Tuple[float, float, float, int, int, int, int]] = None
    for y0, y1 in tile_edges(su.shape[0], cfg.tile_c):
        for x0, x1 in tile_edges(su.shape[1], cfg.tile_c):
            mu = mse(su[y0:y1, x0:x1], eu[y0:y1, x0:x1])
            mv = mse(sv[y0:y1, x0:x1], ev[y0:y1, x0:x1])
            if best is None or mu + mv > best[0]:
                best = (mu + mv, mu, mv, x0, y0, x1, y1)
    s, mu, mv, x0, y0, x1, y1 = best  # type: ignore[misc]
    return ChromaTile(
        x=x0 * 2,
        y=y0 * 2,
        w=(x1 - x0) * 2,
        h=(y1 - y0) * 2,
        psnr_u=_psnr_from_mse(mu),
        psnr_v=_psnr_from_mse(mv),
        mse_uv=s,
    )


# --------------------------------------------------------------------------- #
# Сохранность цвета мелких насыщенных деталей
# --------------------------------------------------------------------------- #


def small_chroma(
    su: np.ndarray, sv: np.ndarray, eu: np.ndarray, ev: np.ndarray, cfg: AnalyzeConfig
) -> ChromaDetail:
    """Сохранность цвета МЕЛКИХ насыщенных деталей любого оттенка (MET-01).

    VMAF считается только по Y, а средний PSNR U/V тонет в фоне, поэтому
    посеревшую мелкую цветную деталь они не видят. Берутся блоки
    cfg.chroma_block x cfg.chroma_block отсчётов цветности, где у источника от
    chroma_min_pts до chroma_max_pts точек с насыщенностью
    hypot(Cb-512, Cr-512) > chroma_sat_thr (мелкая деталь, не заливка), и
    считается проекция цвета энкода на цвет источника: Σ(s·e)/Σ(s·s) по точкам
    блока. 1.0 — цвет сохранён, 0 — деталь посерела, > 1 — перенасыщение,
    < 0 — сдвиг оттенка; проекция НЕ обрезается (D-04).

    Учитываются только ПОЛНЫЕ блоки: края цветности, не кратные размеру блока,
    отбрасываются, как в прототипе — так воспроизводятся приёмочные цифры
    прототипа (71 -> 88 %). Блоков меньше min_chroma_blocks — статус
    no_details без чисел (D-03). Ранжировать кадры следует по p10 (D-02);
    ratio — взвешенный по точкам итог по всем отобранным блокам.
    """
    b = cfg.chroma_block
    h, w = su.shape
    hb, wb = h // b, w // b
    if hb == 0 or wb == 0:
        return ChromaDetail(status=CHROMA_NO_DETAILS, n_blocks=0)

    csu = su.astype(np.float64) - CHROMA_MID
    csv_ = sv.astype(np.float64) - CHROMA_MID
    ceu = eu.astype(np.float64) - CHROMA_MID
    cev = ev.astype(np.float64) - CHROMA_MID
    mask = np.hypot(csu, csv_) > cfg.chroma_sat_thr
    counts = mask[: hb * b, : wb * b].reshape(hb, b, wb, b).sum(axis=(1, 3))
    selected = (counts >= cfg.chroma_min_pts) & (counts <= cfg.chroma_max_pts)

    keep: List[Tuple[float, int, int]] = []
    tot_se = 0.0
    tot_ss = 0.0
    for by, bx in zip(*np.nonzero(selected)):
        y, x = int(by) * b, int(bx) * b
        m = mask[y : y + b, x : x + b]
        su_, sv_ = csu[y : y + b, x : x + b][m], csv_[y : y + b, x : x + b][m]
        eu_, ev_ = ceu[y : y + b, x : x + b][m], cev[y : y + b, x : x + b][m]
        se = float((su_ * eu_ + sv_ * ev_).sum())
        ss = float((su_ * su_ + sv_ * sv_).sum())  # > 0: все точки маски насыщены
        tot_se += se
        tot_ss += ss
        keep.append((se / ss, x * 2, y * 2))

    n = len(keep)
    if n < cfg.min_chroma_blocks:
        return ChromaDetail(status=CHROMA_NO_DETAILS, n_blocks=n)
    vals = np.array([k[0] for k in keep])
    worst = min(keep)  # ничья решается по x, затем y — как в прототипе
    return ChromaDetail(
        status=CHROMA_OK,
        n_blocks=n,
        median=float(np.median(vals)),
        # метод linear (дефолт numpy): на нём получены приёмочные цифры прототипа
        p10=float(np.percentile(vals, 10)),
        ratio=tot_se / tot_ss,
        worst_value=float(worst[0]),
        worst_x=int(worst[1]),
        worst_y=int(worst[2]),
    )
