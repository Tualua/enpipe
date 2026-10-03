# HANDOFF — qsvencc `--seek` отсчитывается от `firstpkt->pts` и молча попадает в следующую GOP (`--avhw`)

**Дата:** 2026-10-03
**Откуда:** enpipe, сессия отладки [`qsvencc-seek-last-gop.md`](./qsvencc-seek-last-gop.md)
**Кому:** соседний проект, где уже чинили qsvencc (ср. 45003f1 / #308, #319/#320)
**Версия, на которой воспроизведено:** QSVEncC 8.32 (r4658), форк Tualua/QSVEnc `8.32-vppsync4`; A380, iHD. Код ридера в форке **побайтно совпадает** с `rigaya/QSVEnc` master (`b16f167`, `QSVPipeline/rgy_input_avcodec.cpp`, 4249 строк) — баг в апстриме.

> ⚠️ **Тихая порча.** В большинстве случаев qsvencc НЕ падает: `--seek` на точное время keyframe приводит к старту с **следующего** keyframe. Число кадров при `--trim`/`--frames` сохраняется, rc=0 — внешне всё нормально, но содержимое берётся из другой GOP. Падение (rc=255) случается только когда «следующего» keyframe нет — при seek в последнюю GOP файла.

---

## 1. Симптом

- `qsvencc --avhw -i SRC --seek T ...`, где `T` — время keyframe K (относительно начала потока), на части источников начинает кодирование не с K, а с keyframe, следующего за K.
- Если K — последний keyframe файла: rc=255, `failed to initialize file reader(s)`, перед этим одно из:
  - `avqsv: failed to seek 0:01:25.961.` (mkv-фрагмент), или
  - `avqsv: No video packets found!` / `avqsv: failed to get first frame position.` (mp4 и TS).
- Затронутые источники в наших замерах: синтетический HEVC в **MPEG-TS**, DV profile 5 в **mp4** и его mkv-нарезка. Не затронуты (сдвиг 0): mkv, сделанный ffmpeg/x265 напрямую; Silo (DV 8.1, mkv); HDR10+ mkv.

## 2. Корневая причина (по коду)

`rgy_input_avcodec.cpp`, ветка `--seek` (~стр. 2236–2262):

```cpp
auto [ret, firstpkt] = getSample();                 // «текущий» первый пакет из очереди
...
const auto seek_time = av_rescale_q(1, av_d2q(seek_sec, 1<<24), m_Demux.video.stream->time_base);
int seek_ret = av_seek_frame(fmt, video.index, firstpkt->pts + seek_time, 0);          // flags=0 → вперёд: keyframe с ts >= цели
if (0 > seek_ret)
    seek_ret = av_seek_frame(fmt, video.index, firstpkt->pts + seek_time, AVSEEK_FLAG_ANY);
if (0 > seek_ret) { AddMessage(RGY_LOG_ERROR, _T("failed to seek %s.\n"), ...); return RGY_ERR_UNKNOWN; }
```

Две вещи вместе:

1. **База отсчёта `firstpkt->pts` ≠ pts первого keyframe.** `getSample()` к этому моменту возвращает не первый keyframe, а более поздний пакет (в порядке декодирования; с B-кадрами его pts больше pts keyframe). При этом сам ридер знает правильную базу — в debug-логе: `avqsv: found first key frame: timestamp 7508 (0.0834222), offset 0` (`m_Demux.video.streamFirstKeyPts`).
   - Измеренный сдвиг `firstpkt->pts − pts(первого keyframe)`:
     | Источник | сдвиг | как получен |
     |---|---|---|
     | синтетика HEVC в TS (x265, bframes=4) | **≈0.250 с** (база = pts 0.3337 — 5-й пакет в порядке декодирования; keyframe 0.0834) | бинарный поиск порога seek: ok ≤5.753, поздно ≥5.761 при K_rel=6.006 |
     | DV P5 mkv-фрагмент (из mp4) | **0.083 с** (2-й пакет; в логе `Got header from actual packet: 124 byte`) | порог 85.879 = 85.961 − 0.083 |
     | mkv от ffmpeg/x265, Silo DV 8.1, HDR10+ mkv | 0 | seek на точный keyframe попадает в него |
   - Заголовок из реального пакета (`Got header from actual packet`) — **не обязательное условие**: в TS заголовок взят из extradata (`GetHeader: 86 bytes`), а сдвиг всё равно 0.25 с.
2. **Прямой (forward) seek.** `flags=0` выбирает ближайший keyframe **не раньше** цели. Цель = K + сдвиг > K ⇒ попадаем в следующий keyframe. Для последнего keyframe «следующего» нет ⇒ `av_seek_frame` < 0 (mkv) или пустая очередь после seek (mp4/TS) ⇒ rc=255.

Ожидаемая семантика `--seek T` (как у `ffmpeg -ss` до входа): старт с keyframe **≤** `start_pts + T`, где `start_pts` — pts первого кадра/keyframe потока.

## 3. Минимальное воспроизведение (без защищённого контента)

```bash
# 12 с, 1280x720 10-bit, GOP 48, B-кадры; keyframes каждые 2.002 с
X="keyint=48:min-keyint=48:scenecut=0:bframes=4:log-level=error"
ffmpeg -v error -f lavfi -i "testsrc2=size=1280x720:rate=24000/1001,format=yuv420p10le" -t 12 \
  -c:v libx265 -x265-params "$X" -muxdelay 0 -muxpreload 0 -y syn.ts
ffmpeg -v error -f lavfi -i "testsrc2=size=1280x720:rate=24000/1001,format=yuv420p10le" -t 12 \
  -c:v libx265 -x265-params "$X" -y syn.mkv
# keyframes (отн. начала): 0 2.002 4.004 6.006 8.008 10.010; у TS start_time=0.0834

enc() { rm -f o.obu; qsvencc --backend qsv --avhw -i "$1" -c av1 --seek "$2" --frames 1 -o o.obu >/dev/null 2>&1; echo "rc=$? $1 seek=$2 md5=$(md5sum < o.obu | cut -c1-8)"; }
enc syn.mkv 0:00:06.006   # bdb64511  = keyframe 6.006 (верно)
enc syn.mkv 0:00:08.008   # 954a103a  = keyframe 8.008 (верно)
enc syn.ts  0:00:04.004   # bdb64511  = keyframe 6.006 (ОШИБКА: ждали 4.004)
enc syn.ts  0:00:06.006   # 954a103a  = keyframe 8.008 (ОШИБКА: ждали 6.006)
enc syn.ts  0:00:10.010   # rc=255, "No video packets found!" (последняя GOP)
```

Содержимое x265 одинаково в обоих контейнерах, поэтому совпадение md5 однокадровых энкодов из TS и mkv однозначно показывает, с какого keyframe начался энкод. (md5 — с нашего прогона; у вас могут отличаться абсолютные значения, но паттерн «TS@K == mkv@K_next» должен сохраниться.)

## 4. Предлагаемый фикс в qsvencc (на ваше усмотрение)

- База отсчёта: использовать `m_Demux.video.streamFirstKeyPts` (или `stream->start_time` / минимальный pts первого GOP), а не `firstpkt->pts`.
- Направление: `AVSEEK_FLAG_BACKWARD` (keyframe ≤ цели) — совпадает с семантикой `ffmpeg -ss`, и seek в последнюю GOP перестаёт падать. Если важна обратная совместимость с «прямым» поведением — хотя бы backward-fallback вместо `AVSEEK_FLAG_ANY` (ANY может встать на не-keyframe).
- Регресс-тест: синтетика из §3 — `TS@K` и `mkv@K` должны дать одинаковый первый кадр; seek на последний keyframe — rc=0.
- Связанное: `--seek` с ratio (`seekRatio`) идёт тем же путём.

## 5. Влияние на enpipe (для контекста, фикс там отдельно)

- enpipe режет источник на сцены и кодирует каждую с `--seek floor_ms(K) --trim (S−K):(E−1−K)`, где K — keyframe ≤ начала сцены. При сдвиге базы чанк начинается с GOP позже ⇒ содержимое сцены неверное, а проверка числа кадров проходит. Последний чанк в последней GOP ⇒ rc=255 ⇒ весь прогон умирает.
- Обход в enpipe, проверенный на dv-p5/dv-p81: `--seek K − m`, `m = min(0.5 с, (K − K_prev)/2)` — работает, пока сдвиг < m (для TS-синтетики сдвиг 0.25 с < 0.5 с; на других источниках не измерен). Решение о фиксе в enpipe отложено до ответа по апстриму.
- В enpipe добавляется аппаратная проверка содержимого чанков (md5 первого кадра чанка vs эталонный декод источника на K), чтобы этот класс ошибок ловился независимо от qsvencc.

## 6. Что осталось неясным (проверить у вас)

- Почему `getSample()` в TS возвращает 5-й пакет (pts 0.3337), а в mkv-фрагменте P5 — 2-й: зависит ли от `checkPtsStatus`/длины очереди на старте, от порядка B-кадров, от `--avhw` vs `--avsw` (мы проверяли только `--avhw`).
- Затрагивает ли то же самое `--seekto` и аудио-seek (синхронизация звука при `--seek` в TS).
- Насколько часто сдвиг > 0 на реальных источниках: m2ts (Blu-ray remux), broadcast TS, mp4 с edit list.

## Артефакты

- Пробные файлы и логи: `/tmp/claude-0/-workspaces-enpipe/7682fc60-44f2-424a-8b15-1a436c99b524/scratchpad/dvprobe/` (`syn.ts`, `syn.mkv`, `p5-nocut.mkv`) — временные, могут исчезнуть; синтетику проще пересоздать по §3.
- Фикстуры enpipe (не распространять, защищённый контент): `/data/downloads/enpipe-fixtures/dv-p5.mkv` (последний kf 85.961, dur 90.174), `dv-p81.mkv`, `hdr10plus.mkv`.
- Полная хронология: [`qsvencc-seek-last-gop.md`](./qsvencc-seek-last-gop.md).
