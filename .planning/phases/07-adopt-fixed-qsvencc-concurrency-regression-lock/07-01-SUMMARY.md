---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
plan: 01
subsystem: infra
tags: [qsvencc, release-mirror, supply-chain, sha256]
requires: []
provides:
  - "GitHub Release deps-qsvencc-r4634 (prerelease) с ассетом qsvencc_8.31-r4634_amd64.deb"
  - "Проверенный распакованный бинарник r4634 в /tmp/enpipe-phase7/r4634/ (для 07-05, если devcontainer не пересобран)"
affects: [07-03, 07-05]
tech-stack:
  added: []
  patterns: ["зеркало внешнего бинарника в собственный Release + sha256-пин"]
key-files:
  created: []
  modified: []
key-decisions:
  - "Релиз создан из devcontainer через gh пользователя (пользователь авторизовал gh и попросил сделать это Claude), а не на хосте"
requirements-completed: [QSV-01]
duration: 10min
completed: 2026-10-02
---

# Phase 7 Plan 01: Зеркало qsvencc r4634 Summary

Ночной .deb апстрима (rigaya/QSVEnc 45003f1, run 36932190976) зеркалирован в Release `deps-qsvencc-r4634` нашего репозитория. Анонимная загрузка зеркала побайтно совпадает с пином.

## Tasks

| # | Задача | Результат |
|---|--------|-----------|
| 1 | Подготовка файла + создание Release | nightly.link zip скачан, sha256/размер/ревизия проверены до загрузки; `gh release create deps-qsvencc-r4634 --prerelease` выполнен 2026-10-02 (до дедлайна 2026-10-15) |
| 2 | Анонимная проверка зеркала | OK (см. доказательства ниже) |

## Evidence

- URL зеркала: https://github.com/Tualua/enpipe/releases/download/deps-qsvencc-r4634/qsvencc_8.31-r4634_amd64.deb
- Страница: https://github.com/Tualua/enpipe/releases/tag/deps-qsvencc-r4634 (isPrerelease: true, один ассет, 30081716 байт)
- `curl -fsSL` без токена → `sha256sum -c`: `/tmp/enpipe-phase7/mirror.deb: OK`
- sha256: `aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d`, размер 30081716
- `dpkg-deb -f Depends`: `libc6 (>= 2.31), libva-drm2, libva-x11-2, intel-media-va-driver-non-free | intel-media-va-driver | i965-va-driver | va-driver` — нет `intel-opencl-icd` и `libmfx1` (D-05)
- `usr/bin/qsvencc --version` (первая строка): `QSVEncC (x64) 8.31 (r4634) by rigaya, Oct  1 2026 22:01:56 (gcc 9.4.0/Linux)`
- Распакованное дерево: `/tmp/enpipe-phase7/r4634/` (может исчезнуть при рестарте контейнера — тогда 07-05 перекачивает и перепроверяет)

## Residual notes

- (a) Ассет Release мутабелен после этой проверки, но пин `ARG QSVENCC_SHA256` из 07-03 перепроверяет дайджест при каждой сборке образа: подменённый ассет громко ломает сборку, а не протекает в образ.
- (b) Сборки образов (локальная и `docker-publish.yml`) теперь зависят от анонимной доступности этого ассета: удалённый релиз или переименованный репозиторий дают fail-closed ошибку сборки.

## Deviations

- Задача 1 по плану предполагала загрузку пользователем на хосте; пользователь авторизовал `gh` в devcontainer и попросил создать пререлиз самостоятельно. Токен в репозиторий/файлы плана не попадал (T-07-03 соблюдён по сути).

## Self-Check: PASSED
