---
phase: quick-261112-dab
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scratch/wmv3_cut.sh
  - tests/integration/test_hardware_real_media.py
  - tests/fixtures/media/README.md
autonomous: true
requirements: [DEC-05]
user_setup: []

estimate:
  tokens: 60000
  raw_tokens: 60000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "Есть кусок wmv3 (ASF, ~90–120 с, без перекодирования) в каталоге mktemp -d вне /data, нарезанный именованным скриптом scratch/wmv3_cut.sh; скрипт печатает готовую команду прогона теста"
    - "В tests/integration/test_hardware_real_media.py есть test_chunk_edges_avsw_wmv3: без ENPIPE_TEST_WMV3 он skip с подсказкой; таблица ключевых кадров — production keyframe_table (ffprobe-фолбэк по пакетам ASF, без требования Cues); seek/trim — production keyframe_table_decoder_order; чанки --avsw через chunk_command(decode=\"sw\") + encode_chunk, в обход отказа в decode.py"
    - "Предусловие «есть ключевой кадр с diff 0 и с diff != 0» сохранено; при невыполнении — pytest.fail, не xfail"
    - "Лог прогона (-s) даёт по каждому чанку: [S,E), K таблицы фолбэка, K production, diff, seek/trim, число кадров, first_best/last_best и вердикт края — и для production, и для контрольного варианта (seek/trim по номерам фолбэка без перенумерации)"
    - "Тест прогнан на B50; в SUMMARY — таблица краёв каждого чанка (first/last), классы diff, вывод: подтверждён ли сдвиг на wmv3 и исправляет ли его перенумерация; результат записан честно, даже если тест упал"
    - "src/ не изменён (git diff --stat -- src/ пуст); отказ wmv3 в src/enpipe/shared/decode.py не тронут"
  artifacts:
    - path: "scratch/wmv3_cut.sh"
      provides: "нарезка куска wmv3 в ASF через ffmpeg -c copy + сводка ffprobe + готовая команда pytest"
    - path: "tests/integration/test_hardware_real_media.py"
      provides: "test_chunk_edges_avsw_wmv3 и обобщённые хелперы _env_cut_or_skip / _vc1_layout(require_cues=...)"
    - path: "tests/fixtures/media/README.md"
      provides: "раздел ENPIPE_TEST_WMV3 с командами нарезки и прогона"
  key_links:
    - from: "test_chunk_edges_avsw_wmv3"
      to: "enpipe.encoding.keyframes.keyframe_table / keyframe_table_decoder_order"
      via: "прямой вызов production-функций (не run_encode, не refuse_unsafe_avsw)"
    - from: "test_chunk_edges_avsw_wmv3"
      to: "_verify_chunk_edges"
      via: "общий хелпер проверки краёв (PSNR, -2..+2, три вердикта)"
---

<objective>
Замер краёв чанков `--avsw` на реальном wmv3 (WMV9 Main, ASF, B-кадры) на B50 — вход для решения оператора в 10.1-11 (`vc1-only` / `lift-family`).

Purpose: на `wmv3` замера нет (10.1-11 Task 1 прямо говорит «кусков wmv3/vc1image нет»). Нужно выяснить на реальном материале: даёт ли ffprobe-фолбэк по пакетам ASF номера ключевых кадров, расходящиеся с выводом декодера (diff != 0), есть ли из-за этого сдвиг краёв чанков, и убирает ли его production-перенумерация `keyframe_table_decoder_order`.
Output: скрипт нарезки, новый аппаратный тест, раздел README, прогон на B50 и таблица в SUMMARY.

Ограничения оператора: `src/` не менять; отказ `wmv3` в `src/enpipe/shared/decode.py` не трогать; тест зовёт production-функции нижнего уровня напрямую, как `test_chunk_edges_avsw_vc1`.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.planning/phases/10.1-programmnyy-dekod-v-enkode-qsvencc-avsw/10.1-09-SUMMARY.md
@.planning/phases/10.1-programmnyy-dekod-v-enkode-qsvencc-avsw/10.1-10-SUMMARY.md
@tests/integration/test_hardware_real_media.py
@src/enpipe/encoding/keyframes.py
@tests/fixtures/media/README.md

