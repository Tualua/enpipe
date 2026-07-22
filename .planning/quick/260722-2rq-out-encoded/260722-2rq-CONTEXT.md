# Quick Task 260722-2rq: Кодирование в папку (--out-dir) - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Task Boundary

Нужна возможность кодирования в папку: на входе имя файла, на выходе — папка.
Папка при необходимости СОЗДАЁТСЯ, туда кладётся `<ориг-стем>.Encoded.<ext>` файл.

Текущее состояние: `resolve_output_path(video, out)` уже кладёт
`<стем>.Encoded<суффикс>` внутрь `out`, НО только если `out.is_dir()` —
т.е. только для УЖЕ существующей директории. Недостающая часть — создание
папки, когда её ещё нет.
</domain>

<decisions>
## Implementation Decisions

### Disambiguation (как отличить папку от файла для несуществующего пути)
- **Отдельный флаг `--out-dir`** (LOCKED, выбор пользователя).
- `--out` остаётся строго путём к выходному ФАЙЛУ — поведение НЕ меняется
  (в т.ч. существующая семантика «`--out` = существующая директория → файл
  внутрь» сохраняется как есть ради байт-идентичности текущих тестов).
- `--out-dir DIR` → `DIR` создаётся (`mkdir -p`, если не существует), итог
  кладётся внутрь как `<стем видео>.Encoded<суффикс видео>` (та же формула,
  что уже в `resolve_output_path`).

### Scope (на какие команды распространить)
- **encode + run + batch** (LOCKED, выбор пользователя).
- Одиночный `enpipe encode`, `enpipe run`, и обе батч-ветки (папка-вход) в
  `encoding/pipeline.py::run_encode` и `cli/main.py::run_pipeline`.
- В батче `--out-dir` заменяет требование «-o должна быть существующей
  папкой»: папка создаётся при необходимости.

### Claude's Discretion (разумные дефолты, correctness-first)
- `--out` и `--out-dir` ВЗАИМОИСКЛЮЧАЮЩИ: если заданы оба — `die()` с ясным
  сообщением (argparse mutually exclusive group ИЛИ ручная проверка). НЕ
  молча предпочитать один другому.
- Расширить `resolve_output_path` (или добавить параллельный путь), чтобы
  оно принимало `out_dir` и делало `mkdir -p` ПЕРЕД возвратом пути. Важно:
  функция сейчас чистая (без сайд-эффектов) — создание папки лучше вынести в
  вызывающий код, а `resolve_output_path` оставить вычисляющим путь, ЛИБО
  явно задокументировать сайд-эффект. Планировщик решает, но байт-идентичность
  существующего поведения `--out` обязана сохраниться.
- Батч-гарды (`args.out is not None and not args.out.is_dir()` → die) должны
  корректно учитывать новый `--out-dir`: при `--out-dir` папка создаётся, а
  не роняет батч.
- Skip-if-exists логика батча (`resolve_output_path(v, ...).exists()`) должна
  указывать в ту же папку `--out-dir`, чтобы «уже готов» работал верно.
- НЕ трогать перезапись/overwrite-семантику итогового файла.
</decisions>

<specifics>
## Specific Ideas

- Ключевая формула пути уже существует: `out / (video.stem + ".Encoded" + video.suffix)`
  в `src/enpipe/encoding/pipeline.py:68`.
- Точки CLI: `encode_p` / `run_p` argparse в `src/enpipe/cli/main.py:149-180`.
- Батч-гарды: `encoding/pipeline.py:102-108`, `cli/main.py:100-106`.
- `_pipeline_one` (`cli/main.py`) пробрасывает `out=args.out` в encode_args —
  надо пробросить и `out_dir`.
</specifics>

<canonical_refs>
## Canonical References

- CLAUDE.md: correctness-first, Russian in-code prose, `typing`-generics style,
  env-var tunables pattern, `die()` для main-thread ошибок.
- Существующий тест байт-идентичности `enpipe run` == ручной two-step
  (test_cli_run.py / test_cli_dispatch.py) — НЕ должен сломаться.
</canonical_refs>
