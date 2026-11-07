"""Log de sessão em JSON Lines (uma linha JSON por evento).

Grava, no notebook, os números de cada sessão para análise posterior
(CLAUDE.md §10: medir antes de otimizar). Nunca grava imagens (§11).

Arquivo: logs/session-AAAAMMDD-HHMMSS.jsonl. Cada linha tem pelo menos
`t` (horário ISO local), `elapsed_s` (segundos desde o início) e `event`.

Eventos: start, connection, hello, status, rtt, tracking_rate, invalid,
vision_state, vision, stop. `vision` é o resumo por segundo do processamento
dos quadros no notebook (D013).
`hand_tracking` chega a ~30/s; para não inflar o arquivo, ele vira um
resumo por segundo (`tracking_rate`).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from desktop.communication.message_protocol import (
    HandTrackingMessage,
    HelloMessage,
    ProtocolError,
    StatusMessage,
)
from desktop.communication.server import ConnectionState, ServerEvents
from desktop.vision.frame_processor import VisionEvents, VisionState, VisionStats

#: Intervalo do resumo de hand_tracking (s).
TRACKING_SUMMARY_S = 1.0


def new_log_path(log_dir: Path, now: dt.datetime | None = None) -> Path:
    now = now or dt.datetime.now()
    return log_dir / f"session-{now:%Y%m%d-%H%M%S}.jsonl"


class SessionLog(ServerEvents, VisionEvents):
    """Recebe os eventos do servidor e grava uma linha JSON por evento."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self._clock = clock
        self._start = clock()
        self._lock = threading.Lock()  # eventos chegam da thread do servidor
        # hand_tracking chega da thread de visão; conexão, da do servidor.
        self._rate_lock = threading.RLock()
        self._marker_checks, self._marker_seen, self._marker_sides = 0, {}, []
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")
        self._rate_start: float | None = None
        self._rate_msgs = 0
        self._rate_with_hand = 0
        self._rate_last_seq: int | None = None

    # --- escrita ---------------------------------------------------------------

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "t": dt.datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_s": round(self._clock() - self._start, 3),
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            if not self._file.closed:
                self._file.write(line + "\n")
                self._file.flush()

    def close(self) -> None:
        self._flush_rate(force=True)
        self.write("stop")
        with self._lock:
            self._file.close()

    # --- eventos do servidor ---------------------------------------------------

    def on_connection_state(self, state: ConnectionState, detail: str) -> None:
        self._flush_rate(force=True)
        self.write("connection", state=state.value, detail=detail)

    def on_hello(self, hello: HelloMessage) -> None:
        cam = hello.camera
        self.write("hello", client=hello.client, client_version=hello.client_version,
                   camera_width=cam.width, camera_height=cam.height, facing=cam.facing.value)

    def on_status(self, status: StatusMessage) -> None:
        self.write(
            "status",
            fps=status.fps,
            tracking_state=status.tracking_state.value,
            inference_ms=status.inference_ms,
            load_ms=status.load_ms,
            delegate=status.delegate.value if status.delegate else None,
            mode=status.mode.value if status.mode else None,
            encode_ms=status.encode_ms,
            frame_kb=status.frame_kb,
            skipped=status.skipped,
            encoder=status.encoder.value if status.encoder else None,
        )

    def on_rtt(self, rtt_ms: float) -> None:
        self.write("rtt", rtt_ms=round(rtt_ms, 2))

    def on_clock_sync(self, estimate) -> None:
        self.write("clock", offset_ms=round(estimate.offset_ms, 1),
                   uncertainty_ms=round(estimate.uncertainty_ms, 1))

    def on_invalid_message(self, error: ProtocolError) -> None:
        self.write("invalid", code=error.code.value, detail=error.detail)

    def on_vision_state(self, state: VisionState, detail: str) -> None:
        self.write("vision_state", state=state.value, detail=detail or None)

    def on_vision_stats(self, stats: VisionStats) -> None:
        self.write("vision", **dataclasses.asdict(stats))
        self._flush_markers()

    def on_markers(self, observation, image_width, image_height) -> None:
        """Acumula; o resumo sai junto com o `vision` de cada segundo."""
        with self._rate_lock:
            self._marker_checks += 1
            for marker_id, corners in observation.items():
                self._marker_seen[marker_id] = self._marker_seen.get(marker_id, 0) + 1
                xs = [p.x * image_width for p in corners]
                ys = [p.y * image_height for p in corners]
                self._marker_sides.append(((max(xs) - min(xs)) + (max(ys) - min(ys))) / 2)

    def _flush_markers(self) -> None:
        with self._rate_lock:
            if not self._marker_checks:
                return
            sides = self._marker_sides
            self.write("markers", checks=self._marker_checks,
                       seen={str(k): v for k, v in sorted(self._marker_seen.items())},
                       mean_side_px=round(sum(sides) / len(sides), 1) if sides else None)
            self._marker_checks, self._marker_seen, self._marker_sides = 0, {}, []

    def on_hand_tracking(self, message: HandTrackingMessage) -> None:
        with self._rate_lock:
            now = self._clock()
            if self._rate_start is None:
                self._rate_start = now
            self._rate_msgs += 1
            self._rate_with_hand += int(message.hand.present)
            self._rate_last_seq = message.seq
            self._flush_rate()

    def _flush_rate(self, force: bool = False) -> None:
        with self._rate_lock:
            self._flush_rate_locked(force)

    def _flush_rate_locked(self, force: bool) -> None:
        if self._rate_start is None:
            return
        elapsed = self._clock() - self._rate_start
        if not force and elapsed < TRACKING_SUMMARY_S:
            return
        if self._rate_msgs:
            self.write("tracking_rate", msgs=self._rate_msgs, with_hand=self._rate_with_hand,
                       window_s=round(elapsed, 3), last_seq=self._rate_last_seq)
        self._rate_start, self._rate_msgs, self._rate_with_hand = None, 0, 0


