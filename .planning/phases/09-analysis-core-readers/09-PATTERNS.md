# Фаза 9: Чистое ядро анализа и ридеры - Карта паттернов

**Составлено:** 2026-10-05
**Файлов проанализировано:** 15 (новые; существующие не меняются)
**Аналоги найдены:** 13 / 15 (2 частичных; у golden-json и numpy-метрик аналога нет, берётся прототип)

## Классификация файлов

| Новый файл | Роль | Поток данных | Ближайший аналог | Качество |
|------------|------|--------------|------------------|----------|
| `src/enpipe/analysis/__init__.py` | пакет | - | `src/enpipe/encoding/__init__.py` (пустой, 0 байт) | exact |
| `src/enpipe/analysis/config.py` | config/model | transform | `src/enpipe/detection/config.py` | exact |
| `src/enpipe/analysis/metrics.py` | utility (чистый numpy) | transform | прототип `vmaf_frames.prototype.py` (стр. 144-209) + `mkv/ebml.py` (чистота) | exact (порт) |
| `src/enpipe/analysis/sources.py` | utility (парсеры) | file-I/O (текст -> модель) | `encoding/scenes_io.py` + `encoding/keyframes.py` (тонкая I/O-обёртка над чистым парсером) | role-match |
| `src/enpipe/analysis/candidates.py` | utility | transform | прототип `pick_worst` (стр. 70-77) + `encoding/pipeline.py:contiguous_run` (чистый помощник) | role-match |
| `src/enpipe/analysis/report.py` | model/renderer | transform | прототип `main` (стр. 318-361, md/html) + `encoding/metrics.py` (inf/nan, `_fmt`) | partial |
| `tests/unit/analysis/test_metrics.py` | test | transform | `tests/unit/encoding/test_metrics.py` | role-match |
| `tests/unit/analysis/test_tiles.py` | test | transform | `tests/unit/mkv/test_ebml.py` (табличные граничные случаи) | role-match |
| `tests/unit/analysis/test_sources.py` | test | file-I/O | `tests/unit/encoding/test_scenes_io.py`, `test_metrics.py` (round-trip через `tmp_path`) | role-match |
| `tests/unit/analysis/test_candidates.py` | test | transform | `tests/unit/encoding/test_pipeline_ordering.py` | role-match |
| `tests/unit/analysis/test_report.py` | test | transform | `tests/unit/encoding/test_metrics.py` | partial |
| `tests/unit/analysis/golden/report_v1.json` | fixture | - | `tests/fixtures/` | нет аналога |

Неизменяемые: `encoding/`, `detection/`, `mkv/`, `pyproject.toml`, `uv.lock`.

## Назначение паттернов

### `src/enpipe/analysis/config.py` (config/model, transform)

**Аналог:** `src/enpipe/detection/config.py`

**Заголовок и импорты** (стр. 1-13): подробный русский docstring модуля «зачем», затем `from __future__ import annotations`, `dataclass`, `typing` (Optional/List/Tuple, НЕ `list[...]`).

**Исключение** (стр. 16-17):
```python
class SceneDetectionError(RuntimeError):
    """Ошибка этапа детектирования сцен (ffprobe/ffmpeg/пайп)."""
```
Для analysis: `class AnalysisError(RuntimeError): """Ошибка этапа анализа (программная: неверный dtype/форма)."""`. Для плохих ВХОДНЫХ данных (CSV/VMAF/`--frames`) исключение не бросать, а возвращать статус источника.

