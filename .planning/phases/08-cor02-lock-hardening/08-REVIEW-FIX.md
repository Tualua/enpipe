---
phase: 08-cor02-lock-hardening
fixed_at: 2026-10-03T00:00:00Z
review_path: .planning/phases/08-cor02-lock-hardening/08-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Фаза 08: отчёт об исправлениях по код-ревью

**Исправлено:** 2026-10-03
**Исходное ревью:** .planning/phases/08-cor02-lock-hardening/08-REVIEW.md
**Итерация:** 1

**Сводка:**
- Находок в области (critical + warning): 7
- Исправлено: 7
- Пропущено: 0

Режим работы: `workflow.use_worktrees=false`. Коммиты сделаны прямо в `main`, без worktree.

**Проверка:**
- Быстрый тир: `uv run pytest` дал 288 passed, 12 deselected. Новых тестов 5: WR-01 добавил 1, WR-02 добавил 1, WR-03 добавил 3.
- `uv run ruff check .` чист.
- `scratch/probe_d02_byte_identity.py --self-test` выдаёт `SELF-TEST OK`.
- Аппаратные тесты (`-m hardware`: замок COR-02, аппаратный тир, пробник D-02, `parity_encode`) здесь **не запускались**, потому что нет Arc-железа. Проверено только, что они собираются: `--collect-only` нашёл 12 тестов. Изменения в WR-03, WR-05 и WR-06 нужно подтвердить прогоном на хосте A380.

## Исправленные находки

### CR-01: `probe_d02` засчитывает сессию без эталона как `byte_identical`

**Изменённые файлы:** `scratch/probe_d02_byte_identity.py`
**Коммит:** cf5e325
**Что сделано:**
- Добавлен класс `no_reference`. `_classify` возвращает его при `same is None`, до проверок байтов и кадров.
- Сессии `no_reference` попадают в столбец ok итоговой таблицы и ставят `passed = False`.
- Если эталон не построен, `passed = False` теперь ставится в обоих вариантах, а не только при `metrics=False`.
- В `--self-test` добавлены два кейса `no_reference`.
- Сам лог `scratch/probe_d02_20261003T013801Z.log` не правился: он в `.gitignore`. В `08-01-SUMMARY.md` (сноска `(*)`) уже записано, что ячейка `metrics=on 1129` побайтно не сверена.

### WR-01: ssim_db строки ИТОГО считается из округлённого ssim_all

**Изменённые файлы:** `src/enpipe/encoding/metrics.py`, `tests/unit/encoding/test_metrics.py`
**Коммит:** 32b5501
**Что сделано:**
- Добавлена `_wmean_raw`: взвешенное среднее без округления. `_wmean` теперь просто её обёртка с округлением.
- В ИТОГО `ssim_all` округляется только на выходе. `ssim_db` считается из неокруглённого значения.
- Добавлен регрессионный тест. Для `0.999996` итоговый ssim_db конечен (≈53.98). При одной сцене ИТОГО совпадает со строкой сцены.

### WR-02: `_NUM` не принимает `-nan`/`-inf`

**Изменённые файлы:** `src/enpipe/encoding/chunk.py`, `tests/unit/encoding/test_chunk.py`
**Коммит:** e5138a8
**Что сделано:**
- `_NUM = r"(?:-?(?:inf|nan)|[\d.]+)"`, рядом комментарий о том, что glibc печатает знаковый NaN.
- Добавлен тест на строки SSIM и PSNR с `-nan`/`-inf`: поля не теряются, nan всплывает.

### WR-03: допуск `METRICS_FAILED` без порога; потеря кадров считалась отказом метрик

