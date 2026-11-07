"""Exportar as anotações em PDF (etapa 6.3, D027): uma página por slide anotado.

Fundo branco, proporção da lousa, número do slide no rodapé. Só as anotações:
o slide em si fica na apresentação original (não capturamos a tela).
Usa o QPdfWriter do Qt (já é dependência; sem biblioteca nova).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter

from desktop.interface import drawing_view
from desktop.presentation.slides import SlideBook


def export_pdf(book: SlideBook, path: Path, aspect: float = 16 / 9, title: str = "") -> int:
    """Grava o PDF e devolve quantas páginas (slides anotados) foram exportadas."""
    slides = [(i, b) for i, b in sorted(book._boards.items()) if b.items]
    if not slides:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    width_mm = 297.0
    writer.setPageSize(QPageSize(QSizeF(width_mm, width_mm / aspect), QPageSize.Unit.Millimeter))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setResolution(150)
    writer.setTitle(title or "Anotações da lousa")
    writer.setCreator("SmartBoard Classroom")
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for page, (index, board) in enumerate(slides):
        if page:
            writer.newPage()
        rect = painter.viewport()
        w, h = float(rect.width()), float(rect.height())
        painter.fillRect(QRectF(0, 0, w, h), QColor("#ffffff"))
        drawing_view.draw_board(painter, board.items, None, w, h)
        font = QFont()
        font.setPixelSize(max(10, int(h * 0.022)))
        painter.setFont(font)
        painter.setPen(QColor("#8a8f98"))
        painter.drawText(QRectF(0, h * 0.95, w * 0.98, h * 0.04),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"Slide {index + 1}  ·  {title}".rstrip(" ·"))
    painter.end()
    return len(slides)
