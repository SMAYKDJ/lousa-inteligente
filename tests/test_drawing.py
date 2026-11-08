"""Motor de desenho: histórico, borracha, formas e ferramentas (Fase 4)."""

from desktop import config
from desktop.drawing.board import Board, Ellipse, Rectangle, Stroke, resample
from desktop.drawing.tools import ToolController
from desktop.interface.sidebar_model import Tool

SIZE = (1000.0, 500.0)


def line(x0, x1, y=0.5, n=50):
    return Stroke(tuple((x0 + (x1 - x0) * i / (n - 1), y) for i in range(n)), "#000", 0.006)


def test_resample_keeps_endpoints_and_spacing():
    pts = resample([(0.0, 0.5), (0.5, 0.5)], spacing=0.01, aspect=2.0)
    assert pts[0] == (0.0, 0.5) and pts[-1] == (0.5, 0.5)
    assert 90 <= len(pts) <= 102  # 0.5*2/0.01 = 100 passos


def test_undo_redo_and_clear():
    b = Board()
    b.add(line(0.1, 0.4)); b.add(line(0.5, 0.9))
    assert len(b.items) == 2
    assert b.undo() and len(b.items) == 1
    assert b.redo() and len(b.items) == 2
    assert b.clear() and b.items == ()
    assert b.undo() and len(b.items) == 2  # limpar pode ser desfeito


def test_new_action_drops_redo():
    b = Board()
    b.add(line(0.1, 0.4)); b.undo()
    b.add(line(0.5, 0.9))
    assert not b.can_redo


def test_eraser_splits_stroke_in_two():
    b = Board()
    b.add(line(0.1, 0.9))
    assert b.erase((0.5, 0.5), radius_px=20, size=SIZE) == 1
    assert len(b.items) == 2
    left, right = b.items
    assert max(p[0] for p in left.points) < 0.5 < min(p[0] for p in right.points)


def test_eraser_far_away_changes_nothing():
    b = Board()
    b.add(line(0.1, 0.9))
    assert b.erase((0.5, 0.9), radius_px=20, size=SIZE) == 0
    assert len(b.items) == 1 and b.can_undo


def test_eraser_removes_shapes_only_on_outline():
    b = Board()
    b.add(Ellipse((0.5, 0.5), (0.6, 0.5), "#000", 0.006))  # raio 100 px
    b.add(Rectangle((0.1, 0.1), (0.3, 0.3), "#000", 0.006))
    assert b.erase((0.5, 0.5), 10, SIZE) == 0  # centro do círculo: não toca o contorno
    assert b.erase((0.2, 0.2), 10, SIZE) == 0  # centro do retângulo
    assert b.erase((0.6, 0.5), 10, SIZE) == 1  # borda do círculo
    assert b.erase((0.3, 0.2), 10, SIZE) == 1  # lado do retângulo
    assert b.items == ()


def test_eraser_gesture_is_one_undo_step():
    b = Board()
    b.add(line(0.1, 0.9, y=0.3)); b.add(line(0.1, 0.9, y=0.7))
    b.begin_group()
    b.erase((0.5, 0.3), 20, SIZE)
    b.erase((0.5, 0.7), 20, SIZE)
    b.end_group()
    assert len(b.items) == 4
    b.undo()
    assert len(b.items) == 2


def test_empty_eraser_gesture_leaves_no_history():
    b = Board()
    b.add(line(0.1, 0.9))
    b.begin_group(); b.erase((0.5, 0.9), 5, SIZE); b.end_group()
    b.undo()
    assert b.items == ()  # o único passo desfeito foi o traço


def run(ctrl, tool, frames):
    events = []
    for i, (down, pt, over) in enumerate(frames):
        events += ctrl.update(tool, down, pt, over, SIZE, now=i * 0.033)
    return events


def test_brush_commits_on_pen_up():
    b = Board(); c = ToolController(b)
    frames = [(True, (0.1 + 0.01 * i, 0.5), False) for i in range(30)] + [(False, (0.4, 0.5), False)]
    ev = run(c, Tool.BRUSH, frames)
    assert len(b.items) == 1 and isinstance(b.items[0], Stroke)
    assert [e["event"] for e in ev] == ["draw_stroke"]
    assert c.preview is None


