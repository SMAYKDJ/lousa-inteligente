"""Testes do protocolo v0 (etapa 1.1). Especificação: docs/communication-protocol.md"""

import copy
import json

import pytest

from desktop import config
from desktop.communication.message_protocol import (
    CameraFacing,
    ErrorCode,
    HandTrackingMessage,
    Handedness,
    HelloMessage,
    PingMessage,
    PongMessage,
    ProtocolError,
    SequenceGate,
    StatusMessage,
    TrackingState,
    make_error,
    make_ping,
    make_pong,
    make_welcome,
    parse_message,
)

# Valores ilustrativos, não dados reais de rastreamento.
HAND_TRACKING = {
    "type": "hand_tracking",
    "v": 0,
    "seq": 1532,
    "t_client_ms": 81234.5,
    "hand": {
        "present": True,
        "handedness": "Right",
        "confidence": 0.93,
        "index_tip": {"x": 0.52, "y": 0.43, "z": -0.04},
    },
    "inference_ms": 18.2,
}

HELLO = {
    "type": "hello",
    "v": 0,
    "client": "mobile-web",
    "client_version": "0.1.0",
    "camera": {"width": 1280, "height": 720, "facing": "environment"},
}


def encode(message: dict) -> str:
    return json.dumps(message)


def with_change(base: dict, path: str, value) -> dict:
    """Cópia de `base` com o campo em `path` (ex.: 'hand.index_tip.x') alterado."""
    message = copy.deepcopy(base)
    *parents, leaf = path.split(".")
    node = message
    for key in parents:
        node = node[key]
    node[leaf] = value
    return message


def without(base: dict, path: str) -> dict:
    message = copy.deepcopy(base)
    *parents, leaf = path.split(".")
    node = message
    for key in parents:
        node = node[key]
    del node[leaf]
    return message


def assert_rejected(raw: str, code: ErrorCode) -> ProtocolError:
    with pytest.raises(ProtocolError) as info:
        parse_message(raw)
    assert info.value.code is code
    return info.value


# --- Mensagens válidas -------------------------------------------------------


def test_hand_tracking_valid():
    msg = parse_message(encode(HAND_TRACKING))
    assert isinstance(msg, HandTrackingMessage)
    assert msg.seq == 1532
    assert msg.hand.present is True
    assert msg.hand.handedness is Handedness.RIGHT
    assert msg.hand.index_tip.x == pytest.approx(0.52)
    assert msg.hand.index_tip.y == pytest.approx(0.43)
    assert msg.inference_ms == pytest.approx(18.2)


def test_hand_absent_needs_only_present_flag():
    raw = encode({"type": "hand_tracking", "v": 0, "seq": 5, "t_client_ms": 10,
                  "hand": {"present": False}})
    msg = parse_message(raw)
    assert msg.hand.present is False
    assert msg.hand.index_tip is None


def test_inference_ms_is_optional():
    msg = parse_message(encode(without(HAND_TRACKING, "inference_ms")))
    assert msg.inference_ms is None


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0])
def test_coordinate_limits_are_inclusive(value):
    msg = parse_message(encode(with_change(HAND_TRACKING, "hand.index_tip.x", value)))
    assert msg.hand.index_tip.x == value


def test_unknown_fields_are_ignored_for_forward_compatibility():
    message = with_change(HAND_TRACKING, "gesture", "pointing")
    assert isinstance(parse_message(encode(message)), HandTrackingMessage)


def test_bytes_input_is_accepted():
    assert isinstance(parse_message(encode(HAND_TRACKING).encode("utf-8")), HandTrackingMessage)


def test_hello_valid():
    msg = parse_message(encode(HELLO))
    assert isinstance(msg, HelloMessage)
    assert msg.camera.facing is CameraFacing.ENVIRONMENT
    assert (msg.camera.width, msg.camera.height) == (1280, 720)


