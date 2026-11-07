"""Desenho na janela da lousa (Qt offscreen, relógio falso): caneta, sidebar e confirmação."""

import os

import pytest

from desktop import config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, Qt as QtNs  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.communication.message_protocol import (  # noqa: E402
    Handedness, HandState, HandTrackingMessage, IndexTip)
from desktop.drawing.board import Ellipse, Stroke  # noqa: E402
from desktop.interaction.confirm import NO, YES  # noqa: E402
from desktop.interface.cursor_window import CursorWindow  # noqa: E402
from desktop.interface.qt_bridge import QtServerBridge  # noqa: E402
from desktop.interface.sidebar_model import Action, Control, SidebarState, Tool  # noqa: E402
from desktop.main import configure_overlay  # noqa: E402
from tests.test_sidebar_gui import snapshot as _snapshot  # noqa: E402


def snapshot(window, name):
    mode, window.overlay = window.overlay, True  # fundo transparente, como na sala
    _snapshot(window, name)
    window.overlay = mode


class Clock:
    now = 50.0

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def board(qt_app):
    clock = Clock()
    log = []
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=clock, overlay=True,
                          event_log=lambda event, **f: log.append((event, f)))
    configure_overlay(window)
    window.resize(1920, 1080)
    window.overlay = False  # mouse = dedo
    window.ensure_sidebar()
    yield window, clock, log
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def step(window, clock, point, down, frames=1):
    for _ in range(frames):
        window._mouse_point, window._mouse_down = point, down
        clock.now += 0.033
        window._ui_tick()


def drag(window, clock, a, b, n=20):
    for i in range(n + 1):
        t = i / n
        step(window, clock, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), True)
    step(window, clock, b, False)


def open_and_pick(window, clock, key):
    sb = window.sidebar
    if sb.state is not SidebarState.EXPANDED:
        step(window, clock, sb.handle_rect().center, False, frames=25)
        step(window, clock, sb.handle_rect().center, False, frames=10)
    assert sb.state is SidebarState.EXPANDED
    step(window, clock, sb.button_center(key, clock.now), False, frames=25)


def leave_panel(window, clock):
    step(window, clock, (1500, 540), False, frames=40)  # dedo na lousa: o painel de estilo fecha


