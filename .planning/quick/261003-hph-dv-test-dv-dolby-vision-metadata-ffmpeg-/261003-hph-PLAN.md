---
phase: quick-261003-hph
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/test_hardware_real_media.py
  - tests/fixtures/media/README.md
autonomous: true
requirements: [QUICK-261003-hph]

must_haves:
  truths:
    - "Проверочные ffprobe-пробы DV/HDR берут бинарник из ENPIPE_TEST_FFPROBE (по умолчанию \"ffprobe\"), а сам пайплайн под тестом продолжает использовать системные ffmpeg/ffprobe из PATH"
    - "test_dv считает кадры с side_data_type \"Dolby Vision Metadata\" (есть и на HEVC-исходнике, и на AV1-выходе, декодированном libdav1d) — паритет с исходником на финальном .mkv и на pre-mux .obu чанках, > 0"
    - "test_dv проверяет запись DOVI configuration record на выходе: dv_profile == 10, dv_bl_signal_compatibility_id == compat id исходника (выведен из записи исходника, не из имени файла)"
    - "Новый test_dv_profile5 на фикстуре dv-p5.mkv выполняет тот же прогон + инварианты кадров/кейфреймов + паритет DV-метаданных + dv_profile==10 и compat==0; при отсутствии фикстуры — честный skip"
    - "Self-check AV1 DOVI использует ffmpeg-соседа проверочного ffprobe; если возможности нет — честный skip, не ложный pass"
    - "src/enpipe/encoding/hdr.py не изменён"
  artifacts:
    - path: "tests/integration/test_hardware_real_media.py"
      provides: "VERIFY_FFPROBE, _dovi_config_record, _dv_metadata_frame_count, _run_dv_case, test_dv, test_dv_profile5"
      contains: "Dolby Vision Metadata"
    - path: "tests/fixtures/media/README.md"
      provides: "Документация dv-p5.mkv и ENPIPE_TEST_FFPROBE"
      contains: "ENPIPE_TEST_FFPROBE"
  key_links:
    - from: "_frame_side_data_types"
      to: "VERIFY_FFPROBE"
      via: "cmd[0]"
      pattern: "\\[VERIFY_FFPROBE, \"-v\""
    - from: "test_dv / test_dv_profile5"
      to: "_run_dv_case"
      via: "shared helper call"
      pattern: "_run_dv_case\\("
---

<objective>
Починить DV-проверки в hardware-тестах: test_dv сейчас всегда skip на системном ffmpeg 6.1.1 (нет dovi_rpu bsf), а на ffmpeg 9 упал бы 0 vs N, потому что считает "Dolby Vision RPU Data", которого нет на AV1-кадрах после libdav1d. Добавить env-override проверочного ffprobe, проверку DOVI configuration record на выходе и новый тест на профиль 5 (P5 → 10.0).

Purpose: DV-сохранность — часть core value (preserved HDR/DV metadata); сейчас она фактически не проверяется.
Output: обновлённый tests/integration/test_hardware_real_media.py и tests/fixtures/media/README.md. Поведение пайплайна (src/enpipe/encoding/hdr.py) НЕ меняется — mkvmerge сам выводит конфиг-запись 10.x из потока (проверено на A380).
</objective>

<execution_context>
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/workflows/execute-plan.md
@/root/.claude/plugins/cache/gsd-plugin/gsd/4.9.1/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@tests/integration/test_hardware_real_media.py
@tests/fixtures/media/README.md

<facts_verified_on_hardware>
Проверено оркестратором и планировщиком на A380 в этом контейнере (ffprobe 9.0.2 = /opt/ffmpeg-9/bin/ffprobe; системный ffmpeg 6.1.1 без AV1 в dovi_rpu):
- `/opt/ffmpeg-9/bin/ffprobe -v error -select_streams v:0 -show_frames -show_entries frame=side_data_list -of json <raw .obu>` работает на сыром AV1 OBU: 48/48 кадров с "Dolby Vision Metadata" (файл scratchpad/dvprobe/p81-10.1.obu). Значит тот же счётчик годится и для pre-mux чанков.
- AV1-выход (libdav1d по умолчанию в ffprobe 9) несёт "Dolby Vision Metadata", но НЕ "Dolby Vision RPU Data". HEVC-исходник несёт оба.
- Конфиг-запись читается так: `ffprobe -v error -select_streams v:0 -show_streams -of json <file>` → streams[0].side_data_list[] элемент с side_data_type == "DOVI configuration record" и целыми полями dv_profile, dv_level, dv_bl_signal_compatibility_id (и dv_version_major/minor). (Вариант `-show_entries stream=side_data_list` возвращает пустые словари — НЕ использовать.) Системный ffprobe 6.1.1 тоже отдаёт эти поля для mkv-исходника.
- Значения: dv.mkv (→ dv-p81.mkv) источник 8 / compat 1 → выход 10 / compat 1. dv-p5.mkv источник 5 / compat 0 → выход 10 / compat 0. Независимо от флага qsvencc --dolby-vision-profile 10.0/10.1.
- `/opt/ffmpeg-9/bin/ffmpeg -hide_banner -h bsf=dovi_rpu` → "Supported codecs: hevc av1".
</facts_verified_on_hardware>

