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
аккуратный die()."""

from __future__ import annotations

from pathlib import Path

from .config import DetectionConfig
from .detect import detect_scenes


def run_detect(args) -> None:
    # приоритет: кадры -> секунды -> дефолт 72 кадра (≈3с при 24fps)
    # (дословно из legacy/scene_detection.py:666-672)
    if args.min_scene_len_frames is not None:
        msl_frames, msl_sec = args.min_scene_len_frames, 3.0
    elif args.min_scene_len is not None:
        msl_frames, msl_sec = None, args.min_scene_len
    else:
        msl_frames, msl_sec = 72, 3.0

    cfg = DetectionConfig(
        analysis_width=args.width,
        use_qsv=not args.no_qsv,
        qsv_device=args.qsv_device,
        adaptive_threshold=args.threshold,
        min_scene_len_frames=msl_frames,
        min_scene_len_sec=msl_sec,
    )
    # по умолчанию: <путь-к-видео>.scenes (напр. movie.mkv -> movie.mkv.scenes)
    out_path = args.output or Path(str(args.input) + ".scenes")

    scenes = detect_scenes(args.input, cfg, jobs=args.jobs)
    lines = [
        f"scene {scene.index:4d}  frames [{scene.start_frame:8d}, "
        f"{scene.end_frame:8d})  {scene.start_sec:10.3f}s .. {scene.end_sec:10.3f}s"
        for scene in scenes
    ]
    out_path.write_text("\n".join(lines) + "\n")
    print(f"{len(scenes)} сцен -> {out_path}")
