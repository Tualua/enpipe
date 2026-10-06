---
phase: 09-analysis-core-readers
verified: 2026-10-06T03:00:00Z
status: passed
score: 5/5 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
gaps:
  - truth: "Ридеры отвергают некорректный ввод, а не превращают его в кандидатов (CND-02/CND-04, контракт «parse_* не бросают»)"
    status: partial
    severity: minor
    reason: "WR-03 подтверждён прогоном: CSV с границами 0,100,50 даёт кадр 75, с -10,-4 даёт кадр -7, статус enabled. WR-01 (parse_frames бросает ValueError на 5000 цифр), WR-02 (строка с пустым start_frame молча пропускается), WR-04 (битый .scenes тихо отключает квоту). Все касаются повреждённого ввода; CSV, записанный write_metrics_csv, корректен (round-trip тест зелёный)."
    artifacts:
      - path: "src/enpipe/analysis/sources.py"
        issue: "нет проверки 0 <= start < end в parse_metrics_csv; int() без лимита длины; read_scenes_file глотает ошибки"
    missing:
      - "проверка границ сцены в parse_metrics_csv (STATE_REJECTED с номером строки)"
      - "ограничение длины числа в _FRAMES_ITEM_RE или try/except ValueError"
      - "статус/заметка для нечитаемого или пустого .scenes"
  - truth: "Константы ΔE ITP сверены со стандартом тестами (D-12, MET-04)"
    status: partial
    severity: minor
    reason: "WR-07: все опорные тесты серые (Cb=Cr=512); ошибка в цветовых строках LMS_TO_ICTCP или в KR/KB тестами не ловится. Сейчас константы верны (ревью проверило вручную), критерий 1 табличных ITP-тестов не требует."
    artifacts:
      - path: "tests/unit/analysis/test_itp.py"
        issue: "нет насыщенных опорных цветов с внешними эталонными значениями"
    missing:
      - "табличный тест ΔE ITP на 2-3 насыщенных цветах с литералами из независимой реализации"
---

# Фаза 9: Чистое ядро анализа и ридеры — отчёт верификации

**Цель фазы:** Метрики кадра, пороги, ридеры источников кандидатов и модель отчёта существуют как чистые функции без subprocess и проверяются быстрым тиром тестов на фикстурах.
**Проверено:** 2026-10-06
**Статус:** passed (есть минорные замечания, блокеров нет)
**Повторная верификация:** нет, первичная.

## Достижение цели

### Наблюдаемые истины (критерии ROADMAP)

| # | Истина | Статус | Доказательство |
|---|--------|--------|----------------|
| 1 | Метрики кадра для пары 10-бит YUV: цвет мелких деталей (медиана/p10/число блоков, при нехватке блоков «нет деталей»), PSNR Y/U/V + худший тайл, ниты/тени/деталь Y, ΔE ITP mean/p99; табличные тесты PQ и тайлинга | ✓ VERIFIED | `metrics.py` (480 строк): `tile_edges`, `psnr`, `pq_nits`, `luminance_stats`, `detail_preservation`, `luma_tiles`/`chroma_tiles`, `small_chroma` (учёт только полных блоков, статус при блоках < `min_chroma_blocks`), `delta_e_itp`, `analyze_frame`. Тесты `test_tiles.py` (таблица `tile_edges`, 2160p, склеенная последняя строка), `test_metrics.py`, `test_itp.py`, `test_core_integration.py` зелёные. Оговорка WR-07 (только серые ITP-тесты) учтена как минор. |
| 2 | Все пороги в одной конфигурации как именованные константы, отчёт помечает «provisional» | ✓ VERIFIED | `config.py`: `AnalyzeConfig` frozen с валидацией, `default_thresholds` строит `Threshold(provisional=True)` на каждое поле; `report.py:217,337` печатает «Пороги (provisional, не откалиброваны)» и «(provisional)» |
| 3 | Кандидаты из `--frames`, CSV qsvencc (`ssim_y`/`psnr_y`), VMAF (tsv/csv, десятичная запятая); при несовпадении длины/базы индекса файл отвергается с причиной | ✓ VERIFIED | `sources.py`: `parse_frames`, `parse_metrics_csv`/`csv_candidates` (середина сцены, inf/nan не берутся), `parse_vmaf`. Прогон: `frame,vmaf` с базой 1 → `rejected, «VMAF отвергнут: база индекса 1»`; строка с лишним полем → `rejected, «строка 2: число полей 2 ≠ 1»`. Тесты-сторожа round-trip с `write_metrics_csv` и формата `.scenes`. Минор: WR-01..WR-04 (см. ниже). |
| 4 | Слияние с разносом `--min-gap`, квотой на сцену, у каждого указан источник | ✓ VERIFIED | `candidates.py:merge_candidates` (приоритет ручной > VMAF > CSV > скан, ручные не выбрасываются, квота, top, детерминизм); `test_candidates.py` покрывает min_gap, квоту, приоритет, список всех источников |
| 5 | `report.md`, `index.html`, `report.json` из одной модели; `report.json` стабилен (golden-тест схемы) | ✓ VERIFIED | `model.py` (frozen), `report.py`: `render_json`/`render_md`/`render_html`; `golden/report_v1.json` и `test_golden_report_v1`, `test_render_json_schema_keys_literal`, inf/nan сериализуются; `test_full_report_renders_all_formats` зелёный |