<interfaces>
Существующее в tests/integration/test_hardware_real_media.py (англоязычные комментарии/докстринги — сохранять английский):
- module-level `pytestmark = pytest.mark.hardware` (l.76), `REPO_ROOT` (l.78)
- `_require_hardware()`, `_run_cli(argv: List[str]) -> None`
- `_verify_frame_counts_and_keyframes(src, workdir, scenes_path, final_mkv) -> None`
- `_frame_side_data_types(path: Path) -> List[List[str]]` (~l.397) — сейчас жёстко "ffprobe"; используется также test_hdr10
- `FIXTURES_DIR`, `_fixture(name) -> Optional[Path]` (~l.566-573)
- `_av1_dovi_self_check() -> bool` (~l.576) — сейчас жёстко "ffmpeg"
- `_dv_rpu_frame_count(path) -> Tuple[int, int]` (~l.590) — считает "Dolby Vision RPU Data"
- `test_dv(tmp_path)` (~l.718-785) — тело: skip без фикстуры, skip без self-check, src-счёт > 0, копия в tmp_path, `enpipe detect --jobs 2`, `enpipe encode ... --keep --no-audio --no-metrics --jobs 2`, `_verify_frame_counts_and_keyframes`, паритет на out и на сумме chunk_{i:05d}.obu
- импорты уже есть: json, os, re, shutil, subprocess, Path, List, Optional, Tuple; read_scenes, count_frames из пакета
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Проверочный ffprobe, счёт "Dolby Vision Metadata", проверка конфиг-записи и test_dv_profile5</name>
  <files>tests/integration/test_hardware_real_media.py</files>
  <action>
Все комментарии/докстринги — на английском (язык файла). Пайплайн под тестом (_run_cli, count_frames, keyframe_table_ffprobe, detect_hdr) НЕ трогать — он остаётся на PATH-ffprobe/ffmpeg.

1. Рядом с FIXTURES_DIR (или выше _frame_side_data_types, т.к. он определён раньше — поместить константу до него, например сразу после REPO_ROOT) добавить `VERIFY_FFPROBE = os.environ.get("ENPIPE_TEST_FFPROBE", "ffprobe")` с комментарием: только для read-only проверочных проб; пайплайн намеренно продолжает использовать системный стек из PATH; для AV1 DOVI нужен ffmpeg >= 7 (например BtbN static build, /opt/ffmpeg-9/bin/ffprobe).

2. `_frame_side_data_types`: заменить литерал "ffprobe" на VERIFY_FFPROBE. Обновить докстринг (упоминание "Task 2" → DV metadata check). test_hdr10 при дефолтном env ведёт себя как раньше.

3. `_av1_dovi_self_check`: брать ffmpeg-соседа проверочного ffprobe. Логика: если VERIFY_FFPROBE содержит разделитель пути (Path(VERIFY_FFPROBE).parent != Path(".")), то ffmpeg = parent / ("ffmpeg" + суффикс имени после "ffprobe", обычно пусто); иначе "ffmpeg" из PATH. Если вычисленный бинарник не существует / не запускается (FileNotFoundError) — вернуть False. Регексп `\bav1\b` и read-only `-h bsf=dovi_rpu` сохранить. Обновить докстринг: проверяется именно тот ffmpeg-билд, к которому относится проверочный ffprobe.

4. Заменить `_dv_rpu_frame_count` на `_dv_metadata_frame_count(path) -> Tuple[int, int]`: считает кадры, у которых в side_data_list есть "Dolby Vision Metadata". Докстринг объясняет почему: ffprobe/libdav1d на AV1 экспортирует распарсенные RPU как "Dolby Vision Metadata", а "Dolby Vision RPU Data" (сырые RPU) есть только на HEVC-исходнике — счёт по RPU Data дал бы 0 на выходе при живых RPU; "Dolby Vision Metadata" есть на обоих, поэтому паритет исходник↔выход сравнивает одно и то же; работает и на сыром .obu (проверено). Упомянуть, что нативный декодер av1 не экспортирует DV side data вовсе — поэтому полагаемся на дефолтный декодер (libdav1d) ffprobe. Удалить старую функцию (других вызовов нет — проверить grep).

