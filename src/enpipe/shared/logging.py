"""Прогресс-лог и фатальные ошибки: die()/log()/step()/_START, перенесённые
из legacy/encode_scenes.py как единый leaf-модуль (используется и detection,
и encoding, зависимостей внутри пакета не имеет — держит keyframes.py и
pipeline.py ацикличными).

ВАЖНО: этот модуль называется так же, как stdlib `logging`, но им не
является. Импортировать только квалифицированно — `from enpipe.shared.logging
import die` или `from enpipe.shared import logging` — и никогда не писать
голый `import logging`, рассчитывая на stdlib, в модуле, который также
ссылается на enpipe.shared.logging.

Префикс сообщения die() — "encode_scenes: " — сохранён дословно (часть
байт-идентичной parity-поверхности D-14/D-15), несмотря на переезд в
enpipe.shared.logging; не модернизировать до "enpipe: ".

_START фиксируется в момент импорта ЭТОГО модуля, что сдвигает
elapsed-time-префиксы логов относительно legacy — это чисто косметика
(текст лога не входит в parity-поверхность) и не подлежит "исправлению".
"""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager


def die(msg: str) -> None:
    sys.exit(f"encode_scenes: {msg}")


_START = time.monotonic()


def log(msg: str) -> None:
    """Строка лога с меткой прошедшего от старта времени (unbuffered)."""
    print(f"[{time.monotonic() - _START:8.1f}s] {msg}", flush=True)


@contextmanager
def step(name: str):
    """Обёртка операции: логирует старт и длительность (✔ печатается только
    при успехе — исключение проходит мимо, без ложного ✔)."""
    t0 = time.monotonic()
    log(f"▶ {name}…")
    yield
    log(f"✔ {name} — {time.monotonic() - t0:.1f}с")
