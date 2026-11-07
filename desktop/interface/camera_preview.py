"""Janela de diagnóstico: o que a câmera vê (Fase 2, D014).

Mostra, na tela do notebook (não na lousa), o último quadro processado com:
- a ponta do indicador detectada (vermelho);
- os cantos já capturados na calibração (verde, numerados);
- depois de calibrar, o contorno onde o sistema acha que está a área
  projetada (amarelo): a homografia inversa aplicada aos cantos da superfície;
- os marcadores ArUco detectados (azul, com o id) — D015.

Serve para posicionar a câmera e entender calibrações ruins. A imagem só
existe em memória e na tela; nunca é gravada (CLAUDE.md §11).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

REFRESH_MS = 100
TIP = QColor("#ff5a5f")
CORNER = QColor("#3ccf8e")
OUTLINE = QColor("#f0b429")
TEXT = QColor("#e8ecf1")
MARKER = QColor("#4cc9f0")
OTHER = QColor("#8a94a3")


class CameraPreviewWindow(QWidget):
    def __init__(self, processor, board_window) -> None:
        """`processor`: FrameProcessor (latest_preview). `board_window`: CursorWindow."""
        super().__init__()
        self._processor = processor
        self._board = board_window
        self._image: QImage | None = None
        self._hand = None
        self.setWindowTitle("SmartBoard — câmera (diagnóstico, não gravada) · teclas C, G, P, F, Q")
        self.resize(420, 760)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(REFRESH_MS)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        # No modo overlay a lousa ignora teclado e mouse (fica "transparente"):
        # as teclas de comando (A, C, G, V, E, H, K, L, M, O, R, S, P, Esc, Q) são digitadas aqui e repassadas.
        self._board.keyPressEvent(event)

    def _refresh(self) -> None:
        preview = self._processor.latest_preview()
        if preview is None:
            self._image, self._hand = None, None
        else:
            rgb, self._hand = preview
            rgb = np.ascontiguousarray(rgb)
            h, w = rgb.shape[:2]
            self._image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self.update()

    def _draw_qr(self, painter: QPainter, matrix, url: str) -> None:
        w, h = self.width(), self.height()
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(TEXT)
        painter.drawText(QRectF(0, 12, w, 34), Qt.AlignmentFlag.AlignCenter, "Conecte o celular")
        n, quiet = len(matrix), 4
        side = min(w - 24, h - 170)
        cell = side / (n + 2 * quiet)
        x0, y0 = (w - side) / 2, 56
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(QRectF(x0, y0, side, side))
        painter.setBrush(QColor("#000000"))
        for r, row in enumerate(matrix):
            for c, dark in enumerate(row):
                if dark:
                    painter.drawRect(QRectF(x0 + (quiet + c) * cell, y0 + (quiet + r) * cell, cell + 0.5, cell + 0.5))
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(TEXT)
        painter.drawText(QRectF(10, y0 + side + 10, w - 20, 40),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         "Aponte a câmera do celular para o código e toque no link (mesma rede Wi-Fi).")
        painter.drawText(QRectF(10, y0 + side + 52, w - 20, 60),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWrapAnywhere, url)

    def _image_rect(self) -> QRectF:
        img = self._image
        scale = min(self.width() / img.width(), (self.height() - 30) / img.height())
        w, h = img.width() * scale, img.height() * scale
        return QRectF((self.width() - w) / 2, 30 + (self.height() - 30 - h) / 2, w, h)

    @staticmethod
    def _to_px(rect: QRectF, x: float, y: float) -> QPointF:
        return QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height())

    def paintEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#05070a"))
        font = QFont()
        font.setPointSize(11)
        painter.setFont(font)
        painter.setPen(TEXT)
        if getattr(self._board, "waiting_for_phone", False) and getattr(self._board, "_qr", None):
            # Celular ainda não conectado: o QR aparece também aqui, na tela do notebook,
            # para quem não está vendo a lousa (TV/projetor) no momento.
            self._draw_qr(painter, self._board._qr, self._board._url)
            painter.end()
            return
        if self._image is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aguardando imagem da câmera…")
            painter.end()
            return
        rect = self._image_rect()
        painter.drawImage(rect, self._image)

        calibration = self._board.calibration
        mapper = getattr(self._board, "_mapper", None)
        homography = getattr(mapper, "homography", None)
        if homography is not None:
            inverse = np.linalg.inv(homography.matrix)
            poly = QPolygonF()
            for sx, sy in ((0, 0), (1, 0), (1, 1), (0, 1)):
                x, y, w = inverse @ np.array([sx, sy, 1.0])
                if w > 1e-9:
                    poly.append(self._to_px(rect, x / w, y / w))
            painter.setPen(QPen(OUTLINE, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

        for i, p in enumerate(calibration.captured_camera_points, start=1):
            pos = self._to_px(rect, p.x, p.y)
            painter.setPen(QPen(CORNER, 2))
            painter.drawEllipse(pos, 7, 7)
            painter.drawText(pos + QPointF(10, -8), str(i))

        painter.setPen(QPen(MARKER, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for marker_id, corners in getattr(self._board, "last_markers", {}).items():
            poly = QPolygonF([self._to_px(rect, p.x, p.y) for p in corners])
            painter.drawPolygon(poly)
            painter.drawText(poly.boundingRect().center() + QPointF(-4, 4), str(marker_id))

        # Todas as mãos vistas (cinza) e a escolhida para o cursor (vermelho).
        candidates = getattr(self._board, "last_candidates", ())
        for other in candidates:
            if other.index_tip is not None:
                painter.setPen(QPen(OTHER, 2))
                painter.drawEllipse(self._to_px(rect, other.index_tip.x, other.index_tip.y), 9, 9)
        chosen = getattr(getattr(self._board, "state", None), "tip", None)
        if chosen is None and self._hand is not None and self._hand.present:
            chosen = self._hand.index_tip
        if chosen is not None:
            painter.setPen(QPen(TIP, 3))
            painter.drawEllipse(self._to_px(rect, chosen.x, chosen.y), 9, 9)
        hand = self._hand

        painter.setPen(TEXT)
        status = "mão detectada" if hand is not None and hand.present else "sem mão"
        if len(candidates) >= 2:
            status = "2 mãos (vermelho = usada)"
        painter.drawText(QRectF(8, 4, self.width() - 16, 22), Qt.AlignmentFlag.AlignVCenter,
                         f"Câmera: {self._image.width()}×{self._image.height()} · {status}")
        painter.end()
