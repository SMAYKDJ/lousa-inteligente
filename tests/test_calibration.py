"""Testes da calibração (Fase 2, D014): homografia, coleta do ponto e máquina de estados."""

import math

import numpy as np
import pytest

from desktop.calibration.calibration_state import (
    VERIFY_TARGET,
    CalibrationSession,
    Phase,
    corner_targets,
)
from desktop.calibration.homography import CalibrationError, Homography, SurfacePoint
from desktop.calibration.point_capture import PointCollector, RejectReason
from desktop.core.coordinate_mapper import CameraNormPoint as C

# Uma "câmera" de lado: a projeção aparece como trapézio na imagem.
TRUE_H = np.array([[0.9, 0.15, 0.1], [0.05, 1.1, 0.12], [0.3, 0.2, 1.0]])


def camera_of(surface: SurfacePoint) -> C:
    """Onde um ponto da superfície aparece na câmera (inversa da homografia verdadeira)."""
    inv = np.linalg.inv(TRUE_H)
    x, y, w = inv @ np.array([surface.x, surface.y, 1.0])
    return C(x / w, y / w)


# --- homografia ------------------------------------------------------------------

def test_homography_round_trip_on_whole_surface():
    targets = corner_targets()
    h = Homography.from_points([camera_of(t) for t in targets], targets)
    for sx, sy in [(0.5, 0.5), (0.0, 0.0), (1.0, 1.0), (0.2, 0.8), (0.95, 0.05)]:
        out = h.to_surface(camera_of(SurfacePoint(sx, sy)))
        assert out.x == pytest.approx(sx, abs=1e-5) and out.y == pytest.approx(sy, abs=1e-5)


def test_outside_projection_is_flagged():
    targets = corner_targets()
    h = Homography.from_points([camera_of(t) for t in targets], targets)
    assert h.to_surface(camera_of(SurfacePoint(1.2, 0.5))).inside is False
    assert h.to_surface(camera_of(SurfacePoint(0.5, 0.5))).inside is True


@pytest.mark.parametrize("camera, fragment", [
    ([C(0.1, 0.1), C(0.1, 0.1), C(0.9, 0.9), C(0.9, 0.1)], "iguais"),
    # ordem trocada: SE, ID, IE, SD → quadrilátero cruzado
    ([C(0.1, 0.1), C(0.9, 0.9), C(0.1, 0.9), C(0.9, 0.1)], "convexo"),
    ([C(0.5, 0.5), C(0.5, 0.52), C(0.52, 0.52), C(0.52, 0.5)], "próximos"),
    ([C(0.1, 0.1), C(0.1, 0.9)], "4 pontos"),
])
def test_invalid_corners_are_rejected(camera, fragment):
    targets = corner_targets()[: len(camera)] if len(camera) < 4 else corner_targets()
    with pytest.raises(CalibrationError) as info:
        Homography.from_points(camera, targets)
    assert fragment in str(info.value)


# --- coleta do ponto ------------------------------------------------------------

def collector():
    return PointCollector(min_presence=0.7, max_spread=0.015)


def test_capture_uses_median_and_ignores_one_bad_frame():
    c = collector()
    for x in (0.300, 0.302, 0.301, 0.299, 0.300, 0.301, 0.300, 0.300, 0.298, 0.302, 0.9):
        c.add(C(x, 0.5))
    result = c.result()
    assert result.accepted and result.point.x == pytest.approx(0.300, abs=1e-3)


def test_capture_rejects_missing_hand():
    c = collector()
    for i in range(10):
        c.add(C(0.3, 0.3) if i < 6 else None)
    assert c.result().reason is RejectReason.HAND_NOT_SEEN


def test_capture_rejects_moving_finger():
    c = collector()
    for i in range(10):
        c.add(C(0.3 + i * 0.01, 0.3))
    assert c.result().reason is RejectReason.FINGER_MOVING


def test_capture_without_frames():
    assert collector().result().reason is RejectReason.NO_FRAMES


# --- máquina de estados ----------------------------------------------------------

class Run:
    """Simula o professor: segura o dedo no alvo indicado, quadro a quadro, a 25 q/s."""

    def __init__(self, session: CalibrationSession) -> None:
        self.s = session
        self.now = 0.0
        self.events = []

    def hold(self, tip, seconds):
        for _ in range(int(seconds * 25)):
            self.now += 0.04
            self.s.on_tip(tip, self.now)
            self.events += self.s.tick(self.now)

    def hold_on_current_target(self):
        view = self.s.view(self.now)
        self.hold(camera_of(view.target), self.s.countdown_s + 0.1)


def new_run(countdown=7.0):
    session = CalibrationSession(countdown_s=countdown)
    run = Run(session)
    run.events += session.start(run.now)
    return run


def test_full_calibration_in_user_order():
    run = new_run()
    names = []
    for _ in range(4):
        names.append(run.s.view(run.now).target_name)
        run.hold_on_current_target()
    assert names == ["superior esquerdo", "inferior esquerdo", "inferior direito", "superior direito"]
    assert run.s.phase is Phase.VERIFY
    assert run.s.view(run.now).target == VERIFY_TARGET
    run.hold_on_current_target()
    assert run.s.phase is Phase.DONE
    dx, dy = run.s.result.verify_error
    assert abs(dx) < 1e-3 and abs(dy) < 1e-3
    done = [e for e in run.events if e["event"] == "calibration_done"][0]
    assert done["rejections"] == 0 and len(done["camera_points"]) == 4
    assert done["duration_s"] == pytest.approx(5 * 7, abs=1)


def test_countdown_is_seven_seconds_by_default():
    assert CalibrationSession().countdown_s == 7.0


