"""Gestos de movimento (D024): deslizar, toque de pinça, zoom com duas mãos."""

from desktop import config
from desktop.drawing.board import Board, Rectangle
from desktop.drawing.tools import ToolController
from desktop.interaction.motions import MotionDetector, Sample, TwoHandZoom, pinch_strength
from desktop.interface.sidebar_model import Tool


def slide(det, x0, x1, pose="open", dy=0.0, n=12, t0=0.0, dur=0.3):
    events = []
    for i in range(n + 1):
        f = i / n
        events += det.update(Sample(t0 + f * dur, x0 + (x1 - x0) * f, 0.5 + dy * f, pose, 0.0))
    return events


def test_swipe_left_and_right_with_open_hand():
    assert [e["direction"] for e in slide(MotionDetector(), 0.7, 0.3)] == ["left"]
    assert [e["direction"] for e in slide(MotionDetector(), 0.3, 0.7)] == ["right"]


def test_no_swipe_when_pointing_fist_slow_short_or_vertical():
    assert slide(MotionDetector(), 0.7, 0.3, pose="pointing") == []  # traço rápido com o indicador
    assert slide(MotionDetector(), 0.7, 0.3, pose="fist") == []
    assert slide(MotionDetector(), 0.6, 0.5) == []  # curto
    assert slide(MotionDetector(), 0.7, 0.3, dur=1.5, n=45) == []  # devagar
    assert slide(MotionDetector(), 0.5, 0.45, dy=0.4) == []  # vertical


def test_swipe_busy_and_cooldown():
    det = MotionDetector()
    events = []
    for i in range(13):
        events += det.update(Sample(i * 0.025, 0.7 - 0.033 * i, 0.5, "open", 0.0), busy=True)
    assert events == []  # duas mãos ou caneta riscando
    det = MotionDetector()
    first = slide(det, 0.8, 0.4)
    again = slide(det, 0.8, 0.4, t0=0.35)  # logo depois: ainda no intervalo de 0,65 s
    assert len(first) == 1 and again == []


def _tap_seq(det, seq):
    ev = []
    for t, gap, pose in seq:
        ev += det.update(Sample(t, 0.5, 0.5, pose, pinch_strength(gap), gap))
    return [e["event"] for e in ev]


def test_tap_quick_vs_slow():
    assert _tap_seq(MotionDetector(), [(0, 0.9, "other"), (0.05, 0.08, "other"), (0.2, 0.08, "other"),
                                       (0.3, 0.9, "other")]) == ["motion_tap"]
    # falha de 1 quadro do rastreamento no meio de um apontar (teste real 13:35): não é toque
    assert _tap_seq(MotionDetector(), [(0, 0.5, "pointing"), (0.04, 0.12, "pointing"),
                                       (0.08, 0.45, "pointing")]) == []
    # segurou a pinça: não é toque
    assert _tap_seq(MotionDetector(), [(0, 0.9, "other"), (0.05, 0.08, "other"), (0.6, 0.08, "other"),
                                       (0.7, 0.9, "other")]) == []


def test_closing_the_hand_is_not_a_tap():
    """Teste real de 2026-11-07: fechar a mão (polegar perto do indicador dobrado) gerava toques."""
    assert _tap_seq(MotionDetector(), [(0, 0.5, "pointing"), (0.05, 0.13, "fist"), (0.15, 0.2, "fist"),
                                       (0.25, 0.45, "fist")]) == []
    # fecha como pinça mas vira punho no meio: anulado
    assert _tap_seq(MotionDetector(), [(0, 0.9, "other"), (0.05, 0.1, "other"), (0.15, 0.12, "fist"),
                                       (0.25, 0.9, "open")]) == []
    # distância intermediária (0,25) não fecha
    assert _tap_seq(MotionDetector(), [(0, 0.9, "other"), (0.05, 0.25, "other"), (0.2, 0.9, "other")]) == []


def test_pinch_strength_from_gap():
    assert pinch_strength(0.1) == 1.0 and pinch_strength(0.6) == 0.0 and pinch_strength(None) == 0.0


def test_two_hand_zoom_ratio_and_grip_rules():
    z = TwoHandZoom()
    assert z.update([(0.4, 0.5, "other", 0.9), (0.6, 0.5, "other", 0.9)]) == 1.0
    assert abs(z.update([(0.3, 0.5, "other", 0.9), (0.7, 0.5, "other", 0.9)]) - 2.0) < 1e-9
    assert z.update([(0.3, 0.5, "open", 0.0), (0.7, 0.5, "other", 0.9)]) is None  # uma mão soltou
    assert z.update([(0.4, 0.5, "fist", 0.0), (0.6, 0.5, "fist", 0.0)]) == 1.0  # nova pegada com punhos
    assert z.update([(0.4, 0.5, "fist", 0.0)]) is None


def test_tools_two_hand_zoom_scales_selected_and_is_one_undo():
    b = Board()
    b.add(Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006))
    c = ToolController(b)
    size = (1000.0, 500.0)
    for i in range(3):
        c.update(Tool.SELECT, True, (0.4, 0.5), False, size, i * 0.03, 1.0)
    c.update(Tool.SELECT, False, (0.4, 0.5), False, size, 0.2, 1.2)  # soltou: redimensionar
    assert c.resizing is not None
    for i, zoom in enumerate((1.0, 1.3, 1.6, 2.0)):
        c.two_hand(zoom, 0.3 + i * 0.03, size)
        c.update(Tool.SELECT, False, (0.4, 0.5), False, size, 0.3 + i * 0.03, 0.5)  # abertura ignorada
    r = b.items[0]
    assert abs((r.b[0] - r.a[0]) - 0.4) < 1e-9  # dobrou
    ev = c.two_hand(None, 1.0, size)
    assert ev == [{"event": "draw_zoom", "scale": 2.0}] and c.resizing is not None
    for i in range(60):  # mão parada: confirma
        c.update(Tool.SELECT, False, (0.4, 0.5), False, size, 1.0 + i * 0.033, 1.2)
    assert c.resizing is None
    b.undo()
    assert b.items[0] == Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006)


def test_config_defaults_from_kit():
    assert config.SWIPE_DISTANCE == 0.20 and config.SWIPE_WINDOW_S == 0.38 and config.TAP_MAX_S == 0.35
