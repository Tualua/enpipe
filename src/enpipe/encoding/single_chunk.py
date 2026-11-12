"""Одночанковый режим для источников без pts (фаза 10.1, план 13).

Зачем. Quick 261112-dab: у `wmv3` в ASF у ВСЕХ видеопакетов `pts_time=N/A`.
Фолбэк таблицы ключевых кадров по пакетам для такого источника пуст, а номера
по dts уходят от вывода декодера на +2/+3 (за окном перенумерации ±2), поэтому
края чанков `--seek/--trim` не гарантированы. Нарезать нечем — источник
кодируется целиком ОДНИМ вызовом `qsvencc --avsw`, без `--seek`/`--trim`, без
детекта сцен и без таблицы ключевых кадров (решения оператора 1–3). Края чанков
отсутствуют, сдвигаться нечему; единственная сверка — число кадров выхода равно
числу кадров полного программного декода источника (решение 4).

Определение «нет pts» (решение 2: по факту, не по кодеку/контейнеру).
Двухступенчатая проверка, только демультиплексирование, без декода. Ступень 1 —
первые PTS_PROBE_WINDOW пакетов `v:0`: хоть один числовой pts — pts есть, ответ
готов (обычные источники). Ступень 2 — только если все прочитанные без pts: тот
же запрос по всему файлу. «Нет pts» — ровно когда pts нет у ВСЕХ видеопакетов
файла. VC-1 в mkv (pts нет у половины пакетов, 2-й пакет с pts) под режим не
попадает и идёт сценовым путём: его таблица берётся из Cues и проверена на B50
(10.1-10). Частичные pts ни в какую сторону не проходят молча: на сценовом пути
ключевой пакет без pts громко останавливает `keyframe_table_ffprobe`.

Мукс. mkvmerge не читает ASF (`mkvmerge -J`: supported=false), а прежний код
добавлял источник в мукс (`--no-video --no-audio <источник>`) ради глав,
субтитров и вложений и упал бы после полного энкода. `mux_source_args` решает
это ДО энкода: источник добавляется, если mkvmerge его читает; иначе ffprobe
ищет всё, что потеряется (потоки кроме видео/аудио, главы, обложку
`attached_pic`), и при наличии — `die()` (решение оператора: «Да, оставляем
die»; перенос через ffmpeg не делается, поддержка — бэклог 999.8).

Сценовая нарезка источников без pts — бэклог 999.8."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from enpipe.shared import proc as _proc
from enpipe.shared.logging import die, log

PTS_PROBE_WINDOW = 1000   # пакетов в ступени 1 (быстрый ответ для обычных источников)


def _pts_lines(src: Path, window: bool) -> List[str]:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if window:
        cmd += ["-read_intervals", f"%+#{PTS_PROBE_WINDOW}"]
    cmd += ["-show_entries", "packet=pts_time", "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (pts пакетов) упал: {proc.stderr.strip()}")
    lines = [ln.strip().rstrip(",").strip() for ln in proc.stdout.splitlines()]
    return [ln for ln in lines if ln]


def _classify(lines: List[str]) -> bool:
    """True, если среди пакетов есть числовой pts. Мусор вместо числа и N/A — die()."""
    has = False
    for ln in lines:
        if ln == "N/A":
            continue
        try:
            float(ln)
        except ValueError:
            die(f"ffprobe (pts пакетов): неожиданное значение {ln!r}")
        has = True
    return has


def probe_pts(src: Path) -> Tuple[bool, int]:
    """(нет pts у всех видеопакетов, сколько пакетов просмотрено)."""
    lines = _pts_lines(src, window=True)
    if not lines:
        die(f"{src.name}: ffprobe не нашёл ни одного видеопакета")
    if _classify(lines):
        return False, len(lines)
    lines = _pts_lines(src, window=False)   # ступень 2: весь файл
    if not lines:
        die(f"{src.name}: ffprobe не нашёл ни одного видеопакета")
    return (not _classify(lines)), len(lines)


def describe_single_chunk(packets: int) -> str:
    return (f"режим: один чанк на весь файл — у всех {packets} видеопакетов "
            f"источника нет pts (pts_time=N/A); сценовая нарезка выключена: "
            f"детекта сцен нет, --seek/--trim не используются "
            f"(сценовая нарезка таких источников — бэклог 999.8)")


def check_single_chunk_args(src: Path, choice, frm: int, to) -> None:
    if choice.path != "sw":
        die(f"{src.name}: одночанковый режим (источник без pts) проверен только "
            f"с --avsw, а решение о декоде — {choice.path}; задайте --decode sw")
    if frm != 0 or to is not None:
        die("--from/--to неприменимы: у источника без pts одна сцена на весь "
            "файл (сцен нет)")


def decoded_frame_count(src: Path) -> int:
    """Число кадров полного программного декода (ffprobe -count_frames)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (подсчёт кадров декодом) упал: {proc.stderr.strip()}")
    raw = proc.stdout.strip().rstrip(",").strip()
    try:
        n = int(raw)
    except ValueError:
        die(f"{src.name}: подсчёт кадров декодом дал {raw!r}")
    if n <= 0:
        die(f"{src.name}: подсчёт кадров декодом дал {n}")
    return n


def mux_source_args(src: Path) -> List[str]:
    """Аргументы источника для мукса; die() до энкода, если контейнер mkvmerge
    не читает, а в нём есть то, что потеряется."""
    proc = _proc.run(["mkvmerge", "-J", str(src)], capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        die(f"mkvmerge -J упал: {proc.stdout.strip()[-400:]}")
    try:
        info = json.loads(proc.stdout)
        container = info["container"]
        supported = bool(container["supported"])
    except (ValueError, KeyError, TypeError) as ex:
        die(f"mkvmerge -J: не разобрать ответ ({ex})")
    if supported:
        return ["--no-video", "--no-audio", str(src)]

    kind = container.get("type", "?")
    fprobe = _proc.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
         "-show_chapters", "-of", "json", str(src)],
        capture_output=True, text=True)
    if fprobe.returncode != 0:
        die(f"ffprobe (потоки и главы) упал: {fprobe.stderr.strip()}")
    try:
        data = json.loads(fprobe.stdout)
    except ValueError as ex:
        die(f"ffprobe (потоки и главы): не разобрать ответ ({ex})")
    lost: List[str] = []
    for st in data.get("streams", []):
        ctype = st.get("codec_type")
        if ctype == "video" and st.get("disposition", {}).get("attached_pic") == 1:
            lost.append("обложка (attached_pic)")
        elif ctype not in ("video", "audio"):
            lost.append(f"поток {ctype}")
    if data.get("chapters"):
        lost.append(f"глав: {len(data['chapters'])}")
    if lost:
        die(f"{src.name}: контейнер ({kind}) mkvmerge не читает, а в нём есть то, "
            f"что при муксе потеряется: {', '.join(lost)}; перенос не реализован "
            f"(бэклог 999.8), остановлено до энкода")
    log(f">> контейнер источника ({kind}) mkvmerge не читает; субтитров, глав и "
        f"вложений в нём нет — источник в мукс не добавляется")
    return []