Факты из кода (HEAD 6305910), чтобы не перечитывать:
- `keyframe_table(src, fps)`: для суффикса не из (.mkv, .mka, .webm) сразу `keyframe_table_ffprobe` — `ffprobe -show_packets packet=flags,pts_time`, номер = `round(pts_time * fps)`; `die()` если таблица пуста или первый номер != 0. `die()` = `sys.exit("encode_scenes: ...")`, т.е. `SystemExit` с текстом.
- `keyframe_table_decoder_order(src, table)` -> `(new_table, decoded, shifted)`; при неоднозначности (нет I-кадра в ±2, ничья, не строго возрастает, 0 не в 0) — `die()`.
- `probe_fps` берёт `avg_frame_rate`, затем `r_frame_rate` (в ASF `r_frame_rate` бывает 1000/1 — печатать fps в лог).
- Тест-модуль: `_vc1_cut_or_skip()` (ENPIPE_TEST_VC1), `_vc1_layout(cut)` (стр. ~1483; требует Cues через `keyframe_table_cues(...) is None -> pytest.fail`, печатает `[vc1] K=.. diff=..`, выбирает starts, проверяет предусловие diff 0 / diff != 0 через `pytest.fail`), `test_chunk_edges_avsw_vc1` (стр. ~1535), `_edge_state`, `test_vc1_seek_experiment_true_keyframes` (контроль/эксперимент, печать `[vc1-exp] ... first_best/last_best/verdict`), `_verify_chunk_edges(src, chunks, total, tmp) -> (errors, inconclusive, bests)`.
- `content.extract_frame_by_index` декодирует от начала файла без `-ss` (O(n)); на 720p ~3600 кадров это приемлемо.
- Маркер `hardware`, по умолчанию исключён (`addopts = -m "not hardware"`).
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Скрипт нарезки scratch/wmv3_cut.sh и кусок wmv3 в ASF</name>
  <files>scratch/wmv3_cut.sh</files>
  <action>
Создать именованный bash-скрипт (правило оператора: в UAT без python-однострочников, только понятные команды или скрипт в scratch/). Комментарии и сообщения по-русски, стиль как у scratch/wmv_codecs.sh (`set -u`, шапка с назначением и использованием).

Использование: `scratch/wmv3_cut.sh ИСТОЧНИК [ДЛИТЕЛЬНОСТЬ_С=100]`. Поведение:
1. Проверить, что источник читается; создать `DIR=$(mktemp -d)` (вне /data — по умолчанию /tmp); выход `$DIR/<имя источника без расширения>_cut.wmv`.
2. Нарезать с начала файла без перекодирования: ffmpeg `-hide_banner -i ИСТОЧНИК -map 0:v:0 -an -sn -t ДЛИТЕЛЬНОСТЬ -c copy -f asf ВЫХОД`. Начало файла, а не середина — чтобы первый ключевой кадр имел pts 0 (иначе production-фолбэк `keyframe_table_ffprobe` отказывает «нет keyframe на кадре 0»).
3. Сводка по куску через ffprobe (только чтение): codec_name, profile, width/height, avg_frame_rate, r_frame_rate, has_b_frames, start_time, duration; число пакетов видео, число пакетов с флагом K, число пакетов с pts != dts, pts_time первого пакета с флагом K; число кадров декода и число кадров с pict_type I (`-show_frames -show_entries frame=pict_type`).
4. Громко завершиться ненулевым кодом с понятным текстом, если codec_name не `wmv3`, если has_b_frames = 0, если pts_time первого K-пакета, умноженный на avg_frame_rate и округлённый, не равен 0, или если K-пакетов меньше 6 (тогда не набрать классы diff). Не подбирать флаги ffmpeg молча: если кусок не проходит, исполнитель фиксирует вывод скрипта в SUMMARY и пробует вариант только явно (например, другую длительность), записывая, что именно менял.
5. В конце напечатать путь к куску и готовую команду прогона: `ENPIPE_TEST_WMV3="<путь>" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k wmv3 -s`.

