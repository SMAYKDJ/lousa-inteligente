"""Desenho da sidebar na lousa (Qt). Só desenha o que o SidebarModel diz."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from desktop import config
from desktop.interaction.dwell import Rect
from desktop.interface.sidebar_model import (
    LABELS, Control, Edge, SidebarModel, SidebarState, Tool)
from desktop.interface.tool_icons import draw_icon

PANEL = QColor(18, 22, 28, config.SIDEBAR_PANEL_ALPHA)
HANDLE = QColor(18, 22, 28, config.SIDEBAR_HANDLE_ALPHA)
BUTTON = QColor(255, 255, 255, 28)
SELECTED = QColor("#3ccf8e")
ICON = QColor("#f4f6f8")
DWELL = QColor("#f0b429")
LABEL = QColor(232, 236, 241, 220)


def _q(rect: Rect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.w, rect.h)


def _ring(painter: QPainter, rect: QRectF, progress: float, color: QColor, width: float) -> None:
    if progress <= 0:
        return
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawArc(rect.adjusted(width / 2, width / 2, -width / 2, -width / 2),
                    90 * 16, -int(progress * 360 * 16))


def draw_sidebar(painter: QPainter, model: SidebarModel, now: float,
                 hover_key=None, hover_progress: float = 0.0) -> None:
    layout = model.layout(now)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if layout.panel is not None:
        panel = _q(layout.panel)
        dragging = model.state is SidebarState.DRAGGING
        painter.setPen(QPen(DWELL, 2, Qt.PenStyle.DashLine) if dragging else Qt.PenStyle.NoPen)
        painter.setBrush(PANEL)
        painter.drawRoundedRect(panel, model.button * 0.25, model.button * 0.25)
        font = QFont()
        font.setPixelSize(max(11, int(model.button * 0.17)))
        font.setBold(True)
        painter.setFont(font)
        for key, rect in layout.buttons:
            r = _q(rect)
            selected = key == model.tool
            painter.setPen(QPen(SELECTED, 3) if selected else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(60, 207, 142, 60) if selected else BUTTON)
            painter.drawEllipse(r)
            draw_icon(painter, key, r, SELECTED if selected else ICON)
            painter.setPen(LABEL)
            painter.drawText(QRectF(r.x() - 6, r.y() + r.height() * 0.66, r.width() + 12, r.height() * 0.3),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, LABELS[key])
            if key == hover_key:
                _ring(painter, r, hover_progress, DWELL, max(4.0, model.button * 0.07))
        if dragging:
            move = dict(layout.buttons).get(Control.MOVE)
            if move is not None:
                _ring(painter, _q(move), model.drag_progress(now), DWELL, max(4.0, model.button * 0.07))
            painter.setPen(DWELL)
            # Abaixo do painel; se não houver espaço (painel encostado embaixo), acima.
            below = panel.bottom() + 30 < model.height
            y = panel.bottom() + 6 if below else panel.top() - 28
            painter.drawText(QRectF(panel.x() - 40, y, panel.width() + 80, 22),
                             Qt.AlignmentFlag.AlignHCenter, "Pare o dedo para soltar")

    # Botão circular (sempre visível), por cima do painel.
    h = _q(layout.handle)
    painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
    painter.setBrush(HANDLE)
    painter.drawEllipse(h)
    _draw_chevron(painter, model, h, layout.open_fraction > 0.5)
    if hover_key is Control.HANDLE:
        _ring(painter, h, hover_progress, DWELL, max(4.0, model.button * 0.08))
    painter.restore()


def _draw_chevron(painter: QPainter, model: SidebarModel, rect: QRectF, is_open: bool) -> None:
    """Seta no botão circular: aponta para dentro da tela (abrir) ou para a borda (recolher)."""
    inward = {Edge.LEFT: (1, 0), Edge.RIGHT: (-1, 0), Edge.TOP: (0, 1), Edge.BOTTOM: (0, -1)}[model.edge]
    dx, dy = inward if not is_open else (-inward[0], -inward[1])
    # Centro da parte visível do botão (a outra parte fica fora da tela).
    c = rect.center() + QPointF(inward[0] * rect.width() * 0.18, inward[1] * rect.height() * 0.18)
    s = rect.width() * 0.16
    painter.setPen(QPen(ICON, max(3.0, rect.width() * 0.06), Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    tip = c + QPointF(dx * s, dy * s)
    back = c - QPointF(dx * s * 0.4, dy * s * 0.4)
    side = QPointF(dy * s, dx * s)
    painter.drawLine(back + side, tip)
    painter.drawLine(back - side, tip)


def draw_style_panel(painter: QPainter, layout, style, button: float,
                     hover_key=None, hover_progress: float = 0.0) -> None:
    """Painel de cor/espessura/borracha (style_panel.py) com a escolha atual destacada."""
    if layout is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PANEL)
    painter.drawRoundedRect(_q(layout.panel), button * 0.25, button * 0.25)
    font = QFont()
    font.setPixelSize(max(11, int(button * 0.17)))
    font.setBold(True)
    painter.setFont(font)
    current = QColor(style.color)
    for (kind, i), rect in layout.buttons:
        r = _q(rect)
        selected = i == {"color": style.color_index, "width": style.width_index,
                         "eraser": style.eraser_index}[kind]
        painter.setPen(QPen(SELECTED, 4) if selected else Qt.PenStyle.NoPen)
        if kind == "color":
            painter.setBrush(QColor(config.BRUSH_COLORS[i][1]))
            painter.drawEllipse(r.adjusted(4, 4, -4, -4))
            if selected:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#ffffff"), 3))
                painter.drawEllipse(r.adjusted(-2, -2, 2, 2))
        else:
            painter.setBrush(QColor(60, 207, 142, 60) if selected else BUTTON)
            painter.drawEllipse(r)
            c = QPointF(r.center().x(), r.y() + r.height() * 0.4)
            if kind == "width":
                pen = QPen(current, max(2.0, config.BRUSH_WIDTHS_FRAC[i] * model_height(button)))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(c - QPointF(r.width() * 0.25, 0), c + QPointF(r.width() * 0.25, 0))
                label = config.BRUSH_WIDTH_LABELS[i]
            else:
                radius = r.width() * (0.12, 0.2, 0.3)[i]
                painter.setBrush(QColor(255, 255, 255, 40))
                painter.setPen(QPen(ICON, 2, Qt.PenStyle.DashLine))
                painter.drawEllipse(c, radius, radius)
                label = config.ERASER_LABELS[i]
            painter.setPen(LABEL)
            painter.drawText(QRectF(r.x() - 6, r.y() + r.height() * 0.66, r.width() + 12, r.height() * 0.3),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        if (kind, i) == hover_key:
            _ring(painter, r, hover_progress, DWELL, max(4.0, button * 0.07))
    painter.restore()


def model_height(button: float) -> float:
    """Altura da lousa a partir do tamanho do botão (o botão é uma fração dela)."""
    return button / config.SIDEBAR_BUTTON_FRAC
