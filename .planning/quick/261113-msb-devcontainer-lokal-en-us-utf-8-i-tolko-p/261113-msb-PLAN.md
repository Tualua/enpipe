---
phase: quick-261113-msb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .devcontainer/Dockerfile
  - .devcontainer/post-create.sh
autonomous: true
requirements: [QUICK-261113-msb]

estimate:
  tokens: 15000
  raw_tokens: 15000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "После пересборки devcontainer `locale -a` содержит en_US.utf8, и `mkvmerge --version` при LANG=en_US.UTF-8 не падает с rc=134 (проверяет оператор после пересборки)"
    - "Первый apt-блок .devcontainer/Dockerfile ставит libatomic1 и locales; en_US.UTF-8 генерируется в том же RUN"
    - "post-create.sh добавляет только маркетплейс open-gsd/gsd-core и ставит только плагин gsd-core@gsd-core; ссылок на jnuyens/gsd-plugin и gsd@gsd-plugin нет"
    - "Самопроверка post-create.sh ищет именно gsd-core в `claude plugin list`"
    - "Рантайм-образ Dockerfile (корень репо) не изменён"
  artifacts:
    - path: ".devcontainer/Dockerfile"
      provides: "locales + locale-gen en_US.UTF-8 + libatomic1 в первом apt-блоке"
    - path: ".devcontainer/post-create.sh"
      provides: "секция 2b: open-gsd/gsd-core, gsd-core@gsd-core; самопроверка по gsd-core"
  key_links:
    - from: "LANG=en_US.UTF-8 (приходит от devcontainer CLI/VS Code)"
      to: "/usr/lib/locale (сгенерированная en_US.UTF-8)"
      via: "locale-gen в .devcontainer/Dockerfile"
      pattern: "locale-gen en_US.UTF-8"
---

<objective>
Починить devcontainer: (1) сгенерировать локаль en_US.UTF-8, чтобы mkvmerge (а за ним enpipe-мукс и `mux_source_args`) не падал с `locale::facet::_S_create_c_locale name not valid` (rc=134) при LANG=en_US.UTF-8; заодно закоммитить уже лежащую в рабочем дереве правку libatomic1 в том же apt-блоке. (2) В post-create.sh заменить GSD-плагин Buildomator (`jnuyens/gsd-plugin`, `gsd@gsd-plugin`) на `open-gsd/gsd-core` / `gsd-core@gsd-core` — только его.

Purpose: devcontainer на новой базе intel/dlstreamer:latest потерял пакеты; без локали мукс в dev-окружении умирает.
Output: правки `.devcontainer/Dockerfile` и `.devcontainer/post-create.sh`, один коммит.

Пересборку контейнера НЕ запускать — её делает оператор. Проверка исполнителя — только статическая.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.devcontainer/Dockerfile
@.devcontainer/post-create.sh

