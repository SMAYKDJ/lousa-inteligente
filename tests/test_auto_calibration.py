"""D034: calibração automática pelos marcadores (+1 toque) e reaproveitamento da última."""

from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from desktop import config  # noqa: E402
from desktop.calibration.calibration_state import Phase  # noqa: E402

FINGER = (0.012, -0.018)  # a ponta do dedo vista pela câmera fica um pouco deslocada (surface_norm)


@pytest.fixture
def make(tmp_path):
    from PySide6.QtWidgets import QApplication
    from desktop.calibration.markers import MarkerDetector
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge
    from tests.test_calibration_gui import Clock, _grab_gray, hold

    app = QApplication.instance() or QApplication([])
    windows = []

    def _make(path=tmp_path / "calibracao.json"):
        clock, log = Clock(), []
        w = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=clock,
                         event_log=lambda e, **f: log.append((e, f)), calibration_path=path)
        w.resize(1200, 600)
        w.filter_enabled = False
        w.show()
        windows.append(w)
        W, H = w.width(), w.height()

        def P(quad):
            return cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]), np.float32(quad))

        cams = {"ref": P([(70, 40), (580, 55), (565, 320), (60, 300)]),
                "moved": P([(110, 70), (600, 60), (610, 335), (95, 330)])}

        def cam_point(name, sx, sy, finger=True):
            if finger:
                sx, sy = sx + FINGER[0], sy + FINGER[1]
            x, y, ww = cams[name] @ np.array([sx * W, sy * H, 1.0])
            return (x / ww / 640, y / ww / 360)

        def observe(name):
            w.panel_visible = False
            gray = cv2.warpPerspective(_grab_gray(w), cams[name], (640, 360))
            return MarkerDetector().detect(cv2.cvtColor(cv2.GaussianBlur(gray, (3, 3), 0), cv2.COLOR_GRAY2RGB))

        def feed(name, n=config.CALIB_AUTO_READINGS):
            obs = observe(name)
            for _ in range(n):
                w._on_markers(obs)
            return obs

        return w, clock, log, cam_point, feed, lambda p, s: hold(w, clock, p, s)

    yield _make
    for w in windows:
        w.close()
        w.deleteLater()
    app.processEvents()


def _touch_center(w, clock, cam_point, hold, cam="ref"):
    assert w.calibration.phase is Phase.VERIFY
    for _ in range(3):
        if w.calibration.phase is not Phase.VERIFY:
            break
        hold(cam_point(cam, 0.5, 0.5), 7.2)


def test_markers_plus_one_touch_calibrates_and_corrects_finger_offset(make, tmp_path):
    w, clock, log, cam_point, feed, hold = make()
    w.start_auto_calibration()
    feed("ref")
    assert ("calibration_start", {"mode": "markers", "countdown_s": config.CALIBRATION_COUNTDOWN_S}) in log
    _touch_center(w, clock, cam_point, hold)
    assert w.calibrated and w.calibration.result.mode == "markers"
    assert "pelos marcadores" in w.calibration_summary
    # Em outro ponto, com o mesmo deslocamento do dedo, o cursor fica no lugar certo.
    W, H = w.width(), w.height()
    for sx, sy in ((0.2, 0.3), (0.8, 0.7)):
        hold(cam_point("ref", sx, sy), 0.1)
        pos = w.cursor_position()
        assert abs(pos.x() - sx * W) < 0.01 * W and abs(pos.y() - sy * H) < 0.01 * H
    # A referência dos marcadores grava a calibração para a próxima aula.
    feed("ref", 1)
    assert (tmp_path / "calibracao.json").exists()


def test_next_class_reuses_calibration_when_phone_did_not_move(make, tmp_path):
    w, clock, log, cam_point, feed, hold = make()
    w.start_auto_calibration()
    feed("ref")
    _touch_center(w, clock, cam_point, hold)
    feed("ref", 1)
    w.close()

    w2, clock2, log2, cam_point2, feed2, hold2 = make()
    w2.start_auto_calibration()
    feed2("ref")
    assert w2.calibrated and not w2.calibration.active  # nenhum toque
    assert any(e == "calibration_reused" for e, _ in log2)
    W, H = w2.width(), w2.height()
    hold2(cam_point2("ref", 0.6, 0.4), 0.1)
    pos = w2.cursor_position()
    assert abs(pos.x() - 0.6 * W) < 0.01 * W and abs(pos.y() - 0.4 * H) < 0.01 * H


def test_phone_moved_since_last_class_asks_one_touch(make):
    w, clock, log, cam_point, feed, hold = make()
    w.start_auto_calibration()
    feed("ref")
    _touch_center(w, clock, cam_point, hold)
    feed("ref", 1)
    w.close()

    w2, clock2, log2, cam_point2, feed2, hold2 = make()
    w2.start_auto_calibration()
    feed2("moved")
    assert not any(e == "calibration_reused" for e, _ in log2)
    assert w2.calibration.phase is Phase.VERIFY  # perspectiva nova pelos marcadores + 1 toque


def test_no_markers_falls_back_to_corners(make):
    w, clock, log, *_ = make()
    w.start_auto_calibration()
    w._on_markers({})
    clock.now += config.CALIB_AUTO_WAIT_S + 0.1
    w._calibration_tick()
    assert w.calibration.phase is Phase.CORNERS
    assert any(e == "calibration_auto_fallback" for e, _ in log)
    assert "4 cantos" in w.calibration.message


def test_touch_far_from_target_falls_back_to_corners(make):
    w, clock, log, cam_point, feed, hold = make()
    w.start_auto_calibration()
    feed("ref")
    hold(cam_point("ref", 0.62, 0.5, finger=False), 7.2)  # 12% longe do centro
    assert w.calibration.phase is Phase.CORNERS
    assert any(e == "calibration_markers_rejected" for e, _ in log)


def test_waits_for_the_phone_before_giving_up(make):
    w, clock, log, *_ = make()
    w.connect_card = True  # celular ainda não conectado
    w.start_auto_calibration()
    clock.now += 60
    w._calibration_tick()
    assert w._auto is not None and not w.calibration.active


def test_saved_calibration_ignored_if_screen_changed(tmp_path):
    from types import SimpleNamespace
    from desktop.calibration import calibration_store

    obs = {i: [SimpleNamespace(x=0.1 * i, y=0.2) for _ in range(4)] for i in range(4)}
    path = tmp_path / "c.json"
    calibration_store.save(path, np.eye(3), obs, (1920, 1080))
    saved = calibration_store.load(path)
    assert saved.matches(obs, (1920, 1080))
    assert not saved.matches(obs, (1280, 720))
    moved = {i: [SimpleNamespace(x=0.1 * i + 0.02, y=0.2) for _ in range(4)] for i in range(4)}
    assert not saved.matches(moved, (1920, 1080))
    path.write_text("lixo", encoding="utf-8")
    assert calibration_store.load(path) is None
