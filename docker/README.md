# enpipe — слим-рантайм-образ

Это отдельный компактный образ для ПРОДОВОГО запуска `enpipe run` (не
dev-контейнер — тот описан в `.devcontainer/`). Собирается и запускается
пользователем на ХОСТЕ с `docker`/`podman` и Intel Arc GPU.

## Сборка

```bash
docker build -t enpipe:slim .
```

(с `podman` — команда аналогична: `podman build -t enpipe:slim .`)

Контекст сборки минимизирован через `.dockerignore` — образу реально нужны
только `pyproject.toml`, `uv.lock` и `src/`; остальное (доки, тесты,
`.planning/`, `legacy/`, `.devcontainer/`) в контекст не попадает.

## Запуск

```bash
docker run --rm --device /dev/dri \
  --group-add "$(stat -c '%g' /dev/dri/renderD128)" \
  -v /path/in:/data -v /path/out:/out \
  enpipe:slim run --no-metrics -o /out /data/movie.mkv
```

Пояснение флагов:

- `--device /dev/dri` — проброс Intel Arc GPU в контейнер для QSV/VA-API;
  без него аппаратный декод/энкод не работает вовсе.
- `--group-add "$(stat -c '%g' /dev/dri/renderD128)"` — добавляет процессу в
  контейнере GID render-группы ХОСТА, чтобы был доступ к узлу `/dev/dri`
  (аналог того, что делает `post-create.sh` в devcontainer при добавлении
  пользователя в render-группу).
- `-v /path/in:/data -v /path/out:/out` — тома со входным видео и
  директорией для результата.
- `ENTRYPOINT` образа уже `enpipe`, поэтому в команде сразу идёт подкоманда
  (`run ...`, `detect ...`, `encode ...`) — не нужно писать `enpipe run`.

## CI / публикация

Образ публикуется в GHCR автоматически по git-тегу `v*` и вручную (manual
dispatch) воркфлоу `.github/workflows/docker-publish.yml`, как
`ghcr.io/tualua/enpipe:<version>` и `:latest`.

Пример pull:

```bash
docker pull ghcr.io/tualua/enpipe:latest
```

Публикацию выполняет CI-раннер штатным `GITHUB_TOKEN` — заводить и
настраивать отдельный секрет не нужно.

Локально, если хотите, чтобы ВАША сборка авторизовалась к GitHub API
(выше лимит запросов, без 403 на общих IP — см. раздел "Опциональная
авторизация" в комментариях `Dockerfile`), передайте токен как
BuildKit-секрет:

```bash
DOCKER_BUILDKIT=1 docker build --secret id=github_token,env=GITHUB_TOKEN -t enpipe:slim .
```

Секрет опционален (`required=false`) — обычный `docker build` без него
ведёт себя ровно как раньше. Современный Docker включает BuildKit по
умолчанию; на старых движках нужен явный `DOCKER_BUILDKIT=1`.

## Метрики (PSNR/SSIM)

Флаги `--psnr`/`--ssim` требуют OpenCL-VPP-фильтр `qsvencc`, а в Debian
trixie пакета `intel-opencl-icd` нет (как и в `.devcontainer/Dockerfile`) —
эти метрики в данном образе НЕ работают. Для прод-энкода используйте
`--no-metrics`.

## Почему `python:3.12-slim-trixie`

Trixie выбран ради glibc >= 2.39, требуемого prebuilt-сборкой `qsvencc`;
Debian bookworm (glibc 2.36) для этого не годится — та же причина, что и в
`.devcontainer/Dockerfile`.

## Честная ремарка про эту среду

В окружении, где писался этот образ, нет `docker`/`podman` — сам образ
здесь НЕ собирался и НЕ запускался. Финальную сборку и прогон на реальном
Intel Arc GPU выполняет пользователь на хосте.
