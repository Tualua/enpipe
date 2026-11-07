---
status: testing
phase: 10-frame-extraction-alignment
source: [10-VERIFICATION.md]
started: 2026-11-07T18:36:03Z
updated: 2026-11-07T18:36:03Z
---

## Current Test

number: 1
name: "UAT 10 на Arc B50: полная пара с .scenes, частичный энкод без --offset, с --offset 4737"
expected: |
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2 -> выровнено либо отказ со списком неопределённых точек; SRC.mkv ENC_PART.mkv -> отказ с подсказкой --offset 4737 (сцены 40..42); с --offset 4737 и .scenes -> выровнено либо отказ со списком точек, но никогда выровнено при незакрытой стороне склейки. Готовые команды — 10-HUMAN-UAT.md, тест 10.
awaiting: user response

## Tests

### 1. UAT 10 на Arc B50: полная пара с .scenes, частичный энкод без --offset, с --offset 4737
expected: см. Current Test; команды — 10-HUMAN-UAT.md, тест 10
result: [pending]

### 2. UAT 11 на Arc B50: флаги ключевых кадров энкода enpipe после mkvmerge (допущение WR-10)
expected: для Gravity Falls S01E01 число K-пакетов в границах [233; 333], причины сверки .scenes пусты; «ВНЕ ГРАНИЦ» — сигнал оператору разобраться, а не доказательство дефекта. Команды — 10-HUMAN-UAT.md, тест 11
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
