#!/usr/bin/env python3
"""UAT модуля analysis на реальной паре (источник + энкод enpipe), запускает оператор.

Зачем: на синтетике нельзя проверить то, что есть только на реальных данных:
  - A8: энкод qsvencc -> mkvmerge сохраняет четыре color-тега источника, иначе
    предпроверка пары отвергнет все реальные энкоды (таблица расхождения тегов
    здесь только диагностика, правила предпроверки не меняются);
  - отказ DV profile 5 первой причиной (--probe-only по одному файлу);
  - выбор DEFAULT_JOBS на ZFS-HDD: время извлечения точек при jobs 1/2/4;
  - время таблицы pts (холодно / из кэша) и пиковая память (ru_maxrss себя и
    дочерних процессов) на реальном разрешении.

Каждый шаг обёрнут: исключение печатает полный traceback и номер шага, остальные
шаги выполняются, чтобы оператор прислал один полный вывод. Файлы не меняются,
пишется только каталог кэша pts. Внешние программы вызываются только через
функции enpipe.analysis.

Пример:
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2,4
  uv run python scratch/analysis_pair_probe.py SRC.mp4 --probe-only
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from enpipe.analysis import frames, pair, precheck  # noqa: E402
from enpipe.analysis.config import AnalyzeConfig  # noqa: E402
from enpipe.analysis.sources import read_scenes_file  # noqa: E402

_TAGS = ("color_range", "color_space", "color_transfer", "color_primaries")
_FAILED: List[int] = []
_WINDOW = 7


def _mem() -> None:
    """ru_maxrss в Linux — КиБ; печатаем МБ, процесс и завершённые дочерние."""
    me = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    ch = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    print(f"  память: ru_maxrss сам {me:.0f} МБ, дочерние (максимум) {ch:.0f} МБ")


def _step(n: int, title: str, fn: Callable[[], Any]) -> Any:
    print(f"\n=== шаг {n}: {title}", flush=True)
    try:
        res = fn()
    except Exception:
        print(traceback.format_exc())
        print(f"шаг {n} не выполнен")
        _FAILED.append(n)
        res = None
    _mem()
    return res


def _skip(n: int, need: int) -> None:
    print(f"\n=== шаг {n}: пропущен: нет данных шага {need}")


def _print_info(label: str, i) -> None:
    print(
        f"  {label}: {i.name}\n"
        f"    codec={i.codec_name} {i.width}x{i.height} pix_fmt={i.pix_fmt} "
        f"fps={i.avg_frame_rate} start_time={i.start_time} field_order={i.field_order}\n"
        f"    color_range={i.color_range} color_space={i.color_space} "
        f"color_transfer={i.color_transfer} color_primaries={i.color_primaries}\n"
        f"    has_dovi={i.has_dovi} dv_profile={i.dv_profile}"
    )


def _step_probe(src: Path, enc: Optional[Path]) -> Dict[str, Any]:
    infos = {"источник": frames.probe_stream(src)}
    _print_info("источник", infos["источник"])
    if enc is not None:
        infos["энкод"] = frames.probe_stream(enc)
        _print_info("энкод", infos["энкод"])
        s, e = infos["источник"], infos["энкод"]
        print("  теги (диагностика A8): тег | источник | энкод | совпадает")
        diff = []
        for t in _TAGS:
            a, b = getattr(s, t), getattr(e, t)
            ok = a == b
            if not ok:
                diff.append(t)
            print(f"    {t} | {a} | {b} | {'да' if ok else 'НЕТ'}")
        print(f"  итог: расходятся: {', '.join(diff)}" if diff else "  итог: теги совпадают")
    return infos


def _timed_pts(label: str, path: Path, cache: Path) -> List[float]:
    t0 = time.monotonic()
    pts = frames.pts_table(path, cache)
    t1 = time.monotonic()
    pts2 = frames.pts_table(path, cache)
    t2 = time.monotonic()
    neg = sum(1 for p in pts if p < 0)
    print(
        f"  {label}: кадров {len(pts)}; первый вызов {t1 - t0:.2f} с, повторный "
        f"(кэш) {t2 - t1:.2f} с; совпадают: {pts == pts2}\n"
        f"    min(pts)={min(pts) if pts else None}, pts < 0: {neg}, "
        f"N/A: 0 (таблица построена)"
    )
    return pts


def _step_pts(src: Path, enc: Optional[Path], cache: Path) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for label, p in (("источник", src), ("энкод", enc)):
        if p is None:
            continue
        try:
            out[label] = _timed_pts(label, p, cache)
        except Exception as e:
            # N/A pts pts_table отвергает исключением — его текст и есть диагностика
            print(f"  {label}: таблица не построена: {e}")
            raise
    return out


def _step_precheck_one(infos: Dict[str, Any], pts: Optional[Dict[str, List[float]]]):
    info = infos["источник"]
    table = (pts or {}).get("источник", [])
    v = precheck.check_pair(info, info, table, table, None, None, AnalyzeConfig())
    print(f"  ok={v.ok}")
    for i, r in enumerate(v.reasons, 1):
        print(f"  причина {i}: {r}")
    for n in v.notes:
        print(f"  пометка: {n}")
    if not v.reasons:
        print("  причин нет")


def _step_check(src, enc, cfg, offset, scenes, cache, jobs) -> Any:
    chk = pair.check_pair_files(
        src, enc, cfg, offset=offset, scenes=scenes, cache_dir=cache, jobs=jobs
    )
    print(f"  ok: {chk.ok}")
    for r in chk.reasons:
        print(f"  причина: {r}")
    v = chk.verdict
    print(f"  offset={v.offset} источник offset={v.offset_source} vfr={v.vfr}")
    for n in v.notes:
        print(f"  пометка: {n}")
    a = chk.alignment
    if a is None:
        print("  выравнивание: не выполнялось (отказ предпроверки)")
        return chk
    print(f"  итог выравнивания: {a.verdict} (выровнено {a.n_aligned} из {len(a.points)}, "
          f"сдвиг {a.shift}, offset {a.offset})")
    print("  кадр энкода | вердикт | сдвиг | запас, дБ | сцена")
    for p in a.points:
        sh = f"{'≥' if p.shift_at_least else ''}{p.shift}" if p.shift is not None else "-"
        mg = f"{p.margin_db:.1f}" if p.margin_db is not None else "-"
        print(f"  {p.enc_frame} | {p.verdict} | {sh} | {mg} | {p.scene}"
              + (f" | {p.error}" if p.error else ""))
    return chk


def _grab_point(task: Tuple[Path, Path, List[float], List[float], int, int, int, int]):
    src, enc, sp, ep, f, off, w, h = task
    s0 = max(0, min(f + off - _WINDOW // 2, len(sp) - _WINDOW))
    frames.grab_frames(src, sp, s0, _WINDOW, w, h)
    frames.grab_frames(enc, ep, f, 1, w, h)


def _step_jobs(src, enc, infos, pts, offset, jobs_list, n_points) -> None:
    sp, ep = pts["источник"], pts["энкод"]
    info = infos["источник"]
    n = len(ep)
    step = max(1, n // n_points)
    runs = len(jobs_list)
    print("  подсказка: первый прогон после чтения других файлов ближе к «холодному» HDD")
    print("  jobs | всего, с | с на точку")
    for r, jobs in enumerate(jobs_list):
        shift = (r + 1) * step // (runs + 1)
        pts_idx = [min(n - 1, i * step + shift) for i in range(n_points)]
        tasks = [(src, enc, sp, ep, f, offset, info.width, info.height) for f in pts_idx]
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(_grab_point, tasks))
        dt = time.monotonic() - t0
        print(f"  {jobs} | {dt:.2f} | {dt / len(tasks):.2f}")
        _mem()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path, help="источник")
    ap.add_argument("enc", type=Path, nargs="?", help="энкод (не нужен при --probe-only)")
    ap.add_argument("--scenes", type=Path, help="файл сцен (по умолчанию <src>.scenes)")
    ap.add_argument("--offset", type=int, help="смещение кадров источника для частичного энкода")
    ap.add_argument("--cache", type=Path, default=Path("/tmp/enpipe-pts-cache"),
                    help="каталог кэша pts")
    ap.add_argument("--jobs", default="1,2,4", help="значения jobs через запятую")
    ap.add_argument("--points", type=int, default=10, help="точек на прогон замера jobs")
    ap.add_argument("--probe-only", action="store_true", help="только probe и предпроверка по src")
    args = ap.parse_args()
    if not args.probe_only and args.enc is None:
        ap.error("нужен enc (или --probe-only)")
    jobs_list = [int(x) for x in args.jobs.split(",") if x.strip()]
    cfg = AnalyzeConfig()

    enc = None if args.probe_only else args.enc
    infos = _step(1, "probe и теги", lambda: _step_probe(args.src, enc))
    pts = _step(2, "таблицы pts (холодно / из кэша)", lambda: _step_pts(args.src, enc, args.cache))

    if args.probe_only:
        if infos is None:
            _skip(3, 1)
        else:
            _step(3, "предпроверка по одному файлу (порядок причин)",
                  lambda: _step_precheck_one(infos, pts))
        return 1 if _FAILED else 0

    scenes_path = args.scenes
    if scenes_path is None and args.src.with_name(args.src.name + ".scenes").exists():
        scenes_path = args.src.with_name(args.src.name + ".scenes")
    scenes = None
    if scenes_path is not None:
        scenes = _step(3, f"чтение сцен {scenes_path}", lambda: read_scenes_file(scenes_path))
        print(f"  сцен: {len(scenes) if scenes else 0}")
    else:
        print("\n=== сцены не заданы (нет <src>.scenes и --scenes)")

    chk = _step(4, "check_pair_files: предпроверка и выравнивание",
                lambda: _step_check(args.src, args.enc, cfg, args.offset, scenes,
                                    args.cache, jobs_list[0]))
    if infos is None or pts is None or len(pts) < 2:
        _skip(5, 1 if infos is None else 2)
    else:
        offset = chk.verdict.offset if chk is not None else (args.offset or 0)
        _step(5, "замер jobs", lambda: _step_jobs(
            args.src, args.enc, infos, pts, offset, jobs_list, args.points))
    print(f"\nитог: упавших шагов {len(_FAILED)}" + (f" ({_FAILED})" if _FAILED else ""))
    return 1 if _FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
