"""Painel de estilo ao lado da sidebar (RF20, RF21), sem Qt.

Escolha do usuário (2026-11-06): ao escolher Pincel ou Borracha, abre um painel
pequeno ao lado da sidebar.
- Pincel: 5 cores na 1ª linha e 3 espessuras na 2ª.
- Borracha: 3 tamanhos.

O painel fica aberto enquanto o professor escolhe e fecha quando ele começa a
riscar, deixa o dedo 1 s fora do painel e da sidebar, troca de ferramenta ou
recolhe a sidebar. Para mudar de novo, basta
escolher o Pincel (ou a Borracha) outra vez.

Chaves dos botões: ("color", i), ("width", i) e ("eraser", i).
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop import config
from desktop.interaction.dwell import Rect, Target
from desktop.interface.sidebar_model import Edge, SidebarModel, SidebarState, Tool, clamp_avoiding

STYLE_TOOLS = (Tool.BRUSH, Tool.ERASER)
STYLE_KINDS = ("color", "width", "eraser")


def is_style_key(key) -> bool:
    return isinstance(key, tuple) and len(key) == 2 and key[0] in STYLE_KINDS


@dataclass(frozen=True)
class StyleLayout:
    panel: Rect
    buttons: tuple[tuple[tuple[str, int], Rect], ...]


class StylePanel:
    def __init__(self) -> None:
        self.open = False

    def on_tool(self, tool: Tool) -> None:
        self.open = tool in STYLE_TOOLS

    def close(self) -> None:
        self.open = False

    def layout(self, sidebar: SidebarModel, now: float) -> StyleLayout | None:
        if not self.open or sidebar.tool not in STYLE_TOOLS or sidebar.state is not SidebarState.EXPANDED:
            return None
        bar = sidebar.layout(now).panel
        if bar is None:
            return None
        if sidebar.tool is Tool.BRUSH:
            rows = [[("color", i) for i in range(len(config.BRUSH_COLORS))],
                    [("width", i) for i in range(len(config.BRUSH_WIDTHS_FRAC))]]
        else:
            rows = [[("eraser", i) for i in range(len(config.ERASER_RADII_FRAC))]]
        b = config.STYLE_BUTTON_SCALE * sidebar.button
        g, p = sidebar.gap, sidebar.pad
        cols = max(len(r) for r in rows)
        w = cols * b + (cols - 1) * g + 2 * p
        h = len(rows) * b + (len(rows) - 1) * g + 2 * p

        # Ao lado da sidebar, na altura do botão da ferramenta escolhida.
        cx, cy = sidebar.button_center(sidebar.tool, now)
        if sidebar.edge is Edge.LEFT:
            rect = Rect(bar.x + bar.w + g, cy - h / 2, w, h)
        elif sidebar.edge is Edge.RIGHT:
            rect = Rect(bar.x - g - w, cy - h / 2, w, h)
        elif sidebar.edge is Edge.TOP:
            rect = Rect(cx - w / 2, bar.y + bar.h + g, w, h)
        else:
            rect = Rect(cx - w / 2, bar.y - g - h, w, h)
        rect = clamp_avoiding(rect, sidebar.width, sidebar.height, sidebar.forbidden + [bar])

        buttons = []
        for r, row in enumerate(rows):
            row_w = len(row) * b + (len(row) - 1) * g
            x0 = rect.x + (rect.w - row_w) / 2  # linhas mais curtas ficam centralizadas
            for c, key in enumerate(row):
                buttons.append((key, Rect(x0 + c * (b + g), rect.y + p + r * (b + g), b, b)))
        return StyleLayout(rect, tuple(buttons))

    def targets(self, sidebar: SidebarModel, now: float) -> list[Target]:
        layout = self.layout(sidebar, now)
        return [] if layout is None else [Target(k, r) for k, r in layout.buttons]
