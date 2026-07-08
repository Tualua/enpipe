"""Оркестрация полного энкода: чтение сцен, keyframe-таблица, HDR-флаги,
параллельное кодирование чанков с упорядоченной high-water-mark склейкой,
параллельное аудио, CSV-метрики, финальный мукс mkvmerge. Перенесено
дословно из main() (legacy/encode_scenes.py:56,110-122,515-724) минус
argparse-блок -> run_encode(args) (D-13/D-15).

САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ (не логическое; review opencode HIGH #2,
consensus #6/#7): из main() вырезан ТОЛЬКО argparse-парсинг
(ArgumentParser/add_argument/parse_args) — это CLI-обвязка фазы 4. Preflight-
проверка (shutil.which по qsvencc/ffprobe/ffmpeg/mkvmerge +
args.video.is_file()) СОХРАНЕНА как первые операторы run_encode — иначе
поведение die() при отсутствии инструмента было бы молча потеряно, что
противоречило бы D-13 "без изменения логики". Параметр run_encode(args)
остаётся argparse.Namespace-подобным объектом с прежними именами атрибутов
(video/scenes/out/frm/to/workdir/keep/jobs/no_audio/no_metrics/csv), чтобы
CLI фазы 4 мог собрать реальный Namespace и вызвать run_encode(args) без
изменений. argv, проверки инструментов и байты вывода не меняются."""

from __future__ import annotations

import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set, Tuple, Union

from enpipe.shared import proc as _proc
from enpipe.shared.logging import _START, die, log, step

from .audio import encode_audio
from .chunk import GOP_LEN, ICQ, QPMAX, chunk_command, count_frames, encode_chunk
from .hdr import detect_hdr
from .keyframes import compute_chunk_seek_trim, keyframe_table
from .metrics import write_metrics_csv
from .scenes_io import read_scenes

JOBS = int(os.environ.get("JOBS", "3"))            # параллельных qsvencc-сессий


def contiguous_run(next_append: int, ready: Union[Dict[int, int], Set[int]]) -> List[int]:
    """Индексы, готовые к склейке прямо сейчас, по порядку, для текущей
    «высокой воды». Чистая функция: не мутирует ready и не двигает
    next_append — это делает вызывающий (D-05, фаза 2, DEBT-02). Вынесено
    дословно из flush_appends()'s `while next_append in ready` (было
    pipeline.py:134-143 до извлечения)."""
    out: List[int] = []
    i = next_append
    while i in ready:
        out.append(i)
        i += 1
    return out


def probe_fps(src: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=avg_frame_rate,r_frame_rate",
           "-of", "json", str(src)]
    data = json.loads(_proc.run(cmd, capture_output=True, text=True, check=True).stdout)
    st = data["streams"][0]
    for key in ("avg_frame_rate", "r_frame_rate"):
        val = st.get(key, "")
        if val and "/" in val:
            num, den = val.split("/")
            if int(den) != 0 and int(num) != 0:
                return int(num) / int(den)
    die("не удалось определить fps источника")


