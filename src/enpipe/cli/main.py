"""Единая точка входа `enpipe`: argparse-диспетчер над `enpipe detect` и
`enpipe encode` (D-01). Чистая обвязка — вся логика в
detection.pipeline.run_detect и encoding.pipeline.run_encode (D-01/D-09:
без изменения поведения). Реконструирует ДОСЛОВНО оба legacy-argparse-
поверхности (legacy/scene_detection.py:648-663,
legacy/encode_scenes.py:517-530), сохраняя обе асимметрии дефолтов --jobs
(detect: хардкод 4; encode: encoding.pipeline.JOBS из env) и оба разных
dest-имени для файла сцен (-o/--output у detect, -o/--out у encode)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from enpipe.detection.pipeline import run_detect
from enpipe.encoding.pipeline import JOBS as ENCODE_JOBS
from enpipe.encoding.pipeline import run_encode


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
    encode_p.add_argument("-o", "--out", type=Path, default=None)
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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
