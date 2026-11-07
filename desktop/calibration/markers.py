"""Marcadores ArUco nos cantos da projeção para corrigir o movimento da câmera (D015).

Peças, cada uma testável isoladamente:
- MarkerLayout: onde cada marcador é desenhado na lousa (px e surface_norm);
- MarkerDetector: acha os marcadores numa imagem RGB (OpenCV, thread de visão);
- MotionCompensator: compara as observações com a do momento da calibração e
  converte um ponto da câmera "de agora" para a câmera "da calibração".

A calibração com o dedo (D014) é feita na câmera da referência. Com a
compensação, ela continua válida depois que o celular se move:

    camera_agora --T--> camera_ref --H_dedo--> surface_norm,
    T = H_marcadores_ref⁻¹ · H_marcadores_agora
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from desktop import config
from desktop.calibration.homography import Homography, SurfacePoint
from desktop.core.coordinate_mapper import CameraNormPoint

#: id do marcador em cada canto, na mesma ordem dos alvos da calibração.
MARKER_IDS = (0, 1, 2, 3)  # superior esquerdo, inferior esquerdo, inferior direito, superior direito

#: Observação: id → 4 cantos do marcador na câmera (ordem ArUco: SE, SD, ID, IE do marcador).
Observation = dict[int, list[CameraNormPoint]]


@dataclass(frozen=True)
class MarkerRect:
    marker_id: int
    x: float  # canto superior esquerdo do desenho preto do marcador, em px da lousa
    y: float
    size: float
    quiet: float  # margem branca em volta (necessária para a detecção)


@dataclass(frozen=True)
class MarkerLayout:
    width: float
    height: float
    rects: tuple[MarkerRect, ...]

    @classmethod
    def for_screen(cls, width: float, height: float,
                   size_frac: float = config.MARKER_SIZE_FRAC) -> "MarkerLayout":
        size = size_frac * min(width, height)
        quiet = size * config.MARKER_QUIET_FRAC
        pad = config.MARKER_EDGE_PAD_FRAC * min(width, height)
        near, far_x, far_y = pad + quiet, width - pad - quiet - size, height - pad - quiet - size
        positions = [(near, near), (near, far_y), (far_x, far_y), (far_x, near)]
        return cls(width, height, tuple(
            MarkerRect(i, x, y, size, quiet) for i, (x, y) in zip(MARKER_IDS, positions)))

    def surface_corners(self, marker_id: int) -> list[SurfacePoint]:
        """Cantos do marcador em surface_norm, na ordem que o ArUco devolve."""
        r = self.rects[MARKER_IDS.index(marker_id)]
        px = [(r.x, r.y), (r.x + r.size, r.y), (r.x + r.size, r.y + r.size), (r.x, r.y + r.size)]
        return [SurfacePoint(x / self.width, y / self.height) for x, y in px]


class MarkerDetector:
    """ArUco DICT_4X4_50. Criar e usar na mesma thread (a de visão)."""

    def __init__(self) -> None:
        import cv2

        self._cv2 = cv2
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        # Cantos com precisão abaixo do pixel: os marcadores ficam pequenos na
        # câmera (~19 px no teste real), e cada pixel conta.
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(dictionary, params)

    def detect(self, rgb: Any) -> Observation:
        gray = self._cv2.cvtColor(rgb, self._cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return {}
        h, w = gray.shape[:2]
        found: Observation = {}
        for marker_corners, marker_id in zip(corners, ids.flatten()):
            if int(marker_id) in MARKER_IDS:
                found[int(marker_id)] = [CameraNormPoint(float(x) / w, float(y) / h)
                                         for x, y in marker_corners[0]]
        return found


def marker_image(marker_id: int, size_px: int) -> np.ndarray:
    """Imagem (cinza, uint8) do marcador, para desenhar na lousa."""
    import cv2

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.generateImageMarker(dictionary, marker_id, size_px)


#: Pares de marcadores em cantos opostos (SE–ID e IE–SD).
_DIAGONALS = ({0, 2}, {1, 3})


def usable(ids, min_markers: int = config.MARKER_MIN_VISIBLE) -> bool:
    """Marcadores suficientes e bem espalhados para definir a perspectiva."""
    ids = set(ids)
    if len(ids) < min_markers:
        return False
    return len(ids) >= 3 or ids in _DIAGONALS


def homography_from_markers(observation: Observation, layout: MarkerLayout,
                            min_markers: int = config.MARKER_MIN_VISIBLE) -> Homography | None:
    """camera_norm → surface_norm usando todos os cantos de marcadores visíveis."""
    ids = [i for i in MARKER_IDS if i in observation]
    if not usable(ids, min_markers):
        return None
    import cv2

    src = np.array([(p.x, p.y) for i in ids for p in observation[i]], dtype=np.float64)
    dst = np.array([(p.x, p.y) for i in ids for p in layout.surface_corners(i)], dtype=np.float64)
    matrix, _ = cv2.findHomography(src, dst, 0)
    if matrix is None or not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-12:
        return None
    return Homography(matrix)


_SURFACE_CORNERS = np.array([[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64).T


def _project(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    out = matrix @ points
    return out[:2] / out[2]


class MotionCompensator:
    """Mantém T: camera_agora → camera_ref, a partir dos marcadores."""

    def __init__(self, layout: MarkerLayout) -> None:
        self.layout = layout
        self.reference: Homography | None = None
        self.transform = np.eye(3)
        self.shift = 0.0  # deslocamento da câmera desde a referência (camera_norm)
        self._smoothed: Observation = {}
        self._current_corners: np.ndarray | None = None  # superfície vista na câmera, agora
        self._pending: list[tuple[np.ndarray, np.ndarray]] = []  # saltos aguardando confirmação

    @property
    def has_reference(self) -> bool:
        return self.reference is not None

    def _smooth(self, observation: Observation) -> Observation:
        """Média móvel por canto, para o cursor não tremer com o ruído da detecção.

        Um salto grande (câmera movida) substitui a média na hora.
        """
        alpha, jump = config.MARKER_SMOOTHING, config.MARKER_JUMP
        for marker_id, corners in observation.items():
            old = self._smoothed.get(marker_id)
            if old is None or max(max(abs(a.x - b.x), abs(a.y - b.y))
                                  for a, b in zip(old, corners)) > jump:
                self._smoothed[marker_id] = list(corners)
            else:
                self._smoothed[marker_id] = [
                    CameraNormPoint(o.x + alpha * (c.x - o.x), o.y + alpha * (c.y - o.y))
                    for o, c in zip(old, corners)]
        return {i: self._smoothed[i] for i in observation}

    def set_reference(self, observation: Observation,
                      min_markers: int = config.MARKER_REFERENCE_MIN_VISIBLE) -> bool:
        if len(observation) < min_markers:
            return False
        self._smoothed = {}
        homography = homography_from_markers(self._smooth(observation), self.layout)
        if homography is None:
            return False
        self.reference, self.transform, self.shift = homography, np.eye(3), 0.0
        self._current_corners = _project(np.linalg.inv(homography.matrix), _SURFACE_CORNERS)
        self._pending = []
        return True

    @property
    def settled(self) -> bool:
        """Sem salto aguardando confirmação (a câmera não está no meio de um movimento)."""
        return not self._pending

    @property
    def surface_quad(self) -> list[tuple[float, float]] | None:
        """Cantos da lousa na câmera agora (camera_norm), ou None sem referência."""
        if self._current_corners is None:
            return None
        return [(float(x), float(y)) for x, y in self._current_corners.T]

    def clear(self) -> None:
        self.reference, self.transform, self.shift = None, np.eye(3), 0.0
        self._smoothed, self._current_corners, self._pending = {}, None, []

    def update(self, observation: Observation) -> bool:
        """Atualiza T. False quando a leitura não é usada (mantém a correção anterior).

        Leituras próximas da atual entram direto (ajuste fino). Um salto só é
        aceito depois de várias leituras seguidas que concordam entre si: assim
        uma leitura ruim (marcadores parcialmente vistos) não faz o cursor pular.
        """
        if self.reference is None:
            return False
        current = homography_from_markers(self._smooth(observation), self.layout)
        if current is None:
            return False
        corners = _project(np.linalg.inv(current.matrix), _SURFACE_CORNERS)
        if float(np.max(np.abs(corners - self._current_corners))) > config.MARKER_STABLE_DELTA:
            if self._pending and float(np.max(np.abs(corners - self._pending[-1][1]))) \
                    > config.MARKER_STABLE_DELTA:
                self._pending = []  # leituras discordantes: recomeça a confirmação
            self._pending.append((current.matrix, corners))
            if len(self._pending) < config.MARKER_JUMP_CONFIRMATIONS:
                return False
        self._pending = []
        self._current_corners = corners
        self.transform = np.linalg.inv(self.reference.matrix) @ current.matrix
        ref = _project(np.linalg.inv(self.reference.matrix), _SURFACE_CORNERS)
        self.shift = float(np.max(np.abs(ref - corners)))
        return True

    def to_reference(self, point: CameraNormPoint) -> CameraNormPoint | None:
        x, y, w = self.transform @ np.array([point.x, point.y, 1.0])
        if abs(w) < 1e-12:
            return None
        return CameraNormPoint(float(x / w), float(y / w))


class CompensatedMapper:
    """Calibração do dedo + correção do movimento da câmera (substitui o HomographyMapper)."""

    def __init__(self, finger: Homography, compensator: MotionCompensator) -> None:
        self.finger = finger
        self.compensator = compensator

    @property
    def homography(self) -> Homography:
        """Homografia efetiva camera_agora → surface (para o diagnóstico e o teste G)."""
        return Homography(self.finger.matrix @ self.compensator.transform)

    def map(self, point: CameraNormPoint, ui):
        from desktop.core.coordinate_mapper import UiPoint

        surface = self.homography.to_surface(point)
        if surface is None or not surface.inside:
            return None
        return UiPoint(surface.x * ui.width, surface.y * ui.height)
