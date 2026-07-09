"""Единая точка входа `enpipe`: argparse-диспетчер над `enpipe detect`,
`enpipe encode` и `enpipe run` (D-01, фаза 5). Чистая обвязка — вся логика в
detection.pipeline.run_detect и encoding.pipeline.run_encode (D-01/D-09:
без изменения поведения). Реконструирует ДОСЛОВНО оба legacy-argparse-
поверхности (legacy/scene_detection.py:648-663,
legacy/encode_scenes.py:517-530), сохраняя обе асимметрии дефолтов --jobs
(detect: хардкод 4; encode: encoding.pipeline.JOBS из env) и оба разных
dest-имени для файла сцен (-o/--output у detect, -o/--out у encode).

`enpipe run <video>` (фаза 5, D-01..D-09) — третий, композитный subcommand:
тонкий последовательный оркестратор run_detect -> run_encode в одном
процессе, без overlap/queue.Queue (см. run_pipeline ниже). `--jobs`
коллизия между стадиями решена отдельными флагами `--detect-jobs`/
`--encode-jobs` (D-03); `detect`/`encode` остаются НЕИЗМЕННЫМИ."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

from enpipe.detection.pipeline import run_detect
from enpipe.encoding.pipeline import JOBS as ENCODE_JOBS
from enpipe.encoding.pipeline import run_encode
from enpipe.shared.logging import die


def run_pipeline(args) -> None:
    """Тонкий последовательный оркестратор `enpipe run` (D-01/D-02): собирает
    detect-Namespace -> run_detect (пишет <video>.scenes) -> encode-Namespace
    (scenes = только что записанный путь) -> run_encode. Строго
    последовательно (без overlap/queue.Queue) -- run_encode стартует только
    после возврата run_detect. Никакой собственной пайплайн-логики -- обе
    стадии вызываются с теми же значениями атрибутов, что и ручной
    двухшаговый запуск, поэтому байт-идентичность гарантирована по
    построению.

    ДОПОЛНИТЕЛЬНЫЙ fail-fast preflight (аддитивный UX, не меняет поведение
    ни run_detect, ни run_encode -- у run_encode остаётся СВОЙ preflight):
    проверяет инструменты энкод-стадии ДО запуска (потенциально долгого)
    детекта, чтобы не тратить его впустую, если энкодер всё равно упадёт из-за
    отсутствующего инструмента."""
    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")

    # тот же путь, что использует enpipe detect (detection/pipeline.py:42);
    # сохраняется (D-04), не удаляется
    scenes_path = args.scenes or Path(str(args.video) + ".scenes")

    detect_args = argparse.Namespace(
        input=args.video,
        output=scenes_path,
        width=args.width,
        threshold=args.threshold,
        min_scene_len_frames=args.min_scene_len_frames,
        min_scene_len=args.min_scene_len,
        no_qsv=args.no_qsv,
        qsv_device=args.qsv_device,
        jobs=args.detect_jobs,
    )
    run_detect(detect_args)

    encode_args = argparse.Namespace(
        video=args.video,
        scenes=scenes_path,
        out=args.out,
        frm=args.frm,
        to=args.to,
        workdir=args.workdir,
        keep=args.keep,
        jobs=args.encode_jobs,
        no_audio=args.no_audio,
        no_metrics=args.no_metrics,
        csv=args.csv,
    )
    run_encode(encode_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enpipe")
    sub = parser.add_subparsers(dest="command", required=True)

    detect_p = sub.add_parser(
        "detect", description="Детектирование сцен (QSV + PySceneDetect)")
    detect_p.add_argument("input", type=Path)
    detect_p.add_argument("-o", "--output", type=Path, default=None,
                           help="файл со списком сцен (по умолчанию <видео>.scenes)")
    detect_p.add_argument("--width", type=int, default=320)
    detect_p.add_argument("--threshold", type=float, default=3.0)
    detect_p.add_argument("--min-scene-len-frames", type=int, default=None,
                           help="мин. длина сцены в КАДРАХ (приоритетнее секунд; дефолт 72)")
    detect_p.add_argument("--min-scene-len", type=float, default=None,
                           help="мин. длина сцены в секундах (если кадры не заданы; дефолт 3.0)")
    detect_p.add_argument("--no-qsv", action="store_true", help="программный декод")
    detect_p.add_argument("--qsv-device", default=None)
    detect_p.add_argument("--jobs", type=int, default=4,
                           help="параллельных сегментов детекта (дефолт 4; 1 = последовательно)")
    detect_p.set_defaults(func=run_detect)

    encode_p = sub.add_parser(
        "encode", description="Сцен-осознанный AV1-энкод (Arc/QSV)")
    encode_p.add_argument("video", type=Path)
    encode_p.add_argument("scenes", type=Path, help="scene_out.log от enpipe detect")
    encode_p.add_argument("-o", "--out", type=Path, default=None,
                           help="итоговый .mkv (по умолчанию <видео>.av1.mkv рядом с источником); "
                                "если указан путь к СУЩЕСТВУЮЩЕЙ директории, файл кладётся внутрь "
                                "неё как <ориг-имя>.Encoded.<ext>")
    encode_p.add_argument("--from", dest="frm", type=int, default=0, help="первая сцена")
    encode_p.add_argument("--to", dest="to", type=int, default=None, help="последняя (искл.)")
    encode_p.add_argument("--workdir", type=Path, default=None, help="папка чанков")
    encode_p.add_argument("--keep", action="store_true", help="не удалять чанки")
    encode_p.add_argument("--jobs", type=int, default=ENCODE_JOBS)
    encode_p.add_argument("--no-audio", action="store_true", help="не кодировать аудио")
    encode_p.add_argument("--no-metrics", action="store_true",
                           help="не считать PSNR/SSIM (быстрее)")
    encode_p.add_argument("--csv", type=Path, default=None,
                           help="CSV с метриками (по умолчанию <out>.metrics.csv)")
    encode_p.set_defaults(func=run_encode)

    run_p = sub.add_parser(
        "run",
        description="Полный конвейер одной командой: детект сцен -> AV1-энкод (D-01)")
    run_p.add_argument("video", type=Path)
    run_p.add_argument("-o", "--out", type=Path, default=None,
                        help="итоговый .mkv (энкод-семантика; см. enpipe encode -o); если указан "
                             "путь к СУЩЕСТВУЮЩЕЙ директории, файл кладётся внутрь неё как "
                             "<ориг-имя>.Encoded.<ext>")
    run_p.add_argument("--scenes", type=Path, default=None,
                        help="путь для <video>.scenes (по умолчанию рядом с видео)")
    # --- detect-опции (D-06) --- #
    run_p.add_argument("--width", type=int, default=320)
    run_p.add_argument("--threshold", type=float, default=3.0)
    run_p.add_argument("--min-scene-len-frames", type=int, default=None,
                        help="мин. длина сцены в КАДРАХ (приоритетнее секунд; дефолт 72)")
    run_p.add_argument("--min-scene-len", type=float, default=None,
                        help="мин. длина сцены в секундах (если кадры не заданы; дефолт 3.0)")
    run_p.add_argument("--no-qsv", action="store_true", help="программный декод")
    run_p.add_argument("--qsv-device", default=None)
    run_p.add_argument("--detect-jobs", type=int, default=4,
                        help="параллельных сегментов детекта (дефолт 4; 1 = последовательно)")
    # --- encode-опции (D-06) --- #
    run_p.add_argument("--from", dest="frm", type=int, default=0, help="первая сцена")
    run_p.add_argument("--to", dest="to", type=int, default=None, help="последняя (искл.)")
    run_p.add_argument("--workdir", type=Path, default=None, help="папка чанков")
    run_p.add_argument("--keep", action="store_true", help="не удалять чанки")
    run_p.add_argument("--no-audio", action="store_true", help="не кодировать аудио")
    run_p.add_argument("--no-metrics", action="store_true",
                        help="не считать PSNR/SSIM (быстрее)")
    run_p.add_argument("--csv", type=Path, default=None,
                        help="CSV с метриками (по умолчанию <out>.metrics.csv)")
    run_p.add_argument("--encode-jobs", type=int, default=ENCODE_JOBS,
                        help="параллельных qsvencc-сессий (дефолт из JOBS/env)")
    run_p.set_defaults(func=run_pipeline)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    # Верхнеуровневый перехват Ctrl-C: без него KeyboardInterrupt всплывает
    # необработанным исключением (в т.ч. из потоков ThreadPoolExecutor на
    # этапе энкода) и печатает шумный Python-трейсбек. 130 -- стандартный
    # код выхода для SIGINT (128 + номер сигнала). Дочерние ffmpeg/qsvencc/
    # mkvmerge и ThreadPoolExecutor гибнут сами по групповому SIGINT и при
    # разворачивании стека -- никаких signal-хендлеров или kill по группе не
    # добавляем (локированное решение).
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        args.func(args)
    except KeyboardInterrupt:
        print("enpipe: прервано (Ctrl-C)", file=sys.stderr)
        raise SystemExit(130)