5. Добавить `_dovi_config_record(path) -> Optional[Dict[str, Any]]` (добавить Dict, Any в импорт typing): запуск `[VERIFY_FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(path)]`, check=True; вернуть первый элемент streams[0].side_data_list с side_data_type == "DOVI configuration record", иначе None. Комментарий: `-show_entries stream=side_data_list` даёт пустые словари, поэтому полный -show_streams.

6. Вынести общее тело в `_run_dv_case(tmp_path: Path, fixture: Path, stem: str, expected_out_compat: Optional[int] = None) -> None`:
   - self-check (`_av1_dovi_self_check()`) → pytest.skip с сообщением как сейчас, но упоминающим ENPIPE_TEST_FFPROBE и "point ENPIPE_TEST_FFPROBE at an ffprobe from ffmpeg >= 7 (e.g. a BtbN static build)".
   - src_cfg = _dovi_config_record(fixture); assert src_cfg is not None (фикстура не DV); src_compat = src_cfg["dv_bl_signal_compatibility_id"].
   - src_with_md, src_total = _dv_metadata_frame_count(fixture); assert src_with_md > 0.
   - копия в tmp_path, scenes, out = tmp_path / f"{stem}.av1.mkv", workdir = tmp_path / f"{stem}.chunks"; detect/encode ровно с теми же аргументами, что сейчас в test_dv (включая комментарий про metrics path); assert out.is_file(); `_verify_frame_counts_and_keyframes`.
   - паритет на out: out_with_md == src_with_md and > 0 (сохранить комментарий opencode M1/qwen M3 про source-parity, заменив RPU на DV metadata).
   - паритет на сумме chunk_{i:05d}.obu (как сейчас).
   - конфиг выхода: out_cfg = _dovi_config_record(out); assert not None; assert out_cfg["dv_profile"] == 10 (комментарий: AV1 DV — всегда profile 10; mkvmerge выводит запись из потока, не из --dolby-vision-profile qsvencc); expected = src_compat if expected_out_compat is None else expected_out_compat; assert out_cfg["dv_bl_signal_compatibility_id"] == expected, при этом если expected_out_compat задан — дополнительно assert src_compat == expected_out_compat (sanity: фикстура действительно того профиля, который подразумевает тест). Сообщения ассертов включают src_cfg и out_cfg полностью.

7. `test_dv(tmp_path)`: skip без dv.mkv (сообщение как сейчас) → `_run_dv_case(tmp_path, fixture, "dv")` (compat из исходника, для P8.1 = 1).

8. Новый `test_dv_profile5(tmp_path)`: fixture = _fixture("dv-p5.mkv"); при None — pytest.skip в том же стиле, что test_dv (путь FIXTURES_DIR / 'dv-p5.mkv', ссылка на README, "NOT a failure", D-06), добавив что это DV profile 5 (bl_signal_compatibility_id 0, IPTPQc2 base layer) source. Дополнительно assert исходника dv_profile == 5 (через _dovi_config_record) — можно внутри теста до _run_dv_case либо через параметр; выбрать: в тесте перед вызовом. Затем `_run_dv_case(tmp_path, fixture, "dv-p5", expected_out_compat=0)`. Докстринг: P5 → AV1 profile 10.0 (compat 0); проверяет, что пайплайн не помечает выход как 10.1 HDR10-совместимый.

9. Обновить фрагмент модульного докстринга про DV RPU verification: проверка через read-only `ffprobe -show_frames frame=side_data_list` по "Dolby Vision Metadata" и `-show_streams` по "DOVI configuration record", бинарник проверки — ENPIPE_TEST_FFPROBE; формулировку "Task 2's helpers" можно оставить/уточнить.
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && uv run pytest tests/integration/test_hardware_real_media.py -m hardware --collect-only -q 2>&1 | grep -E "test_dv\b|test_dv_profile5|error" ; uv run pytest -q 2>&1 | tail -3 ; grep -v '^\s*#' tests/integration/test_hardware_real_media.py | grep -c '_dv_rpu_frame_count' | grep -qx 0 && echo OLD_HELPER_GONE ; git diff --quiet -- src/enpipe/encoding/hdr.py && echo HDR_UNCHANGED</automated>
  </verify>
  <done>Collect-only показывает test_dv и test_dv_profile5 без ошибок; быстрый тир (`uv run pytest`) зелёный; _dv_rpu_frame_count удалена; hdr.py не изменён; при дефолтном ENPIPE_TEST_FFPROBE поведение test_hdr10 не меняется.</done>