**Frozen-конфиг с комментарием на поле** (стр. 25-47):
```python
@dataclass(frozen=True)
class DetectionConfig:
    # Геометрия анализа: ... (комментарий «почему» над полем)
    analysis_width: int = 320
    min_scene_len_frames: Optional[int] = 72  # ≈ 3с при 24fps
```
`AnalyzeConfig`: поля `chroma_block=16`, `sat_thr=30`, `min_pts=3`, `max_pts=20`, `min_chroma_blocks=5`, `tile_y=256`, `tile_c=128`, `shadow_nits=5.0`, `min_gap=48`, `top=40`, `per_scene_quota=2`, `max_frames_range=10000`. Никаких модульных GRID_X/GRID_Y/CHROMA_B (прототип стр. 35, 165). Константы ITP/PQ (`LUMA_BLACK=64`, `LUMA_RANGE=876`, `CHROMA_MID=512`, `CHROMA_RANGE=896`, `KR=0.2627`, `KB=0.0593`) - именованные модульные константы с префиксом UPPER_CASE.

**Value-объекты с @property** (стр. 58-70): `Scene.frame_count` - образец для `ChromaDetail`, `SourceStatus` и т.п. Кадры 0-based, end исключительно.

**Разделитель секций** (стр. 20-22): `# ---... #` / заголовок / `# ---... #`.

---

### `src/enpipe/analysis/metrics.py` (utility, transform)

**Аналог:** прототип `.planning/phases/09-analysis-core-readers/vmaf_frames.prototype.py`

**Что портируем дословно по смыслу:**

PSNR (стр. 145-147), uint16 -> float64 до вычитания, пик 1023, inf при mse == 0:
```python
def psnr(a, b) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * math.log10(1023.0 ** 2 / mse)
```

PQ EOTF (стр. 150-155):
```python
e = np.clip((code.astype(np.float64) - 64) / 876.0, 0, 1)
m1, m2, c1, c2, c3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875
p = e ** (1 / m2)
return 10000 * (np.maximum(p - c1, 0) / (c2 - c3 * p)) ** (1 / m1)
```
Табличный тест: 64->0.0, 100->0.03875, 300->6.7323, 940->10000.0 (RESEARCH, Code Examples).

Лапласиан (стр. 158-162): `4*f[1:-1,1:-1] - соседи`, `mean(abs)`. Добавить защиту `h<3 or w<3 -> None` и `max(src, 1e-9)`; тайлы с `lap(src) < eps` исключать из минимума.

`small_chroma` (стр. 168-195): блоки по `range(0, H-B+1, B)`, маска `sat > 30`, `3 <= m.sum() <= 20`, проекция `(s*e).sum()/(s*s).sum()`, координаты `x*2, y*2` (пиксели Y). Отличия от прототипа по решениям: (1) при `n < min_chroma_blocks` -> `ChromaDetail(status="no_details", n_blocks=n, значения None)`, а НЕ nan и НЕ числа при 1..4 (D-03); (2) добавить `ratio = Σ(s·e)/Σ(s·s)` по всем блокам (D-02); (3) без клипа (D-04); (4) параметры из `cfg`, не глобалы; (5) считать только полные блоки (A4) - иначе не воспроизвести приёмочные 71->88 %. Можно векторизовать отбор через `reshape(hb, B, wb, B)` и `m.sum(axis=(1,3))`, цикл только по отобранным.

`tile_psnr` (стр. 198-209) заменить на `tile_edges` из RESEARCH Pattern 2 (фиксированные пиксельные тайлы, остаток < tile/2 приклеивается). Сетки Y и UV считать независимо, координаты UV в json умножать на 2. Худший цветной тайл - по сумме MSE U+V (D-09).

**Чистота (аналог `mkv/ebml.py`):** вход - numpy-массивы, выход - frozen dataclass/числа, ни `subprocess`, ни `die()`, ни `log()` (CLAUDE.md: только `from enpipe.shared import ...` в I/O-слое, здесь он не нужен). Нет `np.frombuffer` view в сохраняемых результатах - только Python-числа.

**Валидация формы:** при `u.shape != (ceil(h/2), ceil(w/2))` - `raise AnalysisError` (программная ошибка вызывающего).

**ΔE ITP:** аналога в кодовой базе нет, формулы и константы - RESEARCH Pattern 4; считать полосами по 128 строк.

---

