"""Homografia entre a imagem da câmera e a superfície projetada (Fase 2, D014).

Converte `camera_norm` (x, y ∈ [0, 1] sobre o quadro da câmera) em
`surface_norm` (x, y ∈ [0, 1] sobre a área projetada). As duas são
coordenadas distintas e só se convertem aqui, de forma explícita (CLAUDE.md §5.2).

A homografia é exata para pontos NO PLANO da superfície. Com o dedo afastado
da lousa há erro de paralaxe (docs/calibration.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from desktop.core.coordinate_mapper import CameraNormPoint


@dataclass(frozen=True)
class SurfacePoint:
    """Ponto na área projetada, normalizado: (0, 0) canto superior esquerdo, (1, 1) inferior direito."""

    x: float
    y: float

    @property
    def inside(self) -> bool:
        return 0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0


class CalibrationError(ValueError):
    """Pontos de calibração que não formam uma homografia confiável."""


#: Área mínima do quadrilátero na câmera (fração da imagem). Menor que isso,
#: os pontos estão praticamente juntos e a homografia amplificaria o ruído.
MIN_CAMERA_AREA = 0.01


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, list(points[1:]) + [points[0]]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _check_quad(points: Sequence[tuple[float, float]], name: str, min_area: float) -> None:
    if len(points) != 4:
        raise CalibrationError(f"{name}: são necessários 4 pontos (recebidos {len(points)})")
    for i in range(4):
        for j in range(i + 1, 4):
            if np.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]) < 1e-6:
                raise CalibrationError(f"{name}: pontos {i + 1} e {j + 1} são iguais")
    # Convexo e na mesma ordem: produto vetorial com o mesmo sinal em todos os vértices.
    signs = []
    for i in range(4):
        (ax, ay), (bx, by), (cx, cy) = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
        signs.append((bx - ax) * (cy - by) - (by - ay) * (cx - bx))
    if not (all(s > 0 for s in signs) or all(s < 0 for s in signs)):
        raise CalibrationError(
            f"{name}: os pontos não formam um quadrilátero convexo na ordem esperada "
            "(algum canto foi marcado no lugar errado?)")
    if abs(_polygon_area(points)) < min_area:
        raise CalibrationError(f"{name}: os pontos estão próximos demais entre si")


class Homography:
    """camera_norm → surface_norm, calculada a partir de 4 pares de pontos."""

    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = matrix

    @classmethod
    def from_points(cls, camera: Sequence[CameraNormPoint],
                    surface: Sequence[SurfacePoint]) -> "Homography":
        cam = [(p.x, p.y) for p in camera]
        srf = [(p.x, p.y) for p in surface]
        _check_quad(cam, "Câmera", MIN_CAMERA_AREA)
        _check_quad(srf, "Superfície", 1e-6)
        # Uma câmera real pode ver a superfície girada, nunca espelhada:
        # a ordem dos cantos (horário/anti-horário) tem de ser a mesma.
        if (_polygon_area(cam) > 0) != (_polygon_area(srf) > 0):
            raise CalibrationError(
                "Câmera: os cantos foram marcados em ordem espelhada (algum canto trocado?)")
        import cv2

        matrix = cv2.getPerspectiveTransform(np.array(cam, dtype=np.float32),
                                             np.array(srf, dtype=np.float32))
        if not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-12:
            raise CalibrationError("homografia degenerada")
        return cls(matrix.astype(np.float64))

    def to_surface(self, point: CameraNormPoint) -> SurfacePoint | None:
        """Converte um ponto da câmera. None se cair "atrás" do plano (w ≤ 0)."""
        x, y, w = self.matrix @ np.array([point.x, point.y, 1.0])
        if w <= 1e-12:
            return None
        return SurfacePoint(float(x / w), float(y / w))

    def as_list(self) -> list[list[float]]:
        return [[round(float(v), 8) for v in row] for row in self.matrix]


class HomographyMapper:
    """camera_norm → surface_norm → ui_px, com a calibração (substitui o StretchMapper).

    Devolve None quando o dedo está fora da área projetada: não está "na lousa".
    """

    def __init__(self, homography: Homography) -> None:
        self.homography = homography

    def map(self, point: CameraNormPoint, ui: "UiSize") -> "UiPoint | None":
        from desktop.core.coordinate_mapper import UiPoint

        surface = self.homography.to_surface(point)
        if surface is None or not surface.inside:
            return None
        return UiPoint(surface.x * ui.width, surface.y * ui.height)