</task>

<task type="auto">
  <name>Task 2: README фикстур — dv-p5.mkv, ENPIPE_TEST_FFPROBE, что именно считается</name>
  <files>tests/fixtures/media/README.md</files>
  <action>
Обновить README (язык файла — английский, сохранить):
- "Expected filenames": добавить `dv-p5.mkv` — real Dolby Vision profile 5 sample (bl_signal_compatibility_id 0), используется test_dv_profile5; уточнить, что `dv.mkv` — profile 8.1 (HDR10-compatible base layer, compat 1) — ожидаемый вариант, может быть symlink.
- Новый раздел "Verification ffprobe (ENPIPE_TEST_FFPROBE)": DV-проверки требуют ffprobe из ffmpeg >= 7 с AV1 DOVI (libdav1d-декодер экспортирует "Dolby Vision Metadata"; dovi_rpu bsf перечисляет av1); системный ffmpeg 6.1 Ubuntu 24.04 этого не умеет → тесты честно skip. Переменная влияет ТОЛЬКО на проверочные пробы; пайплайн под тестом использует ffmpeg/ffprobe из PATH. Пример: `ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware -k dv` (BtbN static build, ffmpeg сосед ffprobe используется для self-check).
- "What the tests check": переписать пункт test_dv: self-check через ffmpeg рядом с ENPIPE_TEST_FFPROBE; паритет числа кадров с side data "Dolby Vision Metadata" (не "Dolby Vision RPU Data" — эта запись есть только на HEVC-исходнике, на AV1 после libdav1d её нет) на финальном .mkv и сумме pre-mux .obu; плюс DOVI configuration record выхода: dv_profile 10 и dv_bl_signal_compatibility_id равен исходному. Добавить пункт test_dv_profile5: то же самое на dv-p5.mkv, ожидается 10 / compat 0 (P5 → 10.0); запись выводится mkvmerge из потока.
  </action>
  <verify>
    <automated>cd /workspaces/enpipe && grep -c "ENPIPE_TEST_FFPROBE" tests/fixtures/media/README.md && grep -q "dv-p5.mkv" tests/fixtures/media/README.md && grep -q "Dolby Vision Metadata" tests/fixtures/media/README.md && grep -q "test_dv_profile5" tests/fixtures/media/README.md && echo README_OK</automated>
  </verify>
  <done>README описывает dv-p5.mkv, ENPIPE_TEST_FFPROBE (только для проверочных проб), что считается и какие значения конфиг-записи ожидаются.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env → test harness | ENPIPE_TEST_FFPROBE / ENPIPE_TEST_MEDIA задаёт оператор локально |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-hph-01 | Tampering | ENPIPE_TEST_FFPROBE выбирает исполняемый бинарник | accept | локальный тестовый инструмент оператора, вызов списком argv без shell |
| T-hph-02 | Repudiation (ложный pass) | DV-проверки | mitigate | при отсутствии фикстуры/возможности — pytest.skip, никогда не pass; паритет требует > 0 кадров и равенства с исходником; конфиг-запись проверяется явными значениями |
</threat_model>

<verification>
- Быстрый тир зелёный: `uv run pytest -q`.
- `uv run pytest -m hardware --collect-only -q tests/integration/test_hardware_real_media.py` собирает test_dv и test_dv_profile5.
- Опционально (исполнитель может, оркестратор запустит в любом случае; несколько минут на тест, 4K 90 с): `ENPIPE_TEST_MEDIA=/data/downloads/enpipe-fixtures ENPIPE_TEST_FFPROBE=/opt/ffmpeg-9/bin/ffprobe uv run pytest -m hardware -k "dv" -v` — ожидаются 2 passed (test_dv, test_dv_profile5);
- Без ENPIPE_TEST_FFPROBE на системном ffmpeg 6.1.1 оба DV-теста — skip с понятным сообщением.
</verification>

<success_criteria>
- test_dv считает "Dolby Vision Metadata", проверяет паритет на .mkv и .obu и конфиг 10/compat исходника.
- test_dv_profile5 существует, честно скипается без dv-p5.mkv, проверяет 10/0.
- Проверочный ffprobe переопределяется ENPIPE_TEST_FFPROBE; пайплайн остаётся на PATH-стеке; hdr.py не тронут.
- README актуален.
</success_criteria>

<output>
Создать `.planning/quick/261003-hph-dv-test-dv-dolby-vision-metadata-ffmpeg-/261003-hph-SUMMARY.md` по завершении.
</output>
