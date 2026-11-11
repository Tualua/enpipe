"""Общие фикстуры быстрого тира.

Гейт версии qsvencc (ensure_qsvencc_fixed) вызывает `qsvencc --version`, а в
быстром тире бинарника нет; кроме того, test_pipeline_wiring подменяет общий
шов proc.run Mock-ом с пустым stdout -- без заглушки гейт закрылся бы
(fail closed) и уронил бы существующие тесты.

Заглушка патчит ДВА места импорта -- `enpipe.encoding.pipeline.ensure_qsvencc_fixed`
и `enpipe.cli.main.ensure_qsvencc_fixed`, но никогда сам листовой модуль, поэтому
test_qsvencc_version.py по-прежнему проверяет настоящий гейт.

Вторая заглушка, `_stub_resolve_decode`, подменяет resolve_decode в местах
импорта (`enpipe.encoding.pipeline`, `enpipe.cli.main`,
`enpipe.detection.pipeline`): быстрому тиру не нужны qsvencc и ffprobe, а Mock
`_proc.run` с пустым stdout закрыл бы опрос таблицы декодеров (fail-closed).
Сам `enpipe.shared.decode` не патчится -- его проверяют
tests/unit/shared/test_decode.py и tests/subprocess/shared/test_decode.py.

Тесту, которому нужен НАСТОЯЩИЙ гейт, надо заново подставить в место импорта
`enpipe.shared.qsvencc_version.ensure_qsvencc_fixed` и отдавать `qsvencc
--version` через фикстуру `fp` -- а не через Mock `_proc.run` с пустым stdout
(он закрылся бы). Пример: сквозной тест настоящего гейта в test_cli_run.py.
"""
from __future__ import annotations

import pytest

import enpipe.cli.main as cli_main
import enpipe.encoding.pipeline as enc_pipeline
from enpipe.shared.decode import DecodeChoice
from enpipe.shared.qsvencc_version import QSVENCC_MIN_REV


@pytest.fixture(autouse=True)
def _stub_qsvencc_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    def _ok() -> int:
        return QSVENCC_MIN_REV

    monkeypatch.setattr(enc_pipeline, "ensure_qsvencc_fixed", _ok)
    monkeypatch.setattr(cli_main, "ensure_qsvencc_fixed", _ok)


@pytest.fixture(autouse=True)
def _stub_resolve_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    def _resolve(src, mode):
        return DecodeChoice(
            path="sw" if mode == "sw" else "hw", mode=mode, codec="hevc",
            pix_fmt="yuv420p10le", field_order=None,
            reason="заглушка быстрого тира")

    monkeypatch.setattr(enc_pipeline, "resolve_decode", _resolve)
