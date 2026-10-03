---
status: diagnosed
trigger: "qsvencc --avhw --seek в последнюю GOP источника падает rc=255: последний чанк теряется и весь encode умирает"
created: 2026-10-03
updated: 2026-10-03
---

# Debug: qsvencc --seek в последнюю GOP падает (rc=255)

## Symptoms

<!-- DATA_START -->
- **Expected:** `enpipe encode` кодирует каждую сцену, включая последнюю; чанк, чья сцена начинается в последней GOP источника, сикается на последний keyframe (`kf_before`) и кодируется с `--trim` — как для всех остальных сцен.
- **Actual:** qsvencc на таком чанке завершается rc=255 за ~0.1с, `encode_chunk` возвращает ошибку, `run_encode` после drain вызывает `die("часть чанков не удалась — файл собирать нельзя")`. Весь прогон теряется на последнем чанке.
- **Errors:**
  - фрагмент `/data/downloads/enpipe-fixtures/dv-p5.mkv` (mkvmerge `--split parts:00:05:00-00:06:30` из mp4, видео only): `avqsv: Got header from actual packet: 124 byte.` → `avqsv: failed to seek 0:01:25.961.` → `failed to initialize file reader(s).`
  - полный оригинал For All Mankind S01E01 (.mp4, DV P5, 3912.288с), seek на последний kf 3908.238: `avqsv: No video packets found!` → `avqsv: failed to get first frame position.` → `failed to initialize file reader(s).`
- **Timeline:** обнаружено 2026-10-03 первым реальным прогоном `test_dv_profile5` (quick 261003-hph). Ранее DV-тесты на этом стеке не выполнялись (системный ffmpeg 6.1 без `dovi_rpu` → skip). Неизвестно, воспроизводится ли на не-DV источниках.
- **Reproduction:** A380, qsvencc 8.32 (r4658, Tualua fork), в devcontainer (GPU доступен).
  - `ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware -k dv_profile5` → FAIL, чанк 16 сцена[2061,2162).
  - Минимально: `qsvencc --backend qsv --avhw -i /data/downloads/enpipe-fixtures/dv-p5.mkv -c av1 --seek 0:01:25.961 --frames 5 -o /dev/null` → rc=255.
<!-- DATA_END -->

## Known Facts (from orchestrator probing)

- dv-p5.mkv: dur 90.174, 2162 кадров, 23.976 fps, keyframes ... 80.539 82.916 **85.961** (последний). B-кадры: у kf 85.961 dts=85.794.
- Seek-матрица на dv-p5.mkv (`--frames 5`): 0:01:22.916 rc=0; 0:01:25.000 rc=0; 0:01:25.950 / .960 / .962 / 26.000 / 27.000 / 29.000 — все rc=255.
- Тот же P5-источник, нарезанный на 100с (`parts:00:05:00-00:06:40`): seek 0:01:25.961 rc=0, 0:01:35.000 rc=0.
- Полный оригинал .mp4: seek 1:05:00.000 и 1:05:05.000 rc=0; seek на последний kf 1:05:08.238 rc=255 (другое сообщение, см. выше).
- Не воспроизводится: Silo S03E06 (DV P8.1+HDR10+, .mkv) — полный файл, seek на последний kf 0:54:00.279 (3с до конца) rc=0; фрагмент dv-p81.mkv seek 0:01:26.711 rc=0; hdr10plus.mkv seek 0:01:28.088 rc=0. test_dv (P8.1) PASSED полностью, включая последний чанк.
- Seek-математика enpipe: `src/enpipe/encoding/keyframes.py` (`kf_before`, `fmt_seek`, `--trim (S-K):(E-1-K)`), сборка команды `src/enpipe/encoding/chunk.py::chunk_command`, оркестрация `src/enpipe/encoding/pipeline.py::run_encode` (drain-then-die).
- Пробные файлы/логи: `/tmp/claude-0/-workspaces-enpipe/7682fc60-44f2-424a-8b15-1a436c99b524/scratchpad/dvprobe/` (p5-nocut.mkv = 100-с нарезка).
- Исходник qsvencc (avqsv reader): форк Tualua/QSVEnc 8.32-vppsync4 / апстрим rigaya/QSVEnc — можно читать на GitHub (QSVPipeline/rgy_input_avcodec.cpp: "failed to seek", "No video packets found", "failed to get first frame position").