def test_brush_does_not_draw_over_ui_and_lifts_there():
    b = Board(); c = ToolController(b)
    frames = [(True, (0.1 + 0.01 * i, 0.5), False) for i in range(10)]
    frames += [(True, (0.2, 0.5), True)]  # entrou na sidebar: termina o traço
    frames += [(True, (0.21, 0.5), True) for _ in range(5)]
    run(c, Tool.BRUSH, frames)
    assert len(b.items) == 1


def test_lost_hand_lifts_pen():
    b = Board(); c = ToolController(b)
    frames = [(True, (0.1 + 0.01 * i, 0.5), False) for i in range(10)] + [(True, None, False)]
    run(c, Tool.BRUSH, frames)
    assert len(b.items) == 1


def test_circle_and_rectangle_with_preview():
    for tool, kind in ((Tool.CIRCLE, Ellipse), (Tool.RECTANGLE, Rectangle)):
        b = Board(); c = ToolController(b)
        run(c, tool, [(True, (0.3, 0.3), False), (True, (0.4, 0.45), False)])
        assert isinstance(c.preview, kind) and b.items == ()
        ev = run(c, tool, [(False, (0.4, 0.45), False)] * 15)
        assert len(b.items) == 1 and isinstance(b.items[0], kind)
        assert ev[0]["event"] == "draw_shape"


def test_shape_survives_pose_flicker():
    b = Board(); c = ToolController(b)
    frames = [(True, (0.3, 0.3), False), (True, (0.35, 0.35), False)]
    frames += [(False, (0.35, 0.35), False)] * 3  # ~0,1 s levantada: oscilação
    frames += [(True, (0.45, 0.45), False)]
    run(c, Tool.RECTANGLE, frames)
    assert b.items == () and c.preview.a == (0.3, 0.3) and c.preview.b == (0.45, 0.45)
    run(c, Tool.RECTANGLE, [(False, (0.45, 0.45), False)] * 15)
    assert len(b.items) == 1


def test_tiny_shape_is_discarded():
    b = Board(); c = ToolController(b)
    run(c, Tool.CIRCLE, [(True, (0.3, 0.3), False), (True, (0.301, 0.3), False)] + [(False, None, False)] * 15)
    assert b.items == ()


def test_eraser_tool_groups_one_gesture():
    b = Board(); b.add(line(0.1, 0.9, y=0.5))
    c = ToolController(b)
    frames = [(True, (0.2 + 0.05 * i, 0.5), False) for i in range(5)] + [(False, None, False)]
    run(c, Tool.ERASER, frames)
    assert len(b.items) >= 2
    b.undo()
    assert len(b.items) == 1


def test_pointer_trail_expires_and_does_not_draw():
    b = Board(); c = ToolController(b)
    run(c, Tool.POINTER, [(True, (0.1 * i, 0.5), False) for i in range(5)])
    assert b.items == () and len(c.trail) == 5
    c.update(Tool.POINTER, False, None, False, SIZE, now=10.0)
    assert c.trail == []


def test_switching_tool_commits_stroke():
    b = Board(); c = ToolController(b)
    run(c, Tool.BRUSH, [(True, (0.1 + 0.01 * i, 0.5), False) for i in range(10)])
    c.update(Tool.ERASER, True, (0.9, 0.9), True, SIZE, now=1.0)
    assert len(b.items) == 1


def test_hit_prefers_topmost_and_needs_proximity():
    b = Board()
    b.add(Rectangle((0.2, 0.2), (0.6, 0.6), "#000", 0.006))
    b.add(line(0.1, 0.9, y=0.4))
    assert b.hit((0.5, 0.4), 10, SIZE) == 1  # traço por cima do retângulo
    assert b.hit((0.3, 0.3), 10, SIZE) == 0  # dentro do retângulo
    assert b.hit((0.95, 0.9), 10, SIZE) is None


def test_select_drags_item_as_one_undo_step():
    b = Board(); b.add(Ellipse((0.3, 0.3), (0.35, 0.3), "#000", 0.006)); b.add(line(0.6, 0.9, y=0.8))
    c = ToolController(b)
    frames = [(True, (0.3 + 0.01 * i, 0.3 + 0.01 * i), False) for i in range(11)] + [(False, None, False)]
    ev = run(c, Tool.SELECT, frames)
    moved = b.items[0]
    assert abs(moved.center[0] - 0.4) < 1e-9 and abs(moved.center[1] - 0.4) < 1e-9
    assert b.items[1] == line(0.6, 0.9, y=0.8)  # o outro não mexe
    assert ev[-1]["event"] == "draw_move" and c.selected is None
    b.undo()
    assert b.items[0].center == (0.3, 0.3) and len(b.items) == 2


