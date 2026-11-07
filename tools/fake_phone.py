"""Celular simulado — SÓ para desenvolvimento (CLAUDE.md §9.4).

Conecta ao notebook como o celular faria (WSS + token) e envia a ponta do
indicador percorrendo um círculo, com perdas de mão periódicas. Serve para
testar a janela do cursor sem câmera. NÃO valida o rastreamento real.

Forma mais simples (sem copiar token): o notebook já sobe com o simulador

    .venv/bin/python -m desktop.main --simulate

Ou separado, com o notebook rodando em outro terminal:

    .venv/bin/python -m tools.fake_phone "https://192.168.1.74:8443/?token=TOKEN-REAL"
"""

from __future__ import annotations

import argparse
import asyncio
import math
import ssl
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

PROTOCOL_VERSION = 0
CIRCLE_PERIOD_S = 4.0  # uma volta completa
CIRCLE_RADIUS = 0.35  # em camera_norm
HAND_LOST_EVERY_S = 6.0  # simula a mão saindo do quadro...
HAND_LOST_FOR_S = 1.0  # ...por este tempo


def websocket_url(page_url: str) -> str:
    parsed = urlparse(page_url)
    token = parse_qs(parsed.query).get("token", [""])[0]
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/ws?token={token}"


def tip_at(elapsed_s: float) -> tuple[float, float]:
    angle = 2 * math.pi * elapsed_s / CIRCLE_PERIOD_S
    return 0.5 + CIRCLE_RADIUS * math.cos(angle), 0.5 + CIRCLE_RADIUS * math.sin(angle)


def hand_visible(elapsed_s: float) -> bool:
    return (elapsed_s % HAND_LOST_EVERY_S) >= HAND_LOST_FOR_S


async def answer_pings(ws: aiohttp.ClientWebSocketResponse) -> None:
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        data = msg.json()
        if data.get("type") == "ping":
            await ws.send_json({"type": "pong", "v": PROTOCOL_VERSION,
                                "id": data["id"], "t_sender_ms": data["t_sender_ms"]})
        elif data.get("type") == "error":
            print(f"Notebook recusou uma mensagem: {data.get('code')} — {data.get('detail')}")


async def run(page_url: str, rate_hz: float, duration_s: float | None) -> None:
    # Certificado autoassinado do próprio notebook (D004): não há CA para verificar.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(websocket_url(page_url), ssl=ctx) as ws:
            await ws.send_json({"type": "hello", "v": PROTOCOL_VERSION, "client": "fake-phone",
                                "client_version": "0.1.0",
                                "camera": {"width": 1280, "height": 720, "facing": "unknown"}})
            welcome = await ws.receive_json(timeout=5)
            print(f"Conectado: sessão {welcome.get('session_id')} "
                  f"(limite anunciado {welcome.get('max_rate_hz')} msg/s)")

            pinger = asyncio.create_task(answer_pings(ws))
            start = time.monotonic()
            seq, was_visible, last_status = 0, None, 0.0
            try:
                while duration_s is None or time.monotonic() - start < duration_s:
                    elapsed = time.monotonic() - start
                    visible = hand_visible(elapsed)
                    t_ms = elapsed * 1000.0
                    if visible:
                        x, y = tip_at(elapsed)
                        seq += 1
                        await ws.send_json({
                            "type": "hand_tracking", "v": PROTOCOL_VERSION, "seq": seq,
                            "t_client_ms": t_ms, "inference_ms": 0.0,
                            "hand": {"present": True, "handedness": "Right", "confidence": 1.0,
                                     "index_tip": {"x": x, "y": y, "z": 0.0}},
                        })
                    elif was_visible is not False:  # envia "sem mão" uma única vez
                        seq += 1
                        await ws.send_json({"type": "hand_tracking", "v": PROTOCOL_VERSION,
                                            "seq": seq, "t_client_ms": t_ms,
                                            "hand": {"present": False}})
                    was_visible = visible

                    if elapsed - last_status >= 1.0:
                        await ws.send_json({"type": "status", "v": PROTOCOL_VERSION,
                                            "fps": rate_hz,
                                            "tracking_state": "tracking_active" if visible else "tracking_lost"})
                        last_status = elapsed
                    await asyncio.sleep(1.0 / rate_hz)
            finally:
                pinger.cancel()
            print(f"Encerrado: {seq} mensagens em {time.monotonic() - start:.1f} s")


async def run_with_friendly_errors(page_url: str, rate_hz: float, duration_s: float | None) -> bool:
    """Roda o simulador e traduz os erros comuns. Devolve True se terminou bem."""
    host = urlparse(page_url).netloc
    try:
        await run(page_url, rate_hz, duration_s)
        return True
    except aiohttp.WSServerHandshakeError as exc:
        if exc.status == 403:
            print("O notebook recusou o token (403). O token muda toda vez que o servidor "
                  "reinicia: copie a URL atual mostrada pelo notebook.")
        else:
            print(f"O notebook recusou a conexão (HTTP {exc.status}).")
    except aiohttp.ClientConnectorError:
        print(f"Não consegui conectar ao notebook em {host}. O servidor está rodando? "
              "Inicie com: .venv/bin/python -m desktop.main")
    except (aiohttp.ClientError, ConnectionError) as exc:
        print(f"Conexão com o notebook encerrada: {exc}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Celular simulado (desenvolvimento)")
    parser.add_argument("url", help="URL mostrada pelo notebook (https://IP:PORTA/?token=...)")
    parser.add_argument("--rate", type=float, default=30.0, help="mensagens por segundo")
    parser.add_argument("--duration", type=float, help="segundos (padrão: até Ctrl+C)")
    args = parser.parse_args()

    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or "token=" not in parsed.query:
        parser.error(
            f"URL inválida: {args.url!r}\n"
            "Use a URL completa mostrada pelo notebook, entre aspas, por exemplo:\n"
            '  "https://192.168.1.74:8443/?token=AbCdEf123"'
        )
    try:
        ok = asyncio.run(run_with_friendly_errors(args.url, args.rate, args.duration))
    except KeyboardInterrupt:
        ok = True
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
