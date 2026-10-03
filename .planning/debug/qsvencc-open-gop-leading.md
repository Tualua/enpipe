---
status: diagnosed
trigger: "open-GOP источник: чанк начинается с 2 кадров предыдущей сцены (тихая порча, число кадров верное) — test_hdr10 падает на проверке содержимого"
created: 2026-10-03
updated: 2026-10-03
---

# Debug: open-GOP — чанк начинается с кадров предыдущей сцены

## Symptoms

<!-- DATA_START -->
- **Expected:** первый кадр чанка = кадр источника S (начало сцены); `--seek floor_ms(K) --trim (S−K):(E−1−K)` вырезает ровно кадры [S, E) в порядке показа.
- **Actual:** `test_hdr10` (оба варианта метрик): чанк 2, сцена [480,720), K=250, K_next=500 — число кадров 240 верно, но первые 2 кадра чанка — кадры источника 478 и 479 (по анализу исполнителя quick 261003-j55). Проверка содержимого: PSNR(chunk0, src[S]) = 9.52 дБ при пороге 30 дБ (psnr_alt=42.7 против src[S+Δ], psnr_src_alt=9.52).
- **Errors:** нет — rc=0, проверки числа кадров и выравнивания по keyframe проходят. Падает только новая проверка содержимого (`tests/integration/_chunk_content.py`, `_verify_chunk_first_frames` в `tests/integration/test_hardware_real_media.py`).
- **Timeline:** обнаружено 2026-10-03 первым прогоном проверки содержимого (quick 261003-j55). Воспроизводится на qsvencc r4658 и на 8.32-vppsync6 (r4663, где исправлен seek firstpkt) — т.е. НЕ баг firstpkt-seek.
- **Reproduction:**
  - `ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware -k test_hdr10 tests/integration/test_hardware_real_media.py` (системный qsvencc r4658; для r4663 — `PATH=/opt/qsvencc-vppsync6/usr/bin:$PATH`).
  - Также `test_chunk_content_firstpkt_seek_bug` (синтетика mp4, x265 по умолчанию = open-gop) остаётся XFAIL на r4663 — видимо, тот же дефект (исполнитель: с `open-gop=0` не воспроизводится).
<!-- DATA_END -->

## Known Facts

- Источник test_hdr10: x265 ultrafast, HDR10-параметры (`_HDR10_CODEC_ARGS`), keyint по умолчанию (250), open-gop по умолчанию (x265 default = 1) — CRA-кадры с ведущими RASL/RADL-кадрами, pts которых меньше pts CRA.
- Исполнитель 261003-j55: «после keyframe на 10.417 с идут 2 ведущих кадра с более ранними timestamps; keyframe-таблица enpipe считает от keyframe по timestamp, а qsvencc --seek/--trim считают на 2 кадра раньше; qsvencc --seek 10.417 сам попадает на верный keyframe».
- Гипотезы для проверки (не подтверждены):
  1. enpipe нумерует кадры по pts (порядок показа) и считает K = номер CRA; qsvencc после seek на CRA выдаёт и ведущие кадры (pts < CRA), т.е. trim-ноль = первый ведущий кадр, а не CRA ⇒ сдвиг на число ведущих кадров.
  2. Ведущие кадры при старте с CRA — RASL (ссылаются на предыдущую GOP) должны отбрасываться (NoRaslOutputFlag); если qsvencc/декодер их выдаёт — это баг декодирования/qsvencc; если они RADL — их вывод законен и enpipe должен это учитывать.
  3. Чем ключевой кадр в keyframe-таблице (`src/enpipe/encoding/keyframes.py`, Cues и ffprobe-путь) отличается для open-GOP: CRA помечен keyframe, а его pts > pts ведущих кадров.
