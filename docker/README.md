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
