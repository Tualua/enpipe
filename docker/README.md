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

Образ на Ubuntu 24.04 + PPA `kobuk-team/intel-graphics` содержит
`intel-opencl-icd`, поэтому `--psnr`/`--ssim` работают.

Закреплён форк qsvencc `8.32+vppsync7` (r4665): он несёт патчи #319/#320
(на r4658 в матрице фазы 8 получено 0 отказов `METRICS_FAILED` из 640
конкурентных сессий) и исправление `--seek` (старт с первого keyframe на или
после цели; старые сборки стартуют на один GOP позже) и `--trim` на open-GOP
источниках (RASL больше не входят в trim offset). Рантайм-гейт и образ
отказываются работать со сборками старше r4665. Отказы `VIDEOMETRIC: Failed to copy input surface` (rc != 0, чанк
теряется) из дефекта D-12 относятся к r4634 и апстримному 8.32. Если они
появились снова, значит, в образ попала сборка без патчей #319/#320. Проверьте
`qsvencc --version`: ожидается `8.32 (r4665)`.

## Почему `ubuntu:24.04`

- PPA Intel с OpenCL для Arc (`intel-opencl-icd`), без которого метрики не
  работают;
- glibc 2.39 требуется .deb-сборке `qsvencc`;
- тот же стек, что в девконтейнере.

Обе стадии сборки на одной базе: venv хранит ссылку на интерпретатор,
которым создан, поэтому у builder и runtime должен быть один и тот же
`/usr/bin/python3.12`. PPA подключается deb822-файлом `.sources`, ключ
скачивается по закреплённому отпечатку и сверяется до записи в keyring.

## Проверка на хосте

На хосте с Intel Arc, в корне чекаута:

```bash
DOCKER_BUILDKIT=1 docker build --secret id=github_token,env=GITHUB_TOKEN -t enpipe:ubuntu2404 .
docker run --rm --device /dev/dri --entrypoint clinfo enpipe:ubuntu2404 -l
docker run --rm --device /dev/dri --entrypoint sh enpipe:ubuntu2404 -c \
  'vainfo 2>&1 | grep -i "driver version"; dpkg-query -W intel-opencl-icd intel-media-va-driver-non-free libmfx-gen1.2; qsvencc --version | head -1'
```

`clinfo -l` должен показать `Intel(R) Arc(TM) A380 Graphics`. Затем короткий
прогон с метриками: сгенерировать 10-секундный
`testsrc` через ffmpeg и выполнить `enpipe run s.mkv -o s.av1.mkv --no-audio`.
Успех: `rc=0` и в `s.av1.mkv.metrics.csv` строка `ИТОГО` с `ssim_all`/`psnr_avg`.

### Podman (rootless)

Сборка и запуск те же, с тремя отличиями:

```bash
podman build -t enpipe:ubuntu2404 .
podman run --rm --device /dev/dri --group-add keep-groups --entrypoint clinfo enpipe:ubuntu2404 -l
mkdir -p /tmp/enpipe-ck && podman run --rm --device /dev/dri --group-add keep-groups \
  -v /tmp/enpipe-ck:/w:Z --entrypoint sh enpipe:ubuntu2404 -c \
  'ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc=duration=10:size=640x360:rate=24 -pix_fmt yuv420p -c:v libx264 /w/s.mkv && enpipe run /w/s.mkv -o /w/s.av1.mkv --workdir /w/wd --no-audio; echo rc=$?; cat /w/s.av1.mkv.metrics.csv'
```

- `--secret` не нужен: секрет `github_token` объявлен `required=false`, репозиторий
  публичный. Передать его (`--secret id=github_token,env=GITHUB_TOKEN`) стоит
  только при упоре в лимиты загрузки с github.com.
- `--group-add keep-groups`: rootless Podman (crun) иначе сбрасывает членство
  в группе `render`, и `/dev/dri/renderD128` в контейнере не открывается
  (тот же флаг, что в `.devcontainer/devcontainer.json`).
- `:Z` у тома: на хостах с SELinux без перемаркировки контейнер не пишет в
  bind-mount. Если устройство всё равно не видно, добавить
  `--security-opt label=disable`.

Проверено на A380 (NAS, rootless Podman, 2026-10-03): `clinfo -l` видит A380,
`enpipe run` с метриками — rc=0 с первой попытки.

## Переход с образа на Debian trixie

Что изменилось:

- база `ubuntu:24.04` вместо образа на Debian trixie;
- интерпретатор `/usr/bin/python3.12` вместо `/usr/local/bin/python3.12`
  (кто запускал контейнер со своим `--entrypoint` и путём к python, должен
  сменить путь);
- venv по-прежнему `/opt/venv`, `ENTRYPOINT ["enpipe"]` и CLI без изменений;
- `--psnr`/`--ssim` теперь работают, `--no-metrics` больше не обязателен
  (на форке (измерено на r4658) метрики стабильны, см. раздел о метриках выше).

Теги: `latest` и новые semver/sha-теги указывают на образ Ubuntu; образы на
trixie остаются доступны по прежним semver и `sha-<коммит>` тегам и больше не
обновляются. Требования к хосту прежние: `--device /dev/dri`, Intel Arc.

## Честная ремарка про эту среду

В окружении, где писался этот образ, нет `docker`/`podman` — сам образ
здесь НЕ собирался и НЕ запускался. Финальную сборку и прогон на реальном
Intel Arc GPU выполняет пользователь на хосте.