### `src/enpipe/analysis/sources.py` (utility, file-I/O)

**Аналог:** `src/enpipe/encoding/scenes_io.py` + `src/enpipe/encoding/keyframes.py` (чистый разбор + тонкая обёртка).

**Свой regex `.scenes`** (scenes_io.py стр. 16) - скопировать ТОЧНО, тест-сторож сравнивает `.pattern`:
```python
_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")
```
НЕ вызывать `read_scenes` (стр. 19-27): он делает `die()` на пустом результате, а ядро `die()` не использует. Образец ядра - `parse_scenes(text) -> List[Tuple[int,int]]`: `for line in text.splitlines(): m = RE.search(line); if m: out.append((int(m.group(1)), int(m.group(2))))` (стр. 21-24), без die.

**Разделение «чистый парсер / тонкая I/O»** (keyframes.py стр. 14-17, 27-34): модульный docstring фиксирует «X - чистый, Y - тонкая I/O-обёртка»; парсеры принимают `str`/итератор строк (`parse_metrics_csv(text)`, `parse_vmaf(text, expected_frames)`), а `read_*(path)` открывают файл (`encoding="utf-8-sig"` для BOM, `newline=""`) и вызывают парсер.

**Формат CSV qsvencc** (`encoding/metrics.py` стр. 88-116): колонки `scene,start_frame,end_frame,frames,seek,trim,encode_sec,fps,size_mb,ssim_all,ssim_db,psnr_avg,ssim_y,psnr_y`; итоговая строка `scene == "ИТОГО"` с пустыми `start_frame/end_frame`; `csv.DictWriter` пишет `inf`/`nan` как есть, `None` как пустую строку. Ридер: `csv.DictReader`, пропуск ИТОГО (`row["scene"].strip() == "ИТОГО"` или пустой `start_frame`), `float()` в try, `nan`/пусто исключаются из топа, `inf` - в конец (идентичные). Середина сцены `start + (end - start)//2`.

**Образец ридера VMAF** - прототип стр. 39-51:
```python
with path.open(newline="") as f:
    sample = f.read(4096); f.seek(0)
    delim = "\t" if "\t" in sample else ","
    rd = csv.reader(f, delimiter=delim)
    hdr = next(rd)
    col = [h.strip().lower() for h in hdr].index("vmaf")
    ... float(row[col].replace(",", "."))
```
Доработки (D-17): не падать (`.index` бросает ValueError) - вернуть `(None, SourceStatus("rejected", причина))`; проверка длины против `expected_frames` и базы индекса колонки кадра; без автосдвига.

**Паттерн ошибок:** `(result, err)`/статус вместо исключения - CLAUDE.md «Worker functions ... return `Tuple[bool, Optional[str]]`» (образец: `encoding/audio.py:21-25`).

**`parse_frames`:** `"100,200-210,300"` -> отсортированный список без дубликатов; ограничение диапазона `cfg.max_frames_range`; мусор -> статус «отвергнут».

---

### `src/enpipe/analysis/candidates.py` (utility, transform)

**Аналог:** прототип `pick_worst` (стр. 70-77) и `pipeline.py:contiguous_run` (чистая функция списков, `src/enpipe/encoding/pipeline.py:45`).

**Ядро разноса** (прототип стр. 70-77):
```python
def pick_worst(v, n, gap):
    chosen = []
    for k in sorted(range(len(v)), key=v.__getitem__):
        if all(abs(k - c) >= gap for c in chosen):
            chosen.append(k)
            if len(chosen) == n: break
    return sorted(chosen)
```
Граница `abs(a-b) >= gap` разрешена (сохранить, закрепить тестом). Для CND-05 расширить: ключ сортировки `(priority, rank, frame)` для детерминизма; коллизии - слияние источников в ближайший выбранный; ручные первыми и никогда не выбрасываются; квота не расходуется ручными; `bisect` по началам сцен для номера сцены (кадр вне сцен -> `scene=None`). Приоритет: ручной(0) < VMAF(1) < CSV(2) < скан(3). Возврат отсортирован по кадру.

