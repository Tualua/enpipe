---
phase: 08-cor02-lock-hardening
verified: 2026-10-03T12:00:00Z
status: passed
score: 6/6 roadmap-критериев и 31/31 must-have truths планов подтверждены (D-01..D-14 покрыты)
has_blocking_gaps: false
overrides_applied: 0
re_verification: нет (первичная верификация)
gaps:
  - truth: "Пробник D-02 не должен засчитывать сессию без эталона как byte_identical (REVIEW CR-01)"
    status: partial
    severity: minor
    reason: "Ячейка metrics=on / сцена 1129 в 08-01 не сверена побайтно. Позднее перекрыта матрицей 08-06 (эталон 1129 on построен, sha256 совпал с off, 160+60+100 сессий on без расхождений). Сам пробник одноразовый и в замок не входит."
    artifacts:
      - path: "scratch/probe_d02_byte_identity.py"
        issue: "_classify: same is None -> byte_identical; нет класса no_reference"
    missing:
      - "Класс no_reference и passed=False при его появлении, self-test на этот случай (до повторного использования пробника)"
  - truth: "Допуск METRICS_FAILED не ослабляет замок (REVIEW WR-03)"
    status: partial
    severity: minor
    reason: "Замок не имеет нижней границы по ok/METRICS_FAILED, кроме ok>0; маркер 'Decoded frame count does not match' повторяем. Корень (потеря кадров/VIDEOMETRIC) на r4658 не наблюдается: 0 METRICS_FAILED из 688 сессий. Порчу данных это не маскирует: rc=0 сессии всегда идут через побайтный гейт, rc!=0 не дают выход."
    artifacts:
      - path: "tests/integration/_concurrency_harness.py"
        issue: "_METRICS_FAILURE_MARKERS / _METRICS_SUBSYSTEM_FAILURES рассогласованы, 'Decoded frame count...' и 'allocVA' повторяемы"
    missing:
      - "Ужесточить: METRICS_FAILED > 0 на r4658 считать проблемой замка или ввести малый k; убрать 'Decoded frame count' из повторяемых маркеров; свести маркеры в один кортеж (WR-03/IN-02 ревью)"
  - truth: "Документация не содержит устаревших утверждений о trixie/метриках (план 08-02, truth 6)"
    status: partial
    severity: minor
    reason: "Dockerfile и docker/README.md очищены от 'используйте --no-metrics как обход OpenCL', но в CLAUDE.md (строки 26, 32, 37, 51, 52, 83) остаются упоминания Debian trixie / glibc 2.39 как причины выбора, а docker/README.md:77 и Dockerfile:63-64 описывают VIDEOMETRIC как текущий дефект (REVIEW IN-05)."
    artifacts:
      - path: "CLAUDE.md"
        issue: "секция Technology Stack описывает девконтейнер как Debian trixie (девконтейнер на Ubuntu 24.04), пин qsvencc устарел"
    missing:
      - "Обновить CLAUDE.md и формулировки о нестабильности метрик (исторический D-12, r4634/апстрим 8.32)"
deferred: []
---

# Фаза 8: Усиление замка COR-02 — отчёт верификации

**Цель фазы (ROADMAP):** закрыть пробелы верификации фазы 7 (WR-01..03): (1) триада assert_qsvencc_triad на каждой сессии и эталонах; (2) проверка порчи не пропускает кадр: packets == decoded == scene.frames, побайтный критерий вместо PSNR 30 дБ; (3) замок и стресс-матрица гоняют и путь с `--psnr --ssim` (metrics=True) конкурентно. Плюс D-06/D-07: рантайм-образ на ubuntu:24.04 + Intel PPA с OpenCL, проверен на хосте.
**Верифицировано:** 2026-10-03
**Статус:** passed
**Повторная верификация:** нет

**Важно про требования:** ID требований у фазы «TBD». В `.planning/REQUIREMENTS.md` ID для фазы 8 отсутствуют; покрытие сверялось с решениями D-01..D-14 из `08-CONTEXT.md`, а не с REQUIREMENTS.md.

