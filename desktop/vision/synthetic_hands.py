"""Mãos sintéticas em 3D, em qualquer pose, para testes sem câmera (D022).

Adaptado de open-source-hands (Meticulai), licença MIT, © 2026 abouchedidxcode,
src/kit/synthetic.ts (commit dd79fb7). Parametrizadas pela dobra de cada dedo,
pinça, rotação no plano da imagem e abertura entre os dedos, com flexão máxima
por articulação. Mais realistas que as mãos de "dedo reto ou dobrado" dos
testes antigos.

Referencial local: palma para a câmera, x → direita, y → cima, z → longe da
câmera (convenção do MediaPipe), unidade = pulso→base do dedo médio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace

V3 = tuple[float, float, float]


@dataclass(frozen=True)
class HandPose:
    curl: tuple[float, float, float, float, float]  # polegar … mínimo, 0 reto … 1 dobrado
    pinch: float = 0.0  # 0..1: ponta do polegar levada até a ponta do indicador
    roll: float = 0.0  # rotação no plano da imagem (rad, anti-horário)
    spread: float = 1.0  # multiplica o afastamento de cada dedo em relação ao médio


POSES = {
    "open": HandPose((0, 0, 0, 0, 0)),
    "relaxed": HandPose((0.2, 0.25, 0.3, 0.35, 0.4)),
    "fist": HandPose((1, 1, 1, 1, 1)),
    "point": HandPose((1, 0, 1, 1, 1)),
    "victory": HandPose((1, 0, 0, 1, 1), spread=3),
    "pinch": HandPose((0, 0.5, 0.35, 0.4, 0.45), pinch=1),
    "ok": HandPose((0, 0.5, 0, 0, 0), pinch=1),
    "claw": HandPose((0.4, 0.45, 0.45, 0.45, 0.45)),
    "thumbs-up": HandPose((0, 1, 1, 1, 1), roll=-math.pi / 2),
}

# Base de cada dedo (MCP), direção no plano (graus) e comprimento das falanges.
_FINGERS = (
    ((-0.24, 0.96, 0.0), 97, (0.48, 0.28, 0.22)),  # indicador
    ((0.0, 1.0, 0.0), 90, (0.52, 0.32, 0.24)),  # médio
    ((0.19, 0.95, 0.0), 84, (0.48, 0.30, 0.22)),  # anelar
    ((0.36, 0.84, 0.0), 76, (0.38, 0.22, 0.20)),  # mínimo
)
_FLEX = (75, 100, 70)  # flexão máxima (graus) por articulação com dobra = 1
_THUMB_OPEN = ((-0.22, 0.18, 0), (-0.48, 0.36, -0.02), (-0.71, 0.52, -0.03), (-0.91, 0.66, -0.04))
_THUMB_TUCK = ((-0.2, 0.18, -0.02), (-0.38, 0.45, -0.12), (-0.3, 0.72, -0.3), (-0.08, 0.86, -0.42))


def _lerp3(a, b, t) -> V3:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hand_shape(pose: HandPose) -> list[V3]:
    """21 pontos de uma mão DIREITA no referencial local."""
    out: list[V3] = [(0.0, 0.0, 0.0)] * 21
    for f, (mcp, d, seg) in enumerate(_FINGERS):
        direction = 90 + (d - 90) * pose.spread
        c = pose.curl[f + 1]
        if f == 0:
            c = max(c, 0.5 * pose.pinch)  # o indicador numa pinça dobra um pouco
        base = 5 + f * 4
        out[base] = mcp
        dx, dy = math.cos(math.radians(direction)), math.sin(math.radians(direction))
        p, phi = mcp, 0.0
        for s in range(3):
            phi += math.radians(_FLEX[s] * c)
            cs, sn = math.cos(phi), math.sin(phi)
            p = (p[0] + seg[s] * dx * cs, p[1] + seg[s] * dy * cs, p[2] - seg[s] * sn)  # dobra para a câmera
            out[base + 1 + s] = p
    for i in range(4):
        out[1 + i] = _lerp3(_THUMB_OPEN[i], _THUMB_TUCK[i], pose.curl[0])
    if pose.pinch > 0:
        it = out[8]
        target = (it[0] - 0.07, it[1] - 0.06, it[2] + 0.02)
        tip = out[4]
        delta = tuple(target[i] - tip[i] for i in range(3))
        for i, w in enumerate((0.15, 0.4, 0.7, 1.0)):  # base do polegar quase parada, ponta inteira
            k = w * pose.pinch
            q = out[1 + i]
            out[1 + i] = tuple(q[j] + delta[j] * k for j in range(3))
    if pose.roll:
        c, s = math.cos(pose.roll), math.sin(pose.roll)
        out = [(x * c - y * s, x * s + y * c, z) for x, y, z in out]
    return out


def synthetic_hand(x: float, y: float, pose: HandPose, scale: float = 0.2,
                   aspect: float = 16 / 9, left: bool = False):
    """(pontos da imagem, pontos do mundo) com o centro da palma em (x, y) de camera_norm.

    Imagem: y para baixo, como no MediaPipe. Mundo: metros (~9 cm do pulso à base do médio).
    """
    shape = hand_shape(pose)
    sx = -1 if left else 1
    palm = (0, 5, 9, 13, 17)
    cx = sum(shape[i][0] for i in palm) / 5
    cy = sum(shape[i][1] for i in palm) / 5
    image = [(x + sx * (lx - cx) * scale / aspect, y - (ly - cy) * scale, lz * scale) for lx, ly, lz in shape]
    world = [(sx * lx * 0.09, -ly * 0.09, lz * 0.09) for lx, ly, lz in shape]
    return image, world


def as_landmarks(points) -> list:
    """Pontos → objetos com .x .y .z, como os do MediaPipe."""
    return [SimpleNamespace(x=p[0], y=p[1], z=p[2]) for p in points]
