"""Testes do envelope binário de quadros de câmera (D013)."""

import math
import struct

import pytest

from desktop.communication.frame_protocol import (
    FRAME_HEADER_BYTES,
    build_frame,
    parse_frame,
)
from desktop.communication.message_protocol import ErrorCode, ProtocolError

JPEG = b"\xff\xd8\xff\xe0conteudo"


def test_round_trip():
    frame = parse_frame(build_frame(42, 1234.5, JPEG))
    assert (frame.seq, frame.t_client_ms, frame.jpeg) == (42, 1234.5, JPEG)
    assert frame.size_bytes == FRAME_HEADER_BYTES + len(JPEG)


def test_header_is_16_bytes_little_endian():
    raw = build_frame(1, 2.0, JPEG)
    assert raw[:4] == b"SBF1"
    assert struct.unpack_from("<I", raw, 4)[0] == 1
    assert struct.unpack_from("<d", raw, 8)[0] == 2.0
    assert raw[16:] == JPEG


@pytest.mark.parametrize(
    "raw, fragment",
    [
        (b"", "curto"),
        (b"SBF1" + b"\x00" * 12, "curto"),
        (b"XXXX" + b"\x00" * 12 + JPEG, "magic"),
        (build_frame(1, 1.0, b"\x89PNG...."), "JPEG"),
        (build_frame(1, -1.0, JPEG), "t_client_ms"),
        (build_frame(1, math.nan, JPEG), "t_client_ms"),
        (build_frame(1, math.inf, JPEG), "t_client_ms"),
    ],
)
def test_invalid_frames(raw, fragment):
    with pytest.raises(ProtocolError) as info:
        parse_frame(raw)
    assert info.value.code == ErrorCode.INVALID_MESSAGE
    assert fragment in info.value.detail


def test_size_limit():
    raw = build_frame(1, 1.0, JPEG + b"x" * 100)
    with pytest.raises(ProtocolError) as info:
        parse_frame(raw, max_bytes=len(raw) - 1)
    assert info.value.code == ErrorCode.MESSAGE_TOO_LARGE
    assert parse_frame(raw, max_bytes=len(raw)).seq == 1