**Изменённые файлы:** `tests/integration/_concurrency_harness.py`, `tests/integration/test_concurrency_immunity.py`, `tests/integration/test_harness_gates.py`
**Коммит:** 06f8fee
**Что сделано:**
- Маркеры сведены в один кортеж `_METRICS_FAILURE_MARKERS = ("VIDEOMETRIC: Failed", "Failed to finish video quality metric")`. Нога триады выводится из него плюс `_FRAME_LOSS_MARKER`.
- Маркер `allocVA` убран.
- `is_metrics_failure` возвращает False, если в stderr есть «Decoded frame count does not match». Такая сессия становится `SESSION_FAILED`, а `metrics_only_failure` не разрешает её повтор ни в аппаратном тире, ни в `parity_encode`.
- Замок теперь считает любой `METRICS_FAILED > 0` проблемой.
- Тесты гейтов обновлены. Для `allocVA` и маркера потери кадров ожидается False. Добавлены кейсы для смешанного stderr, для `metrics_only_failure` и для статуса `SESSION_FAILED`.
- **Требует проверки человеком.** Это изменение логики. Маркер `VIDEOMETRIC:` сужен до `VIDEOMETRIC: Failed`, чтобы совпадать с прежней ногой триады. Прочие сообщения VIDEOMETRIC, если они бывают, теперь классифицируются как `SESSION_FAILED`, то есть строже. Замок на r4658 нужно прогнать на A380.

### WR-04: блок `dovi_tool` печатает токен GitHub в лог сборки

**Изменённые файлы:** `Dockerfile`
**Коммит:** c1202e4
**Что сделано:**
- Блок `dovi_tool` в рантайм-образе переведён на ту же схему, что и qsvencc. Используется `set -eu; set +x` вокруг чтения секрета и обоих авторизованных `curl`. Затем `set --` сбрасывает заголовок, и только после этого включается `set -x`.
- В `.devcontainer/Dockerfile` блок `dovi_tool` секрет не читает, там утечки нет и правка не нужна.
- Сборку образа здесь не прогоняли.

### WR-05: порог r4634 пропускает сборки без патчей #319/#320

**Изменённые файлы:** `src/enpipe/shared/qsvencc_version.py`, `tests/integration/test_concurrency_immunity.py`, `tests/integration/test_hardware_real_media.py`
**Коммит:** 2a344c3
**Что сделано:**
- Добавлена константа `QSVENCC_METRICS_MIN_REV = 4658` с обоснованием.
- Замок COR-02 при `metrics=True` проваливается (fail, а не skip), если ревизия ниже 4658.
- В аппаратном тире та же проверка стоит в фикстуре `metrics_tap`, а через неё проходят все варианты с метриками.
- Рантайм-гейт `ensure_qsvencc_fixed` и пороги в Dockerfile **намеренно не менялись**, на это есть три причины:
  1. в проде усечение и так ловят `encode_chunk`/`count_frames` через `die()`;
  2. в образе URL без совпадающего SHA256 подменить нельзя, потому что `sha256sum -c` упадёт;
  3. сверка `dpkg-query` с `8.32+vppsync4` сломала бы запланированный переход на официальный 8.33.
- Поднимать ли рантайм-гейт для пути с метриками, решает человек.
- **Требует проверки человеком.**

### WR-06: запасной ΔPSNR-гейт в `parity_encode` сравнивает несопоставимые итоги

**Изменённые файлы:** `scratch/parity_encode.py`
**Коммит:** 84c3aaf
**Что сделано:**
- Сравнение по ИТОГО заменено построчным, по сценам (`_scene_rows`, `_per_scene_metric_gate`).
- Проверяется совпадение наборов сцен и непустота таблицы.
- Пустое, нечисловое или `nan` значение даёт FAIL с понятной причиной вместо `ValueError`. `inf` допустим только при `inf` с обеих сторон.
- Логику проверил на синтетических строках. На железе путь не прогонялся: он латентный и срабатывает только при недетерминизме qsvencc.
- Учтите: legacy не разбирает `inf`. Поэтому сцена без потерь в этом запасном пути даст FAIL «пусто». Так и задумано (явный FAIL лучше молчаливого PASS), но это может потребовать внимания.

## Вне области (info, fix_scope=critical_warning)

IN-01…IN-07 не трогались. Связь с IN-02: в `scratch/probe_d02_byte_identity.py` осталась своя копия маркеров (`VIDEOMETRIC:`, `allocVA`, `Decoded frame count does not match`). Теперь она расходится с харнессом, исправленным в WR-03. Её стоит заменить на `harness.is_metrics_failure`.

---

_Исправлено: 2026-10-03_
_Фиксер: Claude (bm-code-fixer)_
_Итерация: 1_