@pytest.mark.parametrize("facing", ["environment", "user", "unknown"])
def test_hello_accepts_all_camera_facings(facing):
    msg = parse_message(encode(with_change(HELLO, "camera.facing", facing)))
    assert msg.camera.facing.value == facing


def test_ping_pong_status_valid():
    assert isinstance(parse_message(encode({"type": "ping", "v": 0, "id": 7, "t_sender_ms": 1.5})), PingMessage)
    assert isinstance(parse_message(encode({"type": "pong", "v": 0, "id": 7, "t_sender_ms": 1.5})), PongMessage)
    status = parse_message(encode({"type": "status", "v": 0, "fps": 24.0, "tracking_state": "hand_detected"}))
    assert isinstance(status, StatusMessage)
    assert status.tracking_state is TrackingState.HAND_DETECTED


# --- Mensagens inválidas -----------------------------------------------------


def test_invalid_json():
    assert_rejected("{nao e json", ErrorCode.INVALID_JSON)


def test_json_that_is_not_an_object():
    assert_rejected("[1, 2, 3]", ErrorCode.INVALID_MESSAGE)


def test_message_too_large():
    padding = "x" * config.MAX_MESSAGE_BYTES
    assert_rejected(encode(with_change(HAND_TRACKING, "pad", padding)), ErrorCode.MESSAGE_TOO_LARGE)


def test_unknown_type():
    assert_rejected(encode(with_change(HAND_TRACKING, "type", "teleport")), ErrorCode.UNKNOWN_TYPE)


@pytest.mark.parametrize("version", [1, "0", None, True])
def test_unsupported_version(version):
    assert_rejected(encode(with_change(HAND_TRACKING, "v", version)), ErrorCode.UNSUPPORTED_VERSION)


def test_missing_version():
    assert_rejected(encode(without(HAND_TRACKING, "v")), ErrorCode.INVALID_MESSAGE)


@pytest.mark.parametrize(
    "path",
    ["seq", "t_client_ms", "hand", "hand.present", "hand.handedness",
     "hand.confidence", "hand.index_tip", "hand.index_tip.x",
     "hand.index_tip.y", "hand.index_tip.z"],
)
def test_missing_required_field(path):
    error = assert_rejected(encode(without(HAND_TRACKING, path)), ErrorCode.INVALID_MESSAGE)
    assert path.split(".")[-1] in error.detail


@pytest.mark.parametrize(
    "path, value",
    [
        ("hand.index_tip.x", -0.01),
        ("hand.index_tip.x", 1.01),
        ("hand.index_tip.y", 2),
        ("hand.confidence", 1.5),
        ("hand.confidence", -0.1),
    ],
)
def test_values_out_of_range(path, value):
    error = assert_rejected(encode(with_change(HAND_TRACKING, path, value)), ErrorCode.INVALID_MESSAGE)
    assert "fora de" in error.detail


@pytest.mark.parametrize(
    "path, value",
    [
        ("seq", 1.5),
        ("seq", "10"),
        ("seq", True),
        ("seq", -1),
        ("hand.present", 1),
        ("hand.index_tip.x", "0.5"),
        ("hand.index_tip.x", True),
        ("hand.handedness", "Both"),
        ("hand.index_tip", [0.5, 0.5]),
        ("t_client_ms", -5),
        ("inference_ms", -1),
    ],
)
def test_wrong_types_or_values(path, value):
    assert_rejected(encode(with_change(HAND_TRACKING, path, value)), ErrorCode.INVALID_MESSAGE)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(literal):
    raw = encode(HAND_TRACKING).replace('"x": 0.52', f'"x": {literal}')
    assert literal in raw
    assert_rejected(raw, ErrorCode.INVALID_MESSAGE)


@pytest.mark.parametrize(
    "path, value",
    [("camera.width", 0), ("camera.facing", "side"), ("client", ""), ("camera", "1280x720")],
)
def test_invalid_hello(path, value):
    assert_rejected(encode(with_change(HELLO, path, value)), ErrorCode.INVALID_MESSAGE)