Затем запустить скрипт на `/data/downloads/wmv_test4.wmv` с длительностью 100 (если ~4 I-кадра на 30 с, это ~13 ключевых кадров). Кусок не коммитится (лежит в mktemp-каталоге). Путь к куску и вывод сводки сохранить для Task 3.
  </action>
  <verify>
    <automated>bash -n scratch/wmv3_cut.sh && scratch/wmv3_cut.sh /data/downloads/wmv_test4.wmv 100</automated>
  </verify>
  <done>Скрипт существует, исполняемый (chmod +x), проходит `bash -n`; прогон на wmv_test4.wmv завершился кодом 0, напечатал сводку (wmv3, has_b_frames > 0, первый K-пакет на кадре 0, >= 6 K-пакетов) и готовую команду pytest с путём к куску вне /data.</done>
</task>

<task type="auto">
  <name>Task 2: test_chunk_edges_avsw_wmv3 — production-таблица фолбэка + перенумерация, контроль для диагностики</name>
  <files>tests/integration/test_hardware_real_media.py, tests/fixtures/media/README.md</files>
  <action>
Переиспользовать хелперы, не дублировать. Поведение существующих VC-1 тестов не менять (имена, сообщения, печать `[vc1]`, требование Cues для ENPIPE_TEST_VC1).

1. Обобщить `_vc1_cut_or_skip()` в `_env_cut_or_skip(var: str, hint: str) -> Path` (skip, если переменная не задана или файла нет; текст подсказки — аргумент); `_vc1_cut_or_skip()` оставить тонкой обёрткой с прежним текстом про ENPIPE_TEST_VC1. Добавить `_wmv3_cut_or_skip()` на `ENPIPE_TEST_WMV3` с подсказкой: кусок wmv3 в ASF даёт оператор (не хранится в репозитории), см. раздел ENPIPE_TEST_WMV3 в tests/fixtures/media/README.md и scratch/wmv3_cut.sh.

2. Обобщить `_vc1_layout(cut)` в `_vc1_layout(cut, *, tag: str = "vc1", require_cues: bool = True)`: при `require_cues=True` — прежняя проверка Cues и прежний текст fail; при `False` проверку Cues не делать. Таблицу брать production `keyframe_table(cut, fps)` в обоих случаях; вызов обернуть так, чтобы `SystemExit` от `die()` превращался в `pytest.fail` с текстом исключения (например, «нет keyframe на кадре 0» на ASF — это результат замера, а не ошибка теста). Префикс печати `[{tag}]` вместо зашитого `[vc1]` (для VC-1 tag по умолчанию даёт прежний вывод). Дополнительно печатать в шапке `table_source=cues|ffprobe` (cues, если `keyframe_table_cues` вернул таблицу и суффикс mkv; иначе ffprobe) и число ключевых кадров по классам diff (-1/0/+1/None). Предусловие «есть diff 0 и diff != 0» сохранить ровно как есть — `pytest.fail`, не xfail (требование оператора).

