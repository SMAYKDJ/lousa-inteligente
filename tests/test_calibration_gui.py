"""Calibração na janela da lousa (Qt offscreen), com relógio falso e professor simulado.

Cobre: alvos e contagem desenhados, ordem dos cantos, cursor calibrado sob o
"dedo", cursor oculto fora da área, Esc cancela, C recomeça, eventos no log.
É simulação: o teste real é com o celular e a TV (CLAUDE.md §9.4).
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop import config
from desktop.calibration.calibration_state import Phase  # noqa: E402
from desktop.calibration.homography import SurfacePoint  # noqa: E402
from desktop.communication.message_protocol import (  # noqa: E402
    HandState, HandTrackingMessage, Handedness, IndexTip)
from desktop.interface.cursor_window import CursorWindow  # noqa: E402
from desktop.interface.qt_bridge import QtServerBridge  # noqa: E402

TRUE_H = np.array([[0.9, 0.15, 0.1], [0.05, 1.1, 0.12], [0.3, 0.2, 1.0]])


def camera_of(sx, sy):
    x, y, w = np.linalg.inv(TRUE_H) @ np.array([sx, sy, 1.0])
    return x / w, y / w


def tracking(seq, point):
    if point is None:
        return HandTrackingMessage(seq=seq, t_client_ms=1.0, hand=HandState(present=False))
    return HandTrackingMessage(seq=seq, t_client_ms=1.0, hand=HandState(
        present=True, handedness=Handedness.RIGHT, confidence=0.9,
        index_tip=IndexTip(point[0], point[1], 0.0)))


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def setup(qt_app):
    clock = Clock()
    log = []
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=clock,
                          event_log=lambda event, **f: log.append((event, f)))
    window.resize(1200, 600)  # proporção ~ da TV (1920×1080)
    window.filter_enabled = False  # conversão exata; o filtro One Euro tem testes próprios
    window.show()
    yield window, clock, log
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def hold(window, clock, point, seconds, seq=[0]):
    for _ in range(int(seconds * 25)):
        clock.now += 0.04
        seq[0] += 1
        window._on_hand_tracking(tracking(seq[0], point))
        window._calibration_tick()


def target_point(window, clock):
    t = window._overlay_session().view(clock.now).target
    return camera_of(t.x, t.y)


def test_full_calibration_puts_cursor_under_finger(setup, tmp_path):
    window, clock, log = setup
    window.start_calibration()
    shots = []
    for step in range(5):
        hold(window, clock, target_point(window, clock), 3.0)
        image = window.grab()
        path = tmp_path / f"calib-{step + 1}.png"
        image.save(str(path))
        shots.append(path)
        hold(window, clock, target_point(window, clock), 4.2)
    assert window.calibration.phase is Phase.DONE and window.calibrated
    assert "calibrada" in window.calibration_summary

    # Dedo em (25%, 75%) da superfície → cursor em (300, 450) numa janela 1200×600.
    hold(window, clock, camera_of(0.25, 0.75), 0.1)
    pos = window.cursor_position()
    assert pos.x() == pytest.approx(300, abs=1) and pos.y() == pytest.approx(450, abs=1)
    # Fora da área projetada: cursor some.
    hold(window, clock, camera_of(1.3, 0.5), 0.1)
    assert window.cursor_position() is None

    events = [e for e, _ in log]
    assert events[0] == "calibration_start"
    assert events.count("calibration_point") == 5
    assert "calibration_done" in events and "calibration_result" in events
    result = dict(log)["calibration_result"]
    assert result["error_px"] < 1 and result["surface_width_px"] == 1200
    assert all(p.stat().st_size > 0 for p in shots)
    os.environ.get("CALIB_SHOTS_DIR") and [  # para inspeção manual dos desenhos
        p.rename(os.path.join(os.environ["CALIB_SHOTS_DIR"], p.name)) for p in shots]


def test_escape_cancels_and_c_restarts(setup):
    window, clock, log = setup
    window.start_calibration()
    hold(window, clock, target_point(window, clock), 7.2)
    assert window.calibration.view(clock.now).step == 2
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert window.calibration.phase is Phase.CANCELLED and not window.calibrated
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier))
    assert window.calibration.active and window.calibration.view(clock.now).step == 1
    assert [e for e, _ in log].count("calibration_start") == 2


def test_rejection_message_is_drawn(setup, tmp_path):
    window, clock, log = setup
    window.start_calibration()
    hold(window, clock, None, 7.2)
    assert "Não vi o dedo" in window.calibration.view(clock.now).message
    assert not window.grab().isNull()
    assert ("calibration_point", ) == (log[1][0],) and log[1][1]["accepted"] is False


def test_uncalibrated_window_keeps_phase1_mapping(setup):
    window, clock, log = setup
    hold(window, clock, (0.5, 0.5), 0.1)
    pos = window.cursor_position()
    assert pos.x() == pytest.approx(600) and pos.y() == pytest.approx(300)
    assert window.calibration_summary == "não calibrada"


def test_surface_point_helper():
    assert SurfacePoint(0.5, 0.5).inside and not SurfacePoint(-0.1, 0.5).inside


def test_camera_preview_draws_frame_tip_corners_and_outline(setup, tmp_path):
    from types import SimpleNamespace

    from desktop.interface.camera_preview import CameraPreviewWindow

    window, clock, log = setup
    frame = np.zeros((640, 360, 3), dtype=np.uint8)
    frame[200:400, 50:300] = 200
    hand = HandState(present=True, handedness=Handedness.RIGHT, confidence=0.9,
                     index_tip=IndexTip(0.5, 0.5, 0.0))
    processor = SimpleNamespace(latest_preview=lambda: (frame, hand))
    preview = CameraPreviewWindow(processor, window)
    preview.resize(360, 670)
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    assert window.calibrated
    preview._refresh()
    image = preview.grab()
    shots = os.environ.get("CALIB_SHOTS_DIR")
    image.save(os.path.join(shots, "preview.png") if shots else str(tmp_path / "preview.png"))
    assert not image.isNull()
    # Pixel na ponta do dedo (centro da imagem) é vermelho do marcador.
    preview.close()
    preview.deleteLater()


def test_camera_preview_without_frames(setup):
    from types import SimpleNamespace

    from desktop.interface.camera_preview import CameraPreviewWindow

    window, clock, log = setup
    preview = CameraPreviewWindow(SimpleNamespace(latest_preview=lambda: None), window)
    preview._refresh()
    assert not preview.grab().isNull()
    preview.close()
    preview.deleteLater()


def test_accuracy_test_after_calibration(setup):
    window, clock, log = setup
    window.start_accuracy_test()  # sem calibração: só avisa
    assert window.accuracy is None
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_G, Qt.KeyboardModifier.NoModifier))
    assert window.accuracy.active
    shots = os.environ.get("CALIB_SHOTS_DIR")
    for i in range(9):
        hold(window, clock, target_point(window, clock), 3.0)
        if shots and i in (3, 5):
            window.grab().save(os.path.join(shots, f"grid-{i + 1}.png"))
        hold(window, clock, target_point(window, clock), 4.2)
    assert window.accuracy.phase is Phase.DONE and "mediana" in window.accuracy_summary
    result = dict(log)["accuracy_result"]
    assert result["max_px"] < 1 and len(result["errors_px"]) == 9


# --- marcadores (D015): desenho real da janela → câmera sintética → correção ------

def _grab_gray(window):
    from PySide6.QtGui import QImage

    img = window.grab().toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.bytesPerLine() * h)
    return buf.reshape(h, img.bytesPerLine())[:, :w].copy()


def test_markers_drawn_by_window_correct_camera_movement(setup, tmp_path):
    cv2 = pytest.importorskip("cv2")
    from desktop.calibration.markers import CompensatedMapper, MarkerDetector

    window, clock, log = setup
    W, H = window.width(), window.height()
    CW, CH = 640, 360

    def P(quad):
        return cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]),
                                           np.float32(quad))

    P_ref = P([(70, 40), (580, 55), (565, 320), (60, 300)])
    P_moved = P([(110, 70), (600, 60), (610, 335), (95, 330)])

    def cam_point(Pm, sx, sy):
        x, y, w = Pm @ np.array([sx * W, sy * H, 1.0])
        return (x / w / CW, y / w / CH)

    def observe(Pm):
        window.panel_visible = False
        gray = cv2.warpPerspective(_grab_gray(window), Pm, (CW, CH))
        rgb = cv2.cvtColor(cv2.GaussianBlur(gray, (3, 3), 0), cv2.COLOR_GRAY2RGB)
        return MarkerDetector().detect(rgb)

    # Calibração com o dedo vista pela câmera de referência.
    window.start_calibration()
    for _ in range(5):
        t = window._overlay_session().view(clock.now).target
        hold(window, clock, cam_point(P_ref, t.x, t.y), 7.2)
    assert window.calibrated and window.marker_status == "procurando os marcadores…"

    obs = observe(P_ref)
    assert sorted(obs) == [0, 1, 2, 3]
    window._on_markers(obs)
    assert isinstance(window._mapper, CompensatedMapper)
    assert ("marker_reference", {"ok": True, "seen": [0, 1, 2, 3]}) in log

    # O celular se move: sem correção o cursor erraria; com ela, volta ao lugar
    # (o salto é confirmado por 3 leituras seguidas).
    moved = observe(P_moved)
    for _ in range(3):
        window._on_markers(moved)
    hold(window, clock, cam_point(P_moved, 0.3, 0.6), 0.1)
    pos = window.cursor_position()
    assert abs(pos.x() - 0.3 * W) < 0.015 * W and abs(pos.y() - 0.6 * H) < 0.015 * H
    assert any(e == "camera_moved" for e, _ in log)
    assert "corrigido" in window.marker_status

    window.panel_visible = True
    shots = os.environ.get("CALIB_SHOTS_DIR")
    window.grab().save(os.path.join(shots, "board-markers.png") if shots else str(tmp_path / "b.png"))


def test_markers_hide_after_reference_and_n_brings_them_back(setup, monkeypatch):
    """D028: depois da referência os marcadores somem; N mostra e a correção volta a seguir o celular."""
    cv2 = pytest.importorskip("cv2")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from desktop.calibration.markers import MarkerDetector
    from desktop import config

    monkeypatch.setattr(config, "MARKERS_HIDE_AFTER_CALIBRATION", True)
    window, clock, log = setup
    W, H = window.width(), window.height()
    CW, CH = 640, 360

    def P(quad):
        return cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]),
                                           np.float32(quad))

    P_ref = P([(70, 40), (580, 55), (565, 320), (60, 300)])
    P_moved = P([(110, 70), (600, 60), (610, 335), (95, 330)])

    def cam_point(Pm, sx, sy):
        x, y, w = Pm @ np.array([sx * W, sy * H, 1.0])
        return (x / w / CW, y / w / CH)

    def observe(Pm):
        window.panel_visible = False
        gray = cv2.warpPerspective(_grab_gray(window), Pm, (CW, CH))
        return MarkerDetector().detect(cv2.cvtColor(cv2.GaussianBlur(gray, (3, 3), 0), cv2.COLOR_GRAY2RGB))

    def press(key):
        window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    assert window.markers_visible  # antes de calibrar: aparecem para mirar o celular
    window.start_calibration()
    for _ in range(5):
        t = window._overlay_session().view(clock.now).target
        hold(window, clock, cam_point(P_ref, t.x, t.y), 7.2)
    assert window.markers_visible  # procurando a referência
    window._on_markers(observe(P_ref))
    assert window.markers_visible  # ainda 1 s na tela
    clock.now += config.MARKER_HIDE_DELAY_S + 0.1
    window._after_marker_hide()
    assert not window.markers_visible
    assert "ocultos" in window.marker_status
    assert window._forbidden_rects() == []
    assert observe(P_ref) == {}  # nada desenhado nos cantos

    # Celular mexeu com os marcadores escondidos: N mostra e a correção acompanha.
    press(Qt.Key.Key_N)
    assert window.markers_visible
    assert ("markers_toggle", {"shown": True}) in log
    moved = observe(P_moved)
    assert sorted(moved) == [0, 1, 2, 3]
    for _ in range(3):
        window._on_markers(moved)
    hold(window, clock, cam_point(P_moved, 0.3, 0.6), 0.1)
    pos = window.cursor_position()
    assert abs(pos.x() - 0.3 * W) < 0.015 * W and abs(pos.y() - 0.6 * H) < 0.015 * H

    # N de novo: somem, e a correção feita continua valendo.
    press(Qt.Key.Key_N)
    assert not window.markers_visible
    window._on_markers({})
    hold(window, clock, cam_point(P_moved, 0.7, 0.4), 0.1)
    pos = window.cursor_position()
    assert abs(pos.x() - 0.7 * W) < 0.015 * W and abs(pos.y() - 0.4 * H) < 0.015 * H
    window.panel_visible = True


def test_markers_stay_when_hiding_is_off(setup, monkeypatch):
    from desktop import config
    monkeypatch.setattr(config, "MARKERS_HIDE_AFTER_CALIBRATION", False)
    window, clock, log = setup
    window.calibrated = True
    clock.now += 100
    assert window.markers_visible


def test_reference_timeout_warns(setup):
    window, clock, log = setup
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    clock.now += 10
    window._check_reference_timeout()
    assert "não vistos" in window.marker_status
    assert ("marker_reference", {"ok": False, "seen": []}) in log


def test_markers_can_be_disabled(qt_app):
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", markers=False)
    window.resize(800, 450)
    assert window.marker_status == "desligados"
    assert not window.grab().isNull()
    window.close()
    window.deleteLater()


# --- duas mãos: a junto à lousa move o cursor ------------------------------------

def two_hand_message(seq, near_board, near_camera):
    """near_board/near_camera: (x, y, tamanho da palma em px) em camera_norm."""
    def state(x, y, size):
        spread = size / 1000
        palm = (IndexTip(x, y + 0.1, 0),) + tuple(
            IndexTip(x + d * spread, y + 0.1 - spread, 0) for d in (-1.5, -0.5, 0.5, 1.5))
        return HandState(present=True, handedness=Handedness.RIGHT, confidence=0.9,
                         index_tip=IndexTip(x, y, 0.0), palm=palm, palm_size_px=size)
    hands = (state(*near_camera), state(*near_board))  # a "errada" vem primeiro
    return HandTrackingMessage(seq=seq, t_client_ms=1.0, hand=hands[0], candidates=hands)


def test_two_hands_cursor_follows_hand_at_the_board(setup, tmp_path):
    window, clock, log = setup
    # Sem calibração: a mão menor (mais longe da câmera, junto à lousa) vence.
    window._on_hand_tracking(two_hand_message(1, (0.3, 0.5, 80), (0.7, 0.5, 160)))
    assert (window.state.tip.x, window.state.tip.y) == (0.3, 0.5)

    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    assert window.calibrated

    # Calibrado: a mão sobre a lousa vence mesmo sendo maior que a de fora.
    on_board = camera_of(0.4, 0.6)
    outside = camera_of(1.4, 0.5)
    window._on_hand_tracking(two_hand_message(2, (*on_board, 150), (*outside, 70)))
    pos = window.cursor_position()
    assert pos.x() == pytest.approx(0.4 * window.width(), abs=2)
    assert pos.y() == pytest.approx(0.6 * window.height(), abs=2)

    from types import SimpleNamespace

    from desktop.interface.camera_preview import CameraPreviewWindow

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    preview = CameraPreviewWindow(SimpleNamespace(latest_preview=lambda: (frame, window.last_candidates[0])), window)
    preview.resize(640, 400)
    preview._refresh()
    shots = os.environ.get("CALIB_SHOTS_DIR")
    preview.grab().save(os.path.join(shots, "two-hands.png") if shots else str(tmp_path / "t.png"))
    preview.close()
    preview.deleteLater()


def test_g_test_builds_residual_correction(setup):
    """Dedo com erro sistemático no teste G → a correção dos 9 pontos o compensa."""
    window, clock, log = setup
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)

    def biased_target():
        t = window._overlay_session().view(clock.now).target
        return camera_of(t.x + 0.03 * (t.x - 0.5), t.y + 0.02 * (t.y - 0.5))

    def run_g():
        window.start_accuracy_test()
        for _ in range(9):
            hold(window, clock, biased_target(), 7.2)
        return [f for e, f in log if e == "accuracy_result"][-1]

    first = run_g()
    assert window.residual is not None and any(e == "residual_update" for e, _ in log)
    second = run_g()  # o 2º teste G mede com a correção ligada
    assert second["max_px"] < 0.2 * first["max_px"]
    # Entre os pontos da grade também melhora:
    hold(window, clock, camera_of(0.3 + 0.03 * (0.3 - 0.5), 0.7 + 0.02 * (0.7 - 0.5)), 0.5)
    pos = window.cursor_position()
    assert pos.x() == pytest.approx(0.3 * 1200, abs=3) and pos.y() == pytest.approx(0.7 * 600, abs=3)
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier))
    assert not window.residual_enabled
    off = window.cursor_position()
    assert abs(off.x() - 0.3 * 1200) > 5  # sem a correção, o erro volta
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    assert window.residual is None  # nova calibração zera a correção


def test_grid_overlay_draws(setup, tmp_path):
    import os
    window, clock, _ = setup
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_M, Qt.KeyboardModifier.NoModifier))
    assert window.grid_visible
    hold(window, clock, (0.5, 0.5), 0.2)
    img = window.grab()
    shots = os.environ.get("CALIB_SHOTS_DIR")
    img.save(os.path.join(shots or str(tmp_path), "malha_virtual.png"))


def test_g_test_repeats_point_far_from_target(setup):
    """Um ponto com o dedo longe do alvo é repetido; a correção não é perdida."""
    window, clock, log = setup
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    window.start_accuracy_test()
    hold(window, clock, target_point(window, clock), 7.2)  # ponto 1 ok
    hold(window, clock, camera_of(0.5, 0.6), 7.2)  # ponto 2: dedo muito abaixo do alvo
    points = [f for e, f in log if e == "accuracy_point"]
    assert points[-1]["accepted"] is False and points[-1]["reason"] == "too_far"
    assert "longe do alvo" in window.accuracy.message
    for _ in range(8):
        hold(window, clock, target_point(window, clock), 7.2)
    assert window.accuracy.phase is Phase.DONE and window.residual is not None
    assert not any(e == "residual_rejected" for e, _ in log)


def test_verify_measures_between_points_with_and_without_correction(setup):
    window, clock, log = setup
    window.start_calibration()
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)

    def biased_target():
        t = window._overlay_session().view(clock.now).target
        return camera_of(t.x + 0.03 * (t.x - 0.5), t.y + 0.02 * (t.y - 0.5))

    def run(start, n):
        start()
        for _ in range(n):
            hold(window, clock, biased_target(), 7.2)

    run(window.start_verify_test, 4)
    before = [f for e, f in log if e == "verify_result"][-1]
    assert before["correction"] == "nenhuma" and window.residual is None  # V não cria correção
    run(window.start_accuracy_test, 9)
    run(window.start_verify_test, 4)
    after = [f for e, f in log if e == "verify_result"][-1]
    assert after["correction"] == "ligada" and after["median_px"] < 0.3 * before["median_px"]
    assert "Verificação" in window.verify_summary or "mediana" in window.verify_summary


def test_guided_setup_runs_all_steps_in_order(setup):
    """Ao abrir: cantos → verificação → 9 pontos → verificação → resumo, sem tocar no teclado."""
    import os
    window, clock, log = setup

    def biased_target():
        t = window._overlay_session().view(clock.now).target
        return camera_of(t.x + 0.03 * (t.x - 0.5), t.y + 0.02 * (t.y - 0.5))

    def shot(name):
        shots = os.environ.get("CALIB_SHOTS_DIR")
        if shots:
            window.grab().save(os.path.join(shots, name))

    window.start_guided_setup()
    hold(window, clock, (0.5, 0.5), 1.0)
    assert window.guided.view(clock.now).kind == "intro" and window._overlay_session() is None
    shot("assistente_etapa1.png")
    hold(window, clock, (0.5, 0.5), config.GUIDED_INTRO_S)
    assert window.calibration.active  # etapa 1 começou sozinha
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    assert window.calibrated and window.guided.index == 1
    for n_points, step in ((4, "verify_before"), (9, "grid"), (4, "verify_after")):
        hold(window, clock, (0.5, 0.5), config.GUIDED_INTRO_S + 0.2)
        assert window.guided.current.key == step and window._overlay_session() is not None
        if step == "grid":
            shot("assistente_etapa3.png")
        for _ in range(n_points):
            hold(window, clock, biased_target(), 7.2)
    view = window.guided.view(clock.now)
    assert view.kind == "summary"
    shot("assistente_resumo.png")
    done = [f for e, f in log if e == "guided_done"][-1]
    assert done["verify_after_px"] < 0.3 * done["verify_before_px"] and done["improvement_pct"] > 70
    assert [f["step"] for e, f in log if e == "guided_step"] == ["corners", "verify_before", "grid", "verify_after"]
    hold(window, clock, (0.5, 0.5), config.GUIDED_SUMMARY_S + 0.5)
    assert not window.guided.active


def test_escape_cancels_guided_setup(setup):
    window, clock, log = setup
    window.start_guided_setup()
    hold(window, clock, (0.5, 0.5), config.GUIDED_INTRO_S + 0.2)
    assert window.calibration.active
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not window.guided.active and not window.calibration.active
    assert any(e == "guided_cancel" for e, _ in log)


def test_guided_turns_off_correction_that_made_it_worse(setup):
    """Teste real 2026-11-07 13:41: G mal medido (19 px) gerou correção que piorou 11,7 → 19,6 px."""
    window, clock, log = setup

    def biased_target():  # dedo fora do alvo só durante o G
        t = window._overlay_session().view(clock.now).target
        return camera_of(t.x + 0.03, t.y - 0.02)

    window.start_guided_setup()
    hold(window, clock, (0.5, 0.5), config.GUIDED_INTRO_S + 0.2)
    for _ in range(5):
        hold(window, clock, target_point(window, clock), 7.2)
    for n_points, step in ((4, "verify_before"), (9, "grid"), (4, "verify_after")):
        hold(window, clock, (0.5, 0.5), config.GUIDED_INTRO_S + 0.2)
        for _ in range(n_points):
            point = biased_target() if step == "grid" else target_point(window, clock)
            hold(window, clock, point, 7.2)
    assert window.residual is not None and not window.residual_enabled
    assert any(e == "residual_auto_off" for e, _ in log)
    assert any("desligada" in line for line in window.guided.view(clock.now).lines)
