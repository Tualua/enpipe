"""Решение о пути декода файла: аппаратный (`hw`, --avhw) или программный
(`sw`, --avsw).

Почему так:

* Решение одно на файл и принимается до первого чанка (D-01): внутри файла
  путь не меняется. Никаких пробных запусков и отката по коду возврата —
  неудачный аппаратный декод может «пройти» с rc=0 и тихо испортить кадры.
* Источник истины — сам qsvencc (`--check-features`, секция
  `Supported Decode features`), а не вшитая таблица поколений GPU (D-02):
  при замене A380 на B50 таблица уже менялась. Таблицу GPU опрашиваем один
  раз на процесс; решение по файлу принимается заново для каждого файла.
* Ключ решения — (кодек, цветность, разрядность) (D-14): H.264 на B50
  декодируется аппаратно только 8 бит 4:2:0, 10-битный AVC — программно.
  В ячейке таблицы стоит максимальная разрядность.
* Любая неясность — fail closed (D-04): нечитаемый вывод, таймаут, нет
  бинарника, неизвестный pix_fmt дают `die()` с подсказкой `--decode hw|sw`,
  а не догадку. Запасного списка кодеков нет.
* `field_order` читается через `-of json` (в csv пришла бы строка
  `unknown`). Отказ только на явных tt/bb/tb/bt (D-07, D-13), на любом
  режиме и до опроса qsvencc. Известное ограничение: чересстрочный файл без
  флага в контейнере так не поймать — остаточный риск принят оператором.

Публичный API (его импортируют cli/detection/encoding): `DECODE_MODES`,
`DecodeChoice`, `decode_mode_from_args`, `resolve_decode`, `describe_decode`.
Остальные имена модуля — внутренние части решения, открытые для тестов.

Модуль листовой: импортирует только stdlib, `enpipe.shared.proc` и
`enpipe.shared.logging`. `die()` вызывается только в главном потоке.
"""
from __future__ import annotations

import functools
import json
import re
import shlex
import subprocess
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from enpipe.shared import proc as _proc
from enpipe.shared.logging import die

DECODE_MODES: Tuple[str, ...] = ("auto", "hw", "sw")

# Явные признаки чересстрочности; отсутствующий ключ и `unknown` — прогрессив.
INTERLACED_FIELD_ORDERS = frozenset({"tt", "bb", "tb", "bt"})

# ffprobe codec_name -> заголовок колонки в таблице qsvencc. Кодек не из
# словаря (vc1, wmv3, mpeg4, ...) колонки не имеет -> аппаратно не декодируется.
CODEC_COLUMNS: Dict[str, str] = {
    "h264": "H.264",
    "hevc": "HEVC",
    "mpeg2video": "MPEG2",
    "vp8": "VP8",
    "vp9": "VP9",
    "av1": "AV1",
    "vvc": "VVC",
}

# Штатно опрос занимает ~4.3 с (инициализация VA); 30 с — запас на
# загруженную систему, но не бесконечное зависание перед первым чанком.
QUERY_TIMEOUT_SEC = 30

_HDR = "Supported Decode features:"
_HINT = "задайте --decode hw или --decode sw"


@dataclass(frozen=True)
class DecodeChoice:
    """Принятое решение о пути декода для одного файла."""
    path: str                    # "hw" | "sw"
    mode: str                    # запрошенный режим: auto | hw | sw
    codec: str
    pix_fmt: Optional[str]
    field_order: Optional[str]
    reason: str


# ------------------------------------------------------------------ #
# Чистые части
# ------------------------------------------------------------------ #

