"""Ponte entre o servidor (thread asyncio) e a interface Qt (thread principal) — D005.

O servidor chama os métodos de ServerEvents na thread dele. Esta classe só
reemite cada evento como sinal do Qt. Como o objeto vive na thread principal,
o Qt entrega os sinais enfileirados para a thread da interface: nenhum estado
é compartilhado diretamente entre as threads.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from desktop.communication.message_protocol import (
    HandTrackingMessage,
    HelloMessage,
    ProtocolError,
    StatusMessage,
)
from desktop.communication.server import ConnectionState, ServerEvents
from desktop.vision.frame_processor import VisionEvents, VisionState, VisionStats


class QtServerBridge(QObject):
    connection_changed = Signal(object, str)  # ConnectionState, detalhe
    hello_received = Signal(object)  # HelloMessage
    hand_tracking_received = Signal(object)  # HandTrackingMessage
    status_received = Signal(object)  # StatusMessage
    rtt_measured = Signal(float)
    invalid_message = Signal(str)
    vision_state_changed = Signal(object, str)  # VisionState, detalhe
    vision_stats_received = Signal(object)  # VisionStats
    markers_detected = Signal(object)  # dict id → cantos em camera_norm (D015)
    scene_moved = Signal(object)  # SceneShift (D030)

    def events(self) -> ServerEvents:
        """Objeto ServerEvents a ser passado ao servidor."""
        return _BridgeEvents(self)


class _BridgeEvents(ServerEvents, VisionEvents):
    def __init__(self, bridge: QtServerBridge) -> None:
        self._bridge = bridge

    def on_connection_state(self, state: ConnectionState, detail: str) -> None:
        self._bridge.connection_changed.emit(state, detail)

    def on_hello(self, hello: HelloMessage) -> None:
        self._bridge.hello_received.emit(hello)

    def on_hand_tracking(self, message: HandTrackingMessage) -> None:
        self._bridge.hand_tracking_received.emit(message)

    def on_status(self, status: StatusMessage) -> None:
        self._bridge.status_received.emit(status)

    def on_rtt(self, rtt_ms: float) -> None:
        self._bridge.rtt_measured.emit(rtt_ms)

    def on_invalid_message(self, error: ProtocolError) -> None:
        self._bridge.invalid_message.emit(f"{error.code.value}: {error.detail}")

    def on_vision_state(self, state: VisionState, detail: str) -> None:
        self._bridge.vision_state_changed.emit(state, detail)

    def on_vision_stats(self, stats: VisionStats) -> None:
        self._bridge.vision_stats_received.emit(stats)

    def on_markers(self, observation, image_width, image_height) -> None:
        self._bridge.markers_detected.emit(observation)

    def on_scene_motion(self, shift) -> None:
        self._bridge.scene_moved.emit(shift)
