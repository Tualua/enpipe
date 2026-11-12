---
status: open
opened: 2026-11-12
source: фаза 10.1, план 10.1-13 (одночанковый режим для источников без pts), Task 1 — проверка на B50
blocks: 10.1-13 (проверка на B50 на wmv_test4), 10.1-12 (UAT, тест 5)
---

# HANDOFF — `--avsw` на wmv3 (ASF): чтение входа обрывается на `avcodec_send_packet` = INVALIDDATA, а ffmpeg этот же файл декодирует без ошибок

**Дата:** 2026-11-12
**Откуда:** enpipe, фаза 10.1, план 10.1-13
**Кому:** форк Tualua/QSVEnc (владелец — оператор)
**Где воспроизведено:** QSVEncC 8.32 (**r4677**, тег `8.32-vppsync10`), libav внутри qsvencc 9.0.1 (avcodec 63.1.101). Intel Arc B50 (Battlemage), iHD. Входной декод программный (`--avsw`), так что от GPU обрыв, скорее всего, не зависит.

> Порчи нет, падение громкое: rc=240, кадров меньше, чем в источнике. enpipe это ловит: чанк падает, `die()`. Но такие файлы не кодируются совсем.

---

## 1. Симптом

Файл `wmv_test4.wmv` (ASF, wmv3 Main, 1280x720, 29.97 к/с, B-кадры, `pts_time=N/A` у всех видеопакетов, только dts; Flip4Mac WMV Export, 2010).

```
qsvencc --avsw -i wmv_test4.wmv --codec av1 --icq 23 -o out.obu
```

- **Ошибка:** rc=240, `INPUT: Error in reader: undefined behavior..`, `Break in task INPUT`.
- **Где обрывается:** `encoded 975 frames`, около 32.5 с от начала. Место одно и то же на целом файле, на куске с 0 с и на куске с ключевого кадра 20.06 с, то есть обрыв привязан к содержимому, а не к началу чтения.
- **Причина в логе:** `--log-level debug` перед обрывом печатает
  ```
  [wmv3 @ ...] MB Direct Type plane encoding: Imode: 0, Invert: 0
  [wmv3 @ ...] MB Skip plane encoding: Imode: 2, Invert: 1
  avsw: failed to send packet to video decoder: Invalid data found when processing input.
  INPUT: Error in reader: undefined behavior..
  ```
- **Флаги синхронизации не помогают.** `--avsync forcecfr` и `--avsync vfr` отказывают при старте: `timestamp not acquired successfully from input stream, avsync forcecfr cannot be used.` Это ожидаемо, pts нет. `--input-analyze 30` ничего не меняет.

### Контроль: ffmpeg декодирует тот же файл без ошибок

ffmpeg n9.0.2 (BtbN static; libav почти той же версии, что внутри qsvencc):

```
ffmpeg -v error -xerror -i wmv_test4.wmv -map 0:v -f null -        # rc=0, ошибок декодера нет
ffmpeg -v error -xerror -threads 1 -i wmv_test4.wmv -map 0:v -f null -   # rc=0
# то же с -threads 2/4/16 и -thread_type frame/slice — rc=0
ffprobe -v error -count_frames ... → кадров декода == пакетов (кусок 100 с: 2996 == 2996)
```

Ни один пакет декодером не отвергнут: если бы он отверг пакет, кадров было бы меньше, чем пакетов.

### Другие ASF-файлы оператора: qsvencc `--avsw --trim 0:4000` проходит

| файл | кодек | pts | результат |
|---|---|---|---|
| wmv_test4.wmv | wmv3 | нет | ✗ rc=240 на ~975 |
| wmv_test1.wmv | vc1 (WVC1) | **нет** | ✓ 4001 кадр |
| wmv_test2.wmv | wmv3 | есть | ✓ 4001 |
| wmv_test3.wmv | wmv3 | есть | ✓ 4001 |
| wmv_test.wmv | wmv2 | есть | ✓ 4001 |

Значит, дело не в отсутствии pts как таковом: vc1 без pts проходит. Ломается конкретное содержимое wmv_test4, точнее то, как qsvencc его читает.

## 2. Где в коде

`QSVPipeline/rgy_input_avcodec.cpp` (тег `8.32-vppsync10`), `RGYInputAvcodec::LoadNextFrameInternal`, около стр. 4060:

```cpp
int ret = avcodec_send_packet(m_Demux.video.codecCtxDecode, pkt);
...
} else if (ret < 0 && ret != AVERROR(EAGAIN)) {
    AddMessage(RGY_LOG_ERROR, _T("failed to send packet to video decoder: %s.\n"), ...);
    return RGY_ERR_UNDEFINED_BEHAVIOR;   // ← любая ошибка декодера = конец чтения
}
```

