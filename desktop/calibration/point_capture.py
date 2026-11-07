"""Coleta da posição do dedo num alvo de calibração (D014, docs/calibration.md §2.1).

Durante a janela de coleta (os últimos instantes da contagem), junta as
posições da ponta do indicador e decide se o ponto é confiável:
- a mão apareceu em pelo menos `min_presence` dos quadros;
- o dedo ficou parado: a dispersão não passa de `max_spread` (camera_norm).
O ponto aceito é a MEDIANA das posições: um quadro errado não o desloca.
A dispersão usa o percentil 80 dos desvios em relação à mediana, pelo mesmo
motivo: um quadro isolado errado não reprova um dedo que estava parado.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum

from desktop.core.coordinate_mapper import CameraNormPoint


class RejectReason(str, Enum):
    NO_FRAMES = "no_frames"  # nenhum quadro chegou (câmera/conexão)
    HAND_NOT_SEEN = "hand_not_seen"  # mão ausente em quadros demais
    FINGER_MOVING = "finger_moving"  # dedo não ficou parado


REJECT_MESSAGES = {
    RejectReason.NO_FRAMES: "Nenhuma imagem da câmera chegou. Verifique o celular.",
    RejectReason.HAND_NOT_SEEN: "Não vi o dedo no alvo. Mantenha a mão visível para a câmera.",
    RejectReason.FINGER_MOVING: "O dedo se moveu. Mantenha a ponta parada no alvo até o fim.",
}


@dataclass(frozen=True)
class CaptureResult:
    point: CameraNormPoint | None
    reason: RejectReason | None
    frames: int
    with_hand: int
    spread: float | None  # desvio (percentil 80, em camera_norm) em relação à mediana

    @property
    def accepted(self) -> bool:
        return self.point is not None


class PointCollector:
    def __init__(self, min_presence: float, max_spread: float) -> None:
        self.min_presence = min_presence
        self.max_spread = max_spread
        self._frames = 0
        self._tips: list[CameraNormPoint] = []

    def add(self, tip: CameraNormPoint | None) -> None:
        self._frames += 1
        if tip is not None:
            self._tips.append(tip)

    def result(self) -> CaptureResult:
        frames, tips = self._frames, self._tips
        if frames == 0:
            return CaptureResult(None, RejectReason.NO_FRAMES, 0, 0, None)
        if not tips or len(tips) / frames < self.min_presence:
            return CaptureResult(None, RejectReason.HAND_NOT_SEEN, frames, len(tips), None)
        median = CameraNormPoint(statistics.median(p.x for p in tips),
                                 statistics.median(p.y for p in tips))
        deviations = sorted(max(abs(p.x - median.x), abs(p.y - median.y)) for p in tips)
        spread = deviations[int(0.8 * (len(deviations) - 1))]
        if spread > self.max_spread:
            return CaptureResult(None, RejectReason.FINGER_MOVING, frames, len(tips), spread)
        return CaptureResult(median, None, frames, len(tips), spread)
