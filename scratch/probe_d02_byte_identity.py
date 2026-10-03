#!/usr/bin/env python3
"""Одноразовый аппаратный пробник побайтного детерминизма (стоп-гейт D-02).

ЗАЧЕМ. Дизайн фазы по ужесточению замка (D-01) опирается на побайтный
критерий: чистая конкурентная сессия qsvencc >= r4634 обязана бит в бит
совпадать с изолированным эталоном того же argv. Если это неверно, критерий
негоден, и переписывать замок под него нельзя. Поэтому пробник запускается
ДО любой правки замка и сообщает вердикт `D-02 PASS` / `D-02 FAIL`.

ПОЧЕМУ ПОВЕРХ НЕИЗМЕННОГО ХАРНЕССА. Харнесс tests/integration/_concurrency_harness.py
(run_session, HANDOFF_SCENES, _fixture_hdr_flags, FIXTURE) подключается через
sys.path и не меняется: пробник измеряет предпосылку, а не меняет то, что
потом будет проверяться. Argv строится продакшен-функцией chunk_command, без
подмен (metrics=False / metrics=True - единственное различие вариантов).

ПОЧЕМУ SHA256 БЛОКАМИ. Эталон сцены 1129 весит сотни МБ; читать его целиком
в память незачем, хеш считается блоками по 1 МиБ.

КЛАССИФИКАЦИЯ. Маркеры сбоя метрик ищутся в ПОЛНОМ stderr-файле сессии (а не
в 500-символьном хвосте из run_session). Сама классификация вынесена в чистую
функцию _classify и проверяется режимом --self-test без GPU, чтобы ошибка
пробника не дала ложный вердикт D-02.

Без /dev/dri/renderD128, qsvencc или фикстуры печатает SKIP и выходит 0.
Код возврата: 0 - PASS (или SKIP / self-test), 1 - FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
try:
    import _concurrency_harness as harness  # noqa: E402
except ImportError as exc:
    raise SystemExit(
        f"не найден tests/integration/_concurrency_harness.py ({exc}); "
        f"пробник запускать из корня чекаута"
    )

from enpipe.encoding.chunk import chunk_command, count_frames  # noqa: E402

_METRICS_FAILURE_MARKERS: Tuple[str, ...] = (
    "VIDEOMETRIC:",
    "allocVA",
    "Decoded frame count does not match",
)
CLASSES: Tuple[str, ...] = (
    "byte_identical", "byte_mismatch", "SESSION_FAILED", "METRICS_FAILED", "frames_bad",
)
REF_ATTEMPTS_METRICS = 5


# --------------------------------------------------------------------------- #
# Чистые функции (проверяются --self-test без GPU)
# --------------------------------------------------------------------------- #


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _classify(
    ok: bool,
    stderr_text: str,
    metrics: bool,
    same: Optional[bool],
    frames_ok: Optional[bool],
) -> str:
    """Класс одной сессии. Расхождение байтов главнее расхождения кадров;
    сбой старта никогда не засчитывается как совпадение."""
    if not ok:
        clean = harness.strip_ansi(stderr_text)
        if metrics and any(m in clean for m in _METRICS_FAILURE_MARKERS):
            return "METRICS_FAILED"
        return "SESSION_FAILED"
    if same is False:
        return "byte_mismatch"
    if frames_ok is False:
        return "frames_bad"
    return "byte_identical"


def _self_test() -> int:
    ansi_vm = "\x1b[31mVIDEOMETRIC: error\x1b[0m"
    assert _classify(False, ansi_vm, True, None, None) == "METRICS_FAILED"
    assert _classify(False, ansi_vm, False, None, None) == "SESSION_FAILED"
    assert _classify(False, "rc=1: avqsv: failed to seek", True, None, None) == "SESSION_FAILED"
    assert _classify(True, "", False, False, False) == "byte_mismatch"
    assert _classify(True, "", False, True, False) == "frames_bad"
    assert _classify(True, "", False, True, True) == "byte_identical"
    tmp = Path(tempfile.mkdtemp(prefix="probe_d02_selftest_"))
    try:
        a, b, c = tmp / "a", tmp / "b", tmp / "c"
        a.write_bytes(b"x" * 3_000_000)
        b.write_bytes(b"x" * 3_000_000)
        c.write_bytes(b"x" * 2_999_999 + b"y")
        assert _sha256(a) == _sha256(b)
        assert _sha256(a) != _sha256(c)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("SELF-TEST OK")
    return 0


# --------------------------------------------------------------------------- #
# Аппаратная часть
# --------------------------------------------------------------------------- #


def _cmd(scene: "harness.HandoffScene", out: Path, metrics: bool) -> List[str]:
    return chunk_command(
        harness.FIXTURE, scene.seek, scene.trim, out,
        hdr_flags=list(harness._fixture_hdr_flags()), metrics=metrics,
    )


def _session(
    scene: "harness.HandoffScene", out: Path, log: Path, metrics: bool
) -> Tuple[bool, Optional[str]]:
    return harness.run_session(_cmd(scene, out, metrics), out, log)


def _log_text(log: Path) -> str:
    return log.read_text(errors="replace") if log.is_file() else ""


def _uname_r() -> str:
    return subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()


def _opencl_icd_version() -> str:
    proc = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", "intel-opencl-icd"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "not installed"


def _build_ref(
    scene: "harness.HandoffScene", workdir: Path, tag: str, metrics: bool
) -> Optional[Path]:
    """Один изолированный эталон; с метриками до 5 попыток (rc=0 и кадры)."""
    attempts = REF_ATTEMPTS_METRICS if metrics else 1
    for attempt in range(attempts):
        out = workdir / f"ref_{tag}_{scene.scene}_m{int(metrics)}.obu"
        log = workdir / f"ref_{tag}_{scene.scene}_m{int(metrics)}.log"
        out.unlink(missing_ok=True)
        ok, _err = _session(scene, out, log, metrics)
        if ok and count_frames(out) == scene.frames:
            return out
    return None


def main(argv: Optional[List[str]] = None) -> int:  # noqa: C901 -- линейный скрипт-доказательство
    ap = argparse.ArgumentParser(description="Пробник побайтного детерминизма D-02")
    ap.add_argument("--metrics", choices=("off", "on", "both"), default="both")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "scratch")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not (Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc")):
        print("SKIP: нет Arc-железа (/dev/dri/renderD128 или qsvencc)")
        return 0
    if not harness.fixture_available():
        print(f"SKIP: фикстура не найдена: {harness.FIXTURE}")
        return 0

    variants = {"off": [False], "on": [True], "both": [False, True]}[args.metrics]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir: Path = args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    def emit(line: str = "") -> None:
        print(line, flush=True)
        lines.append(line)

    emit("=== probe D-02: побайтный детерминизм ===")
    emit(f"UTC: {ts}")
    emit(f"uname -r: {_uname_r()}")
    emit(f"qsvencc: {harness.qsvencc_version_line()}")
    emit(f"intel-opencl-icd: {_opencl_icd_version()}")
    emit(f"варианты metrics: {variants}, итераций: {args.iters}")
    emit("")

    workdir = Path(tempfile.mkdtemp(prefix="probe_d02_"))
    scenes = harness.HANDOFF_SCENES
    passed = True
    # (metrics) -> scene -> class -> count
    tally: Dict[bool, Dict[int, Dict[str, int]]] = {}
    ref_sha: Dict[Tuple[bool, int], str] = {}
    ref_pairs: Dict[Tuple[bool, int], Optional[bool]] = {}
    metrics_failed_total = 0
    sessions_total = 0
    mismatch_seq = 0

    try:
        for metrics in variants:
            emit(f"--- вариант metrics={'on' if metrics else 'off'} ---")
            tally[metrics] = {s.scene: {c: 0 for c in CLASSES} for s in scenes}
            refs: Dict[int, Path] = {}
            for scene in scenes:
                ra = _build_ref(scene, workdir, "a", metrics)
                rb = _build_ref(scene, workdir, "b", metrics)
                if ra is None or rb is None:
                    emit(f"scene {scene.scene}: эталон не построен (metrics={metrics})")
                    ref_pairs[(metrics, scene.scene)] = None
                    if not metrics:
                        passed = False
                    continue
                sa, sb = _sha256(ra), _sha256(rb)
                ref_sha[(metrics, scene.scene)] = sa
                ref_pairs[(metrics, scene.scene)] = sa == sb
                refs[scene.scene] = ra
                emit(f"scene {scene.scene}: ref_a sha256={sa}")
                emit(f"scene {scene.scene}: ref_b sha256={sb}  ref_a == ref_b: {sa == sb}")
                if sa != sb:
                    passed = False

            for it in range(args.iters):
                outs = {
                    s.scene: (workdir / f"it{it}_m{int(metrics)}_{s.scene}.obu",
                              workdir / f"it{it}_m{int(metrics)}_{s.scene}.log")
                    for s in scenes
                }
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futs = {
                        s.scene: pool.submit(_session, s, outs[s.scene][0], outs[s.scene][1], metrics)
                        for s in scenes
                    }
                    results = {k: f.result() for k, f in futs.items()}
                for scene in scenes:
                    out, log = outs[scene.scene]
                    ok, _err = results[scene.scene]
                    same: Optional[bool] = None
                    frames_ok: Optional[bool] = None
                    if ok:
                        ref = refs.get(scene.scene)
                        same = (_sha256(out) == ref_sha[(metrics, scene.scene)]) if ref else None
                        frames_ok = count_frames(out) == scene.frames
                    cls = _classify(ok, _log_text(log), metrics, same, frames_ok)
                    tally[metrics][scene.scene][cls] += 1
                    sessions_total += 1
                    if cls == "METRICS_FAILED":
                        metrics_failed_total += 1
                    if cls == "byte_mismatch":
                        mismatch_seq += 1
                        pre = f"probe_d02_{ts}_mismatch_{mismatch_seq}_scene{scene.scene}_m{int(metrics)}"
                        shutil.copyfile(out, evidence_dir / f"{pre}.test.obu")
                        shutil.copyfile(refs[scene.scene], evidence_dir / f"{pre}.ref.obu")
                        shutil.copyfile(log, evidence_dir / f"{pre}.verbose.log")
                    emit(f"iter {it} scene {scene.scene} metrics={int(metrics)}: {cls}")
            emit("")

        # D-05: эталон metrics on == эталон metrics off
        if len(variants) == 2:
            emit("--- D-05 (предварительно) ---")
            for scene in scenes:
                a = ref_sha.get((False, scene.scene))
                b = ref_sha.get((True, scene.scene))
                eq = (a == b) if (a and b) else None
                emit(f"scene {scene.scene}: ref metrics=off == ref metrics=on: {eq}")
            emit("")

        emit("--- итоговая таблица (вариант x сцена) ---")
        emit("variant scene | ok | " + " | ".join(CLASSES))
        for metrics in variants:
            for scene in scenes:
                t = tally[metrics][scene.scene]
                ok_n = t["byte_identical"] + t["byte_mismatch"] + t["frames_bad"]
                emit(
                    f"metrics={'on ' if metrics else 'off'} {scene.scene:>4} | {ok_n} | "
                    + " | ".join(str(t[c]) for c in CLASSES)
                )
                if t["byte_mismatch"] or t["frames_bad"]:
                    passed = False
                if not metrics and t["SESSION_FAILED"]:
                    passed = False
        on_total = sum(sum(t.values()) for t in tally.get(True, {}).values())
        if True in variants:
            emit(f"METRICS_FAILED: {metrics_failed_total} из {on_total} конкурентных сессий с метриками")
        emit("")
        emit("D-02 PASS" if passed else "D-02 FAIL")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    log_path = evidence_dir / f"probe_d02_{ts}.log"
    log_path.write_text("\n".join(lines) + "\n")
    print(f"лог записан: {log_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
