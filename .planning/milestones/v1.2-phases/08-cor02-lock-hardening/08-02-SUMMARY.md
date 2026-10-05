---
phase: 08-cor02-lock-hardening
plan: 02
subsystem: packaging
status: complete
tags: [docker, podman, ubuntu-24.04, intel-ppa, opencl, metrics]
requires: []
provides:
  - рантайм-образ на ubuntu:24.04 + Intel PPA (intel-opencl-icd) с самопроверкой D-07
  - fast-tier страж структуры рантайм-Dockerfile
  - docker/README.md: метрики, проверка на хосте (docker и rootless Podman), переход с trixie
affects: [999.4]
key-files:
  created:
    - tests/unit/shared/test_runtime_dockerfile.py
  modified:
    - Dockerfile
    - docker/README.md
    - CLAUDE.md
key-decisions:
  - "Проверка образа на хосте выполнена rootless Podman, а не docker: на NAS с A380 docker нет; нужны --group-add keep-groups и :Z у тома"
  - "Образ проверен уже с qsvencc 8.32 (r4658, форк vppsync4, quick 261003-8qq), а не r4634 из плана"
metrics:
  completed: 2026-10-03
---

# Phase 08 Plan 02: рантайм-образ на Ubuntu 24.04 + Intel PPA — SUMMARY

Корневой `Dockerfile` переведён с `python:3.12-slim-trixie` на `ubuntu:24.04` +
PPA `kobuk-team/intel-graphics` (deb822, ключ по закреплённому отпечатку), чтобы
путь по умолчанию с `--psnr --ssim` в образе работал (OpenCL). Самопроверка
D-07 выполняется при сборке. На хосте с A380 образ подтверждён: OpenCL видит
GPU, `enpipe run` с метриками даёт rc=0 и CSV с SSIM/PSNR с первой попытки.

## Задачи

| Задача | Коммит | Что |
|---|---|---|
| 1 (RED) | 3999143 | `tests/unit/shared/test_runtime_dockerfile.py` — страж баз, PPA, отпечатка ключа, пакетов, самопроверки |
| 1 (GREEN) | 9e0a827 | `Dockerfile` на ubuntu:24.04 + PPA, самопроверка D-07 (путь библиотеки из ICD-файла) |
| 2 | 7591226 | `docker/README.md` и `CLAUDE.md`: метрики на 24.04, проверка на хосте, переход с trixie |
| 3 (чекпоинт) | — | проверка пользователем на хосте (ниже) + раздел Podman в README |

## Чекпоинт D-07/D-14 (хост NAS, A380, rootless Podman, 2026-10-03)

Сборка `podman build -t enpipe:ubuntu2404 .` (без `--secret`) прошла; самопроверка:

```
+ lib=/usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so
+ test -e /usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so
/usr/bin/clinfo
QSVEncC (x64) 8.32 (r4658) by rigaya, Oct  3 2026 05:55:43 (gcc 9.4.0/Linux)
```

Шаг 2, `clinfo -l`:

```
Platform #0: Intel(R) OpenCL Graphics
 `-- Device #0: Intel(R) Arc(TM) A380 Graphics
```

Шаг 3, стек:

```
vainfo: Driver version: Intel iHD driver for Intel(R) Gen Graphics - 26.3.2 ()
intel-media-va-driver-non-free:amd64    26.3.2-1~24.04~ppa1
intel-opencl-icd        26.31.39395.14-1~24.04~ppa1
libmfx-gen1.2   26.3.2-1~24.04~ppa1
QSVEncC (x64) 8.32 (r4658)
ffmpeg hwaccels с qsv: 1
```

Шаг 4, `enpipe run` с метриками (testsrc 640x360, 240 кадров, 1 сцена):
**попыток: 1**, `rc=0`, склейка 240 кадров, CSV:

```
scene,start_frame,end_frame,frames,seek,trim,encode_sec,fps,size_mb,ssim_all,ssim_db,psnr_avg,ssim_y,psnr_y
0,0,240,240,00:00:00.000,0:239,5.48,43.8,0.07,0.998991,29.96021,54.760158,0.999282,56.393794
ИТОГО,,,240,,,5.5,,0.1,0.99899,29.95679,54.76016,0.99928,56.39379
```

Критерий D-14 выполнен: сборка прошла, `clinfo -l` видит A380, первая же
попытка с метриками дала rc=0 и `ИТОГО` с SSIM/PSNR.

## Отклонения от плана

1. **Podman вместо docker.** На хосте с A380 есть только rootless Podman.
   Команды адаптированы: `--secret` не нужен (`required=false`), к `run`
   добавлен `--group-add keep-groups` (иначе теряется группа `render`), к тому
   `:Z` (SELinux). В `docker/README.md` добавлен подраздел «Podman (rootless)».
2. **Бинарь qsvencc r4658 вместо r4634.** Между задачами 1–2 и чекпоинтом
   quick 261003-8qq перевела оба Dockerfile на 8.32+vppsync4 (форк
   Tualua/QSVEnc). Ожидаемая строка сборки соответственно `8.32 (r4658)`.

## Замечено попутно (не исправлялось)

В строке `ИТОГО` `ssim_db` = 29.95679 вычислен из округлённого `ssim_all`
(0.99899), тогда как строка сцены даёт 29.96021 из 0.998991. Расхождение
~0.003 дБ — артефакт округления в агрегации (quick 261003-8fs), на
корректность кодирования не влияет.

## Self-Check: PASSED

- `tests/unit/shared/test_runtime_dockerfile.py` + `test_qsvencc_threshold_sync.py`: 14 passed
- Коммиты 3999143, 9e0a827, 7591226 присутствуют в истории
