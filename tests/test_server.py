"""Testes do servidor (etapa 1.2), via cliente de teste do aiohttp.

Os testes usam HTTP/WS sem TLS: o TLS é coberto em test_tls.py, e a
combinação real (HTTPS + celular) só é validada no teste com o Android.
"""

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import WSMsgType

from desktop import config
from desktop.communication.frame_protocol import build_frame
from desktop.communication.message_protocol import ErrorCode
from desktop.communication.server import (
    ConnectionState,
    ServerEvents,
    ServerSettings,
    create_app,
)

TOKEN = "token-de-teste"

HELLO = {
    "type": "hello", "v": 0, "client": "mobile-web", "client_version": "0.1.0",
    "camera": {"width": 1280, "height": 720, "facing": "environment"},
}


def tracking(seq: int, x: float = 0.5) -> dict:
    return {
        "type": "hand_tracking", "v": 0, "seq": seq, "t_client_ms": 100.0 + seq,
        "hand": {"present": True, "handedness": "Right", "confidence": 0.9,
                 "index_tip": {"x": x, "y": 0.5, "z": 0.0}},
    }


class RecordingEvents(ServerEvents):
    def __init__(self) -> None:
        self.states: list[tuple[ConnectionState, str]] = []
        self.hellos = []
        self.tracking = []
        self.statuses = []
        self.rtts: list[float] = []
        self.invalid = []
        self.frames = []

    def on_frame(self, frame):
        self.frames.append(frame)

    def on_connection_state(self, state, detail):
        self.states.append((state, detail))

    def on_hello(self, hello):
        self.hellos.append(hello)

    def on_hand_tracking(self, message):
        self.tracking.append(message)

    def on_status(self, status):
        self.statuses.append(status)

    def on_rtt(self, rtt_ms):
        self.rtts.append(rtt_ms)

    def on_invalid_message(self, error):
        self.invalid.append(error)


@pytest.fixture
def mobile_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!DOCTYPE html><title>teste</title>", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "app.js").write_text("// app", encoding="utf-8")
    return tmp_path


@pytest.fixture
def events() -> RecordingEvents:
    return RecordingEvents()


@pytest.fixture
async def client(aiohttp_client, mobile_dir, events):
    settings = ServerSettings(
        token=TOKEN, mobile_dir=mobile_dir, hello_timeout_s=0.3,
        max_invalid_messages=3, ping_interval_s=0.05, heartbeat_s=5.0,
    )
    return await aiohttp_client(create_app(settings, events))


async def connect(client):
    ws = await client.ws_connect(f"/ws?token={TOKEN}")
    await ws.send_str(json.dumps(HELLO))
    welcome = await ws.receive_json(timeout=1)
    assert welcome["type"] == "welcome"
    return ws


async def receive_until(ws, msg_type: str, timeout: float = 1.0) -> dict:
    """Lê mensagens até chegar uma do tipo pedido (ignora pings do servidor)."""
    async def loop():
        while True:
            msg = await ws.receive()
            if msg.type != WSMsgType.TEXT:
                raise AssertionError(f"conexão encerrada: {msg.type}")
            data = json.loads(msg.data)
            if data["type"] == msg_type:
                return data
    return await asyncio.wait_for(loop(), timeout)


async def wait_for(condition, timeout: float = 1.0) -> None:
    async def loop():
        while not condition():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(loop(), timeout)


# --- Página e token ----------------------------------------------------------


@pytest.mark.parametrize("query", ["", "?token=", "?token=errado"])
async def test_index_requires_token(client, query):
    response = await client.get(f"/{query}")
    assert response.status == 403


async def test_index_with_token(client):
    response = await client.get(f"/?token={TOKEN}")
    assert response.status == 200
    assert "teste" in await response.text()
    assert response.headers["Cache-Control"] == "no-store"


async def test_static_files_are_public(client):
    response = await client.get("/static/scripts/app.js")
    assert response.status == 200


