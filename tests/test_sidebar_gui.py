"""Sidebar na janela da lousa (Qt offscreen, relógio falso): dedo simulado aciona por permanência."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.interface.cursor_window import CursorWindow  # noqa: E402
from desktop.interface.qt_bridge import QtServerBridge  # noqa: E402
from desktop.interface.sidebar_model import Control, Orientation, SidebarState, Tool  # noqa: E402
from desktop.main import configure_overlay  # noqa: E402


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
    yield window, clock, log
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def hold(window, clock, point, seconds):
    window._mouse_point = None
    window.overlay = False  # o "dedo" simulado entra pelo caminho do mouse
    window._mouse_point = point
    for _ in range(int(seconds / 0.033)):
        clock.now += 0.033
        window._ui_tick()
    window.overlay = True


def snapshot(window, name):
    shots = os.environ.get("CALIB_SHOTS_DIR")
    if not shots:
        return
    slide = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    slide.fill(QColor("#f4f1ea"))
    p = QPainter(slide)
    f = QFont()
    f.setPixelSize(64)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1d3557"))
    p.drawText(QRectF(0, 200, 1920, 100), Qt.AlignmentFlag.AlignCenter, "Frações equivalentes")
    f.setPixelSize(40)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#333"))
    p.drawText(QRectF(0, 420, 1920, 300), Qt.AlignmentFlag.AlignCenter, "1/2 = 2/4 = 4/8")
    overlay = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    overlay.fill(Qt.GlobalColor.transparent)
    window.render(overlay)
    p.drawImage(0, 0, overlay)
    p.end()
    slide.scaled(960, 540, Qt.AspectRatioMode.KeepAspectRatio,
                 Qt.TransformationMode.SmoothTransformation).save(os.path.join(shots, name))


def test_open_select_tool_rotate_move_close(board):
    window, clock, log = board
    sidebar = window.ensure_sidebar()
    snapshot(window, "sidebar-1-recolhida.png")

    hold(window, clock, sidebar.handle_rect().center, 0.5)
    snapshot(window, "sidebar-2-carregando.png")
    hold(window, clock, sidebar.handle_rect().center, 0.6)
    hold(window, clock, None, 0.3)
    assert sidebar.state is SidebarState.EXPANDED

    hold(window, clock, sidebar.button_center(Tool.BRUSH, clock.now), 0.5)
    snapshot(window, "sidebar-3-aberta.png")
    hold(window, clock, sidebar.button_center(Tool.BRUSH, clock.now), 0.4)
    assert sidebar.tool is Tool.BRUSH

    hold(window, clock, sidebar.button_center(Control.ORIENTATION, clock.now), 1.0)
    assert sidebar.orientation is Orientation.HORIZONTAL
    hold(window, clock, None, 0.2)
    snapshot(window, "sidebar-4-horizontal.png")

    grab = sidebar.button_center(Control.MOVE, clock.now)
    hold(window, clock, grab, 1.0)
    assert sidebar.state is SidebarState.DRAGGING
    for i in range(20):
        hold(window, clock, (grab[0] + (900 - grab[0]) * i / 19, grab[1] + (980 - grab[1]) * i / 19), 0.04)
    snapshot(window, "sidebar-5-arrastando.png")
    hold(window, clock, (900, 980), 1.0)
    assert sidebar.state is SidebarState.EXPANDED and sidebar.edge.value == "bottom"
    hold(window, clock, None, 0.2)
    snapshot(window, "sidebar-6-embaixo.png")

    hold(window, clock, sidebar.handle_rect().center, 1.0)
    hold(window, clock, None, 0.5)
    assert sidebar.state is SidebarState.COLLAPSED and sidebar.tool is Tool.BRUSH

    events = [e for e, _ in log]
    for expected in ("ui_open", "ui_tool", "ui_orientation", "ui_drag_start", "ui_drop", "ui_close"):
        assert expected in events


def test_sidebar_ignored_during_calibration(board):
    window, clock, log = board
    window.start_calibration()
    sidebar = window.ensure_sidebar()
    hold(window, clock, sidebar.handle_rect().center, 1.2)
    assert sidebar.state is SidebarState.COLLAPSED
    assert "ui_open" not in [e for e, _ in log]


def test_resize_preserves_tool_and_position(board):
    window, clock, log = board
    sidebar = window.ensure_sidebar()
    sidebar.tool = Tool.ERASER
    window.resize(1280, 720)
    resized = window.ensure_sidebar()
    assert resized is not sidebar and resized.tool is Tool.ERASER and resized.width == 1280
