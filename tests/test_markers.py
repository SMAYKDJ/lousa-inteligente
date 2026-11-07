"""Marcadores ArUco e correção do movimento da câmera (D015), com câmera sintética.

A "lousa" é desenhada como na janela (mesmo layout), e a "câmera" a vê em
perspectiva (warpPerspective). Depois a câmera "se move" e o ponto deve
continuar indo para o mesmo lugar da superfície. É simulação: imagem real
tem ruído, reflexo e desfoque (CLAUDE.md §9.4).
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from desktop.calibration.homography import Homography, SurfacePoint  # noqa: E402
from desktop.calibration.markers import (  # noqa: E402
    MARKER_IDS, CompensatedMapper, MarkerDetector, MarkerLayout, MotionCompensator,
    homography_from_markers, marker_image)
from desktop.core.coordinate_mapper import CameraNormPoint, UiSize  # noqa: E402

W, H = 1920, 1080
CAM_W, CAM_H = 640, 360  # celular na horizontal


def board(layout: MarkerLayout) -> np.ndarray:
    img = np.zeros((H, W), np.uint8)
    for r in layout.rects:
        q = int(round(r.quiet))
        x, y, s = int(round(r.x)), int(round(r.y)), int(round(r.size))
        img[y - q:y + s + q, x - q:x + s + q] = 255
        img[y:y + s, x:x + s] = marker_image(r.marker_id, s)
    return img


def camera_matrix(quad) -> np.ndarray:
    """Lousa (px) → câmera (px): os 4 cantos da lousa caem em `quad`."""
    return cv2.getPerspectiveTransform(np.float32([(0, 0), (W, 0), (W, H), (0, H)]),
                                       np.float32(quad))


def shoot(scene: np.ndarray, P: np.ndarray) -> np.ndarray:
    gray = cv2.warpPerspective(scene, P, (CAM_W, CAM_H))
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def camera_of(P: np.ndarray, s: SurfacePoint) -> CameraNormPoint:
    x, y, w = P @ np.array([s.x * W, s.y * H, 1.0])
    return CameraNormPoint(x / w / CAM_W, y / w / CAM_H)


def finger_homography(P: np.ndarray) -> Homography:
    """A calibração com o dedo "perfeita" para a câmera P (camera_norm → surface_norm)."""
    to_board = np.linalg.inv(P) @ np.diag([CAM_W, CAM_H, 1.0])
    return Homography(np.diag([1 / W, 1 / H, 1.0]) @ to_board)


QUAD_REF = [(70, 40), (580, 55), (565, 320), (60, 300)]
QUAD_MOVED = [(110, 70), (600, 60), (610, 335), (95, 330)]  # celular deslocado e girado


@pytest.fixture(scope="module")
def layout():
    return MarkerLayout.for_screen(W, H)


@pytest.fixture(scope="module")
def detector():
    return MarkerDetector()


def test_layout_keeps_markers_inside_screen_in_corners(layout):
    assert [r.marker_id for r in layout.rects] == list(MARKER_IDS)
    for r in layout.rects:
        assert r.x - r.quiet >= 0 and r.y - r.quiet >= 0
        assert r.x + r.size + r.quiet <= W and r.y + r.size + r.quiet <= H
    se = layout.surface_corners(0)[0]
    assert se.x < 0.1 and se.y < 0.2


def test_detects_all_four_markers(layout, detector):
    obs = detector.detect(shoot(board(layout), camera_matrix(QUAD_REF)))
    assert sorted(obs) == [0, 1, 2, 3]


def test_marker_homography_matches_true_geometry(layout, detector):
    P = camera_matrix(QUAD_REF)
    h = homography_from_markers(detector.detect(shoot(board(layout), P)), layout)
    for s in (SurfacePoint(0.5, 0.5), SurfacePoint(0.2, 0.8), SurfacePoint(0.9, 0.1)):
        out = h.to_surface(camera_of(P, s))
        assert abs(out.x - s.x) < 0.01 and abs(out.y - s.y) < 0.01


def test_cursor_returns_to_place_after_camera_moves(layout, detector):
    scene = board(layout)
    P_ref, P_moved = camera_matrix(QUAD_REF), camera_matrix(QUAD_MOVED)
    comp = MotionCompensator(layout)
    assert comp.set_reference(detector.detect(shoot(scene, P_ref)))
    mapper = CompensatedMapper(finger_homography(P_ref), comp)
    target = SurfacePoint(0.3, 0.6)

    # Sem correção, a câmera movida erra muito:
    stale = finger_homography(P_ref).to_surface(camera_of(P_moved, target))
    assert abs(stale.x - target.x) + abs(stale.y - target.y) > 0.05

    moved = detector.detect(shoot(scene, P_moved))
    # Um salto só vale depois de 3 leituras que concordam (evita pulos por leitura ruim).
    assert not comp.update(moved) and not comp.update(moved)
    assert comp.update(moved)
    assert comp.shift > 0.03
    ui = mapper.map(camera_of(P_moved, target), UiSize(W, H))
    assert abs(ui.x - target.x * W) < 0.01 * W and abs(ui.y - target.y * H) < 0.01 * H


def test_hand_covering_two_markers_still_corrects(layout, detector):
    scene = board(layout)
    comp = MotionCompensator(layout)
    comp.set_reference(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    obs = detector.detect(shoot(scene, camera_matrix(QUAD_MOVED)))
    covered = {i: c for i, c in obs.items() if i in (0, 2)}  # só 2 visíveis, em diagonal
    for _ in range(3):
        accepted = comp.update(covered)
    assert accepted
    mapper = CompensatedMapper(finger_homography(camera_matrix(QUAD_REF)), comp)
    target = SurfacePoint(0.5, 0.5)
    out = mapper.homography.to_surface(camera_of(camera_matrix(QUAD_MOVED), target))
    assert abs(out.x - 0.5) < 0.02 and abs(out.y - 0.5) < 0.02


def test_one_marker_is_not_enough_keeps_last_correction(layout, detector):
    scene = board(layout)
    comp = MotionCompensator(layout)
    comp.set_reference(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    before = comp.transform.copy()
    obs = detector.detect(shoot(scene, camera_matrix(QUAD_MOVED)))
    assert not comp.update({0: obs[0]})
    assert np.allclose(comp.transform, before)


def test_still_camera_means_identity(layout, detector):
    scene = board(layout)
    comp = MotionCompensator(layout)
    comp.set_reference(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    comp.update(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    assert comp.shift < 0.002
    assert np.allclose(comp.transform / comp.transform[2, 2], np.eye(3), atol=0.01)


def test_no_reference_without_markers(layout):
    comp = MotionCompensator(layout)
    assert not comp.set_reference({}) and not comp.has_reference
    assert not comp.update({})


def test_two_markers_on_same_side_are_not_used(layout, detector):
    scene = board(layout)
    comp = MotionCompensator(layout)
    comp.set_reference(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    obs = detector.detect(shoot(scene, camera_matrix(QUAD_MOVED)))
    left_side = {i: obs[i] for i in (0, 1)}
    for _ in range(5):
        assert not comp.update(left_side)
    assert comp.shift == 0.0


def test_reference_needs_three_markers(layout, detector):
    obs = detector.detect(shoot(board(layout), camera_matrix(QUAD_REF)))
    comp = MotionCompensator(layout)
    assert not comp.set_reference({i: obs[i] for i in (1, 3)})
    assert comp.set_reference({i: obs[i] for i in (0, 1, 3)})


def test_single_bad_reading_does_not_move_cursor(layout, detector):
    scene = board(layout)
    comp = MotionCompensator(layout)
    comp.set_reference(detector.detect(shoot(scene, camera_matrix(QUAD_REF))))
    still = detector.detect(shoot(scene, camera_matrix(QUAD_REF)))
    moved = detector.detect(shoot(scene, camera_matrix(QUAD_MOVED)))
    for reading in (still, moved, still, moved, still):  # leituras alternando
        comp.update(reading)
    assert comp.shift < 0.005
