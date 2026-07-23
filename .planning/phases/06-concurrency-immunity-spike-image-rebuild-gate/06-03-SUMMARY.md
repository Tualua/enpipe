---
phase: 06-concurrency-immunity-spike-image-rebuild-gate
plan: 03
subsystem: testing
tags: [concurrency, corruption-gate, qsv, av1, psnr, hardware-gated-tests, gate-evidence, D-09, D-12]
dependency-graph:
  requires:
    - phase: 06-01
      provides: "hard-asserted ENV-01 environment (ffmpeg-8.1/ffprobe-8.1 + av1_qsv + av1_metadata/dovi_rpu BSFs)"
    - phase: 06-02
      provides: "the COR-01 harness (_concurrency_harness.py), hardware-gated pytest (test_concurrency_immunity.py), and one-time stress-matrix script (gate_stress_matrix.py) exercised here"
  provides:
    - "D-09 durable gate evidence: ffmpeg av1_qsv proven IMMUNE to cross-process per-frame corruption at JOBS 3/5/8 (320 sessions, 0 corrupt, 0 failed starts); qsvencc control corrupts (96 frames) — v1.2 migration premise VALID"
    - "Locked HW-decode triad leg: [h264_qsv regex confirmed against a live -v verbose capture; UNVERIFIED comment removed; 10-bit leg moved from log-grep to output .obu ffprobe probe"
    - "D-12 tiered-pivot verdict = PROCEED (no hard-pivot, no JOBS cap — ffmpeg clean through JOBS=8)"
  affects:
    - "Phase 7 (BK-02 backends/ seam) — cleared to proceed at full JOBS; the ffmpeg av1_qsv encode path is corruption-immune under concurrency"
    - "Whole v1.2 milestone — the gate this milestone is premised on is answered PASS"
tech-stack:
  added: []
  patterns:
    - "captured-then-locked marker: confirm a log-assertion regex against a real HW-vs-fully-specified-SW -v verbose diff before trusting it (anti-false-clean), not an assumed string"
    - "probe the output, not the log, when the pipeline is opaque: QSV decode surfaces don't print pix_fmt in -v verbose, so the 10-bit triad leg reads the output .obu's ffprobe pix_fmt instead of grepping the encoder log"
key-files:
  created: []
  modified:
    - tests/integration/_concurrency_harness.py
    - tests/integration/test_concurrency_immunity.py
    - scratch/gate_stress_matrix.py
    - .planning/debug/scene-chunk-frame-mismatch.md
decisions:
  - "HW-decode triad regex `\\[h264_qsv\\b` CONFIRMED against a live ffmpeg-8.1 -v verbose HW capture and demonstrably absent from a fully-specified forced-SW log; UNVERIFIED comment removed (closes RESEARCH Open Q1)"
  - "10-bit triad leg moved from log-grep to an ffprobe pix_fmt probe of the output .obu — QSV decode uses opaque surfaces and never prints pix_fmt in -v verbose, so a log-grep leg was unprovable; probing the encoded output is the sound equivalent (commit 0c89616)"
  - "D-12 tiered-pivot verdict = PROCEED: ffmpeg av1_qsv 0 corrupt at ALL levels (3/5/8) with every session started+succeeded — not a hard-pivot and not even a JOBS cap"
  - "Gate evidence captured on a side-loaded ffmpeg 8.1 (/opt/ffmpeg-8.1), NOT a canonical rebuilt devcontainer image — environment (kernel/driver/iHD) identical, only the ffmpeg binary delivery differed; same result expected on a clean rebuild (noted in the D-09 entry)"
requirements-completed: [COR-01, ENV-01]
metrics:
  duration_minutes: 90
  completed: 2026-07-23
---

# Phase 6 Plan 3: ffmpeg av1_qsv Concurrency-Immunity Gate Proof (D-09) Summary

**Proved on real Arc A380 hardware that ffmpeg `av1_qsv` is IMMUNE to cross-process per-frame corruption under concurrent JOBS (320 sessions, 0 corrupt frames at JOBS 3/5/8) while qsvencc corrupts in the identical harness (96 frames) — D-12 verdict PROCEED, the v1.2 migration premise is VALID, D-09 evidence recorded.**

## Performance

- **Duration:** ~90 min (incl. ~45–60 min stress matrix wall time on A380)
- **Completed:** 2026-07-23
- **Tasks:** 3 (2 human-verify checkpoints + 1 auto)
- **Files modified:** 4

## Accomplishments

