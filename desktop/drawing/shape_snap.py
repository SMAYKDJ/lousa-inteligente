"""Traço do Pincel que parece uma forma vira a forma perfeita (D033).

Inspirado no reconhecedor "$1" (Wobbrock, Wilson e Li, UIST 2007) e nas suas
variantes que devolvem o círculo ou o retângulo que melhor se ajusta ao traço.
Em vez de comparar com modelos desenhados, aqui cada candidato é **ajustado
geometricamente** e medido pelo erro médio, em pixels da lousa, relativo ao
tamanho da forma:

- **linha reta:** traço aberto cujos pontos ficam perto da corda entre o início e o fim;
- **círculo:** traço fechado cujos pontos ficam a uma distância quase constante do centro;
- **retângulo:** traço fechado cujos pontos ficam perto das bordas da caixa que o contém
  e que passa perto dos quatro cantos (alinhado à tela, como a ferramenta Retângulo).

Rabiscos, letras e formas tortas demais continuam como traço livre. Puro (sem Qt).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from desktop import config
from desktop.drawing.board import Ellipse, Point, Rectangle, Stroke


@dataclass(frozen=True)
class Snap:
    kind: str  # "line", "circle" ou "rectangle"
    item: object
    error: float  # erro médio ÷ tamanho da forma


def _px(points, size):
    w, h = size
    return [(x * w, y * h) for x, y in points]


def _length(pts) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _line(pts) -> float | None:
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    chord = math.hypot(x1 - x0, y1 - y0)
    if chord < 1e-6:
        return None
    dev = [abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / chord for x, y in pts]
    if _length(pts) > chord * config.SNAP_LINE_MAX_DETOUR:
        return None  # vai e volta (rabisco), mesmo que em cima da reta
    return (sum(dev) / len(dev)) / chord


def _circle(pts) -> tuple[float, float, float, float] | None:
    """Ajuste algébrico (Kåsa) de círculo: (cx, cy, r, erro relativo)."""
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    u = [(x - mx, y - my) for x, y in pts]
    suu = sum(a * a for a, _ in u)
    svv = sum(b * b for _, b in u)
    suv = sum(a * b for a, b in u)
    suuu = sum(a ** 3 for a, _ in u)
    svvv = sum(b ** 3 for _, b in u)
    suvv = sum(a * b * b for a, b in u)
    svuu = sum(b * a * a for a, b in u)
    det = suu * svv - suv * suv
    if abs(det) < 1e-9:
        return None
    rhs1 = 0.5 * (suuu + suvv)
    rhs2 = 0.5 * (svvv + svuu)
    uc = (rhs1 * svv - rhs2 * suv) / det
    vc = (suu * rhs2 - suv * rhs1) / det
    cx, cy = uc + mx, vc + my
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    if r < 1e-6:
        return None
    err = sum(abs(math.hypot(x - cx, y - cy) - r) for x, y in pts) / n / r
    # O traço precisa dar a volta: ângulos cobertos em volta do centro.
    sectors = {int((math.atan2(y - cy, x - cx) + math.pi) / (2 * math.pi) * 12) % 12 for x, y in pts}
    if len(sectors) < 10:
        return None
    return cx, cy, r, err


def _rectangle(pts) -> tuple[float, float, float, float, float] | None:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w < 1e-6 or h < 1e-6:
        return None
    scale = math.hypot(w, h)
    err = sum(min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1)) for x, y in pts) / len(pts) / scale
    # Passa perto dos quatro cantos (um círculo não passa).
    reach = config.SNAP_RECT_CORNER * scale
    for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        if min(math.hypot(x - cx, y - cy) for x, y in pts) > reach:
            return None
    return x0, y0, x1, y1, err


def recognize(points: list[Point], size: tuple[float, float], color: str, width: float) -> Snap | None:
    """Forma reconhecida no traço (em surface_norm), ou None para manter o traço livre."""
    if len(points) < 6:
        return None
    pts = _px(points, size)
    length = _length(pts)
    min_size = config.SNAP_MIN_FRAC * min(size)
    if length < min_size:
        return None
    w, h = size
    gap = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    closed = gap <= config.SNAP_CLOSED_GAP * length

    if not closed:
        err = _line(pts)
        if err is not None and err <= config.SNAP_LINE_ERROR:
            item = Stroke((points[0], points[-1]), color, width)
            return Snap("line", item, err)
        return None

    candidates = []
    circ = _circle(pts)
    if circ is not None and circ[3] <= config.SNAP_CIRCLE_ERROR and 2 * circ[2] >= min_size:
        cx, cy, r, err = circ
        candidates.append(Snap("circle", Ellipse((cx / w, cy / h), ((cx + r) / w, cy / h), color, width), err))
    rect = _rectangle(pts)
    if rect is not None and rect[4] <= config.SNAP_RECT_ERROR:
        x0, y0, x1, y1, err = rect
        candidates.append(Snap("rectangle", Rectangle((x0 / w, y0 / h), (x1 / w, y1 / h), color, width), err))
    return min(candidates, key=lambda s: s.error) if candidates else None
