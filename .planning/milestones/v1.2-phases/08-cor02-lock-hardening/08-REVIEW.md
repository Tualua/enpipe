---
phase: 08-cor02-lock-hardening
reviewed: 2026-10-03T12:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - .devcontainer/Dockerfile
  - .gitignore
  - CLAUDE.md
  - Dockerfile
  - docker/README.md
  - scratch/gate_stress_matrix.py
  - scratch/parity_encode.py
  - scratch/probe_d02_byte_identity.py
  - src/enpipe/encoding/chunk.py
  - src/enpipe/encoding/metrics.py
  - tests/integration/_concurrency_harness.py
  - tests/integration/test_concurrency_immunity.py
  - tests/integration/test_hardware_real_media.py
  - tests/integration/test_harness_gates.py
  - tests/integration/test_qsvencc_triad_parse.py
  - tests/unit/encoding/test_chunk.py
  - tests/unit/encoding/test_metrics.py
  - tests/unit/shared/test_runtime_dockerfile.py
findings:
  critical: 1
  warning: 6
  info: 7
  total: 14
status: issues_found
---

# Фаза 08: отчёт код-ревью

**Проверено:** 2026-10-03
**Глубина:** standard (diff `7bc5e49..HEAD` плюс полные файлы для контекста)
**Файлов:** 18
**Статус:** issues_found

## Сводка

Байтовый гейт в `_concurrency_harness.run_concurrent` устроен правильно. Сравнение байтов идёт первым. Сессия без эталона получает `SWEEP_SKIPPED`, а не «чисто». Для байт-идентичной сессии с неверным числом кадров бросается исключение. При расхождении байтов диагностика ничего не бросает. Быстрый тир зелёный (`uv run pytest`: 98 passed), конвенционный чек пуст.

Найденные проблемы:

1. **Пробник D-02 выдаёт ложное «чисто».** Сессия без эталона попадает в класс `byte_identical`. Это уже случилось в закоммиченном доказательстве: `scratch/probe_d02_20261003T013801Z.log`, строка `iter 2 scene 1129 metrics=1: byte_identical`, хотя эталон 1129 с метриками не построен.
2. **Замечание из задачи подтверждено.** В `metrics.py` ssim_db строки ИТОГО считается из `ssim_all`, уже округлённого до 5 знаков. При SSIM ≥ 0.999995 это даёт `ssim_db = inf` для сжатия с потерями (воспроизведено).
3. **Регэксп метрик не принимает `-nan`.** Это то самое тихое пустое поле, которое правка в `chunk.py` должна была закрыть.
4. **Допуск `METRICS_FAILED` ничем не ограничен.** Маркер `Decoded frame count does not match` признаёт симптом потери кадров «только метриками». На r4658 (0 из 640) такой допуск уже ничего не защищает и только может спрятать регрессию.
5. **Утечка токена в лог сборки** в блоке `dovi_tool` рантайм-Dockerfile.

## Критические проблемы

### CR-01: `probe_d02` засчитывает сессию без эталона как `byte_identical` (ложное «чисто», уже попало в доказательства)

**Файл:** `scratch/probe_d02_byte_identity.py:91-95`, `:256-260`
**Проблема:** если эталон не построен (`refs.get(scene) is None`), получается `same = None`. В `_classify` проверка `same is False` не срабатывает. При `frames_ok=True` функция возвращает `"byte_identical"`, хотя байты ни с чем не сравнивались. Для варианта `metrics=True` неудачный эталон к тому же не ставит `passed = False` (строки 224-229). Значит, вердикт `D-02 PASS` может держаться на непроверенных сессиях. В реальном логе `scratch/probe_d02_20261003T013801Z.log` так и вышло: `scene 1129: эталон не построен (metrics=True)`, затем `iter 2 scene 1129 metrics=1: byte_identical` и строка таблицы `metrics=on 1129 | 1 | 1 | ...`. `--self-test` этот случай не покрывает.

Практический вред ограничен: позже был прогон матрицы 08-06 через харнесс, где сессия без эталона корректно получает `SWEEP_SKIPPED`. Но инструмент гейта выдаёт ложный вердикт, а доказательство D-02 содержит неверную точку данных. По приоритету проекта (никаких ложных «чисто») это блокер для повторного использования пробника, например при переходе на официальный 8.33.
**Исправление:**
```python
CLASSES = ("byte_identical", "byte_mismatch", "no_reference",
           "SESSION_FAILED", "METRICS_FAILED", "frames_bad")

def _classify(ok, stderr_text, metrics, same, frames_ok):
    if not ok:
        ...
    if same is None:
        return "no_reference"          # никогда не «совпало»
    if same is False:
        return "byte_mismatch"
    if frames_ok is False:
        return "frames_bad"
    return "byte_identical"
# в итоговой таблице:
if t["byte_mismatch"] or t["frames_bad"] or t["no_reference"]:
    passed = False
# self-test:
assert _classify(True, "", True, None, True) == "no_reference"
```
В логе 08-01 стоит пометить, что ячейка `metrics=on 1129` не доказана.

