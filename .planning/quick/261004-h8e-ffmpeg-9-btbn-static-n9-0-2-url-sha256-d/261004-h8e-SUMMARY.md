---
phase: quick-261004-h8e
plan: 01
subsystem: образы / ffmpeg
tags: [ffmpeg, dockerfile, devcontainer, pin, sha256]
key-files:
  modified:
    - Dockerfile
    - .devcontainer/Dockerfile
    - .devcontainer/post-create.sh
    - tests/unit/shared/test_runtime_dockerfile.py
    - tests/integration/_concurrency_harness.py
    - tests/integration/test_concurrency_immunity.py
    - tests/integration/test_hardware_real_media.py
    - tests/fixtures/media/README.md
    - docker/README.md
    - .planning/codebase/STACK.md
    - .planning/codebase/INTEGRATIONS.md
    - .planning/codebase/CONCERNS.md
  created:
    - tests/unit/shared/test_ffmpeg_pin_sync.py
metrics:
  completed: 2026-10-04
---

# Quick 261004-h8e: ffmpeg 9.0.2 (BtbN static, пин URL+SHA256) основной в обоих образах

**Итог:** в рантайм- и девконтейнер-образе `ffmpeg`/`ffprobe` теперь один и тот же
закреплённый архив BtbN n9.0.2 (sha256 проверяется до распаковки), симлинки
`/usr/local/bin` -> `/opt/ffmpeg-9/bin`; opt-in блок ffmpeg-8.1 удалён.

## Коммиты

- `e5ea12c` build: Dockerfile x2, post-create ENV-01, test_ffmpeg_pin_sync, test_runtime_dockerfile
- `c912e6b` test: harness на основном ffmpeg (гейт `ffmpeg_av1qsv_available` по наличию av1_qsv), доки
- `954845a` fix: HDR10-фикстура без `-color_*` + уточнение комментариев harness

## Решения

- **ldd-решение (Task 1c):** `ldd $(command -v qsvencc) | grep -E 'libav|libsw|libpostproc'` -> совпадений нет
  (grep rc=1), поэтому apt-пакет `ffmpeg` убран из рантайм-образа. Тест
  `test_apt_does_not_install_ffmpeg` это фиксирует (смотрит только списки `apt-get install`).
- Совместимых симлинков `ffmpeg-8.1`/`ffprobe-8.1` нет (вызывающие мигрированы).
- Публикации/зеркалирования не делалось.

## Результаты проверок (ffmpeg 9 первым в PATH, `ENPIPE_TEST_FFPROBE` не задан)

| Проверка | Результат |
|---|---|
| `uv run pytest -q tests/unit/shared` | 56 passed |
| `uv run pytest -q` (быстрый уровень) | 324 passed, 16 deselected, ~20 с; `ruff check` чисто |
| ENV-01 блок post-create (извлечён и запущен с PATH=/opt/ffmpeg-9/bin) | `ENV01_OK=1`, версия n9.0.2 |
| Аудио-путь: testsrc 720p + 5.1 pcm_s16le + stereo ac3, `enpipe run`, 240 кадров | rc=0, 6.4 с; потоки `av1`, `flac` (6 ch), `opus` (2 ch); проверка кадров склейки пройдена |
| `test_hardware_real_media.py` (13 тестов, ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures) | первый прогон: 11 passed, **2 failed** (test_hdr10[*]), 21м39с; skip нет, DV-тесты (`test_dv`, `test_dv_profile5`) выполнены и PASSED через ffprobe по умолчанию |
| `test_hdr10` после правки фикстуры | 2 passed на ffmpeg 9 (29 с) и на системном 6.1 (37 с) |
| COR-02: `test_concurrency_immunity.py` целиком (ffmpeg av1_qsv + qsvencc no-metrics/metrics) | 3 passed, 6м58с; ffmpeg-ветка не пропущена (1м47с отдельным прогоном) |

Модуль real_media целиком после правки фикстуры заново не прогонялся (только test_hdr10, на обоих ffmpeg); остальные 11 тестов прошли в первом прогоне до правки, правка затронула только `_HDR10_CODEC_ARGS`.

## Отклонения от плана

**1. [Rule 1 - Bug, фикстура] test_hdr10 падал на ffmpeg 9**
- **Причина (исследована):** при генерации клипа с ffmpeg 9 выходные опции
  `-color_primaries/-color_trc/-colorspace` заставляют Matroska-muxer записать в Colour
  только matrix coefficients; `ffprobe` 9 читает `color_transfer=unknown`,
  `color_primaries=unknown`, и `detect_hdr` не видит HDR (`--master-display` не в списке).
  Тот же клип под ffprobe 6.1 даёт `smpte2084`. VUI в битстриме верный (raw hevc -> smpte2084).
  Без этих опций (только x265 VUI) ffmpeg 9 пишет теги корректно. Базовый прогон на 6.1
  проходил (2 passed).
- **Исправление:** убраны три `-color_*` из `_HDR10_CODEC_ARGS` (теги остаются в x265 VUI),
  пороги и проверки не менялись. Коммит `954845a`.
- **Заметка о риске (не исправлялось, вне плана):** `detect_hdr` опирается на
  `stream=color_transfer` из ffprobe. С ffprobe 9 источник, у которого теги цвета есть
  только в VUI битстрима, а не в контейнере (например, mkv, созданный ffmpeg 9 с `-color_trc`),
  классифицируется как SDR, и HDR-флаги qsvencc тихо не передаются. Для реальных мастеров с
  корректными тегами контейнера (fixture hdr10plus/dv) проблем не наблюдалось. Стоит
  рассмотреть отдельной задачей (fallback на SPS/frame-level color_transfer).

**2. [Конфликт verify плана]** автоматический verify Task 2 содержит `! grep -rn 'ffmpeg-8.1' tests/`,
а требуемый планом `test_ffmpeg_pin_sync.py` обязан содержать эти литералы (проверка отсутствия).
Литералы оставлены в стражe; во всех остальных tests/ ссылок на 8.1-имена нет.

## Что не проверено

Образы не собирались (docker в этом контейнере нет): `sha256sum -c`, build-time self-check и
`command -v ffmpeg` -> `/usr/local/bin/ffmpeg` проверены только чтением; ENV-01 проверен на
симуляции PATH, не в реальном образе.

## Follow-ups для пользователя

1. Пересобрать оба образа на хосте и выполнить runtime-smoke из `docker/README.md`
   (`ffmpeg -version` -> `n9.0.2`; `enpipe run` на testsrc с аудио -> av1+flac+opus).
2. По желанию зеркалировать архив ассетом GitHub Release проекта (нужны `gh` и ваше
   одобрение), затем сменить `FFMPEG_URL` в обоих Dockerfile (SHA256 прежний; страж синхронности
   следит за идентичностью).

## Self-Check: PASSED

Файлы и коммиты e5ea12c, c912e6b, 954845a существуют в `git log`.
