"""Protocolo de mensagens celular ↔ notebook, versão 0.

Especificação: docs/communication-protocol.md

Responsabilidade deste módulo (CLAUDE.md §3.1, Comunicação):
- converter texto JSON recebido em objetos tipados e validados;
- rejeitar estruturas inválidas com um código de erro claro;
- descartar mensagens de rastreamento antigas (SequenceGate);
- montar as mensagens que o notebook envia.

Não conhece rede, interface nem coordenadas de tela. As coordenadas aqui
estão sempre em `camera_norm` (docs/architecture.md §3).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Union

from desktop import config


# --- Erros -------------------------------------------------------------------


class ErrorCode(str, Enum):
    """Códigos enviados ao celular na mensagem `error`."""

    INVALID_JSON = "invalid_json"
    MESSAGE_TOO_LARGE = "message_too_large"
    INVALID_MESSAGE = "invalid_message"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNKNOWN_TYPE = "unknown_type"


class ProtocolError(Exception):
    """Mensagem recebida rejeitada pela validação."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


# --- Valores enumerados do protocolo ----------------------------------------


class Handedness(str, Enum):
    LEFT = "Left"
    RIGHT = "Right"


class CameraFacing(str, Enum):
    ENVIRONMENT = "environment"  # câmera traseira
    USER = "user"  # câmera frontal
    UNKNOWN = "unknown"  # navegador não informa (ex.: webcam de notebook)


class TrackingState(str, Enum):
    """Estados de rastreamento do celular (CLAUDE.md §8)."""

    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    HAND_DETECTED = "hand_detected"
    TRACKING_ACTIVE = "tracking_active"
    TRACKING_LOST = "tracking_lost"


# --- Mensagens recebidas do celular ------------------------------------------


@dataclass(frozen=True)
class CameraInfo:
    width: int
    height: int
    facing: CameraFacing


@dataclass(frozen=True)
class HelloMessage:
    client: str
    client_version: str
    camera: CameraInfo


