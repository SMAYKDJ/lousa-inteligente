"""Celular mexido com os marcadores escondidos (D030): medida da cena, processador e janela."""

from __future__ import annotations

import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from desktop import config  # noqa: E402
from desktop.vision.scene_motion import SceneMotion, SceneShift, small_gray  # noqa: E402

H, W = 640, 360  # quadro como chega do celular em pé (640 no lado maior)
QUAD = [(0.15, 0.3), (0.85, 0.3), (0.85, 0.7), (0.15, 0.7)]  # lousa vista na câmera


def scene(rng, slide_seed=0):
    """Parede com textura em volta e uma lousa (slide) no meio."""
    base = cv2.GaussianBlur(rng.uniform(0, 255, (H, W)).astype(np.float32), (0, 0), 6)
    base = cv2.normalize(base, None, 40, 200, cv2.NORM_MINMAX)
    for _ in range(12):  # objetos na parede
        x, y = rng.integers(0, W), rng.integers(0, H)
        cv2.rectangle(base, (int(x), int(y)), (int(x) + 30, int(y) + 20), float(rng.uniform(0, 255)), -1)
    srng = np.random.default_rng(slide_seed)
    slide = cv2.GaussianBlur(srng.uniform(0, 255, (H, W)).astype(np.float32), (0, 0), 3)
    poly = np.round(np.array(QUAD) * [W, H]).astype(np.int32)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    return np.where(mask > 0, slide, base)


def shifted(img, dx_px, dy_px):
    m = np.float32([[1, 0, dx_px], [0, 1, dy_px]])
    return cv2.warpAffine(img, m, (W, H), borderMode=cv2.BORDER_REFLECT)


def rgb(img, rng=None):
    if rng is not None:
        img = img + rng.normal(0, 2, img.shape)
    g = np.clip(img, 0, 255).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)


def test_detects_phone_moved_and_ignores_slide_change():
    rng = np.random.default_rng(1)
    img = scene(rng)
    motion = SceneMotion()
    motion.set_reference(small_gray(rgb(img, rng)), QUAD)
    assert not motion.used_whole_frame  # a parede tem textura: a lousa fica de fora

    still = motion.measure(small_gray(rgb(img, rng)))
    assert still.magnitude < config.SCENE_MOVED_SHIFT

    # Slide trocou (só dentro da lousa): não é o celular.
    rng2 = np.random.default_rng(1)
    new_slide = scene(rng2, slide_seed=9)
    s = motion.measure(small_gray(rgb(new_slide, rng)))
    assert s.magnitude < config.SCENE_MOVED_SHIFT

    # Celular mexido: 12 px para a direita e 8 para baixo.
    moved = motion.measure(small_gray(rgb(shifted(img, 12, 8), rng)))
    assert moved.magnitude >= config.SCENE_MOVED_SHIFT and moved.response >= config.SCENE_MIN_RESPONSE
    assert abs(moved.dx - 12 / W) < 0.01 and abs(moved.dy - 8 / H) < 0.01


def test_person_walking_by_gives_disagreeing_measures():
    """Uma mancha grande atravessando a parede não imita um deslocamento firme."""
    rng = np.random.default_rng(2)
    img = scene(rng)
    motion = SceneMotion()
    motion.set_reference(small_gray(rgb(img, rng)), QUAD)
    triggers = 0
    for k in range(10):
        frame = img.copy()
        x = 20 + 30 * k
        cv2.rectangle(frame, (x, 380), (x + 70, 640), 20.0, -1)  # pessoa na frente da parede
        s = motion.measure(small_gray(rgb(frame, rng)))
        triggers += s.magnitude >= config.SCENE_MOVED_SHIFT and s.response >= config.SCENE_MIN_RESPONSE
    assert triggers <= 2


def test_plain_wall_falls_back_to_whole_frame():
    rng = np.random.default_rng(3)
    img = np.full((H, W), 180.0, np.float32)
    poly = np.round(np.array(QUAD) * [W, H]).astype(np.int32)
    slide = cv2.GaussianBlur(rng.uniform(0, 255, (H, W)).astype(np.float32), (0, 0), 3)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    img = np.where(mask > 0, slide, img)
    motion = SceneMotion()
    motion.set_reference(small_gray(rgb(img)), QUAD)
    assert motion.used_whole_frame
    moved = motion.measure(small_gray(rgb(shifted(img, 10, 0))))
    assert moved.magnitude >= config.SCENE_MOVED_SHIFT


