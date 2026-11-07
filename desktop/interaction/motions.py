"""Gestos de movimento na lousa (D024): deslizar, toque de pinça e zoom com duas mãos.

Adaptado de open-source-hands (Meticulai), licença MIT, © 2026 abouchedidxcode,
src/kit/motions.ts e engine.ts (updateTwo), commit dd79fb7.

Diferenças em relação ao kit:
- Tudo em **surface_norm** (coordenadas da lousa), não da câmera: a câmera do
  celular pode estar de lado ou espelhada em relação à lousa; "deslizar para a
  esquerda" tem de ser para a esquerda do professor diante da lousa.
- Deslizar só com a **mão aberta** (o kit só exclui o punho): na lousa, um traço
  rápido com o indicador não pode virar troca de slide.
- Só os gestos escolhidos pelo usuário (2026-11-07): deslizar ← →, toque de
  pinça e zoom com duas mãos.

Puro (sem Qt): recebe amostras e devolve eventos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from desktop import config


@dataclass(frozen=True)
class Sample:
    t: float  # s
    x: float  # surface_norm
    y: float
    pose: str | None  # pointing / open / fist / other
    pinch: float  # força da pinça 0..1 (zoom com duas mãos)
    gap: float | None = None  # polegar↔indicador ÷ palma (toque de pinça)


def pinch_strength(gap: float | None) -> float:
    """Distância polegar↔indicador ÷ palma → força 0..1 (kit: 1 − smoothstep(0,20; 0,42))."""
    if gap is None:
        return 0.0
    t = min(1.0, max(0.0, (gap - 0.20) / (0.42 - 0.20)))
    return 1 - t * t * (3 - 2 * t)


class MotionDetector:
    """Histórico curto da mão escolhida; `update` devolve os gestos detectados neste quadro."""

    def __init__(self) -> None:
        self.hist: list[Sample] = []
        self._cooldown: dict[str, float] = {}
        self._tap_closed_at: float | None = None
        self._tap_spoiled = False
        self._tap_frames = 0

    def reset(self) -> None:
        self.hist.clear()
        self._tap_closed_at = None

    def _back(self, now: float, s: float) -> Sample:
        """Amostra mais recente com pelo menos `s` segundos (ou a mais antiga)."""
        for sample in reversed(self.hist):
            if now - sample.t >= s:
                return sample
        return self.hist[0]

    def update(self, sample: Sample | None, busy: bool = False) -> list[dict]:
        """`busy`: duas mãos em uso (zoom) ou caneta riscando — não detecta deslizar."""
        if sample is None:
            self.reset()
            return []
        now = sample.t
        self.hist.append(sample)
        while self.hist and now - self.hist[0].t > config.MOTION_HISTORY_S:
            self.hist.pop(0)
        events = []
        swipe = None if busy else self._swipe(now)
        if swipe and now >= self._cooldown.get("swipe", 0.0):
            self._cooldown["swipe"] = now + config.MOTION_COOLDOWN_S
            events.append(swipe)
            self.hist = [sample]  # como no kit: limpa o histórico ao disparar
        tap = self._tap(sample)
        if tap:
            events.append(tap)
        return events

    def _swipe(self, now: float) -> dict | None:
        cur = self.hist[-1]
        old = self._back(now, config.SWIPE_WINDOW_S)
        if now - old.t < config.SWIPE_WINDOW_S * 0.4:
            return None
        # só com a mão aberta durante o movimento todo (um traço rápido não é deslizar)
        recent = [s for s in self.hist if now - s.t <= config.SWIPE_WINDOW_S]
        if any(s.pose != "open" for s in recent):
            return None
        dx, dy = cur.x - old.x, cur.y - old.y
        if abs(dx) < config.SWIPE_DISTANCE or abs(dx) < abs(dy) * config.SWIPE_AXIS_RATIO:
            return None
        return {"event": "motion_swipe", "direction": "left" if dx < 0 else "right", "distance": round(abs(dx), 3)}

    def _tap(self, cur: Sample) -> dict | None:
        """Pinça fechada e aberta em pouco tempo, sem a mão fechada no meio.

        O kit usa a força da pinça (fecha > 0,75, abre < 0,40). Na gravação real de
        2026-11-07 isso gerou 11 toques falsos ao fechar a mão (o polegar encosta no
        indicador dobrado). Aqui: distância < 0,18 para fechar, > 0,33 para abrir, e
        qualquer quadro com a mão fechada anula o toque — 0 falsos na mesma gravação.
        Gravação de 13:35: falhas de 1 quadro só → a pinça precisa aparecer fechada em
        pelo menos 2 quadros (17 falsos → 0).
        """
        if cur.gap is None:
            self._tap_closed_at = None
            return None
        if self._tap_closed_at is None:
            if cur.gap < config.TAP_CLOSE_GAP and cur.pose != "fist":
                self._tap_closed_at, self._tap_spoiled, self._tap_frames = cur.t, False, 1
            return None
        if cur.pose == "fist":
            self._tap_spoiled = True
        if cur.gap < config.TAP_CLOSE_GAP:
            self._tap_frames += 1
        if cur.gap > config.TAP_OPEN_GAP:
            closed_for = cur.t - self._tap_closed_at
            self._tap_closed_at = None
            if (closed_for <= config.TAP_MAX_S and not self._tap_spoiled
                    and self._tap_frames >= config.TAP_MIN_CLOSED_FRAMES):
                return {"event": "motion_tap", "closed_s": round(closed_for, 3)}
        return None


class TwoHandZoom:
    """Duas mãos "pegando" (as duas em pinça ou as duas fechadas): a razão entre a distância
    atual e a do início é o zoom. Devolve None quando não há pegada com duas mãos."""

    def __init__(self) -> None:
        self.grip = ""
        self.d0 = 0.0

    @staticmethod
    def _grip(pose: str | None, pinch: float) -> str:
        return "pinch" if pinch > 0.7 else "fist" if pose == "fist" else ""

    def update(self, hands: list[tuple[float, float, str | None, float]]) -> float | None:
        """`hands`: (x, y, pose, força da pinça) de cada mão, em surface_norm."""
        if len(hands) < 2:
            self.grip = ""
            return None
        a, b = hands[0], hands[1]
        g = self._grip(a[2], a[3])
        g = g if g and g == self._grip(b[2], b[3]) else ""
        d = math.hypot(a[0] - b[0], a[1] - b[1])
        if g != self.grip:
            self.grip, self.d0 = g, d
        if not g or self.d0 < 1e-3:
            return None
        return d / self.d0
