"""Testes do detector de mão do notebook (D013).

A conversão do resultado roda sempre. Os testes com o MediaPipe real são
pulados se ele não estiver instalado (rode scripts/setup_mac.sh).
"""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from desktop.communication.message_protocol import Handedness
from desktop.vision.hand_tracker import INDEX_TIP, hand_state_from_result

FIXTURE = Path(__file__).parent / "fixtures" / "hand_thumbs_up.jpg"


def landmarks_with_tip(x, y, z=0.0):
    points = [NS(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    points[INDEX_TIP] = NS(x=x, y=y, z=z)
    return [points]


def test_no_hand():
    assert hand_state_from_result([], []).present is False


def test_tip_and_handedness():
    state = hand_state_from_result(landmarks_with_tip(0.2, 0.7, -0.1),
                                   [[NS(category_name="Left", score=0.93)]])
    assert state.present
    assert (state.index_tip.x, state.index_tip.y, state.index_tip.z) == (0.2, 0.7, -0.1)
    assert state.handedness is Handedness.LEFT and state.confidence == 0.93


def test_tip_is_clamped_like_on_the_phone():
    state = hand_state_from_result(landmarks_with_tip(-0.05, 1.2),
                                   [[NS(category_name="Right", score=1.5)]])
    assert (state.index_tip.x, state.index_tip.y) == (0.0, 1.0)
    assert state.confidence == 1.0


def test_missing_handedness_defaults():
    state = hand_state_from_result(landmarks_with_tip(0.3, 0.3), [])
    assert state.handedness is Handedness.RIGHT and state.confidence == 0.0


# --- MediaPipe real ------------------------------------------------------------

@pytest.fixture(scope="module")
def detector():
    pytest.importorskip("mediapipe")
    from desktop.vision.hand_tracker import MediaPipeHandDetector

    det = MediaPipeHandDetector()
    yield det
    det.close()


def test_decode_jpeg():
    pytest.importorskip("cv2")
    from desktop.vision.hand_tracker import decode_jpeg_rgb

    rgb = decode_jpeg_rgb(FIXTURE.read_bytes())
    assert rgb.shape == (427, 640, 3)
    assert decode_jpeg_rgb(b"\xff\xd8 corrompido") is None


def test_real_mediapipe_finds_hand(detector):
    from desktop.vision.hand_tracker import decode_jpeg_rgb

    rgb = decode_jpeg_rgb(FIXTURE.read_bytes())
    hands = detector.detect(rgb, 1)
    # Na foto as duas mãos se sobrepõem: o MediaPipe acha uma delas.
    assert len(hands) >= 1
    state = hands[0]
    assert state.present and state.confidence > 0.5  # score da lateralidade
    assert 0.1 < state.index_tip.x < 0.45 and 0.35 < state.index_tip.y < 0.7
    assert len(state.palm) == 5 and state.palm_size_px > 20


def two_hands_scene():
    """A mão da foto duas vezes, separadas: grande (perto da câmera) e 60% (longe)."""
    import cv2
    import numpy as np

    from desktop.vision.hand_tracker import decode_jpeg_rgb

    crop = decode_jpeg_rgb(FIXTURE.read_bytes())[60:400, 120:380]
    small = cv2.resize(crop, None, fx=0.6, fy=0.6)
    canvas = np.full((540, 960, 3), (70, 90, 70), np.uint8)
    canvas[100:100 + crop.shape[0], 60:60 + crop.shape[1]] = crop
    canvas[200:200 + small.shape[0], 620:620 + small.shape[1]] = small
    return canvas


def test_real_mediapipe_finds_two_hands_with_different_sizes(detector):
    hands = []
    for t in range(3):  # modo VIDEO: o rastreamento firma nos primeiros quadros
        hands = detector.detect(two_hands_scene(), 5000 + t * 33)
    assert len(hands) == 2
    near, far = sorted(hands, key=lambda h: h.index_tip.x)  # grande à esquerda
    assert near.palm_size_px > 1.3 * far.palm_size_px


def test_real_mediapipe_blank_image_has_no_hand(detector):
    import numpy as np

    blank = np.full((360, 640, 3), 128, dtype=np.uint8)
    assert detector.detect(blank, 90000) == []