## Предупреждения

### WR-01: ssim_db строки ИТОГО считается из округлённого ssim_all; при SSIM ≥ 0.999995 получается ложный `inf`

**Файл:** `src/enpipe/encoding/metrics.py:43`, `:78-84`
**Проблема:** `_wmean` возвращает `_round(...)`, то есть 5 знаков, и `_ssim_db_total` применяет `-10*log10(1-SSIM)` уже к округлённому значению. Погрешность (1−SSIM) достигает ±5e-6, а в дБ это растёт к единице:
- 0.999: до ~0.02 дБ. Так получилось наблюдаемое 0.99899 → 29.95679 против per-scene 29.96021. Даже при одной сцене ИТОГО расходится со строкой сцены.
- 0.9999: до ~0.22 дБ.
- ≥ 0.999995: `round` даёт ровно `1.0`, и `_ssim_db_total` возвращает `inf`, то есть «без потерь». Воспроизведено: одна сцена с `ssim_all=0.999996` даёт ИТОГО `ssim_all=1.0, ssim_db=inf`.

Значение выходного видео это не портит, но CSV врёт. При этом докстринг модуля обещает именно математически корректный итог.
**Исправление:** округлять только на выходе:
```python
def _wmean_raw(ordered, key):
    vals = _vals(ordered, key)
    fr = sum(f for f, _ in vals)
    if not fr:
        return None
    if any(math.isnan(v) for _, v in vals):
        return float("nan")
    return sum(f * v for f, v in vals) / fr

ssim_raw = _wmean_raw(ordered, "ssim_all")
total["ssim_all"] = None if ssim_raw is None else _round(ssim_raw)
total["ssim_db"] = _ssim_db_total(ssim_raw)   # из НЕокруглённого
```
Нужен регрессионный тест на одну сцену `0.999996`: ИТОГО ssim_db должен быть конечным (≈53.98).

### WR-02: `_NUM` не принимает `-nan`/`-inf`, и строка метрик целиком тихо теряется

**Файл:** `src/enpipe/encoding/chunk.py:57`
**Проблема:** glibc печатает NaN с установленным знаковым битом как `-nan`. «Default NaN» на x86 после 0/0 как раз отрицательный. Альтернатива `(?:[\d.]+|inf|nan)` на `(-nan)` не совпадает, и весь `_SSIM_RE.search` возвращает `None`. Воспроизведено: `SSIM YUV: 1.000000 (-nan), ... All: 1.000000 (-nan)` даёт все поля `None`. Дальше `_vals` в `metrics.py` молча исключает такую сцену из ИТОГО. Получается ровно то, что комментарий на строках 54-56 обещает предотвратить: nan не всплывает и превращается в пустое поле.
**Исправление:**
```python
_NUM = r"(?:-?(?:inf|nan)|[\d.]+)"
```
`float("-nan")` и `float("-inf")` Python разбирает штатно. Добавить кейс `(-nan)` в `tests/unit/encoding/test_chunk.py`.

### WR-03: допуск `METRICS_FAILED` без порога, причём маркер «Decoded frame count does not match» считает потерю кадров отказом только метрик

**Файл:** `tests/integration/_concurrency_harness.py:477-484`, `:812-822`; `tests/integration/test_concurrency_immunity.py:109-111`, `:191-211`; `tests/integration/test_hardware_real_media.py:138-162`
**Проблема:**
- `ssim/psnr: Decoded frame count does not match original frames` значит, что число декодированных кадров выхода не совпало с входом. Это прямой симптом той самой потери кадров (236 из 240), из-за которой взят форк. Сейчас такой rc≠0 в замке становится `METRICS_FAILED` и в итог не идёт, а в аппаратном тире и parity запускает повтор. Повтор может пройти, и прерывистая потеря кадров уйдёт незамеченной.
- `allocVA` — общий маркер ошибки VA-аллокации, не обязательно связанной с метриками. Под конкурентной нагрузкой он отправит в «метрики» и обычный отказ ресурсов.
- `test_qsvencc_immune_at_production_jobs[metrics]` пройдёт и при 23 `METRICS_FAILED` из 24 при одной `ok`-сессии. Нижней границы нет.
- Списки маркеров в харнессе не согласованы: `_METRICS_FAILURE_MARKERS` использует `"VIDEOMETRIC:"`, а `_METRICS_SUBSYSTEM_FAILURES` использует `"VIDEOMETRIC: Failed"`.

