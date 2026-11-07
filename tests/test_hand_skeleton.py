"""D036: os 21 pontos da mão, esqueleto na janela da câmera e palma × dorso."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from desktop.communication.message_protocol import Handedness, HandState, IndexTip
from desktop.vision.hand_side import hand_side, true_hand

W, H = 360, 640  # imagem do celular em pé


def hand(palm_to_camera: bool, right: bool, tilt_edge: bool = False):
    """21 pontos de uma mão em pé. Direita com a palma para a câmera: polegar à direita
    da imagem (a câmera está de frente para a pessoa)."""
    thumb_right = right == palm_to_camera
    sx = 1 if thumb_right else -1
    spread = 0.01 if tilt_edge else 0.06
    pts = [(0.5, 0.75)]  # pulso
    pts += [(0.5 + sx * spread * k * 0.8, 0.72 - 0.03 * k) for k in range(1, 5)]  # polegar
    for f, dx in enumerate((0.5, 0.17, -0.17, -0.5)):  # indicador → mindinho
        x = 0.5 + sx * dx * spread * 2
        pts += [(x, 0.62 - 0.05 * k) for k in range(4)]
    return tuple(IndexTip(x, y, 0.0) for x, y in pts)


def label_for(right: bool, mirrored: bool = False) -> str:
    """O nome que o MediaPipe daria (ele supõe imagem espelhada)."""
    return ("Right" if right else "Left") if mirrored else ("Left" if right else "Right")


@pytest.mark.parametrize("right", [True, False])
@pytest.mark.parametrize("palm", [True, False])
def test_palm_or_back_for_each_hand(right, palm):
    pts = hand(palm, right)
    assert len(pts) == 21
    assert hand_side(pts, label_for(right), W, H) == ("palma" if palm else "dorso")
    assert true_hand(label_for(right)) == ("direita" if right else "esquerda")


def test_front_camera_mirrored_flips_the_name_not_the_answer():
    pts = hand(True, True)
    assert hand_side(pts, label_for(True, mirrored=True), W, H, mirrored=True) == "palma"


def test_edge_on_and_unknown():
    assert hand_side(hand(True, True, tilt_edge=True), "Left", W, H) == "de lado"
    assert hand_side(hand(True, True), None, W, H) is None
    assert hand_side((), "Left", W, H) is None


def test_mediapipe_result_carries_all_21_points():
    from desktop.vision.hand_tracker import hands_from_result
    lms = [SimpleNamespace(x=x, y=y, z=0.0) for x, y in [(p.x, p.y) for p in hand(True, True)]]
    cat = SimpleNamespace(category_name="Left", score=0.9)
    [state] = hands_from_result([lms], [[cat]], W, H)
    assert len(state.landmarks) == 21 and state.landmarks[8].x == pytest.approx(lms[8].x)


def test_preview_draws_the_skeleton_and_side():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from desktop.interface.camera_preview import CameraPreviewWindow
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge

    app = QApplication.instance() or QApplication([])
    board = CursorWindow(QtServerBridge(), "https://x/?token=t")
    pts = hand(True, True)
    state = HandState(present=True, handedness=Handedness.LEFT, confidence=0.9,
                      index_tip=pts[8], landmarks=pts)
    rgb = np.full((H, W, 3), 20, np.uint8)

    class Proc:
        def latest_preview(self):
            return rgb, state

    preview = CameraPreviewWindow(Proc(), board)
    preview.resize(360, 640)
    preview._refresh()
    img = preview.grab().toImage()
    rect = preview._image_rect()

    def color_at(p):
        q = preview._to_px(rect, p.x, p.y)
        return img.pixelColor(int(q.x()), int(q.y()))

    mid = IndexTip((pts[6].x + pts[7].x) / 2, (pts[6].y + pts[7].y) / 2, 0)
    c = color_at(mid)  # meio do indicador: vermelho do esqueleto
    assert c.red() > 200 and c.green() < 140
    tip = color_at(pts[8])
    assert tip.lightness() > 200  # ponto branco nas pontas
    preview.close()
    board.close()
    app.processEvents()
