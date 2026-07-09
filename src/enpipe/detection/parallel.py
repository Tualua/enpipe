"""Параллельный детект: разбиение файла на сегменты с границами НА РЕАЛЬНЫХ
РЕЗАХ. Перенесено дословно из legacy/scene_detection.py:498-644 (D-13/D-15),
с заменой subprocess.run на enpipe.shared.proc.run (D-08).

Ключевая идея: если граница сегмента стоит точно на резе, результат совпадает
с последовательным — AdaptiveDetector и его min_scene_len сбрасываются в тех
же точках. Рез — почти всегда keyframe источника, поэтому границу можно
покадрово-точно сикать через -ss, а склейка сводится к конкатенации.

САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ (не логическое): импорт detect_scenes отложен
внутрь тела detect_scenes_parallel (оба fallback-вызова), чтобы разбить
detect.py<->parallel.py цикл, возникающий только из-за разделения одного
legacy-файла на два модуля — см. RESEARCH.md Pattern 2."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from scenedetect.platform import tqdm

from enpipe.shared import proc

from .config import DetectionConfig, PathLike, Scene, SceneDetectionError
from .detect import _build_scenes, _detect_relative, _min_scene_len
from .stream import QsvPipeStream, probe_source


def keyframes_in_window(path: PathLike, config: DetectionConfig, fps: float,
                        t0: float, t1: float) -> List[Tuple[int, float]]:
    """keyframe'ы источника (frame, pts_time) в окне [t0, t1] — быстрый seek
    ffprobe по интервалу, без полного скана."""
    cmd = [config.ffprobe_bin, "-v", "error", "-select_streams", "v:0",
           "-read_intervals", f"{max(0.0, t0):.3f}%{t1:.3f}",
           "-show_packets", "-show_entries", "packet=flags,pts_time",
           "-of", "csv=p=0", str(path)]
    try:
        out = proc.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return []
    kfs: List[Tuple[int, float]] = []
    for line in out.splitlines():
        parts = line.split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        kfs.append((round(t * fps), t))
    kfs.sort()
    return kfs


def find_boundary(path: PathLike, config: DetectionConfig, mark: int,
                  fps: float, total: int) -> Optional[Tuple[int, float, bool]]:
    """Найти границу сегмента у метки mark. Возвращает (kf_frame, kf_time,
    is_cut) — keyframe источника у первого реза ≥ mark, и совпал ли этот
    keyframe с самим резом. None, если реза в окне нет.

    Границу ставим на KEYFRAME (kf_time — точный pts, -ss/copyts/select дают
    точный счётчик кадров). Если keyframe НЕ совпал с резом (is_cut=False) —
    стык не настоящий, и получившуюся лишнюю сцену склеим при merge.

    Разгон ~10с до метки: адаптивный детектор и его min_scene_len у метки
    совпадают с полным проходом. rel точен благодаря copyts+select в потоке.
    """
    mark_t = mark / fps
    kfs = keyframes_in_window(path, config, fps, mark_t - 14.0, mark_t + 30.0)
    if not kfs:
        return None
    lead = [kf for kf in kfs if kf[1] <= mark_t - 10.0]
    start_frame, start_time = lead[-1] if lead else kfs[0]
    stream = QsvPipeStream(path, config,
                           seek_sec=(start_time if start_frame > 0 else None),
                           to_sec=mark_t + 30.0)
    rel = _detect_relative(stream, config)
    cuts = sorted(start_frame + p[0] for p in rel if p[0] > 0)
    cands = [c for c in cuts if c >= mark]
    if not cands:
        return None
    cut = cands[0]
    kf_frame, kf_time = min(kfs, key=lambda k: abs(k[0] - cut))
    return (kf_frame, kf_time, abs(kf_frame - cut) <= 1)


def _sanitize_boundaries(bnds: List[Tuple[int, float, bool]],
                         total: int) -> List[Tuple[int, float, bool]]:
    """Отсортировать, убрать дубли/выходы за [0,total]. Строго возрастающие.
    Каждая граница — (frame, time, is_cut)."""
    seen = {}
    for f, t, is_cut in bnds:
        if 0 <= f <= total:
            seen[f] = (t, is_cut)
    return [(f, seen[f][0], seen[f][1]) for f in sorted(seen)]


# Воркеры module-level (лямбды/замыкания не пиклятся) — по тому же паттерну,
# что и ProcessPoolExecutor-совместимые воркеры, даже когда фактически
# используются с ThreadPoolExecutor (см. ниже).
#
# ИЗМЕРЕНО (DEBT-03, scratch/profiling_debt03.py — воспроизводимо):
# ThreadPoolExecutor ОСТАВЛЕН, ProcessPoolExecutor НЕ переключён. Раньше
# здесь было утверждение "настоящий параллелизм в обход GIL нужен
# процессам" — оно противоречило коду (оба `with`-блока ниже уже
# ThreadPoolExecutor). Решение ниже основано на реальных числах, а не на
# этом утверждении.
#
# Layer 1 — реальный путь, синтетический клип 156с@24fps, jobs=1 vs jobs=2:
#   use_qsv=True:  jobs=1 10.88s, jobs=2 13.57s, speedup 0.80x
#   use_qsv=False: jobs=1  6.53s, jobs=2  9.81s, speedup 0.67x
#   На клипе такой длины jobs=2 ФАКТИЧЕСКИ МЕДЛЕННЕЕ: фиксированная
#   стоимость поиска границ (доп. ffmpeg-субпроцессы) и рестарта декодера
#   на каждый сегмент перекрывает выигрыш от параллелизма.
#
# Layer 2 — изолированный CPU-микробенч (чистый
# AdaptiveDetector.process_frame, БЕЗ subprocess/pipe I/O), 300 кадров,
# 2-way split против baseline на 1 воркере:
#   ThreadPoolExecutor:  baseline 0.71s, split 0.68s (внутренний speedup
#                        1.04x — детектор частично сериализуется по GIL)
#   ProcessPoolExecutor: baseline 1.08s, split 0.47s (внутренний speedup
#                        2.27x — реальный параллелизм в обход GIL)
#   ProcessPool/ThreadPool ratio = 1.43x
#
# Количественное правило (D-02): переключаться на ProcessPoolExecutor ТОЛЬКО
# ЕСЛИ (Layer-1 speedup при use_qsv=False < 1.5x) И (Layer-2 ratio > 2x).
# Первое условие выполнено (0.67x < 1.5x), второе — НЕТ (1.43x < 2x) →
# ОСТАВИТЬ потоки. GIL действительно частично сериализует CPU-детектор в
# потоках (это видно по Layer 2), но это малая доля общего wall-time,
# доминируемого subprocess/декод I/O, которое потоки и так корректно
# перекрывают; переход на процессы добавил бы реальную стоимость старта
# процесса и повторного импорта scenedetect/numpy/cv2 (дважды за вызов —
# по разу на каждый `with`-блок ниже), что на этом масштабе задачи ухудшило
# бы, а не улучшило, картину по реальному пути (Layer 1 это уже отражает).

def _boundary_worker(args: tuple) -> Optional[Tuple[int, float, bool]]:
    path, config, mark, fps, total = args
    return find_boundary(path, config, mark, fps, total)


def _segment_worker(args: tuple) -> List[Tuple[int, int]]:
    # 5-й элемент (progress_cb) опционален — 4-кортежные вызовы (ветка
    # show_progress=False через ex.map + test_parallel_merge) продолжают
    # работать без правок.
    path, config, seek_sec, to_sec = args[0], args[1], args[2], args[3]
    progress_cb = args[4] if len(args) > 4 else None
    stream = QsvPipeStream(path, config, seek_sec=seek_sec, to_sec=to_sec,
                           progress_cb=progress_cb)
    return _detect_relative(stream, config)


def detect_scenes_parallel(
    path: PathLike, config: DetectionConfig, jobs: int,
    show_progress: bool = False,
) -> List[Scene]:
    """show_progress=True рисует ОДИН агрегированный tqdm-бар поверх всех
    сегментов (см. шаг 2 ниже); дефолт False сохраняет прежний ex.map-путь
    байт-идентичным."""
    info = probe_source(path, config)
    fps = float(info.frame_rate)
    total = round(info.duration_sec * fps) if info.duration_sec else None

    # слишком короткий файл / не знаем длину -> последовательно
    min_span = max(2 * _min_scene_len(config, fps), round(60 * fps))
    if total is None or jobs < 2 or total < jobs * min_span:
        from .detect import detect_scenes  # deferred: breaks the cycle
        return detect_scenes(path, config, jobs=1, show_progress=show_progress)

    # 1) границы на реальных резах у меток i/jobs (пред-проходы параллельно)
    marks = [round(total * i / jobs) for i in range(1, jobs)]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        found = list(ex.map(
            _boundary_worker, [(path, config, m, fps, total) for m in marks]))
    bnds = _sanitize_boundaries(
        [(0, 0.0, True)] + [b for b in found if b]
        + [(total, total / fps, True)], total)
    if len(bnds) < 3:                       # границы схлопнулись -> последовательно
        from .detect import detect_scenes  # deferred: breaks the cycle
        return detect_scenes(path, config, jobs=1, show_progress=show_progress)

    # 2) детект каждого сегмента [b_i, b_{i+1}) параллельно, кадры -> абсолютные
    seg_args = []
    for i in range(len(bnds) - 1):
        is_last = (i + 1 == len(bnds) - 1)
        seg_args.append((
            path, config,
            bnds[i][1] if i > 0 else None,          # seek_sec (None для 1-го)
            None if is_last else bnds[i + 1][1],    # to_sec (None для последнего)
        ))
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        if not show_progress:
            # Байт-идентичный прежнему поведению путь — не трогать.
            results = list(ex.map(_segment_worker, seg_args))
        else:
            # Один общий бар, который двигают ПОКАДРОВЫЕ cb-вызовы из
            # read() КАЖДОГО сегментного потока (tqdm.update потокобезопасен)
            # — так бар плавно ползёт по мере декода, а не рывком по
            # завершению целого сегмента. КРИТИЧНО: results собираются ниже
            # СТРОГО по futures[i] (не as_completed) — cut-математика шагов
            # 3-4 зависит от порядка сегментов, а не от того, какой
            # закончился раньше; иначе склейка на «стыках-не-резах» сломается.
            # Сумма покадровых update ≈ total (ведущие -ss кадры отбрасывает
            # select в _build_command и в read() не попадают) — бар может
            # закрыться на ~99%, это косметика, tqdm недо/переполнение терпит.
            bar = tqdm(total=total, unit="frame",
                      desc=f"Детект сцен (jobs={jobs})")
            cb = bar.update
            seg_args_p = [a + (cb,) for a in seg_args]  # cb пятым элементом
            try:
                futures = [ex.submit(_segment_worker, a) for a in seg_args_p]
                results = [f.result() for f in futures]  # В ИСХОДНОМ ПОРЯДКЕ
            finally:
                bar.close()

    # 3) абсолютные кадры = накопленная сумма реальных счётчиков (НЕ round(pts*fps),
    #    он дрейфует от индекса декода). copyts+select в потоке убирает ведущие
    #    кадры -ss, поэтому счётчики сегментов точно стыкуются.
    pairs: List[Tuple[int, int]] = []
    offset = 0
    non_cut_offsets = set()             # стыки на keyframe'ах, что НЕ рез
    for i, rel in enumerate(results):
        if not rel:
            continue
        pairs.extend((s + offset, e + offset) for s, e in rel)
        offset += rel[-1][1]            # длина сегмента = конец последней сцены
        # offset теперь = старт следующего сегмента = граница bnds[i+1]
        if i + 1 <= len(bnds) - 2 and not bnds[i + 1][2]:
            non_cut_offsets.add(offset)
    if not pairs:
        raise SceneDetectionError(f"Не прочитано ни одного кадра: {path}")

    # 4) склеить сцены на «стыках-не-резах»: сегмент, начатый на keyframe, что не
    #    рез, дал лишнюю границу — соединяем её сцену с предыдущей.
    if non_cut_offsets:
        merged: List[Tuple[int, int]] = []
        for s, e in pairs:
            if merged and merged[-1][1] == s and s in non_cut_offsets:
                merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        pairs = merged
    return _build_scenes(pairs, fps)
