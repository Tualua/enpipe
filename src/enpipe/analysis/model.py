"""Модель отчёта и метрик офлайн-анализа качества энкода.

Это единственный источник данных для report.md, index.html и report.json
(RPT-01): рендереры только читают эти датаклассы. Имена полей — английский
snake_case и являются ключами report.json (D-18). «Нет данных» выражается
None, а не nan (D-03). Каркас полный уже сейчас: последующие этапы
(выравнивание, кропы, флаги, серьёзность) лишь заполняют готовые поля, а
schema_version не меняется (D-20). Поля выравнивания, отказа и пометок
опциональны, а report.json ещё не выпускался, поэтому версия остаётся 1.

Модуль чистый: только stdlib, без numpy, subprocess и импортов enpipe.
Коллекции — только Tuple (неизменяемость и хешируемость).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Optional, Tuple, Union

SCHEMA_VERSION = 1

# Статус метрики цвета мелких деталей (MET-01, D-03).
CHROMA_OK = "ok"
CHROMA_NO_DETAILS = "no_details"

# Источники кандидатов (CND-*). Приоритет при слиянии: меньше = важнее (D-15).
SOURCE_MANUAL = "manual"
SOURCE_VMAF = "vmaf"
SOURCE_CSV = "csv"
SOURCE_SCAN = "scan"
SOURCE_PRIORITY: Dict[str, int] = {
    SOURCE_MANUAL: 0,
    SOURCE_VMAF: 1,
    SOURCE_CSV: 2,
    SOURCE_SCAN: 3,
}

# Состояние источника кандидатов в отчёте (D-17, D-20).
STATE_ENABLED = "enabled"
STATE_UNAVAILABLE = "unavailable"
STATE_REJECTED = "rejected"
STATE_NOT_REQUESTED = "not_requested"

# Статус строки кадра (строки ошибок извлечения — часть модели, D-20).
ROW_OK = "ok"
ROW_ERROR = "error"

# Вердикт выравнивания точки/файла (ALN-*): совпал свой кадр / совпал кадр со
# сдвигом / нельзя определить.
ALIGN_ALIGNED = "aligned"
ALIGN_SHIFT = "shift"
ALIGN_UNDETERMINED = "undetermined"

# Статус отчёта: анализ выполнен или пара отвергнута предпроверкой.
REPORT_OK = "ok"
REPORT_REFUSED = "refused"

# Источник значения --offset: задан оператором / проверен по .scenes.
OFFSET_MANUAL = "manual"
OFFSET_SCENES = "scenes"


# --------------------------------------------------------------------------- #
# Метрики кадра
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChromaDetail:
    """Сохранность цвета мелких деталей (MET-01, D-01..D-06)."""

    status: str  # CHROMA_OK | CHROMA_NO_DETAILS
    n_blocks: int
    median: Optional[float] = None
    p10: Optional[float] = None
    ratio: Optional[float] = None  # Σ(s·e)/Σ(s·s) по всем блокам (D-02)
    worst_value: Optional[float] = None
    worst_x: Optional[int] = None  # пиксели Y (D-06)
    worst_y: Optional[int] = None


@dataclass(frozen=True)
class LumaTile:
    """Худший тайл по Y (MET-02, D-09); координаты и размеры в пикселях Y."""

    x: int
    y: int
    w: int
    h: int
    psnr: float


@dataclass(frozen=True)
class ChromaTile:
    """Худший цветной тайл по суммарному MSE U+V (MET-02, D-09); пиксели Y."""

    x: int
    y: int
    w: int
    h: int
    psnr_u: float
    psnr_v: float
    mse_uv: float


@dataclass(frozen=True)
class DetailTile:
    """Самый «замыленный» тайл по энергии лапласиана (D-10); пиксели Y."""

    x: int
    y: int
    w: int
    h: int
    detail: float


@dataclass(frozen=True)
class FrameMetrics:
    """Все метрики одного кадра (MET-01..04)."""

    psnr_y: float  # inf допустим (идентичные плоскости, D-19)
    psnr_u: float
    psnr_v: float
    worst_tile_y: LumaTile
    worst_tile_c: ChromaTile
    nits_mean: float
    shadow_fraction: float
    detail: Optional[float]  # None: источник плоский
    worst_tile_detail: Optional[DetailTile]
    delta_e_itp_mean: float
    delta_e_itp_p99: float
    chroma: ChromaDetail


# --------------------------------------------------------------------------- #
# Источники и кандидаты (CND-*)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceStatus:
    """Состояние источника кандидатов: включён / недоступен / отвергнут."""

    source: str  # SOURCE_*
    state: str  # STATE_*
    reason: Optional[str] = None  # русский текст причины отказа/недоступности
    notes: Tuple[str, ...] = ()  # предупреждения (не отказ)
    count: int = 0  # сколько кандидатов дал источник


@dataclass(frozen=True)
class RawCandidate:
    """Кандидат от одного источника до слияния.

    rank — ключ порядка ВНУТРИ источника (меньше = важнее): vmaf — значение
    VMAF, csv — лучшая позиция в топе (0-based), manual — 0.0; между
    источниками не сравнивается.
    """

    frame: int
    source: str
    rank: float
    tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    """Итоговый кандидат после слияния (CND-05): все источники сохранены."""

    frame: int
    primary: str
    sources: Tuple[str, ...]
    tags: Tuple[str, ...] = ()
    scene: Optional[int] = None


# --------------------------------------------------------------------------- #
# Пара источник/энкод и выравнивание
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StreamInfo:
    """Сведения о видеопотоке файла для предпроверки пары.

    Контракт нормализации: теги уже приведены — None вместо
    "unknown"/"unspecified"/"N/A" и отсутствия. avg_frame_rate — Fraction, не
    float (точное сравнение с допуском, D-16). field_order: "progressive",
    "tt", "bb", "tb", "bt" или None (не указан; трактуется как прогрессивный).
    В report.json StreamInfo не сериализуется.
    """

    name: str
    format_name: Optional[str]
    codec_name: Optional[str]
    width: int
    height: int
    pix_fmt: Optional[str]
    avg_frame_rate: Optional[Fraction]
    start_time: Optional[float]
    color_range: Optional[str]
    color_space: Optional[str]
    color_transfer: Optional[str]
    color_primaries: Optional[str]
    has_dovi: bool = False
    dv_profile: Optional[int] = None
    field_order: Optional[str] = None


@dataclass(frozen=True)
class PairVerdict:
    """Итог предпроверки пары: отказ с причинами или допуск с пометками."""

    ok: bool
    reasons: Tuple[str, ...] = ()  # русские причины отказа
    notes: Tuple[str, ...] = ()  # пометки (VFR, start_time) — не отказ
    offset: int = 0
    offset_source: Optional[str] = None  # OFFSET_*
    vfr: bool = False


@dataclass(frozen=True)
class PointAlignment:
    """Вердикт выравнивания одной точки.

    shift: d = номер совпавшего кадра источника − (enc_frame + offset).
    shift_at_least=True — «сдвиг ≥ W»: лучший на краю необрезанного окна (D-12).
    """

    enc_frame: int
    verdict: str  # ALIGN_*
    shift: Optional[int] = None
    shift_at_least: bool = False
    margin_db: Optional[float] = None
    scene: Optional[int] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class FileAlignment:
    """Файловый вердикт выравнивания по точкам."""

    verdict: str  # ALIGN_*
    shift: Optional[int] = None
    offset: int = 0
    n_aligned: int = 0  # число разнесённых (> 2W) голосов «выровнено», см. align.aggregate
    points: Tuple[PointAlignment, ...] = ()


# --------------------------------------------------------------------------- #
# Отчёт (RPT-01, MET-05)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ImageRef:
    """Ссылка на кроп/картинку кадра (RPT-02, заполняется позже)."""

    kind: str
    path: str
    caption: str


@dataclass(frozen=True)
class FrameRow:
    """Строка кадра, включая строки ошибок извлечения (RPT-04)."""

    frame: int
    status: str  # ROW_OK | ROW_ERROR
    sources: Tuple[str, ...] = ()
    scene: Optional[int] = None
    scene_pos: Optional[int] = None
    time_sec: Optional[float] = None
    vmaf: Optional[float] = None
    metrics: Optional[FrameMetrics] = None
    error: Optional[str] = None
    alignment: Optional[str] = None  # заполняется при выравнивании
    alignment_shift: Optional[int] = None
    flags: Tuple[str, ...] = ()  # флаги (CND-06)
    severity: Optional[float] = None  # серьёзность (RPT-03)
    images: Tuple[ImageRef, ...] = ()  # кропы (RPT-02)


@dataclass(frozen=True)
class RunMeta:
    """Метаданные запуска: только имена файлов и версии, без секретов."""

    src_name: str
    enc_name: str
    tool: str = "enpipe analyze"
    created_at: Optional[str] = None
    enpipe_version: Optional[str] = None
    ffmpeg_version: Optional[str] = None
    qsvencc_version: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    frame_count: Optional[int] = None
    offset: Optional[int] = None
    offset_source: Optional[str] = None  # OFFSET_*
    notes: Tuple[str, ...] = ()  # пометки: VFR, start_time, «сдвиг задан вручную»


@dataclass(frozen=True)
class Threshold:
    """Порог анализа с пометкой provisional до калибровки (MET-05)."""

    name: str
    value: Union[int, float]
    provisional: bool = True


@dataclass(frozen=True)
class PercentileSummary:
    """Сводка метрики по кадрам; поле minimum, чтобы не затенять min."""

    metric: str
    n: int
    minimum: Optional[float] = None
    p1: Optional[float] = None
    p5: Optional[float] = None
    p10: Optional[float] = None
    median: Optional[float] = None


@dataclass(frozen=True)
class AnalysisReport:
    """Полная модель отчёта; из неё рендерятся md, html и json."""

    meta: RunMeta
    thresholds: Tuple[Threshold, ...]
    sources: Tuple[SourceStatus, ...]
    candidates: Tuple[Candidate, ...]
    frames: Tuple[FrameRow, ...]
    summary: Tuple[PercentileSummary, ...]
    status: str = REPORT_OK
    refusal_reasons: Tuple[str, ...] = ()
    alignment: Optional[FileAlignment] = None
    schema_version: int = SCHEMA_VERSION
