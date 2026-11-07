"""Quadro de câmera enviado pelo celular como mensagem binária do WebSocket (D013).

Formato v1 (little-endian), 16 bytes de cabeçalho + imagem JPEG:

    offset  tamanho  campo
    0       4        magic  b"SBF1"
    4       4        seq          uint32, crescente por conexão
    8       8        t_client_ms  float64, relógio do celular (performance.now)
    16      ...      JPEG (começa com FF D8)

A imagem é a mesma cena do vídeo da câmera, apenas reduzida: coordenadas
normalizadas calculadas sobre ela valem para o quadro original (camera_norm).

Este módulo só valida o envelope. Não decodifica o JPEG (isso é da visão
computacional) e nunca grava a imagem (CLAUDE.md §11).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from desktop import config
from desktop.communication.message_protocol import ErrorCode, ProtocolError

FRAME_MAGIC = b"SBF1"
_HEADER = struct.Struct("<4sId")
FRAME_HEADER_BYTES = _HEADER.size  # 16
_JPEG_SOI = b"\xff\xd8"


@dataclass(frozen=True)
class FrameMessage:
    seq: int
    t_client_ms: float
    jpeg: bytes
    # Preenchidos pelo servidor, no relógio monotônico do notebook (ms):
    received_ms: float | None = None  # chegada ao notebook
    capture_ms: float | None = None  # captura no celular, convertida (clock_sync)

    @property
    def size_bytes(self) -> int:
        return FRAME_HEADER_BYTES + len(self.jpeg)


def _fail(detail: str) -> ProtocolError:
    return ProtocolError(ErrorCode.INVALID_MESSAGE, f"quadro: {detail}")


def parse_frame(raw: bytes, max_bytes: int = config.MAX_FRAME_BYTES) -> FrameMessage:
    """Valida o envelope binário. Lança ProtocolError se inválido."""
    if len(raw) > max_bytes:
        raise ProtocolError(ErrorCode.MESSAGE_TOO_LARGE, f"quadro com {len(raw)} bytes (máx. {max_bytes})")
    if len(raw) < FRAME_HEADER_BYTES + len(_JPEG_SOI):
        raise _fail("curto demais")
    magic, seq, t_client_ms = _HEADER.unpack_from(raw)
    if magic != FRAME_MAGIC:
        raise _fail("magic desconhecido")
    if not math.isfinite(t_client_ms) or t_client_ms < 0:
        raise _fail("t_client_ms inválido")
    jpeg = bytes(raw[FRAME_HEADER_BYTES:])
    if not jpeg.startswith(_JPEG_SOI):
        raise _fail("conteúdo não é JPEG")
    return FrameMessage(seq=seq, t_client_ms=t_client_ms, jpeg=jpeg)


def build_frame(seq: int, t_client_ms: float, jpeg: bytes) -> bytes:
    """Monta um quadro (usado por testes e pelo celular simulado)."""
    return _HEADER.pack(FRAME_MAGIC, seq, t_client_ms) + jpeg
