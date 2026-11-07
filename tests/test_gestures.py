"""Reconhecimento de poses com filtro, forma 3D e histerese (D022).

Adaptado do open-source-hands (MIT); as mãos sintéticas também vêm de lá.
"""

import math
import random

import pytest

from desktop import config
from desktop.vision.gestures import GestureEngine, compute_features, score_pose, POSES
from desktop.vision.hand_tracker import classify_pose, finger_ratios
from desktop.vision.synthetic_hands import POSES as SP, HandPose, as_landmarks, hand_shape, synthetic_hand

ASPECT = 16 / 9


def settle(engine, image, world, frames=10, t0=0.0, label="Right"):
    r = None
    for i in range(frames):
        r = engine.update([(image, world, label)], t0 + i / 30, ASPECT)[0]
    return r


@pytest.mark.parametrize("name,expected", [("open", "open"), ("fist", "fist"), ("point", "point"),
                                           ("victory", "victory"), ("pinch", "pinch"), ("ok", "ok"),
                                           ("claw", "claw"), ("relaxed", "open")])
@pytest.mark.parametrize("roll", [0.0, 1.2, 3.0])
@pytest.mark.parametrize("use_world", [True, False])
def test_synthetic_poses_any_roll_with_or_without_world(name, expected, roll, use_world):
    p = SP[name]
    image, world = synthetic_hand(0.5, 0.5, HandPose(p.curl, p.pinch, p.roll + roll, p.spread))
    r = settle(GestureEngine(), image, world if use_world else None)
    assert r.pose == expected, (r.pose, sorted(r.scores.items(), key=lambda kv: -kv[1])[:3])


def test_board_names_and_thumbs_up_does_not_write():
    image, world = synthetic_hand(0.5, 0.5, SP["point"])
    assert settle(GestureEngine(), image, world).board_pose == "pointing"
    image, world = synthetic_hand(0.5, 0.5, SP["thumbs-up"])
    assert settle(GestureEngine(), image, world).board_pose != "pointing"


def test_pinch_gap_closed_vs_open():
    pinched = settle(GestureEngine(), *synthetic_hand(0.5, 0.5, SP["pinch"]))
    apart = settle(GestureEngine(), *synthetic_hand(0.5, 0.5, SP["point"]))
    assert pinched.pinch_gap < config.PINCH_ON_RATIO < config.PINCH_OFF_RATIO < apart.pinch_gap
    assert pinched.pinch > 0.9 and apart.pinch < 0.1


def test_switch_needs_debounce_time_not_frames():
    e = GestureEngine()
    point, fist = synthetic_hand(0.5, 0.5, SP["point"]), synthetic_hand(0.5, 0.5, SP["fist"])
    assert settle(e, *point).pose == "point"
    # um único quadro de punho (33 ms) não troca a pose: a troca precisa durar 70 ms
    assert e.update([(fist[0], fist[1], "Right")], 1.0, ASPECT)[0].pose == "point"
    r = None
    for i in range(1, 12):
        r = e.update([(fist[0], fist[1], "Right")], 1.0 + i / 30, ASPECT)[0]
    assert r.pose == "fist"


def test_lost_hand_is_forgotten():
    e = GestureEngine()
    settle(e, *synthetic_hand(0.5, 0.5, SP["point"]))
    e.update([], 5.0, ASPECT)
    assert e.tracks == []


def test_two_hands_keep_their_own_state():
    e = GestureEngine()
    a, b = synthetic_hand(0.25, 0.5, SP["point"]), synthetic_hand(0.75, 0.5, SP["open"], left=True)
    r = None
    for i in range(10):
        r = e.update([(a[0], a[1], "Right"), (b[0], b[1], "Left")], i / 30, ASPECT)
    assert [x.pose for x in r] == ["point", "open"]
    for i in range(10, 20):  # ordem trocada no resultado do MediaPipe: cada mão segue a sua
        r = e.update([(b[0], b[1], "Left"), (a[0], a[1], "Right")], i / 30, ASPECT)
    assert [x.pose for x in r] == ["open", "point"]


def _sideways(pose, yaw_deg, scale):
    a = math.radians(yaw_deg)
    pts = [(x * math.cos(a) + z * math.sin(a), y, -x * math.sin(a) + z * math.cos(a)) for x, y, z in hand_shape(pose)]
    image = [(0.5 + x * scale / ASPECT, 0.5 - y * scale, z * scale) for x, y, z in pts]
    world = [(x * 0.09, -y * 0.09, z * 0.09) for x, y, z in pts]
    return image, world


def test_much_less_flicker_than_legacy_with_hand_sideways():
    """Professor de lado: mão a 70°, dedos relaxados, pequena na imagem, com tremor.

    Simulação de 2026-11-07: antigo 108 trocas em 20 s, novo 0.
    """
    random.seed(1)
    image0, world0 = _sideways(HandPose((0.6, 0.1, 0.6, 0.65, 0.7)), 70, 0.07)
    e, legacy, kit = GestureEngine(), [], []
    for i in range(600):
        image = [(x + random.gauss(0, 0.004), y + random.gauss(0, 0.004), z + random.gauss(0, 0.008))
                 for x, y, z in image0]
        world = [(x + random.gauss(0, 0.003), y + random.gauss(0, 0.003), z + random.gauss(0, 0.006))
                 for x, y, z in world0]
        legacy.append(classify_pose(finger_ratios(as_landmarks(image), 640, 360)))
        kit.append(e.update([(image, world, "Right")], i / 30, ASPECT)[0].board_pose)
    flips = lambda s: sum(a != b for a, b in zip(s, s[1:]))  # noqa: E731
    assert flips(legacy) > 50 and flips(kit[10:]) <= 2
    assert kit[10:].count("pointing") / len(kit[10:]) > 0.97


def test_features_curl_range():
    f = compute_features(*synthetic_hand(0.5, 0.5, SP["fist"]), ASPECT)
    assert all(c > 0.8 for c in f.curl[1:]) and f.openness < 0.2
    f = compute_features(*synthetic_hand(0.5, 0.5, SP["open"]), ASPECT)
    assert all(c < 0.1 for c in f.curl[1:]) and f.openness > 0.9


def test_score_is_geometric_with_worst_rule():
    f = compute_features(*synthetic_hand(0.5, 0.5, SP["point"]), ASPECT)
    point = next(p for p in POSES if p.id == "point")
    fist = next(p for p in POSES if p.id == "fist")
    assert score_pose(point, f) > 0.85 and score_pose(fist, f) < 0.05  # um dedo errado derruba


def test_relaxed_pointing_is_pointing_but_relaxed_hand_is_not():
    """O apontar real tem médio/anelar/mínimo meio dobrados (~0,55)."""
    img, wld = synthetic_hand(0.5, 0.5, HandPose((0.7, 0.1, 0.55, 0.55, 0.65)))
    assert settle(GestureEngine(), img, wld).board_pose == "pointing"
    img, wld = synthetic_hand(0.5, 0.5, SP["relaxed"])  # mão solta, dedos pouco dobrados
    assert settle(GestureEngine(), img, wld).board_pose != "pointing"
