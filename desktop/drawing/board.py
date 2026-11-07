"""Anotações da lousa e seu histórico (Fase 4).

Tudo em surface_norm (x, y ∈ [0, 1] sobre a área projetada): as anotações não
dependem do tamanho da janela. Itens são imutáveis; o histórico guarda
"fotografias" da lista de itens (são só referências, custo baixo).

Sem Qt: testável isoladamente (CLAUDE.md §9.1, histórico de desenho).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Union

Point = tuple[float, float]


@dataclass(frozen=True)
class Stroke:
    points: tuple[Point, ...]
    color: str
    width: float  # fração da altura da lousa


@dataclass(frozen=True)
class Ellipse:
    center: Point
    edge: Point  # ponto da borda: raio = distância em px até o centro
    color: str
    width: float


@dataclass(frozen=True)
class Rectangle:
    a: Point
    b: Point  # vértice oposto
    color: str
    width: float


Item = Union[Stroke, Ellipse, Rectangle]


def resample(points: list[Point], spacing: float, aspect: float) -> list[Point]:
    """Pontos a cada `spacing` (em unidades da altura), mantendo o primeiro e o último."""
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for p in points[1:]:
        last = out[-1]
        dx, dy = (p[0] - last[0]) * aspect, p[1] - last[1]
        dist = math.hypot(dx, dy)
        steps = int(dist // spacing)
        for i in range(1, steps + 1):
            t = i * spacing / dist
            out.append((last[0] + (p[0] - last[0]) * t, last[1] + (p[1] - last[1]) * t))
        if out[-1] != p and math.hypot((p[0] - out[-1][0]) * aspect, p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def _dist_px(a: Point, b: Point, size: tuple[float, float]) -> float:
    return math.hypot((a[0] - b[0]) * size[0], (a[1] - b[1]) * size[1])


def _touches_outline(item: Item, p: Point, radius_px: float, size: tuple[float, float]) -> bool:
    w, h = size
    px, py = p[0] * w, p[1] * h
    if isinstance(item, Ellipse):
        r = _dist_px(item.center, item.edge, size)
        d = math.hypot(px - item.center[0] * w, py - item.center[1] * h)
        return abs(d - r) <= radius_px
    x0, x1 = sorted((item.a[0] * w, item.b[0] * w))
    y0, y1 = sorted((item.a[1] * h, item.b[1] * h))
    inside_x, inside_y = x0 - radius_px <= px <= x1 + radius_px, y0 - radius_px <= py <= y1 + radius_px
    near_vertical = min(abs(px - x0), abs(px - x1)) <= radius_px and inside_y
    near_horizontal = min(abs(py - y0), abs(py - y1)) <= radius_px and inside_x
    return near_vertical or near_horizontal


def translate(item: Item, dx: float, dy: float) -> Item:
    """O mesmo item deslocado de (dx, dy) em surface_norm."""
    move = lambda p: (p[0] + dx, p[1] + dy)  # noqa: E731
    if isinstance(item, Stroke):
        return dataclasses.replace(item, points=tuple(move(p) for p in item.points))
    if isinstance(item, Ellipse):
        return dataclasses.replace(item, center=move(item.center), edge=move(item.edge))
    return dataclasses.replace(item, a=move(item.a), b=move(item.b))


def scale_item(item: Item, factor: float, anchor: Point) -> Item:
    """O item ampliado/reduzido em torno de `anchor` (surface_norm), mantendo a forma em px."""
    def sc(p):
        return (anchor[0] + (p[0] - anchor[0]) * factor, anchor[1] + (p[1] - anchor[1]) * factor)
    if isinstance(item, Stroke):
        return dataclasses.replace(item, points=tuple(sc(p) for p in item.points))
    if isinstance(item, Ellipse):
        return dataclasses.replace(item, center=sc(item.center), edge=sc(item.edge))
    return dataclasses.replace(item, a=sc(item.a), b=sc(item.b))


def bounds(item: Item, size: tuple[float, float]) -> tuple[float, float, float, float]:
    """Retângulo que envolve o item, em surface_norm: (x0, y0, x1, y1)."""
    if isinstance(item, Stroke):
        xs, ys = [p[0] for p in item.points], [p[1] for p in item.points]
        return min(xs), min(ys), max(xs), max(ys)
    if isinstance(item, Ellipse):
        r = _dist_px(item.center, item.edge, size)
        rx, ry = r / size[0], r / size[1]
        return item.center[0] - rx, item.center[1] - ry, item.center[0] + rx, item.center[1] + ry
    return (min(item.a[0], item.b[0]), min(item.a[1], item.b[1]),
            max(item.a[0], item.b[0]), max(item.a[1], item.b[1]))


def _touches(item: Item, p: Point, radius_px: float, size: tuple[float, float]) -> bool:
    """Para pegar com Selecionar: no traço, no contorno ou dentro da forma."""
    if isinstance(item, Stroke):
        reach = radius_px + item.width * size[1] / 2
        return any(_dist_px(q, p, size) <= reach for q in item.points)
    x0, y0, x1, y1 = bounds(item, size)
    if isinstance(item, Ellipse):
        r = _dist_px(item.center, item.edge, size)
        return _dist_px(item.center, p, size) <= r + radius_px
    m = radius_px
    return x0 * size[0] - m <= p[0] * size[0] <= x1 * size[0] + m and \
        y0 * size[1] - m <= p[1] * size[1] <= y1 * size[1] + m


class Board:
    def __init__(self) -> None:
        self.items: tuple[Item, ...] = ()
        self._undo: list[tuple[Item, ...]] = []
        self._redo: list[tuple[Item, ...]] = []
        self._group_open = False

    # --- histórico -------------------------------------------------------------

    def _checkpoint(self) -> None:
        if self._group_open:
            return  # dentro de um gesto da borracha: uma só entrada para o gesto todo
        self._undo.append(self.items)
        self._redo.clear()

    def begin_group(self) -> None:
        """Início de um gesto que muda várias vezes (borracha): desfaz tudo de uma vez."""
        if not self._group_open:
            self._undo.append(self.items)
            self._redo.clear()
            self._group_open = True

    def end_group(self) -> None:
        if self._group_open:
            self._group_open = False
            if self._undo and self._undo[-1] == self.items:
                self._undo.pop()  # o gesto não apagou nada: não ocupa o histórico

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.items)
        self.items = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.items)
        self.items = self._redo.pop()
        return True

    # --- alterações --------------------------------------------------------------

    def add(self, item: Item) -> None:
        self._checkpoint()
        self.items = self.items + (item,)

    def clear(self) -> bool:
        if not self.items:
            return False
        self._checkpoint()
        self.items = ()
        return True

    def hit(self, point: Point, radius_px: float, size: tuple[float, float]) -> int | None:
        """Índice do item mais recente sob o dedo (o que está por cima), ou None."""
        for i in range(len(self.items) - 1, -1, -1):
            if _touches(self.items[i], point, radius_px, size):
                return i
        return None

    def move(self, index: int, dx: float, dy: float) -> None:
        """Desloca um item. Use dentro de begin_group/end_group: o arrasto vira uma ação só."""
        if dx == 0 and dy == 0:
            return
        self._checkpoint()
        items = list(self.items)
        items[index] = translate(items[index], dx, dy)
        self.items = tuple(items)

    def replace(self, index: int, item: Item) -> None:
        """Troca um item (redimensionar). Use dentro de begin_group/end_group."""
        self._checkpoint()
        items = list(self.items)
        items[index] = item
        self.items = tuple(items)

    def erase(self, point: Point, radius_px: float, size: tuple[float, float]) -> int:
        """Apaga o que está a até `radius_px` do ponto. Traços são cortados; formas
        tocadas no contorno saem inteiras. Devolve quantos itens mudaram."""
        changed, result = 0, []
        for item in self.items:
            if isinstance(item, Stroke):
                pieces, current, cut = [], [], False
                for p in item.points:
                    if _dist_px(p, point, size) <= radius_px:
                        cut = True
                        if len(current) >= 2:
                            pieces.append(current)
                        current = []
                    else:
                        current.append(p)
                if len(current) >= 2:
                    pieces.append(current)
                if cut:
                    changed += 1
                    result += [Stroke(tuple(piece), item.color, item.width) for piece in pieces]
                else:
                    result.append(item)
            elif _touches_outline(item, point, radius_px, size):
                changed += 1
            else:
                result.append(item)
        if changed:
            self._checkpoint()
            self.items = tuple(result)
        return changed