def parse_decode_table(text: str) -> Optional[Dict[Tuple[str, str], int]]:
    """{(колонка, 'yuv420'): макс. разрядность} или None, если вывод не разобрался.

    Ячейки смещены на 1 символ относительно заголовка колонки, поэтому токен
    ячейки относится к ближайшему началу заголовка (допуск <= 2); ничья или
    расстояние больше — отказ (None)."""
    lines = text.splitlines()
    try:
        i = next(k for k, ln in enumerate(lines) if ln.strip() == _HDR)
    except StopIteration:
        return None
    rest = lines[i + 1:]
    head_i = next((k for k, ln in enumerate(rest) if ln.strip()), None)
    if head_i is None:
        return None
    cols = [(m.group(), m.start()) for m in re.finditer(r"\S+", rest[head_i])]
    if not any(name in CODEC_COLUMNS.values() for name, _ in cols):
        return None  # формат сменился — не угадываем
    out: Dict[Tuple[str, str], int] = {}
    for row in rest[head_i + 1:]:
        if not row.strip():
            break
        m = re.match(r"(yuv\d{3})\b", row)
        if not m:
            return None
        for tok in re.finditer(r"\S+", row[m.end():]):
            start = m.end() + tok.start()
            d = re.fullmatch(r"(\d+)bit", tok.group())
            near = sorted(cols, key=lambda c: abs(c[1] - start))
            if (not d or abs(near[0][1] - start) > 2
                    or (len(near) > 1
                        and abs(near[1][1] - start) == abs(near[0][1] - start))):
                return None
            out[(near[0][0], m.group(1))] = int(d.group(1))
    return out or None  # пустая таблица = не разобрали


_PIX_FMT_RE = re.compile(r"yuvj?(420|422|444)p(?:(9|10|12|14|16)(?:le|be))?")


def pix_fmt_format(pix_fmt: Optional[str]) -> Optional[Tuple[str, int]]:
    """(цветность, разрядность) из pix_fmt ffprobe; незнакомый -> None."""
    if not pix_fmt:
        return None
    m = _PIX_FMT_RE.fullmatch(pix_fmt)
    if not m:
        return None
    return f"yuv{m.group(1)}", int(m.group(2)) if m.group(2) else 8


def auto_path(table: Dict[Tuple[str, str], int], codec: str,
              pix_fmt: Optional[str]) -> Tuple[Optional[str], str]:
    """(путь hw/sw или None, причина). None — pix_fmt не распознан (D-14)."""
    fmt = pix_fmt_format(pix_fmt)
    if fmt is None:
        return None, f"не распознан pix_fmt «{pix_fmt}»"
    chroma, depth = fmt
    column = CODEC_COLUMNS.get(codec)
    if column is None:
        return "sw", f"{codec} нет среди аппаратных декодеров GPU"
    have = table.get((column, chroma), 0)
    if have >= depth:
        return "hw", (f"{codec} {chroma} {depth} бит есть среди "
                      "аппаратных декодеров GPU")
    if have == 0:
        return "sw", (f"{column} {chroma} нет среди аппаратных декодеров GPU")
    return "sw", (f"{codec} {chroma} {depth} бит: GPU декодирует "
                  f"{column} {chroma} только до {have} бит")


def check_progressive(field_order: Optional[str]) -> Optional[str]:
    """Текст отказа для явно чересстрочного источника, иначе None (D-13)."""
    if field_order in INTERLACED_FIELD_ORDERS:
        return (f"источник чересстрочный (field_order={field_order}): "
                "кодирование чересстрочного видео не поддерживается, "
                "деинтерлейс — отдельная фаза")
    return None


def decode_mode_from_args(args: Namespace) -> str:
    """Режим декода из аргументов CLI; `--no-qsv` — синоним `sw` (D-06)."""
    mode = getattr(args, "decode", "auto")
    no_qsv = getattr(args, "no_qsv", False)
    if mode not in DECODE_MODES:
        die(f"неизвестный режим декода «{mode}»; допустимы: "
            + ", ".join(DECODE_MODES))
    if no_qsv:
        if mode == "hw":
            die("--no-qsv и --decode hw взаимоисключающи: --no-qsv устарел "
                "и означает --decode sw")
        return "sw"
    return mode


def describe_decode(choice: DecodeChoice) -> str:
    return f"декод: {choice.path} ({choice.reason}; --decode {choice.mode})"