3. Новый тест `test_chunk_edges_avsw_wmv3(tmp_path)` рядом с `test_chunk_edges_avsw_vc1`. Docstring (английский, как у соседних тестов) объясняет: замер для решения 10.1-11 по wmv3; таблица — production `keyframe_table` (ffprobe-фолбэк по пакетам ASF, номер = round(pts_time*fps)); seek/trim — production `keyframe_table_decoder_order`; чанки кодируются напрямую `chunk_command(..., decode="sw")` + `encode_chunk` в обход `run_encode`, поэтому отказ `refuse_unsafe_avsw` для wmv3 не срабатывает и не меняется. Шаги:
   - `cut = _wmv3_cut_or_skip()`; `fps, table, i_pos, total, diffs, starts = _vc1_layout(cut, tag="wmv3", require_cues=False)`.
   - `keyframe_table_decoder_order(cut, table)`, `SystemExit` -> `pytest.fail` с текстом (неоднозначная перенумерация — тоже результат замера); `decoded != total` -> `pytest.fail`. Напечатать `shifted`. Сверить production-таблицу с независимым оракулом `content.true_keyframe_table(table, i_pos)` через assert, как в `test_vc1_seek_experiment_true_keyframes`.
   - Для каждого start, как в эксперименте 10.1-08/10.1-10, кодировать два варианта с `decode="sw"`: `prod` (seek/trim по production-таблице — проверяемый вариант) и `ctl` (seek/trim по таблице фолбэка без перенумерации — только диагностика: показывает, есть ли сдвиг без исправления). Это решение исполнителя-планировщика (Claude's discretion): без контроля из одного прогона нельзя ответить на вопрос оператора «подтверждён ли сдвиг»; контроль не ассертится.
   - Печать на чанк одной строкой с префиксом `[wmv3]`: индекс, `[S,E)`, `fbK` (K фолбэка), `prodK`, `diff`, для ctl и prod — seek, trim, frames/ожидаемо, err, `first_best`, `last_best`, вердикт `ok|fail|inconcl`. Края проверить одним вызовом `_verify_chunk_edges(cut, ctl_chunks + prod_chunks, total, tmp_path / "edges")` (индексы 0..n-1 — контроль, n..2n-1 — production). Для ctl в список чанков брать только `got > 0`; если у ctl нет чанка — печатать `ctl=нет кадров` и не ломать нумерацию prod (держать отдельное соответствие индексов; при необходимости проверять ctl и prod двумя вызовами `_verify_chunk_edges` в разные подкаталоги). Состояние inconclusive различать отдельно от fail (расширить `_edge_state` или собрать множество индексов из списка inconclusive по тому же префиксу `chunk {i} `).
   - Итоговая строка `[wmv3] ИТОГ: ...`: число чанков с diff != 0; у контроля — сколько чанков с fail-краем и совпадает ли множество fail с множеством diff != 0; у production — сколько fail/inconclusive/ошибок кадров.
   - Ассерты только по production, в порядке `test_chunk_edges_avsw_vc1`: ошибки кодирования prod -> `pytest.fail`; fail-края prod -> `assert not ...`; inconclusive prod -> `pytest.fail`. Печать таблицы — ДО ассертов, чтобы лог содержал замер и при падении.
   - Не трогать `src/`; не импортировать и не вызывать `refuse_unsafe_avsw`.

4. tests/fixtures/media/README.md: раздел `## ENPIPE_TEST_WMV3: a short real wmv3 (WMV9, ASF) cut` после раздела ENPIPE_TEST_VC1, в том же стиле (английский): зачем (ASF без Cues — номера ключевых кадров из ffprobe-фолбэка по pts пакетов, B-кадры; замер для 10.1-11), кусок не в репозитории, команда нарезки `scratch/wmv3_cut.sh /data/downloads/wmv_test4.wmv 100`, команда прогона с `-k wmv3 -s`.

Стиль: `from __future__ import annotations` уже есть; generics из `typing` (`List`, `Tuple`, `Optional`, `Dict`); комментарии в коде по-русски, объясняют «почему».
  </action>
  <verify>
    <automated>uv run ruff check src tests && uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k "wmv3 or vc1" -rs --collect-only -q && env -u ENPIPE_TEST_WMV3 -u ENPIPE_TEST_VC1 uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k "test_chunk_edges_avsw_wmv3 or test_chunk_edges_avsw_vc1" -rs && uv run pytest -q && git diff --quiet -- src/</automated>
  </verify>
  <done>`grep -c "def test_chunk_edges_avsw_wmv3" tests/integration/test_hardware_real_media.py` = 1 (на HEAD 0); `grep -c "ENPIPE_TEST_WMV3" tests/fixtures/media/README.md` >= 1 (на HEAD 0); без переменных окружения оба теста skip с подсказками; ruff чист; весь не-аппаратный набор зелёный; `git diff --quiet -- src/` (src не изменён).</done>
</task>

<task type="auto">
  <name>Task 3: Прогон на B50 и протокол замера в SUMMARY</name>
  <files>.planning/quick/261112-dab-zamer-kraev-chankov-avsw-dlya-wmv3-s-b-k/261112-dab-SUMMARY.md</files>
  <action>
Оператор явно попросил прогнать на B50 — прогон входит в задачу. Перед прогоном: `ls /dev/dri/renderD*`, `qsvencc --version` (>= r4677). Затем, если ENPIPE_TEST_VC1 есть у оператора, VC-1 тесты НЕ запускать (не входят в замер); запустить только новый тест с путём куска из Task 1, сохранив полный лог в mktemp-каталог куска (не в репозиторий): `ENPIPE_TEST_WMV3="<путь>" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k wmv3 -s -rA 2>&1 | tee "<каталог куска>/wmv3_edges.log"`.

В SUMMARY (по-русски) записать честно, даже если тест упал (fail предусловия/ошибки кодирования/inconclusive — это тоже результат):
1. Источник и кусок: сводка scratch/wmv3_cut.sh (кодек, профиль, разрешение, fps avg/r, has_b_frames, start_time, пакеты/K/pts!=dts, кадров декода, I-кадров), команда нарезки.
2. Таблица ключевых кадров: K фолбэка, diff, K production; распределение классов diff; `shifted`; совпадение с оракулом.
3. Таблица по чанкам: `[S,E)`, diff, для контроля и production — seek, trim, кадры/ожидаемо, first_best, last_best, вердикт.
4. Вывод отдельными пунктами: (а) подтверждён ли сдвиг краёв на wmv3 без перенумерации (fail контроля ровно там, где diff != 0); (б) исправляет ли его перенумерация (production без fail/inconclusive и с верным числом кадров); (в) если предусловие diff 0 / diff != 0 не выполнилось — так и написать, привести классы diff и что это значит (например, все diff = 0: фолбэк по pts пакетов ASF с B-кадрами уже даёт номера по выводу декодера), без обходов теста.
5. Итог одним абзацем для вопроса 10.1-11 Task 1 (`vc1-only` / `lift-family`): что замер говорит о wmv3 — без выбора за оператора (решение остаётся за ним), и что vc1image по-прежнему без замера.
6. Готовые команды повторения (нарезка и прогон) — для оператора.

Не менять src/, не трогать отказ в decode.py, не править 10.1-11-PLAN.md.
  </action>
  <verify>
    <automated>test -s .planning/quick/261112-dab-zamer-kraev-chankov-avsw-dlya-wmv3-s-b-k/261112-dab-SUMMARY.md && grep -c "first_best\|diff" .planning/quick/261112-dab-zamer-kraev-chankov-avsw-dlya-wmv3-s-b-k/261112-dab-SUMMARY.md && git diff --quiet -- src/</automated>
  </verify>
  <done>Тест прогнан на B50 (результат pass или fail записан как есть, с причиной); SUMMARY содержит сводку куска, таблицу ключевых кадров с diff, таблицу краёв всех чанков (first/last) для контроля и production, вывод по сдвигу и по перенумерации, абзац для 10.1-11 без выбора за оператора и команды повторения; src/ не изменён.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| операторский медиафайл -> ffmpeg/ffprobe/qsvencc | внешний файл из /data разбирается внешними бинарниками |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-q261112-01 | Tampering | /data/downloads/wmv_test4.wmv | low | mitigate | Источник только читается; кусок пишется в mktemp -d вне /data (флаги скрипта не пишут в каталог источника) |
| T-q261112-02 | Information disclosure | кусок и лог прогона | low | accept | Не коммитятся (mktemp-каталог), в репозиторий попадают только сводные числа в SUMMARY |
| T-q261112-03 | Tampering | тест-модуль: ложный «ok» краёв | medium | mitigate | Предусловие diff 0 / diff != 0 — pytest.fail; inconclusive production — pytest.fail; production сверяется с независимым оракулом true_keyframe_table; печать замера до ассертов |
| T-q261112-SC | Tampering | npm/pip/cargo installs | low | accept | Установок пакетов нет |
</threat_model>

<verification>
- `bash -n scratch/wmv3_cut.sh` и успешный прогон скрипта на wmv_test4.wmv.
- `uv run ruff check src tests`, `uv run pytest -q` зелёные; без переменных окружения VC-1/wmv3 тесты skip.
- `git diff --quiet -- src/` — src не изменён; `grep -n "refuse_unsafe_avsw" tests/integration/test_hardware_real_media.py` не находит вызова в новом тесте.
- Аппаратный прогон `-k wmv3 -s` выполнен на B50, лог сохранён в каталоге куска.
</verification>

<success_criteria>
Оператор получает в SUMMARY фактический замер краёв чанков `--avsw` на wmv3 с B-кадрами (контроль без перенумерации и production с перенумерацией), классы diff и вывод по сдвигу и исправлению — достаточный вход для решения 10.1-11 Task 1; тест остаётся в наборе как opt-in регрессия по ENPIPE_TEST_WMV3.
</success_criteria>

<output>
Create `.planning/quick/261112-dab-zamer-kraev-chankov-avsw-dlya-wmv3-s-b-k/261112-dab-SUMMARY.md` when done
</output>
