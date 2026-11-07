"""Pose da mão (dedos esticados) e estado da caneta (Fase 4, D018)."""

import math
from types import SimpleNamespace as P

import pytest

from desktop.interaction.pen_state import PenState
from desktop.vision.hand_tracker import classify_pose, finger_ratios


def synthetic_hand(extended: set[str], angle_deg: float = 0.0, scale: float = 0.1):
    """21 landmarks de uma mão em camera_norm, girada; dedos esticados ou dobrados."""
    pts = [None] * 21
    a = math.radians(angle_deg)

    def put(i, x, y):
        rx, ry = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        pts[i] = P(x=0.5 + rx * scale, y=0.5 + ry * scale, z=0.0)

    put(0, 0, 0)  # pulso
    for k, (mcp, pip, dip, tip) in enumerate(((5, 6, 7, 8), (9, 10, 11, 12),
                                               (13, 14, 15, 16), (17, 18, 19, 20))):
        name = ("index", "middle", "ring", "pinky")[k]
        x = -0.3 + 0.2 * k
        put(mcp, x, -1.0)
        put(pip, x, -1.45)
        if name in extended:
            put(dip, x, -1.75)
            put(tip, x, -2.05)
        else:  # dobrado: a ponta volta para perto da palma
            put(dip, x + 0.05, -1.25)
            put(tip, x + 0.05, -1.0)
    for i in range(1, 5):  # polegar (ignorado na regra)
        put(i, -0.5 - 0.1 * i, -0.3 * i)
    return pts


ALL = {"index", "middle", "ring", "pinky"}


@pytest.mark.parametrize("angle", [0, 45, 90, 180, -120])
def test_pointing_open_fist_at_any_rotation(angle):
    for extended, expected in (({"index"}, "pointing"), (ALL, "open"), (set(), "fist"),
                               ({"index", "middle"}, "other")):
        ratios = finger_ratios(synthetic_hand(extended, angle), 640, 360)
        assert classify_pose(ratios) == expected, (extended, angle, ratios)


def test_ratios_extended_vs_curled():
    ratios = finger_ratios(synthetic_hand({"index"}), 640, 360)
    assert ratios["index"] > 1.15 and all(ratios[k] < 1.0 for k in ("middle", "ring", "pinky"))


def test_real_photo_thumbs_up_is_not_writing():
    pytest.importorskip("mediapipe")
    from pathlib import Path

    from desktop.vision.hand_tracker import MediaPipeHandDetector, decode_jpeg_rgb

    detector = MediaPipeHandDetector()
    try:
        rgb = decode_jpeg_rgb((Path(__file__).parent / "fixtures" / "hand_thumbs_up.jpg").read_bytes())
        hands = detector.detect(rgb, 1)
    finally:
        detector.close()
    assert hands and all(h.pose != "pointing" for h in hands)  # polegar para cima não escreve
    assert all(h.pose_alt is not None and h.pose_alt != "pointing" for h in hands)  # o outro reconhecimento também


# --- estado da caneta -------------------------------------------------------------

def test_pen_goes_down_after_two_pointing_frames():
    pen = PenState(down_frames=2, up_frames=3)
    assert pen.update("pointing") is False
    assert pen.update("pointing") is True


def test_one_bad_frame_does_not_break_the_stroke():
    pen = PenState(down_frames=2, up_frames=3)
    for pose in ("pointing", "pointing", "open", "pointing", "other", None, "pointing"):
        state = pen.update(pose)
    assert state is True


def test_pen_lifts_after_three_frames_open_or_lost():
    pen = PenState(down_frames=2, up_frames=3)
    pen.update("pointing"), pen.update("pointing")
    assert [pen.update(p) for p in ("open", "open", "open")] == [True, True, False]
    pen.update("pointing"), pen.update("pointing")
    assert [pen.update(None) for _ in range(3)][-1] is False


def test_isolated_pointing_frame_does_not_start():
    pen = PenState(down_frames=2, up_frames=3)
    assert [pen.update(p) for p in ("pointing", "open", "pointing", "fist")] == [False] * 4


def test_openness_fist_vs_open_any_rotation():
    from desktop.vision.hand_tracker import hand_openness
    for angle in (0, 70, 180):
        fist = hand_openness(synthetic_hand(set(), angle), 640, 360)
        point = hand_openness(synthetic_hand({"index"}, angle), 640, 360)
        open_ = hand_openness(synthetic_hand(ALL, angle), 640, 360)
        assert fist < point < open_ and open_ > 1.6 * fist, (angle, fist, point, open_)


def test_pinch_ratio_closed_vs_apart_any_rotation():
    from desktop.vision.hand_tracker import pinch_ratio
    for angle in (0, 90, 200):
        apart = synthetic_hand({"index"}, angle)
        pinched = synthetic_hand({"index"}, angle)
        pinched[4] = P(x=pinched[8].x + 0.002, y=pinched[8].y + 0.002, z=0.0)  # polegar na ponta do indicador
        assert pinch_ratio(pinched, 640, 360) < 0.1 < 0.6 < pinch_ratio(apart, 640, 360)


def test_pen_pinch_mode_with_hysteresis():
    p = PenState(down_frames=2, up_frames=3, mode="pinch")
    from desktop import config
    mid = (config.PINCH_ON_RATIO + config.PINCH_OFF_RATIO) / 2
    for _ in range(3):
        p.update("open", mid)  # entre ON e OFF, ainda levantada: não desce
    assert not p.down
    for _ in range(2):
        p.update("other", 0.08)
    assert p.down  # pinça fechada desce, qualquer pose (menos punho)
    for _ in range(5):
        p.update("other", mid)  # abriu um pouco (abaixo de OFF): continua descida
    assert p.down
    for _ in range(3):
        p.update("other", 0.7)
    assert not p.down
    for _ in range(2):
        p.update("pointing", None)  # sem medida: não desce
    assert not p.down


def test_real_photo_is_not_a_pinch():
    pytest.importorskip("mediapipe")
    from pathlib import Path

    from desktop import config
    from desktop.vision.hand_tracker import MediaPipeHandDetector, decode_jpeg_rgb
    detector = MediaPipeHandDetector()
    try:
        rgb = decode_jpeg_rgb((Path(__file__).parent / "fixtures" / "hand_thumbs_up.jpg").read_bytes())
        hands = detector.detect(rgb, 1)
    finally:
        detector.close()
    assert hands and all(h.pinch is not None and h.pinch > config.PINCH_OFF_RATIO for h in hands)


def test_pen_pinch_mode_ignores_fist():
    """Mão fechada nunca é pinça (teste real 2026-11-07: o polegar encosta no indicador dobrado)."""
    p = PenState(down_frames=2, up_frames=3, mode="pinch")
    for _ in range(5):
        p.update("fist", 0.08)
    assert not p.down
    for _ in range(2):
        p.update("other", 0.08)
    assert p.down
    for _ in range(3):
        p.update("fist", 0.08)  # fechou a mão: levanta
    assert not p.down