# ------------------------------------------------------------------ #
# Части с подпроцессами (только через enpipe.shared.proc)
# ------------------------------------------------------------------ #

def probe_video_format(src: Path) -> Tuple[str, Optional[str], Optional[str]]:
    """(codec_name, pix_fmt, field_order) первого видеопотока одним ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=codec_name,pix_fmt,field_order",
           "-of", "json", str(src)]

    def fail(why: str, stderr: str = "") -> None:
        tail = (stderr or "").strip()[-300:]
        die(f"{src.name}: не удалось определить формат видео ({why}); "
            f"команда: {shlex.join(cmd)}" + (f"; stderr: {tail}" if tail else ""))

    try:
        r = _proc.run(cmd, capture_output=True, text=True)
    except OSError as e:
        fail(f"{type(e).__name__}: {e}")
    if r.returncode != 0:
        fail(f"ffprobe rc={r.returncode}", r.stderr)
    try:
        streams = json.loads(r.stdout).get("streams") or []
    except (json.JSONDecodeError, AttributeError):
        fail("ffprobe вернул не JSON", r.stderr)
    if not streams or not streams[0].get("codec_name"):
        fail("нет видеопотока или codec_name", r.stderr)
    st = streams[0]
    return st["codec_name"], st.get("pix_fmt"), st.get("field_order")


@functools.lru_cache(maxsize=1)
def _decode_table_cached() -> Tuple[Tuple[Tuple[str, str], int], ...]:
    # Таблица зависит от GPU и сборки qsvencc, а не от файла, и за время
    # жизни процесса не меняется: батч из N файлов спрашивает её один раз
    # (опрос ~4 с). Сбой кончается die() (SystemExit) — lru_cache исключения
    # не кэширует, следующий вызов спросит заново. Кортеж пар неизменяем:
    # общий кэш нельзя испортить мутацией.
    seen: str
    try:
        r = _proc.run(["qsvencc", "--check-features"], capture_output=True,
                      text=True, timeout=QUERY_TIMEOUT_SEC)
    except FileNotFoundError:
        die("qsvencc не найден в PATH: режим --decode auto (по умолчанию "
            "в encode, run и detect) спрашивает у него аппаратные декодеры "
            f"GPU; {_HINT}")
    except (OSError, subprocess.TimeoutExpired) as e:
        seen = f"{type(e).__name__}: {e}"
    else:
        # Только stdout: stderr шумный (libva info, InitSession ...) при rc=0.
        if r.returncode == 0:
            table = parse_decode_table(r.stdout or "")
            if table is not None:
                return tuple(table.items())
            seen = "секция «Supported Decode features» не разобрана"
        else:
            seen = f"код возврата {r.returncode}"
    die(f"не удалось узнать аппаратные декодеры GPU "
        f"(qsvencc --check-features: «{seen}»); {_HINT}")


def query_hw_decoders() -> Dict[Tuple[str, str], int]:
    """Таблица {(кодек, цветность): макс. разрядность} аппаратных декодеров."""
    return dict(_decode_table_cached())


def resolve_decode(src: Path, mode: str) -> DecodeChoice:
    """Одно решение о пути декода для файла; логирует вызывающий."""
    codec, pix_fmt, field_order = probe_video_format(src)
    refusal = check_progressive(field_order)
    if refusal:
        die(f"{src.name}: {refusal}")

    def choice(path: str, reason: str) -> DecodeChoice:
        return DecodeChoice(path=path, mode=mode, codec=codec,
                            pix_fmt=pix_fmt, field_order=field_order,
                            reason=reason)

    if mode in ("hw", "sw"):
        return choice(mode, "задан явно")
    if pix_fmt_format(pix_fmt) is None:
        die(f"{src.name}: не распознан pix_fmt «{pix_fmt}»; {_HINT}")
    path, reason = auto_path(query_hw_decoders(), codec, pix_fmt)
    if path is None:
        die(f"{src.name}: {reason}; {_HINT}")
    return choice(path, reason)
