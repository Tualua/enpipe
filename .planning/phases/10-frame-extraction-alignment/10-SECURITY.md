---
phase: "10"
slug: "frame-extraction-alignment"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-10"
---

# Phase 10 — Security

> Контракт безопасности фазы: реестр угроз, принятые риски, журнал аудита.
> Реестр собран из `<threat_model>` планов 10-01…10-21 (авторство на этапе планирования) и `## Threat Flags` в SUMMARY.
> Компонент PSNR-выравнивания (align.aggregate, `_point_worker`, junction_*, `_taken_frames`, `align_window`) удалён в 10-19 (D-24…D-28);
> угрозы, защищавшие только его, закрыты как «компонент удалён» — в `src/` и `tests/` этих имён нет.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| пути файлов оператора → argv ffprobe/ffmpeg | имена файлов произвольные; процессы только через `shared.proc` в `frames.py` | путь к файлу (недоверенный) |
| stdout/stderr ffprobe/ffmpeg → StreamInfo / pts / numpy / showinfo | вывод внешнего процесса по файлам оператора; разбор падает только `AnalysisError` | текст и сырые кадры |
| файлы оператора (src/enc/.scenes) → `check_pair_files` / `grab_frame_pair` | любые несоответствия — причины отказа, не исключение и не тихий проход | медиа, текст `.scenes` |
| CLI `--offset` + `.scenes` → окно энкода | окно [K, K + n_enc) должно совпасть с границами сцен (D-26) | целое число, текст |
| флаги ключевых кадров после mkvmerge → сверка WR-10 | источник истины о началах чанков; допущение закреплено аппаратным тестом (D-28) | флаги пакетов |
| кэш pts/флагов (JSON) → предпроверка | файл на диске может быть старого формата, испорчен или подменён | JSON |
| модель → report.json / report.md / index.html | машинный контракт фаз 11/12; причины отказа содержат имена файлов и вывод ffprobe | текст (экранируется) |
| конфиг/флаги CLI (фаза 11) → AnalyzeConfig | пороги и лимиты приходят от оператора | числа |
| scratch-скрипт замера → кэш | только чтение медиа; запись только в приватный каталог кэша 0700 | JSON |
| тест → GPU/qsvencc/mkvmerge | реальные бинарники на синтетике во временном каталоге (tier `hardware`) | синтетические медиа |

---

## Threat Register

