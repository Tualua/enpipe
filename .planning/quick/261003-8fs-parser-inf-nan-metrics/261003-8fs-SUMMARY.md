# Quick 261003-8fs: парсер метрик inf/nan и агрегат ИТОГО

Парсер qsvencc принимает `inf`/`nan`; ИТОГО считает PSNR через frame-weighted MSE, ssim_db выводит из итогового SSIM, nan не маскируется.

## Коммиты
- 2a2b4c1: регэкспы `_NUM` (inf/nan) в chunk.py + тесты
- 8caf3b3 (HEAD после amend с документами): агрегация ИТОГО в metrics.py, тесты, проверка в `_assert_metrics_csv`

## Проверено (реально запущено)
- `uv run pytest`: 283 passed, 12 deselected (было 274)
- сбор hardware-теста (`-m ""`): 9 tests collected; сами hardware-тесты не запускались (нет GPU-прогона)
- `git diff --stat legacy/`: пусто

## Отклонения
Нет. pipeline.py не менялся.