def test_brush_draws_and_undo_redo(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    assert window.sidebar.tool is Tool.BRUSH
    leave_panel(window, clock)
    assert window.style_panel.layout(window.sidebar, clock.now) is None
    drag(window, clock, (600, 400), (1200, 500))
    assert len(window.board.items) == 1 and isinstance(window.board.items[0], Stroke)
    xs = [p[0] for p in window.board.items[0].points]
    assert min(xs) < 0.35 and max(xs) > 0.6  # surface_norm, não px
    assert any(e == "draw_stroke" for e, _ in log)
    window.do_action(Action.UNDO, clock.now)
    assert window.board.items == ()
    window.do_action(Action.REDO, clock.now)
    assert len(window.board.items) == 1


def test_pen_down_over_sidebar_does_not_draw_until_lifted(board):
    window, clock, _ = board
    open_and_pick(window, clock, Tool.BRUSH)
    start = window.sidebar.button_center(Tool.BRUSH, clock.now)
    # Apontou o botão e saiu para a lousa sem relaxar a mão: nada de risco.
    drag(window, clock, start, (1200, 500))
    assert window.board.items == ()
    drag(window, clock, (800, 600), (1000, 600))  # caneta desceu fora: risca
    assert len(window.board.items) == 1


def test_stroke_into_sidebar_stops_and_does_not_fire(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    target = window.sidebar.button_center(Tool.ERASER, clock.now)
    for i in range(21):
        step(window, clock, (900 - (900 - target[0]) * i / 20, target[1]), True)
    step(window, clock, target, True, frames=40)  # parado sobre a Borracha com a caneta descida
    assert window.sidebar.tool is Tool.BRUSH  # risco não aciona a sidebar
    step(window, clock, target, False)
    assert len(window.board.items) == 1
    xs = [p[0] * 1920 for p in window.board.items[0].points]
    panel = window.sidebar.layout(clock.now).panel
    assert min(xs) > panel.x + panel.w - 1  # o traço parou na borda do painel


def test_clear_needs_confirmation(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    drag(window, clock, (800, 300), (1000, 300))
    window.do_action(Action.CLEAR, clock.now)
    prompt = window._confirm
    assert prompt is not None and len(window.board.items) == 1
    drag(window, clock, (800, 900), (1000, 900))  # com a pergunta aberta, nada risca
    assert len(window.board.items) == 1
    step(window, clock, prompt.no.center, False, frames=25)
    assert window._confirm is None and len(window.board.items) == 1
    window.do_action(Action.CLEAR, clock.now)
    snapshot(window, "fase4_confirmar_limpar.png")
    step(window, clock, window._confirm.yes.center, False, frames=25)
    assert window.board.items == ()
    assert [f["answer"] for e, f in log if e == "ui_confirm"] == ["no", "yes"]
    window.do_action(Action.UNDO, clock.now)
    assert len(window.board.items) == 1  # limpar pode ser desfeito


def test_clear_confirmation_times_out(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    drag(window, clock, (800, 300), (1000, 300))
    window.do_action(Action.CLEAR, clock.now)
    step(window, clock, (1500, 900), False, frames=int(9 / 0.033))
    assert window._confirm is None and len(window.board.items) == 1
    assert ("ui_confirm", {"action": "clear", "answer": "timeout"}) in log


def test_circle_via_sidebar(board):
    window, clock, _ = board
    open_and_pick(window, clock, Tool.CIRCLE)
    drag(window, clock, (1300, 500), (1450, 500))
    step(window, clock, (1450, 500), False, frames=15)
    assert isinstance(window.board.items[-1], Ellipse)


def test_one_shape_per_selection(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.RECTANGLE)
    drag(window, clock, (1200, 400), (1500, 600))
    step(window, clock, (1500, 600), False, frames=15)
    assert len(window.board.items) == 1 and window.sidebar.tool is Tool.POINTER
    drag(window, clock, (1200, 700), (1500, 900))  # caneta de novo: não cria outro
    step(window, clock, (1500, 900), False, frames=15)
    assert len(window.board.items) == 1
    open_and_pick(window, clock, Tool.RECTANGLE)  # escolheu de novo: pode desenhar
    drag(window, clock, (1200, 700), (1500, 900))
    step(window, clock, (1500, 900), False, frames=15)
    assert len(window.board.items) == 2
    assert ("ui_tool_auto", {"tool": "pointer", "reason": "shape_done"}) in log


def test_hand_pose_controls_pen(board):
    window, clock, _ = board
    open_and_pick(window, clock, Tool.BRUSH)
    window.overlay = True

    def hand(seq, x, pose):
        window._on_hand_tracking(HandTrackingMessage(seq=seq, t_client_ms=1.0, hand=HandState(
            present=True, handedness=Handedness.RIGHT, confidence=0.9,
            index_tip=IndexTip(x, 0.5, 0.0), pose=pose)))
        clock.now += 0.033
        window._ui_tick()

    for i in range(10):
        hand(i, 0.6 - 0.01 * i, "open")  # mão aberta: move sem riscar
    assert window.board.items == () and not window.pen_down()
    for i in range(20):
        hand(10 + i, 0.5 - 0.01 * i, "pointing")
    assert window.pen_down() and window._tools.preview is not None
    hand(31, 0.3, "other")  # um quadro ruim não quebra o traço
    assert window.pen_down()
    for i in range(4):
        hand(32 + i, 0.3, "open")
    assert len(window.board.items) == 1
    window._on_hand_tracking(HandTrackingMessage(seq=99, t_client_ms=1.0, hand=HandState(present=False)))
    assert not window.pen_down()


def test_annotations_survive_resize_and_snapshot(board):
    window, clock, _ = board
    open_and_pick(window, clock, Tool.BRUSH)
    drag(window, clock, (700, 700), (1100, 760))
    open_and_pick(window, clock, Tool.RECTANGLE)
    drag(window, clock, (1250, 650), (1600, 850))
    step(window, clock, (1600, 850), False, frames=15)
    open_and_pick(window, clock, Tool.CIRCLE)
    drag(window, clock, (500, 300), (580, 300))
    step(window, clock, (580, 300), False, frames=15)
    open_and_pick(window, clock, Tool.POINTER)
    for i in range(12):
        step(window, clock, (1300 + 25 * i, 300 + 8 * i), False)
    snapshot(window, "fase4_desenho_sobre_slide.png")
    items = window.board.items
    window.resize(1280, 720)
    window.ensure_sidebar()
    assert window.board.items == items  # surface_norm: tamanho da janela não importa
    assert len(window._tools.trail) > 0


def test_style_panel_in_window(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    lay = window.style_panel.layout(window.sidebar, clock.now)
    assert lay is not None
    blue = dict(lay.buttons)[("color", 1)]
    thick = dict(lay.buttons)[("width", 2)]
    step(window, clock, blue.center, False, frames=25)
    step(window, clock, thick.center, False, frames=25)
    assert ("ui_style", {"color": "Azul"}) in log and ("ui_style", {"width": "Grosso"}) in log
    snapshot(window, "fase4_painel_estilo.png")
    step(window, clock, (1100, 300), False)
    drag(window, clock, (1100, 300), (1500, 350))
    assert window.board.items[-1].color == "#1e6fd9"
    assert window.style_panel.layout(window.sidebar, clock.now) is None  # fechou ao riscar
    open_and_pick(window, clock, Tool.ERASER)
    lay = window.style_panel.layout(window.sidebar, clock.now)
    step(window, clock, dict(lay.buttons)[("eraser", 2)].center, False, frames=25)
    assert window.style.eraser_index == 2


def test_drawing_over_style_panel_is_blocked(board):
    window, clock, _ = board
    open_and_pick(window, clock, Tool.BRUSH)
    lay = window.style_panel.layout(window.sidebar, clock.now)
    a = lay.panel.center
    drag(window, clock, (a[0] - 5, a[1]), (a[0] + 5, a[1]))
    assert window.board.items == ()


def test_select_moves_annotation_in_window(board):
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    leave_panel(window, clock)
    drag(window, clock, (900, 500), (1100, 500))
    open_and_pick(window, clock, Tool.SELECT)
    step(window, clock, (1500, 540), False)
    for i in range(21):
        step(window, clock, (1000, 500 + 10 * i), True)
    assert window._tools.selected == 0
    snapshot(window, "fase4_selecionar.png")
    step(window, clock, (1000, 700), False)
    ys = [p[1] * 1080 for p in window.board.items[0].points]
    assert abs(sum(ys) / len(ys) - 700) < 3
    assert any(e == "draw_move" for e, _ in log)
    window.do_action(Action.UNDO, clock.now)
    ys = [p[1] * 1080 for p in window.board.items[0].points]
    assert abs(sum(ys) / len(ys) - 500) < 3


def test_select_resize_with_hand_openness(board, monkeypatch):
    """Comportamento anterior (4.6), ainda disponível com RESIZE_SIGNAL = "openness"."""
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    leave_panel(window, clock)
    drag(window, clock, (900, 500), (1100, 500))
    open_and_pick(window, clock, Tool.SELECT)
    step(window, clock, (1500, 540), False)
    window.overlay = True
    seq = [100]

    def hand(x, y, pose, openness):
        seq[0] += 1
        window._on_hand_tracking(HandTrackingMessage(seq=seq[0], t_client_ms=1.0, hand=HandState(
            present=True, handedness=Handedness.RIGHT, confidence=0.9,
            index_tip=IndexTip(x, y, 0.0), pose=pose, openness=openness)))
        clock.now += 0.033
        window._ui_tick()

    for _ in range(6):
        hand(1000 / 1920, 500 / 1080, "pointing", 1.1)  # pega o traço
    assert window._tools.selected == 0
    for _ in range(15):
        hand(1000 / 1920, 500 / 1080, "fist", 1.0)  # soltou com a mão fechada
    for i in range(12):
        hand(1000 / 1920, 500 / 1080, "open", 1.0 + 0.06 * i)  # abrindo
    assert window._tools.resizing is not None and window._tools.resizing["scale"] > 1.3
    snapshot(window, "fase4_redimensionar.png")
    for _ in range(45):
        hand(1000 / 1920, 500 / 1080, "open", 1.66)  # parada: confirma
    assert window._tools.resizing is None
    resize = [f for e, f in log if e == "draw_resize"]
    assert resize and resize[-1]["scale"] > 1.3
    xs = [p[0] * 1920 for p in window.board.items[0].points]
    assert max(xs) - min(xs) > 1.3 * 200


def test_select_resize_by_hand_distance_to_camera(board):
    """D035: segurando o desenho com o indicador, para os lados move e aproximar a mão da
    câmera (palma maior) amplia; abrir a mão solta e, parada 1 s, confirma."""
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    leave_panel(window, clock)
    drag(window, clock, (900, 500), (1100, 500))
    open_and_pick(window, clock, Tool.SELECT)
    step(window, clock, (1500, 540), False)
    window.overlay = True
    seq = [300]

    def hand(x, y, pose, palm):
        seq[0] += 1
        window._on_hand_tracking(HandTrackingMessage(seq=seq[0], t_client_ms=1.0, hand=HandState(
            present=True, handedness=Handedness.RIGHT, confidence=0.9,
            index_tip=IndexTip(x, y, 0.0), pose=pose, openness=1.6, palm_size_px=palm)))
        clock.now += 0.033
        window._ui_tick()

    def width():
        xs = [p[0] * 1920 for p in window.board.items[0].points]
        return max(xs) - min(xs), min(xs)

    w0, x0 = width()
    for _ in range(8):
        hand(1000 / 1920, 500 / 1080, "pointing", 60.0)  # pega o traço
    assert window._tools.selected == 0
    for i in range(15):  # para a direita e para perto da câmera, ainda segurando
        hand((1000 + 10 * i) / 1920, 500 / 1080, "pointing", 60.0 + 2.0 * i)
    for _ in range(15):
        hand(1140 / 1920, 500 / 1080, "pointing", 88.0)
    w1, x1 = width()
    assert w1 > 1.3 * w0
    snapshot(window, "fase4_redimensionar.png")
    for _ in range(45):
        hand(1140 / 1920, 500 / 1080, "open", 88.0)  # abriu a mão: solta; parada 1 s confirma
    assert window._tools.resizing is None and window._tools.selected is None
    big = [f for e, f in log if e == "draw_resize"][-1]
    assert big["scale"] > 1.3 and big["signal"] == "size"
    assert abs(width()[0] - w1) < 1  # soltar não mudou o tamanho

    # De novo, levando a mão para perto da lousa: reduz.
    cx = 1140 + 0
    for _ in range(8):
        hand(cx / 1920, 500 / 1080, "pointing", 88.0)
    for i in range(15):
        hand(cx / 1920, 500 / 1080, "pointing", 88.0 - 2.5 * i)
    for _ in range(15):
        hand(cx / 1920, 500 / 1080, "pointing", 53.0)
    for _ in range(45):
        hand(cx / 1920, 500 / 1080, "open", 53.0)
    small = [f for e, f in log if e == "draw_resize"][-1]
    assert small["scale"] < 0.75
    window.do_action(Action.UNDO, clock.now)
    assert abs(width()[0] - w1) < 1  # Voltar desfaz o último redimensionar


def test_pinch_mode_draws_and_k_toggles(board):
    from PySide6.QtCore import QEvent, Qt as QtNs
    from PySide6.QtGui import QKeyEvent
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    leave_panel(window, clock)
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, QtNs.Key.Key_K, QtNs.KeyboardModifier.NoModifier))
    assert window._pen.mode == "pinch" and ("pen_mode", {"mode": "pinch"}) in log
    window.overlay = True
    seq = [500]

    def hand(x, pose, pinch):
        seq[0] += 1
        window._on_hand_tracking(HandTrackingMessage(seq=seq[0], t_client_ms=1.0, hand=HandState(
            present=True, handedness=Handedness.RIGHT, confidence=0.9,
            index_tip=IndexTip(x, 0.5, 0.0), pose=pose, pinch=pinch)))
        clock.now += 0.033
        window._ui_tick()

    for i in range(10):
        hand(0.6 + 0.01 * i, "pointing", 0.9)  # indicador esticado sem pinça: não escreve
    assert window.board.items == ()
    for i in range(20):
        hand(0.6 - 0.01 * i, "other", 0.08)  # pinça fechada (real ≈ 0,09): escreve
    for _ in range(4):
        hand(0.4, "open", 0.9)
    assert len(window.board.items) == 1
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, QtNs.Key.Key_K, QtNs.KeyboardModifier.NoModifier))
    assert window._pen.mode == "pose"


def _send(window, clock, seq, hands, primary=0):
    """Mensagem com uma ou duas mãos: (x, y, pose, pinch_gap, openness) em camera_norm."""
    states = tuple(HandState(present=True, handedness=Handedness.RIGHT if i == 0 else Handedness.LEFT,
                             confidence=0.9, index_tip=IndexTip(x, y, 0.0), pose=pose, pinch=gap,
                             openness=op)
                   for i, (x, y, pose, gap, op) in enumerate(hands))
    window._on_hand_tracking(HandTrackingMessage(seq=seq, t_client_ms=1.0, hand=states[primary],
                                                 candidates=states if len(states) > 1 else ()))
    clock.now += 0.033
    window._ui_tick()


def test_swipe_changes_slide(board):
    from tests.test_slides import FakeSender
    window, clock, log = board
    sender = FakeSender()
    window._keys = sender
    window.overlay = True
    for i in range(14):  # mão aberta deslizando para a esquerda, rápido
        _send(window, clock, 900 + i, [(0.75 - 0.035 * i, 0.5, "open", 0.9, 1.9)])
    assert sender.sent == ["next"] and window.slides.index == 1
    assert any(e == "motion_swipe" for e, _ in log)
    for i in range(14):  # com o indicador (escrevendo rápido): não troca
        _send(window, clock, 950 + i, [(0.75 - 0.035 * i, 0.5, "pointing", 0.9, 1.3)])
    assert sender.sent == ["next"]
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, QtNs.Key.Key_H, QtNs.KeyboardModifier.NoModifier))
    assert not window.motions_enabled
    for i in range(14):
        _send(window, clock, 990 + i, [(0.75 - 0.035 * i, 0.5, "open", 0.9, 1.9)])
    assert sender.sent == ["next"]  # desligado


