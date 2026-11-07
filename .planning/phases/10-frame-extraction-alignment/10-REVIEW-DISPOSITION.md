---
phase: 10
review: 10-REVIEW.md
titles: json
findings:
  - id: IN-26
    severity: info
    disposition: open
    title: "тест битого кэша не ловит «починить вместо отвергнуть»: вариант `[1, 0]` после сортировки равен ответу пересчёта (новое)"
  - id: IN-03
    severity: info
    disposition: open
    title: "`offset_hints` теряет окно после любой сцены нулевой длины; после WR-11 подсказки расходятся с явным `--offset` (открыт, шире)"
  - id: IN-23
    severity: info
    disposition: open
    title: "`.scenes`, который не читается или целиком состоит из чужих строк, превращается в «без .scenes» без отказа (открыт, вне объёма, для фазы 11)"
  - id: IN-18
    severity: info
    disposition: open
    title: "по отчёту не видно, какую цель представляет итоговая точка (без изменений)"
  - id: IN-06
    severity: info
    disposition: open
    title: "итог «выровнено N из M» расходится с таблицей точек (без изменений)"
  - id: IN-24
    severity: info
    disposition: open
    title: "`_point_worker` ~90 строк с вложенной функцией (без изменений)"
  - id: IN-25
    severity: info
    disposition: open
    title: "необобщённость — параметр `n_enc` в `junction_prev_retry_frames` не используется (без изменений)"
  - id: IN-19
    severity: info
    disposition: open
    title: "вёрстка docstring (без изменений)"
  - id: IN-16
    severity: info
    disposition: open
    title: "«ближе vote_separation» против `<= sep` (без изменений)"
  - id: IN-17
    severity: info
    disposition: open
    title: "устаревший пример в docstring `AlignTarget` (без изменений)"
  - id: IN-02
    severity: info
    disposition: open
    title: "«сдвиг не менее W» теряется в итоге файла и строках кадров (без изменений)"
  - id: IN-04
    severity: info
    disposition: open
    title: "`UnicodeDecodeError` выходит из `check_pair_files` (без изменений)"
  - id: IN-05
    severity: info
    disposition: open
    title: "нет таймаута у ffmpeg/ffprobe (без изменений)"
  - id: IN-07
    severity: info
    disposition: open
    title: "замер jobs в scratch-скрипте обрывается на первой ошибке точки (без изменений, вне объёма)"
  - id: IN-09
    severity: info
    disposition: open
    title: "критерий независимости голосов неявно зависит от шага повтора (без изменений)"
  - id: WR-11
    severity: warning
    disposition: open
    title: "при `--offset` конец окна энкода (K + кадры_энкода) не сверяется с границей сцены: несогласованные `.scenes` отвергаются на одном пути и молча принимаются на другом (новое, зеркальная сторона правила D-07)"
  - id: WR-12
    severity: warning
    disposition: open
    title: "варианты битого кэша с неверными `keyframes` в `test_pts_cache_corrupt_recomputed` ничего не проверяют, валидация кэша T-10-44 не закреплена ни одним тестом (новое)"
  - id: IN-22
    severity: info
    disposition: open
    title: "UAT 11 не отличит «флаги mkvmerge верны» от «флаг K на каждом кадре», при котором WR-10 молча пуст (новое)"
open: 18
total: 18
recorded: 2026-11-07T18:33:20.100Z
---

# Phase 10: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| IN-26 | info | open | - |
| IN-03 | info | open | - |
| IN-23 | info | open | - |
| IN-18 | info | open | - |
| IN-06 | info | open | - |
| IN-24 | info | open | - |
| IN-25 | info | open | - |
| IN-19 | info | open | - |
| IN-16 | info | open | - |
| IN-17 | info | open | - |
| IN-02 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-07 | info | open | - |
| IN-09 | info | open | - |
| WR-11 | warning | open | - (not in the current review) |
| WR-12 | warning | open | - (not in the current review) |
| IN-22 | info | open | - (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