Сцена по кадру в прототипе (стр. 303): `next((i for i,(s,e) in enumerate(scenes) if s <= k < e), None)` - семантика `[S,E)`; в ядре заменить на `bisect`.

Кортежи `Tuple[int, int]` для границ сцен (CLAUDE.md: лёгкие внутренние пары - кортежи, dataclass только для публичных значений -> `Candidate` dataclass).

---

### `src/enpipe/analysis/report.py` (model/renderer, transform)

**Аналог:** прототип стр. 318-361 (md/html) + `encoding/metrics.py` (обработка inf/nan/None).

**Форматирование с None -> «н/д»** (`encoding/metrics.py` стр. 119-123):
```python
def _fmt(value, spec: str, suffix: str = "") -> str:
    if value is None:
        return "н/д"
    return format(value, spec) + suffix
```
Использовать для md/html; inf/nan печатаются как есть в тексте, но в JSON нормализуются (`inf`->`"inf"`, `nan`->`null`) ровно в одной функции `to_jsonable`.

**Округление только на выходе** (metrics.py стр. 30-32):
```python
def _round(v: float) -> float:
    return round(v, 5) if math.isfinite(v) else v
```

**md/html из прототипа:** таблица md - строки `"| ... |"` через `"\n".join(md) + "\n"` (стр. 323-332); html - `html.escape(...)` на пользовательских строках (стр. 344-345), `<meta charset=utf-8>` (стр. 354). Прототип экранирует не всё (`r['tile']`, имена файлов `a.src.name` в md без экранирования) - в ядре экранировать ВСЕ пользовательские строки через `html.escape(s, quote=True)`; тест на имя `a&b "x" <i>.mkv`.

**JSON:** `json.dumps(to_jsonable(report), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"`; numpy-скаляры -> Python; `schema_version: 1` в корне. Список порогов строится из `dataclasses.fields(AnalyzeConfig)`.

---

### Тесты `tests/unit/analysis/*`

**Аналог:** `tests/unit/encoding/test_metrics.py`

**Заголовок/импорты** (стр. 1-9): русский docstring с маркером требования (`"""MET-01 (чистая логика): ... Без subprocess/hardware."""`), `from __future__ import annotations`, абсолютные импорты `from enpipe.analysis.metrics import ...`.

**Хелпер-строитель + `tmp_path`** (стр. 12-34): `_row(...)` с keyword-only необязательными полями; тесты `def test_<что>_<условие>(tmp_path):`. Round-trip сторож CSV: собрать `rows` через `_row`-подобный хелпер -> `write_metrics_csv(tmp_path/"m.csv", rows)` -> `parse`; импорт `enpipe.encoding.metrics` и `enpipe.encoding.scenes_io._SCENE_RE` допустим ТОЛЬКО в тестах (в `analysis` - нет).

**Табличные граничные тесты** - `tests/unit/mkv/test_ebml.py` (Case A..G, docstring со списком кейсов): образец для `tile_edges` (1600, 3840, 2160, 1080, `n<tile`, rem == tile/2) через `pytest.mark.parametrize`.

**Организация:** каталог `tests/unit/analysis/`; `tests/unit/encoding/` и `tests/unit/shared/` без `__init__.py` (только `mkv/` его имеет, из-за относительного импорта `from . import _ebml_builder as b`). Для analysis `__init__.py` не нужен; режим `--import-mode=importlib` в `pyproject.toml`. Golden читать через `Path(__file__).parent / "golden" / "report_v1.json"`, `read_bytes()`.

**Автофикстура:** `tests/unit/conftest.py` (`_stub_qsvencc_gate`, autouse) применяется ко всем тестам и безвредна; импортирует `cli.main` и `encoding.pipeline`.

---

## Общие паттерны

