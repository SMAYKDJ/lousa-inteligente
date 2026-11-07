"""Desenho da calibração na tela da lousa (D014, docs/calibration.md §2.1).

Só desenha o que a CalibrationView diz; não decide nada (a lógica fica em
desktop/calibration/calibration_state.py).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from desktop.calibration.calibration_state import CalibrationView, Phase

BACKGROUND = QColor("#05070a")
TARGET = QColor("#ffffff")
RING_BG = QColor("#2a313c")
RING = QColor("#f0b429")
RING_COLLECT = QColor("#3ccf8e")
DONE = QColor("#3ccf8e")
TEXT = QColor("#e8ecf1")
MUTED = QColor("#8a94a3")
ALERT = QColor("#ff5a5f")

TARGET_ARM_PX = 28
RING_RADIUS_PX = 46


def _to_px(target, width: float, height: float) -> QPointF:
    return QPointF(target.x * width, target.y * height)


def _draw_cross(painter: QPainter, center: QPointF, color: QColor, arm: float, width: int) -> None:
    painter.setPen(QPen(color, width))
    painter.drawLine(center + QPointF(-arm, 0), center + QPointF(arm, 0))
    painter.drawLine(center + QPointF(0, -arm), center + QPointF(0, arm))


def draw_calibration(painter: QPainter, view: CalibrationView, width: float, height: float,
                     prefix: str = "") -> None:
    """`prefix`: "Etapa 2 de 4 · " durante o assistente de calibração."""
    painter.fillRect(QRectF(0, 0, width, height), BACKGROUND)

    for done in view.captured:
        _draw_cross(painter, _to_px(done, width, height), DONE, TARGET_ARM_PX * 0.6, 3)

    if view.target is not None:
        center = _to_px(view.target, width, height)
        # O anel nunca passa da borda: o alvo fica a só 5% dela.
        room = min(center.x(), width - center.x(), center.y(), height - center.y())
        radius = max(16.0, min(RING_RADIUS_PX, room - 6))
        ring = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(RING_BG, 8))
        painter.drawEllipse(ring)
        painter.setPen(QPen(RING_COLLECT if view.collecting else RING, 8,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        # drawArc usa 1/16 de grau; começa no topo e anda no sentido horário.
        painter.drawArc(ring, 90 * 16, -int(view.progress * 360 * 16))
        _draw_cross(painter, center, TARGET, min(TARGET_ARM_PX, radius - 4), 3)

        # Número da contagem, deslocado para o centro da tela (não cobre o alvo).
        toward_x = 1 if view.target.x < 0.5 else -1
        toward_y = 1 if view.target.y < 0.5 else -1
        if abs(view.target.y - 0.5) < 0.2:  # linha do meio: número ao lado
            toward_x, toward_y = (1.3 if view.target.x <= 0.5 else -1.3), 0
        number_center = center + QPointF(toward_x * 110, toward_y * 90)
        font = QFont()
        font.setPointSize(48)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(RING_COLLECT if view.collecting else TEXT)
        painter.drawText(QRectF(number_center.x() - 70, number_center.y() - 45, 140, 90),
                         Qt.AlignmentFlag.AlignCenter, str(max(1, math.ceil(view.remaining_s))))

    _draw_instructions(painter, view, width, height, prefix)


def _draw_instructions(painter: QPainter, view: CalibrationView, width: float, height: float,
                       prefix: str = "") -> None:
    # Com o alvo no centro (verificação), o texto sobe para não cobri-lo.
    # Alvo perto do centro: o texto sobe para não cobri-lo.
    near_center = view.target is not None and abs(view.target.y - 0.5) < 0.2
    top = height * (0.19 if near_center else 0.34)
    box = QRectF(width * 0.08, top, width * 0.84, height * 0.3)
    font = QFont()
    font.setPointSize(22)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(TEXT)
    if view.title:
        title = view.title
    elif view.phase is Phase.VERIFY:
        title = "Verificação: encoste no alvo do centro"
    else:
        title = f"Calibrar a tela — canto {view.step} de 4 ({view.target_name})"
    painter.drawText(QRectF(box.left(), box.top(), box.width(), 44), Qt.AlignmentFlag.AlignCenter, prefix + title)

    font.setPointSize(15)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(MUTED)
    painter.drawText(QRectF(box.left(), box.top() + 50, box.width(), 30),
                     Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                     "Encoste a ponta do indicador no centro da cruz e mantenha até o tempo acabar.")
    painter.setPen(DONE if view.finger_seen else MUTED)
    painter.drawText(QRectF(box.left(), box.top() + 84, box.width(), 30), Qt.AlignmentFlag.AlignCenter,
                     "Dedo visto pela câmera ✓" if view.finger_seen else "Dedo não visto pela câmera")
    if view.message:
        painter.setPen(ALERT)
        painter.drawText(QRectF(box.left(), box.top() + 120, box.width(), 60),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, view.message)
    painter.setPen(MUTED)
    font.setPointSize(12)
    painter.setFont(font)
    # Rodapé no meio da borda inferior: longe dos alvos dos cantos e do centro.
    painter.drawText(QRectF(width * 0.3, height - 40, width * 0.4, 24), Qt.AlignmentFlag.AlignCenter,
                     "Esc cancela")


def draw_guided_card(painter: QPainter, view, width: float, height: float,
                     footer: str = "Esc cancela o assistente · A recomeça") -> None:
    """Cartão do assistente: instrução antes de cada etapa, ou o resumo final.

    Layout de cima para baixo, cada linha medida pela própria fonte (cabe em qualquer tela).
    """
    painter.fillRect(QRectF(0, 0, width, height), BACKGROUND)
    unit = height / 1080 * 1.0  # tamanhos pensados para 1080 linhas
    pad = 36 * unit
    rows = []  # (texto, tamanho em pt, negrito, cor, quebra de linha)
    if view.kind == "intro":
        rows.append((f"Etapa {view.step} de {view.total}", 18, True, MUTED, False))
        rows.append(("•dots", 0, False, None, False))
    rows.append((view.title, 34, True, TEXT, False))
    rows.append((view.text, 20, False, TEXT, True))
    if view.kind == "summary":
        for line in view.lines:
            bad = "piorou" in line or "não foi aplicada" in line
            rows.append((line, 19, not bad and line.startswith("Melhora"), ALERT if bad else TEXT, False))
    else:
        rows.append((str(max(1, math.ceil(view.seconds_left))), 48, True, RING, False))
    rows.append((footer, 13, False, MUTED, False))

    box_w = width * 0.64
    text_w = box_w - 2 * pad

    def font_for(size, bold):
        f = QFont()
        f.setPointSizeF(max(8.0, size * unit * 1.35))
        f.setBold(bold)
        return f

    heights = []
    for text, size, bold, _, wrap in rows:
        if text == "•dots":
            heights.append(30 * unit)
            continue
        painter.setFont(font_for(size, bold))
        flags = Qt.AlignmentFlag.AlignCenter | (Qt.TextFlag.TextWordWrap if wrap else Qt.AlignmentFlag(0))
        rect = painter.fontMetrics().boundingRect(QRectF(0, 0, text_w, 10_000).toRect(), int(flags), text)
        heights.append(rect.height() + 14 * unit)
    box_h = sum(heights) + 2 * pad
    box = QRectF((width - box_w) / 2, max(10.0, (height - box_h) / 2), box_w, box_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 18))
    painter.drawRoundedRect(box, 18, 18)

    y = box.top() + pad
    for (text, size, bold, color, wrap), h in zip(rows, heights):
        if text == "•dots":
            r, gap = 7 * unit + 2, 26 * unit + 6
            x0 = box.center().x() - (view.total - 1) * gap / 2
            for i in range(view.total):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(DONE if i < view.step - 1 else (RING if i == view.step - 1 else RING_BG))
                painter.drawEllipse(QPointF(x0 + i * gap, y + h / 2), r, r)
        else:
            painter.setFont(font_for(size, bold))
            painter.setPen(color)
            flags = Qt.AlignmentFlag.AlignCenter | (Qt.TextFlag.TextWordWrap if wrap else Qt.AlignmentFlag(0))
            painter.drawText(QRectF(box.left() + pad, y, text_w, h), flags, text)
        y += h
