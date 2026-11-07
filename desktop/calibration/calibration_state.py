"""Máquina de estados da calibração com o dedo (D014, docs/calibration.md §2).

Sem Qt e sem relógio próprio: quem usa informa o horário (`now`, em segundos)
a cada chamada. Assim os testes controlam o tempo (CLAUDE.md §9.1).

Fluxo: para cada alvo, na ordem superior esquerdo → inferior esquerdo →
inferior direito → superior direito, há uma contagem regressiva. Nos últimos
`collect_s` segundos, as posições do dedo são coletadas. No fim da contagem:
- ponto aceito → próximo alvo (ou, após o 4º, calcula a homografia);
- ponto rejeitado → a contagem do MESMO alvo recomeça, com uma mensagem.
Depois dos 4 cantos, um alvo no centro verifica o resultado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from desktop import config
from desktop.calibration.homography import CalibrationError, Homography, SurfacePoint
from desktop.calibration.point_capture import REJECT_MESSAGES, PointCollector
from desktop.core.coordinate_mapper import CameraNormPoint


def corner_targets(margin: float = config.CALIBRATION_TARGET_MARGIN) -> list[SurfacePoint]:
    """Alvos na ordem definida pelo usuário: SE → IE → ID → SD."""
    lo, hi = margin, 1.0 - margin
    return [SurfacePoint(lo, lo), SurfacePoint(lo, hi), SurfacePoint(hi, hi), SurfacePoint(hi, lo)]


CORNER_NAMES = ["superior esquerdo", "inferior esquerdo", "inferior direito", "superior direito"]
VERIFY_TARGET = SurfacePoint(0.5, 0.5)


class Phase(str, Enum):
    IDLE = "idle"  # nenhuma calibração em andamento
    CORNERS = "corners"  # contagem nos 4 cantos
    VERIFY = "verify"  # contagem no alvo central de verificação
    DONE = "done"  # calibrado
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CalibrationResult:
    homography: Homography
    camera_points: list[CameraNormPoint]
    surface_points: list[SurfacePoint]
    verify_error: tuple[float, float]  # (dx, dy) em surface_norm, no alvo central
    duration_s: float
    rejections: int
    mode: str = "corners"  # "corners" (4 toques) ou "markers" (marcadores + 1 toque, D034)


@dataclass(frozen=True)
class CalibrationView:
    """O que a tela da lousa precisa desenhar."""

    phase: Phase
    step: int  # 1–4 nos cantos, 5 na verificação
    target: SurfacePoint | None
    target_name: str
    remaining_s: float
    progress: float  # 0 → 1 ao longo da contagem
    collecting: bool
    finger_seen: bool
    message: str
    captured: tuple[SurfacePoint, ...]  # alvos já aceitos (para pintar de verde)
    title: str = ""  # se preenchido, substitui o título padrão (ex.: teste de precisão)


@dataclass
class CalibrationSession:
    countdown_s: float = config.CALIBRATION_COUNTDOWN_S
    collect_s: float = config.CALIBRATION_COLLECT_S
    min_presence: float = config.CALIBRATION_MIN_PRESENCE
    max_spread: float = config.CALIBRATION_MAX_SPREAD
    max_verify_error: float = config.CALIBRATION_MAX_VERIFY_ERROR
    targets: list[SurfacePoint] = field(default_factory=corner_targets)

    phase: Phase = Phase.IDLE
    result: CalibrationResult | None = None
    message: str = ""

    def __post_init__(self) -> None:
        self._index = 0
        self._step_start = 0.0
        self._started_at = 0.0
        self._captured: list[CameraNormPoint] = []
        self._collector = self._new_collector()
        self._homography: Homography | None = None
        self._rejections = 0
        self._last_tip: CameraNormPoint | None = None
        self._last_tip_at = -1e9
        self._last_corners: list[CameraNormPoint] = []
        self._from_markers = False  # D034: perspectiva já veio dos marcadores

    # --- controle --------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.phase in (Phase.CORNERS, Phase.VERIFY)

    def start(self, now: float) -> list[dict[str, Any]]:
        self.__post_init__()
        self.phase, self.result, self.message = Phase.CORNERS, None, ""
        self._started_at = now
        self._begin_step(now)
        return [{"event": "calibration_start", "countdown_s": self.countdown_s}]

    def start_from_markers(self, homography: Homography, now: float) -> list[dict[str, Any]]:
        """Calibração automática (D034): a perspectiva vem dos marcadores; falta só um
        toque no centro para medir quanto a ponta do dedo vista pela câmera fica
        deslocada do ponto encostado na tela."""
        self.__post_init__()
        self.phase, self.result, self.message = Phase.VERIFY, None, ""
        self._homography, self._from_markers = homography, True
        self._started_at = now
        self._begin_step(now)
        return [{"event": "calibration_start", "mode": "markers", "countdown_s": self.countdown_s}]

    def cancel(self) -> list[dict[str, Any]]:
        if not self.active:
            return []
        self.phase = Phase.CANCELLED
        return [{"event": "calibration_cancel", "step": self._step_number()}]

    # --- entradas --------------------------------------------------------------

    def on_tip(self, tip: CameraNormPoint | None, now: float) -> None:
        """Cada resultado do rastreamento (com ou sem mão)."""
        if tip is not None:
            self._last_tip, self._last_tip_at = tip, now
        if self.active and self._collecting(now):
            self._collector.add(tip)

    def tick(self, now: float) -> list[dict[str, Any]]:
        """Avança o tempo. Devolve eventos para o log de sessão."""
        if not self.active or now - self._step_start < self.countdown_s:
            return []
        return self._finish_step(now)

    # --- saída -----------------------------------------------------------------

    @property
    def captured_camera_points(self) -> list[CameraNormPoint]:
        """Cantos já aceitos nesta tentativa, em camera_norm (para o diagnóstico)."""
        return list(self._captured)

    def view(self, now: float) -> CalibrationView:
        elapsed = now - self._step_start
        verify = self.phase is Phase.VERIFY
        target = VERIFY_TARGET if verify else (
            self.targets[self._index] if self.phase is Phase.CORNERS else None)
        return CalibrationView(
            phase=self.phase,
            step=self._step_number(),
            target=target,
            target_name="centro (verificação)" if verify else (
                CORNER_NAMES[self._index] if self.phase is Phase.CORNERS else ""),
            remaining_s=max(0.0, self.countdown_s - elapsed) if self.active else 0.0,
            progress=min(1.0, max(0.0, elapsed / self.countdown_s)) if self.active else 0.0,
            collecting=self.active and self._collecting(now),
            finger_seen=now - self._last_tip_at < 0.3,
            message=self.message,
            captured=tuple(self.targets[: len(self._captured)]),
            title="Calibração automática: encoste uma vez no alvo do centro"
            if (verify and self._from_markers) else "",
        )

    # --- interno ---------------------------------------------------------------

    def _finish_from_markers(self, dx: float, dy: float, error: float, now: float) -> list[dict[str, Any]]:
        if not error <= config.CALIB_AUTO_MAX_OFFSET:  # também pega NaN
            # Deslocamento grande demais para ser só a ponta do dedo: calibra pelos cantos.
            self.message = "O toque não conferiu com os marcadores: vamos tocar os 4 cantos."
            self._rejections += 1
            self._from_markers = False
            self.phase, self._index, self._captured = Phase.CORNERS, 0, []
            self._begin_step(now)
            return [{"event": "calibration_markers_rejected",
                     "offset_dx": round(dx, 4), "offset_dy": round(dy, 4)}]
        shift = np.array([[1.0, 0.0, -dx], [0.0, 1.0, -dy], [0.0, 0.0, 1.0]])
        final = Homography(shift @ self._homography.matrix)
        self.result = CalibrationResult(
            homography=final, camera_points=[], surface_points=[], verify_error=(dx, dy),
            duration_s=now - self._started_at, rejections=self._rejections, mode="markers")
        self.phase = Phase.DONE
        return [{"event": "calibration_done", "mode": "markers", "matrix": final.as_list(),
                 "offset_dx": round(dx, 4), "offset_dy": round(dy, 4),
                 "duration_s": round(now - self._started_at, 1), "rejections": self._rejections}]

    def _homography_points(self) -> list[CameraNormPoint]:
        return list(self._last_corners)

    def _new_collector(self) -> PointCollector:
        return PointCollector(self.min_presence, self.max_spread)

    def _step_number(self) -> int:
        return 5 if self.phase is Phase.VERIFY else self._index + 1

    def _collecting(self, now: float) -> bool:
        return now - self._step_start >= self.countdown_s - self.collect_s

    def _begin_step(self, now: float) -> None:
        self._step_start = now
        self._collector = self._new_collector()

    def _finish_step(self, now: float) -> list[dict[str, Any]]:
        capture = self._collector.result()
        step = self._step_number()
        base = {"step": step, "frames": capture.frames, "with_hand": capture.with_hand,
                "spread": None if capture.spread is None else round(capture.spread, 4)}
        if not capture.accepted:
            self._rejections += 1
            self.message = REJECT_MESSAGES[capture.reason]
            self._begin_step(now)
            return [{"event": "calibration_point", "accepted": False,
                     "reason": capture.reason.value, **base}]

        point = capture.point
        events = [{"event": "calibration_point", "accepted": True,
                   "x": round(point.x, 4), "y": round(point.y, 4), **base}]
        self.message = ""
        if self.phase is Phase.CORNERS:
            self._captured.append(point)
            self._index += 1
            if self._index < len(self.targets):
                self._begin_step(now)
                return events
            self._last_corners = list(self._captured)
            try:
                self._homography = Homography.from_points(self._captured, self.targets)
            except CalibrationError as error:
                # Os 4 cantos não formam um quadrilátero válido: recomeça do 1º.
                self.message = f"{error}. Vamos recomeçar pelo primeiro canto."
                self._rejections += 1
                self._index, self._captured = 0, []
                self._begin_step(now)
                return events + [{"event": "calibration_invalid", "detail": str(error)}]
            self.phase = Phase.VERIFY
            self._begin_step(now)
            return events

        # Verificação no alvo central.
        surface = self._homography.to_surface(point)
        dx = (surface.x - VERIFY_TARGET.x) if surface else float("nan")
        dy = (surface.y - VERIFY_TARGET.y) if surface else float("nan")
        error = math.hypot(dx, dy)
        if self._from_markers:
            return events + self._finish_from_markers(dx, dy, error, now)
        if not error <= self.max_verify_error:  # também pega NaN
            self.message = (f"A verificação errou {100 * error:.0f}% da tela: os cantos não "
                            "conferem. Vamos recomeçar pelo primeiro canto.")
            self._rejections += 1
            self.phase, self._index, self._captured = Phase.CORNERS, 0, []
            self._begin_step(now)
            return events + [{"event": "calibration_verify_failed",
                              "verify_dx": round(dx, 4), "verify_dy": round(dy, 4),
                              "camera_points": [[round(p.x, 4), round(p.y, 4)]
                                                for p in self._homography_points()]}]
        self.result = CalibrationResult(
            homography=self._homography, camera_points=list(self._captured),
            surface_points=list(self.targets), verify_error=(dx, dy),
            duration_s=now - self._started_at, rejections=self._rejections)
        self.phase = Phase.DONE
        return events + [{
            "event": "calibration_done",
            "camera_points": [[round(p.x, 4), round(p.y, 4)] for p in self._captured],
            "surface_points": [[p.x, p.y] for p in self.targets],
            "matrix": self._homography.as_list(),
            "verify_dx": round(dx, 4), "verify_dy": round(dy, 4),
            "duration_s": round(now - self._started_at, 1), "rejections": self._rejections,
        }]
