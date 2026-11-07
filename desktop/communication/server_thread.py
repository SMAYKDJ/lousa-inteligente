"""Servidor aiohttp rodando numa thread própria (D005).

A interface Qt ocupa a thread principal. O servidor roda num laço asyncio
nesta thread, e os eventos chegam à interface por sinais do Qt (qt_bridge).
Este módulo não conhece Qt.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import threading

from aiohttp import web

log = logging.getLogger(__name__)

#: Tempo máximo esperando o servidor subir ou parar (s).
START_STOP_TIMEOUT_S = 10.0


class ServerThread(threading.Thread):
    def __init__(
        self,
        app: web.Application,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None,
    ) -> None:
        super().__init__(name="smartboard-server", daemon=True)
        self._app = app
        self._host = host
        self._port = port
        self._ssl = ssl_context
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        # Não usar "_started": é um atributo interno de threading.Thread.
        self._ready = threading.Event()
        self.error: BaseException | None = None
        #: Porta realmente aberta (útil quando port=0 nos testes).
        self.bound_port: int | None = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # registrado para quem iniciou a thread
            self.error = exc
            log.exception("Servidor encerrado com erro")
        finally:
            self._ready.set()
            self._loop.close()

    async def _serve(self) -> None:
        self._stop_event = asyncio.Event()
        runner = web.AppRunner(self._app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port, ssl_context=self._ssl)
        try:
            await site.start()
            sockets = runner.addresses
            self.bound_port = sockets[0][1] if sockets else self._port
            self._ready.set()
            await self._stop_event.wait()
        finally:
            await runner.cleanup()

    def wait_started(self, timeout: float = START_STOP_TIMEOUT_S) -> None:
        """Bloqueia até o servidor aceitar conexões. Repassa erro de inicialização."""
        if not self._ready.wait(timeout):
            raise TimeoutError("o servidor não iniciou a tempo")
        if self.error is not None:
            raise RuntimeError(f"o servidor não iniciou: {self.error}") from self.error

    def stop(self, timeout: float = START_STOP_TIMEOUT_S) -> None:
        if self._loop is not None and self._stop_event is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.join(timeout)