Severity «—» — в планах 10-01…10-15 колонки severity не было.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-10-01 | DoS (память) | AnalyzeConfig.align_window | — | mitigate | компонент удалён (10-19); потолок `MAX_GRAB_FRAMES=18` (config.py), проверка в frames.py | closed |
| T-10-02 | Tampering (html) | report.render_html | — | mitigate | `_h` = html.escape, `_md_cell`; `test_refusal_html_escaped` | closed |
| T-10-03 | Elevation | test_isolation allow-list | — | mitigate | точный allow только для `enpipe/analysis/frames.py`; `test_checker_allow_does_not_cover` | closed |
| T-10-04 | Repudiation | golden report_v1.json | — | accept | см. Accepted Risks | closed |
| T-10-05 | Tampering | check_pair / check_offset | — | mitigate | все причины собираются; `test_all_reasons_collected` | closed |
| T-10-06 | Tampering | point_verdict | — | mitigate | компонент удалён; `grab_frame_pair` только при `check.ok` | closed |
| T-10-07 | DoS | offset_hints | — | mitigate | O(n) двумя указателями, лимит `OFFSET_HINTS_MAX` | closed |
| T-10-08 | Tampering | check_pair DV | — | mitigate | `_dv_reasons` первыми; `test_real_p5_dv_reason_first` | closed |
| T-10-21 | Tampering | field_order | — | mitigate | не-progressive — отказ; `test_interlaced_refused` | closed |
| T-10-22 | Tampering | pts_reasons | — | mitigate | отрицательный pts — отказ; `test_negative_pts_refused` | closed |
| T-10-09 | Tampering (инъекция имени) | frames._run | — | mitigate | argv списком через `_proc.run`, без shell | closed |
| T-10-10 | Tampering (кэш) | pts cache | — | mitigate | только JSON, версия+ключ (path,size,mtime_ns)+конечные float, tmp+os.replace | closed |
| T-10-11 | DoS (память) | grab_frames | — | mitigate | count 1..18, точная проверка длины вывода | closed |
| T-10-12 | DoS (помехи энкоду) | все вызовы | — | mitigate | nice -n 10, -threads, без hwaccel; `test_no_hw_flags`, `test_no_gpu_needed` | closed |
| T-10-13 | Info disclosure | StreamInfo.name | — | accept | см. Accepted Risks | closed |
| T-10-23 | Tampering (кэш, тот же mtime) | pts cache | — | accept | см. Accepted Risks | closed |
| T-10-14 | Tampering | check_pair_files / PairCheck.ok | — | mitigate | `ok = not reasons and verdict.ok`; `test_precheck_fail_no_grab` | closed |
| T-10-15 | DoS (память пула) | _point_worker | — | mitigate | компонент удалён; 1 кадр на сторону, `MAX_GRAB_FRAMES` | closed |
| T-10-16 | Repudiation | пул | — | mitigate | пул удалён; ошибки возвращаются данными (`grab_frame_pair`, `PairCheck`) | closed |
| T-10-17 | DoS | медиа-тест | — | mitigate | `test_no_gpu_needed` | closed |
| T-10-20 | Tampering (ослабление порога) | test_frames_media | — | mitigate | компонент удалён (10-19) | closed |
| T-10-18 | Tampering (ослабление D-17) | сверка тегов | — | mitigate | `a != b` для каждого тега, unknown — несовпадение | closed |
| T-10-19 | DoS | замер jobs 4 | — | accept | см. Accepted Risks | closed |
| T-10-24 | Info disclosure | вывод скрипта | — | accept | см. Accepted Risks | closed |
| T-10-30 | Tampering | align.aggregate | — | mitigate | компонент удалён (D-24) | closed |
| T-10-31 | Tampering | grab_frame_pair | — | mitigate | guard `not check.ok`; `test_grab_frame_pair_rejected_check` | closed |
| T-10-32 | Repudiation | _point_worker | — | mitigate | компонент удалён; `except Exception` в `grab_frame_pair` → строка ошибки | closed |
| T-10-33 | DoS (4K MemoryError) | _point_worker | — | accept | компонент удалён | closed |
| T-10-34 | Tampering (подмена номера кадра) | grab_frames | — | mitigate | `_check_decoded_pts` → AnalysisError; `test_rasl_frame_pair_error`, `test_rasl_leading_frames_refused` | closed |
| T-10-35 | Tampering (ложный отказ) | _check_decoded_pts | — | mitigate | целые pts с time_base; `test_seek_matches_framemd5` | closed |
| T-10-36 | DoS (объём stderr) | grab_frames | — | accept | см. Accepted Risks | closed |
| T-10-37 | Elevation (GPU-сессии) | argv grab | — | mitigate | без hwaccel, nice; `test_grab_no_filters_no_hw`, `test_no_gpu_needed` | closed |
| T-10-08-01 | Tampering | align.aggregate | — | mitigate | компонент удалён (10-19) | closed |
| T-10-08-02 | Tampering | окрестность _point_worker | — | mitigate | компонент удалён (10-19) | closed |
| T-10-08-03 | Tampering | align_retry_step | — | mitigate | поля удалены; `__post_init__` валидирует оставшиеся (`test_invalid_config_raises`) | closed |
| T-10-08-04 | DoS | aggregate | — | accept | компонент удалён | closed |
| T-10-09-01 | Tampering | vote_separation | — | mitigate | компонент удалён (10-19) | closed |
| T-10-09-02 | Tampering | _taken_frames | — | mitigate | компонент удалён (10-19) | closed |
| T-10-09-03 | Tampering | расхождение правил | — | mitigate | компонент удалён (10-19) | closed |
| T-10-09-04 | DoS | статичные пары | — | accept | компонент удалён | closed |
| T-10-10-01 | Tampering | docstring | — | mitigate | процессный контроль; компонент удалён | closed |
| T-10-10-02 | DoS | статичные энкоды | — | accept | компонент удалён | closed |
| T-10-10-03 | Repudiation | пометки WR-06 | — | mitigate | записаны в 10-09-SUMMARY / 10-09-PLAN | closed |
| T-10-11-01 | Tampering | docstring | — | mitigate | процессный контроль; компонент удалён | closed |
| T-10-11-02 | Repudiation | цифры в обосновании | — | mitigate | процессный контроль; компонент удалён | closed |
| T-10-12-01 | Tampering | docstring `_taken_frames` | — | mitigate | компонент удалён | closed |
| T-10-12-02 | Repudiation | цифры docstring | — | mitigate | компонент удалён | closed |
| T-10-12-03 | Tampering | ожидания test_pair | — | mitigate | компонент удалён; test_pair.py проверяет текущую логику | closed |
| T-10-13-01 | Tampering | правило (c) aggregate | — | mitigate | компонент удалён (10-19) | closed |
| T-10-13-02 | Tampering | retry_frames | — | mitigate | компонент удалён (10-19) | closed |
| T-10-13-03 | Tampering | junction_replacements | — | mitigate | компонент удалён (10-19) | closed |
| T-10-13-04 | DoS | число декодов | — | accept | компонент удалён; `check_pair_files` кадров не извлекает | closed |
| T-10-13-05 | Repudiation | дрейф docstring | — | mitigate | docstring pair.py соответствует D-24 | closed |
| T-10-14-01 | Tampering | порядок склеек | — | mitigate | компонент удалён (10-19) | closed |
| T-10-14-02 | Tampering | потеря повтора склейки | — | mitigate | компонент удалён (10-19) | closed |
| T-10-14-03 | Tampering | правило (c) aggregate | — | mitigate | компонент удалён (10-19) | closed |
| T-10-14-04 | DoS | декоды склеек | — | mitigate | компонент удалён | closed |
| T-10-14-05 | Repudiation | дрейф docstring | — | mitigate | компонент удалён | closed |
| T-10-15-01 | Tampering | junction_retry_frames | — | mitigate | компонент удалён (10-19) | closed |
| T-10-15-02 | Tampering | замена, закрывающая склейку | — | mitigate | компонент удалён (10-19) | closed |
| T-10-15-03 | Tampering | ослабление детекта сдвига | — | mitigate | компонент удалён (10-19) | closed |
| T-10-15-04 | DoS | декоды склеек | — | mitigate | компонент удалён | closed |
| T-10-15-05 | Repudiation | неоднозначность точки голоса | — | accept | компонент удалён | closed |
| T-10-38 | Tampering | junction_prev_retry_frames | high | mitigate | компонент удалён (10-19) | closed |
| T-10-39 | Tampering | одна сторона закрывает цель | high | mitigate | компонент удалён (10-19) | closed |
| T-10-40 | DoS | декоды склеек | low | mitigate | компонент удалён | closed |
| T-10-41 | Repudiation | предыдущая сцена короче шага | low | accept | компонент удалён | closed |
| T-10-42 | Tampering (устаревший .scenes) | precheck.check_pair | high | mitigate | `scenes_reasons`/`keyframe_reasons` и при K=0; `test_scenes_stale_full_encode_refused`, `test_scenes_keyframe_mismatch_refused`, `test_check_pair_full_encode_scenes_checked` | closed |
| T-10-43 | Tampering (fail-open без флагов) | check_pair | high | mitigate | `enc_keyframes is None` при непустых сценах — отказ; `test_check_pair_keyframes_missing` | closed |
| T-10-44 | Tampering (кэш keyframes) | frames cache | medium | mitigate | `_PTS_CACHE_VERSION=2`, проверка int/диапазона/возрастания; `test_pts_cache_corrupt_recomputed`, `test_pts_cache_v1_file_recomputed` | closed |
| T-10-45 | Tampering (порядок флагов) | packet_table | medium | mitigate | сортировка пар по pts; `test_packet_table_keyframes` | closed |
| T-10-46 | DoS (ложные отказы) | допущение WR-10 | medium | mitigate | текст отказа подсказывает запуск без .scenes; `test_keyframe_flags_after_mkvmerge` (D-28) | closed |
| T-10-47 | Repudiation | WR-10 | low | accept | см. Accepted Risks | closed |
| T-10-48 | Tampering (конец окна внутри сцены) | check_offset | medium | mitigate | `offset + n_enc` должен быть концом сцены; `test_offset_window_end_not_scene_end`, `test_partial_window_end_refused` | closed |
| T-10-49 | Tampering (кэш, bool как int) | _read_cache | medium | mitigate | `type(i) is not int`; `test_pts_cache_corrupt_recomputed` | closed |
| T-10-50 | Repudiation (UAT принимает ключи на каждом кадре) | границы K | low | mitigate | автотест: `lo <= K <= hi`, `len(keys) < n_enc` (test_hardware_real_media.py) | closed |
| T-10-51 | DoS (ложный отказ частичной пары) | check_offset | low | mitigate | `test_offset_window_end_on_scene_end`, `test_partial_with_offset_ok` | closed |
| T-10-SC | Tampering (supply chain) | npm/pip/cargo | high | accept | см. Accepted Risks | closed |
| T-10-52 | Tampering (offset без проверки) | check_offset | high | mitigate | D-26: `--offset` без .scenes — отказ; начало/конец — границы сцен; `test_partial_without_offset_hint`, `test_partial_with_offset_ok` | closed |
| T-10-53 | Tampering (не та пара кадров) | grab_frame_pair | medium | mitigate | guard `check.ok`, проверки диапазона, ошибки данными; `test_rasl_frame_pair_error` | closed |
| T-10-54 | Repudiation (удаление PSNR-проверки) | D-24 | low | accept | см. Accepted Risks | closed |
| T-10-55 | Tampering (схема report.json) | schema | low | mitigate | `SCHEMA_VERSION=1`, golden report_v1.json | closed |
| T-10-56 | Info disclosure | report.md/html | low | accept | см. Accepted Risks | closed |
| T-10-57 | Tampering (допущение флагов WR-10) | аппаратный тест | high | mitigate | `test_keyframe_flags_after_mkvmerge`: обе границы K и пустые `keyframe_reasons`; 1 passed на B50 2026-11-08 | closed |
| T-10-58 | DoS | tier hardware | low | accept | см. Accepted Risks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-01 | T-10-04 | schema_version 1 сохранён осознанно — report.json ещё не выпускался; смена golden видна в diff | план 10-01 | 2026-11-10 |
| AR-10-02 | T-10-13 | в модель идёт только `path.name`; абсолютный путь — лишь в локальном кэше оператора | план 10-03 | 2026-11-10 |
| AR-10-03 | T-10-23 | ключ кэша (path, size, mtime_ns) не ловит подмену с тем же размером и mtime; описано в docstring `packet_table` | план 10-03 | 2026-11-10 |
| AR-10-04 | T-10-19 | замер jobs 4 запускает оператор вручную | план 10-05 | 2026-11-10 |
| AR-10-05 | T-10-24 | вывод скрипта — только локальный терминал | план 10-05 | 2026-11-10 |
| AR-10-06 | T-10-36 | объём stderr ограничен потолком 18 кадров и обрезкой `_error_text` | план 10-07 | 2026-11-10 |
| AR-10-07 | T-10-33, T-10-08-04, T-10-09-04, T-10-10-02, T-10-13-04, T-10-15-05, T-10-41 | относились к компоненту выравнивания, удалённому в 10-19 — неактуальны | планы 10-07…10-15, 10-19 | 2026-11-10 |
| AR-10-08 | T-10-47 | устаревший .scenes, совпавший с началами GOP, не ловится — сверка «необходимая, не достаточная», описано в docstring precheck.py | план 10-17 | 2026-11-10 |
| AR-10-09 | T-10-54 | PSNR-выравнивание удалено решением оператора D-24 (10-CONTEXT.md) | оператор, 2026-11-08 | 2026-11-10 |
| AR-10-10 | T-10-56 | отчёт не раскрывает новых данных; экранирование `_h` не менялось | план 10-20 | 2026-11-10 |
| AR-10-11 | T-10-58 | tier hardware выключен по умолчанию (`addopts = -m "not hardware"`) | план 10-21 | 2026-11-10 |
| AR-10-12 | T-10-SC | планы фазы не ставят пакетов; uv.lock и pyproject.toml зависимостей не меняли | планы 10-18…10-21 | 2026-11-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-10 | 85 | 85 | 0 | gsd-security-auditor (ASVS L1, block_on high) |

Примечания аудитора (не блокируют):
- Тесты, привязанные к удалённому компоненту (`test_static_inf_is_undetermined`, `test_shift_fixture_margin` и др.), больше не существуют — соответствующие угрозы закрыты удалением компонента.
- T-10-46 и T-10-57 опираются на тест с маркером `hardware`, исключённый по умолчанию; срабатывает только с `-m hardware` (так задумано по D-28).
- Аудитор проверял наличие кода и тестов, тесты не запускал; регрессия фазы — 808 passed (10-VERIFICATION.md).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-10