ffmpeg на ошибке `send_packet` пишет в лог и продолжает. Но здесь ffmpeg ошибки вообще **не получает**. Поэтому главный вопрос — почему декодер внутри qsvencc получает другой пакет или иначе настроенный контекст. Сама реакция на ошибку вторична.

Что отличается от ffmpeg (гипотезы, не проверены):
1. **Данные пакета.** Например, при чтении без pts пакеты дробятся или склеиваются по-другому, или есть побочный эффект предварительного анализа (`avsw: read 128/256 packets`, затем повторное открытие или seek к началу).
2. **Extradata.** `GetHeader extradata(5): 4f f1 08 31 00` — 5 байт. Для wmv3 sequence header обычно 4 байта. Плюс есть код подрезки extradata по первому пакету (стр. ~4000).
3. **Параметры контекста декодера** (`threads` и др., стр. ~1284 / ~2676) относительно ffmpeg CLI. Значения `threads` 1/2/4/16 в ffmpeg ошибки не дают.

## 3. Воспроизведение

Синтетику сделать нельзя: в ffmpeg нет кодера wmv3, только декодер. Нужен кусок реального файла. Решение о его передаче за оператором: это клип стороннего происхождения.

Минимальный кусок, ~5 МБ, 397 кадров декода, начинается с ключевого кадра 20.06 с:

```
ffmpeg -v error -ss 29.9 -i /data/downloads/wmv_test4.wmv -map 0:v:0 -an -t 3.5 -c copy -f asf repro.wmv
# ASF без индекса: -ss встаёт на ключевой кадр 20.06 с, это нормально
ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 repro.wmv   # 397
qsvencc --avsw -i repro.wmv --codec av1 --icq 23 -o out.obu --log-level debug    # rc=240, encoded 371 frames
ffmpeg -v error -xerror -i repro.wmv -map 0:v -f null -                           # rc=0
```

Граница проверена: с `-t 3` (382 кадра) qsvencc проходит (rc=0, 382 из 382), с `-t 3.5` уже падает. Значит, «плохой» для qsvencc пакет — один из пакетов 382…396 этого куска, примерно 32.8–33.2 с исходника. Размеры этих пакетов ничем не выделяются: 7–25 КБ, нулевых и аномальных нет.

Проверенные копии (живут до перезапуска контейнера):
- `/tmp/tmp.T3kCbJtscI/c_29.9_3.5.wmv` — падает;
- `/tmp/tmp.T3kCbJtscI/c_29.9_3.wmv` — проходит;
- `/tmp/tmp.6WHtxPUtaz/wmv_test4_cut.wmv` — первые 100 с;
- отладочный лог: `/tmp/tmp.polWBJa3kw/dbg.log`.

## 4. Что предлагается

1. Найти, чем пакет (или контекст декодера) в qsvencc отличается от ffmpeg на пакетах 382…396 `repro.wmv`. Например, сделать отладочный дамп `pkt->size`/первых байт/флагов перед `avcodec_send_packet` и сравнить с `ffprobe -show_packets -show_data`.
2. Если причина в чтении (дробление/склейка, extradata, повторное открытие после анализа) — исправить чтение, чтобы декодер получал то же, что у ffmpeg.
3. Только если пакет действительно битый и ffmpeg его прячет: решать, пропускать ли INVALIDDATA, как ffmpeg (предупреждение и продолжение). Для enpipe это допустимо **только** при честном числе кадров на выходе: если кадр выпал, enpipe поймает это сверкой и упадёт громко. Тихо подставлять кадры нельзя.

## 5. Открытые вопросы

- Воспроизводится ли на апстриме rigaya/QSVEnc (тот же код чтения)?
- Падает ли `--avhw`? Вряд ли применимо: аппаратного декода wmv3 на Arc нет.
- Затронут ли сценовый путь (`--seek/--trim`) на wmv3 **с** pts (wmv_test2/3)? В этих прогонах до 4001 кадра обрыва нет, но целиком файлы не прогонялись.

## 6. Что в enpipe до ответа форка

- План 10.1-13 остановлен на чекпоинте Task 1 (проверка на B50). Код одночанкового режима закоммичен (`6beca86`), юнит-тесты зелёные.
- Отдельный отказ в enpipe не нужен: обрыв qsvencc и так громкий (rc≠0 → `die()`), тихой порчи нет.
- После ответа форка: на новой сборке повторить `repro.wmv` и полный `wmv_test4.wmv`, затем довести 10.1-13 (сверка числа кадров с полным декодом на B50).
