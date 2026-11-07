"""Sidebar aprovada (PROJECT_CONTEXT.md §7), sem Qt: estados, layout, limites e arrasto.

Padrão aprovado: botão circular semitransparente encaixado na borda, que abre
um painel flutuante com animação lateral; orientação vertical ou horizontal;
reposicionamento livre; nunca desloca a apresentação (é desenhada no overlay).

Escolhas do usuário (2026-11-06): botão na borda ESQUERDA, no meio; painel
vertical; acionamento por permanência de 0,8 s (desktop/interaction/dwell.py).

Ferramentas e ações só mudam estado e geram eventos nesta fase. O desenho é
da Fase 4, e a troca de slides é da Fase 6.

Coordenadas: tudo em ui_px da janela da lousa (CLAUDE.md §5.2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from desktop import config
from desktop.interaction.dwell import Rect, Target


class Edge(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class Orientation(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class SidebarState(str, Enum):
    COLLAPSED = "collapsed"  # recolhida: só o botão circular
    OPENING = "opening"
    EXPANDED = "expanded"
    CLOSING = "closing"
    DRAGGING = "dragging"  # painel sendo movido pelo dedo


class Tool(str, Enum):
    POINTER = "pointer"
    SELECT = "select"
    BRUSH = "brush"
    ERASER = "eraser"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"


class Action(str, Enum):
    UNDO = "undo"
    REDO = "redo"
    CLEAR = "clear"
    PREV_SLIDE = "prev_slide"
    NEXT_SLIDE = "next_slide"
    EXPORT = "export"  # salvar as anotações em PDF (D031)


class Control(str, Enum):
    HANDLE = "handle"  # botão circular: abre/recolhe
    ORIENTATION = "orientation"  # alterna vertical/horizontal
    MOVE = "move"  # alça de arrasto


#: Ordem dos botões no painel.
BUTTONS: tuple = (
    Tool.POINTER, Tool.SELECT, Tool.BRUSH, Tool.ERASER, Tool.CIRCLE, Tool.RECTANGLE,
    Action.UNDO, Action.REDO, Action.CLEAR, Action.PREV_SLIDE, Action.NEXT_SLIDE,
    Action.EXPORT, Control.ORIENTATION, Control.MOVE,
)

LABELS = {
    Tool.POINTER: "Ponteiro", Tool.SELECT: "Selecionar", Tool.BRUSH: "Pincel",
    Tool.ERASER: "Borracha", Tool.CIRCLE: "Círculo", Tool.RECTANGLE: "Retângulo",
    Action.UNDO: "Voltar", Action.REDO: "Avançar", Action.CLEAR: "Limpar",
    Action.PREV_SLIDE: "Slide ant.", Action.NEXT_SLIDE: "Próx. slide", Action.EXPORT: "Salvar PDF",
    Control.ORIENTATION: "Girar barra", Control.MOVE: "Mover",
}

#: O painel tem 2 colunas (vertical) ou 2 linhas (horizontal): cabe entre os
#: marcadores dos cantos mesmo com botões de 80 px.
_SHORT_SIDE = 2


@dataclass(frozen=True)
class Layout:
    handle: Rect  # quadrado que contém o botão circular
    panel: Rect | None  # None quando recolhida
    buttons: tuple[tuple[Any, Rect], ...]  # (chave, retângulo) de cada botão visível
    open_fraction: float  # 0 recolhida → 1 aberta (animação)


def _intersects(a: Rect, b: Rect) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def clamp_avoiding(rect: Rect, width: float, height: float, forbidden: Sequence[Rect],
                   margin: float = 8.0) -> Rect:
    """Mantém `rect` dentro da tela e fora das áreas proibidas (marcadores), com o menor deslocamento."""
    def inside(r: Rect) -> Rect:
        x = min(max(r.x, margin), width - margin - r.w)
        y = min(max(r.y, margin), height - margin - r.h)
        return Rect(x, y, r.w, r.h)

    r = inside(rect)
    for _ in range(4):
        hit = next((f for f in forbidden if _intersects(r, f)), None)
        if hit is None:
            return r
        options = [
            Rect(hit.x + hit.w + margin, r.y, r.w, r.h), Rect(hit.x - margin - r.w, r.y, r.w, r.h),
            Rect(r.x, hit.y + hit.h + margin, r.w, r.h), Rect(r.x, hit.y - margin - r.h, r.w, r.h),
        ]
        valid = [o for o in options if inside(o) == o]
        if not valid:
            return r
        r = min(valid, key=lambda o: abs(o.x - r.x) + abs(o.y - r.y))
    return r


class SidebarModel:
    def __init__(self, width: float, height: float, forbidden: Sequence[Rect] = (),
                 edge: Edge = Edge.LEFT, offset: float = 0.5,
                 orientation: Orientation = Orientation.VERTICAL) -> None:
        self.width, self.height = width, height
        self.forbidden = list(forbidden)
        self.edge, self.offset, self.orientation = edge, offset, orientation
        self.state = SidebarState.COLLAPSED
        self.tool = Tool.POINTER
        self.button = config.SIDEBAR_BUTTON_FRAC * min(width, height)
        self.gap = 0.12 * self.button
        self.pad = 0.15 * self.button
        self._anim_start = -1e9
        self._drag_rect: Rect | None = None  # posição do painel durante o arrasto
        self._drag_grab = (0.0, 0.0)  # ponto do painel "seguro" pelo dedo
        self._still_since = 0.0
        self._still_point: tuple[float, float] | None = None
        self._last_seen = 0.0

    # --- geometria -----------------------------------------------------------

    def _grid(self) -> tuple[int, int]:
        n = len(BUTTONS)
        long_side = math.ceil(n / _SHORT_SIDE)
        return (_SHORT_SIDE, long_side) if self.orientation is Orientation.VERTICAL \
            else (long_side, _SHORT_SIDE)

    def panel_size(self) -> tuple[float, float]:
        cols, rows = self._grid()
        b, g, p = self.button, self.gap, self.pad
        return (cols * b + (cols - 1) * g + 2 * p, rows * b + (rows - 1) * g + 2 * p)

    def handle_rect(self) -> Rect:
        d = 1.1 * self.button
        r = d / 2
        inset = 0.5 * r  # ~75% do círculo à mostra, encaixado na borda
        if self.edge is Edge.LEFT:
            cx, cy = inset, self.offset * self.height
        elif self.edge is Edge.RIGHT:
            cx, cy = self.width - inset, self.offset * self.height
        elif self.edge is Edge.TOP:
            cx, cy = self.offset * self.width, inset
        else:
            cx, cy = self.offset * self.width, self.height - inset
        rect = Rect(cx - r, cy - r, d, d)
        # Desvia dos marcadores só ao longo da borda (o encaixe na borda é intencional).
        along = Edge.LEFT, Edge.RIGHT
        for f in self.forbidden:
            if _intersects(rect, f):
                if self.edge in along:
                    cy = f.y + f.h + r + 4 if cy > f.y + f.h / 2 else f.y - r - 4
                else:
                    cx = f.x + f.w + r + 4 if cx > f.x + f.w / 2 else f.x - r - 4
                rect = Rect(cx - r, cy - r, d, d)
        return rect

    def _panel_final(self) -> Rect:
        w, h = self.panel_size()
        hr = self.handle_rect()
        cx, cy = hr.center
        g = self.gap
        if self.edge is Edge.LEFT:
            rect = Rect(hr.x + hr.w + g, cy - h / 2, w, h)
        elif self.edge is Edge.RIGHT:
            rect = Rect(hr.x - g - w, cy - h / 2, w, h)
        elif self.edge is Edge.TOP:
            rect = Rect(cx - w / 2, hr.y + hr.h + g, w, h)
        else:
            rect = Rect(cx - w / 2, hr.y - g - h, w, h)
        return clamp_avoiding(rect, self.width, self.height, self.forbidden)

    def _open_fraction(self, now: float) -> float:
        t = min(1.0, max(0.0, (now - self._anim_start) / config.SIDEBAR_ANIMATION_S))
        ease = 1 - (1 - t) ** 3  # desacelera no fim
        if self.state is SidebarState.OPENING:
            return ease
        if self.state is SidebarState.CLOSING:
            return 1 - ease
        return 1.0 if self.state in (SidebarState.EXPANDED, SidebarState.DRAGGING) else 0.0

    def layout(self, now: float) -> Layout:
        fraction = self._open_fraction(now)
        if self.state is SidebarState.DRAGGING and self._drag_rect is not None:
            panel = self._drag_rect
        elif fraction <= 0.0:
            return Layout(self.handle_rect(), None, (), 0.0)
        else:
            final = self._panel_final()
            # Desliza a partir da borda: fora da tela em 0, posição final em 1.
            dx = dy = 0.0
            if self.edge is Edge.LEFT:
                dx = -(final.x + final.w) * (1 - fraction)
            elif self.edge is Edge.RIGHT:
                dx = (self.width - final.x) * (1 - fraction)
            elif self.edge is Edge.TOP:
                dy = -(final.y + final.h) * (1 - fraction)
            else:
                dy = (self.height - final.y) * (1 - fraction)
            panel = Rect(final.x + dx, final.y + dy, final.w, final.h)
        return Layout(self.handle_rect(), panel, self._button_rects(panel), fraction)

    def _button_rects(self, panel: Rect) -> tuple[tuple[Any, Rect], ...]:
        cols, _ = self._grid()
        b, g, p = self.button, self.gap, self.pad
        rects = []
        for i, key in enumerate(BUTTONS):
            if self.orientation is Orientation.VERTICAL:
                col, row = i % cols, i // cols
            else:
                col, row = i // _SHORT_SIDE, i % _SHORT_SIDE
            rects.append((key, Rect(panel.x + p + col * (b + g), panel.y + p + row * (b + g), b, b)))
        return tuple(rects)

    # --- interação -----------------------------------------------------------

    def targets(self, now: float) -> list[Target]:
        """Alvos de permanência disponíveis agora (o botão circular sempre)."""
        if self.state is SidebarState.DRAGGING:
            return []
        layout = self.layout(now)
        targets = [Target(Control.HANDLE, layout.handle)]
        if self.state is SidebarState.EXPANDED:
            targets += [Target(key, rect) for key, rect in layout.buttons]
        return targets

    def tick(self, now: float) -> None:
        if now - self._anim_start >= config.SIDEBAR_ANIMATION_S:
            if self.state is SidebarState.OPENING:
                self.state = SidebarState.EXPANDED
            elif self.state is SidebarState.CLOSING:
                self.state = SidebarState.COLLAPSED

    def on_fire(self, key, now: float, point: tuple[float, float] | None = None) -> list[dict]:
        """Um alvo foi acionado por permanência. Devolve eventos para o log."""
        if key is Control.HANDLE:
            if self.state in (SidebarState.COLLAPSED, SidebarState.CLOSING):
                self.state, self._anim_start = SidebarState.OPENING, now
                return [{"event": "ui_open"}]
            if self.state in (SidebarState.EXPANDED, SidebarState.OPENING):
                self.state, self._anim_start = SidebarState.CLOSING, now
                return [{"event": "ui_close"}]
            return []
        if self.state is not SidebarState.EXPANDED:
            return []
        if isinstance(key, Tool):
            self.tool = key
            return [{"event": "ui_tool", "tool": key.value}]
        if isinstance(key, Action):
            return [{"event": "ui_action", "action": key.value}]
        if key is Control.ORIENTATION:
            self.orientation = (Orientation.HORIZONTAL if self.orientation is Orientation.VERTICAL
                                else Orientation.VERTICAL)
            return [{"event": "ui_orientation", "orientation": self.orientation.value}]
        if key is Control.MOVE:
            panel = self.layout(now).panel
            grab = point or self.button_center(Control.MOVE, now)
            self._drag_grab = (grab[0] - panel.x, grab[1] - panel.y)
            self._drag_rect = panel
            self.state = SidebarState.DRAGGING
            self._still_point, self._still_since, self._last_seen = grab, now, now
            return [{"event": "ui_drag_start"}]
        return []

    def button_center(self, key, now: float) -> tuple[float, float]:
        for k, rect in self.layout(now).buttons:
            if k == key:
                return rect.center
        return self.handle_rect().center

    # --- arrasto ---------------------------------------------------------------

    def drag_update(self, point: tuple[float, float] | None, now: float) -> list[dict]:
        """Durante o arrasto: o painel segue o dedo; parar o dedo (ou perdê-lo) solta."""
        if self.state is not SidebarState.DRAGGING:
            return []
        if point is None:
            if now - self._last_seen >= config.SIDEBAR_DROP_LOST_S:
                return self._drop()
            return []
        self._last_seen = now
        gx, gy = self._drag_grab
        w, h = self.panel_size()
        self._drag_rect = clamp_avoiding(Rect(point[0] - gx, point[1] - gy, w, h),
                                         self.width, self.height, self.forbidden)
        sp = self._still_point
        tolerance = config.DWELL_TOLERANCE_FRAC * self.width
        if sp is None or math.hypot(point[0] - sp[0], point[1] - sp[1]) > tolerance:
            self._still_point, self._still_since = point, now
        elif now - self._still_since >= config.DWELL_S:
            return self._drop()
        return []

    def drag_progress(self, now: float) -> float:
        """Quanto falta para soltar (0–1), para o anel de progresso."""
        if self.state is not SidebarState.DRAGGING:
            return 0.0
        return min(1.0, (now - self._still_since) / config.DWELL_S)

    def _drop(self) -> list[dict]:
        """Encaixa na borda mais próxima do centro do painel, na altura (ou largura) em que foi solto."""
        rect = self._drag_rect
        cx, cy = rect.center
        distances = {Edge.LEFT: cx, Edge.RIGHT: self.width - cx,
                     Edge.TOP: cy, Edge.BOTTOM: self.height - cy}
        self.edge = min(distances, key=distances.get)
        if self.edge in (Edge.LEFT, Edge.RIGHT):
            self.offset = cy / self.height
        else:
            self.offset = cx / self.width
        self.state, self._drag_rect = SidebarState.EXPANDED, None
        return [{"event": "ui_drop", "edge": self.edge.value, "offset": round(self.offset, 3)}]