def test_pinch_tap_clicks_button_immediately(board):
    window, clock, log = board
    sb = window.sidebar
    step(window, clock, sb.handle_rect().center, False, frames=25)
    step(window, clock, sb.handle_rect().center, False, frames=10)
    window.overlay = True
    cx, cy = sb.button_center(Tool.ERASER, clock.now)
    x, y = cx / 1920, cy / 1080
    for gap in (0.9, 0.9, 0.1, 0.1, 0.9):  # pinça rápida sobre o botão (~0,1 s)
        _send(window, clock, 1100 + int(gap * 10) + int(clock.now * 100), [(x, y, "other", gap, 1.2)])
    assert sb.tool is Tool.ERASER  # sem esperar os 0,6 s de permanência
    assert ("motion_click", {"key": "eraser"}) in log


def test_two_hand_zoom_resizes_selected(board, monkeypatch):
    monkeypatch.setattr(config, "RESIZE_SIGNAL", "openness")
    window, clock, log = board
    open_and_pick(window, clock, Tool.BRUSH)
    leave_panel(window, clock)
    drag(window, clock, (900, 500), (1100, 500))
    open_and_pick(window, clock, Tool.SELECT)
    step(window, clock, (1500, 540), False)
    window.overlay = True
    seq = 2000
    for _ in range(6):  # pega o traço
        seq += 1
        _send(window, clock, seq, [(1000 / 1920, 500 / 1080, "pointing", 0.9, 1.1)])
    for _ in range(12):  # soltou com a mão meio aberta: fica selecionado
        seq += 1
        _send(window, clock, seq, [(1000 / 1920, 500 / 1080, "open", 0.9, 1.4)])
    assert window._tools.resizing is not None
    for i in range(16):  # duas mãos em pinça se afastando
        seq += 1
        spread = 0.1 + 0.01 * i
        _send(window, clock, seq, [(0.5 - spread, 0.5, "other", 0.1, 1.2), (0.5 + spread, 0.5, "other", 0.1, 1.2)])
    assert window._two_hand_zoom is not None and window._two_hand_zoom > 2.0
    for _ in range(3):  # soltou as duas mãos
        seq += 1
        _send(window, clock, seq, [(0.6, 0.5, "open", 0.9, 1.4)])
    assert any(e == "draw_zoom" for e, _ in log)
    xs = [p[0] * 1920 for p in window.board.items[0].points]
    assert max(xs) - min(xs) > 2.0 * 200
    assert window.board.items  # a pinça das duas mãos não riscou nada novo
    assert len(window.board.items) == 1


def test_gesture_lab_in_window(board):
    window, clock, log = board
    window.overlay = True
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, QtNs.Key.Key_L, QtNs.KeyboardModifier.NoModifier))
    assert window.lab.active
    seq = 3000
    for i in range(20):
        seq += 1
        _send(window, clock, seq, [(0.5, 0.5, "pointing", 0.9, 1.2)])
    snapshot(window, "laboratorio_gestos.png")
    assert window.board.items == ()  # durante o laboratório não se desenha
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, QtNs.Key.Key_Escape, QtNs.KeyboardModifier.NoModifier))
    assert not window.lab.active and any(e == "lab_cancel" for e, _ in log)