def run_encode(args) -> None:
    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")
    if not args.video.is_file():
        die(f"нет файла: {args.video}")

    out = args.out or args.video.with_name(args.video.stem + ".av1.mkv")
    workdir = args.workdir or out.with_name(out.stem + ".chunks")
    workdir.mkdir(parents=True, exist_ok=True)

    scenes_all = read_scenes(args.scenes)
    lo = max(0, args.frm)
    hi = args.to if args.to is not None else len(scenes_all)
    scenes = scenes_all[lo:hi]
    if not scenes:
        die("пустой диапазон сцен (--from/--to)")
    partial = (lo != 0) or (hi != len(scenes_all))

    metrics_on = not args.no_metrics
    log(f">> источник: {args.video.name}")
    log(f">> сцен: {len(scenes)} [{lo},{hi})  ICQ={ICQ} qp-max={QPMAX} "
        f"gop={GOP_LEN} jobs={args.jobs} metrics={'on' if metrics_on else 'off'}")

    fps = probe_fps(args.video)
    log(f">> fps={fps:.5f}")
    with step("чтение keyframe-таблицы источника"):
        table = keyframe_table(args.video, fps)
    log(f">> keyframe'ов в источнике: {len(table)}")
    hdr_flags = detect_hdr(args.video)
    if hdr_flags:
        log(f">> HDR/DV: {' '.join(hdr_flags)}")

    total_expect = sum(e - s for s, e in scenes)

    # --- аудио СРАЗУ, параллельно фазе чанков (CPU/ffmpeg vs GPU/qsvencc) ---
    audio = workdir / "audio.mka"
    audio_pool = ThreadPoolExecutor(max_workers=1)
    audio_future = None
    audio_t0 = time.monotonic()
    if not args.no_audio:
        a_ss = (scenes[0][0] / fps) if partial else None
        a_dur = (total_expect / fps) if partial else None
        audio_future = audio_pool.submit(encode_audio, args.video, audio, a_ss, a_dur)
        log("▶ аудио стартовало параллельно с чанками")

    # --- задания на чанки ---
    tasks = []
    chunk_paths: List[Path] = []
    meta: Dict[int, Tuple[int, int, str, str]] = {}  # idx -> (s, e, seek, trim)
    for i, (s, e) in enumerate(scenes):
        seek, trim = compute_chunk_seek_trim(table, s, e)
        cp = workdir / f"chunk_{i:05d}.obu"
        chunk_paths.append(cp)
        cmd = chunk_command(args.video, seek, trim, cp, hdr_flags, metrics_on)
        tasks.append((i, cmd, cp, e - s))
        meta[i] = (s, e, seek, trim)

    # --- кодирование чанков + инкрементальная упорядоченная склейка ---
    # Чанки финишируют не по порядку (параллель), а склейка обязана быть в
    # порядке сцен -> «высокая вода»: дописываем chunk i, когда готовы i и все
    # до него. I/O склейки прячется за GPU-энкодом; чанк удаляется сразу после
    # дозаписи (пиковый диск вдвое меньше).
    log(f"▶ кодирую {len(tasks)} чанков (по {args.jobs} параллельно), "
        f"склеиваю по мере готовности…")
    phase_t0 = time.monotonic()
    movie = workdir / "movie.obu"
    movie_fh = movie.open("wb")
    next_append = 0
    ready: Dict[int, int] = {}      # idx -> кадров (готов, ждёт очереди на склейку)
    rows: Dict[int, dict] = {}      # idx -> строка метрик для CSV
    ctimes: List[float] = []
    errors: List[str] = []
    done = 0

    def flush_appends() -> None:
        nonlocal next_append
        for i in contiguous_run(next_append, ready):
            cp = chunk_paths[i]
            with cp.open("rb") as r:
                shutil.copyfileobj(r, movie_fh, length=8 << 20)
            movie_fh.flush()
            if not args.keep:
                cp.unlink(missing_ok=True)
            next_append = i + 1

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(encode_chunk, t): t[0] for t in tasks}
        for fut in as_completed(futs):
            idx, got, err, el, info = fut.result()
            done += 1
            s, e, seek, trim = meta[idx]
            head = f"  [{done}/{len(tasks)}] чанк {idx+lo:>4d} сцена[{s},{e})"
            if err:
                errors.append(f"чанк {idx+lo}: {err}")
                log(f"{head} — ОШИБКА за {el:.1f}с: {err}")
                continue
            ctimes.append(el)
            ss, ps = info.get("ssim_all"), info.get("psnr_avg")
            mtxt = (f" SSIM {ss:.5f} PSNR {ps:.2f}dB"
                    if ss is not None and ps is not None else " (метрик нет)")
            log(f"{head}: {got}к/{el:.1f}с {(e-s)/el:.0f}fps{mtxt}")
            rows[idx] = {
                "scene": idx + lo, "start_frame": s, "end_frame": e,
                "frames": e - s, "seek": seek, "trim": trim,
                "encode_sec": round(el, 2), "fps": round((e - s) / el, 1),
                "size_mb": round(info.get("size", 0) / 1e6, 2),
                "ssim_all": info.get("ssim_all"), "ssim_db": info.get("ssim_db"),
                "psnr_avg": info.get("psnr_avg"),
                "ssim_y": info.get("ssim_y"), "psnr_y": info.get("psnr_y"),
            }
            ready[idx] = got
            flush_appends()          # дописать в порядке всё готовое подряд
    movie_fh.close()
    phase_wall = time.monotonic() - phase_t0
    if ctimes:
        log(f"✔ чанки+склейка — wall {phase_wall:.1f}с, сумма энкода {sum(ctimes):.1f}с "
            f"(параллелизм ×{sum(ctimes)/phase_wall:.1f}), "
            f"на чанк min/avg/max {min(ctimes):.1f}/"
            f"{sum(ctimes)/len(ctimes):.1f}/{max(ctimes):.1f}с")
    if errors:
        die("часть чанков не удалась — файл собирать нельзя:\n  "
            + "\n  ".join(errors[:10]))
    if next_append != len(tasks):
        die(f"склейка неполная: дописано {next_append} из {len(tasks)} чанков")

    # --- проверка кадров склейки ---
    with step("проверка кадров склейки"):
        got = count_frames(movie)
    if got != total_expect:
        die(f"после склейки кадров {got}, ожидалось {total_expect} — стоп")
    log(f">> склейка: {got} кадров (совпало с суммой сцен)")
    if not partial and scenes_all and got != scenes_all[-1][1]:
        log(f"   ВНИМАНИЕ: кадров {got}, а конец последней сцены "
            f"{scenes_all[-1][1]} — расхождение с исходником")

    # --- дождаться аудио (шло параллельно фазе чанков) ---
    has_audio = False
    if args.no_audio:
        log(">> аудио: пропущено (--no-audio)")
    else:
        with step("ожидание аудио (шло параллельно)"):
            has_audio, aerr = audio_future.result()
        if aerr:
            die(f"кодирование аудио упало: {aerr}")
        log(f">> аудио: {'готово' if has_audio else 'нет дорожек'} "
            f"(общее время {time.monotonic()-audio_t0:.1f}с)")
    audio_pool.shutdown(wait=True)

    # --- CSV с метриками (строка на сцену + итоговая) ---
    if rows:
        csv_path = args.csv or Path(str(out) + ".metrics.csv")
        total = write_metrics_csv(csv_path, rows)
        log(f">> метрики -> {csv_path}")
        if total.get("ssim_all") is not None:
            log(f">> ИТОГО (frame-weighted): SSIM {total['ssim_all']:.5f} "
                f"PSNR {total['psnr_avg']:.2f}dB  | {total['frames']} кадров, "
                f"{total['size_mb']:.0f} MB")

    # --- финальный мукс ---
    num, den = fps.as_integer_ratio() if isinstance(fps, float) else (fps, 1)
    # точный рациональный fps для mkvmerge (24000/1001 и т.п.)
    fps_str = f"{round(fps*1001)}/1001" if abs(fps*1001 - round(fps*1001)) < 0.5 else f"{num}/{den}"
    mux = ["mkvmerge", "-o", str(out),
           "--default-duration", f"0:{fps_str}p", str(movie)]
    if has_audio:
        mux += [str(audio)]
    if not partial:
        # сабы + главы + вложения из источника (видео/аудио источника не берём)
        mux += ["--no-video", "--no-audio", str(args.video)]
    with step("финальный мукс (mkvmerge)"):
        proc = _proc.run(mux, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # 1 = предупреждения mkvmerge
        die(f"mkvmerge упал: {proc.stdout.strip()[-800:]}")

    if not args.keep:
        for cp in chunk_paths:
            cp.unlink(missing_ok=True)
        movie.unlink(missing_ok=True)
        audio.unlink(missing_ok=True)
        try:
            workdir.rmdir()
        except OSError:
            pass

    insz = args.video.stat().st_size
    outsz = out.stat().st_size
    log(f">> ГОТОВО за {time.monotonic() - _START:.1f}с: {out}")
    log(f">>   {insz/1e9:.2f} GB -> {outsz/1e9:.2f} GB "
        f"({outsz/insz*100:.0f}% от источника)")
    if partial:
        log(">>   (частичный диапазон --from/--to: сабы/главы/вложения НЕ вмуксены)")
