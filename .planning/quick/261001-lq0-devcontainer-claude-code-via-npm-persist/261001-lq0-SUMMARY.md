---
phase: quick-261001-lq0
plan: 01
status: complete
date: 2026-10-01
files_modified:
  - .devcontainer/devcontainer.json
  - .devcontainer/devcontainer-lock.json
  - .devcontainer/post-create.sh
---

# Quick 261001-lq0 — claude-code через npm + персистентные авторизации AI-CLI

## Что сделано

**1. claude-code ставится npm'ом, а не devcontainer-фичей.**
Из `devcontainer.json` убрана `ghcr.io/anthropics/devcontainer-features/claude-code:1`
(осталась только `node:2`), из `devcontainer-lock.json` — её pin. В `post-create.sh`
секция 2 стала `npm install -g @anthropic-ai/claude-code opencode-ai @qwen-code/qwen-code`.

Переход безопасен, потому что фича делала ровно то же: осмотр работающего контейнера
показал `.../nvm/versions/node/v24.18.0/bin/claude -> ../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`,
т.е. тот же npm-пакет в том же nvm-префиксе. Выигрыш — все три AI-CLI в одной строке,
на один pin меньше и сборка не зависит от доступности ghcr. Версии не пинятся
сознательно, как у opencode/qwen.

**2. Авторизации claude/opencode/qwen переживают ребилд.**
Добавлены 4 named volume'а в `mounts`:

| Том | Точка монтирования | Что держит |
|-----|--------------------|------------|
| `enpipe-claude` | `/root/.claude` | `.credentials.json` (OAuth), `.claude.json`, плагины, settings |
| `enpipe-qwen` | `/root/.qwen` | `settings.json` (`env.DASHSCOPE_API_KEY`), `oauth_creds.json` |
| `enpipe-opencode-data` | `/root/.local/share/opencode` | `auth.json` (провайдер+ключ), сессионная БД |
| `enpipe-opencode-config` | `/root/.config/opencode` | `opencode.jsonc`, плагины |

Локации кредов установлены осмотром работающего контейнера, не по памяти.

## Главное инженерное решение: `CLAUDE_CONFIG_DIR` вместо symlink

Claude Code держит состояние в ДВУХ местах: каталог `~/.claude` и **отдельный файл**
`~/.claude.json` (`oauthAccount`, onboarding-флаги). Named volume монтируется только
на каталог, поэтому сам файл томом не прикрыть.

Очевидный ход — symlink `~/.claude.json -> ~/.claude/.claude.json` — **ловушка**.
В бинарнике есть `saveConfigWithLock`, т.е. конфиг пишется атомарно (temp + `rename()`),
а `rename()` ЗАМЕНЯЕТ симлинк обычным файлом. Персистентность сломалась бы молча,
после первой же записи, и проявилась бы только повторным запросом `/login`.

Вместо этого задан официальный `CLAUDE_CONFIG_DIR=/root/.claude` в `containerEnv`.
Проверено эмпирически, а не по документации: `CLAUDE_CONFIG_DIR=<tmp> claude plugin list`
создал `<tmp>/.claude.json` и `<tmp>/backups/` — переменная переносит и config-каталог,
и `.claude.json`. Значение совпадает с дефолтным путём каталога, так что меняется ровно
одно: `.claude.json` переезжает ВНУТРЬ тома.

Секция 2a `post-create.sh` делает разовую миграцию старого `$HOME/.claude.json` на новое
место. Она идемпотентна и **никогда не перезаписывает** уже персистентный конфиг: если
приёмник существует, исходник остаётся на месте с предупреждением (затереть рабочую
авторизацию хуже, чем оставить мусорный файл).

## Самопроверка (почему не просто grep)

В самопроверку добавлен блок с флагом `PERSIST_OK` и сводной строкой в конце — в стиле
существующего `ENV01_OK`, best-effort, без mid-script `exit 1`. По каждому пути
проверяются две независимые вещи:

- **том** (`findmnt`) — реально ли путь отдельная точка монтирования. Если нет, тома из
  `devcontainer.json` не подхватились (контейнер ещё не пересобран), и креды снова
  потеряются. Это молчаливый отказ, заметный иначе только по повторному `/login`.
- **креды** — есть ли файл. Отсутствие НЕ ошибка (свежий том = ещё не логинились).

Плюс отдельный варнинг, если `$HOME/.claude.json` оказался ВНЕ тома —
признак, что `CLAUDE_CONFIG_DIR` не применился.

## Верификация

Пересобрать контейнер изнутри него нельзя (`docker`/`podman` недоступны), поэтому всё
проверялось статически и в песочнице:

- `bash -n .devcontainer/post-create.sh` — OK
- `devcontainer.json` распарсен (JSONC): `features == ["…/node:2"]`,
  `containerEnv.CLAUDE_CONFIG_DIR == "/root/.claude"`, ровно 4 `type=volume`-маунта
- `devcontainer-lock.json` — валидный JSON, записи claude-code нет
- `npm view @anthropic-ai/claude-code version` → `2.1.286` (имя в реестре верно, реестр доступен)
- **Блок миграции прогнан в песочничном `HOME` во всех 4 ветках** (извлечён из реального
  файла, не копия, под `set -euo pipefail`):
  - только `$HOME/.claude.json` → перенесён в том
  - оба файла есть → исходник НЕ тронут, варнинг
  - ничего нет → «нечего переносить»
  - `CLAUDE_CONFIG_DIR == $HOME` → миграция пропущена, файл не тронут
  - двойной прогон подряд → идемпотентен, содержимое не повреждено
- **`findmnt` на не-mountpoint проверен отдельно** (`rc=1` на `/root/.qwen`,
  `/root/.claude`, несуществующем пути; `rc=0` на реальном bind-mount `/data/media`) —
  родителя не резолвит, значит проверка тома не даёт ложного OK
- Реальный `/root/.claude.json` после всех тестов на месте

## Что НЕ проверено здесь (делает пользователь на хосте)

Сам ребилд и рантайм. Чек-лист — в `261001-lq0-PLAN.md`, секция `<rebuild_checklist>`.

**Важно:** тома создаются ПУСТЫМИ — старый writable-слой в них не переносится. Поэтому
либо один раз залогиниться заново после ребилда, либо ЗАРАНЕЕ (из текущего контейнера)
снять tar на `/data/downloads` (bind-mount хоста, ребилд переживает) и распаковать обратно.
Команды — в чек-листе плана.
