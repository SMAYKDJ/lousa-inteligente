"""Desenho do estudo do toque (etapa 5.3, tecla T): alvo ou linha, instrução e contagem.

Só desenha o que `TouchView` diz (desktop/interaction/touch_study.py).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from desktop.interface.calibration_overlay import (
    ALERT, BACKGROUND, MUTED, RING, RING_BG, TARGET, TEXT, draw_guided_card)

#: Meia largura da linha de arrasto (fração da largura da lousa).
DRAG_HALF_WIDTH = 0.15


def draw_touch_study(painter: QPainter, view, width: float, height: float,
                     cursor: QPointF | None = None) -> None:
    if view.kind == "summary":
        draw_guided_card(painter, view, width, height, "Esc fecha · T repete o estudo")
        return
    painter.fillRect(QRectF(0, 0, width, height), BACKGROUND)
    unit = height / 1080
    recording = view.kind == "record"
    color = RING if not recording else TARGET
    center = QPointF(view.spot[0] * width, view.spot[1] * height)

    # Alvo (parado) ou linha (arrastar).
    if view.motion == "drag":
        half = DRAG_HALF_WIDTH * width
        painter.setPen(QPen(color, max(3.0, 6 * unit), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(center + QPointF(-half, 0), center + QPointF(half, 0))
        for end in (-half, half):
            painter.drawEllipse(center + QPointF(end, 0), 10 * unit, 10 * unit)
    else:
        painter.setPen(QPen(color, max(3.0, 5 * unit)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, 40 * unit, 40 * unit)
        arm = 24 * unit
        painter.drawLine(center + QPointF(-arm, 0), center + QPointF(arm, 0))
        painter.drawLine(center + QPointF(0, -arm), center + QPointF(0, arm))

    if cursor is not None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ALERT))
        painter.drawEllipse(cursor, 8 * unit, 8 * unit)

    # Faixa de instrução no alto (longe dos alvos: eles ficam entre 35% e 65% da altura).
    band = QRectF(0, 0, width, 210 * unit)
    painter.fillRect(band, QColor(255, 255, 255, 14))

    def font(size, bold=False):
        f = QFont()
        f.setPointSizeF(max(8.0, size * unit * 1.35))
        f.setBold(bold)
        return f

    painter.setPen(MUTED)
    painter.setFont(font(15))
    state = "● GRAVANDO" if recording else "Prepare a mão"
    painter.drawText(QRectF(30 * unit, 16 * unit, width - 60 * unit, 34 * unit),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     f"Estudo do toque · etapa {view.step} de {view.total}")
    painter.setPen(ALERT if recording else RING)
    painter.drawText(QRectF(30 * unit, 16 * unit, width - 60 * unit, 34 * unit),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, state)
    painter.setPen(TEXT)
    painter.setFont(font(28, True))
    painter.drawText(QRectF(30 * unit, 56 * unit, width - 60 * unit, 60 * unit),
                     Qt.AlignmentFlag.AlignCenter, view.title)
    painter.setPen(MUTED)
    painter.setFont(font(16))
    painter.drawText(QRectF(30 * unit, 118 * unit, width - 60 * unit, 80 * unit),
                     Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, view.text)

    # Contagem no canto inferior direito.
    painter.setPen(RING_BG)
    painter.setFont(font(40, True))
    painter.setPen(ALERT if recording else RING)
    painter.drawText(QRectF(width - 200 * unit, height - 110 * unit, 170 * unit, 90 * unit),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     str(max(1, math.ceil(view.seconds_left))))
    painter.setPen(MUTED)
    painter.setFont(font(12))
    painter.drawText(QRectF(30 * unit, height - 50 * unit, width - 260 * unit, 30 * unit),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Esc cancela o estudo")
