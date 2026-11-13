"""Плагин pytest ТОЛЬКО для эксперимента (2026-11-13): подменяет
renumber_to_decoder_order кандидатом «монотонное сопоставление» (ближайший
I-кадр в окне, строго больший предыдущего назначенного). Код в src/ не меняется.

Зачем: проверить на B50 края чанков в местах, где действующее правило даёт
ничью (два I-кадра через один, Fringe S02E01: Cues 750 -> [749, 751]), до
решения оператора о правиле. Кусок — первые 85 с серии (ничьи на 750, 936,
961, 1837); вырезается командой из tests/fixtures/media/README.md с
`--split parts:00:00:00.000-00:01:25.000`.

Запуск (ENPIPE_TEST_VC1 — путь куска):
  PYTHONPATH=scratch uv run pytest -p vc1_tiefix_candidate_plugin -m hardware \
    tests/integration/test_hardware_real_media.py -k "test_run_auto_vc1_cut" -s -rA
"""
import enpipe.encoding.keyframes as kf

def renumber_monotone(table, i_positions, window=kf.RENUMBER_WINDOW):
    out = []
    prev = -1
    for k, t in table:
        near = [q for q in i_positions if abs(q - k) <= window and q > prev]
        if not near:
            raise ValueError(f"нет свободного I-кадра в пределах ±{window} от ключевого кадра Cues {k}")
        best = min(abs(q - k) for q in near)
        tied = sorted({q for q in near if abs(q - k) == best})
        if len(tied) > 1:
            raise ValueError(f"неоднозначный I-кадр для ключевого кадра Cues {k}: {tied}")
        out.append((tied[0], t))
        prev = tied[0]
    if not out or out[0][0] != 0:
        raise ValueError("ключевой кадр 0 не отображается в позицию 0")
    return out

kf.renumber_to_decoder_order = renumber_monotone
print("[tiefix] renumber_to_decoder_order -> кандидат «монотонное сопоставление»")