Допуск был решением D-12, принятым на r4634. На r4658 измерено `METRICS_FAILED = 0 из 640` и 0 из 24+24 в замке, так что исходная предпосылка снята. Сейчас допуск только расширяет окно для ложного зелёного в варианте с метриками. Вариант без метрик это частично страхует.
**Исправление:** в замке считать `METRICS_FAILED > 0` проблемой, или хотя бы требовать `ok >= sessions - k` с малым `k`. Убрать `Decoded frame count does not match` из повторяемых маркеров в `metrics_only_failure`: такой отказ должен валить тест сразу. Свести маркеры в один кортеж и использовать его и в классификации, и в триаде.

### WR-04: блок `dovi_tool` печатает токен GitHub в лог сборки (xtrace)

**Файл:** `Dockerfile:175-184` (и аналогичный блок в `.devcontainer/Dockerfile`)
**Проблема:** `RUN ... set -eux;` и затем `set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"`. При `-x` оболочка выводит уже раскрытую команду (`+ set -- -H 'Authorization: Bearer ghp_…'`) и обе `curl`-строки с заголовком. Блок qsvencc в том же файле (строки 126-141) именно от этого защищён: в комментарии сказано «xtrace отключён… иначе токен печатается в лог сборки». Блок `dovi_tool` осталось несогласованным. В CI с `--secret` токен окажется в публичном build-логе. Проблема существовала и до фазы, но файл переписан в этой фазе.
**Исправление:**
```dockerfile
RUN --mount=type=secret,id=github_token,required=false set -eu; \
    set +x; \
    if [ -s /run/secrets/github_token ]; then set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; else set --; fi; \
    url="$(curl -fsSL "$@" https://api.github.com/... | jq -r ... | head -1)"; \
    test -n "$url"; \
    curl -fsSL "$@" -o /tmp/dovi.tgz "$url"; \
    set -x; \
    ...
```

### WR-05: порог ревизии 4634 пропускает сборки без патчей #319/#320, на которых фаза зафиксировала усечение при rc=0

**Файл:** `Dockerfile:149`, `.devcontainer/Dockerfile` (тот же `test "${rev:-0}" -ge 4634`), `src/enpipe/shared/qsvencc_version.py:36`, `tests/integration/test_concurrency_immunity.py:177-185`
**Проблема:** фаза закрепила форк `8.32+vppsync4 (r4658)` потому, что на r4634 и в апстримном 8.32 путь `--psnr/--ssim` усекал выход при rc=0 и падал с VIDEOMETRIC. Метрики при этом включены в пути по умолчанию. Но все гейты (сборка образа, рантайм-гейт QSV-02, предусловие замка) требуют только `>= 4634`. Если подменить `QSVENCC_URL` через `--build-arg` или поставить qsvencc на хост вне образа, сборка без патчей пройдёт все проверки. Вариант замка с метриками и допуском из WR-03 тоже может позеленеть. Ревизия r-числа к тому же не отличает форк от апстрима с тем же номером. Тихой порчи в проде не будет, потому что `encode_chunk`/`count_frames` поймают усечение и вызовут `die()`. Но заявленный в докстринге замка инвариант «на старой сборке замок FAILS» на деле слабее.
**Исправление:** для пути с метриками поднять минимум до 4658 (`QSVENCC_METRICS_MIN_REV = 4658`) и проверять его в замке и в аппаратном тире при `metrics=True`. В образе дополнительно сверять `dpkg-query -W -f='${Version}' qsvencc` с `8.32+vppsync4`, либо полагаться только на sha256 и запретить переопределение URL без SHA.

### WR-06: запасной ΔPSNR-гейт в `parity_encode` сравнивает несопоставимые итоги и падает на пустом `psnr_avg`

**Файл:** `scratch/parity_encode.py:309-321`
**Проблема:** legacy считает ИТОГО `psnr_avg` как frame-weighted среднее дБ, а новый `metrics.py` считает его через MSE. Формулы отличаются намеренно, это записано в докстринге `metrics.py`. Разрыв Йенсена для сцен с разным PSNR легко превышает `PSNR_EPS_DB = 0.05`: 40 и 50 дБ в пропорции 1:3 дают 47.5 против 44.88. Значит, при недетерминизме гейт выдаст ложный FAIL. Кроме того, проверяется только непустота `ssim_all`. При пустом `psnr_avg` (legacy не разбирает `inf`) `float("")` бросит `ValueError`. Путь сейчас латентный, потому что на этой машине qsvencc детерминирован, но это и есть единственная страховка на случай недетерминизма.
**Исправление:** сравнивать построчно (per-scene `psnr_avg`/`ssim_all` из обоих CSV) или пересчитывать оба итога одной функцией из per-scene строк. Явно проверять, что значения непусты и конечны, а иначе выдавать FAIL с понятным сообщением.

