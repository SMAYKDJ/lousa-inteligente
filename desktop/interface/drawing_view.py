"""Desenho das anotações e da confirmação na lousa (Qt).

Recebe itens em surface_norm e converte para ui_px aqui, explicitamente
(CLAUDE.md §5.2): x_px = x * largura, y_px = y * altura da janela, que cobre
exatamente a área projetada.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from desktop import config
from desktop.drawing.board import Ellipse, Rectangle, Stroke, bounds
from desktop.interaction.confirm import NO, YES, ConfirmPrompt

TRAIL = QColor("#ff3b30")
BOX = QColor(18, 22, 28, 250)
TEXT = QColor("#f4f6f8")
YES_COLOR = QColor("#e63946")
NO_COLOR = QColor("#3ccf8e")
DWELL = QColor("#f0b429")


def _pen(color: str, width_frac: float, h: float) -> QPen:
    pen = QPen(QColor(color), max(1.0, width_frac * h))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_item(painter: QPainter, item, w: float, h: float) -> None:
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(item.color, item.width, h))
    if isinstance(item, Stroke):
        pts = [QPointF(x * w, y * h) for x, y in item.points]
        if len(pts) == 1 or all(p == pts[0] for p in pts):
            painter.drawPoint(pts[0])
            return
        path = QPainterPath(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        painter.drawPath(path)
    elif isinstance(item, Ellipse):
        cx, cy = item.center[0] * w, item.center[1] * h
        r = math.hypot(item.edge[0] * w - cx, item.edge[1] * h - cy)
        painter.drawEllipse(QPointF(cx, cy), r, r)
    elif isinstance(item, Rectangle):
        painter.drawRect(QRectF(QPointF(item.a[0] * w, item.a[1] * h),
                                QPointF(item.b[0] * w, item.b[1] * h)).normalized())


def draw_board(painter: QPainter, items, preview, w: float, h: float) -> None:
    for item in items:
        draw_item(painter, item, w, h)
    if preview is not None:
        draw_item(painter, preview, w, h)


def draw_pointer_trail(painter: QPainter, trail, now: float, w: float, h: float) -> None:
    """Rastro tipo laser: mais grosso e opaco perto do dedo, some com o tempo."""
    for (a, ta), (b, _) in zip(trail, trail[1:]):
        fade = max(0.0, 1 - (now - ta) / config.POINTER_TRAIL_S)
        color = QColor(TRAIL)
        color.setAlphaF(0.85 * fade)
        pen = QPen(color, max(2.0, 0.008 * h * (0.4 + 0.6 * fade)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(a[0] * w, a[1] * h), QPointF(b[0] * w, b[1] * h))
    if trail:
        (x, y), _ = trail[-1]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(TRAIL)
        painter.drawEllipse(QPointF(x * w, y * h), 0.007 * h, 0.007 * h)


def draw_eraser(painter: QPainter, point, h: float, radius_frac: float) -> None:
    if point is None:
        return
    painter.setBrush(QColor(255, 255, 255, 40))
    painter.setPen(QPen(QColor(255, 255, 255, 200), 2, Qt.PenStyle.DashLine))
    r = radius_frac * h
    painter.drawEllipse(QPointF(*point), r, r)


def draw_confirm(painter: QPainter, prompt: ConfirmPrompt, hover_key, hover_progress: float) -> None:
    b = prompt.box
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BOX)
    painter.drawRoundedRect(QRectF(b.x, b.y, b.w, b.h), 14, 14)
    font = QFont()
    font.setPixelSize(max(14, int(prompt.yes.h * 0.32)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(TEXT)
    painter.drawText(QRectF(b.x, b.y, b.w, prompt.yes.y - b.y), Qt.AlignmentFlag.AlignCenter,
                     prompt.question)
    for key, rect, label, color in ((YES, prompt.yes, "Sim", YES_COLOR), (NO, prompt.no, "Não", NO_COLOR)):
        r = QRectF(rect.x, rect.y, rect.w, rect.h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(r)
        painter.setPen(TEXT)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        if key == hover_key and hover_progress > 0:
            width = max(4.0, rect.w * 0.07)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(DWELL, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(r.adjusted(-width, -width, width, width), 90 * 16,
                            -int(hover_progress * 360 * 16))


def draw_selection(painter: QPainter, item, w: float, h: float,
                   scale: float | None = None, progress: float = 0.0) -> None:
    """Moldura tracejada no item seguro pelo Selecionar.

    Redimensionando (`scale` não é None): mostra o tamanho em % e um anel que
    enche enquanto a mão fica parada (ao completar, o tamanho fica).
    """
    if item is None:
        return
    x0, y0, x1, y1 = bounds(item, (w, h))
    m = 0.012 * h
    frame = QRectF(x0 * w - m, y0 * h - m, (x1 - x0) * w + 2 * m, (y1 - y0) * h + 2 * m)
    color = QColor("#f0b429") if scale is not None else QColor("#3ccf8e")
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, 3, Qt.PenStyle.DashLine))
    painter.drawRoundedRect(frame, 8, 8)
    if scale is None:
        return
    font = QFont()
    font.setPixelSize(max(16, int(h * 0.026)))
    font.setBold(True)
    painter.setFont(font)
    label = QRectF(frame.center().x() - 110, frame.top() - font.pixelSize() * 2.2, 220, font.pixelSize() * 1.8)
    if label.top() < 0:
        label.moveTop(frame.bottom() + 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 200))
    painter.drawRoundedRect(label, 8, 8)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(label, Qt.AlignmentFlag.AlignCenter, f"Tamanho {scale * 100:.0f}%")
    if progress > 0:
        r = font.pixelSize() * 0.7
        c = QPointF(label.right() - r - 6, label.center().y())
        painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 90 * 16, -int(progress * 360 * 16))