class FanOutEvents(ServerEvents, VisionEvents):
    """Repassa cada evento do servidor e da visão para vários ouvintes.

    Eventos de visão só vão a quem os implementa (ex.: janela e log; o
    processador de quadros não precisa ouvir a si mesmo).
    """

    def __init__(self, *listeners: ServerEvents) -> None:
        self._listeners = listeners

    def on_connection_state(self, state, detail):
        for listener in self._listeners:
            listener.on_connection_state(state, detail)

    def on_hello(self, hello):
        for listener in self._listeners:
            listener.on_hello(hello)

    def on_hand_tracking(self, message):
        for listener in self._listeners:
            listener.on_hand_tracking(message)

    def on_status(self, status):
        for listener in self._listeners:
            listener.on_status(status)

    def on_rtt(self, rtt_ms):
        for listener in self._listeners:
            listener.on_rtt(rtt_ms)

    def on_invalid_message(self, error):
        for listener in self._listeners:
            listener.on_invalid_message(error)

    def on_frame(self, frame):
        for listener in self._listeners:
            listener.on_frame(frame)

    def on_clock_sync(self, estimate):
        for listener in self._listeners:
            listener.on_clock_sync(estimate)

    def on_vision_state(self, state, detail):
        for listener in self._listeners:
            if isinstance(listener, VisionEvents):
                listener.on_vision_state(state, detail)

    def on_vision_stats(self, stats):
        for listener in self._listeners:
            if isinstance(listener, VisionEvents):
                listener.on_vision_stats(stats)

    def on_markers(self, observation, image_width, image_height):
        for listener in self._listeners:
            if isinstance(listener, VisionEvents):
                listener.on_markers(observation, image_width, image_height)

    def on_scene_motion(self, shift):
        for listener in self._listeners:
            if isinstance(listener, VisionEvents):
                listener.on_scene_motion(shift)
