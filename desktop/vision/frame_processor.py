"""Processa os quadros do celular em uma thread própria, sempre o mais recente (D013).

Fluxo: servidor → on_frame() → [vaga única] → thread → JPEG→RGB → MediaPipe
→ HandTrackingMessage para os mesmos ouvintes que recebiam o rastreamento
feito no celular (cursor e log). O resto do programa não muda.

Política de atraso (CLAUDE.md §6.2, evitar processar dados antigos): há uma
única vaga. Se chega um quadro enquanto outro espera, o que esperava é
descartado e contado. Assim a fila nunca cresce: quando o notebook não dá
conta, a taxa cai, mas o cursor não fica atrasado.

Imagens só existem em memória, durante o processamento (CLAUDE.md §11).
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from desktop import config
from desktop.communication.frame_protocol import FrameMessage
from desktop.communication.message_protocol import HandState, HandTrackingMessage
from desktop.communication.server import ConnectionState, ServerEvents
from desktop.vision.hand_tracker import HandDetector

log = logging.getLogger(__name__)


class VisionState(str, Enum):
    """Estado do MediaPipe no notebook."""

    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class VisionStats:
    """Resumo de uma janela de tempo (padrão: 1 s)."""

    window_s: float
    received: int  # quadros entregues pelo servidor
    processed: int  # quadros que passaram pelo MediaPipe
    dropped: int  # substituídos por um mais novo antes de processar
    decode_errors: int
    fps: float  # processed / window_s
    decode_ms: float | None  # média JPEG → RGB
    inference_ms: float | None  # média MediaPipe
    wait_ms: float | None  # média entre chegar ao notebook e começar a processar
    frame_kb: float | None  # tamanho médio dos quadros recebidos
    width: int | None  # dimensões do último quadro decodificado
    height: int | None
    with_hand: int  # quadros processados com mão
    # Latência (precisa da sincronia de relógios; None antes do 1º pong):
    to_arrival_ms: float | None = None  # captura no celular → chegada ao notebook (inclui o JPEG)
    to_result_ms: float | None = None  # captura no celular → resultado do MediaPipe
    two_hands: int = 0  # quadros com as duas mãos visíveis
    # Comparação de reconhecimentos (D022), só com uma mão na imagem: trocas de pose
    # do reconhecimento ativo e do outro, nos mesmos quadros.
    pose_flips: int = 0
    pose_alt_flips: int = 0
    one_hand: int = 0
    # Consumo do programa inteiro (visão + lousa + servidor), para a Fase 7 (D031):
    cpu_pct: float | None = None  # tempo de CPU ÷ tempo real (100 = um núcleo inteiro)
    rss_peak_mb: float | None = None  # pico de memória desde o início


def process_usage() -> tuple[float, float | None]:
    """(tempo de CPU do processo em s, pico de memória em MB ou None)."""
    cpu = time.process_time()
    try:
        import resource  # não existe no Windows
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux informa em KB; macOS, em bytes.
        mb = peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
    except (ImportError, OSError):
        mb = None
    return cpu, mb


class _Window:
    """Acumulador das métricas de uma janela."""

    def __init__(self, start: float) -> None:
        self.start = start
        self.cpu_start = time.process_time()
        self.received = self.processed = self.dropped = self.decode_errors = 0
        self.with_hand = 0
        self.two_hands = 0
        self.pose_flips = self.pose_alt_flips = self.one_hand = 0
        self.bytes = 0
        self.decode_ms = self.inference_ms = self.wait_ms = 0.0
        self.width: int | None = None
        self.height: int | None = None
        self.timed = 0  # quadros com horário de captura conhecido
        self.to_arrival_ms = self.to_result_ms = 0.0

    def stats(self, now: float) -> VisionStats:
        window = max(now - self.start, 1e-9)
        n = self.processed

        def avg(total: float, count: int) -> float | None:
            return round(total / count, 2) if count else None

        return VisionStats(
            window_s=round(window, 3), received=self.received, processed=n,
            dropped=self.dropped, decode_errors=self.decode_errors,
            fps=round(n / window, 2),
            decode_ms=avg(self.decode_ms, n + self.decode_errors),
            inference_ms=avg(self.inference_ms, n), wait_ms=avg(self.wait_ms, n),
            frame_kb=avg(self.bytes / 1024, self.received),
            width=self.width, height=self.height, with_hand=self.with_hand,
            to_arrival_ms=avg(self.to_arrival_ms, self.timed),
            to_result_ms=avg(self.to_result_ms, self.timed),
            two_hands=self.two_hands,
            pose_flips=self.pose_flips, pose_alt_flips=self.pose_alt_flips, one_hand=self.one_hand,
            **self._usage(window),
        )

    def _usage(self, window: float) -> dict:
        cpu, mb = process_usage()
        return {"cpu_pct": round(100 * (cpu - self.cpu_start) / window, 1),
                "rss_peak_mb": None if mb is None else round(mb, 1)}


class VisionEvents:
    """Saída do processador. FanOutEvents/SessionLog/ponte Qt implementam."""

    def on_hand_tracking(self, message: HandTrackingMessage) -> None: ...

    def on_vision_state(self, state: VisionState, detail: str) -> None: ...

    def on_vision_stats(self, stats: VisionStats) -> None: ...

    def on_markers(self, observation: dict, image_width: int, image_height: int) -> None:
        """Marcadores ArUco vistos num quadro (D015). Chega a cada N quadros."""

    def on_scene_motion(self, shift) -> None:
        """Deslocamento da cena desde a referência (D030), com os marcadores escondidos."""


class FrameProcessor(ServerEvents):
    """Recebe quadros do servidor (como ServerEvents) e roda o detector na sua thread."""

    def __init__(
        self,
        detector_factory: Callable[[], HandDetector],
        output: VisionEvents,
        decoder: Callable[[bytes], Any],
        clock: Callable[[], float] = time.monotonic,
        stats_interval_s: float = config.VISION_STATS_INTERVAL_S,
        marker_detector_factory: Callable[[], Any] | None = None,
        marker_every_n: int = config.MARKER_DETECT_EVERY_N,
    ) -> None:
        self._factory = detector_factory
        self._output = output
        self._decode = decoder
        self._clock = clock
        self._interval = stats_interval_s

        self._cond = threading.Condition()
        self._pending: tuple[FrameMessage, float] | None = None
        self._stopping = False
        self._window = _Window(clock())
        self._last_ts_ms = -1
        # Último quadro e mão, para a janela de diagnóstico. Só em memória
        # (CLAUDE.md §11); substituído a cada quadro, nunca gravado.
        self._preview_lock = threading.Lock()
        self._preview: tuple[Any, Any] | None = None
        self._marker_factory = marker_detector_factory
        self._marker_every_n = max(1, marker_every_n)
        self._marker_detector = None
        # Celular mexido com os marcadores escondidos (D030). Pedidos chegam da janela.
        self._scene = None
        self._scene_request: tuple | None = None
        self._scene_lock = threading.Lock()
        self._frames_done = 0
        self._last_poses: tuple | None = None  # (pose, pose_alt) do quadro anterior, para contar trocas
        self._thread = threading.Thread(target=self._run, name="frame-processor", daemon=True)

    # --- ciclo de vida ---------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout_s)

    # --- entrada (thread do servidor) ------------------------------------------

    def on_frame(self, frame: FrameMessage) -> None:
        now = self._clock()
        with self._cond:
            self._window.received += 1
            self._window.bytes += frame.size_bytes
            if self._pending is not None:
                self._window.dropped += 1
            self._pending = (frame, now)
            self._cond.notify()

    def on_connection_state(self, state: ConnectionState, detail: str) -> None:
        if state is ConnectionState.DISCONNECTED:
            with self._cond:
                self._pending = None  # quadro de uma conexão que já acabou
            with self._preview_lock:
                self._preview = None

    def latest_preview(self) -> tuple[Any, Any] | None:
        """(imagem RGB, HandState) do último quadro processado, ou None."""
        with self._preview_lock:
            return self._preview

    # --- thread de processamento -----------------------------------------------

    def _next_frame(self) -> tuple[FrameMessage, float] | None:
        with self._cond:
            while self._pending is None and not self._stopping:
                self._cond.wait(timeout=self._interval)
                self._maybe_emit_stats_locked()
            if self._stopping:
                return None
            item, self._pending = self._pending, None
            return item

    # --- celular mexido (D030) ------------------------------------------------------

    def watch_scene(self, surface_quad) -> None:
        """Tira a foto de referência no próximo quadro e passa a medir o deslocamento.

        Chamado pela janela (outra thread) quando os marcadores somem.
        `surface_quad`: cantos da lousa na câmera, para excluí-la da comparação.
        """
        with self._scene_lock:
            self._scene_request = ("watch", None if surface_quad is None else list(surface_quad))

    def stop_watching_scene(self) -> None:
        with self._scene_lock:
            self._scene_request = ("stop", None)

    def _watch_scene(self, rgb) -> None:
        with self._scene_lock:
            request, self._scene_request = self._scene_request, None
        try:
            if request is not None:
                if request[0] == "stop":
                    if self._scene is not None:
                        self._scene.clear()
                    return
                from desktop.vision.scene_motion import SceneMotion, small_gray
                self._scene = self._scene or SceneMotion()
                self._scene.set_reference(small_gray(rgb), request[1])
                return
            if self._scene is not None and self._scene.has_reference:
                from desktop.vision.scene_motion import small_gray
                shift = self._scene.measure(small_gray(rgb))
                if shift is not None:
                    self._output.on_scene_motion(shift)
        except Exception:  # noqa: BLE001 — falhar aqui não pode parar o rastreamento
            log.exception("Vigilância da cena falhou")
            self._scene = None

    def _timestamp_ms(self) -> int:
        # O modo VIDEO exige carimbos estritamente crescentes. Usar o relógio
        # do notebook evita depender do relógio do celular, que recomeça a
        # cada recarga da página.
        ts = max(int(self._clock() * 1000), self._last_ts_ms + 1)
        self._last_ts_ms = ts
        return ts

    def _run(self) -> None:
        self._output.on_vision_state(VisionState.LOADING, "")
        t0 = self._clock()
        try:
            detector = self._factory()
        except Exception as error:  # noqa: BLE001 — qualquer falha vira estado visível
            log.exception("MediaPipe não iniciou")
            self._output.on_vision_state(VisionState.ERROR, f"{type(error).__name__}: {error}")
            return
        if self._marker_factory is not None:
            try:
                self._marker_detector = self._marker_factory()
            except Exception:  # noqa: BLE001 — sem marcadores, o resto funciona
                log.exception("Detector de marcadores não iniciou")
        load_ms = (self._clock() - t0) * 1000
        log.info("MediaPipe pronto em %.0f ms", load_ms)
        self._output.on_vision_state(VisionState.READY, f"{load_ms:.0f} ms")
        with self._cond:
            self._window = _Window(self._clock())  # não conta o tempo de carga
        try:
            while (item := self._next_frame()) is not None:
                self._process(detector, *item)
        finally:
            detector.close()

    def _process(self, detector: HandDetector, frame: FrameMessage, received_at: float) -> None:
        start = self._clock()
        rgb = self._decode(frame.jpeg)
        decoded = self._clock()
        if rgb is None:
            with self._cond:
                self._window.decode_errors += 1
                self._window.decode_ms += (decoded - start) * 1000
                self._maybe_emit_stats_locked()
            return
        result = detector.detect(rgb, self._timestamp_ms())
        done = self._clock()
        # Detector real devolve a lista de mãos; detectores de teste, uma HandState.
        candidates = [h for h in result if h.present] if isinstance(result, list) else (
            [result] if result.present else [])
        hand = candidates[0] if candidates else HandState(present=False)
        with self._preview_lock:
            self._preview = (rgb, hand)
        self._frames_done += 1
        if self._marker_detector is not None and self._frames_done % self._marker_every_n == 0:
            observation = self._marker_detector.detect(rgb)
            self._output.on_markers(observation, rgb.shape[1], rgb.shape[0])
            self._watch_scene(rgb)
        inference_ms = (done - decoded) * 1000

        self._output.on_hand_tracking(HandTrackingMessage(
            seq=frame.seq, t_client_ms=frame.t_client_ms, hand=hand,
            inference_ms=round(inference_ms, 2), candidates=tuple(candidates),
        ))
        with self._cond:
            w = self._window
            w.processed += 1
            w.with_hand += int(hand.present)
            w.two_hands += int(len(candidates) >= 2)
            if len(candidates) == 1:
                w.one_hand += 1
                h = candidates[0]
                if self._last_poses is not None:
                    w.pose_flips += int(h.pose != self._last_poses[0])
                    w.pose_alt_flips += int(h.pose_alt != self._last_poses[1])
                self._last_poses = (h.pose, h.pose_alt)
            else:
                self._last_poses = None
            w.decode_ms += (decoded - start) * 1000
            w.inference_ms += inference_ms
            w.wait_ms += (start - received_at) * 1000
            w.height, w.width = rgb.shape[0], rgb.shape[1]
            if frame.capture_ms is not None and frame.received_ms is not None:
                w.timed += 1
                w.to_arrival_ms += frame.received_ms - frame.capture_ms
                w.to_result_ms += done * 1000 - frame.capture_ms
            self._maybe_emit_stats_locked()

    def _maybe_emit_stats_locked(self) -> None:
        now = self._clock()
        w = self._window
        if now - w.start < self._interval:
            return
        self._window = _Window(now)
        if w.received or w.processed:
            # Chamado com o lock; os ouvintes só gravam/enfileiram, não bloqueiam.
            self._output.on_vision_stats(w.stats(now))
