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
from dataclasses import replace
from typing import List, Optional, Tuple

import numpy as np

from enpipe.analysis.config import (
    AnalysisError,
    AnalyzeConfig,
    CHROMA_MID,
    CHROMA_RANGE,
    ITP_SCALE,
    ITP_STRIP_ROWS,
    KB,
    KR,
    LUMA_BLACK,
    LMS_TO_ICTCP,
    LUMA_RANGE,
    PEAK_10BIT,
    PQ_C1,
    PQ_C2,
    PQ_C3,
    PQ_M1,
    PQ_M2,
    PQ_PEAK_NITS,
    RGB_TO_LMS,
)
from enpipe.analysis.model import (
    CHROMA_NO_DETAILS,
    CHROMA_OK,
    ChromaDetail,
    ChromaTile,
    DetailTile,
    FrameMetrics,
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


# --------------------------------------------------------------------------- #
# ΔE ITP (ITU-R BT.2124)
# --------------------------------------------------------------------------- #

_M_RGB_LMS = np.array(RGB_TO_LMS, dtype=np.float64) / 4096.0
_M_LMS_ICTCP = np.array(LMS_TO_ICTCP, dtype=np.float64) / 4096.0


def _pq_eotf_norm(e: np.ndarray) -> np.ndarray:
    """PQ EOTF с нормировкой на пик: 1.0 = PQ_PEAK_NITS (те же константы, что pq_nits)."""
    p = e ** (1 / PQ_M2)
    return (np.maximum(p - PQ_C1, 0) / (PQ_C2 - PQ_C3 * p)) ** (1 / PQ_M1)


def _pq_oetf_norm(lin: np.ndarray) -> np.ndarray:
    """Обратная PQ EOTF: линейный свет (1.0 = пик) -> сигнал PQ."""
    ym = lin**PQ_M1
    return ((PQ_C1 + PQ_C2 * ym) / (1 + PQ_C3 * ym)) ** PQ_M2


def ycbcr_to_itp(
    y: np.ndarray, u: np.ndarray, v: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """10-битные limited-range PQ YCbCr (BT.2020 NCL) -> (I, T, P).

    Все три массива одной формы (цветность уже апсемплирована). Конвейер:
    YCbCr -> R'G'B' (клип в [0, 1]: шум энкода выходит за гамму) -> линейный
    свет PQ EOTF -> LMS (BT.2100) -> PQ OETF -> ICtCp -> (I, 0.5·Ct, Cp);
    T = 0.5·Ct по BT.2124, поэтому ΔE = 720·sqrt(ΔI² + ΔT² + ΔP²).
    """
    yn = (y.astype(np.float64) - LUMA_BLACK) / LUMA_RANGE
    cb = (u.astype(np.float64) - CHROMA_MID) / CHROMA_RANGE
    cr = (v.astype(np.float64) - CHROMA_MID) / CHROMA_RANGE
    r = yn + 2 * (1 - KR) * cr
    b = yn + 2 * (1 - KB) * cb
    g = (yn - KR * r - KB * b) / (1 - KR - KB)
    rgb = np.stack([r, g, b])
    np.clip(rgb, 0.0, 1.0, out=rgb)
    lin = _pq_eotf_norm(rgb)
    lms = np.tensordot(_M_RGB_LMS, lin, axes=1)
    ictcp = np.tensordot(_M_LMS_ICTCP, _pq_oetf_norm(lms), axes=1)
    return ictcp[0], 0.5 * ictcp[1], ictcp[2]


def _upsample2(c: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(c, 2, axis=0), 2, axis=1)


def delta_e_itp(
    sy: np.ndarray,
    su: np.ndarray,
    sv: np.ndarray,
    ey: np.ndarray,
    eu: np.ndarray,
    ev: np.ndarray,
    cfg: AnalyzeConfig,
) -> Tuple[float, float]:
    """(среднее, p99) ΔE ITP по ПОЛНОМУ кадру без подвыборки (D-12).

    Считается полосами ITP_STRIP_ROWS строк Y (константа чётна, поэтому полоса
    цветности — строки r0//2..r1//2). Цветность апсемплируется повтором
    (ближайший сосед, допущение A2); копия повтора — размером полосы (на 4K
    порядка 0,5 МБ на канал). ΔE полосы складывается в заранее выделенный
    float32-массив кадра (на 4K около 33 МБ): float32 даёт погрешность порядка
    1e-7 относительно, чего достаточно для отчёта. cfg оставлен в сигнатуре для
    единообразия вызова.
    """
    h, w = sy.shape
    de = np.empty((h, w), dtype=np.float32)
    for r0, r1 in _strips(h, ITP_STRIP_ROWS):
        c0, c1 = r0 // 2, r1 // 2
        si, st, sp = ycbcr_to_itp(sy[r0:r1], _upsample2(su[c0:c1]), _upsample2(sv[c0:c1]))
        ei, et, ep = ycbcr_to_itp(ey[r0:r1], _upsample2(eu[c0:c1]), _upsample2(ev[c0:c1]))
        de[r0:r1] = ITP_SCALE * np.sqrt((si - ei) ** 2 + (st - et) ** 2 + (sp - ep) ** 2)
    return float(de.mean(dtype=np.float64)), float(np.percentile(de, 99))


# --------------------------------------------------------------------------- #
# Сборка метрик кадра
# --------------------------------------------------------------------------- #


def _check_planes(sy, su, sv, ey, eu, ev) -> None:
    """Проверка входа: программная ошибка вызывающего, а не данные оператора."""
    planes = (sy, su, sv, ey, eu, ev)
    for p in planes:
        if getattr(p, "ndim", None) != 2:
            raise AnalysisError("плоскости должны быть двумерными numpy-массивами")
        if p.dtype != np.uint16:
            raise AnalysisError(f"плоскости должны быть uint16, получено {p.dtype}")
    if sy.shape != ey.shape or su.shape != eu.shape or sv.shape != ev.shape:
        raise AnalysisError("формы плоскостей источника и энкода не совпадают")
    h, w = sy.shape
    if h % 2 or w % 2:
        raise AnalysisError(f"размеры кадра должны быть чётными, получено {w}x{h}")
    if su.shape != (h // 2, w // 2) or sv.shape != (h // 2, w // 2):
        raise AnalysisError(
            f"цветность должна быть ровно {w // 2}x{h // 2}, получено {su.shape} и {sv.shape}"
        )


def _r6(x: Optional[float]) -> Optional[float]:
    """Округление до 6 знаков; inf/nan и None сохраняются, результат — Python float."""
    if x is None:
        return None
    x = float(x)
    return round(x, 6) if math.isfinite(x) else x


def analyze_frame(
    sy: np.ndarray,
    su: np.ndarray,
    sv: np.ndarray,
    ey: np.ndarray,
    eu: np.ndarray,
    ev: np.ndarray,
    cfg: AnalyzeConfig,
) -> FrameMetrics:
    """Все метрики пары кадров источник/энкод (MET-01..MET-04).

    Требование к вызывающему (извлечение кадров): подавать uint16-плоскости
    10-битного PQ, чётные H и W (кроп/масштаб — при извлечении), цветность
    ровно (H/2, W/2); иначе AnalysisError. Метрики определены только для
    10-битного PQ HDR, SDR вне рамок. Яркость в нитах считается по ИСТОЧНИКУ,
    как в прототипе. Float-поля округляются до 6 знаков, inf сохраняется.
    """
    _check_planes(sy, su, sv, ey, eu, ev)
    wt_y = luma_tiles(sy, ey, cfg)
    wt_c = chroma_tiles(su, sv, eu, ev, cfg)
    nits_mean, shadow = luminance_stats(sy, cfg)
    detail, wt_d = detail_preservation(sy, ey, cfg)
    de_mean, de_p99 = delta_e_itp(sy, su, sv, ey, eu, ev, cfg)
    chroma = small_chroma(su, sv, eu, ev, cfg)

    return FrameMetrics(
        psnr_y=_r6(psnr(sy, ey)),
        psnr_u=_r6(psnr(su, eu)),
        psnr_v=_r6(psnr(sv, ev)),
        worst_tile_y=replace(wt_y, psnr=_r6(wt_y.psnr)),
        worst_tile_c=replace(
            wt_c, psnr_u=_r6(wt_c.psnr_u), psnr_v=_r6(wt_c.psnr_v), mse_uv=_r6(wt_c.mse_uv)
        ),
        nits_mean=_r6(nits_mean),
        shadow_fraction=_r6(shadow),
        detail=_r6(detail),
        worst_tile_detail=None if wt_d is None else replace(wt_d, detail=_r6(wt_d.detail)),
        delta_e_itp_mean=_r6(de_mean),
        delta_e_itp_p99=_r6(de_p99),
        chroma=replace(
            chroma,
            median=_r6(chroma.median),
            p10=_r6(chroma.p10),
            ratio=_r6(chroma.ratio),
            worst_value=_r6(chroma.worst_value),
        ),
    )
