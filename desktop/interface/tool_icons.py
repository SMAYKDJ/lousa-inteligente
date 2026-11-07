"""Ícones da sidebar desenhados em código (sem imagens externas, sem dependência nova).

Traços grossos e formas simples: precisam ser legíveis numa projeção a alguns
metros (CLAUDE.md §7, legibilidade em projeção).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from desktop.interface.sidebar_model import Action, Control, Tool


def _pen(color: QColor, width: float, dashed: bool = False) -> QPen:
    pen = QPen(color, width, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    return pen


def _arrow(painter: QPainter, c: QPointF, s: float, direction: int) -> None:
    """Seta curva de desfazer (-1) ou refazer (+1)."""
    path = QPainterPath()
    path.moveTo(c + QPointF(direction * s * 0.5, s * 0.35))
    path.cubicTo(c + QPointF(direction * s * 0.5, -s * 0.35), c + QPointF(-direction * s * 0.4, -s * 0.4),
                 c + QPointF(-direction * s * 0.45, s * 0.05))
    painter.drawPath(path)
    tip = c + QPointF(-direction * s * 0.45, s * 0.05)
    painter.drawLine(tip, tip + QPointF(-direction * s * 0.05, -s * 0.28))
    painter.drawLine(tip, tip + QPointF(direction * s * 0.25, -s * 0.12))


def draw_icon(painter: QPainter, key, rect: QRectF, color: QColor) -> None:
    """Desenha o ícone de `key` centralizado em `rect` (a parte de cima do botão)."""
    s = min(rect.width(), rect.height()) * 0.5
    c = QPointF(rect.center().x(), rect.top() + rect.height() * 0.42)
    w = max(2.0, s * 0.12)
    painter.save()
    painter.setPen(_pen(color, w))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if key is Tool.POINTER:
        poly = QPolygonF([c + QPointF(-s * .35, -s * .5), c + QPointF(s * .4, s * .05),
                          c + QPointF(0, s * .12), c + QPointF(-s * .12, s * .5)])
        painter.setBrush(color)
        painter.drawPolygon(poly)
    elif key is Tool.SELECT:
        painter.setPen(_pen(color, w, dashed=True))
        painter.drawRect(QRectF(c.x() - s * .45, c.y() - s * .4, s * .9, s * .8))
    elif key is Tool.BRUSH:
        path = QPainterPath(c + QPointF(-s * .5, s * .2))
        path.cubicTo(c + QPointF(-s * .2, -s * .6), c + QPointF(s * .1, s * .6), c + QPointF(s * .5, -s * .3))
        painter.drawPath(path)
    elif key is Tool.ERASER:
        painter.translate(c)
        painter.rotate(-35)
        painter.drawRoundedRect(QRectF(-s * .5, -s * .22, s, s * .44), 4, 4)
        painter.drawLine(QPointF(-s * .1, -s * .22), QPointF(-s * .1, s * .22))
    elif key is Tool.CIRCLE:
        painter.drawEllipse(c, s * .45, s * .45)
    elif key is Tool.RECTANGLE:
        painter.drawRect(QRectF(c.x() - s * .5, c.y() - s * .35, s, s * .7))
    elif key is Action.UNDO:
        _arrow(painter, c, s, +1)  # ↶ ponta à esquerda
    elif key is Action.REDO:
        _arrow(painter, c, s, -1)  # ↷ ponta à direita
    elif key is Action.CLEAR:
        painter.drawLine(c + QPointF(-s * .45, -s * .3), c + QPointF(s * .45, -s * .3))
        painter.drawLine(c + QPointF(-s * .12, -s * .45), c + QPointF(s * .12, -s * .45))
        painter.drawPolygon(QPolygonF([c + QPointF(-s * .32, -s * .3), c + QPointF(s * .32, -s * .3),
                                       c + QPointF(s * .24, s * .5), c + QPointF(-s * .24, s * .5)]))
    elif key in (Action.PREV_SLIDE, Action.NEXT_SLIDE):
        d = -1 if key is Action.PREV_SLIDE else 1
        painter.drawRoundedRect(QRectF(c.x() - s * .5, c.y() - s * .38, s, s * .76), 3, 3)
        painter.drawPolyline(QPolygonF([c + QPointF(-d * s * .1, -s * .2), c + QPointF(d * s * .15, 0),
                                        c + QPointF(-d * s * .1, s * .2)]))
    elif key is Action.EXPORT:
        # Folha com a ponta dobrada e uma seta para baixo (salvar).
        page = QPolygonF([c + QPointF(-s * .36, -s * .5), c + QPointF(s * .14, -s * .5),
                          c + QPointF(s * .36, -s * .28), c + QPointF(s * .36, s * .5),
                          c + QPointF(-s * .36, s * .5)])
        painter.drawPolygon(page)
        painter.drawLine(c + QPointF(0, -s * .22), c + QPointF(0, s * .26))
        painter.drawLine(c + QPointF(0, s * .26), c + QPointF(-s * .15, s * .1))
        painter.drawLine(c + QPointF(0, s * .26), c + QPointF(s * .15, s * .1))
    elif key is Control.ORIENTATION:
        painter.drawRect(QRectF(c.x() - s * .5, c.y() - s * .15, s * .45, s * .3))
        painter.drawRect(QRectF(c.x() + s * .12, c.y() - s * .5, s * .3, s * .8))
    elif key is Control.MOVE:
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tip = c + QPointF(dx * s * .5, dy * s * .5)
            painter.drawLine(c, tip)
            side = QPointF(dy * s * .14, dx * s * .14)
            back = tip - QPointF(dx * s * .18, dy * s * .18)
            painter.drawLine(tip, back + side)
            painter.drawLine(tip, back - side)
    painter.restore()
