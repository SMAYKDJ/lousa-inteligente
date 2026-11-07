"""Conversão de coordenadas entre sistemas (CLAUDE.md §5.2, docs/architecture.md §3).

Fase 1: só existe o mapeamento PROVISÓRIO `camera_norm → ui_px`, que estica o
frame inteiro da câmera sobre a janela. Não é calibração. Na Fase 2 ele será
substituído pela homografia `camera_norm → surface → ui_px`, sem mudar quem
o usa.

Cada sistema tem seu próprio tipo, para que uma coordenada de câmera nunca
seja usada como coordenada de tela por engano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CameraNormPoint:
    """Ponto no frame da câmera, normalizado: x, y ∈ [0, 1], origem no canto superior esquerdo."""

    x: float
    y: float


@dataclass(frozen=True)
class UiSize:
    width: float
    height: float


@dataclass(frozen=True)
class UiPoint:
    """Ponto na área da interface do notebook, em pixels lógicos do Qt."""

    x: float
    y: float


class CameraToUiMapper(Protocol):
    def map(self, point: CameraNormPoint, ui: UiSize) -> UiPoint: ...


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


class StretchMapper:
    """Mapeamento provisório da Fase 1: o frame inteiro da câmera ocupa a janela.

    Limitações conhecidas (documentadas, não bugs):
    - não corrige perspectiva nem o ângulo da câmera (isso é a Fase 2);
    - se o frame e a janela têm proporções diferentes (ex.: câmera em retrato
      720×1280 e janela em paisagem), o movimento fica esticado num eixo.
    """

    def map(self, point: CameraNormPoint, ui: UiSize) -> UiPoint:
        return UiPoint(x=_clamp01(point.x) * ui.width, y=_clamp01(point.y) * ui.height)