## Constraints for the fix

- Инварианты нельзя ослаблять: границы чанков на keyframe источника, побайтная склейка .obu, проверка числа кадров на чанк и на склейку, DV RPU per-chunk.
- Кандидат обхода: при отказе seek — повтор с предыдущего keyframe (`kf_before(table, K-1)`) и бо́льшим `--trim`; повторять только при распознанной ошибке инициализации ридера (не маскировать другие отказы). Альтернативы искать в причине (например, сколько пакетов avqsv дочитывает после seek).
- Код/комментарии/логи — на русском (CLAUDE.md). Тесты: быстрый тир `uv run pytest`; аппаратный — см. Reproduction.

## Current Focus

hypothesis: CONFIRMED - qsvencc seek target = firstpkt->pts + seek (p5: +83ms, header from actual packet consumes 1st packet); forward seek lands on first kf >= target; exact-kf seek lands one GOP late, last kf -> past end -> rc=255
next_action: ждём фикс апстрима (handoff передан); тем временем — тест содержимого чанков. Было: ЖДЁМ ВЫБОРА ПОЛЬЗОВАТЕЛЯ по варианту фикса (правки production seek/trim не применены). Старый план: gather initial evidence — прочитать код avqsv seek/first-frame-position в исходниках QSVEnc, определить условие отказа (хвост после seek-цели? кол-во пакетов? контейнер/таймстемпы P5?) и проверить на дополнительных источниках.

## Evidence

- rgy_input_avcodec.cpp ~2230: av_seek_frame(ts = firstpkt->pts + seek_time, flags 0 = forward, then ANY); error 'failed to seek' if both <0.
- Harness libavformat 6.1: dv-p5 seek works up to ts<=85961, -1 beyond; qsvencc fails from 85.879 = 85961-83 exactly; dv-p81 (header from extradata, offset 0) fails from 86.712 = last kf+1ms. mp4 original: same effect -> 'No video packets found'.
- dv-p5 log: 'Got header from actual packet: 124 byte' (p81: 'GetHeader: 106 bytes' from extradata).
- md5 of 1-frame encode: dv-p5 seek 1:22.916 (== kf) gives same output as seek 1:25.500 (kf 85.961), i.e. LANDS ON NEXT GOP (silent wrong content, frame count still right). seek 1:22.616 -> kf 82.916 correct; 1:25.661 -> kf 85.961 correct. p81: 1:23.333 == 1:23.000 == kf 83.333 correct.

- 2026-10-03 (оркестратор) синтетика без DV: HEVC x265 в MPEG-TS (заголовок из extradata, `GetHeader: 86 bytes`) — seek на точный kf попадает в СЛЕДУЮЩИЙ (md5 TS@4.004 == mkv@6.006, TS@6.006 == mkv@8.008), seek на последний kf → rc=255 `No video packets found`. Тот же контент в mkv — верно. Порог: ok ≤5.753, поздно ≥5.761 при K_rel 6.006 ⇒ база firstpkt->pts ≈ 0.3337 (5-й пакет в decode-order), сдвиг ≈0.25 с от первого kf (0.0834). Исходник: форк Tualua == rigaya master b16f167 (rgy_input_avcodec.cpp побайтно).

## Eliminated

- hypothesis: условие — «заголовок взят из реального пакета» (Got header from actual packet). Опровергнуто TS-синтетикой: заголовок из extradata, сдвиг всё равно 0.25 с. Истинное условие — firstpkt->pts ≠ pts первого keyframe (streamFirstKeyPts).

## Resolution

decision (пользователь, 2026-10-03): фикс в qsvencc — в соседнем проекте; передан [`HANDOFF-qsvencc-seek-firstpkt.md`](./HANDOFF-qsvencc-seek-firstpkt.md). Обход в enpipe (seek K − m) не применён, ждёт ответа по апстриму. Отдельно: добавить аппаратную проверку содержимого чанков (md5 первого кадра vs эталон на K).
