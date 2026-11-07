"""Malha virtual sobre a lousa (tecla M): coordenadas X/Y e a correção dos 9 pontos.

Diagnóstico de precisão. A malha não muda a precisão: mostra onde o sistema
põe o dedo, em células de tamanho fixo, para comparar com o que se vê na lousa.
- X de 0 a 100 na largura; Y de 0 até o valor que mantém as células quadradas.
- Linhas a cada célula (fracas) e a cada 10 (fortes, com número).
- Cruz e coordenadas na posição do dedo.
- Setas da correção residual nos 9 pontos do teste G (em tamanho real).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from desktop import config

MINOR = QColor(0, 150, 255, 45)
MAJOR = QColor(0, 150, 255, 140)
LABEL = QColor(0, 110, 220, 230)
FINGER = QColor("#ff006e")
ARROW = QColor("#ff9f1c")


def grid_rows(width: float, height: float) -> int:
    return max(1, round(config.GRID_COLUMNS * height / max(width, 1)))


def grid_coords(x_px: float, y_px: float, width: float, height: float) -> tuple[float, float]:
    """ui_px → coordenadas da malha (X 0–100, Y 0–linhas)."""
    return (x_px / width * config.GRID_COLUMNS, y_px / height * grid_rows(width, height))


def _fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def draw_grid(painter: QPainter, width: float, height: float,
              finger: tuple[float, float] | None, residual=None) -> None:
    cols, rows = config.GRID_COLUMNS, grid_rows(width, height)
    painter.save()
    font = QFont()
    font.setPixelSize(max(11, int(height * 0.014)))
    font.setBold(True)
    painter.setFont(font)
    for i in range(cols + 1):
        x = width * i / cols
        major = i % config.GRID_MAJOR_EVERY == 0
        painter.setPen(QPen(MAJOR if major else MINOR, 2 if major else 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, height))
        if major and 0 < i < cols:
            painter.setPen(LABEL)
            painter.drawText(QRectF(x + 3, height * 0.5 + 2, 60, 20), Qt.AlignmentFlag.AlignLeft, str(i))
    for j in range(rows + 1):
        y = height * j / rows
        major = j % config.GRID_MAJOR_EVERY == 0
        painter.setPen(QPen(MAJOR if major else MINOR, 2 if major else 1))
        painter.drawLine(QPointF(0, y), QPointF(width, y))
        if major and 0 < j < rows:
            painter.setPen(LABEL)
            painter.drawText(QRectF(width * 0.5 + 3, y + 2, 60, 20), Qt.AlignmentFlag.AlignLeft, str(j))

    if residual is not None:
        painter.setPen(QPen(ARROW, 3))
        for x, y, dx, dy in residual.nodes():
            a = QPointF(x * width, y * height)
            b = QPointF((x + dx) * width, (y + dy) * height)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(a, 6, 6)
            painter.drawLine(a, b)
            painter.setBrush(ARROW)
            painter.drawEllipse(b, 4, 4)

    if finger is not None:
        fx, fy = finger
        painter.setPen(QPen(FINGER, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(fx, 0), QPointF(fx, height))
        painter.drawLine(QPointF(0, fy), QPointF(width, fy))
        gx, gy = grid_coords(fx, fy, width, height)
        text = f"X {_fmt(gx)} · Y {_fmt(gy)}"
        big = QFont(font)
        big.setPixelSize(max(16, int(height * 0.026)))
        painter.setFont(big)
        box = QRectF(fx + 14, fy + 14, big.pixelSize() * 10, big.pixelSize() * 1.8)
        if box.right() > width:
            box.moveRight(fx - 14)
        if box.bottom() > height:
            box.moveBottom(fy - 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 200))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
