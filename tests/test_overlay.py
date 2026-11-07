"""Lousa como overlay transparente (Fase 3, etapa 3.0), em Qt offscreen.

Cobre o que dá para verificar sem tela real: fundo transparente onde nada é
desenhado, marcadores e cursor visíveis, sinalizadores da janela, teclas pela
janela de diagnóstico. Ficar por cima de uma apresentação em tela cheia
(macOS/Windows) só se valida no aparelho real.
"""

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QImage, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.communication.message_protocol import (  # noqa: E402
    HandState, HandTrackingMessage, Handedness, IndexTip)
from desktop.interface.camera_preview import CameraPreviewWindow  # noqa: E402
from desktop.interface.cursor_window import CursorWindow  # noqa: E402
from desktop.interface.overlay_platform import make_overlay_window  # noqa: E402
from desktop.interface.qt_bridge import QtServerBridge  # noqa: E402
from desktop.main import configure_overlay, parse_args  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def overlay(qt_app):
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", overlay=True)
    configure_overlay(window)
    window.resize(800, 450)
    yield window
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def render(window) -> QImage:
    image = QImage(window.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    window.render(image)
    return image


def test_background_is_transparent_but_markers_and_cursor_are_drawn(overlay):
    overlay._on_hand_tracking(HandTrackingMessage(seq=1, t_client_ms=1, hand=HandState(
        present=True, handedness=Handedness.RIGHT, confidence=0.9, index_tip=IndexTip(0.5, 0.5, 0))))
    image = render(overlay)
    assert image.pixelColor(400, 100).alpha() == 0  # área vazia: o slide aparece
    first = overlay.marker_layout().rects[0]
    assert image.pixelColor(int(first.x - first.quiet / 2), int(first.y)).alpha() == 255  # margem branca
    cx, cy = 400, 225 + 18  # borda do círculo do cursor
    assert max(image.pixelColor(cx + dx, cy).alpha() for dx in range(-3, 4)) > 0


def test_panel_hidden_by_default_in_overlay(overlay):
    assert overlay.panel_visible is False


def test_window_flags(overlay):
    flags = overlay.windowFlags()
    for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint,
                 Qt.WindowType.WindowTransparentForInput):
        assert flags & flag
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_keys_from_diagnostic_window_reach_the_board(overlay):
    preview = CameraPreviewWindow(SimpleNamespace(latest_preview=lambda: None), overlay)
    preview.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier))
    assert overlay.calibration.active
    preview.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not overlay.calibration.active
    preview.close()
    preview.deleteLater()


def test_calibration_screen_is_opaque_in_overlay(overlay):
    overlay.start_calibration()
    image = render(overlay)
    assert image.pixelColor(400, 100).alpha() == 255  # calibração cobre o slide


def test_platform_adjustment_only_on_macos(overlay):
    if sys.platform == "darwin":
        pytest.skip("no macOS o ajuste é real e é validado no aparelho")
    assert make_overlay_window(overlay) is False


def test_overlay_flag():
    assert parse_args(["--overlay"]).overlay and not parse_args([]).overlay