def test_select_on_empty_area_moves_nothing_even_if_finger_reaches_item():
    b = Board(); b.add(line(0.5, 0.9, y=0.5))
    c = ToolController(b)
    frames = [(True, (0.1 + 0.05 * i, 0.5), False) for i in range(10)] + [(False, None, False)]
    ev = run(c, Tool.SELECT, frames)
    assert b.items == (line(0.5, 0.9, y=0.5),) and ev == []
    b.undo()
    assert b.items == ()  # o único passo no histórico é o traço


def resize_run(c, frames, t0=0.0):
    events = []
    for i, (down, pt, openness) in enumerate(frames):
        events += c.update(Tool.SELECT, down, pt, False, SIZE, now=t0 + i * 0.033, openness=openness)
    return events


def test_release_then_open_hand_scales_and_hold_confirms(monkeypatch):
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")  # jeito anterior (4.6)
    b = Board(); b.add(Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006))
    c = ToolController(b)
    frames = [(True, (0.4, 0.5), 1.0)] * 3  # pega pelo lado esquerdo
    frames += [(False, (0.4, 0.5), 1.2)] * 15  # soltou: assenta e mede a referência (1.2)
    frames += [(False, (0.4, 0.5), 1.2 + 0.05 * i) for i in range(1, 9)]  # abrindo até 1.6
    frames += [(False, (0.4, 0.5), 1.6)] * 50  # parada: confirma
    ev = resize_run(c, frames)
    r = b.items[0]
    assert r.b[0] - r.a[0] > 0.2 * 1.3  # ficou maior
    cx = (r.a[0] + r.b[0]) / 2
    assert abs(cx - 0.5) < 1e-9  # ampliou em torno do centro
    assert c.resizing is None and ev[-1]["event"] == "draw_resize" and ev[-1]["scale"] > 1.3
    b.undo()
    assert b.items[0] == Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006)


def test_closing_hand_shrinks(monkeypatch):
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")  # jeito anterior (4.6)
    b = Board(); b.add(line(0.3, 0.7))
    c = ToolController(b)
    frames = [(True, (0.5, 0.5), 1.0)] * 3 + [(False, (0.5, 0.5), 1.8)] * 15
    frames += [(False, (0.5, 0.5), 1.8 - 0.05 * i) for i in range(1, 12)] + [(False, (0.5, 0.5), 1.25)] * 50
    resize_run(c, frames)
    xs = [p[0] for p in b.items[0].points]
    assert max(xs) - min(xs) < 0.4 * 0.7


def test_still_hand_after_release_changes_nothing(monkeypatch):
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")  # jeito anterior (4.6)
    b = Board(); b.add(line(0.3, 0.7))
    c = ToolController(b)
    ev = resize_run(c, [(True, (0.5, 0.5), 1.0)] * 3 + [(False, (0.5, 0.5), 1.5)] * 60)
    assert c.resizing is None and b.items == (line(0.3, 0.7),)
    assert [e["event"] for e in ev] == ["draw_resize_none"]
    b.undo()
    assert b.items == ()  # nenhum passo vazio no histórico


def test_pointing_again_confirms_and_lost_hand_keeps_size(monkeypatch):
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")  # jeito anterior (4.6)
    b = Board(); b.add(line(0.3, 0.7)); b.add(line(0.3, 0.7, y=0.8))
    c = ToolController(b)
    frames = [(True, (0.5, 0.5), 1.0)] * 3 + [(False, (0.5, 0.5), 1.2)] * 15
    frames += [(False, (0.5, 0.5), 1.2 + 0.05 * i) for i in range(1, 9)]
    resize_run(c, frames)
    assert c.resizing is not None
    resize_run(c, [(True, (0.5, 0.8), 1.0)], t0=5.0)  # apontou de novo: confirma
    assert c.resizing is None and c.selected == 1  # e já pega o outro traço
    c.update(Tool.SELECT, False, (0.5, 0.8), False, SIZE, now=6.0, openness=1.3)
    c.update(Tool.SELECT, False, None, False, SIZE, now=6.5, openness=None)  # mão perdida
    assert c.resizing is None