# --- processador de quadros ---------------------------------------------------------

def test_processor_measures_only_while_watching():
    from desktop.communication.frame_protocol import FrameMessage
    from desktop.communication.message_protocol import HandState
    from desktop.vision.frame_processor import FrameProcessor, VisionEvents, VisionState

    rng = np.random.default_rng(4)
    img = scene(rng)
    frames = {b"a": rgb(img), b"b": rgb(shifted(img, 14, 0))}

    class Out(VisionEvents):
        def __init__(self):
            self.states, self.shifts, self.markers, self.tracked = [], [], 0, 0

        def on_hand_tracking(self, message):
            self.tracked += 1  # vem depois dos marcadores e da cena, no mesmo quadro

        def on_vision_state(self, state, detail):
            self.states.append(state)

        def on_markers(self, observation, w, h):
            self.markers += 1

        def on_scene_motion(self, shift):
            self.shifts.append(shift)

    class Det:
        def detect(self, rgb_, ts):
            return HandState(present=False)

        def close(self):
            pass

    class Markers:
        def detect(self, rgb_):
            return {}

    out = Out()
    proc = FrameProcessor(lambda: Det(), out, lambda jpeg: frames[jpeg[-1:]],
                          marker_detector_factory=Markers, marker_every_n=1)
    proc.start()
    try:
        deadline = time.monotonic() + 2
        while VisionState.READY not in out.states and time.monotonic() < deadline:
            time.sleep(0.005)

        def feed(seq, key):
            n = out.tracked
            proc.on_frame(FrameMessage(seq=seq, t_client_ms=float(seq), jpeg=b"\xff\xd8" + key))
            end = time.monotonic() + 2
            while out.tracked == n and time.monotonic() < end:
                time.sleep(0.005)

        feed(1, b"a")
        assert out.shifts == []  # sem pedido, não mede
        proc.watch_scene(QUAD)
        feed(2, b"a")  # tira a referência
        feed(3, b"a")
        feed(4, b"b")
        assert len(out.shifts) == 2
        assert out.shifts[0].magnitude < config.SCENE_MOVED_SHIFT
        assert abs(out.shifts[1].dx - 14 / W) < 0.01
        proc.stop_watching_scene()
        feed(5, b"b")
        feed(6, b"b")
        assert len(out.shifts) == 2
    finally:
        proc.stop()


# --- janela -----------------------------------------------------------------------------

class FakeWatch:
    def __init__(self):
        self.calls = []

    def watch_scene(self, quad):
        self.calls.append(("watch", quad))

    def stop_watching_scene(self):
        self.calls.append(("stop", None))


def test_window_brings_markers_back_when_phone_moves_and_hides_when_it_stops(qt_setup):
    window, clock, log, observe, P_ref, P_moved, cam_point, hold = qt_setup
    W_, H_ = window.width(), window.height()
    watch = FakeWatch()
    window.scene_watch = watch

    # Calibrado, referência ok, marcadores somem → começa a vigiar a cena.
    window._on_markers(observe(P_ref))
    clock.now += config.MARKER_HIDE_DELAY_S + 0.1
    window._after_marker_hide()
    window._ui_tick()
    assert not window.markers_visible
    assert watch.calls[-1][0] == "watch" and len(watch.calls[-1][1]) == 4

    # Medidas que não concordam (alguém passando): nada acontece.
    for dx in (0.02, -0.03, 0.025, -0.02):
        window._on_scene_motion(SceneShift(dx, 0.0, 0.3))
    assert not window.markers_visible

    # O celular mexe: medidas firmes → os cantos voltam sozinhos.
    for _ in range(config.SCENE_MOVED_CONFIRMATIONS):
        window._on_scene_motion(SceneShift(0.03, 0.02, 0.3))
    assert window.markers_visible
    assert any(e == "phone_moved" for e, _ in log)
    window._ui_tick()
    assert watch.calls[-1] == ("stop", None)

    # A câmera vê os marcadores no novo lugar; com as leituras firmes por 1 s, eles somem.
    moved = observe(P_moved)
    assert sorted(moved) == [0, 1, 2, 3]
    for _ in range(config.MARKER_JUMP_CONFIRMATIONS + config.SCENE_SETTLE_CHECKS + 2):
        clock.now += 0.15
        window._on_markers(moved)
    assert not window.markers_visible
    assert any(e == "phone_reframed" for e, _ in log)
    assert "reenquadrado" in window.marker_status
    window._ui_tick()
    assert watch.calls[-1][0] == "watch"  # nova foto de referência, no lugar novo

    hold(window, clock, cam_point(P_moved, 0.3, 0.6), 0.1)
    pos = window.cursor_position()
    assert abs(pos.x() - 0.3 * W_) < 0.015 * W_ and abs(pos.y() - 0.6 * H_) < 0.015 * H_


