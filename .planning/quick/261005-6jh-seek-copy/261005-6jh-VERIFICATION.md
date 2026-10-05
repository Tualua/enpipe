---
phase: quick-261005-6jh
verified: 2026-10-05T00:00:00Z
status: passed
score: 5/5 must-haves verified
has_blocking_gaps: false
---

# Quick 261005-6jh: Verification

**Goal:** copy-дорожки в частичном режиме начинаются с пакета источника на ss, длительность ≈ dur; перекодируемые и полный режим без изменений; legacy/ и pipeline.py не тронуты.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | copy начинается с пакета с \|pts-ss\| ≤ длительности пакета | VERIFIED | `_track_command`: input `-ss ss-30` до `-i`, output `-ss` после (audio.py, коммит 5f3fad0). Медиа-тест на 28YL: a:4 E-AC3 pts=600.000, TrueHD 600.006 (допуск major sync, обосновано в SUMMARY) |
| 2 | Длительность ≈ dur | VERIFIED | span 60.0000 (eac3), 59.994 (truehd); синтетика зелёная |
| 3 | argv перекодируемых прежний | VERIFIED | ветка `elif ss is not None` не менялась, `-t` после `-i`; юнит-тесты |
| 4 | Полный режим без -ss/-t | VERIFIED | `two_step` только при ss is not None; юнит-тест |
| 5 | Порядок/метаданные/параллельность/(bool, str) сохранены | VERIFIED | изменён только `_track_command`; 258 unit+subprocess зелёные, воркер не менялся |

## Прогоны (выполнены верификатором)

- `uv run ruff check src tests`: All checks passed
- `uv run pytest tests/unit tests/subprocess -q`: 258 passed
- `uv run pytest tests/integration/test_audio_seek_copy.py -m "hardware or not hardware" -v`: 2 passed (синтетика + 28YL)
- `git diff 1a0653f HEAD -- legacy src/enpipe/encoding/pipeline.py`: пусто
- Использование proc seam: изменения только в построении argv, вызовы через `_proc` прежние.

## Замечания

- Отклонение для TrueHD (начало с первого keyframe/major sync, 600.006 против 600.000) обосновано и допустимо по условию задачи.
- Тест `test_audio_seek_copy.py` 149 строк (≥ 80).
- RED-проверка на старом коде описана в SUMMARY, не перепроверялась.

## Gaps

Нет.
