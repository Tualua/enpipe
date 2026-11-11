"""Оркестрация детект-этапа для CLI: сборка DetectionConfig из аргументов,
вызов detect_scenes, форматирование и запись <video>.scenes. Перенесено
дословно из __main__ (legacy/scene_detection.py:647-692) минус argparse-блок
-> run_detect(args) (D-02), симметрично run_encode(args) в
encoding/pipeline.py.

САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ (не логическое; D-09/legacy parity): в отличие
от run_encode, здесь НЕТ shutil.which-preflight по инструментам — у
legacy/scene_detection.py's __main__ его никогда не было (preflight есть
только в encode_scenes.py's main()), поэтому его добавление сюда было бы
изменением поведения. Отсутствие ffmpeg/ffprobe проявится как обычный
FileNotFoundError из недр detect_scenes, ровно как в legacy, а не как
аккуратный die().

ИЗМЕНЕНИЕ ПОВЕДЕНИЯ (фаза 10.1): раньше `enpipe detect` не зависел от
qsvencc; теперь в режиме auto (дефолт, D-03) он спрашивает qsvencc
(`--check-features`) и ffprobe, чтобы выбрать аппаратный или программный
декод. При отсутствии qsvencc -- понятный отказ D-04 «qsvencc не найден …
задайте --decode hw или --decode sw» до детекта и без .scenes; с явным
`--decode hw|sw` qsvencc детекту не нужен. which-preflight по-прежнему нет
(санкционированное отклонение выше не меняется). Известное ограничение
(deferred): на VC-1 в mkv параллельный детект тихо уходит в
последовательный (`keyframes_in_window` не видит `pts_time=N/A`), результат
корректен."""

from __future__ import annotations

import sys
import time
from argparse import Namespace
from pathlib import Path

from enpipe.shared.batch import iter_input_videos, run_batch
from enpipe.shared.decode import decode_mode_from_args, describe_decode, resolve_decode
from enpipe.shared.logging import die

from .config import DetectionConfig
from .detect import detect_scenes


def run_detect(args) -> None:
    # fail-fast взаимоисключения --no-qsv/--decode hw (D-06) -- до батча
    mode = decode_mode_from_args(args)

    # --- батч-ветка: args.input — директория (QUICK-260709-89t) --- #
    if args.input.is_dir():
        # -o одноместный: .scenes должен писаться РЯДОМ с каждым файлом
        # папки, а не в один общий путь (T-89t-04).
        if args.output is not None:
            die("-o нельзя с папкой: .scenes пишется рядом с каждым файлом")

        videos = iter_input_videos(args.input, getattr(args, "recursive", False))
        if not videos:
            die("в папке нет видеофайлов")

        def process_one(v: Path) -> None:
            # decode_choice=None: решение о декоде у каждого файла своё (D-05)
            run_detect(Namespace(**{**vars(args), "input": v, "output": None,
                                    "decode_choice": None}))

        def should_skip(v: Path):
            out_path = Path(str(v) + ".scenes")
            return "уже готов" if out_path.exists() else None

        run_batch(videos, process_one, "детект", should_skip)
        return

    # --- одиночный файл ИЛИ несуществующий путь: без изменений --- #
    # приоритет: кадры -> секунды -> дефолт 72 кадра (≈3с при 24fps)
    # (дословно из legacy/scene_detection.py:666-672)
    if args.min_scene_len_frames is not None:
        msl_frames, msl_sec = args.min_scene_len_frames, 3.0
    elif args.min_scene_len is not None:
        msl_frames, msl_sec = None, args.min_scene_len
    else:
        msl_frames, msl_sec = 72, 3.0

    # Решение о декоде -- до любой работы и до записи .scenes. Из `run` оно
    # приходит готовым и уже залогированным (D-05). Строка идёт в stderr,
    # чтобы не смешаться с парсибельной итоговой строкой stdout (D-12).
    choice = getattr(args, "decode_choice", None)
    if choice is None:
        choice = resolve_decode(args.input, mode)
        print(describe_decode(choice), file=sys.stderr, flush=True)

    cfg = DetectionConfig(
        analysis_width=args.width,
        use_qsv=(choice.path == "hw"),
        qsv_device=args.qsv_device,
        adaptive_threshold=args.threshold,
        min_scene_len_frames=msl_frames,
        min_scene_len_sec=msl_sec,
    )
    # по умолчанию: <путь-к-видео>.scenes (напр. movie.mkv -> movie.mkv.scenes)
    out_path = args.output or Path(str(args.input) + ".scenes")

    # СТАРТ/ФИНИШ-строки и живой прогресс-бар — в stderr, чтобы не смешиваться
    # с парсибельной итог-строкой в stdout (ниже).
    mode = "параллельный" if args.jobs and args.jobs > 1 else "последовательный"
    print(f"Детекция сцен: {args.input} (jobs={args.jobs}, {mode})",
          file=sys.stderr, flush=True)
    t0 = time.monotonic()
    scenes = detect_scenes(args.input, cfg, jobs=args.jobs, show_progress=True)
    print(f"Готово: {len(scenes)} сцен за {time.monotonic() - t0:.1f}с",
          file=sys.stderr, flush=True)
    lines = [
        f"scene {scene.index:4d}  frames [{scene.start_frame:8d}, "
        f"{scene.end_frame:8d})  {scene.start_sec:10.3f}s .. {scene.end_sec:10.3f}s"
        for scene in scenes
    ]
    out_path.write_text("\n".join(lines) + "\n")
    print(f"{len(scenes)} сцен -> {out_path}")
