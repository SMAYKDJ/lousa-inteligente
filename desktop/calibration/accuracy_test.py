"""Teste de precisão da calibração: grade de 9 alvos (Fase 2, etapa 2.4).

Com a tela já calibrada, o professor encosta o dedo em cada alvo, com a mesma
contagem da calibração. Para cada ponto, mede a diferença entre onde o
sistema põe o dedo (homografia) e onde o alvo está. Isso mede a precisão em
toda a superfície, e não só no centro (docs/calibration.md §6).

Sem Qt e sem relógio próprio, como calibration_state.py.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

from desktop import config
from desktop.calibration.calibration_state import CalibrationView, Phase
from desktop.calibration.homography import Homography, SurfacePoint
from desktop.calibration.point_capture import REJECT_MESSAGES, PointCollector
from desktop.core.coordinate_mapper import CameraNormPoint


def grid_targets(margin: float = 0.15) -> list[SurfacePoint]:
    """3×3, linha a linha, de cima para baixo e da esquerda para a direita."""
    values = (margin, 0.5, 1.0 - margin)
    return [SurfacePoint(x, y) for y in values for x in values]


def verify_targets() -> list[SurfacePoint]:
    """Verificação (tecla V): 4 pontos ENTRE os 9 do teste G, onde a correção só interpola.

    O G repetido mede nos mesmos pontos usados para corrigir, e por isso sai
    otimista. Estes pontos mostram o erro real entre eles.
    """
    a, b = 0.325, 0.675
    return [SurfacePoint(a, a), SurfacePoint(b, a), SurfacePoint(a, b), SurfacePoint(b, b)]


@dataclass(frozen=True)
class AccuracySummary:
    errors: list[tuple[float, float]]  # (dx, dy) em surface_norm, um por alvo

    def errors_px(self, width: float, height: float) -> list[float]:
        return [math.hypot(dx * width, dy * height) for dx, dy in self.errors]

    def report(self, width: float, height: float) -> dict[str, Any]:
        px = self.errors_px(width, height)
        return {
            "errors_px": [round(e, 1) for e in px],
            "median_px": round(statistics.median(px), 1),
            "max_px": round(max(px), 1),
            "median_pct": round(100 * statistics.median(px) / width, 2),
            "max_pct": round(100 * max(px) / width, 2),
        }


@dataclass
class AccuracyTest:
    homography: Homography
    countdown_s: float = config.CALIBRATION_COUNTDOWN_S
    collect_s: float = config.CALIBRATION_COLLECT_S
    min_presence: float = config.CALIBRATION_MIN_PRESENCE
    max_spread: float = config.CALIBRATION_MAX_SPREAD
    targets: list[SurfacePoint] = field(default_factory=grid_targets)
    #: Conversão usada na medida. Padrão: só a homografia. A lousa passa a
    #: conversão completa (com a correção dos 9 pontos), para medir o que o
    #: professor de fato vê.
    to_surface: Callable[[CameraNormPoint], SurfacePoint | None] | None = None
    name: str = "Teste de precisão"

    phase: Phase = Phase.IDLE
    summary: AccuracySummary | None = None
    message: str = ""

    def __post_init__(self) -> None:
        self._index = 0
        self._step_start = 0.0
        self._errors: list[tuple[float, float]] = []
        self._collector = PointCollector(self.min_presence, self.max_spread)
        self._last_tip_at = -1e9

    @property
    def active(self) -> bool:
        return self.phase is Phase.CORNERS

    def start(self, now: float) -> list[dict[str, Any]]:
        self.__post_init__()
        self.phase, self.summary, self.message = Phase.CORNERS, None, ""
        self._begin(now)
        return [{"event": "accuracy_start", "points": len(self.targets), "name": self.name}]

    def cancel(self) -> list[dict[str, Any]]:
        if not self.active:
            return []
        self.phase = Phase.CANCELLED
        return [{"event": "accuracy_cancel", "step": self._index + 1}]

    def on_tip(self, tip: CameraNormPoint | None, now: float) -> None:
        if tip is not None:
            self._last_tip_at = now
        if self.active and now - self._step_start >= self.countdown_s - self.collect_s:
            self._collector.add(tip)

    def tick(self, now: float) -> list[dict[str, Any]]:
        if not self.active or now - self._step_start < self.countdown_s:
            return []
        capture = self._collector.result()
        step = self._index + 1
        if not capture.accepted:
            self.message = REJECT_MESSAGES[capture.reason]
            self._begin(now)
            return [{"event": "accuracy_point", "step": step, "accepted": False,
                     "reason": capture.reason.value}]
        target = self.targets[self._index]
        convert = self.to_surface or self.homography.to_surface
        surface = convert(capture.point)
        dx = surface.x - target.x if surface else float("nan")
        dy = surface.y - target.y if surface else float("nan")
        if not (surface and math.hypot(dx, dy) <= config.RESIDUAL_MAX_ERROR):
            # Longe demais do alvo: outra mão, o braço ou o dedo no lugar errado.
            # Repete o ponto em vez de estragar a medida (e a correção) inteira.
            # Teste real de 2026-11-06 23:56: um ponto com 562 px fez a correção ser recusada.
            self.message = "O dedo ficou longe do alvo: encoste de novo"
            self._begin(now)
            return [{"event": "accuracy_point", "step": step, "accepted": False, "reason": "too_far",
                     "dx": round(dx, 4) if surface else None, "dy": round(dy, 4) if surface else None}]
        self._errors.append((dx, dy))
        self.message = ""
        events = [{"event": "accuracy_point", "step": step, "accepted": True,
                   "target": [target.x, target.y],
                   "camera": [round(capture.point.x, 4), round(capture.point.y, 4)],
                   "dx": round(dx, 4), "dy": round(dy, 4)}]
        self._index += 1
        if self._index < len(self.targets):
            self._begin(now)
        else:
            self.summary = AccuracySummary(list(self._errors))
            self.phase = Phase.DONE
        return events

    def view(self, now: float) -> CalibrationView:
        elapsed = now - self._step_start
        target = self.targets[self._index] if self.active else None
        return CalibrationView(
            phase=self.phase, step=self._index + 1, target=target, target_name="",
            remaining_s=max(0.0, self.countdown_s - elapsed) if self.active else 0.0,
            progress=min(1.0, max(0.0, elapsed / self.countdown_s)) if self.active else 0.0,
            collecting=self.active and elapsed >= self.countdown_s - self.collect_s,
            finger_seen=now - self._last_tip_at < 0.3, message=self.message,
            captured=tuple(self.targets[: self._index]),
            title=f"{self.name} — ponto {self._index + 1} de {len(self.targets)}",
        )

    def _begin(self, now: float) -> None:
        self._step_start = now
        self._collector = PointCollector(self.min_presence, self.max_spread)
