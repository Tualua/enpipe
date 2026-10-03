---
phase: quick-261003-hph
plan: 01
subsystem: tests/integration
tags: [dolby-vision, hardware-tests, ffprobe]
key-files:
  modified:
    - tests/integration/test_hardware_real_media.py
    - tests/fixtures/media/README.md
decisions:
  - "Проверочный ffprobe переопределяется ENPIPE_TEST_FFPROBE; пайплайн остаётся на PATH-стеке"
  - "DV-паритет считается по side data 'Dolby Vision Metadata', а не 'Dolby Vision RPU Data'"
metrics:
  tasks: 2
  completed: 2026-10-03
---

# Quick 261003-hph: исправление DV-проверок в hardware-тестах

Тесты DV теперь считают кадры с "Dolby Vision Metadata" (есть и на HEVC-исходнике, и на AV1-выходе), проверяют DOVI configuration record выхода (profile 10, compat исходника) и включают новый `test_dv_profile5` (P5 -> 10.0). Проверочный ffprobe задаётся через `ENPIPE_TEST_FFPROBE`.

## Что сделано

- Task 1 (`cc02840`): `VERIFY_FFPROBE`, `_verify_ffmpeg` (ffmpeg-сосед ffprobe для self-check; отсутствие бинарника даёт False, то есть skip), `_dv_metadata_frame_count` (заменила `_dv_rpu_frame_count`), `_dovi_config_record`, общий `_run_dv_case`, `test_dv`, `test_dv_profile5`. `_frame_side_data_types` использует `VERIFY_FFPROBE`.
- Task 2 (`0a0df5a`): README фикстур. Добавлены `dv-p5.mkv`, раздел про `ENPIPE_TEST_FFPROBE`, описание проверок.

## Проверки (реально запущены)

- `uv run pytest`: 298 passed, 13 deselected.
- `uv run ruff check .`: All checks passed.
- `uv run pytest -m hardware --collect-only -q`: собираются `test_dv` и `test_dv_profile5`.
- `git diff -- src`: пусто (`hdr.py` не изменён); `_dv_rpu_frame_count` нигде не осталась.
- Hardware-тесты НЕ запускались (по условию задачи, их запускает оркестратор). Поведение на A380 и значения 10/compat этим исполнителем не подтверждены, только опираются на факты из плана.

## Отклонения от плана

Нет, план выполнен как написан.

## Known Stubs

Нет.

## Self-Check: PASSED

Коммиты cc02840 и 0a0df5a существуют, изменённые файлы на месте.
