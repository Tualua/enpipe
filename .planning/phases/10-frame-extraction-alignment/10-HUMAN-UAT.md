---
status: testing
phase: 10-frame-extraction-alignment
source: [10-VERIFICATION.md]
started: 2026-10-08T21:59:42Z
updated: 2026-11-07T18:23:29Z
---

## Current Test

[ожидает прогона на B50: тесты 10, 11]

## Tests

### 1. Решить по WR-04: принять ослабленную защиту D-13 или закрыть до фазы 11
expected: Решение оператора. Рекомендация — закрыть малым патчем (описан в 10-REVIEW.md): окрестность ±2W вокруг занятых кадров в pair.py, разнесённый подсчёт голосов в align.aggregate, проверка align_retry_step > 2*align_window в AnalyzeConfig, регрессионный тест.
result: issue — оператор: закрыть WR-04 до фазы 11 (гэп-план); закрыто планом 10-08

### 2. Решить по WR-05: масштаб «независимости» голосов выравнивания (D-13)
expected: Решение оператора о том, какой разнос голосов считать «разными местами файла». Сейчас разнос > 2W кадров (7 при W=3); «выровнено» может держаться на одной вспышке движения ≥ 2W+2 = 8 кадров (воспроизведено: n=165, движение 41..49 → ok=True, n_aligned=2). Развилка — 10-REVIEW.md, WR-05.
result: issue — оператор: разнос ≈ 1 с, max(2W, align_retry_step // 2) в aggregate и _taken_frames; гэп-план 10-09; закрыто планом 10-09

### 3. Решить по WR-06: принять отключение повторов D-11 на энкодах 49..225 кадров или сдвигать повторы
expected: Решение оператора. Принятие T-10-09-04 в 10-09-PLAN.md/SUMMARY сделано на заниженных данных («часть длин 121, 165, 189»); фактически повторов нет на всём диапазоне 49..225 кадров (≈ до 9,4 с при 24 fps), а также при 241 и 289. Ложного «выровнено» это не даёт — только лишние «неопределённо». Варианты — 10-REVIEW.md, WR-06: (а) сдвигать повтор за окрестность ±sep вместо пропуска; (б) оставить, исправить формулировку и добавить граничный тест n=225/226.
result: issue — оператор: вариант (б) — поведение оставить (пропуск повторов в чужой окрестности ±sep), исправить формулировку масштаба в комментарии pair._taken_frames и 10-09-SUMMARY (49..225, а также 241 и 289; до ~200 кадров окрестности покрывают весь файл — сдвигать некуда), добавить граничный тест n=225/226; гэп-план

### 4. Решить по WR-07/IN-10: формулировка обоснования в docstring pair._taken_frames и комментарии test_retries_allowed_boundary
expected: Решение оператора. Масштаб (49..225, 241, 289) верен, но «сдвигать повтор некуда» истинно только до n ≤ 197 (на 225 свободно 28 кадров, 241 — 44, 289 — 92); диапазон верен только без .scenes (IN-10). Поведение не меняется. Варианты: мини-правка текста или backlog. Отдельно — IN-11 (граничный тест дублирует условие пропуска, не идёт через _point_worker).
result: issue — оператор: мини-правка текста по WR-07/IN-10 (ограничить «сдвигать некуда» условием n ≤ 197, оговорка «без .scenes», исправить комментарий теста) и исправить IN-11 сейчас (граничный тест через check_pair_files с Fake, а не дублем условия); поведение повторов не меняется; гэп-план; закрыто планом 10-11 (оператор подтвердил по check_10_11.py и мутационной проверке теста)

### 5. Решить по IN-12/IN-13: порядок фраз в docstring pair._taken_frames и покрытие граничного теста
expected: Решение оператора. IN-12: после абзаца про .scenes фразы «каждый повтор попадает в окрестность цели» и «при n ≤ 197 окрестности покрывают весь файл» читаются как общие, а со .scenes неверны. IN-13: test_retries_boundary_via_worker не закрепляет 49..224 и пример n=192 со .scenes. Поведение не меняется.
result: issue — оператор: IN-12 — мини-правка сейчас (переставить фразы, чтобы утверждения о покрытии явно относились к случаю без .scenes); IN-13 — добавить тесты сейчас (диапазон 49..224 и пример n=192, scenes=[(0,152),(152,192)] → повтор 96); поведение не меняется; гэп-план 10-12; закрыто планом 10-12 (оператор подтвердил после повторного ревью и верификации)

### 6. Решить по IN-14/IN-15: ограничение «на этих длинах» и фраза «Числа закреплены тестами» в docstring pair._taken_frames
expected: Решение оператора. IN-14: «Без .scenes каждый повтор попадает в окрестность какой-либо цели» потеряло ограничение «на этих длинах» и читается как общее (неверно с n=226; 372 длины из 49..599). IN-15: «Числа закреплены тестами» обещает больше, чем проверяют тесты (покрытие при n ≤ 197 и 28/44/92 свободных кадров не закреплены). Поведение не меняется.
result: issue — оператор: мини-правка сейчас (IN-14, IN-15); поведение не меняется; гэп-план; поглощено тестом 7 (docstring _taken_frames переписывается под новое поведение)

### 7. Пересмотр WR-06/D-13: пропущенный повтор может скрыть сдвиг (ложное «выровнено»)
expected: Решение оператора. При планировании 10-13 plan-checker показал контрпример к посылке теста 3: три цели «выровнено», две «неопределённо», сдвиг только на пропущенном повторе → aggregate даёт «выровнено». Посылка «ложного «выровнено» не даёт» неверна.
result: issue — оператор (2026-10-24): (в) ужесточить D-13 — «выровнено» только если после повторов не осталось точек «неопределённо»; (а) сдвигать повтор за чужую окрестность вместо пропуска; повторы назад, если вперёд некуда (крайние точки, вариант 2), общий лимит ≤ 3; неопределённая склейка заменяется соседней склейкой из .scenes; гэп-план 10-13 (заменяет прежний текстовый 10-13)

### 8. Решить по WR-08: склейка на кадре 0 без свободных замен
expected: Решение оператора (10-REVIEW.md, WR-08; 10-VERIFICATION.md). С .scenes склейка на кадре 0 меряется одним кадром и повторов D-11 не получает; при «неопределённо» и отсутствии свободной замены правило (в) даёт отказ («неопределённые точки (кадры энкода): 0»), хотя без .scenes та же пара выровнена (повтор 48). Ложного «выровнено» нет. Варианты: (1) после неудачных замен проверять склейку обычными повторами align.retry_frames, тот же общий лимит; (2) оставить отказ, записать в docstring _point_worker и SUMMARY, добавить тест-якорь; (3) backlog.
result: issue — оператор (2026-11-05): вариант 1 — склейке без замен (или после неудачных замен) давать обычные повторы align.retry_frames; лимит align_retry_max ОБЩИЙ на замены и повторы склейки (≤ 3); правило (в) не меняется; гэп-план 10-14
  закрыто кодом: 10-14 (WR-08), 10-15 (CR-01, WR-09), 10-16 (CR-02); регрессии test_partial_junctions_retried_aligned, test_junction_zero_retry ×3, test_junction_prev_side_refused; подтверждение на реальной паре — тест 10

### 9. Повторный прогон теста 7 на реальной паре (B50)
expected: Пара без сдвига с .scenes — «выровнено» либо отказ с причиной «неопределённые точки (кадры энкода): …», но никогда «выровнено» при оставшейся неопределённой точке. Частичный энкод без --offset — отказ «сдвиг …». Время извлечения приемлемо (до 20 декодов кадров энкода на файл у обычных точек).
commands: |
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv          # частичный энкод, без --offset → «сдвиг»
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --offset N
result: pass (корректность) — прогон Claude по просьбе оператора 2026-11-05, B50, пара Young Sherlock S01E01 (HEVC PQ 3840x1600 → AV1 enpipe):
  - полная пара (76378 кадров, .scenes 592 сцены): aligned 5/5 (648, 19050, 38111, 57516, 71293), запас 3.9..24.9 дБ; jobs 1 — 4.75 с/точку, jobs 2 — 2.90 с/точку
  - частичный энкод сцен 40..42 ([4737, 5139), 402 кадра) без --offset: отказ «число кадров различается», подсказка «--offset 4737 (сцены 40..42)» первой
  - тот же энкод, --offset 4737, с .scenes: ОТКАЗ на верной паре — «выровнено 3 из 5 …; неопределённые точки (кадры энкода): 75, 149» (склейки сцен 41 и 42, запас 2.4 и 2.6 дБ < align_margin_db 3.0; замен нет — все три склейки энкода уже цели)
  - тот же энкод без .scenes (check_pair_files напрямую): --offset 4737 → aligned 5/5; 4738 → shift −1 во всех 5 точках; 4736 → shift +1 во всех 5 точках
  - --offset 4738 с .scenes отвергается предпроверкой («не совпадает с началом ни одной сцены»), до выравнивания не доходит
  Ложного «выровнено» нет; сдвиг ±1 ловится. Наблюдение для теста 8: WR-08 шире кадра 0 — частичный энкод из 1–3 сцен с .scenes даёт ложный отказ на любой склейке «неопределённо» (замен нет).

### 10. Повторный прогон теста 9 на B50 после CR-02 (10-16) и WR-10 (10-17)
expected: Полная пара с .scenes — «выровнено» либо отказ со списком неопределённых точек, никогда «выровнено» при незакрытой точке. Частичный энкод сцен 40..42 без --offset — отказ с подсказкой «--offset 4737 (сцены 40..42)». С --offset 4737 и .scenes — «выровнено» (ожидание после CR-02: склейки 75 и 149 закрыты повторами обеих сторон) либо отказ со списком точек. Ни на одной паре enpipe нет причины «.scenes не совпадают с энкодом».
commands: |
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --jobs 1,2
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv
  uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --offset 4737
result: [pending]

### 11. WR-10 / IN-22: флаги ключевых кадров энкода enpipe после mkvmerge на началах сцен
expected: Число пакетов с флагом K в энкоде лежит в границах [нижняя; верхняя]. Нижняя — число различных начал непустых сцен в окне [offset, offset + кадры_энкода) (чанк начинается с ключевого кадра). Верхняя — Σ ceil((min(e, offset + кадры_энкода) − s) / GOP_LEN) по непустым сценам окна, где GOP_LEN — значение при энкоде (по умолчанию 300, encoding/chunk.py): qsvencc ставит ключевой кадр в начале чанка и каждые GOP_LEN кадров внутри него. Верхняя граница много меньше числа кадров, поэтому энкод «ключевой каждый кадр» (сверка WR-10 тогда молча пуста) отличается от верных флагов. Для готовой пары Gravity Falls S01E01 (233 сцены, 30325 кадров, offset 0) K-пакетов от 233 до верхней границы не больше 333 (ceil(l/300) ≤ (l + 299)/300, сумма ≤ (30325 + 233·299)/300 ≈ 333,3). Граница предполагает флаг K только в начале чанка и каждые GOP_LEN кадров: округление GOP у qsvencc (--gop-ref-dist) или адаптивные I-кадры могут дать больше на верном энкоде, поэтому «ВНЕ ГРАНИЦ» — сигнал оператору разобраться, а не доказательство дефекта; остановиться и вынести оператору, кода не менять (при K = числу кадров сверка WR-10 бессмысленна). scenes_reasons, check_offset и keyframe_reasons пусты для полной пары (offset 0) и для частичной (offset 4737: конец окна — конец сцены 42, WR-11). Если keyframe_reasons не пуст на настоящем энкоде enpipe при K в границах — допущение о флагах mkvmerge (ключевой флаг на первом кадре каждого чанка) ложно: остановиться и вынести оператору (иначе все пары enpipe получают ложный отказ). Если команда печатает «сцен 0» — путь к .scenes неверен (read_scenes_file молча даёт пустой список).
commands: |
  # число ключевых пакетов энкода и число сцен
  ffprobe -v error -select_streams V:0 -show_entries packet=pts_time,flags -of csv=p=0 ENC.mkv | awk -F, '$2 ~ /K/ {n++} END {print n}'
  wc -l < SRC.mkv.scenes
  # границы K-пакетов, вердикт и причины кодом enpipe, аргументы: SRC ENC SCENES OFFSET GOP_LEN
  # (проверено на синтетике: «в границах» и пустые причины; all-intra энкод — «ВНЕ ГРАНИЦ»)
  # полная пара (offset 0):
  uv run python -c 'import sys, math; from pathlib import Path; from enpipe.analysis import frames, precheck; from enpipe.analysis.sources import read_scenes_file; src, enc, sc, off, gop = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]); sp, _ = frames.packet_table(src); ep, ek = frames.packet_table(enc); s = read_scenes_file(sc); hi = off + len(ep); w = [(a, min(b, hi)) for a, b in s if b > a and off <= a < hi]; lo = len({a for a, _ in w}); up = sum(math.ceil((e - a) / gop) for a, e in w); print("кадров источника", len(sp), "энкода", len(ep), "сцен", len(s), "сцен в окне", len(w)); print("K-пакетов", len(ek), "границы [", lo, ";", up, "]", "в границах" if lo <= len(ek) <= up else "ВНЕ ГРАНИЦ"); print("scenes_reasons:", precheck.scenes_reasons(s, len(sp))); print("check_offset:", precheck.check_offset(len(sp), len(ep), off, s)[2]); print("keyframe_reasons:", precheck.keyframe_reasons(s, off, len(ep), ek))' SRC.mkv ENC.mkv SRC.mkv.scenes 0 300
  # частичный энкод (offset 4737):
  uv run python -c 'import sys, math; from pathlib import Path; from enpipe.analysis import frames, precheck; from enpipe.analysis.sources import read_scenes_file; src, enc, sc, off, gop = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]); sp, _ = frames.packet_table(src); ep, ek = frames.packet_table(enc); s = read_scenes_file(sc); hi = off + len(ep); w = [(a, min(b, hi)) for a, b in s if b > a and off <= a < hi]; lo = len({a for a, _ in w}); up = sum(math.ceil((e - a) / gop) for a, e in w); print("кадров источника", len(sp), "энкода", len(ep), "сцен", len(s), "сцен в окне", len(w)); print("K-пакетов", len(ek), "границы [", lo, ";", up, "]", "в границах" if lo <= len(ek) <= up else "ВНЕ ГРАНИЦ"); print("scenes_reasons:", precheck.scenes_reasons(s, len(sp))); print("check_offset:", precheck.check_offset(len(sp), len(ep), off, s)[2]); print("keyframe_reasons:", precheck.keyframe_reasons(s, off, len(ep), ek))' SRC.mkv ENC_PART.mkv SRC.mkv.scenes 4737 300
  # готовая реальная пара enpipe (Gravity Falls S01E01, 233 сцены, 30325 кадров, offset 0, границы [233; не больше 333]):
  uv run python -c 'import sys, math; from pathlib import Path; from enpipe.analysis import frames, precheck; from enpipe.analysis.sources import read_scenes_file; src, enc, sc, off, gop = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]); sp, _ = frames.packet_table(src); ep, ek = frames.packet_table(enc); s = read_scenes_file(sc); hi = off + len(ep); w = [(a, min(b, hi)) for a, b in s if b > a and off <= a < hi]; lo = len({a for a, _ in w}); up = sum(math.ceil((e - a) / gop) for a, e in w); print("кадров источника", len(sp), "энкода", len(ep), "сцен", len(s), "сцен в окне", len(w)); print("K-пакетов", len(ek), "границы [", lo, ";", up, "]", "в границах" if lo <= len(ek) <= up else "ВНЕ ГРАНИЦ"); print("scenes_reasons:", precheck.scenes_reasons(s, len(sp))); print("check_offset:", precheck.check_offset(len(sp), len(ep), off, s)[2]); print("keyframe_reasons:", precheck.keyframe_reasons(s, off, len(ep), ek))' "/data/media/series/Gravity Falls/S01/Gravity.Falls.S01E01.Tourist.Trapped.1080p.BDRemux.AVC.DTS-HD.MA.5.1-tim1ch.mkv" "/data/downloads/enpipe-test/gf-s01e01/Gravity.Falls.S01E01.Tourist.Trapped.1080p.BDRemux.AVC.DTS-HD.MA.5.1-tim1ch.Encoded.mkv" "/data/downloads/enpipe-test/gf-s01e01/S01E01.scenes" 0 300
  ffprobe -v error -select_streams V:0 -show_entries packet=pts_time,flags -of csv=p=0 "/data/downloads/enpipe-test/gf-s01e01/Gravity.Falls.S01E01.Tourist.Trapped.1080p.BDRemux.AVC.DTS-HD.MA.5.1-tim1ch.Encoded.mkv" | awk -F, '$2 ~ /K/ {n++} END {print n}'
result: [pending]

## Summary

total: 11
passed: 1
issues: 8
pending: 2
skipped: 0
blocked: 0

## Gaps

- truth: "D-13: ≥2 независимых точки означает ≥2 разнесённых места файла, а не ≥2 различных кадра"
  status: resolved
  reason: "WR-04 (10-REVIEW.md): повтор точки голосует соседним кадром другой цели; ok=True при n_aligned=2 из одного места"
  severity: major
  test: 1
  fix: "окрестность ±2W вокруг занятых кадров (pair.py), разнесённый подсчёт в align.aggregate, align_retry_step > 2*align_window в AnalyzeConfig, регрессионный тест — 10-08"

- truth: "D-13: голоса «выровнено» засчитываются раздельно только при разносе ≈ 1 с (max(2W, align_retry_step // 2)), одна вспышка движения не даёт двух мест"
  status: resolved
  reason: "WR-05 (10-REVIEW.md): порог 2W лишь поднял минимальную вспышку до 8 кадров; n=165, движение 41..49 → ok=True, n_aligned=2"
  severity: major
  test: 2
  fix: "sep = max(2*align_window, align_retry_step // 2) в align.aggregate и как guard в pair._taken_frames; регрессия n=165/41..49 → undetermined; поправить docstring aggregate про окна склеек"

- truth: "Масштаб известного следствия 10-09 (пропуск повторов D-11) описан верно и закреплён тестом"
  status: resolved
  reason: "WR-06 (10-REVIEW.md): комментарий pair._taken_frames и 10-09-SUMMARY говорят «часть длин (121, 165, 189)»; фактически повторов нет на всех энкодах 49..225 кадров, а также 241 и 289"
  severity: minor
  test: 3
  fix: "поведение не менять; исправить формулировку в docstring _taken_frames (и _point_worker при необходимости) и в 10-09-SUMMARY; граничный тест: n=225 — ни одного разрешённого повтора, n=226 — есть хотя бы один"

- truth: "Обоснование масштаба в docstring pair._taken_frames и комментарии теста верно (n ≤ 197 — сдвигать некуда; 198..225, 241, 289 — пропуск по решению; диапазон без .scenes), а граничный тест проверяет реальный путь _point_worker"
  status: resolved
  reason: "WR-07/IN-10/IN-11 (10-REVIEW.md, 10-VERIFICATION.md): «сдвигать повтор некуда» неверно на 198..225, 241, 289; нет оговорки «без .scenes»; test_retries_allowed_boundary дублирует условие пропуска"
  severity: minor
  test: 4
  fix: "поведение не менять; уточнить docstring _taken_frames (и retry_frames при необходимости) и комментарий теста; переписать граничный тест через check_pair_files с Fake — 10-11"

- truth: "Утверждения docstring pair._taken_frames о покрытии окрестностями явно ограничены случаем без .scenes, а заявленная граница закреплена тестами целиком (49..224 без повторов, пример n=192 со .scenes)"
  status: resolved
  reason: "IN-12/IN-13 (10-REVIEW.md после 10-11): фразы после абзаца про .scenes читаются как общие (со .scenes на 49..197 свободные кадры есть в 8874 из 20000 раскладок); тест проверяет только n=48, 225, 226, 241, 289"
  severity: minor
  test: 5
  fix: "поведение не менять; переставить фразы docstring _taken_frames; добавить тесты из 10-REVIEW.md (IN-13): 49..224 без повторов и n=192 со .scenes → повтор 96 — 10-12"

- truth: "Каждое утверждение docstring pair._taken_frames о покрытии окрестностями ограничено длинами, на которых оно верно, а фраза о закреплении тестами называет только то, что тесты действительно проверяют"
  status: resolved
  reason: "IN-14/IN-15 (10-REVIEW.md после 10-12): «Без .scenes каждый повтор попадает в окрестность какой-либо цели» без «на этих длинах» неверно с n=226; «Числа закреплены тестами» — покрытие при n ≤ 197 и 28/44/92 свободных кадров ни один тест не проверяет"
  severity: minor
  test: 6
  fix: "поведение не менять; вернуть ограничение «на этих длинах» (IN-14); IN-15 — оператор выбрал тест-перебор test_taken_coverage_numbers из 10-REVIEW.md (n ≤ 197 покрыто, на 198..225 free(n) > 0, 225/241/289 → 28/44/92; расширение с free(198) — решение оператора 2026-10-23) и перечисление его в концовке docstring и в комментарии над граничным тестом"

- truth: "Файл со сдвигом не получает вердикт «выровнено» из-за точки, оставшейся «неопределённо» (в том числе из-за пропущенного повтора); повторы D-11 не теряются из-за чужой окрестности, если за ней есть свободный кадр"
  status: resolved
  reason: "Контрпример plan-checker при планировании 10-13: цели 0/56/112 «выровнено», 168/224 «неопределённо», сдвиг виден только на пропущенном повторе 168 → align.aggregate = aligned; посылка WR-06 (б) неверна"
  severity: major
  test: 7
  fix: "(в) aggregate: любая оставшаяся точка «неопределённо» → «неопределённо»; (а) _point_worker: повтор в окрестности taken сдвигается на первый свободный кадр; переписать docstring _taken_frames/тесты под новое поведение (включая IN-14/IN-15) — 10-13; закрыто планом 10-13 (d75f7b6), подтверждено повторным ревью и верификацией 2026-10-24"

- truth: "Верная пара без сдвига с .scenes не получает отказ только из-за склейки «неопределённо», которой нечем заменить: склейка получает обычные повторы в пределах общего лимита align_retry_max"
  status: resolved
  reason: "WR-08 (10-REVIEW.md после 10-13) и UAT тест 9: частичный энкод Young Sherlock S01E01 сцен 40..42, --offset 4737, с .scenes — отказ «неопределённые точки (кадры энкода): 75, 149» (запас 2.4/2.6 дБ < 3.0, замен нет); без .scenes — aligned 5/5"
  severity: major
  test: 8
  fix: "_point_worker: для склейки после замен (или без них) — повторы align.retry_frames(start, n, cfg, taken) остатком общего лимита align_retry_max (замены+повторы ≤ 3); регрессия на Fake: 3 сцены, склейки «неопределённо», повтор «выровнено» → aligned; повтор «сдвиг» → shift; лимит; склейка 0; docstring _point_worker и junction_replacements под новое поведение — 10-14; закрыто планами 10-14, 10-15, 10-16"