@dataclass(frozen=True)
class IndexTip:
    """Ponta do indicador em `camera_norm`: x, y ∈ [0, 1]; z relativo ao pulso."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HandState:
    present: bool
    handedness: Handedness | None = None
    confidence: float | None = None
    index_tip: IndexTip | None = None
    # Só no processamento do notebook (não trafega pela rede): pulso e as 4
    # articulações da base dos dedos, em camera_norm, e o tamanho aparente da
    # palma em px da câmera. Usados para escolher entre duas mãos.
    palm: tuple[IndexTip, ...] | None = None
    palm_size_px: float | None = None
    # Pose da mão (Fase 4, D018): "pointing" (só o indicador esticado),
    # "open", "fist" ou "other". None quando não calculada (ex.: modo local).
    pose: str | None = None
    # Abertura da mão (pontas ÷ palma; fechada ≈ 1, aberta ≈ 2). Só no notebook.
    openness: float | None = None
    # Pinça: distância polegar↔indicador ÷ palma (D021). Só no notebook.
    pinch: float | None = None
    # Pose do outro reconhecimento (D022: "kit" × "legacy"), só para comparar no log.
    pose_alt: str | None = None
    # Os 21 pontos da mão em camera_norm (D036), só no notebook: desenho do esqueleto
    # na janela da câmera e lado da mão (palma/dorso).
    landmarks: tuple[IndexTip, ...] | None = None


@dataclass(frozen=True)
class HandTrackingMessage:
    seq: int
    t_client_ms: float
    hand: HandState
    inference_ms: float | None = None
    # Todas as mãos detectadas no quadro (modo stream, até 2). `hand` é a
    # primeira; quem conhece a calibração escolhe a certa (hand_selection.py).
    candidates: tuple[HandState, ...] = ()


@dataclass(frozen=True)
class PingMessage:
    id: int
    t_sender_ms: float


@dataclass(frozen=True)
class PongMessage:
    id: int
    t_sender_ms: float
    # Horário do celular ao responder (opcional): permite estimar a diferença
    # entre os relógios e medir a latência ponta a ponta (clock_sync.py).
    t_reply_ms: float | None = None


class PhoneMode(str, Enum):
    """Onde a mão é detectada (D013)."""

    STREAM = "stream"  # celular envia quadros; o notebook roda o MediaPipe
    LOCAL = "local"  # celular roda o MediaPipe e envia só coordenadas (D002)


class JpegEncoder(str, Enum):
    """Onde o celular gera o JPEG no modo stream (etapa 2.0)."""

    WORKER = "worker"  # Web Worker com OffscreenCanvas
    MAIN = "main"  # na própria página (canvas.toBlob)


class Delegate(str, Enum):
    """Onde o MediaPipe roda no celular."""

    GPU = "GPU"
    CPU = "CPU"


@dataclass(frozen=True)
class StatusMessage:
    fps: float
    tracking_state: TrackingState
    # Métricas opcionais de diagnóstico (gravadas no log de sessão).
    inference_ms: float | None = None  # tempo médio do MediaPipe por quadro
    load_ms: float | None = None  # tempo para o MediaPipe ficar pronto
    delegate: Delegate | None = None
    mode: PhoneMode | None = None
    encode_ms: float | None = None  # modo stream: tempo médio para gerar o JPEG
    frame_kb: float | None = None  # modo stream: tamanho médio do quadro enviado
    skipped: int | None = None  # modo stream: quadros não enviados por contrapressão
    encoder: JpegEncoder | None = None  # modo stream: onde o JPEG é gerado


IncomingMessage = Union[
    HelloMessage, HandTrackingMessage, PingMessage, PongMessage, StatusMessage
]


# --- Validadores de campos ---------------------------------------------------


def _fail(detail: str) -> ProtocolError:
    return ProtocolError(ErrorCode.INVALID_MESSAGE, detail)


def _require(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise _fail(f"campo obrigatório ausente: {path}{key}")
    return data[key]


def _as_object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _fail(f"{path} deve ser um objeto")
    return value


def _as_number(value: Any, path: str) -> float:
    # bool é subclasse de int em Python; não é um número válido aqui.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(f"{path} deve ser numérico")
    number = float(value)
    if not math.isfinite(number):
        raise _fail(f"{path} deve ser finito")
    return number


def _as_number_in(value: Any, path: str, low: float, high: float) -> float:
    number = _as_number(value, path)
    if not low <= number <= high:
        raise _fail(f"{path} fora de [{low:g}, {high:g}]")
    return number


def _as_non_negative(value: Any, path: str) -> float:
    number = _as_number(value, path)
    if number < 0:
        raise _fail(f"{path} não pode ser negativo")
    return number


def _as_int(value: Any, path: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{path} deve ser inteiro")
    if value < minimum:
        raise _fail(f"{path} deve ser >= {minimum}")
    return value


def _as_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{path} deve ser texto não vazio")
    return value


def _as_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(f"{path} deve ser true/false")
    return value


def _as_enum(enum_cls: type[Enum], value: Any, path: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise _fail(f"{path} deve ser um de: {allowed}") from None


# --- Parsers por tipo de mensagem --------------------------------------------


def _parse_hello(data: Mapping[str, Any]) -> HelloMessage:
    camera = _as_object(_require(data, "camera", ""), "camera")
    return HelloMessage(
        client=_as_text(_require(data, "client", ""), "client"),
        client_version=_as_text(_require(data, "client_version", ""), "client_version"),
        camera=CameraInfo(
            width=_as_int(_require(camera, "width", "camera."), "camera.width", 1),
            height=_as_int(_require(camera, "height", "camera."), "camera.height", 1),
            facing=_as_enum(
                CameraFacing, _require(camera, "facing", "camera."), "camera.facing"
            ),
        ),
    )


def _parse_hand(data: Mapping[str, Any]) -> HandState:
    present = _as_bool(_require(data, "present", "hand."), "hand.present")
    if not present:
        return HandState(present=False)

    tip = _as_object(_require(data, "index_tip", "hand."), "hand.index_tip")
    return HandState(
        present=True,
        handedness=_as_enum(
            Handedness, _require(data, "handedness", "hand."), "hand.handedness"
        ),
        confidence=_as_number_in(
            _require(data, "confidence", "hand."), "hand.confidence", 0.0, 1.0
        ),
        index_tip=IndexTip(
            x=_as_number_in(_require(tip, "x", "hand.index_tip."), "hand.index_tip.x", 0.0, 1.0),
            y=_as_number_in(_require(tip, "y", "hand.index_tip."), "hand.index_tip.y", 0.0, 1.0),
            z=_as_number(_require(tip, "z", "hand.index_tip."), "hand.index_tip.z"),
        ),
    )


def _parse_hand_tracking(data: Mapping[str, Any]) -> HandTrackingMessage:
    inference = data.get("inference_ms")
    return HandTrackingMessage(
        seq=_as_int(_require(data, "seq", ""), "seq", 0),
        t_client_ms=_as_non_negative(_require(data, "t_client_ms", ""), "t_client_ms"),
        hand=_parse_hand(_as_object(_require(data, "hand", ""), "hand")),
        inference_ms=None if inference is None else _as_non_negative(inference, "inference_ms"),
    )


def _parse_ping(data: Mapping[str, Any]) -> PingMessage:
    return PingMessage(
        id=_as_int(_require(data, "id", ""), "id", 0),
        t_sender_ms=_as_non_negative(_require(data, "t_sender_ms", ""), "t_sender_ms"),
    )


def _parse_pong(data: Mapping[str, Any]) -> PongMessage:
    return PongMessage(
        id=_as_int(_require(data, "id", ""), "id", 0),
        t_sender_ms=_as_non_negative(_require(data, "t_sender_ms", ""), "t_sender_ms"),
        t_reply_ms=_optional(data, "t_reply_ms", _as_non_negative),
    )


def _optional(data: Mapping[str, Any], key: str, parse) -> Any:
    value = data.get(key)
    return None if value is None else parse(value, key)


def _parse_status(data: Mapping[str, Any]) -> StatusMessage:
    return StatusMessage(
        fps=_as_non_negative(_require(data, "fps", ""), "fps"),
        tracking_state=_as_enum(
            TrackingState, _require(data, "tracking_state", ""), "tracking_state"
        ),
        inference_ms=_optional(data, "inference_ms", _as_non_negative),
        load_ms=_optional(data, "load_ms", _as_non_negative),
        delegate=_optional(data, "delegate", lambda v, k: _as_enum(Delegate, v, k)),
        mode=_optional(data, "mode", lambda v, k: _as_enum(PhoneMode, v, k)),
        encode_ms=_optional(data, "encode_ms", _as_non_negative),
        frame_kb=_optional(data, "frame_kb", _as_non_negative),
        skipped=_optional(data, "skipped", lambda v, k: _as_int(v, k, 0)),
        encoder=_optional(data, "encoder", lambda v, k: _as_enum(JpegEncoder, v, k)),
    )


_PARSERS = {
    "hello": _parse_hello,
    "hand_tracking": _parse_hand_tracking,
    "ping": _parse_ping,
    "pong": _parse_pong,
    "status": _parse_status,
}


# --- API pública -------------------------------------------------------------


def parse_message(raw: str | bytes) -> IncomingMessage:
    """Converte uma mensagem recebida do celular em objeto validado.

    Campos desconhecidos são ignorados, para permitir que fases futuras
    acrescentem campos sem quebrar a v0 (docs/communication-protocol.md §4).

    Raises:
        ProtocolError: se a mensagem for inválida.
    """
    size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
    if size > config.MAX_MESSAGE_BYTES:
        raise ProtocolError(
            ErrorCode.MESSAGE_TOO_LARGE,
            f"{size} bytes (máximo {config.MAX_MESSAGE_BYTES})",
        )

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(ErrorCode.INVALID_JSON, str(exc)) from None

    if not isinstance(data, dict):
        raise _fail("a mensagem deve ser um objeto JSON")

    version = _require(data, "v", "")
    if isinstance(version, bool) or version != config.PROTOCOL_VERSION:
        raise ProtocolError(
            ErrorCode.UNSUPPORTED_VERSION,
            f"v={version!r}; esperado {config.PROTOCOL_VERSION}",
        )

    msg_type = _require(data, "type", "")
    parser = _PARSERS.get(msg_type) if isinstance(msg_type, str) else None
    if parser is None:
        raise ProtocolError(ErrorCode.UNKNOWN_TYPE, f"type={msg_type!r}")

    return parser(data)


class SequenceGate:
    """Descarta mensagens hand_tracking antigas ou repetidas.

    Uma instância por conexão: o `seq` recomeça quando o celular reconecta.
    """

    def __init__(self) -> None:
        self._last_seq: int | None = None

    @property
    def last_seq(self) -> int | None:
        return self._last_seq

    def accept(self, seq: int) -> bool:
        """True se `seq` é mais novo que o último aceito; False para descartar."""
        if self._last_seq is not None and seq <= self._last_seq:
            return False
        self._last_seq = seq
        return True


# --- Mensagens enviadas pelo notebook ---------------------------------------


def _envelope(msg_type: str, **fields: Any) -> str:
    payload = {"type": msg_type, "v": config.PROTOCOL_VERSION, **fields}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def make_welcome(session_id: str, max_rate_hz: int = config.MAX_TRACKING_RATE_HZ) -> str:
    return _envelope("welcome", session_id=session_id, max_rate_hz=max_rate_hz)


def make_error(error: ProtocolError) -> str:
    return _envelope("error", code=error.code.value, detail=error.detail)


def make_ping(ping_id: int, t_sender_ms: float) -> str:
    return _envelope("ping", id=ping_id, t_sender_ms=t_sender_ms)


def make_pong(ping: PingMessage) -> str:
    """Responde um ping devolvendo o mesmo id e o horário de quem enviou."""
    return _envelope("pong", id=ping.id, t_sender_ms=ping.t_sender_ms)