**Контекст бинаря:** планы писались под qsvencc r4634. До 08-06 quick 261003-8qq (97be1a3, 6f54fe9) перевёл оба Dockerfile и установленный бинарь на форк 8.32+vppsync4 (r4658). Критерий «(r4634)» читается как «закреплённый бинарь под тестом, ревизия ≥ r4634»; r4658 удовлетворяет. Доказательства сняты на r4658, подмена записана в 08-02 и 08-06 как отклонение. Эталоны фаз 7/08-01 сняты на r4634; изолированные эталоны харнесс строит сам при каждом прогоне.

## Достижение цели

### Наблюдаемые truths (roadmap + PLAN must_haves)

| # | Truth | Статус | Доказательство |
|---|-------|--------|----------------|
| 1 | (WR-01, D-08) Триада проверяется на каждой rc=0 сессии и на каждом эталоне | VERIFIED | `run_concurrent` вызывает `triad_for(...)` для каждой rc=0 сессии с эталоном (harness ~строка 372); `_run_immunity` вызывает `reference_triad_violations` для эталонов и копит `(metrics, iter, job, scene, reason)`; матрица печатает «triad intact on every ok session and reference: True», «0 violation(s)». Лог замка: `triad_violations=0` при 24 ok × 2 варианта |
| 2 | (WR-02, D-01) Критерий «чисто» = побайтное равенство (sha256) с эталоном того же argv; PSNR-свип только диагностика | VERIFIED | `same_bytes`/`sha256_file` вычисляются первыми, до всего, что может бросить; при расхождении `byte_identical=False`, свип в `diag`. Порог 30 дБ в замке не гейт. 08-01: 9/9 сессий off побайтно равны эталону (D-02 PASS) |
| 3 | (WR-02, D-03) Сверка packets == decoded == scene.frames; несовпадение не даёт «чисто» | VERIFIED с оговоркой | `verify_frames` (count_frames == ffprobe `nb_read_frames` с пустым stderr == scene.frames); для идентичной сессии при несовпадении `HarnessError` с повторной сверкой эталона, для отличной уходит в diag, исход остаётся byte_mismatch. Отклонение от буквы D-03: `-xerror` и счёт строк PSNR только в диагностическом `sweep_chunk` (обоснование в 08-03: на ffmpeg 6.1.1 `-xerror` даёт rc=0 на битом пакете). Цель D-03 сохранена; зафиксировано планом |
| 4 | (WR-03, D-04) Замок параметризован `metrics=[False, True]`, JOBS=3 × IMMUNITY_ITERS=8 по варианту, argv из `chunk_command(..., metrics=...)` | VERIFIED | `@pytest.mark.parametrize("metrics", [False, True], ids=["no-metrics","metrics"])`; `_build_command`/`qsvencc_command` передают `metrics=metrics`. Железо: `2 passed` (332 с) |
| 5 | (D-05) У каждого варианта свой изолированный эталон; результат on/off записан | VERIFIED | `build_isolated_reference(backend, workdir, metrics)`; матрица печатает D-05 для 923/928/1129: эталоны on и off идентичны (sha256 в логе и SUMMARY) |
| 6 | (D-09) 4-я нога триады: метрики реально посчитаны (SSIM/PSNR через `parse_metrics`, `Frames:` == scene.frames, нет `VIDEOMETRIC: Failed`) | VERIFIED | `assert_qsvencc_triad(..., metrics, expect_frames)`, `_METRICS_FRAMES_RE`; fast-tier `test_qsvencc_triad_parse.py`; 0 нарушений на 328 ok-сессиях с метриками (замок 24 + матрица 320 + ref) означает, что строки метрик присутствовали |
| 7 | (D-12, D-13) METRICS_FAILED — отдельный исход; эталон с метриками до 5 попыток | VERIFIED | `METRICS_FAILED`, `REF_MAX_ATTEMPTS_METRICS = 5`; fast-tier тесты гейтов. Замечание WR-03 ниже (minor) |
| 8 | (D-10a) Замок на пинованном бинаре в обоих вариантах | VERIFIED | `/tmp/enpipe-phase8/logs/lock_20261003T063157Z.out`: 2 passed; sessions=24 ok=24 byte_mismatch=0 triad=0 failed=0 в каждом варианте; бинарь r4658 |
| 9 | (D-10b, WR-03) Стресс-матрица JOBS 3/5/8 × 20 × оба варианта, 640 сессий: 0 расхождений, 0 нарушений триады, 0 SESSION_FAILED | VERIFIED | `scratch/gate_stress_matrix_20261003T063808Z.log`: 6 ячеек, ok 60/100/160 по варианту, всё по нулям, skipped 0, вердикт PASS, без HARNESS ERROR |
| 10 | (D-10c) Непустота: тот же харнесс на r4604 (strip_backend) даёт byte_mismatch > 0 | VERIFIED | `scratch/gate_stress_matrix_20261003T062807Z.log`: «corruption reproduced (byte mismatches 3 > 0): True», PASS; sha256-проверка .deb до распаковки записана в SUMMARY/debug. Нарушения триады на r4604 («Backend qsv not confirmed») ожидаемы для `--expect corrupt` |
| 11 | (D-10d) Аппаратный тир и паритет с legacy идут с метриками | VERIFIED | `hwtier_*.out`: 7 passed, 2 skipped (HDR10+/DV без фикстур); `parity_*.out`: PARITY OK, movie.obu побайтно идентичен, попытки 1/1/1. `METRICS_UNAVAILABLE` в коде не найден. Сужение D-10d (test_hdr10plus/dv/run_parity без метрик) обосновано в 08-05, принято |
| 12 | (D-06) Корневой Dockerfile на `ubuntu:24.04` + PPA kobuk-team с закреплённым отпечатком ключа, остальное содержимое сохранено | VERIFIED | `Dockerfile`: `FROM ubuntu:24.04` в обеих стадиях, `INTEL_PPA_KEY_FPR=0C0E6AF9…`, deb822 `.sources`, `intel-opencl-icd`, `ocl-icd-libopencl1`, `clinfo`; страж `tests/unit/shared/test_runtime_dockerfile.py` + sync-тест порога в fast-tier |
| 13 | (D-07, D-14) Самопроверка при сборке + человеческий чекпоинт на хосте | VERIFIED (человеческое доказательство принято) | В Dockerfile: `test -s /etc/OpenCL/vendors/intel.icd`, путь библиотеки из ICD, `qsvencc --version`. 08-02-SUMMARY: хост NAS, rootless Podman, самопроверка прошла, `clinfo -l` видит Arc A380, `enpipe run` с метриками с 1-й попытки rc=0 и CSV с ИТОГО SSIM/PSNR. Выполнено пользователем, принято по условию задачи |
| 14 | (D-11) Доказательства (uname, iHD, opencl-icd, qsvencc, счётчики, D-05) в SUMMARY и в debug-записи | VERIFIED | `.planning/debug/scene-chunk-frame-mismatch.md` раздел «ФАЗА 8: ЗАМОК УСИЛЕН» со всеми полями; идентично 08-06-SUMMARY |
| 15 | (D-12) Продакшен-дефект метрик заведён в бэклог, `src/` не правился фазой | VERIFIED | `### Phase 999.4` в ROADMAP, `.planning/phases/999.4-…/.gitkeep`. Изменения `src/enpipe/encoding/{chunk,metrics}.py` относятся к quick 261003-8fs, а не к планам фазы (отмечено в 08-06) |

