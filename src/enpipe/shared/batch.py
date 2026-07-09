"""Дискавери видео-файлов в директории и батч-оркестрация верхнего уровня
для `enpipe run/detect/encode` (QUICK-260709-89t). Единая точка правды: и
какие файлы считаются «видео на входе», и как политика collect-then-report
(продолжать при ошибке одного файла, сводка + ненулевой код в конце)
применяется одинаково во всех трёх подкомандах — вместо трёх независимых
копий одной и той же логики.

Leaf-модуль: импортирует только stdlib + `enpipe.shared.logging` (die/log).
НЕ импортировать отсюда detection/encoding/cli — они импортируют ЭТОТ
модуль, обратная зависимость создала бы цикл."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from enpipe.shared.logging import die, log

# --- дискавери --- #

# нижнерегистровые суффиксы «известных» видео-контейнеров; всё остальное
# (.scenes, .csv, .obu-чанки и т.п.) на батч-вход не попадает
VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".m4v", ".mov", ".ts", ".m2ts", ".webm",
    ".avi", ".mpg", ".mpeg", ".wmv", ".flv",
})


def _is_own_output(name: str) -> bool:
    """Исключает собственные выходы пайплайна из входа: иначе повторный
    прогон по той же папке взял бы вчерашний `movie.av1.mkv`/
    `movie.Encoded.mkv` за новый источник и переэнкодил бы уже сжатое видео
    (T-89t-01). Сравнение без учёта регистра."""
    lower = name.lower()
    return fnmatch.fnmatch(lower, "*.encoded.*") or lower.endswith(".av1.mkv")


def iter_input_videos(path: Path, recursive: bool) -> List[Path]:
    """path — файл: одиночный режим, возвращает [path] независимо от
    расширения (даже путь без видео-суффикса — вызывающий уже решил, что
    это видео). path — директория: allowlist по VIDEO_EXTS (T-89t-02),
    минус собственные выходы (T-89t-01), обход `rglob("*")` при recursive
    иначе только прямые дети `iterdir()`. Несуществующий путь -> [] (die —
    забота вызывающего, здесь только дискавери)."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []

    walker: Iterable[Path] = path.rglob("*") if recursive else path.iterdir()
    videos = [
        p for p in walker
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not _is_own_output(p.name)
    ]
    return sorted(videos)


# --- батч-оркестрация --- #

def run_batch(
    videos: List[Path],
    process_one: Callable[[Path], None],
    label: str,
    should_skip: Optional[Callable[[Path], Optional[str]]] = None,
) -> None:
    """collect-then-report батч-обёртка (тот же принцип, что и
    errors: List[str] в legacy encode_scenes.py::main): один упавший файл
    не должен оборвать обработку остальных.

    Ловим И SystemExit, И Exception вокруг process_one — это осознанное
    отступление от правила «worker-функции возвращают (ok,err), а не
    вызывают die()»: process_one здесь оборачивает run_detect/run_encode
    для ОДНОГО файла, а те вызывают die() (SystemExit) на реальных
    ошибках. run_batch — оркестратор верхнего уровня, а не фоновый поток,
    поэтому ему разрешено ловить SystemExit одного файла и продолжать
    батч; итоговый die() всё равно поднимается после обхода всех файлов,
    если были падения."""
    ok: List[Path] = []
    skipped: List[Path] = []
    failed: List[str] = []

    for video in videos:
        reason = should_skip(video) if should_skip is not None else None
        if reason is not None:
            skipped.append(video)
            log(f">> [{label}] пропущено: {video} ({reason})")
            continue
        try:
            process_one(video)
        except (SystemExit, Exception) as exc:  # noqa: BLE001 — collect-then-report
            failed.append(f"{video}: {exc}")
            log(f">> [{label}] ОШИБКА: {video}: {exc}")
            continue
        ok.append(video)

    log(f">> [{label}] батч завершён: ок {len(ok)} / пропущено {len(skipped)} / "
        f"упало {len(failed)}")

    if failed:
        die(f"батч [{label}]: упало {len(failed)} файл(ов):\n  "
            + "\n  ".join(failed[:10]))