def test_no_capture_before_countdown_ends():
    run = new_run()
    run.hold(camera_of(run.s.view(0).target), 6.0)
    assert run.s.view(run.now).step == 1
    assert run.s.view(run.now).remaining_s == pytest.approx(1.0, abs=0.05)


def test_hand_away_repeats_same_corner_with_message():
    run = new_run()
    run.hold(None, 7.1)
    view = run.s.view(run.now)
    assert view.step == 1 and "Não vi o dedo" in view.message
    rejected = [e for e in run.events if e["event"] == "calibration_point"][0]
    assert rejected["accepted"] is False and rejected["reason"] == "hand_not_seen"
    run.hold_on_current_target()
    assert run.s.view(run.now).step == 2 and run.s.view(run.now).message == ""


def test_finger_only_needs_to_be_still_at_the_end():
    run = new_run()
    target = camera_of(run.s.view(0).target)
    run.hold(C(0.9, 0.9), 3.0)  # chegando ao alvo, longe
    run.hold(target, 4.2)  # parado nos últimos segundos
    assert run.s.view(run.now).step == 2


def test_wrong_corner_order_restarts_from_first():
    run = new_run()
    targets = corner_targets()
    swapped = [targets[0], targets[2], targets[1], targets[3]]  # cruzado
    for t in swapped:
        run.hold(camera_of(t), 7.1)
    view = run.s.view(run.now)
    assert run.s.phase is Phase.CORNERS and view.step == 1
    assert "recomeçar" in view.message
    assert any(e["event"] == "calibration_invalid" for e in run.events)


def test_cancel_and_restart():
    run = new_run()
    run.hold_on_current_target()
    assert run.s.cancel()[0]["event"] == "calibration_cancel"
    assert run.s.phase is Phase.CANCELLED and not run.s.active
    run.s.start(run.now)
    assert run.s.view(run.now).step == 1 and run.s.view(run.now).captured == ()


def test_view_reports_finger_seen_and_progress():
    run = new_run()
    run.hold(C(0.5, 0.5), 3.5)
    view = run.s.view(run.now)
    assert view.finger_seen and view.progress == pytest.approx(0.5, abs=0.02)
    assert not view.collecting
    run.hold(None, 0.5)
    assert not run.s.view(run.now).finger_seen


def test_verify_error_reflects_offset():
    run = new_run()
    for _ in range(4):
        run.hold_on_current_target()
    # Professor encosta 2% à direita do alvo central.
    run.hold(camera_of(SurfacePoint(0.52, 0.5)), 7.1)
    dx, dy = run.s.result.verify_error
    assert dx == pytest.approx(0.02, abs=1e-3) and abs(dy) < 1e-3
    assert not math.isnan(dx)


def test_mirrored_corner_order_is_rejected():
    targets = corner_targets()
    mirrored = [camera_of(SurfacePoint(1 - t.x, t.y)) for t in targets]  # esquerda ↔ direita
    with pytest.raises(CalibrationError) as info:
        Homography.from_points(mirrored, targets)
    assert "espelhada" in str(info.value)


def test_bad_verification_restarts_instead_of_accepting():
    # Reproduz o 1º teste real (2026-11-06 18:09): cantos aceitos, mas o
    # alvo central caiu a mais de 50% de distância. Não pode virar "calibrada".
    run = new_run()
    for _ in range(4):
        run.hold_on_current_target()
    run.hold(camera_of(SurfacePoint(0.9, 0.9)), 7.1)
    assert run.s.phase is Phase.CORNERS and run.s.view(run.now).step == 1
    assert "verificação errou" in run.s.view(run.now).message
    failed = [e for e in run.events if e["event"] == "calibration_verify_failed"]
    assert len(failed) == 1 and len(failed[0]["camera_points"]) == 4
    assert run.s.result is None


def test_small_verification_error_is_accepted():
    run = new_run()
    for _ in range(4):
        run.hold_on_current_target()
    run.hold(camera_of(SurfacePoint(0.53, 0.5)), 7.1)  # 3% < 5%
    assert run.s.phase is Phase.DONE


# --- teste de precisão (grade de 9 pontos) ---------------------------------------

from desktop.calibration.accuracy_test import AccuracyTest, grid_targets  # noqa: E402


def calibrated_homography():
    targets = corner_targets()
    return Homography.from_points([camera_of(t) for t in targets], targets)


def test_grid_has_nine_points_in_reading_order():
    grid = grid_targets()
    assert len(grid) == 9
    assert (grid[0].x, grid[0].y) == (0.15, 0.15) and (grid[8].x, grid[8].y) == (0.85, 0.85)


def test_accuracy_test_measures_every_point():
    test = AccuracyTest(calibrated_homography(), countdown_s=7.0)
    run = Run(test)
    run.events += test.start(0.0)
    for i, target in enumerate(grid_targets()):
        offset = 0.01 if i == 4 else 0.0  # o ponto central com 1% de erro
        run.hold(camera_of(SurfacePoint(target.x + offset, target.y)), 7.1)
    assert test.phase is Phase.DONE
    report = test.summary.report(1920, 1080)
    assert len(report["errors_px"]) == 9
    assert report["max_px"] == pytest.approx(19.2, abs=0.5)  # 1% de 1920
    assert report["median_px"] < 1
    points = [e for e in run.events if e["event"] == "accuracy_point"]
    assert len(points) == 9 and all(p["accepted"] for p in points)


def test_accuracy_test_repeats_point_without_hand():
    test = AccuracyTest(calibrated_homography(), countdown_s=7.0)
    run = Run(test)
    test.start(0.0)
    run.hold(None, 7.1)
    assert test.view(run.now).step == 1 and "Não vi o dedo" in test.view(run.now).message
    assert "Teste de precisão — ponto 1 de 9" == test.view(run.now).title