**Оценка:** 5/5.

### Чистота и изоляция

`metrics.py`, `model.py`, `candidates.py` по грепу не импортируют subprocess и другие слои enpipe (docstring + AST-сторож `test_isolation.py`: `test_analysis_module_is_isolated`, `test_encode_path_does_not_import_analysis`). Лишних импортов `enpipe.shared`/`enpipe.encoding` в `analysis/` нет.

### Поведенческие проверки

| Проверка | Команда | Результат | Статус |
|----------|---------|-----------|--------|
| Быстрый тир | `uv run pytest -q` | 633 passed, 17 deselected | ✓ PASS |
| Линтер | `uv run ruff check src tests` | All checks passed | ✓ PASS |
| WR-03 | `parse_metrics_csv` + `csv_candidates` на `0,100,50` и `1,-10,-4` | кадры [75, -7], статус enabled | подтверждён (минор) |
| VMAF база/число полей | `parse_vmaf` на двух вариантах | оба rejected с причиной | ✓ PASS |

Probe-скриптов и `TBD/FIXME/XXX` в изменённых файлах нет.

### Покрытие требований

| Требование | Статус | Свидетельство |
|-----------|--------|---------------|
| MET-01 | ✓ SATISFIED | `small_chroma`, `ChromaDetail` |
| MET-02 | ✓ SATISFIED | `psnr`, `luma_tiles`, `chroma_tiles` |
| MET-03 | ✓ SATISFIED | `pq_nits`, `luminance_stats`, `detail_preservation` |
| MET-04 | ✓ SATISFIED | `delta_e_itp` (замечание WR-07 по тестам) |
| MET-05 | ✓ SATISFIED | `AnalyzeConfig`, `Threshold(provisional)` |
| CND-01 | ✓ SATISFIED | `parse_frames`, `manual_candidates` |
| CND-02 | ✓ SATISFIED | `csv_candidates` (кадр в сцене для корректного CSV; WR-03 минор) |
| CND-04 | ✓ SATISFIED | `parse_vmaf` |
| CND-05 | ✓ SATISFIED | `merge_candidates` |
| RPT-01 | ✓ SATISFIED | `report.py` + golden |

Все 10 ID из ROADMAP присутствуют в REQUIREMENTS.md (отмечены Complete, трассировка Phase 9). Осиротевших требований нет: CND-03 (фаза 12) и CND-06 (фаза 11) в этой фазе не заявлялись.

## Оценка замечаний 09-REVIEW.md

Ни одно из WR-01..WR-07 не ломает критерий успеха: все они касаются повреждённого или краевого ввода и тестового покрытия, а не нормального пути.

| ID | Влияние на критерии | Класс |
|----|--------------------|-------|
| WR-03 | Критерий 3/4: при корректном CSV кадр внутри сцены; повреждённый CSV даёт кадр вне `[S,E)`. Данные пишет сам enpipe (round-trip тест), риск низкий, но исправить стоит до фазы 10 (кадр уйдёт в извлечение) | минор |
| WR-07 | Критерий 1: табличных ITP-тестов критерий не требует; D-12 закреплён только серыми тестами, константы верны | минор |
| WR-01, WR-02, WR-04 | Критерий 3: нарушение «ридеры не бросают / не молчат» на патологическом вводе | минор |
| WR-05 | Конфиг с `chroma_sat_thr < 0` даёт ZeroDivisionError; дефолт безопасен | минор |
| WR-06 | `_time_text(59.999) = "0:60.00"`; косметика отчёта | минор |

Рекомендация: закрыть WR-01..WR-03, WR-05 и WR-07 до того, как фаза 10/11 начнёт пользоваться ридерами (или отдельным мелким планом), остальное в бэклог.

## Замечание о правке теста в 09-03

Исполнитель убрал из теста `test_csv_candidates_middle_and_tags` ожидание `notes` для `unavailable`. Сверка с планом: must_haves 09-03 требуют для обеих пустых колонок `STATE_UNAVAILABLE` с `reason="колонки ssim_y и psnr_y пусты — метрики не считались"`, notes для этого случая не требуются. Код соответствует (`sources.py:238-243`), а тест `test_csv_candidates_all_empty_unavailable` проверяет state и reason. Заметка «нет конечных значений» проверяется для случая enabled (строки 221, 229). Отклонения от must_haves нет.

## Человеческая верификация

Не требуется: фаза не содержит запускаемых путей и внешних сервисов. Визуальный осмотр `index.html` желателен позже, на реальных данных (фаза 11+), но в критерии фазы не входит.

## Итог

Цель фазы достигнута: чистое ядро (метрики, пороги, ридеры, слияние, модель и рендеры отчёта) существует, изолировано от subprocess и закрыто быстрым тиром (633 passed, ruff чист). Блокирующих пробелов нет, минорные пробелы (WR-01..WR-07) перечислены в frontmatter.

---

_Проверено: 2026-10-06_
_Верификатор: Claude (bm-verifier)_
