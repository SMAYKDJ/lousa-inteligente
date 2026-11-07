"""Acionar por permanência: o dedo fica sobre um alvo até completar o tempo (Fase 3).

PROJECT_CONTEXT.md §8.2: a seleção não pode acontecer só porque a mão passou
sobre o botão. Enquanto não detectamos o toque na superfície (Fase 5), a
confirmação é o tempo de permanência (aprovado: 0,8 s), com:
- tolerância: pequenas oscilações perto do alvo não zeram o progresso;
- uma vez por entrada: depois de acionar, o mesmo alvo só aciona de novo
  quando o dedo sair e voltar (sem disparo em cascata).

Puro: recebe pontos em ui_px e retângulos dos alvos; não conhece Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Sequence

from desktop import config


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, px: float, py: float, margin: float = 0.0) -> bool:
        return (self.x - margin <= px <= self.x + self.w + margin
                and self.y - margin <= py <= self.y + self.h + margin)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass(frozen=True)
class Target:
    key: Hashable
    rect: Rect


@dataclass(frozen=True)
class DwellEvent:
    kind: str  # "fire" (acionou) ou "cancel" (saiu antes de completar)
    key: Hashable
    progress: float  # fração completada ao cancelar (1.0 ao acionar)


class DwellTracker:
    def __init__(self, dwell_s: float = config.DWELL_S, tolerance_px: float = 0.0) -> None:
        self.dwell_s = dwell_s
        self.tolerance_px = tolerance_px
        self.current: Hashable | None = None
        self._since = 0.0
        self._fired = False

    def reset(self) -> None:
        self.current, self._fired = None, False

    def progress(self, now: float) -> float:
        if self.current is None or self._fired:
            return 0.0
        return min(1.0, (now - self._since) / self.dwell_s)

    def update(self, now: float, point: tuple[float, float] | None,
               targets: Sequence[Target]) -> DwellEvent | None:
        """Novo ponto do dedo (ou None sem dedo). Devolve um evento quando há."""
        hit = self._hit(point, targets)
        if hit != self.current:
            event = None
            if self.current is not None and not self._fired:
                done = self.progress(now)
                if done >= 0.25:  # entrou de fato e desistiu: registra (métrica de uso)
                    event = DwellEvent("cancel", self.current, round(done, 2))
            self.current, self._since, self._fired = hit, now, False
            return event
        if hit is not None and not self._fired and now - self._since >= self.dwell_s:
            self._fired = True
            return DwellEvent("fire", hit, 1.0)
        return None

    def _hit(self, point, targets: Sequence[Target]) -> Hashable | None:
        if point is None:
            return None
        x, y = point
        # Continua no alvo atual com tolerância; para entrar num novo, precisa estar dentro.
        for target in targets:
            if target.key == self.current and target.rect.contains(x, y, self.tolerance_px):
                return target.key
        for target in targets:
            if target.rect.contains(x, y):
                return target.key
        return None