async def test_static_does_not_escape_mobile_dir(client):
    response = await client.get("/static/../../etc/passwd")
    assert response.status in (403, 404)


@pytest.mark.parametrize("query", ["", "?token=errado"])
async def test_websocket_requires_token(client, query):
    response = await client.get(f"/ws{query}")
    assert response.status == 403


# --- Handshake ---------------------------------------------------------------


async def test_hello_gets_welcome_and_reports_connected(client, events):
    ws = await connect(client)
    assert events.hellos[0].camera.width == 1280
    assert events.states[-1][0] is ConnectionState.CONNECTED
    await ws.close()
    await wait_for(lambda: events.states[-1][0] is ConnectionState.DISCONNECTED)


async def test_first_message_must_be_hello(client, events):
    ws = await client.ws_connect(f"/ws?token={TOKEN}")
    await ws.send_str(json.dumps(tracking(1)))
    error = await ws.receive_json(timeout=1)
    assert error["type"] == "error"
    assert (await ws.receive(timeout=1)).type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
    assert events.states == []


async def test_connection_without_hello_times_out(client, events):
    ws = await client.ws_connect(f"/ws?token={TOKEN}")
    msg = await ws.receive(timeout=2)
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
    assert events.states == []


# --- Mensagens durante a conexão --------------------------------------------


async def test_tracking_is_forwarded_and_old_seq_dropped(client, events):
    ws = await connect(client)
    for seq in (1, 2, 2, 1, 5):
        await ws.send_str(json.dumps(tracking(seq)))
    await wait_for(lambda: len(events.tracking) >= 3)
    await asyncio.sleep(0.05)
    assert [m.seq for m in events.tracking] == [1, 2, 5]
    await ws.close()


async def test_invalid_message_gets_error_and_connection_survives(client, events):
    ws = await connect(client)
    await ws.send_str(json.dumps(tracking(1, x=1.7)))
    error = await receive_until(ws, "error")
    assert error["code"] == ErrorCode.INVALID_MESSAGE.value
    await ws.send_str(json.dumps(tracking(2)))
    await wait_for(lambda: len(events.tracking) == 1)
    assert len(events.invalid) == 1
    await ws.close()


async def test_too_many_invalid_messages_closes_connection(client, events):
    ws = await connect(client)
    for _ in range(3):
        await ws.send_str("{nao e json")
    async def until_closed():
        while (await ws.receive()).type not in (WSMsgType.CLOSE, WSMsgType.CLOSED):
            pass
    await asyncio.wait_for(until_closed(), 1)
    await wait_for(lambda: events.states[-1] == (ConnectionState.DISCONNECTED, "too_many_invalid"))


JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


async def test_invalid_binary_message_is_rejected(client, events):
    ws = await connect(client)
    await ws.send_bytes(b"\x00\x01")
    error = await receive_until(ws, "error")
    assert "quadro" in error["detail"]
    assert events.frames == []
    await ws.close()


async def test_valid_frame_is_delivered(client, events):
    ws = await connect(client)
    await ws.send_bytes(build_frame(1, 50.0, JPEG))
    await wait_for(lambda: len(events.frames) == 1)
    assert events.frames[0].seq == 1 and events.frames[0].jpeg == JPEG
    await ws.close()


async def test_old_frames_are_dropped(client, events):
    ws = await connect(client)
    for seq in (5, 3, 6):
        await ws.send_bytes(build_frame(seq, float(seq), JPEG))
    await ws.send_str(json.dumps(tracking(1)))  # marca de que tudo acima chegou
    await wait_for(lambda: len(events.tracking) == 1)
    assert [f.seq for f in events.frames] == [5, 6]
    await ws.close()


