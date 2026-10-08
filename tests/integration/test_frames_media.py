"""ALN-01..04, ANL-03: медиа-тест среднего тира на реальном ffmpeg без GPU и /dev/dri
(программный декод).

Синтетика генерируется в тесте (x265 для источников, SVT-AV1 для энкодов,
декод AV1 — libdav1d). Все фикстуры module-scope: один раз на модуль.
Нарезка open-GOP для RASL-фикстуры — реальный mkvmerge --split.
Сбой генерации (сборка ffmpeg без нужного кодера/фильтра) — skip с причиной;
любая проверка свойств фикстуры (теги, запас сдвига) — assert/fail: пороги
D-03 в тестах не ослабляются.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from enpipe.analysis import align, frames, metrics, pair, precheck
from enpipe.analysis.config import AnalysisError, AnalyzeConfig
from enpipe.analysis.model import FileAlignment, ALIGN_ALIGNED, ALIGN_SHIFT, ALIGN_UNDETERMINED, OFFSET_SCENES
from enpipe.encoding.scenes_io import read_scenes

W, H = 640, 360


def _has_encoders() -> bool:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return False
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    return "libx265" in out and "libsvtav1" in out


pytestmark = pytest.mark.skipif(
    not _has_encoders(), reason="нужны ffmpeg/ffprobe с libx265 и libsvtav1"
)

_X265_TAGS = (
    "bframes=4:keyint=48:open-gop=1:colorprim=bt2020:transfer=smpte2084:"
    "colormatrix=bt2020nc:range=limited:log-level=error"
)
_SVT_TAGS = (
    "color-primaries=9:transfer-characteristics=16:matrix-coefficients=9:color-range=0"
)


def _gen(cmd: Sequence[str], what: str) -> None:
    """Генерация фикстуры; сбой сборки ffmpeg — skip с хвостом stderr."""
    try:
        subprocess.run(list(cmd), check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        pytest.skip(f"фикстура {what} не сгенерирована этой сборкой ffmpeg: {tail}")


def _x265(src_args: List[str], dst: Path, what: str, vf: Optional[str] = None,
          extra: Sequence[str] = ()) -> None:
    cmd = ["ffmpeg", "-v", "error", "-y", *src_args]
    if vf:
        cmd += ["-vf", vf]
    cmd += [*extra, "-pix_fmt", "yuv420p10le", "-c:v", "libx265", "-preset", "ultrafast",
            "-x265-params", _X265_TAGS, str(dst)]
    _gen(cmd, what)


def _av1(src: Path, dst: Path, vf: Optional[str] = None, crf: int = 35) -> None:
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-pix_fmt", "yuv420p10le", "-c:v", "libsvtav1", "-preset", "12", "-crf", str(crf),
        "-svtav1-params", _SVT_TAGS,
        "-color_primaries", "bt2020", "-color_trc", "smpte2084",
        "-colorspace", "bt2020nc", "-color_range", "tv", str(dst),
    ]
    _gen(cmd, f"AV1 {dst.name}")


_LAVFI = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=4"]
_SHIFT_VF = "trim=start_frame=1,setpts=PTS-STARTPTS,tpad=stop=1:stop_mode=clone"


@pytest.fixture(scope="module")
def media(tmp_path_factory) -> Dict[str, Path]:
    d = tmp_path_factory.mktemp("frames_media")
    m: Dict[str, Path] = {k: d / f"{k}.mkv" for k in (
        "src_cfr", "src_st", "src_vfr", "src_av", "enc_ok", "enc_shift", "enc_part",
        "gray_src", "gray_enc",
    )}
    m["dir"] = d
    _x265(_LAVFI, m["src_cfr"], "src_cfr")
    _gen(["ffmpeg", "-v", "error", "-y", "-i", str(m["src_cfr"]), "-c", "copy",
          "-output_ts_offset", "2.5", str(m["src_st"])], "src_st")
    _x265(_LAVFI, m["src_vfr"], "src_vfr",
          vf="setpts='if(lt(N,48),N/24,2+(N-48)/12)/TB'", extra=["-fps_mode", "passthrough"])
    _gen(["ffmpeg", "-v", "error", "-y", "-itsoffset", "2.5", "-i", str(m["src_cfr"]),
          "-f", "lavfi", "-i", "sine=duration=6", "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "flac", str(m["src_av"])], "src_av")
    _av1(m["src_cfr"], m["enc_ok"])
    _av1(m["src_cfr"], m["enc_shift"], _SHIFT_VF)
    _av1(m["src_cfr"], m["enc_part"], "trim=start_frame=24:end_frame=72,setpts=PTS-STARTPTS")
    _x265(["-f", "lavfi", "-i", "color=c=gray:size=640x360:rate=24:duration=4"],
          m["gray_src"], "gray_src")
    _av1(m["gray_src"], m["gray_enc"])
    scenes = m["src_cfr"].with_name("src_cfr.mkv.scenes")
    scenes.write_text("".join(
        f"scene {i:4d} frames [{i * 24:8d}, {i * 24 + 24:8d}) {i:.3f} .. {i + 1:.3f}\n"
        for i in range(4)
    ))
    m["scenes"] = scenes
    return m


# --------------------------------------------------------------------------- #
# Хелперы
# --------------------------------------------------------------------------- #


def _real_check(src: Path, enc: Path, offset: int = 0,
                scenes: Optional[Sequence[Tuple[int, int]]] = None,
                cfg: Optional[AnalyzeConfig] = None) -> pair.PairCheck:
    """PairCheck по реальным файлам: probe, pts_table и precheck без подмен."""
    cfg = cfg or AnalyzeConfig()
    si, ei = frames.probe_stream(src), frames.probe_stream(enc)
    sp, ep = frames.pts_table(src), frames.pts_table(enc)
    verdict = precheck.check_pair(si, ei, sp, ep, offset, scenes, cfg)
    return pair.PairCheck(verdict=verdict, src_info=si, enc_info=ei,
                          src_pts=tuple(sp), enc_pts=tuple(ep), reasons=verdict.reasons,
                          # файловый вердикт принят выровненным: тест проверяет
                          # локальный вердикт кадра (D-14), а не агрегат
                          alignment=FileAlignment(verdict=ALIGN_ALIGNED, offset=offset))


def _framemd5(path: Path) -> List[str]:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-pix_fmt",
         "yuv420p10le", "-fps_mode", "passthrough", "-f", "framemd5", "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [ln.split(",")[-1].strip() for ln in out.splitlines() if ln and not ln.startswith("#")]


def _md5(planes) -> str:
    h = hashlib.md5()
    for p in planes:
        h.update(p.tobytes())
    return h.hexdigest()


def _shift_margins(src: Path, enc: Path, cfg: AnalyzeConfig) -> List[Tuple[int, float]]:
    """Запас точек: PSNR(d=+1) − max PSNR остальных d; (кадр, запас).

    Точки без d=+1 в окне (клон последнего кадра у конца файла) не
    измеряются: там сдвига по построению нет.
    """
    sp, ep = frames.pts_table(src), frames.pts_table(enc)
    out: List[Tuple[int, float]] = []
    for t in align.pick_points(len(ep), None, 0, cfg):
        f = t.enc_frame
        lo, hi = align.window_range(f, cfg.align_window, len(sp))
        ey = frames.grab_frames(enc, ep, f, 1, W, H)[0][0]
        sy = frames.grab_frames(src, sp, lo, hi - lo + 1, W, H)
        by = {lo + i - f: metrics.psnr(ey, p[0]) for i, p in enumerate(sy)}
        if 1 not in by:
            continue
        others = [v for d, v in by.items() if d != 1]
        out.append((f, by[1] - max(others)))
    return out


@pytest.fixture(scope="module")
def shift_pair(media):
    """(src, enc, вариант, запасы): основной crf 35, при нехватке запаса — шумный crf 20."""
    cfg = AnalyzeConfig()
    need = cfg.align_margin_db + 1.0
    tried: Dict[str, List[Tuple[int, float]]] = {}
    m = _shift_margins(media["src_cfr"], media["enc_shift"], cfg)
    tried["основной"] = m
    if len(m) >= 3 and min(v for _, v in m) >= need:
        return media["src_cfr"], media["enc_shift"], "основной", m
    d = media["dir"]
    src_n, enc_n = d / "src_noisy.mkv", d / "enc_shift_noisy.mkv"
    _x265(_LAVFI, src_n, "src_noisy", vf="noise=alls=12:allf=t+u")
    _av1(src_n, enc_n, _SHIFT_VF, crf=20)
    m = _shift_margins(src_n, enc_n, cfg)
    tried["запасной"] = m
    if len(m) >= 3 and min(v for _, v in m) >= need:
        return src_n, enc_n, "запасной", m
    pytest.fail(f"запаса фикстуры сдвига нет (нужно >= {need} дБ): {tried}")


# --------------------------------------------------------------------------- #
# Критерий 1: seek == последовательный декод
# --------------------------------------------------------------------------- #


def test_fixture_tags_match(media):
    a, b = frames.probe_stream(media["src_cfr"]), frames.probe_stream(media["enc_ok"])
    diff = [n for n in ("color_range", "color_space", "color_transfer", "color_primaries")
            if getattr(a, n) != getattr(b, n)]
    assert not diff, f"теги фикстур расходятся: {diff} ({a}, {b})"
    assert a.color_transfer == "smpte2084"


@pytest.mark.parametrize("name", ["src_cfr", "src_st", "src_vfr", "src_av", "enc_ok"])
def test_seek_matches_framemd5(media, name):
    """Кадр N через seek совпадает с framemd5 последовательного декода.

    framemd5 хеширует упакованные плоскости без stride-паддинга, поэтому
    md5(Y+U+V байт) == хеш строки framemd5 (проверено на закреплённом ffmpeg
    n9.0.2; при смене ffmpeg сверить заново).
    """
    f = media[name]
    ref = _framemd5(f)
    pts = frames.pts_table(f)
    assert len(pts) == len(ref)
    for n in (0, 1, 2, 13, 47, 48, 49, 95):
        got = _md5(frames.grab_frames(f, pts, n, 1, W, H)[0])
        assert got == ref[n], f"{name}: кадр {n}"


def test_window_matches_framemd5(media):
    f = media["src_vfr"]
    ref = _framemd5(f)
    pts = frames.pts_table(f)
    got = frames.grab_frames(f, pts, 45, 7, W, H)
    assert [_md5(p) for p in got] == ref[45:52]


# --------------------------------------------------------------------------- #
# Критерии 3, 4: вердикты
# --------------------------------------------------------------------------- #


def test_aligned_pair_ok(media, tmp_path):
    cfg = AnalyzeConfig()
    scenes = read_scenes(media["scenes"])
    chk = pair.check_pair_files(media["src_cfr"], media["enc_ok"], cfg,
                                scenes=scenes, cache_dir=tmp_path)
    assert chk.ok, chk.reasons
    assert chk.alignment.verdict == ALIGN_ALIGNED
    assert list(tmp_path.glob("*.pts.json"))
    again = pair.check_pair_files(media["src_cfr"], media["enc_ok"], cfg,
                                  scenes=scenes, cache_dir=tmp_path)
    assert again.ok


def test_shift_fixture_margin(shift_pair):
    _src, _enc, variant, margins = shift_pair
    print(f"вариант фикстуры сдвига: {variant}; запасы по точкам: {margins}")
    need = AnalyzeConfig().align_margin_db + 1.0
    assert min(v for _, v in margins) >= need, (variant, margins)


def test_shift_one_refused(shift_pair):
    src, enc, _variant, _m = shift_pair
    chk = pair.check_pair_files(src, enc, AnalyzeConfig())
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_SHIFT
    assert chk.alignment.shift == 1
    assert any("сдвиг +1" in r for r in chk.reasons)


def test_static_undetermined(media):
    chk = pair.check_pair_files(media["gray_src"], media["gray_enc"], AnalyzeConfig())
    assert not chk.ok
    assert chk.alignment.verdict == ALIGN_UNDETERMINED


def test_partial_without_offset_hint(media):
    scenes = read_scenes(media["scenes"])
    chk = pair.check_pair_files(media["src_cfr"], media["enc_part"], AnalyzeConfig(),
                                scenes=scenes)
    assert not chk.ok
    assert chk.alignment is None
    assert any("--offset 24 (сцены 1..2)" in r for r in chk.reasons)


def test_partial_with_offset_aligned(media):
    cfg = AnalyzeConfig()
    scenes = read_scenes(media["scenes"])
    src, enc = media["src_cfr"], media["enc_part"]
    chk = pair.check_pair_files(src, enc, cfg, offset=24, scenes=scenes)
    assert chk.ok, chk.reasons
    assert chk.verdict.offset_source == OFFSET_SCENES
    manual = pair.check_pair_files(src, enc, cfg, offset=24)
    assert manual.ok, manual.reasons
    assert any("сдвиг задан вручную" in n for n in manual.verdict.notes)
    assert not pair.check_pair_files(src, enc, cfg, offset=48, scenes=scenes).ok
    bad = pair.check_pair_files(src, enc, cfg, offset=30, scenes=scenes)
    assert any("не совпадает с началом" in r for r in bad.reasons)


# --------------------------------------------------------------------------- #
# Кадровый уровень и критерий 5
# --------------------------------------------------------------------------- #


def test_frame_pair_and_metrics_readonly(media):
    cfg = AnalyzeConfig()
    src, enc = media["src_cfr"], media["enc_ok"]
    chk = pair.check_pair_files(src, enc, cfg)
    assert chk.ok, chk.reasons
    fp, err = pair.grab_frame_pair(src, enc, chk, 10, cfg)
    assert err is None
    assert fp.alignment.verdict == ALIGN_ALIGNED
    assert not fp.src_planes[0].flags.writeable
    fm = metrics.analyze_frame(*fp.src_planes, *fp.enc_planes, cfg)
    assert fm.psnr_y > 0 and fm.psnr_y != float("inf")


def test_frame_pair_local_shift(shift_pair):
    src, enc, _variant, _m = shift_pair
    cfg = AnalyzeConfig()
    chk = _real_check(src, enc, offset=0, cfg=cfg)
    fp, err = pair.grab_frame_pair(src, enc, chk, 10, cfg)
    assert err is None
    assert fp.alignment.verdict == ALIGN_SHIFT and fp.alignment.shift == 1
    assert align.row_alignment(fp.alignment)[2]


def test_no_gpu_needed(media, monkeypatch, tmp_path):
    import enpipe.shared.proc as proc

    seen: List[List[str]] = []
    orig = proc.run

    def spy(cmd, *a, **kw):
        seen.append(list(cmd))
        return orig(cmd, *a, **kw)

    monkeypatch.setattr(proc, "run", spy)
    f = media["src_cfr"]
    frames.probe_stream(f)
    pts = frames.pts_table(f)
    frames.grab_frames(f, pts, 10, 1, W, H)
    assert seen
    for cmd in seen:
        joined = " ".join(cmd)
        for bad in ("-hwaccel", "qsv", "vaapi", "/dev/dri"):
            assert bad not in joined
        if shutil.which("nice"):
            assert cmd[:3] == ["nice", "-n", "10"]
    ff = [c for c in seen if "ffmpeg" in c]
    assert ff and all("-threads" in c and c[c.index("-threads") + 1] == "2" for c in ff)


# --------------------------------------------------------------------------- #
# WR-02: RASL после CRA в начале нарезки
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def rasl_cut(media) -> Tuple[Path, int]:
    """Нарезка open-GOP HEVC Main10 с CRA и RASL-кадрами в начале; (файл, lead).

    lead — число пакетов, которые декодер отбрасывает (RASL): индексы таблицы
    pts 0..lead-1 не декодируются.
    """
    if shutil.which("mkvmerge") is None:
        pytest.skip("нужен mkvmerge для нарезки open-GOP")
    d = media["dir"]
    r = subprocess.run(
        ["mkvmerge", "-q", "-o", str(d / "cut.mkv"), "--split", "timestamps:2s",
         str(media["src_cfr"])],
        capture_output=True, text=True,
    )
    # mkvmerge возвращает 1 при одних предупреждениях
    if r.returncode not in (0, 1):
        pytest.fail(f"mkvmerge код {r.returncode}: {(r.stdout + r.stderr)[-500:]}")
    cut = d / "cut-002.mkv"
    if not cut.exists():
        pytest.fail(f"нет cut-002.mkv; в каталоге: {sorted(x.name for x in d.iterdir())}")
    info = frames.probe_stream(cut)
    assert info.codec_name == "hevc" and info.pix_fmt == "yuv420p10le"
    lead = len(frames.pts_table(cut)) - len(_framemd5(cut))
    assert lead >= 1, "в нарезке нет недекодируемых RASL-кадров — фикстура не воспроизводит дефект"
    return cut, lead


def test_rasl_leading_frames_refused(rasl_cut):
    cut, lead = rasl_cut
    pts = frames.pts_table(cut)
    for n in range(lead):
        with pytest.raises(AnalysisError, match="pts"):
            frames.grab_frames(cut, pts, n, 1, W, H)


def test_rasl_decodable_frames_numbered(rasl_cut):
    cut, lead = rasl_cut
    pts = frames.pts_table(cut)
    ref = _framemd5(cut)
    for n in (lead, lead + 1, lead + 13, len(pts) - 1):
        assert _md5(frames.grab_frames(cut, pts, n, 1, W, H)[0]) == ref[n - lead], n
    win = frames.grab_frames(cut, pts, lead, 7, W, H)
    assert [_md5(f) for f in win] == ref[0:7]


def test_rasl_window_crossing_refused(rasl_cut):
    cut, lead = rasl_cut
    pts = frames.pts_table(cut)
    with pytest.raises(AnalysisError):
        frames.grab_frames(cut, pts, 0, lead + 2, W, H)


def test_rasl_pair_refused(rasl_cut):
    cut, _ = rasl_cut
    chk = pair.check_pair_files(cut, cut, AnalyzeConfig())
    assert not chk.ok
    assert any(r.startswith("точка 0:") and "pts" in r for r in chk.reasons), chk.reasons