### Шапка модуля
**Источник:** `src/enpipe/detection/config.py:1-11`, `src/enpipe/encoding/scenes_io.py:1-12`
**Применять:** ко всем модулям `analysis/` и тестам. Многострочный русский docstring «зачем» + `from __future__ import annotations` + stdlib, затем сторонние (`numpy as np`), затем `enpipe.*` (абсолютные импорты `from enpipe...`; относительные только для циклов - в `analysis` не нужны).

### Типизация
`typing.List/Optional/Tuple/Dict/Union`, не `list[...]`/`X | None` (CLAUDE.md). `Optional[float]` вместо nan для «нет данных».

### Frozen-датаклассы
`@dataclass(frozen=True)` для конфига и значений, `@property` для вычисляемых полей (`detection/config.py:25-70`). Имена полей = ключи `report.json` (D-18).

### Обработка ошибок
Ядро не вызывает `die()`/`log()` и не использует `subprocess`; плохие входы -> статус источника (`(result, status)`), программные ошибки -> `AnalysisError`. Образец контракта «не бросать»: `encoding/audio.py:21-25`.

### Именование
`snake_case` модулей, глаголы-первыми для функций, `_`-префикс для помощников и приватных констант (`_SCENE_RE`, `_round`, `_fmt`), `UPPER_CASE` для констант. Все комментарии/docstring/сообщения по-русски, идентификаторы по-английски. Секции файла - баннеры `# ---- #`.

### Линт
ruff `F`, `E9` (`uv run ruff check src tests`); без новых зависимостей, `pyproject.toml`/`uv.lock` не меняются.

## Конвенции (производные)

Запуск `verify conventions --derive --scope src/enpipe` (JS-ориентированный модуль; на питоновском дереве точность низкая, оси export/import-style - `insufficient-data`):

| Ось | Доминанта | Доля | Энтропия | Статус |
|-----|-----------|------|----------|--------|
| имена файлов | camel* (по факту односложный/`snake_case`, см. CLAUDE.md) | 80 % | 0.58 | named contract (*артефакт классификатора: файлы `config.py`, `metrics.py` - lowercase snake_case) |
| регистр идентификаторов | Pascal (5 образцов) | - | - | insufficient-data |
| стиль экспорта | - | - | - | insufficient-data |
| стиль импорта | absolute | 72 % (13/18) | 0.85 | named contract (py-import-relativity; wildcard: explicit 100 %) |

**Спорные места (выбор автора):** CJS<->SDK dual resolver (`bin/lib/**` - CJS `module.exports`/`require`; `sdk/src/**` - ESM `export`/`import`) - прототип намеренного contested-раздела: каждая половина внутренне согласована по каталогам и спорна только по репозиторию. К этому репозиторию (enpipe, чистый Python) не относится; для `analysis/` следовать локальному стилю соседних пакетов: абсолютные `from enpipe...` импорты, явные имена (без `*`), `snake_case`.

## Аналога нет

| Файл | Роль | Поток | Причина |
|------|------|-------|---------|
| `analysis/metrics.py::delta_e_itp` | utility | transform | В репозитории нет цветовых преобразований; брать RESEARCH Pattern 4 (BT.2020 YCbCr -> R'G'B' -> PQ EOTF -> LMS -> ICtCp, множитель 720) |
| `tests/unit/analysis/golden/report_v1.json` | fixture | - | Golden-файлов в `tests/` нет; `tests/fixtures/` для медиа. Положить рядом с тестом, сравнивать побайтно (D-21) |
| `analysis/report.py::to_jsonable` | utility | transform | Нет сериализации dataclass в JSON; использовать `dataclasses.asdict` + нормализатор inf/nan/numpy-скаляров (RESEARCH Pattern 8) |

## Метаданные

**Область поиска аналогов:** `src/enpipe/{detection,encoding,mkv,shared,cli}`, `tests/unit/{encoding,mkv,shared}`, прототип фазы
**Просканировано файлов:** ~14
**Дата извлечения:** 2026-10-05