- **SC#2/SC#3/SC#4 all TRUE on hardware.** ffmpeg `av1_qsv` immune at production JOBS=3 and stress JOBS 5/8; corruption triad asserted present (no silent SW-decode fallback); qsvencc control corrupts in the same harness (non-vacuous).
- **Closed RESEARCH Open Q1:** locked the HW-decode triad-leg regex `\[h264_qsv\b` against a live `-v verbose` capture (present in HW, absent in fully-specified forced-SW) and removed the UNVERIFIED comment.
- **Fixed an unprovable triad leg:** moved the 10-bit leg from a `-v verbose` log-grep (QSV surfaces are opaque, never print pix_fmt) to an ffprobe pix_fmt probe of the output `.obu`.
- **Ran the one-time stress matrix** (JOBS 3/5/8 × 20 iters × both backends, full-file per-frame PSNR sweep) and applied the **D-12 tiered verdict = PROCEED**.
- **Recorded the D-09 durable evidence** as a timestamped Russian entry in `scene-chunk-frame-mismatch.md`, mirrored verbatim below.

## Task Commits

1. **Task 1: Confirm/lock HW-decode triad regex + run committed pytest on hardware** — `0c89616` (fix(06-03): lock triad HW-decode regex + move P010 leg to output probe). Human-verify checkpoint; pytest ran green on hardware (`2 passed`).
2. **Task 2: One-time heavy stress matrix (JOBS 3/5/8 × ≥20 iters × 2 backends) + D-12 verdict** — human-verify checkpoint; evidence in the D-09 entry below (throwaway `gate_stress_matrix_<timestamp>.log` is `.gitignore`d by design — the SUMMARY/debug-doc append IS the durable record).
3. **Task 3: Record D-09 gate evidence** — `ecefbcd` (docs(06): record D-09 gate evidence — ffmpeg av1_qsv immunity PASS).

## Files Created/Modified

- `tests/integration/_concurrency_harness.py` — locked HW-decode regex; 10-bit leg moved to output-`.obu` ffprobe probe; silent-fallback guard confirmed present.
- `tests/integration/test_concurrency_immunity.py` — adjusted alongside the harness change.
- `scratch/gate_stress_matrix.py` — adjusted alongside the harness change.
- `.planning/debug/scene-chunk-frame-mismatch.md` — appended the timestamped `## ФАЗА 6 (GATE)` D-09 evidence entry (existing convention, prior entries untouched).

## D-09 Gate Evidence (verbatim — mirrors scene-chunk-frame-mismatch.md)

## ФАЗА 6 (GATE): ПРУВ ИММУННОСТИ ffmpeg av1_qsv 2026-07-23 — PASS (премиса v1.2 валидна)

**Вердикт:** ffmpeg `av1_qsv` **иммунен** к межпроцессной покадровой порче под конкурентными
`JOBS` на этом ядре/драйвере; qsvencc в ТОМ ЖЕ харнессе корраптит (контроль сработал →
регресс-тест non-vacuous). По D-12 это **PROCEED** — не hard-pivot и даже не потолок JOBS
(ffmpeg чист вплоть до JOBS=8).

**Среда (side-load-прогон, НЕ канонический ребилд образа):**
- `uname -r`: **6.19.14-200.fc43.x86_64** (хостовое ядро Fedora 43 через контейнер)
- iHD driver: **26.2.2**, VA-API **1.23** (libva 2.23.0), Arc A380 (`/dev/dri/renderD128`)
- i915/Xe: из контейнера не определяется (нет доступа к debugfs)
- ffmpeg **8.1** (BtbN static, n8.1.2-30-g45f1910444) — **side-load'нут** в текущий Ubuntu-24.04
  контейнер (`/opt/ffmpeg-8.1`), НЕ пересобранный образ. Системный ffmpeg 6.1.1 не тронут.
- qsvencc 8.22 (r4385), фикстура `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv`, сцены 923/928/1129.

**Стресс-матрица (D-10/D-11: JOBS 3/5/8 × 20 итераций × оба бэкенда, полнофайловый покадровый PSNR-свип, порог <30 dB):**

| JOBS | ffmpeg av1_qsv | qsvencc (контроль) |
|------|----------------|--------------------|
| 3 | **60 сессий, 0 порченых кадров, 0 SESSION_FAILED** | 60, **14 порченых** |
| 5 | **100 сессий, 0 порченых, 0 SESSION_FAILED** | 100, **31 порченых** |
| 8 | **160 сессий, 0 порченых, 0 SESSION_FAILED** | 160, **51 порченых** |
| **Σ** | **320 сессий, 0 порченых, 0 сорванных стартов** | 320 сессий, **96 порченых** |

