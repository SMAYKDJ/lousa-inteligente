"""Integração da etapa 1.3: servidor em thread + TLS real + ponte Qt + janela.

Roda o Qt em modo "offscreen" (sem tela). Cobre o caminho completo do
notebook: WSS → servidor (thread) → sinal Qt → estado → posição do cursor.
É simulação: não substitui o teste com o celular (CLAUDE.md §9.4).
"""

import asyncio
import os
import ssl
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
import aiohttp  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.communication.server import ConnectionState, ServerSettings, create_app  # noqa: E402
from desktop.communication.server_thread import ServerThread  # noqa: E402
from desktop.communication.tls import build_ssl_context, ensure_certificate  # noqa: E402
from desktop.interface.cursor_window import CursorWindow  # noqa: E402
from desktop.interface.qt_bridge import QtServerBridge  # noqa: E402

TOKEN = "token-gui"


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def process_events_until(qt_app, condition, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condição não satisfeita a tempo")
        qt_app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def running(qt_app, tmp_path):
    bridge = QtServerBridge()
    window = CursorWindow(bridge, "https://127.0.0.1/?token=" + TOKEN)
    window.filter_enabled = False  # aqui se testa a conversão exata; o filtro tem testes próprios
    window.resize(1000, 500)
    cert = ensure_certificate("127.0.0.1", cert_dir=tmp_path)
    app = create_app(ServerSettings(token=TOKEN), bridge.events())
    server = ServerThread(app, "127.0.0.1", 0, build_ssl_context(cert))
    server.start()
    server.wait_started()
    yield window, server
    server.stop()
    assert not server.is_alive()
    # Destruição determinística dos objetos Qt. Sem isto, o coletor de lixo
    # do Python pode liberar o widget dentro do processEvents de outro teste.
    window.close()
    window.deleteLater()
    bridge.deleteLater()
    qt_app.processEvents()


def client_ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def phone_session(port: int, messages: list[dict], hold_s: float = 0.3) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"wss://127.0.0.1:{port}/ws?token={TOKEN}",
                                      ssl=client_ssl()) as ws:
            await ws.send_json({"type": "hello", "v": 0, "client": "teste", "client_version": "0",
                                "camera": {"width": 640, "height": 480, "facing": "unknown"}})
            assert (await ws.receive_json(timeout=2))["type"] == "welcome"
            for message in messages:
                await ws.send_json(message)
            await asyncio.sleep(hold_s)


def tracking(seq, x, y):
    return {"type": "hand_tracking", "v": 0, "seq": seq, "t_client_ms": float(seq),
            "hand": {"present": True, "handedness": "Right", "confidence": 0.9,
                     "index_tip": {"x": x, "y": y, "z": 0.0}}}


def test_server_thread_starts_and_stops(running):
    _, server = running
    assert server.is_alive()
    assert server.bound_port


def test_tracking_over_wss_moves_cursor_in_window(qt_app, running):
    window, server = running
    import threading

    phone = threading.Thread(target=asyncio.run, args=(phone_session(
        server.bound_port, [tracking(1, 0.1, 0.1), tracking(2, 0.75, 0.25)], hold_s=1.0),))
    phone.start()

    process_events_until(qt_app, lambda: window.state.last_seq == 2)
    assert window.state.connection is ConnectionState.CONNECTED
    pos = window.cursor_position()
    assert (round(pos.x()), round(pos.y())) == (750, 125)  # 0.75×1000, 0.25×500

    phone.join(5)
    process_events_until(qt_app, lambda: window.state.connection is ConnectionState.DISCONNECTED)
    assert window.cursor_position() is None


def test_window_renders_without_errors(qt_app, running):
    window, _ = running
    window.state.on_connection(ConnectionState.CONNECTED, "sessão teste")
    image = window.grab()
    assert not image.isNull()
    assert image.width() == window.width()