def test_no_openness_means_plain_drop():
    b = Board(); b.add(line(0.3, 0.7))
    c = ToolController(b)
    resize_run(c, [(True, (0.5, 0.5), None)] * 3 + [(False, (0.5, 0.5), None)])
    assert c.resizing is None and c.selected is None


def test_holding_moves_and_hand_distance_scales_at_the_same_time():
    """D035: segurando com o indicador, os lados movem e a palma maior (mão perto da câmera)
    amplia; ao soltar, 1 s de confirmação; Voltar desfaz tudo de uma vez."""
    b = Board(); b.add(Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006))
    c = ToolController(b)
    frames = [(True, (0.4, 0.5), 60.0)] * 8  # pega pelo lado esquerdo; palma de referência 60
    frames += [(True, (0.4 + 0.01 * i, 0.5), 60.0 + 3.0 * i) for i in range(1, 11)]  # vai à direita e à câmera
    frames += [(True, (0.5, 0.5), 90.0)] * 20  # parado segurando: o tamanho acompanha a palma
    ev = resize_run(c, frames)
    r = b.items[0]
    assert r.b[0] - r.a[0] > 0.2 * 1.35  # ampliou
    assert abs((r.a[0] + r.b[0]) / 2 - 0.6) < 0.01  # andou 0,1 para a direita
    ev += resize_run(c, [(False, (0.5, 0.5), 92.0)] * 10, t0=2.0)  # abriu a mão: soltou
    assert c.resizing is not None and c.resizing["confirm_only"]
    assert abs((b.items[0].b[0] - b.items[0].a[0]) - (r.b[0] - r.a[0])) < 1e-9  # solto, não muda mais
    ev += resize_run(c, [(False, (0.5, 0.5), 92.0)] * 40, t0=2.4)  # 1 s: confirma
    assert c.resizing is None and c.selected is None
    names = [e["event"] for e in ev]
    assert "draw_move" in names and any(e["event"] == "draw_resize" and e["scale"] > 1.35 for e in ev)
    b.undo()
    assert b.items[0] == Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006)


def test_hand_toward_board_shrinks_while_holding():
    b = Board(); b.add(line(0.3, 0.7))
    c = ToolController(b)
    frames = [(True, (0.5, 0.5), 80.0)] * 8
    frames += [(True, (0.5, 0.5), 80.0 - 3.0 * i) for i in range(1, 11)] + [(True, (0.5, 0.5), 50.0)] * 20
    frames += [(False, (0.5, 0.5), 50.0)] * 45
    resize_run(c, frames)
    xs = [p[0] for p in b.items[0].points]
    assert max(xs) - min(xs) < 0.4 * 0.7 and c.resizing is None


def test_palm_noise_while_moving_does_not_resize():
    """1º teste real (D035): só mover mudava o tamanho em ±5% pelo ruído da palma."""
    b = Board(); b.add(Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006))
    c = ToolController(b)
    frames = [(True, (0.4, 0.5), 30.0)] * 8
    frames += [(True, (0.4 + 0.01 * i, 0.5), 30.0 * (1 + 0.06 * (-1) ** i)) for i in range(1, 21)]
    frames += [(False, (0.6, 0.5), 30.0)] * 45
    ev = resize_run(c, frames)
    r = b.items[0]
    assert abs((r.b[0] - r.a[0]) - 0.2) < 1e-9
    assert not any(e["event"] == "draw_resize" for e in ev)


def test_other_hand_taking_over_does_not_resize():
    """1º relato do usuário (D038): a outra mão entrou, virou a escolhida (palma menor, perto
    da lousa) e o desenho encolheu. Salto de palma de um quadro para o outro = troca de mão."""
    b = Board(); b.add(Rectangle((0.4, 0.4), (0.6, 0.6), "#000", 0.006))
    c = ToolController(b)
    frames = [(True, (0.4, 0.5), 39.0)] * 10          # pega com a mão perto da câmera
    frames += [(True, (0.4, 0.5), 30.0)] * 10         # outra mão (perto da lousa) assume
    frames += [(False, (0.4, 0.5), 30.0)] * 45        # solta e confirma
    ev = resize_run(c, frames)
    r = b.items[0]
    assert abs((r.b[0] - r.a[0]) - 0.2) < 1e-9
    assert not any(e["event"] == "draw_resize" for e in ev)