- Триада (HW-декод `[h264_qsv` + 10-битный выход `yuv420p10le` + `GopRefDist:6`/`BRefType:pyramid`)
  **INTACT** на каждом из 3 уровней (anti-false-clean, SC#3) — silent SW-fallback исключён.
- PSNR-сигнатура порчи прежняя: порченый кадр ≈ **15.74 dB** vs чистый ≈ 41.5 dB (часто бит-идентичен);
  порог детекции 30 dB — глубоко в зазоре.
- qsvencc-порча РАСТЁТ с конкурентностью (14→31→51) — триггер (конкурентные 10-битные reference-сюрфейсы)
  масштабируется, как и в исходном расследовании выше.

**Committed COR-01 pytest (`tests/integration/test_concurrency_immunity.py`, IMMUNITY_ITERS=8, JOBS=3):**
`2 passed` на железе (ffmpeg 0 порчи + триада цела; qsvencc-контроль корраптит >0).

**Побочно закрыто на железе:**
- RESEARCH Open Q1: HW-декод регэксп `\[h264_qsv\b` **подтверждён** против живого `-v verbose` лога;
  10-битная нога триады перенесена с грепа лога (QSV не печатает pix_fmt — непрозрачные сюрфейсы)
  на пробу ВЫХОДНОГО `.obu` (ffprobe pix_fmt) — коммит `0c89616`.
- ENV-01 self-check: устранён флаки-провал (`pipefail`+`grep -q` гонка → SIGPIPE) — коммит `a515137`.

**Оговорка:** прогон на side-load'нутом ffmpeg 8.1, НЕ на каноническом пересобранном образе.
Для формального закрытия SC#1/D-09 остаётся ребилд devcontainer и повтор self-check + матрицы на
чистом образе; результат при этом ожидается тот же (среда/ядро/драйвер идентичны — менялся только
способ доставки бинаря ffmpeg).

## Decisions Made

- **HW-decode regex confirmed-then-locked** against a real HW-vs-fully-specified-SW `-v verbose` diff (not an assumed string) — closes RESEARCH Open Q1.
- **10-bit leg probes the output, not the log** — QSV decode surfaces are opaque and never print pix_fmt in `-v verbose`, so the leg reads the output `.obu`'s ffprobe pix_fmt.
- **D-12 verdict = PROCEED** — ffmpeg 0 corrupt at all three JOBS levels with every session started+succeeded; no pivot, no cap.

## Deviations from Plan

**1. [Discretionary — sound-equivalent leg swap] 10-bit triad leg moved from log-grep to output-`.obu` probe**
- **Found during:** Task 1, locking the triad against the real `-v verbose` capture.
- **Issue:** QSV decode uses opaque hardware surfaces; ffmpeg-8.1 `-v verbose` does not print a `yuv420p10le`/`p010le` pix_fmt line for the QSV-decoded frames, so a log-grep leg for 10-bit was unprovable.
- **Fix:** Probe the encoded output `.obu` with ffprobe for its pix_fmt instead — a sound equivalent that directly verifies the 10-bit path.
- **Committed in:** `0c89616` (fix(06-03)).

**2. [Caveat — evidence on side-loaded ffmpeg, not canonical rebuild]**
- The gate ran on a **side-loaded** ffmpeg 8.1 (`/opt/ffmpeg-8.1`), not a from-scratch rebuilt devcontainer image. Kernel/driver/iHD/hardware identical; only the ffmpeg binary delivery differed. Verdict is PASS; formal closure on a canonical rebuild is expected to reproduce it (noted in the D-09 entry). Accepted by operator decision at phase closeout.

## Issues Encountered

- The 10-bit triad leg was unprovable via log-grep (resolved via the output-probe swap, see Deviations). qsvencc control corruption was confirmed non-vacuous (96 frames total across the matrix; IMMUNITY_ITERS=8 for the committed pytest per the ≥8-iter guard against a false-clean control).

## Closeout Note

This SUMMARY was reconstructed at phase closeout: the prior execution session committed all code (`0c89616`) and the D-09 evidence (`ecefbcd`) and ran both hardware checkpoints, but terminated before writing this file. All commits, the recorded D-09 evidence, and the pytest/matrix results were verified present against git and the debug doc before writing. No hardware tests were re-run.

## Next Phase Readiness

- **The milestone gate is answered PASS.** ffmpeg `av1_qsv` is corruption-immune under concurrency at full JOBS — Phase 7 (BK-02 `backends/` seam) is cleared to proceed at full JOBS with the ffmpeg encode path.
- **Residual (documented, non-blocking):** formal SC#1/D-09 closure on a canonical rebuilt devcontainer image (vs the side-loaded ffmpeg 8.1) remains available if stricter provenance is later required; the result is expected to be identical.

---
*Phase: 06-concurrency-immunity-spike-image-rebuild-gate*
*Completed: 2026-07-23*
