---
phase: 10
review: 10-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "`DEFAULT_JOBS` and its comment describe an API that no longer exists (necessity)"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "K-flag hardware test has an upper bound that can fail on a correct pipeline"
  - id: IN-01
    severity: info
    disposition: fixed
    title: "Over-long, stale module docstring paragraph"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "`OFFSET_*` comments name a family that has a single member"
  - id: IN-03
    severity: info
    disposition: fixed
    title: "Scratch script gaps"
  - id: IN-04
    severity: info
    disposition: fixed
    title: "Unneeded `noqa` on the broad catch"
  - id: IN-26
    severity: info
    disposition: open
    title: "тест битого кэша не ловит «починить вместо отвергнуть»: вариант `[1, 0]` после сортировки равен ответу пересчёта (новое)"
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
open: 15
total: 21
recorded: 2026-11-08T09:31:21.810Z
---

# Phase 10: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | fixed | 10-REVIEW-FIX.md |
| WR-02 | warning | fixed | 10-REVIEW-FIX.md |
| IN-01 | info | fixed | 10-REVIEW-FIX.md |
| IN-02 | info | fixed | 10-REVIEW-FIX.md |
| IN-03 | info | fixed | 10-REVIEW-FIX.md |
| IN-04 | info | fixed | 10-REVIEW-FIX.md |
| IN-26 | info | open | - (not in the current review) |
| IN-23 | info | open | - (not in the current review) |
| IN-18 | info | open | - (not in the current review) |
| IN-06 | info | open | - (not in the current review) |
| IN-24 | info | open | - (not in the current review) |
| IN-25 | info | open | - (not in the current review) |
| IN-19 | info | open | - (not in the current review) |
| IN-16 | info | open | - (not in the current review) |
| IN-17 | info | open | - (not in the current review) |
| IN-05 | info | open | - (not in the current review) |
| IN-07 | info | open | - (not in the current review) |
| IN-09 | info | open | - (not in the current review) |
| WR-11 | warning | open | - (not in the current review) |
| WR-12 | warning | open | - (not in the current review) |
| IN-22 | info | open | - (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
