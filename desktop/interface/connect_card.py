"""Cartão "Conecte o celular" com QR code (abrir com dois cliques, D025).

Enquanto nenhum celular está conectado, a lousa mostra o endereço de acesso e um
QR code: basta apontar a câmera do celular para a TV/projeção, sem digitar o
endereço nem o token. Some quando o celular conecta.

O QR é gerado com segno (BSD-3, Python puro, sem dependências; requirements.txt).
Sem segno, o cartão mostra só o endereço.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

BACKGROUND = QColor(10, 14, 20, 235)
TEXT = QColor("#f4f6f8")
MUTED = QColor("#9aa4b2")
ACCENT = QColor("#f0b429")


def qr_matrix(url: str) -> list[list[bool]] | None:
    """Módulos do QR (True = escuro), ou None se o segno não estiver instalado."""
    try:
        import segno
    except ImportError:
        return None
    code = segno.make(url, error="m", micro=False)
    return [[bool(v) for v in row] for row in code.matrix]


def draw_connect_card(painter: QPainter, url: str, matrix: list[list[bool]] | None,
                      width: float, height: float) -> None:
    painter.save()
    painter.fillRect(QRectF(0, 0, width, height), BACKGROUND)
    unit = height / 1080
    font = QFont()
    font.setBold(True)
    font.setPointSizeF(max(10.0, 34 * unit * 1.35))
    painter.setFont(font)
    painter.setPen(TEXT)
    painter.drawText(QRectF(0, height * 0.06, width, 70 * unit), Qt.AlignmentFlag.AlignCenter, "Conecte o celular")

    top = height * 0.06 + 90 * unit
    if matrix:
        n = len(matrix)
        quiet = 4  # margem branca exigida pelo padrão do QR
        side = min(height * 0.52, width * 0.4)
        cell = side / (n + 2 * quiet)
        x0 = (width - side) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(x0, top, side, side), 12 * unit, 12 * unit)
        painter.setBrush(QColor("#000000"))
        for r, row in enumerate(matrix):
            for c, dark in enumerate(row):
                if dark:
                    painter.drawRect(QRectF(x0 + (quiet + c) * cell, top + (quiet + r) * cell, cell + 0.5, cell + 0.5))
        top += side + 24 * unit
        lines = [("Aponte a câmera do celular para o código e toque no link.", TEXT, 20),
                 ("Na 1ª vez: \"Avançado\" → \"Ir para … (não seguro)\". Mesma rede Wi-Fi do notebook.", MUTED, 15)]
    else:
        top += 40 * unit
        lines = [("Digite este endereço no navegador do celular (mesma rede Wi-Fi):", TEXT, 20),
                 ("Para ver o QR code: instale o segno (o ícone de dois cliques instala sozinho).", MUTED, 15)]
    font.setBold(False)
    for text, color, size in lines:
        font.setPointSizeF(max(9.0, size * unit * 1.35))
        painter.setFont(font)
        painter.setPen(color)
        h = painter.fontMetrics().height() + 10 * unit
        painter.drawText(QRectF(0, top, width, h), Qt.AlignmentFlag.AlignCenter, text)
        top += h
    font.setBold(True)
    font.setPointSizeF(max(9.0, 17 * unit * 1.35))
    painter.setFont(font)
    painter.setPen(ACCENT)
    painter.drawText(QRectF(0, top + 6 * unit, width, painter.fontMetrics().height() + 8),
                     Qt.AlignmentFlag.AlignCenter, url)
    painter.restore()
