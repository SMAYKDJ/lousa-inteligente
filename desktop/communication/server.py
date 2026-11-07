"""Servidor do notebook: página do celular por HTTPS e WebSocket em /ws (D003).

Responsabilidades (CLAUDE.md §3.1, Comunicação):
- servir mobile/ ao celular;
- exigir o token de sessão na página e no WebSocket (D007);
- validar cada mensagem (message_protocol) e descartar dados antigos;
- validar quadros de câmera binários (frame_protocol, D013) e entregá-los
  a quem processa, sem decodificar a imagem;
- medir RTT com ping/pong de aplicação;
- avisar quem estiver ouvindo (ServerEvents) sobre conexão e dados recebidos.

Não conhece Qt nem coordenadas de tela. A interface recebe os eventos por
um ServerEvents (na etapa 1.3, uma ponte para sinais do Qt — D005).

Política de conexão: um celular por vez. Uma conexão nova substitui a
anterior, o que torna a reconexão do celular imediata mesmo que o notebook
ainda não tenha percebido a queda da conexão antiga. A conexão substituída é
fechada com o código WS_CLOSE_REPLACED, e o cliente que o recebe não reconecta
sozinho (evita dois aparelhos se derrubando em ciclo — ver docs/testing.md).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from aiohttp import WSMsgType, web

from desktop import config
from desktop.communication.clock_sync import ClockEstimate, ClockSync
from desktop.communication.frame_protocol import FrameMessage, parse_frame
from desktop.communication.message_protocol import (
    ErrorCode,
    HandTrackingMessage,
    HelloMessage,
    PingMessage,
    PongMessage,
    ProtocolError,
    SequenceGate,
    StatusMessage,
    make_error,
    make_ping,
    make_pong,
    make_welcome,
    parse_message,
)

log = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Estado da conexão visto pelo notebook (CLAUDE.md §8)."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"


class CloseReason(str, Enum):
    CLIENT_CLOSED = "client_closed"
    HELLO_TIMEOUT = "hello_timeout"
    HELLO_EXPECTED = "hello_expected"
    TOO_MANY_INVALID = "too_many_invalid"
    REPLACED = "replaced"
    SERVER_SHUTDOWN = "server_shutdown"


class ServerEvents:
    """Interface de eventos do servidor. Implementações sobrescrevem o que usam.

    Os métodos são chamados na thread do laço asyncio do servidor.
    """

    def on_connection_state(self, state: ConnectionState, detail: str) -> None: ...

    def on_hello(self, hello: HelloMessage) -> None: ...

    def on_hand_tracking(self, message: HandTrackingMessage) -> None: ...

    def on_status(self, status: StatusMessage) -> None: ...

    def on_rtt(self, rtt_ms: float) -> None: ...

    def on_invalid_message(self, error: ProtocolError) -> None: ...

    def on_frame(self, frame: FrameMessage) -> None:
        """Quadro de câmera válido e mais novo que o anterior (D013)."""

    def on_clock_sync(self, estimate: ClockEstimate) -> None:
        """Nova estimativa da diferença entre os relógios (para medir latência)."""


@dataclass
class ServerSettings:
    token: str
    mobile_dir: Path = config.MOBILE_DIR
    hello_timeout_s: float = config.HELLO_TIMEOUT_S
    max_invalid_messages: int = config.MAX_INVALID_MESSAGES
    ping_interval_s: float = config.PING_INTERVAL_S
    heartbeat_s: float = config.WS_HEARTBEAT_S


def new_session_token() -> str:
    return secrets.token_urlsafe(config.SESSION_TOKEN_BYTES)


def _monotonic_ms() -> float:
    return time.monotonic() * 1000.0


@dataclass
class _Connection:
    """Estado de uma conexão de celular."""

    ws: web.WebSocketResponse
    session_id: str
    gate: SequenceGate = field(default_factory=SequenceGate)
    frame_gate: SequenceGate = field(default_factory=SequenceGate)
    clock: ClockSync = field(default_factory=ClockSync)
    invalid_count: int = 0
    next_ping_id: int = 0
    close_reason: CloseReason = CloseReason.CLIENT_CLOSED


_SETTINGS_KEY = web.AppKey("settings", ServerSettings)
_EVENTS_KEY = web.AppKey("events", ServerEvents)
_STATE_KEY = web.AppKey("state", dict)


def _token_ok(request: web.Request) -> bool:
    supplied = request.query.get("token", "")
    expected = request.app[_SETTINGS_KEY].token
    return secrets.compare_digest(supplied.encode(), expected.encode())


async def _index(request: web.Request) -> web.StreamResponse:
    if not _token_ok(request):
        raise web.HTTPForbidden(text="Token de sessão ausente ou inválido.")
    index = request.app[_SETTINGS_KEY].mobile_dir / "index.html"
    return web.FileResponse(index, headers={"Cache-Control": "no-store"})


async def _send_pings(conn: _Connection, interval_s: float) -> None:
    while not conn.ws.closed:
        await asyncio.sleep(interval_s)
        if conn.ws.closed:
            break
        conn.next_ping_id += 1
        await conn.ws.send_str(make_ping(conn.next_ping_id, _monotonic_ms()))


async def _reject(conn: _Connection, error: ProtocolError, events: ServerEvents) -> None:
    conn.invalid_count += 1
    events.on_invalid_message(error)
    log.warning("Mensagem rejeitada (%s): %s", error.code.value, error.detail)
    await conn.ws.send_str(make_error(error))


async def _handle_message(
    conn: _Connection, raw: str, settings: ServerSettings, events: ServerEvents
) -> None:
    try:
        message = parse_message(raw)
    except ProtocolError as error:
        await _reject(conn, error, events)
        return

    if isinstance(message, HandTrackingMessage):
        if conn.gate.accept(message.seq):
            events.on_hand_tracking(message)
    elif isinstance(message, PingMessage):
        await conn.ws.send_str(make_pong(message))
    elif isinstance(message, PongMessage):
        now = _monotonic_ms()
        events.on_rtt(now - message.t_sender_ms)
        if message.t_reply_ms is not None:
            conn.clock.add_sample(message.t_sender_ms, message.t_reply_ms, now)
            events.on_clock_sync(conn.clock.estimate)
    elif isinstance(message, StatusMessage):
        events.on_status(message)
    elif isinstance(message, HelloMessage):
        await _reject(
            conn, ProtocolError(ErrorCode.INVALID_MESSAGE, "hello repetido"), events
        )


async def _handle_frame(conn: _Connection, raw: bytes, events: ServerEvents) -> None:
    try:
        frame = parse_frame(raw)
    except ProtocolError as error:
        await _reject(conn, error, events)
        return
    if conn.frame_gate.accept(frame.seq):
        events.on_frame(dataclasses.replace(
            frame, received_ms=_monotonic_ms(),
            capture_ms=conn.clock.to_local_ms(frame.t_client_ms)))


async def _wait_for_hello(
    conn: _Connection, settings: ServerSettings
) -> HelloMessage | None:
    """Primeira mensagem deve ser `hello`. Devolve None e define o motivo se não for."""
    try:
        first = await conn.ws.receive(timeout=settings.hello_timeout_s)
    except asyncio.TimeoutError:
        conn.close_reason = CloseReason.HELLO_TIMEOUT
        return None

    if first.type != WSMsgType.TEXT:
        conn.close_reason = CloseReason.CLIENT_CLOSED
        return None

    try:
        message = parse_message(first.data)
    except ProtocolError as error:
        await conn.ws.send_str(make_error(error))
        conn.close_reason = CloseReason.HELLO_EXPECTED
        return None

    if not isinstance(message, HelloMessage):
        await conn.ws.send_str(
            make_error(ProtocolError(ErrorCode.INVALID_MESSAGE, "primeira mensagem deve ser hello"))
        )
        conn.close_reason = CloseReason.HELLO_EXPECTED
        return None
    return message


async def _websocket(request: web.Request) -> web.StreamResponse:
    if not _token_ok(request):
        raise web.HTTPForbidden(text="Token de sessão ausente ou inválido.")

    settings = request.app[_SETTINGS_KEY]
    events = request.app[_EVENTS_KEY]
    state = request.app[_STATE_KEY]

    ws = web.WebSocketResponse(
        # Folga acima do limite: o tamanho é validado em parse_frame, que
        # responde com erro em vez de derrubar a conexão.
        heartbeat=settings.heartbeat_s, max_msg_size=config.MAX_FRAME_BYTES * 2
    )
    await ws.prepare(request)
    conn = _Connection(ws=ws, session_id=secrets.token_hex(4))
    peer = request.remote or "?"

    hello = await _wait_for_hello(conn, settings)
    if hello is None:
        log.info("Conexão de %s recusada: %s", peer, conn.close_reason.value)
        await ws.close()
        return ws

    # A nova conexão vira a ativa ANTES de fechar a anterior: assim o
    # encerramento da anterior não gera um "desconectado" falso.
    previous: _Connection | None = state.get("active")
    state["active"] = conn
    if previous is not None and not previous.ws.closed:
        previous.close_reason = CloseReason.REPLACED
        await previous.ws.close(code=config.WS_CLOSE_REPLACED, message=b"replaced")

    await ws.send_str(make_welcome(conn.session_id))
    events.on_hello(hello)
    events.on_connection_state(ConnectionState.CONNECTED, f"{peer} (sessão {conn.session_id})")
    log.info("Celular conectado: %s, %s %s", peer, hello.client, hello.client_version)

    pinger = asyncio.create_task(_send_pings(conn, settings.ping_interval_s))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await _handle_message(conn, msg.data, settings, events)
            elif msg.type == WSMsgType.BINARY:
                await _handle_frame(conn, msg.data, events)
            if conn.invalid_count >= settings.max_invalid_messages:
                conn.close_reason = CloseReason.TOO_MANY_INVALID
                await ws.close()
                break
    finally:
        pinger.cancel()
        if state.get("active") is conn:
            state["active"] = None
            events.on_connection_state(ConnectionState.DISCONNECTED, conn.close_reason.value)
        log.info("Conexão %s encerrada: %s", conn.session_id, conn.close_reason.value)
    return ws


async def _close_active(app: web.Application) -> None:
    active: _Connection | None = app[_STATE_KEY].get("active")
    if active is not None and not active.ws.closed:
        active.close_reason = CloseReason.SERVER_SHUTDOWN
        await active.ws.close()


def create_app(settings: ServerSettings, events: ServerEvents | None = None) -> web.Application:
    app = web.Application()
    app[_SETTINGS_KEY] = settings
    app[_EVENTS_KEY] = events or ServerEvents()
    app[_STATE_KEY] = {"active": None}

    app.router.add_get("/", _index)
    app.router.add_get("/ws", _websocket)
    # Arquivos públicos (scripts, MediaPipe). Não dão controle sobre o
    # notebook: os comandos só passam pelo /ws, que exige o token.
    app.router.add_static("/static", settings.mobile_dir, follow_symlinks=False)
    app.on_shutdown.append(_close_active)
    return app
