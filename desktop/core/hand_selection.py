"""Escolha da mão quando a câmera vê as duas (pedido do usuário, 2026-11-06).

Situação: o professor explica de lado para a lousa. A câmera vê os dois
braços, mas quem interage é a mão JUNTO À SUPERFÍCIE; o braço afastado da
lousa não deve mover o cursor.

Regra:
1. Prefere a mão cuja ponta do indicador está sobre a área da lousa (ou mais
   perto dela), quando há calibração.
2. Empate (as duas sobre a lousa, ou sem calibração): prefere a mão que
   aparece MENOR. A câmera fica de frente para a lousa, então a mão encostada
   na superfície está mais longe da câmera; o braço afastado da lousa fica
   mais perto dela e parece maior. Com calibração, o tamanho é medido na
   superfície, o que desconta a perspectiva de cada região da lousa.
3. Estabilidade: só troca de mão quando a outra é claramente melhor
   (margens em config.py), para o cursor não pular entre as duas.

Puro: não conhece Qt nem MediaPipe; a conversão para a superfície vem de fora.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from desktop import config
from desktop.communication.message_protocol import HandState
from desktop.core.coordinate_mapper import CameraNormPoint

#: camera_norm → (x, y) em surface_norm, ou None. Vem da calibração.
ToSurface = Callable[[CameraNormPoint], "tuple[float, float] | None"]


@dataclass(frozen=True)
class HandScore:
    board_distance: float  # 0 sobre a lousa; senão, distância até a borda (surface_norm)
    size: float  # tamanho aparente (surface_norm ou px da câmera)


def _board_distance(point: tuple[float, float] | None) -> float:
    if point is None:
        return math.inf
    x, y = point
    dx = max(0.0, -x, x - 1.0)
    dy = max(0.0, -y, y - 1.0)
    return math.hypot(dx, dy)


def score(hand: HandState, to_surface: ToSurface | None, aspect: float = 16 / 9) -> HandScore:
    tip = hand.index_tip
    if to_surface is None or tip is None:
        return HandScore(0.0, hand.palm_size_px or 0.0)
    distance = _board_distance(to_surface(CameraNormPoint(tip.x, tip.y)))
    size = hand.palm_size_px or 0.0
    if hand.palm:
        pts = [to_surface(CameraNormPoint(p.x, p.y)) for p in hand.palm]
        if all(p is not None for p in pts):
            wx, wy = pts[0]
            # Distâncias na superfície com a proporção da tela (x vale `aspect` vezes y).
            size = sum(math.hypot((x - wx) * aspect, y - wy) for x, y in pts[1:]) / (len(pts) - 1)
    return HandScore(distance, size)


def _better(a: HandScore, b: HandScore) -> bool:
    """`a` é claramente melhor que `b` (margens de estabilidade)?"""
    if a.board_distance + config.HAND_SWITCH_BOARD_MARGIN < b.board_distance:
        return True
    if abs(a.board_distance - b.board_distance) <= config.HAND_SWITCH_BOARD_MARGIN:
        return a.size * (1 + config.HAND_SWITCH_SIZE_MARGIN) < b.size
    return False


class HandSelector:
    def __init__(self) -> None:
        self._previous_tip: CameraNormPoint | None = None

    def reset(self) -> None:
        self._previous_tip = None

    def select(self, candidates: Sequence[HandState], to_surface: ToSurface | None = None,
               aspect: float = 16 / 9) -> HandState | None:
        hands = [h for h in candidates if h.present and h.index_tip is not None]
        if not hands:
            self._previous_tip = None
            return None
        if len(hands) == 1:
            chosen = hands[0]
        else:
            scores = [score(h, to_surface, aspect) for h in hands]
            best = min(range(len(hands)),
                       key=lambda i: (scores[i].board_distance, scores[i].size))
            chosen = hands[best]
            previous = self._same_as_previous(hands)
            if previous is not None and previous != best and not _better(scores[best], scores[previous]):
                chosen = hands[previous]  # a outra não é claramente melhor: mantém
        self._previous_tip = CameraNormPoint(chosen.index_tip.x, chosen.index_tip.y)
        return chosen

    def _same_as_previous(self, hands: Sequence[HandState]) -> int | None:
        if self._previous_tip is None:
            return None
        p = self._previous_tip
        distances = [math.hypot(h.index_tip.x - p.x, h.index_tip.y - p.y) for h in hands]
        i = min(range(len(hands)), key=distances.__getitem__)
        return i if distances[i] <= config.HAND_SAME_MAX_DIST else None
