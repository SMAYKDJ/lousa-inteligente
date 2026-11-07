"""Abrir com dois cliques (D025): tela automática, QR code, cartão "Conecte o celular"."""

import os
import subprocess
from pathlib import Path

import pytest

from desktop.main import parse_args, resolve_screen

ROOT = Path(__file__).resolve().parents[1]
URL = "https://192.168.1.74:8443/?token=ro1zG63DgCYcITTAFKhmsw"


def test_screen_auto_picks_tv_when_present():
    assert resolve_screen(["notebook", "tv"], "auto") == 1
    assert resolve_screen(["notebook"], "auto") == 0
    assert resolve_screen(["notebook", "tv"], 0) == 0 and resolve_screen([], None) is None
    assert parse_args(["--screen", "auto"]).screen == "auto" and parse_args(["--screen", "1"]).screen == 1
    with pytest.raises(SystemExit):
        parse_args(["--screen", "tv"])


def test_qr_encodes_the_url():
    """O QR desenhado decodifica de volta para o endereço (lido com o OpenCV do projeto)."""
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from desktop.interface.connect_card import qr_matrix
    m = qr_matrix(URL)
    assert m is not None
    n, cell, quiet = len(m), 8, 4
    img = np.full(((n + 2 * quiet) * cell,) * 2, 255, np.uint8)
    for r, row in enumerate(m):
        for c, dark in enumerate(row):
            if dark:
                img[(quiet + r) * cell:(quiet + r + 1) * cell, (quiet + c) * cell:(quiet + c + 1) * cell] = 0
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert text == URL


def test_connect_card_until_phone_connects_and_guided_waits(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import cv2
    import numpy as np
    from PySide6.QtWidgets import QApplication

    from desktop import config
    from desktop.communication.server import ConnectionState
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge
    app = QApplication.instance() or QApplication([])

    class Clock:
        now = 10.0

        def __call__(self):
            return self.now
    clock = Clock()
    window = CursorWindow(QtServerBridge(), URL, clock=clock, connect_card=True)
    window.resize(1280, 720)
    assert window.waiting_for_phone
    window.start_guided_setup()
    for _ in range(int(config.GUIDED_INTRO_S * 3)):  # bem mais que o cartão do assistente
        clock.now += 0.5
        window._calibration_tick()
    assert window.guided.phase == "intro" and not window.calibration.active  # esperou o celular
    image = window.grab()
    shots = os.environ.get("CALIB_SHOTS_DIR") or str(tmp_path)
    image.save(os.path.join(shots, "conecte_o_celular.png"))
    # O QR na tela (como a câmera do celular veria) decodifica para o endereço:
    image.save(str(tmp_path / "card.png"))
    gray = cv2.imread(str(tmp_path / "card.png"), cv2.IMREAD_GRAYSCALE)
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(gray)
    assert text == URL
    window._on_connection(ConnectionState.CONNECTED, "")
    assert not window.waiting_for_phone
    clock.now += config.GUIDED_INTRO_S + 0.1
    window._calibration_tick()
    assert window.calibration.active  # conectou: o assistente segue
    window.close()
    window.deleteLater()
    app.processEvents()


def test_mac_launcher_is_valid_and_executable():
    script = ROOT / "SmartBoard.command"
    assert os.access(script, os.X_OK)
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    text = script.read_text()
    assert "--overlay --screen auto" in text and "requirements.txt" in text


def test_windows_launcher_uses_crlf_and_same_options():
    data = (ROOT / "SmartBoard.bat").read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    assert b"--overlay --screen auto" in data and b"py -3.11 -m venv" in data


def test_preview_window_shows_qr_while_phone_not_connected():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from desktop.interface.camera_preview import CameraPreviewWindow
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge

    app = QApplication.instance() or QApplication([])
    board = CursorWindow(QtServerBridge(), "https://192.168.1.74:8443/?token=abc", connect_card=True)

    class Proc:
        def latest_preview(self):
            return None

    preview = CameraPreviewWindow(Proc(), board)
    preview.resize(420, 760)
    img = preview.grab().toImage()
    # O QR (branco com módulos pretos) ocupa o meio da janela.
    whites = sum(img.pixelColor(x, y).lightness() > 240 for x in range(60, 360, 10) for y in range(120, 400, 10))
    blacks = sum(img.pixelColor(x, y).lightness() < 15 for x in range(60, 360, 10) for y in range(120, 400, 10))
    assert whites > 100 and blacks > 100
    board.connect_card = False  # conectado: volta a imagem da câmera
    img = preview.grab().toImage()
    whites = sum(img.pixelColor(x, y).lightness() > 240 for x in range(60, 360, 10) for y in range(120, 400, 10))
    assert whites < 20
    preview.close()
    board.close()
    app.processEvents()