def test_window_does_not_watch_without_marker_reference(qt_setup):
    window, clock, log, *_ = qt_setup
    watch = FakeWatch()
    window.scene_watch = watch
    clock.now += 10
    window._check_reference_timeout()  # referência falhou: não há correção para manter
    window._ui_tick()
    assert watch.calls == []


@pytest.fixture
def qt_setup(monkeypatch):
    """Lousa calibrada com a câmera de referência, como no teste dos marcadores."""
    from tests.test_calibration_gui import _grab_gray, hold
    from tests.test_calibration_gui import Clock
    from desktop.calibration.markers import MarkerDetector
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(config, "MARKERS_HIDE_AFTER_CALIBRATION", True)
    app = QApplication.instance() or QApplication([])
    clock, log = Clock(), []
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=clock,
                          event_log=lambda event, **f: log.append((event, f)))
    window.resize(1200, 600)
    window.filter_enabled = False
    window.show()
    Wd, Hd = window.width(), window.height()
    CW, CH = 640, 360

    def P(quad):
        return cv2.getPerspectiveTransform(np.float32([(0, 0), (Wd, 0), (Wd, Hd), (0, Hd)]), np.float32(quad))

    P_ref = P([(70, 40), (580, 55), (565, 320), (60, 300)])
    P_moved = P([(110, 70), (600, 60), (610, 335), (95, 330)])

    def cam_point(Pm, sx, sy):
        x, y, w = Pm @ np.array([sx * Wd, sy * Hd, 1.0])
        return (x / w / CW, y / w / CH)

    def observe(Pm):
        window.panel_visible = False
        gray = cv2.warpPerspective(_grab_gray(window), Pm, (CW, CH))
        return MarkerDetector().detect(cv2.cvtColor(cv2.GaussianBlur(gray, (3, 3), 0), cv2.COLOR_GRAY2RGB))

    window.start_calibration()
    for _ in range(5):
        t = window._overlay_session().view(clock.now).target
        hold(window, clock, cam_point(P_ref, t.x, t.y), 7.2)
    assert window.calibrated
    yield window, clock, log, observe, P_ref, P_moved, cam_point, hold
    window.close()
    window.deleteLater()
    app.processEvents()


def test_window_ignores_scene_motion_while_holding_a_drawing(qt_setup):
    window, clock, log, observe, P_ref, *_ = qt_setup
    window.scene_watch = FakeWatch()
    window._on_markers(observe(P_ref))
    clock.now += config.MARKER_HIDE_DELAY_S + 0.1
    window._after_marker_hide()
    window._ui_tick()
    window._tools.selected = 0  # segurando um desenho: mão grande perto da câmera
    for _ in range(config.SCENE_MOVED_CONFIRMATIONS + 2):
        window._on_scene_motion(SceneShift(0.03, 0.02, 0.3))
    assert not window.markers_visible
    window._tools.selected = None
    for _ in range(config.SCENE_MOVED_CONFIRMATIONS):
        window._on_scene_motion(SceneShift(0.03, 0.02, 0.3))
    assert window.markers_visible
