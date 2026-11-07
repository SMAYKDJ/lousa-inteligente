"""Palma ou dorso virado para a câmera (D036).

Com a mão em pé, o produto vetorial (pulso→base do indicador) × (pulso→base do
mindinho), na imagem (y para baixo), é negativo para a mão **direita mostrando
a palma** e positivo mostrando o dorso; na esquerda, o contrário. Como a conta
depende de qual mão é, usa-se o nome que o MediaPipe dá, que supõe imagem
espelhada (selfie): com a câmera traseira do celular (sem espelho), "Left" é a
mão direita de verdade.

É uma estimativa para diagnóstico na janela da câmera; não decide nada na lousa.
"""

from __future__ import annotations

from typing import Sequence

from desktop import config

WRIST, INDEX_MCP, PINKY_MCP = 0, 5, 17


def true_hand(label: str | None, mirrored: bool = config.CAMERA_MIRRORED) -> str | None:
    """"direita"/"esquerda" de verdade a partir do nome do MediaPipe."""
    if label not in ("Left", "Right"):
        return None
    right = (label == "Right") if mirrored else (label == "Left")
    return "direita" if right else "esquerda"


def hand_side(points: Sequence, label: str | None, width: int, height: int,
              mirrored: bool = config.CAMERA_MIRRORED) -> str | None:
    """"palma", "dorso", "de lado" ou None (sem pontos ou sem saber qual mão é)."""
    if not points or len(points) <= PINKY_MCP:
        return None
    hand = true_hand(label, mirrored)
    if hand is None:
        return None
    w, i, p = points[WRIST], points[INDEX_MCP], points[PINKY_MCP]
    ax, ay = (i.x - w.x) * width, (i.y - w.y) * height
    bx, by = (p.x - w.x) * width, (p.y - w.y) * height
    cross = ax * by - ay * bx
    scale = max(ax * ax + ay * ay, bx * bx + by * by, 1e-9)
    if abs(cross) / scale < config.HAND_SIDE_EDGE:
        return "de lado"
    palm_if_negative = hand == "direita"
    return "palma" if (cross < 0) == palm_if_negative else "dorso"
