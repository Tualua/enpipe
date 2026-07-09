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
from enpipe.encoding.pipeline import resolve_output_path, run_encode
from enpipe.shared.batch import iter_input_videos, run_batch
from enpipe.shared.logging import die


def _pipeline_one(video: Path, scenes_path: Path, args) -> None:
    """Один прогон detect->encode для ОДНОГО видео (D-01/D-02): собирает
    detect-Namespace -> run_detect (пишет scenes_path) -> encode-Namespace
    (scenes = только что записанный путь) -> run_encode. Строго
    последовательно (без overlap/queue.Queue) -- run_encode стартует только
    после возврата run_detect. Никакой собственной пайплайн-логики -- обе
    стадии вызываются с теми же значениями атрибутов, что и ручной
    двухшаговый запуск, поэтому байт-идентичность гарантирована по
    построению. Namespace-поля НЕ переименовывать -- test_cli_run.py
    проверяет их поимённо (в т.ч. non-contamination между стадиями).

    Извлечено из run_pipeline (QUICK-260709-89t) для переиспользования и
    одиночным путём, и батч-веткой директории — тело дословно то же, что
    было в run_pipeline до извлечения; which-preflight остаётся в
    run_pipeline (делается один раз на весь батч, не на файл)."""
    detect_args = argparse.Namespace(
        input=video,
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
        video=video,
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


def run_pipeline(args) -> None:
    """Диспетчер `enpipe run` (D-01/D-02, QUICK-260709-89t): which-preflight
    -> ветвление файл-или-директория СТРОГО по `.is_dir()` (несуществующий
    путь и файл идут одиночным путём -- байт-идентичность с
    test_cli_run.py/test_cli_dispatch.py гарантирована тем, что ветка
    директории вообще не задействуется).

    ДОПОЛНИТЕЛЬНЫЙ fail-fast preflight (аддитивный UX, не меняет поведение
    ни run_detect, ни run_encode -- у run_encode остаётся СВОЙ preflight):
    проверяет инструменты энкод-стадии ДО запуска (потенциально долгого)
    детекта, чтобы не тратить его впустую, если энкодер всё равно упадёт из-за
    отсутствующего инструмента."""
    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")

    if args.video.is_dir():
        # GUARD: батч пробрасывает out/workdir/csv в КАЖДОЕ видео папки —
        # если они указывают на ОДИН путь/файл, выходы всех видео
        # схлопываются в один, и второе+ видео молча уходит в skipped
        # вместо кодирования (T-89t-04, потеря видео тихо — нарушение
        # correctness-first). --scenes тоже одноместный: .scenes должен
        # писаться РЯДОМ с каждым файлом, а не в один общий путь.
        if args.scenes is not None:
            die("--scenes нельзя с папкой: .scenes пишется рядом с каждым файлом")
        if args.out is not None and not args.out.is_dir():
            die("в батче -o должен быть папкой или опущен, иначе все выходы "
                "схлопнутся в один файл")
        if args.workdir is not None:
            die("--workdir нельзя с папкой: единый workdir смешает чанки разных источников")
        if args.csv is not None:
            die("--csv нельзя с папкой: единый csv перезапишется каждым видео")

        videos = iter_input_videos(args.video, getattr(args, "recursive", False))
        if not videos:
            die("в папке нет видеофайлов")

        def process_one(v: Path) -> None:
            _pipeline_one(v, Path(str(v) + ".scenes"), args)

        def should_skip(v: Path) -> Optional[str]:
            return "уже готов" if resolve_output_path(v, args.out).exists() else None

        run_batch(videos, process_one, "run", should_skip)
        return

    # одиночный файл ИЛИ несуществующий путь: байт-идентично прежнему
    scenes_path = args.scenes or Path(str(args.video) + ".scenes")
    _pipeline_one(args.video, scenes_path, args)


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
    detect_p.add_argument("--recursive", action="store_true",
                           help="рекурсивный обход вложенных папок (только если input — папка)")
    detect_p.set_defaults(func=run_detect)

    encode_p = sub.add_parser(
        "encode", description="Сцен-осознанный AV1-энкод (Arc/QSV)")
    encode_p.add_argument("video", type=Path)
    encode_p.add_argument("scenes", type=Path, nargs="?", default=None,
                           help="scene_out.log от enpipe detect "
                                "(по умолчанию <видео>.scenes рядом с источником)")
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
    encode_p.add_argument("--recursive", action="store_true",
                           help="рекурсивный обход вложенных папок (только если video — папка)")
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
    run_p.add_argument("--recursive", action="store_true",
                        help="рекурсивный обход вложенных папок (только если video — папка)")
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