async def test_oversized_frame_is_rejected_without_closing(client, events):
    ws = await connect(client)
    await ws.send_bytes(build_frame(1, 1.0, JPEG + b"x" * config.MAX_FRAME_BYTES))
    error = await receive_until(ws, "error")
    assert error["code"] == ErrorCode.MESSAGE_TOO_LARGE.value
    await ws.send_bytes(build_frame(2, 2.0, JPEG))
    await wait_for(lambda: len(events.frames) == 1)
    await ws.close()


async def test_ping_from_phone_gets_pong(client):
    ws = await connect(client)
    await ws.send_str(json.dumps({"type": "ping", "v": 0, "id": 9, "t_sender_ms": 123.0}))
    pong = await receive_until(ws, "pong")
    assert (pong["id"], pong["t_sender_ms"]) == (9, 123.0)
    await ws.close()


async def test_server_ping_measures_rtt(client, events):
    ws = await connect(client)
    ping = await receive_until(ws, "ping")
    await ws.send_str(json.dumps({"type": "pong", "v": 0, "id": ping["id"],
                                  "t_sender_ms": ping["t_sender_ms"]}))
    await wait_for(lambda: len(events.rtts) == 1)
    assert 0 <= events.rtts[0] < 1000
    await ws.close()


async def test_status_is_forwarded(client, events):
    ws = await connect(client)
    await ws.send_str(json.dumps({"type": "status", "v": 0, "fps": 0, "tracking_state": "inactive"}))
    await wait_for(lambda: len(events.statuses) == 1)
    await ws.close()


# --- Reconexão ---------------------------------------------------------------


async def test_new_connection_replaces_previous(client, events):
    first = await connect(client)
    second = await connect(client)

    msg = await first.receive(timeout=1)
    while msg.type == WSMsgType.TEXT:  # pings pendentes antes do fechamento
        msg = await first.receive(timeout=1)
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED)
    # Código próprio: o cliente substituído sabe que não deve reconectar sozinho.
    assert first.close_code == config.WS_CLOSE_REPLACED

    # A conexão nova continua funcionando e começa com seq próprio.
    await second.send_str(json.dumps(tracking(1)))
    await wait_for(lambda: len(events.tracking) == 1)
    # A troca não gerou nenhum "desconectado": o notebook seguiu conectado.
    assert [state for state, _ in events.states] == [ConnectionState.CONNECTED] * 2
    await second.close()


async def test_reconnect_after_disconnect(client, events):
    ws = await connect(client)
    await ws.send_str(json.dumps(tracking(100)))
    await ws.close()
    await wait_for(lambda: events.states[-1][0] is ConnectionState.DISCONNECTED)

    ws = await connect(client)
    await ws.send_str(json.dumps(tracking(1)))  # seq recomeça na nova conexão
    await wait_for(lambda: len(events.tracking) == 2)
    assert events.states[-1][0] is ConnectionState.CONNECTED
    await ws.close()


async def test_pong_with_reply_time_timestamps_frames(client, events):
    clock_events = []
    events.on_clock_sync = clock_events.append
    ws = await connect(client)
    ping = await receive_until(ws, "ping")
    await ws.send_str(json.dumps({"type": "pong", "v": 0, "id": ping["id"],
                                  "t_sender_ms": ping["t_sender_ms"], "t_reply_ms": 5.0}))
    await wait_for(lambda: clock_events)
    await ws.send_bytes(build_frame(1, 5.0, JPEG))
    await wait_for(lambda: events.frames)
    frame = events.frames[0]
    assert frame.received_ms is not None and frame.capture_ms is not None
    # O quadro foi "capturado" quando o celular respondeu o ping: antes da chegada.
    assert frame.capture_ms <= frame.received_ms
    await ws.close()


async def test_frames_without_clock_sync_have_no_capture_time(client, events):
    ws = await connect(client)
    await ws.send_bytes(build_frame(1, 5.0, JPEG))
    await wait_for(lambda: events.frames)
    assert events.frames[0].capture_ms is None and events.frames[0].received_ms is not None
    await ws.close()
