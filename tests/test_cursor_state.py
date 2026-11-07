"""Testes do estado da janela do cursor, sem Qt (etapa 1.3)."""

import json

import pytest

from desktop.communication.message_protocol import parse_message
from desktop.communication.server import ConnectionState
from desktop.core.coordinate_mapper import CameraNormPoint
from desktop.interface.cursor_state import CursorState


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def tracking(seq: int, x: float = 0.5, y: float = 0.5, present: bool = True):
    hand = ({"present": True, "handedness": "Right", "confidence": 0.9,
             "index_tip": {"x": x, "y": y, "z": 0.0}} if present else {"present": False})
    return parse_message(json.dumps({"type": "hand_tracking", "v": 0, "seq": seq,
                                     "t_client_ms": 1.0, "hand": hand}))


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def state(clock):
    return CursorState(clock=clock)


def test_starts_without_cursor(state):
    assert state.tip is None
    assert state.connection is ConnectionState.DISCONNECTED


def test_tracking_moves_cursor_and_hand_loss_hides_it(state):
    state.on_hand_tracking(tracking(1, x=0.2, y=0.8))
    assert state.tip == CameraNormPoint(0.2, 0.8)
    assert state.last_seq == 1
    state.on_hand_tracking(tracking(2, present=False))
    assert state.tip is None


def test_disconnect_clears_cursor_and_phone_metrics(state):
    state.on_connection(ConnectionState.CONNECTED, "sessão x")
    state.on_hand_tracking(tracking(1))
    state.on_status(parse_message('{"type":"status","v":0,"fps":24,"tracking_state":"tracking_active"}'))
    state.on_rtt(10.0)
    state.on_connection(ConnectionState.DISCONNECTED, "client_closed")
    assert state.tip is None
    assert state.phone_fps is None
    assert state.rtt_ms is None
    assert state.camera == "—"
    assert state.messages_per_second() == 0


def test_messages_per_second_uses_last_second_only(state, clock):
    for seq in range(30):  # 30 mensagens em 1 s
        state.on_hand_tracking(tracking(seq))
        clock.now += 1 / 30
    assert state.messages_per_second() == pytest.approx(30, abs=1)
    clock.now += 2.0  # 2 s sem mensagens
    assert state.messages_per_second() == 0


def test_hello_status_and_rtt_are_shown(state):
    state.on_hello(parse_message(json.dumps({
        "type": "hello", "v": 0, "client": "mobile-web", "client_version": "0.1.0",
        "camera": {"width": 720, "height": 1280, "facing": "environment"}})))
    state.on_status(parse_message('{"type":"status","v":0,"fps":24.5,"tracking_state":"hand_detected"}'))
    state.on_rtt(12.3)
    assert state.camera == "720×1280 (environment)"
    assert (state.phone_fps, state.tracking_state, state.rtt_ms) == (24.5, "hand_detected", 12.3)


# --- Visão no notebook (D013) --------------------------------------------------

from desktop.vision.frame_processor import VisionState, VisionStats  # noqa: E402


def vision_stats(**overrides):
    base = dict(window_s=1.0, received=20, processed=18, dropped=2, decode_errors=0,
                fps=18.0, decode_ms=1.5, inference_ms=24.4, wait_ms=0.4, frame_kb=40.0,
                width=640, height=360, with_hand=18)
    base.update(overrides)
    return VisionStats(**base)


def test_vision_summary_follows_state(clock):
    state = CursorState(clock=clock)
    state.on_vision_state(VisionState.LOADING, "")
    assert state.vision_summary() == "loading"
    state.on_vision_state(VisionState.READY, "1800 ms")
    assert "sem quadros" in state.vision_summary()
    state.on_vision_stats(vision_stats())
    assert state.vision_summary() == "18.0 q/s · 24 ms · descartados 2 · 640×360"


def test_vision_error_is_visible(clock):
    state = CursorState(clock=clock)
    state.on_vision_state(VisionState.ERROR, "FileNotFoundError: modelo")
    assert "FileNotFoundError" in state.vision_summary()


def test_disconnect_clears_vision_and_mode(clock):
    state = CursorState(clock=clock)
    state.on_vision_state(VisionState.READY, "1 ms")
    state.on_vision_stats(vision_stats())
    state.on_status(parse_message(json.dumps(
        {"type": "status", "v": 0, "fps": 25, "tracking_state": "inactive", "mode": "stream"})))
    assert state.phone_mode == "stream"
    state.on_connection(ConnectionState.DISCONNECTED, "client_closed")
    assert state.vision is None and state.phone_mode == "—"
    assert state.vision_state == "ready"  # o MediaPipe continua carregado
