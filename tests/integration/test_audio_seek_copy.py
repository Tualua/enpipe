"""Медиа-тест точности copy-аудиодорожек в частичном режиме (`--from/--to`).

Ловит дефект input-seek для `-c copy`: `-ss` перед `-i` в mkv прыгает к
точке Cues (keyframe видео <= ss), а при stream copy пакеты от неё до ss
сохраняются, и муксер сдвигает их к нулю. Выход получался рассинхронизован
с видео (на 28YL a:4 — на ~0.7 с, на синтетике с редкими keyframe — на 10 с)
и длиннее dur.

Критерий приёмки: первые 4 пакета выхода побайтно (MD5) совпадают с 4
подряд идущими пакетами источника, первый из которых лежит не дальше
длительности одного пакета от ss, а длительность выхода равна dur с
точностью до 2 пакетов.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

from enpipe.encoding.audio import _track_codec_args, encode_audio

SRC_28YL = os.environ.get(
    "ENPIPE_TEST_28YL",
    "/data/downloads/28.Years.Later.2025.Hybrid.2160p.UHD.BDRemux.HDR10+.DV."
    "HEVC-Нечипорук.mkv",
)

# длительность пакета, если ffprobe не дал duration_time и соседей нет
_FALLBACK_DUR = {"eac3": 0.032, "truehd": 0.00083 + 0.001, "flac": 0.096}


# TrueHD декодируется только с major sync (keyframe, раз в 8 access unit
# ~6.7 мс): ffmpeg при stream copy начинает с первого keyframe >= ss и
# отбрасывает недекодируемые пакеты до него (на 28YL a:15: ss=600.000,
# первый keyframe 600.006). Допуск начала — один период major sync.
_START_LAG = {"truehd": 8 * 0.00083 + 0.002}


def _packets(path: Path, spec: str, read_intervals: Optional[str] = None,
             data_hash: bool = False, codec: str = "") -> List[dict]:
    """Пакеты дорожки (spec — `a:N`) с float pts/duration; при отсутствии
    или `N/A` duration_time длительность берётся как дельта pts до
    следующего пакета (для последнего — до предыдущего, иначе константа
    по кодеку)."""
    entries = "packet=pts_time,duration_time" + (",data_hash" if data_hash else "")
    cmd = ["ffprobe", "-v", "error", "-select_streams", spec,
           "-show_entries", entries]
    if data_hash:
        cmd += ["-show_data_hash", "MD5"]
    if read_intervals:
        cmd += ["-read_intervals", read_intervals]
    cmd += ["-of", "json", str(path)]
    raw = json.loads(subprocess.run(cmd, capture_output=True, text=True,
                                    check=True).stdout).get("packets", [])
    pk = [{"pts": float(p["pts_time"]), "hash": p.get("data_hash"),
           "dur": (float(p["duration_time"])
                   if p.get("duration_time") not in (None, "N/A") else None)}
          for p in raw if p.get("pts_time") not in (None, "N/A")]
    for i, p in enumerate(pk):
        if p["dur"] is None:
            if i + 1 < len(pk):
                p["dur"] = pk[i + 1]["pts"] - p["pts"]
            elif i > 0:
                p["dur"] = pk[i - 1]["dur"]
            else:
                p["dur"] = _FALLBACK_DUR.get(codec, 0.032)
    return pk


def _assert_copy_aligned(src: Path, out: Path, a_idx: int, ss: float,
                         dur: float, codec: str = "") -> dict:
    """Проверка выходной дорожки a:a_idx против одноимённой дорожки источника.
    Возвращает фактические величины для отчёта."""
    spec = f"a:{a_idx}"
    window = _packets(src, spec, f"{max(0.0, ss - 5):.3f}%{ss + 5:.3f}",
                      data_hash=True, codec=codec)
    head = _packets(out, spec, "%+#4", data_hash=True, codec=codec)
    assert len(head) == 4, f"{spec}: в выходе {len(head)} пакетов в голове"
    want = [p["hash"] for p in head]
    k = next((i for i in range(len(window) - 3)
              if [p["hash"] for p in window[i:i + 4]] == want), None)
    assert k is not None, (
        f"{spec}: первые 4 пакета выхода (pts {[p['pts'] for p in head]}) не "
        f"найдены в источнике в окне {ss - 5}..{ss + 5}")
    first = window[k]
    pkt = max(first["dur"], _START_LAG.get(codec, 0.0))
    assert first["pts"] >= ss - pkt - 0.001, (
        f"{spec}: выход начинается с пакета источника pts={first['pts']:.3f}, "
        f"ss={ss} (начало раньше ss)")
    assert abs(first["pts"] - ss) <= pkt + 0.001, (
        f"{spec}: первый пакет источника pts={first['pts']:.3f}, ss={ss}, "
        f"длительность пакета {pkt:.4f}")
    allp = _packets(out, spec, codec=codec)
    span = allp[-1]["pts"] + allp[-1]["dur"] - allp[0]["pts"]
    assert abs(span - dur) <= 2 * pkt + 0.002, (
        f"{spec}: длительность выхода {span:.3f} с, ожидалось {dur} "
        f"(пакет {pkt:.4f})")
    return {"first_pts": first["pts"], "span": span, "pkt": pkt}


def test_synthetic_flac_copy_partial(tmp_path, monkeypatch):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("нужны ffmpeg и ffprobe в PATH")
    monkeypatch.delenv("AUDIO_COPY", raising=False)
    src = tmp_path / "src.mkv"
    # keyframe раз в 10 с: точка Cues заведомо далеко от ss
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-t", "40", "-c:v", "mpeg4", "-g", "250", "-c:a", "flac", str(src)],
        check=True)
    out = tmp_path / "audio.mka"
    assert encode_audio(src, out, ss=17.3, dur=8.0) == (True, None)
    _assert_copy_aligned(src, out, 0, 17.3, 8.0, codec="flac")


@pytest.mark.hardware
def test_28yl_copy_tracks_partial(tmp_path, monkeypatch):
    src = Path(SRC_28YL)
    if not src.exists():
        pytest.skip(f"нет файла {src}")
    monkeypatch.delenv("AUDIO_COPY", raising=False)
    out = tmp_path / "audio.mka"
    assert encode_audio(src, out, ss=600.0, dur=60.0) == (True, None)
    # индекс аудио-относительный: enumerate по `-select_streams a`,
    # а не stream["index"] (это глобальный индекс потока)
    streams = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index,codec_name,profile,channels,channel_layout",
         "-of", "json", str(src)],
        capture_output=True, text=True, check=True).stdout)["streams"]
    copied = [(i, st) for i, st in enumerate(streams)
              if _track_codec_args(st, False) == ["-c:a", "copy"]
              and st.get("codec_name") in ("eac3", "truehd")]
    codecs = {i: st["codec_name"] for i, st in copied}
    assert codecs.get(4) == "eac3", f"a:4 не E-AC3 copy: {codecs}"
    assert "truehd" in codecs.values(), f"нет TrueHD Atmos copy: {codecs}"
    for i, st in copied:
        r = _assert_copy_aligned(src, out, i, 600.0, 60.0,
                                 codec=st["codec_name"])
        print(f"a:{i} {st['codec_name']}: first_pts={r['first_pts']:.4f} "
              f"span={r['span']:.4f} pkt={r['pkt']:.5f}")
