"""Estilo atual do desenho: cor e espessura do pincel, tamanho da borracha (RF20, RF21).

Círculo e retângulo usam a cor e a espessura do pincel.
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop import config


@dataclass
class DrawingStyle:
    color_index: int = 0
    width_index: int = 1
    eraser_index: int = 1

    @property
    def color(self) -> str:
        return config.BRUSH_COLORS[self.color_index][1]

    @property
    def width_frac(self) -> float:
        return config.BRUSH_WIDTHS_FRAC[self.width_index]

    @property
    def eraser_frac(self) -> float:
        return config.ERASER_RADII_FRAC[self.eraser_index]

    def apply(self, kind: str, index: int) -> dict:
        """Aplica uma escolha do painel ("color", "width" ou "eraser"). Devolve o evento do log."""
        if kind == "color":
            self.color_index = index
            return {"event": "ui_style", "color": config.BRUSH_COLORS[index][0]}
        if kind == "width":
            self.width_index = index
            return {"event": "ui_style", "width": config.BRUSH_WIDTH_LABELS[index]}
        if kind == "eraser":
            self.eraser_index = index
            return {"event": "ui_style", "eraser": config.ERASER_LABELS[index]}
        raise ValueError(kind)
