---
status: resolved
resolved: "Tualua/QSVEnc 8.32-vppsync7 (r4665); закрыто при закрытии v1.2 2026-10-04"
---

**Статус: Решено в 8.32-vppsync7 (r4665)** — патч #6 форка Tualua/QSVEnc; проверено на A380 (--avhw и --avsw: `--seek 2.002 --trim 4:13` -> первый кадр 52, 10 кадров; `--trim 0:9` -> 48, 10 кадров; на r4663 было 48 / 6); защита enpipe снята в quick 261003-mj7

# HANDOFF — qsvencc `--trim` уезжает на −N кадров на open-GOP источниках (`m_trimParam.offset` считает отброшенные RASL)

**Дата:** 2026-10-03
**Откуда:** enpipe, сессия отладки [`qsvencc-open-gop-leading.md`](./resolved/qsvencc-open-gop-leading.md)
**Кому:** соседний проект, где чинили qsvencc (45003f1/#308, #319/#320/#322, seek-фикс в 8.32-vppsync6)
**Где воспроизведено:** QSVEncC 8.32 (**r4663**, Tualua/QSVEnc `8.32-vppsync6` — уже с фиксом `--seek`) и r4658; A380, iHD, `--avhw`. Код ветки ниже присутствует в `rgy_input_avcodec.cpp` форка vppsync6 (стр. ~3565–3570) и в апстриме rigaya.

> ⚠️ **Тихая порча.** rc=0, число кадров чанка верное, но `--trim a:b` после `--seek` на CRA выдаёт кадры, сдвинутые на **−N** (N — число ведущих RASL-кадров после CRA): кодирование начинается на N кадров раньше запрошенного. Проверка числа кадров этого не видит.

---

## 1. Симптом

- Источник HEVC с open-GOP (x265 по умолчанию: `open-gop=1`): после каждого CRA в порядке декодирования идут N «ведущих» пакетов с pts < pts(CRA) (RASL, ссылаются на предыдущую GOP).
- `qsvencc --avhw --seek T_cra --trim a:b ...` выдаёт кадры `[a−N, b−N]` относительно CRA, а не `[a, b]`. В логе: `Trim 4-9 [offset: 4]` при `--trim 0:9` (на closed-GOP источнике — `Trim 0-9 [offset: 0]`).
- Побочные эффекты: `--trim 0:9` даёт меньше кадров (6 вместо 10 — начало «съедено» отрицательным смещением, `max(0, …)`).

## 2. Корневая причина (по коду)

`rgy_input_avcodec.cpp`, `getSample()`, после нахождения первого keyframe:

```cpp
} else if (auto timestamp = (pkt->pts == AV_NOPTS_VALUE) ? pkt->dts : pkt->pts;
           timestamp != AV_NOPTS_VALUE && timestamp < m_Demux.video.streamFirstKeyPts) {
    // OpenGOP等で、最初のキーフレームより前にBフレームがある場合がある
    // こうした場合にoffsetを加算しておかないとtrimがずれる
    m_trimParam.offset++;
}
```

и затем (стр. ~2332–2348) `offset` вычитается из каждого trim-диапазона: `start -= offset; fin -= offset`.

Замысел — учесть B-кадры, которые идут раньше первого keyframe по pts. Но после `--seek` на CRA эти пакеты — **RASL**, и декодер (QSV, `NoRaslOutputFlag=1` при старте с CRA) их **не выдаёт**: первый выходной кадр — сам CRA. Счётчик же их учитывает ⇒ trim смещается на −N, хотя смещать нечего.

Подтверждение на синтетике (r4663, 12 с, keyint 48, bframes 4, open-gop → после каждого CRA 4 ведущих пакета, N=4):

| Команда (seek на CRA = кадр 48) | Ожидали кадры источника | Получили (по PSNR против источника) |
|---|---|---|
| `--trim 4:13` | 52..61 | **48..57** (−4) |
| `--trim 0:9` | 48..57 | 48..53 (только 6 кадров) |
| `--trim 10:19` | 58.. | **54..** (−4) |
| `--trim 8:17` (ручная компенсация +N) | 56.. по запросу | 52.. = то, что нужно для «4:13» |
| то же на closed-GOP (`open-gop=0`) | 52..61 | 52..61 (offset 0) |

## 3. Минимальное воспроизведение (без защищённого контента)

```bash
X="keyint=48:min-keyint=48:scenecut=0:bframes=4:open-gop=1:log-level=error"
ffmpeg -v error -f lavfi -i "testsrc2=size=1280x720:rate=24000/1001,format=yuv420p10le" -t 12 \
  -c:v libx265 -x265-params "$X" -y og1.mkv
ffmpeg -v error -f lavfi -i "testsrc2=size=1280x720:rate=24000/1001,format=yuv420p10le" -t 12 \
  -c:v libx265 -x265-params "${X/open-gop=1/open-gop=0}" -y og0.mkv

# ведущие пакеты после CRA (pts < pts keyframe в порядке декодирования): og1 → 4, og0 → 0
ffprobe -v error -select_streams v:0 -show_entries packet=pts,flags -of csv=p=0 og1.mkv | sed -n 45,51p
#   og1: 2002,K  1919  1835  1877  1960  2211 ...   ← CRA и 4 ведущих (pts < 2002)
#   og0: 1960  1877  1835  1919  2002,K  2211 ...   ← закрытый GOP: B-кадры до IDR, после него ведущих нет

# лог: offset
qsvencc --backend qsv --avhw -i og1.mkv -c av1 --seek 0:00:02.002 --trim 0:9 --log-level debug -o /dev/null 2>&1 | grep -i 'trim\|offset'
#   → "adjust trim by offset 4." / "Trim 4-9 [offset: 4]";   на og0.mkv → "Trim 0-9 [offset: 0]"

# какой кадр источника реально первый (PSNR против кадров 50..54 источника):
qsvencc --backend qsv --avhw -i og1.mkv -c av1 --seek 0:00:02.002 --trim 4:13 -o t.obu
ffmpeg -v error -i t.obu -frames:v 1 -c:v ffv1 -y f0.nut
for n in 46 47 48 49 50 51 52; do
  printf "%s " $n; ffmpeg -v info -i og1.mkv -i f0.nut -lavfi \
   "[0:v]select=eq(n\,$n),setpts=N/TB/24[a];[1:v]setpts=N/TB/24[b];[a][b]psnr" -f null - 2>&1 | grep -o 'average:[0-9.inf]*'
done
#   наш прогон: 46:23.5 47:23.8 48:52.6 49:23.9 50:23.2 51:23.1 52:23.1 — максимум на 48, а должен быть на 52
```

## 4. Предлагаемый фикс в qsvencc (на ваше усмотрение)

- Не увеличивать `m_trimParam.offset` за пакеты, которые декодер не выдаст. Варианты:
  - для HEVC — смотреть тип NAL: RASL_N/RASL_R (8/9) не считать; RADL_N/RADL_R (6/7) декодируемы и выдаются — их учитывать по реальной семантике вывода;
  - либо считать offset по фактическому выходу декодера (сколько кадров с pts < pts первого keyframe реально вышло), а не по демуксеру;
  - либо после `--seek` (старт с CRA, `NoRaslOutputFlag=1`) не входить в эту ветку вовсе.
- Регресс-тест: синтетика из §3 — `og1@seek+trim a:b` и `og0@seek+trim a:b` должны давать одинаковые номера кадров источника (по PSNR); лог `offset: 0` на og1 после seek.
- Проверить AVC open-GOP (I-кадр без IDR + B-кадры с ранним pts) и старт файла с CRA без `--seek`.

## 5. Влияние на enpipe (контекст)

- enpipe режет сцены `--seek floor_ms(K) --trim (S−K):(E−1−K)`; на open-GOP источнике каждый чанк, начинающийся не на K, начинается на N кадров раньше (кадры предыдущей сцены), и заканчивается на N раньше. Число кадров совпадает ⇒ порча тихая. Найдено новой аппаратной проверкой содержимого (`test_hdr10`: чанк [480,720) начинается с кадров 478, 479; PSNR 9.5 дБ).
- Решение в enpipe до фикса: **жёсткий отказ** на источниках с ведущими кадрами после keyframe (громкая ошибка вместо тихой порчи). Компенсацию `trim + N` не вводим, чтобы не получить обратный сдвиг после фикса апстрима.
- Реальные фикстуры enpipe (Silo DV 8.1, DV P5, HDR10+ WEB-DL) ведущих кадров не имеют — не затронуты. Под риском: x265-энкоды с настройками по умолчанию, вероятно часть Blu-ray HEVC/AVC.

## 6. Что осталось неясным

- Выдаёт ли QSV-декодер RADL-кадры после seek на CRA (тогда «правильный» offset ≠ 0 для них) — в синтетике x265 ведущие кадры RASL.
- Поведение без `--seek`, когда файл начинается с CRA с RASL (offset тоже вычитается?).
- Затрагивает ли то же `--avsw`.

## Артефакты

- Синтетика: `/tmp/claude-0/-workspaces-enpipe/7682fc60-44f2-424a-8b15-1a436c99b524/scratchpad/dvprobe/og1.mkv`, `og0.mkv` (временные; проще пересоздать по §3).
- Связанный, уже исправленный баг: [`HANDOFF-qsvencc-seek-firstpkt.md`](./HANDOFF-qsvencc-seek-firstpkt.md) (решён в 8.32-vppsync6).