def test_status_optional_metrics():
    raw = encode({"type": "status", "v": 0, "fps": 8.5, "tracking_state": "tracking_active",
                  "inference_ms": 98.0, "load_ms": 14800, "delegate": "GPU"})
    status = parse_message(raw)
    assert (status.inference_ms, status.load_ms, status.delegate.value) == (98.0, 14800.0, "GPU")


def test_status_without_metrics_still_valid():
    status = parse_message(encode({"type": "status", "v": 0, "fps": 0, "tracking_state": "inactive"}))
    assert status.inference_ms is None and status.load_ms is None and status.delegate is None


def test_status_stream_metrics():
    raw = encode({"type": "status", "v": 0, "fps": 24.0, "tracking_state": "inactive",
                  "mode": "stream", "encode_ms": 6.2, "frame_kb": 41.5, "skipped": 3,
                  "encoder": "worker"})
    status = parse_message(raw)
    assert (status.mode.value, status.encode_ms, status.frame_kb, status.skipped,
            status.encoder.value) == ("stream", 6.2, 41.5, 3, "worker")


@pytest.mark.parametrize("field, value", [
    ("delegate", "TPU"), ("inference_ms", -1), ("load_ms", "rápido"),
    ("mode", "cloud"), ("encode_ms", -2), ("encoder", "gpu"), ("frame_kb", "grande"), ("skipped", -1), ("skipped", 1.5),
])
def test_status_invalid_metrics(field, value):
    message = {"type": "status", "v": 0, "fps": 1, "tracking_state": "inactive", field: value}
    assert_rejected(encode(message), ErrorCode.INVALID_MESSAGE)


def test_invalid_status_state():
    raw = encode({"type": "status", "v": 0, "fps": 24.0, "tracking_state": "dancing"})
    assert_rejected(raw, ErrorCode.INVALID_MESSAGE)


# --- Descarte de mensagens antigas ------------------------------------------


def test_sequence_gate_accepts_increasing_and_drops_old_or_repeated():
    gate = SequenceGate()
    assert gate.last_seq is None
    assert gate.accept(10) is True
    assert gate.accept(11) is True
    assert gate.accept(11) is False  # repetida
    assert gate.accept(9) is False   # antiga
    assert gate.accept(15) is True   # lacuna é permitida (mensagens perdidas)
    assert gate.last_seq == 15


def test_sequence_gate_starts_fresh_per_connection():
    first, second = SequenceGate(), SequenceGate()
    first.accept(500)
    assert second.accept(0) is True


# --- Mensagens enviadas pelo notebook ---------------------------------------


def test_outgoing_messages_have_type_and_version():
    error = ProtocolError(ErrorCode.INVALID_MESSAGE, "hand.index_tip.x fora de [0, 1]")
    for raw in (make_welcome("abc"), make_error(error), make_ping(1, 2.0)):
        data = json.loads(raw)
        assert data["v"] == config.PROTOCOL_VERSION
        assert isinstance(data["type"], str)


def test_welcome_announces_rate_limit():
    data = json.loads(make_welcome("abc"))
    assert data == {"type": "welcome", "v": 0, "session_id": "abc",
                    "max_rate_hz": config.MAX_TRACKING_RATE_HZ}


def test_error_message_carries_code_and_detail():
    data = json.loads(make_error(ProtocolError(ErrorCode.UNKNOWN_TYPE, "type='x'")))
    assert data["code"] == "unknown_type"
    assert data["detail"] == "type='x'"


def test_pong_echoes_ping_and_round_trips_through_parser():
    ping = parse_message(make_ping(77, 81300.0))
    pong = parse_message(make_pong(ping))
    assert isinstance(pong, PongMessage)
    assert (pong.id, pong.t_sender_ms) == (77, 81300.0)