**Счёт:** все 15 групп truths (покрывают 31 пункт must_haves шести планов) VERIFIED; 3 minor-замечания не нарушают цели.

### Покрытие решений D-01..D-14 (вместо REQUIREMENTS.md)

| Решения | План(ы) | Статус |
|---------|---------|--------|
| D-01, D-03 | 08-03 | SATISFIED (оговорка про `-xerror` выше) |
| D-02 | 08-01 | SATISFIED (стоп-гейт PASS, 9/9 off) |
| D-04, D-05 | 08-03, 08-04, 08-06 | SATISFIED |
| D-06, D-07, D-14 | 08-02 | SATISFIED (чекпоинт на Podman вместо docker, на r4658) |
| D-08, D-09 | 08-03, 08-04 | SATISFIED |
| D-10 (a-d), D-11 | 08-04..08-06 | SATISFIED |
| D-12, D-13 | 08-03, 08-05, 08-06 | SATISFIED (метрики стабильны на r4658: 0 отказов) |

Осиротевших (orphaned) требований нет: REQUIREMENTS.md этой фазе ID не назначает.

### Ключевые связи

| От | К | Статус |
|----|---|--------|
| `run_concurrent` -> `same_bytes`/`verify_frames`/`triad_for`/`sweep_chunk` | порядок: same_bytes первым | WIRED (прочитан код) |
| `assert_qsvencc_triad` -> `parse_metrics` | наличие ssim_all/psnr_avg | WIRED |
| `qsvencc_command` -> `chunk_command(metrics=metrics)` | продакшен-argv | WIRED |
| `_run_immunity` -> `run_concurrent(..., metrics)` / `reference_triad_violations` | замок | WIRED, `HarnessError` не перехватывается |
| `gate_stress_matrix` -> `build_isolated_reference(..., metrics)` | эталон на вариант | WIRED (в логе два блока эталонов) |
| `test_hardware_real_media` / `parity_encode` -> `install_qsvencc_tap`/`metrics_only_failure` | полный stderr | WIRED (прогоны с попытками 1) |
| Dockerfile -> `/etc/OpenCL/vendors/intel.icd` | самопроверка D-07 | WIRED |