Факты (проверено в текущем контейнере 2026-11-13):
- LANG=en_US.UTF-8 задан не в devcontainer.json/Dockerfile проекта и не в /proc/1/environ — приходит от devcontainer CLI/VS Code.
- `locale -a` = C, C.utf8, POSIX. `mkvmerge --version` / `mkvmerge -J` при этом падают rc=134; с `LANG=C.UTF-8` работают.
- В рабочем дереве уже есть незакоммиченная правка `.devcontainer/Dockerfile`: строка `libatomic1 \` в первом apt-блоке (строки ~27–31) с русским комментарием. Её сохранить как есть и закоммитить вместе с этой задачей.
- Корневой `Dockerfile` (ubuntu:24.04, рантайм) не трогать: там LANG не задан, mkvmerge работает в C.
- post-create.sh: секция 2b — строки ~78–81; самопроверка GSD — строка ~188 (`claude plugin list 2>/dev/null | grep -qi gsd`).
</context>

<tasks>

<task type="auto">
  <name>Задача 1: локаль en_US.UTF-8 в .devcontainer/Dockerfile (+ libatomic1 из рабочего дерева)</name>
  <files>.devcontainer/Dockerfile</files>
  <action>
В ПЕРВОМ apt-блоке (`RUN apt-get update && apt-get install -y --no-install-recommends ...`, где уже стоит незакоммиченная строка `libatomic1 \`) добавить пакет `locales` отдельной строкой рядом с `libatomic1`. В том же RUN, после `apt-get install` и ДО `rm -rf /var/lib/apt/lists/*`, добавить генерацию локали: `&& locale-gen en_US.UTF-8` (на Ubuntu 24.04 `locale-gen` с аргументом сам дописывает запись и генерирует; если исполнитель предпочтёт явный путь — раскомментировать `en_US.UTF-8 UTF-8` в /etc/locale.gen через sed и затем вызвать `locale-gen`; любой вариант допустим, но генерация должна быть в этом же RUN, отдельный слой не заводить).

Правку libatomic1 и её комментарий не менять и не переносить.

В блок русских комментариев над этим RUN (после абзаца про libatomic1) добавить абзац по-русски: locales + locale-gen en_US.UTF-8 — devcontainer CLI/VS Code прокидывают LANG=en_US.UTF-8, а в dlstreamer:latest локали нет (`locale -a` = C, C.utf8, POSIX); mkvmerge (libstdc++ std::locale) тогда падает «locale::facet::_S_create_c_locale name not valid», rc=134, и enpipe-мукс умирает. Рантайм-образ (корневой Dockerfile) не затронут — там LANG не задан, mkvmerge работает в C.

`ENV LANG`/`ENV LC_ALL` НЕ добавлять (в задаче не просили; LANG уже приходит снаружи). Корневой `Dockerfile` не трогать. Сборку образа не запускать.
  </action>
  <verify>
    <automated>grep -v '^\s*#' .devcontainer/Dockerfile | grep -qE '^\s+locales \\$' && grep -v '^\s*#' .devcontainer/Dockerfile | grep -q 'locale-gen' && grep -v '^\s*#' .devcontainer/Dockerfile | grep -qE '^\s+libatomic1 \\$' && ! grep -qE '^ENV (LANG|LC_ALL)' .devcontainer/Dockerfile && git diff --quiet -- Dockerfile && echo OK</automated>
  </verify>
  <done>Первый apt-блок .devcontainer/Dockerfile содержит libatomic1 и locales, в том же RUN вызывается locale-gen для en_US.UTF-8 до очистки списков apt; есть русский комментарий с причиной; ENV LANG не добавлен; корневой Dockerfile без изменений.</done>
</task>

<task type="auto">
  <name>Задача 2: post-create.sh — только open-gsd/gsd-core (gsd-core@gsd-core)</name>
  <files>.devcontainer/post-create.sh</files>
  <action>
Секция 2b (строки ~78–81): заменить целиком.
- Заголовок-комментарий по-русски: `# --- 2b) Claude Code: плагин GSD (маркетплейс open-gsd/gsd-core, плагин gsd-core) ---`.
- echo: `-- claude plugin: open-gsd/gsd-core --`.
- `claude plugin marketplace add open-gsd/gsd-core || echo "   marketplace add не удался (сеть?)"`.
- `claude plugin install gsd-core@gsd-core || echo "   install gsd-core@gsd-core не удался"`.
Ни маркетплейс jnuyens/gsd-plugin, ни плагин gsd@gsd-plugin больше не упоминать (в т.ч. в комментариях); удаление старого плагина в уже существующем томе не добавлять — в задаче не просили.

Самопроверка (строка ~188): заменить `grep -qi gsd` на `grep -qi gsd-core`, подпись `GSD-плагин:` поменять на `GSD-плагин (gsd-core):`; сообщения «установлен»/«не найден» оставить по-русски.

Остальной скрипт не трогать. Не запускать post-create.sh и `claude plugin ...` — только статическая проверка.
  </action>
  <verify>
    <automated>bash -n .devcontainer/post-create.sh && grep -q 'claude plugin marketplace add open-gsd/gsd-core' .devcontainer/post-create.sh && grep -q 'claude plugin install gsd-core@gsd-core' .devcontainer/post-create.sh && grep -q 'grep -qi gsd-core' .devcontainer/post-create.sh && ! grep -qE 'jnuyens|gsd-plugin' .devcontainer/post-create.sh && echo OK</automated>
  </verify>
  <done>`bash -n` проходит; секция 2b ставит только open-gsd/gsd-core и gsd-core@gsd-core; строк jnuyens/gsd-plugin нет; самопроверка ищет gsd-core; все комментарии и echo по-русски.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| сеть → сборка devcontainer | apt-пакеты из репозиториев Ubuntu; плагин Claude Code из GitHub-маркетплейса |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-261113msb-01 | Tampering | apt: locales, libatomic1 | low | accept | Официальные пакеты main Ubuntu 24.04, подписанные apt-ключом дистрибутива; dev-образ, не рантайм |
| T-261113msb-02 | Tampering | claude plugin marketplace open-gsd/gsd-core | medium | accept | Источник выбран оператором явно (тот же GSD-ядро, которым ведётся проект); только dev-контейнер, в рантайм-образ не попадает |
| T-261113msb-SC | Tampering | npm/pip/cargo installs | low | accept | В задаче нет установок через npm/pip/cargo — гейт легитимности пакетов не применим |
</threat_model>

<verification>
- `bash -n .devcontainer/post-create.sh` — без ошибок.
- `git diff --stat` затрагивает только `.devcontainer/Dockerfile` и `.devcontainer/post-create.sh` (плюс артефакты .planning/quick/261113-msb-*).
- Корневой `Dockerfile` не изменён.
- Динамическая проверка — за оператором после пересборки: `locale -a | grep -i en_US`, `mkvmerge --version; echo rc=$?`, `claude plugin list | grep -i gsd-core`.
</verification>

<success_criteria>
- Оба `<automated>` выводят OK.
- Один коммит включает правку libatomic1 из рабочего дерева, locales/locale-gen и замену GSD-плагина.
- Пересборка контейнера не запускалась исполнителем.
</success_criteria>

<output>
Create `.planning/quick/261113-msb-devcontainer-lokal-en-us-utf-8-i-tolko-p/261113-msb-SUMMARY.md` when done. В SUMMARY привести готовые команды проверки для оператора после пересборки (без python-однострочников): `locale -a`, `mkvmerge --version; echo rc=$?`, `claude plugin list`.
</output>
