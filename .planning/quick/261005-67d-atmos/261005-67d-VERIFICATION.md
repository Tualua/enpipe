---
phase: quick-261005-67d
verified: 2026-10-05T00:00:00Z
status: passed
score: 7/7 must-haves verified
has_blocking_gaps: false
human_verification:
  - test: "Atmos-copy на реальном источнике (28.Years.Later, a:4 eac3 Atmos) и partial-range ss/dur с copy-дорожкой"
    expected: "Дорожка Atmos скопирована как есть; при частичном диапазоне длительность copy-дорожки равна -t (иначе A/V рассинхрон)"
    why_human: "Нужен реальный Atmos-файл и реальные медиа; правило проверено только юнит-тестами на строках profile"
  - test: "Замер времени аудио на E01 Young Sherlock"
    expected: "Аудио короче фазы чанков (цель правки)"
    why_human: "Выигрыш по времени не измерялся"
---

# Quick 261005-67d: Verification Report

**Goal:** параллельное кодирование аудио по ffmpeg на дорожку, Atmos -> copy, остальные правила/порядок/метаданные сохранены, воркер без исключений, subprocess через enpipe.shared.proc.
**Status:** human_needed (автоматические проверки пройдены, остаются проверки на реальных медиа)

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Каждая дорожка — свой ffmpeg, параллельно | VERIFIED | `audio.py:155-157`: ThreadPoolExecutor(max_workers=min(len(streams), os.cpu_count() or 1)), `submit(_encode_track, c)` на каждую |
| 2 | Atmos (profile содержит «Atmos», без регистра) -> copy, приоритет выше lossless | VERIFIED | `audio.py:52`: `"atmos" in prof.lower()` стоит до lossless-ветки; unit-тесты есть |
| 3 | Прочие правила (FLAC/flac->copy/opus->copy/libopus 128k/256k+aformat, AUDIO_COPY, -ss/-t, -map_chapters -1) сохранены | VERIFIED | Сравнено с `80c4705^`: логика та же, спецификаторы стали безиндексными (в части одна дорожка); `-ss` до `-i`, `-t` после — как раньше |
| 4 | Порядок, language/title/disposition сохраняются | VERIFIED | `_merge_command` (`audio.py:96-118`): `-map i:a` по порядку, явные `-disposition:a:n` (включая "0"), теги language/title, `-default_mode passthrough`. Реальный прогон на синтетике по SUMMARY (мной не перезапускался) |
| 5 | encode_audio -> (bool, Optional[str]), не бросает, ошибка с номером дорожки после дренажа | VERIFIED | `_encode_track` ловит OSError; внешний `try/except Exception`; ошибки `дорожка N: ...` собираются после ожидания всех futures |
| 6 | Временные `<stem>.aNN.mka` удаляются при успехе и ошибке | VERIFIED | `finally` с `unlink(missing_ok=True)`; пути считаются до `try` |
| 7 | pipeline.py не менялся | VERIFIED | `git diff 80c4705^ HEAD -- pipeline.py` пуст; оба коммита затрагивают только audio.py и тесты |

Ограничение subprocess: все вызовы идут через `_proc.run` (`audio.py:124,141,169`), прямых `subprocess.*` нет.

## Spot-Checks

| Check | Result |
|-------|--------|
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit tests/subprocess -q` | 252 passed |
| TBD/FIXME/XXX в audio.py | нет |

GPU/hardware-тесты не запускались, в /data ничего не писалось.

## Inherited vs introduced: copy + частичный диапазон длиннее -t

**Унаследовано, не внесено.** Старый `encode_audio` (`80c4705^`) строил тот же argv: `-ss` до `-i`, `-t` после `-i`, `-map_chapters -1`, и `-c:a:n copy` для flac/opus/AUDIO_COPY. Новый `_track_command` даёт эквивалентный argv. Нюанс для оркестратора: новое правило Atmos добавляет в круг copy-дорожек ещё и Atmos-дорожки, которые по умолчанию (без AUDIO_COPY) раньше шли в Opus. Для них проблема теперь может проявляться при частичном диапазоне, чего раньше не было. Это расширение зоны воздействия, а не новый дефект кода. Я это не воспроизводил, а только сравнил argv. Проверять на реальном Atmos-источнике с `ss`/`dur`.

## Gaps

Блокирующих нет. Не проверено (см. human_verification): реальный Atmos-copy, длительность copy-дорожки при ss/dur, замер времени аудио.

Замечание: в SUMMARY заявлена проверка на синтетическом mkv, scratch-артефактов я не перепроверял.
