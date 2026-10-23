# Quick 261023-gpq: перепин ffmpeg BtbN на месячную сборку Summary

**Пин ffmpeg в обоих Dockerfile переведён на autobuild-2026-09-30-13-08 (n9.0.2-17-g2a571b6068), сохраняемую месячную сборку BtbN, с комментарием о политике пина.**

## Commits
- 6ce07be: Dockerfile, .devcontainer/Dockerfile (ARG FFMPEG_URL/FFMPEG_SHA256 + комментарии)
- 0fb1639: .planning/codebase/CONCERNS.md, docker/README.md

## Результаты проверок
- grep старых тега/хеша в обоих Dockerfile пуст; ARG в двух файлах идентичны (diff).
- `uv`/`pytest` в окружении отсутствуют, поэтому страж test_ffmpeg_pin_sync.py не запускался; синхронность проверена diff по строкам `^ARG FFMPEG_`.
- `podman build -f Dockerfile`: шаг ffmpeg ПРОШЁЛ (`/tmp/ffmpeg.tar.xz: OK`, `ffmpeg version n9.0.2-17-g2a571b6068-20260930`).
- Сборка в целом ПАДАЕТ на шаге `RUN enpipe --help >/dev/null` (после ffmpeg): `ImportError: libGL.so.1: cannot open shared object file` при `import cv2` (opencv). К пину ffmpeg не относится; в этом плане Dockerfile libGL не трогался, в Dockerfile libgl не упоминается. Требует отдельной задачи (вероятно, нужен пакет libgl1/libglib или переход на opencv-headless в рантайм-venv).
- Тестовый образ не создан (сборка упала), `podman rmi` нечего удалять.

## Deviations
- [Rule 1] Комментарий переформулирован без литералов `n9.0.2-22` / `autobuild-2026-10-01` («предыдущий пин, ежедневная сборка 1 октября 2026»), чтобы удовлетворить автоматической проверке плана (must_haves: этих строк в Dockerfile быть не должно).

## Self-Check: PASSED