- Инварианты: границы чанков на keyframe, побайтная склейка .obu, проверка числа кадров на чанк и склейку, DV RPU per-chunk.
- Связанное: апстрим-фикс firstpkt-seek — `.planning/debug/HANDOFF-qsvencc-seek-firstpkt.md` (решён в 8.32-vppsync6, r4663).
- Код: `src/enpipe/encoding/keyframes.py` (`kf_before`, `fmt_seek`, `compute_chunk_seek_trim`), `src/enpipe/encoding/chunk.py::chunk_command`, `src/enpipe/encoding/pipeline.py::run_encode`; legacy-оракул `legacy/encode_scenes.py` имеет ту же математику.
- Пробная синтетика: `/tmp/claude-0/-workspaces-enpipe/7682fc60-44f2-424a-8b15-1a436c99b524/scratchpad/dvprobe/og1.*` (open-gop=1) и `og0.*` (open-gop=0), 12 с, keyint 48, bframes 4.

## Constraints for the fix

- Не ослаблять инварианты и порог проверки содержимого (30 дБ). Не трогать `test_hdr10`.
- Ответить на вопрос: где ошибка — в enpipe (нумерация/trim) или в qsvencc (вывод ведущих кадров после seek). Если в qsvencc — подготовить handoff по образцу `HANDOFF-qsvencc-seek-firstpkt.md` с минимальным репро без защищённого контента.
- Оценить масштаб: сколько реальных источников open-GOP (x265 по умолчанию, Blu-ray HEVC/AVC). Проверить на реальных фикстурах (`/data/downloads/enpipe-fixtures/*.mkv`) — есть ли у них ведущие кадры.
- Код/комментарии/логи — на русском.

## Current Focus

hypothesis: CONFIRMED — баг qsvencc (rgy_input_avcodec.cpp ~3519, ветка OpenGOP: m_trimParam.offset++ за каждый ведущий пакет с pts < streamFirstKeyPts), а не enpipe.
next_action: ожидать решения пользователя (handoff в апстрим и/или компенсация trim в enpipe) — gather initial evidence (устарело) — на og1 vs og0 синтетике: порядок pts/dts вокруг CRA, что выдаёт qsvencc (r4663) при seek на CRA + trim 0:N (первые кадры по PSNR против источника), сравнить с ffmpeg -ss на тот же keyframe.

## Evidence

- og1.mkv (HEVC, bframes=4, open-gop): после каждого CRA 4 ведущих пакета с pts < pts(CRA) (ffprobe packets). og0 (closed): 0.
- qsvencc r4663 --avhw --seek 2.002 (K=кадр 48) на og1: лог `Trim 4-9 [offset: 4]` при `--trim 0:9`; на og0 `Trim 0-9 [offset: 0]`.
- PSNR-сверка с источником: og1 `--trim 4:13` (ожидали 52..61) даёт кадры 48..57 (сдвиг -4 = число ведущих кадров); `--trim 0:9` даёт всего 6 кадров (48..53); `--trim 10:19` даёт 54.. (ожидали 58). Декодер ведущие (RASL) кадры НЕ выдаёт: индекс 0 = сам CRA.
- Код: в getSample ветка `timestamp < streamFirstKeyPts => m_trimParam.offset++` (комментарий: OpenGOP, B-кадры перед первым keyframe) вычитается из trim (стр. 2318-2320). Она срабатывает и для RASL-пакетов ПОСЛЕ CRA, которые декодер отбрасывает => trim смещается на -N, число кадров сохраняется (поэтому проверка счёта проходит).
- Компенсация `--trim (S-K+N):(E-1-K+N)`, N=число ведущих пакетов: og1 `--trim 8:17` даёт кадры 52.. (верно). Реальные фикстуры (dv*, hdr10plus .mkv): ведущих кадров 0 => не затронуты.

## Eliminated

- hypothesis: баг firstpkt-seek qsvencc. Опровергнуто: воспроизводится на 8.32-vppsync6 (r4663), где firstpkt-seek исправлен и проверен.

## Resolution

root_cause: qsvencc (rigaya/QSVEnc rgy_input_avcodec.cpp, ветка OpenGOP в getSample) увеличивает trim-offset на каждый пакет с pts < pts первого keyframe, включая отбрасываемые декодером RASL-кадры после CRA; trim сдвигается на -N кадров (N=число ведущих), счёт кадров сохраняется. enpipe-математика корректна.
fix: (не применён — ждёт решения) варианты: A) handoff в апстрим; B) компенсация в enpipe (N из ffprobe-пакетов после K); C) A+B.
