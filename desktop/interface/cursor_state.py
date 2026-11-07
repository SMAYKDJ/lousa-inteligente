"""Estado da janela do cursor, sem dependência do Qt.

Separado do widget para ser testável sem interface gráfica (CLAUDE.md §9.1).
O widget (cursor_window.py) só desenha o que este estado diz.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from desktop.communication.message_protocol import (
    HandTrackingMessage,
    HelloMessage,
    StatusMessage,
)
from desktop.communication.server import ConnectionState
from desktop.core.coordinate_mapper import CameraNormPoint
from desktop.vision.frame_processor import VisionState, VisionStats

#: Janela de tempo usada para calcular mensagens por segundo.
RATE_WINDOW_S = 1.0


@dataclass
class CursorState:
    """O que a janela precisa saber para desenhar o cursor e o painel."""

    clock: Callable[[], float] = time.monotonic

    connection: ConnectionState = ConnectionState.DISCONNECTED
    connection_detail: str = ""
    camera: str = "—"
    phone_fps: float | None = None
    tracking_state: str = "—"
    rtt_ms: float | None = None
    last_seq: int | None = None
    phone_mode: str = "—"

    #: Visão computacional no notebook (D013).
    vision_state: str = "—"
    vision_detail: str = ""
    vision: VisionStats | None = None

    #: Última posição da ponta do indicador; None quando não há mão.
    tip: CameraNormPoint | None = None

    _arrivals: deque = field(default_factory=deque)

    # --- eventos -------------------------------------------------------------

    def on_connection(self, state: ConnectionState, detail: str) -> None:
        self.connection = state
        self.connection_detail = detail
        if state is ConnectionState.DISCONNECTED:
            # Nada da sessão anterior continua na tela como se fosse atual.
            self.tip = None
            self.phone_fps = None
            self.tracking_state = "—"
            self.rtt_ms = None
            self.camera = "—"
            self.phone_mode = "—"
            self.vision = None
            self._arrivals.clear()

    def on_hello(self, hello: HelloMessage) -> None:
        cam = hello.camera
        self.camera = f"{cam.width}×{cam.height} ({cam.facing.value})"

    def on_hand_tracking(self, message: HandTrackingMessage) -> None:
        self._arrivals.append(self.clock())
        self.last_seq = message.seq
        hand = message.hand
        if hand.present and hand.index_tip is not None:
            self.tip = CameraNormPoint(hand.index_tip.x, hand.index_tip.y)
        else:
            self.tip = None

    def on_status(self, status: StatusMessage) -> None:
        self.phone_fps = status.fps
        self.tracking_state = status.tracking_state.value
        if status.mode is not None:
            self.phone_mode = status.mode.value

    def on_rtt(self, rtt_ms: float) -> None:
        self.rtt_ms = rtt_ms

    def on_vision_state(self, state: VisionState, detail: str) -> None:
        self.vision_state = state.value
        self.vision_detail = detail

    def on_vision_stats(self, stats: VisionStats) -> None:
        self.vision = stats

    def vision_summary(self) -> str:
        """Linha do painel sobre o MediaPipe no notebook."""
        if self.vision_state != VisionState.READY.value:
            return f"{self.vision_state} {self.vision_detail}".strip()
        v = self.vision
        if v is None:
            return f"pronto ({self.vision_detail}) · sem quadros"
        ms = "—" if v.inference_ms is None else f"{v.inference_ms:.0f} ms"
        size = f" · {v.width}×{v.height}" if v.width else ""
        return f"{v.fps:.1f} q/s · {ms} · descartados {v.dropped}{size}"

    # --- métricas ------------------------------------------------------------

    def messages_per_second(self) -> float:
        """Mensagens hand_tracking recebidas no último segundo."""
        now = self.clock()
        while self._arrivals and now - self._arrivals[0] > RATE_WINDOW_S:
            self._arrivals.popleft()
        return len(self._arrivals) / RATE_WINDOW_S
