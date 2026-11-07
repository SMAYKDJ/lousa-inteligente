"""Gravação dos pontos da mão (sem imagem) e reprodução (D024)."""

import gzip
import json
import math
import random
from pathlib import Path

import pytest

from desktop import config
from desktop.vision.landmark_recorder import LandmarkRecorder, read_recording
from desktop.vision.synthetic_hands import HandPose, hand_shape
from tools import replay_landmarks


def _sideways(pose, yaw_deg, scale=0.07, aspect=16 / 9):
    a = math.radians(yaw_deg)
    pts = [(x * math.cos(a) + z * math.sin(a), y, -x * math.sin(a) + z * math.cos(a)) for x, y, z in hand_shape(pose)]
    return ([(0.5 + x * scale / aspect, 0.5 - y * scale, z * scale) for x, y, z in pts],
            [(x * 0.09, -y * 0.09, z * 0.09) for x, y, z in pts])


def test_round_trip_and_no_image(tmp_path):
    rec = LandmarkRecorder(tmp_path / "landmarks-x.jsonl.gz")
    img, wld = _sideways(HandPose((1, 0, 1, 1, 1)), 0)
    rec.write(1000, 16 / 9, [(img, wld, "Right")])
    rec.write(1033, 16 / 9, [])
    rec.close()
    frames = list(read_recording(tmp_path / "landmarks-x.jsonl.gz"))
    assert len(frames) == 2 and frames[0][0] == 1.0 and frames[1][2] == []
    assert len(frames[0][2][0][0]) == 21 and frames[0][2][0][2] == "Right"
    with gzip.open(tmp_path / "landmarks-x.jsonl.gz", "rt") as f:
        record = json.loads(f.readline())
    assert set(record) == {"t", "aspect", "hands"}  # só pontos e tempo: nenhuma imagem


def test_replay_compares_recognizers(tmp_path, capsys):
    random.seed(1)
    rec = LandmarkRecorder(tmp_path / "landmarks-20261107-120000.jsonl.gz")
    img0, wld0 = _sideways(HandPose((0.6, 0.1, 0.6, 0.65, 0.7)), 70)
    for i in range(600):
        img = [(x + random.gauss(0, 0.004), y + random.gauss(0, 0.004), z + random.gauss(0, 0.008)) for x, y, z in img0]
        wld = [(x + random.gauss(0, 0.003), y + random.gauss(0, 0.003), z + random.gauss(0, 0.006)) for x, y, z in wld0]
        rec.write(int(i * 1000 / 30), 16 / 9, [(img, wld, "Right")])
    rec.close()
    r = replay_landmarks.analyze(rec.path)
    assert r["frames"] == 600 and r["antigo"]["flips"] > 50 and r["novo"]["flips"] <= 2
    assert r["novo"]["time"]["pointing"] > 0.95
    assert replay_landmarks.main([str(rec.path)]) == 0
    out = capsys.readouterr().out
    assert "novo" in out and "antigo" in out and "trocas" in out


def test_replay_threshold_override(tmp_path):
    saved = (config.GESTURE_ENTER, config.GESTURE_EXIT, config.GESTURE_DEBOUNCE_S)
    try:
        rec = LandmarkRecorder(tmp_path / "landmarks-a.jsonl.gz")
        img, wld = _sideways(HandPose((1, 0, 1, 1, 1)), 0)
        for i in range(30):
            rec.write(i * 33, 16 / 9, [(img, wld, "Right")])
        rec.close()
        assert replay_landmarks.main([str(rec.path), "--enter", "0.5", "--exit", "0.3", "--debounce", "0.1"]) == 0
        assert config.GESTURE_ENTER == 0.5
    finally:
        config.GESTURE_ENTER, config.GESTURE_EXIT, config.GESTURE_DEBOUNCE_S = saved


def test_detector_records_when_enabled(tmp_path):
    pytest.importorskip("mediapipe")
    from desktop.vision.hand_tracker import MediaPipeHandDetector, decode_jpeg_rgb
    saved = config.RECORD_LANDMARKS_PATH
    config.RECORD_LANDMARKS_PATH = str(tmp_path / "landmarks-real.jsonl.gz")
    try:
        detector = MediaPipeHandDetector()
        rgb = decode_jpeg_rgb((Path(__file__).parent / "fixtures" / "hand_thumbs_up.jpg").read_bytes())
        detector.detect(rgb, 1)
        detector.close()
    finally:
        config.RECORD_LANDMARKS_PATH = saved
    frames = list(read_recording(tmp_path / "landmarks-real.jsonl.gz"))
    assert len(frames) == 1 and len(frames[0][2]) == 1
    assert frames[0][2][0][1] is not None and len(frames[0][2][0][1]) == 21  # pontos 3D do mundo também


REAL = config.LOG_DIR / "landmarks-20261107-122234.jsonl.gz"
REAL2 = config.LOG_DIR / "landmarks-20261107-133539.jsonl.gz"


@pytest.mark.parametrize("REAL", [REAL, REAL2], ids=["12h22", "13h35"])
def test_real_recording_regression(REAL):
    """Gravações reais de 2026-11-07 (12:22 e 13:35, nenhuma pinça de propósito na 1ª):
    o novo pisca muito menos que o antigo, e fechar a mão não vira toque nem caneta-pinça."""
    if not REAL.is_file():
        pytest.skip("gravação real só existe no Mac do usuário")
    from desktop.interaction.motions import MotionDetector, Sample, pinch_strength
    from desktop.interaction.pen_state import PenState
    from desktop.vision.gestures import GestureEngine
    r = replay_landmarks.analyze(REAL)
    assert r["novo"]["blinks"] * 5 < r["antigo"]["blinks"]
    engine, det, pen = GestureEngine(), MotionDetector(), PenState(mode="pinch")
    taps = downs = 0
    for t, aspect, hands in read_recording(REAL):
        res = engine.update(hands, t, aspect)
        if len(hands) != 1:
            det.update(None)
            continue
        g = res[0]
        taps += sum(e["event"] == "motion_tap" for e in det.update(
            Sample(t, 0.5, 0.5, g.board_pose, pinch_strength(g.pinch_gap), g.pinch_gap)))
        was = pen.down
        downs += pen.update(g.board_pose, g.pinch_gap) and not was
    assert taps == 0 and downs <= 15


REAL3 = config.LOG_DIR / "landmarks-20261107-135916.jsonl.gz"


@pytest.mark.parametrize("path", [REAL2, REAL3], ids=["13h35", "13h59"])
def test_real_pointing_is_recognized(path):
    """Quando o reconhecimento antigo vê "apontar", o novo também deve ver (era 63–66%)."""
    if not path.is_file():
        pytest.skip("gravação real só existe no Mac do usuário")
    from desktop.vision.gestures import GestureEngine
    from desktop.vision.hand_tracker import classify_pose, finger_ratios
    from desktop.vision.synthetic_hands import as_landmarks
    engine, both, legacy = GestureEngine(), 0, 0
    for t, aspect, hands in read_recording(path):
        res = engine.update(hands, t, aspect)
        if len(hands) != 1:
            continue
        if classify_pose(finger_ratios(as_landmarks(hands[0][0]), 640, round(640 / aspect))) == "pointing":
            legacy += 1
            both += res[0].board_pose == "pointing"
    assert both / legacy > 0.82
