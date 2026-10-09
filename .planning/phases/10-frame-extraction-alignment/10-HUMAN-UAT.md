---
status: partial
phase: 10-frame-extraction-alignment
source: [10-VERIFICATION.md]
started: 2026-10-08T21:59:42Z
updated: 2026-10-09T23:59:00Z
---

## Current Test

[ожидает решения оператора по WR-05]

## Tests

### 1. Решить по WR-04: принять ослабленную защиту D-13 или закрыть до фазы 11
expected: Решение оператора. Рекомендация — закрыть малым патчем (описан в 10-REVIEW.md): окрестность ±2W вокруг занятых кадров в pair.py, разнесённый подсчёт голосов в align.aggregate, проверка align_retry_step > 2*align_window в AnalyzeConfig, регрессионный тест.
result: issue — оператор: закрыть WR-04 до фазы 11 (гэп-план); закрыто планом 10-08

### 2. Решить по WR-05: масштаб «независимости» голосов выравнивания (D-13)
expected: Решение оператора о том, какой разнос голосов считать «разными местами файла». Сейчас разнос > 2W кадров (7 при W=3); «выровнено» может держаться на одной вспышке движения ≥ 2W+2 = 8 кадров (воспроизведено: n=165, движение 41..49 → ok=True, n_aligned=2). Развилка — 10-REVIEW.md, WR-05.
result: [pending]

## Summary

total: 2
passed: 0
issues: 1
pending: 1
skipped: 0
blocked: 0

## Gaps

- truth: "D-13: ≥2 независимых точки означает ≥2 разнесённых места файла, а не ≥2 различных кадра"
  status: resolved
  reason: "WR-04 (10-REVIEW.md): повтор точки голосует соседним кадром другой цели; ok=True при n_aligned=2 из одного места"
  severity: major
  test: 1
  fix: "окрестность ±2W вокруг занятых кадров (pair.py), разнесённый подсчёт в align.aggregate, align_retry_step > 2*align_window в AnalyzeConfig, регрессионный тест — 10-08"