## Info

### IN-01: нога `(Frames: N)` в триаде вакуумна, если в строках нет `(Frames:`

**Файл:** `tests/integration/_concurrency_harness.py:716-720`
**Проблема:** `finditer` без совпадений не даёт нарушений. `parse_metrics` может найти строки SSIM/PSNR, а `_METRICS_FRAMES_RE` при изменённом формате ничего не найдёт, и проверка `Frames == expect_frames` молча пропустится.
**Исправление:** собрать `kinds = {mm.group(1) for mm in ...}` и требовать `kinds == {"SSIM", "PSNR"}`, иначе писать нарушение «Frames not reported».

### IN-02: маркеры отказа метрик продублированы в трёх местах

**Файл:** `scratch/probe_d02_byte_identity.py:53-57`, `tests/integration/_concurrency_harness.py:477-479`, `:668-672`
**Проблема:** копия кортежа в пробнике и два разных списка в харнессе (см. WR-03) со временем разойдутся.
**Исправление:** в пробнике использовать `harness.is_metrics_failure`, а в харнессе оставить один кортеж.

### IN-03: `gate_stress_matrix` даёт вакуумный PASS при пустой лестнице JOBS

**Файл:** `scratch/gate_stress_matrix.py:152`, `:339-344`
**Проблема:** при `--jobs ","` или `--jobs ""` получается `ladder = ()`, `cells` остаётся пустым, `bad_cells = []`, и итог `PASS` без единой сессии.
**Исправление:** `if not ladder: ap.error("empty JOBS ladder")`, а в вердикте добавить `passed = passed and bool(cells)`.

### IN-04: решение о повторе зависит от подстроки «ожидалось» в обрезанном сообщении `die()`

**Файл:** `tests/integration/_concurrency_harness.py:821`; `src/enpipe/encoding/pipeline.py:283-284`
**Проблема:** `die()` включает только `errors[:10]`. Если перед несовпадением кадров стоят 10 отказов метрик, слова «ожидалось» в сообщении не будет, и прогон уйдёт на повтор. Плюс жёсткая привязка к русскому тексту сообщения. В текущих тестах (4 чанка) не проявляется.
**Исправление:** для enpipe проверять кадры независимо, например сканировать `*.obu` в workdir через `count_frames`, или хотя бы задокументировать ограничение.

### IN-05: устаревшие заявления о нестабильности метрик и битая фраза в CLAUDE.md

**Файл:** `Dockerfile:63-64`, `docker/README.md` (раздел «Известная нестабильность», «до 3 повторов из-за D-12»), `CLAUDE.md:51`, `:54`
**Проблема:** на r4658 измерено 0 `METRICS_FAILED` из 640, а тексты всё ещё описывают VIDEOMETRIC как текущий дефект стека. В `CLAUDE.md` строка про qsvencc по-прежнему говорит «latest GitHub release .deb… with dependency patching (strips intel-opencl-icd/libmfx1…)», а в строке про `ocl-icd-libopencl1` не хватает связки («for VPP filters Intel's OpenCL ICD…»).
**Исправление:** обновить формулировки: метрики стабильны на форке r4658, а D-12 исторический и касается r4634/апстримного 8.32. Исправить пин qsvencc в CLAUDE.md.

### IN-06: проверка ключа PPA подтверждает наличие отпечатка, но не единственность ключа

**Файл:** `Dockerfile:86-90`
**Проблема:** `grep -q "^fpr:::::::::${FPR}:"` пройдёт и тогда, когда ответ keyserver содержит дополнительные ключи. `gpg --dearmor` запишет в keyring все ключи, и `Signed-By` будет доверять каждому из них.
**Исправление:** импортировать во временный `GNUPGHOME` и экспортировать ровно этот ключ: `gpg --import /tmp/intel-ppa.asc && gpg --export "$FPR" > /etc/apt/keyrings/...gpg`. Либо проверять, что строк `fpr:` (primary) ровно одна.

### IN-07: ИТОГО не показывает, что метрики есть не у всех сцен

**Файл:** `src/enpipe/encoding/metrics.py:31-32`, `:78-87`
**Проблема:** `_vals` отбрасывает сцены с `None`, а `frames` в ИТОГО суммирует все сцены. Средние посчитаны по подмножеству, и это никак не помечено. Вместе с WR-02 это скрывает потерю строк метрик.
**Исправление:** если есть хотя бы одна сцена без метрики, а у других она есть, ставить в ИТОГО `nan` для этой колонки (в духе пункта 4 докстринга) или выводить предупреждение в лог.

---

_Проверено: 2026-10-03_
_Ревьюер: Claude (bm-code-reviewer)_
_Глубина: standard_
