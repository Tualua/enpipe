---
quick_id: 261003-8qq
status: complete
date: 2026-10-03
files_modified:
  - Dockerfile
  - .devcontainer/Dockerfile
---

# Quick 261003-8qq: qsvencc 8.32+vppsync4 (форк Tualua/QSVEnc) — SUMMARY

## Что сделано

- Оба Dockerfile пиннят релиз форка `Tualua/QSVEnc` тег `8.32-vppsync4`
  (коммит 94d6f7b) вместо зеркала `deps-qsvencc-r4634`:
  `qsvencc_8.32+vppsync4_amd64_ubuntu2004.deb`,
  sha256 `d2aa8412…6cb6` (скачанный ассет == `SHA256SUMS` релиза == digest API).
- Комментарий-провенанс переписан, TODO(D-06) снят; todo
  `2026-10-02-qsvencc-pin-upstream-release.md` перенесён в `todos/done/`.
- Порог ревизии (`-ge 4634`, `QSVENCC_MIN_REV`, post-create.sh) не менялся:
  сборка даёт `8.32 (r4658)`. Порог по ревизии форк от стокового 8.32 не
  отличает — метрические патчи гарантирует только sha256-пин.
- Сборка установлена в текущий devcontainer (`dpkg -i`, было 8.31 r4634).

## Проверка

- `tests/unit/shared/test_qsvencc_threshold_sync.py` — 6 passed.
- A380, 240 кадров testsrc2 1080p 10-bit, `--avsw -c av1 --icq 23 --psnr --ssim`,
  3 прогона: rc=0, 240/240 кадров, PSNR Avg 49.25 дБ, SSIM All 0.998162,
  три выхода побайтно идентичны (md5 2393c088…).
- Повтор на пути `--avhw` (рабочий режим пайплайна): исходник HEVC Main10
  1080p24, 240 кадров (libx265, keyint 48, mkv), `--avhw -c av1 --icq 23
  --output-depth 10 --psnr --ssim`. 3 последовательных + 3 одновременных
  прогона: все rc=0, 240/240 кадров, шесть выходов побайтно идентичны
  (md5 f6ab8aab…), метрики во всех прогонах одинаковы.
- Сверка метрик с ffmpeg (выход завёрнут mkvmerge, кадры по порядку
  `setpts=N`): SSIM Y/U/V/All совпадает до 1e-6 (0.996970); PSNR qsvencc =
  PSNR от среднего MSE по кадрам (Y 49.076896 против 49.076981 у ffmpeg),
  а не среднее покадровых PSNR (49.415). Сырой OBU в ffmpeg напрямую
  сравнивать нельзя: кадры сопоставляются неверно (479 строк вместо 240).
- Образы НЕ пересобраны здесь (нет docker) — хост пересобирает.

## Не сделано / дальше

- Фаза 08 (08-06): блокер «236/240 при rc=0» должен уйти — подтвердить
  `test_sdr[metrics]`, `parity_encode.py` с метриками и замком COR-02 на r4658.
- Эталоны/доказательства фаз 07–08 сняты на r4634; при сверке побайтных
  эталонов с прошлыми логами учитывать смену сборки.
