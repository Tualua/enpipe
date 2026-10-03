# Quick 261003-c1b: строка ИТОГО без PSNR не роняет run_encode

`run_encode` больше не падает с TypeError на строке ИТОГО, когда SSIM распарсен, а PSNR нет. Форматирование вынесено в `format_total_line` в `src/enpipe/encoding/metrics.py`, где каждое поле форматируется независимо: None даёт «н/д», nan и inf печатаются как есть. Если нет ни SSIM, ни PSNR, строка не печатается.

## Коммиты
- 6775d35 — fix: `format_total_line` и юнит-тесты в `test_metrics.py`
- a154dd2 — fix: подключение в `pipeline.py` и регрессионный тест `test_run_encode_survives_total_without_psnr`

## Проверка (фактически запущено)
- До фикса `pipeline.py` новый wiring-тест падал: 1 failed, 3 passed. Это подтверждает воспроизведение бага.
- После фикса `uv run pytest tests/unit -q` дал 205 passed.
- `uv run ruff check .` дал "All checks passed".
- `grep "total['psnr_avg']"` по `pipeline.py` пуст.

## Отклонения
- Task 1 (TDD): тесты и реализация `format_total_line` написаны в одном шаге. Красная фаза для `test_metrics.py` отдельно не прогонялась. Красная фаза для wiring-теста прогонялась и упала на старом коде.
- Первый запуск правки не сработал, потому что `python` не найден в PATH. Скрипт перезапущен через `uv run python`, файлы не пострадали.