### Поведенческие проверки

| Проверка | Команда | Результат | Статус |
|----------|---------|-----------|--------|
| Быстрый тир | `.venv/bin/python -m pytest -q -m "not hardware"` | 283 passed, 12 deselected | PASS |
| Линтер | `.venv/bin/ruff check .` | All checks passed | PASS |
| Аппаратные логи (замок, матрица, r4604, hwtier, parity) | чтение логов | как в таблице truths | PASS (доказательства записаны, повторный аппаратный запуск не делался) |

### Анти-паттерны

Маркеров TBD/FIXME/XXX без ссылок в изменённых файлах не искалось отдельно; `src/` фазой не менялся. Замечания код-ревью учтены ниже.

### Оценка замечаний 08-REVIEW.md

| Находка | Подрывает must-have? | Оценка |
|---------|----------------------|--------|
| CR-01 (пробник: сессия без эталона = byte_identical) | Нет | Затрагивает только точку 1129/metrics=on в 08-01 (сам SUMMARY сноской пометил её как не сверенную побайтно). Цель D-02 (стоп-гейт) держится на metrics=off 9/9 и 923/928 on 6/6. Затем эталон 1129 on построен в 08-06 и совпал с off, а все 320 сессий on побайтно сверены в боевом харнессе, где «нет эталона» = `SWEEP_SKIPPED`, не «чисто». Minor |
| WR-03 (допуск METRICS_FAILED, маркер «Decoded frame count…») | Нет, ослабляет запас | Гарантия замка «0 побайтных расхождений среди rc=0 сессий» не затронута: rc=0 всегда идёт через побайтный гейт, rc≠0 выход не порождает как «чисто». Наблюдено METRICS_FAILED = 0 из 688 сессий (640 матрицы + 48 замка). Ужесточение рекомендуется до смены бинаря, но фаза-цель не нарушена. Minor |
| WR-05 (порог ревизии 4634 не отличает сборку без патчей #319/#320) | Нет | Продакшен-тихой порчи нет (frame-count верификация в `encode_chunk`); рекомендуется поднять минимум для метрик до 4658. Minor |
| WR-01/WR-02 (ИТОГО ssim_db от округлённого, `-nan` в `_NUM`) | Нет | Код относится к quick 261003-8fs, вне scope must_haves фазы 8; правки в бэклог |
| WR-04 (токен в xtrace блока dovi_tool), WR-06, IN-01..IN-07 | Нет | Улучшения безопасности/надёжности; WR-04 стоит исправить до публикации образа в CI (токен в публичном логе) |

### Требуется участие человека

Нет открытых пунктов. Хостовый чекпоинт D-07/D-14 выполнен пользователем и принят как человеческое доказательство.

### Итог по пробелам

Блокирующих пробелов нет: все критерии ROADMAP и must_haves планов подтверждены кодом и аппаратными логами (замок 2/2, матрица 640 сессий без расхождений на r4658, непустота на r4604 с 3 расхождениями, паритет с legacy с метриками, рантайм-образ на Ubuntu 24.04 проверен на хосте). Три minor-пробела (CR-01, WR-03, устаревшие формулировки в CLAUDE.md/README) вынесены для бэклога и не блокируют переход к следующей фазе.

---

_Verified: 2026-10-03_
_Verifier: Claude (bm-verifier)_
