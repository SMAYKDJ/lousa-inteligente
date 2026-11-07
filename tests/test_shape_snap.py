"""D033: traço do Pincel que parece forma vira a forma perfeita."""

from __future__ import annotations

import math
import random

import pytest

from desktop.drawing.board import Board, Ellipse, Rectangle, Stroke
from desktop.drawing.shape_snap import recognize

pytestmark = pytest.mark.snap

SIZE = (1920, 1080)


def norm(pts):
    return [(x / SIZE[0], y / SIZE[1]) for x, y in pts]


def wobbly_circle(cx=900, cy=500, r=200, n=60, noise=6, seed=1, close=0.0):
    rng = random.Random(seed)
    span = 2 * math.pi * (1 - close)
    return norm([(cx + (r + rng.gauss(0, noise)) * math.cos(i * span / n),
                  cy + (r + rng.gauss(0, noise)) * math.sin(i * span / n)) for i in range(n + 1)])


def wobbly_rect(x0=500, y0=300, x1=1100, y1=700, step=20, noise=5, seed=2):
    rng = random.Random(seed)
    pts = []
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        n = int(math.hypot(bx - ax, by - ay) // step)
        for i in range(n):
            t = i / n
            pts.append((ax + (bx - ax) * t + rng.gauss(0, noise), ay + (by - ay) * t + rng.gauss(0, noise)))
    pts.append((x0 + 4, y0 + 6))
    return norm(pts)


def test_wobbly_circle_becomes_circle():
    s = recognize(wobbly_circle(), SIZE, "#fff", 0.007)
    assert s.kind == "circle" and isinstance(s.item, Ellipse)
    cx, cy = s.item.center
    r = math.hypot((s.item.edge[0] - cx) * SIZE[0], (s.item.edge[1] - cy) * SIZE[1])
    assert abs(cx * SIZE[0] - 900) < 8 and abs(cy * SIZE[1] - 500) < 8 and abs(r - 200) < 8
    assert s.item.color == "#fff" and s.item.width == 0.007


def test_circle_not_quite_closed_still_counts():
    assert recognize(wobbly_circle(close=0.08), SIZE, "#fff", 0.007).kind == "circle"


def test_half_circle_is_not_a_circle():
    assert recognize(wobbly_circle(close=0.5), SIZE, "#fff", 0.007) is None


def test_wobbly_rectangle_becomes_rectangle():
    s = recognize(wobbly_rect(), SIZE, "#fff", 0.007)
    assert s.kind == "rectangle" and isinstance(s.item, Rectangle)
    (ax, ay), (bx, by) = s.item.a, s.item.b
    assert abs(ax * SIZE[0] - 500) < 15 and abs(by * SIZE[1] - 700) < 15


def test_straight_line_becomes_two_point_line():
    rng = random.Random(3)
    pts = norm([(300 + 10 * i, 400 + 2 * i + rng.gauss(0, 2)) for i in range(60)])
    s = recognize(pts, SIZE, "#fff", 0.007)
    assert s.kind == "line" and len(s.item.points) == 2


def test_handwriting_and_scribbles_stay_free():
    # Letra "S" (curva aberta), zigue-zague e rabisco de ida e volta.
    s_curve = norm([(900 + 120 * math.sin(t / 10), 300 + 8 * t) for t in range(60)])
    zigzag = norm([(400 + 15 * i, 500 + (40 if i % 2 else -40)) for i in range(40)])
    back_forth = norm([(400 + (i if i < 30 else 60 - i) * 15, 500) for i in range(60)])
    tiny = norm([(500 + 3 * math.cos(i / 3), 500 + 3 * math.sin(i / 3)) for i in range(30)])
    for pts in (s_curve, zigzag, back_forth, tiny):
        assert recognize(pts, SIZE, "#fff", 0.007) is None


def test_brush_snaps_and_undo_restores_the_hand_drawn_stroke():
    from desktop.drawing.style import DrawingStyle
    from desktop.drawing.tools import ToolController
    from desktop.interface.sidebar_model import Tool

    board = Board()
    tools = ToolController(board, DrawingStyle())
    t = 0.0
    events = []
    for p in wobbly_circle():
        t += 0.02
        events += tools.update(Tool.BRUSH, True, p, False, SIZE, t)
    for _ in range(30):
        t += 0.02
        events += tools.update(Tool.BRUSH, False, None, False, SIZE, t)
    assert any(e["event"] == "draw_snap" and e["shape"] == "circle" for e in events)
    assert isinstance(board.items[-1], Ellipse)
    board.undo()
    assert isinstance(board.items[-1], Stroke)  # Voltar: o traço como foi desenhado
    board.undo()
    assert board.items == ()
