---
phase: quick-261113-msb
plan: 01
subsystem: devcontainer
tags: [devcontainer, locale, mkvmerge, gsd-core]
status: complete
requirements: [QUICK-261113-msb]
key-files:
  modified:
    - .devcontainer/Dockerfile
    - .devcontainer/post-create.sh
actuals:
  tokens: 1500
  tasks: 2
  commits: 2
plan_head_before: 817323fc3f020a6f4a366bd47d238d4fdc744e58
plan_head_after: 0363e65007ce384107e8e0d12c525440267aec7a
---

# Quick 261113-msb: локаль en_US.UTF-8 в devcontainer и плагин open-gsd/gsd-core

**Итог:** в первый apt-блок `.devcontainer/Dockerfile` добавлены `locales` и `locale-gen en_US.UTF-8` (в том же RUN, до очистки списков apt), а `post-create.sh` ставит GSD только из `open-gsd/gsd-core`.

## Что сделано

1. **Dockerfile (коммит 61acdec).** `locales` стоит рядом с `libatomic1`, `locale-gen en_US.UTF-8` вызывается в том же RUN. Добавлен русский комментарий с причиной (mkvmerge rc=134 при LANG=en_US.UTF-8). Незакоммиченная правка `libatomic1` вошла в этот же коммит без изменений. `ENV LANG` не добавлялся, корневой `Dockerfile` не тронут.
2. **post-create.sh (коммит 0363e65).** Секция 2b теперь делает `marketplace add open-gsd/gsd-core` и `install gsd-core@gsd-core`. Самопроверка ищет `gsd-core`. Упоминаний `jnuyens` и `gsd-plugin` не осталось.

## Отклонения от плана

Коммитов два (по одному на задачу), а не один, как в критериях успеха плана. Так требовали ограничения запуска (атомарный коммит каждой задачи). Других отклонений нет.

## Проверка

Статическая проверка обеих задач (`<automated>` из плана) выдала OK, `bash -n` проходит. Пересборку контейнера я не запускал.

## Проверка оператором после пересборки

```bash
locale -a | grep -i en_US
mkvmerge --version; echo rc=$?
claude plugin list | grep -i gsd-core
```

Ожидается: `en_US.utf8` в списке локалей, `rc=0` у mkvmerge при `LANG=en_US.UTF-8`, `gsd-core` в списке плагинов.

## Known Stubs

Нет.

## Self-Check: PASSED

Файлы `.devcontainer/Dockerfile` и `.devcontainer/post-create.sh` изменены, коммиты 61acdec и 0363e65 присутствуют в истории.
