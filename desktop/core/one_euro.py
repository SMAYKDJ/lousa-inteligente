"""Filtro One Euro (Casiez, Roussel e Vogel, CHI 2012) para o dedo.

Passa-baixa com corte adaptativo: com o dedo parado, o corte é baixo e o
tremor some; com o dedo rápido, o corte sobe e o atraso fica pequeno.
cutoff = min_cutoff + beta · |velocidade|.

Sem dependências. Com o tempo de cada amostra. Como no open-source-hands
(MIT, src/kit/oneEuro.ts): o intervalo entre amostras é limitado a 1 ms–100 ms
(protege contra carimbos de tempo repetidos e travadas), e o filtro 2D usa a
velocidade do vetor — dois filtros independentes atrasam mais o eixo lento e
entortam movimentos diagonais retos.
"""

from __future__ import annotations

import math

from desktop import config


MIN_DT, MAX_DT = 0.001, 0.1


def _alpha(cutoff_hz: float, dt: float) -> float:
    tau = 1.0 / (2 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuro:
    def __init__(self, min_cutoff: float = config.ONE_EURO_MIN_CUTOFF_HZ,
                 beta: float = config.ONE_EURO_BETA,
                 d_cutoff: float = config.ONE_EURO_D_CUTOFF_HZ) -> None:
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x: float | None = None
        self._dx = 0.0
        self._t: float | None = None

    def __call__(self, x: float, t: float) -> float:
        if self._x is None or self._t is None:
            self._x, self._t, self._dx = x, t, 0.0
            return x
        dt = min(MAX_DT, max(MIN_DT, t - self._t))
        self._t = t
        dx = (x - self._x) / dt
        self._dx = self._dx + _alpha(self.d_cutoff, dt) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x = self._x + _alpha(cutoff, dt) * (x - self._x)
        return self._x


class OneEuro2D:
    """2D com a velocidade do vetor: os dois eixos abrem juntos."""

    def __init__(self, min_cutoff: float = config.ONE_EURO_MIN_CUTOFF_HZ,
                 beta: float = config.ONE_EURO_BETA,
                 d_cutoff: float = config.ONE_EURO_D_CUTOFF_HZ) -> None:
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._p: tuple[float, float] | None = None
        self._d = (0.0, 0.0)
        self._t: float | None = None

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self._p is None or self._t is None:
            self._p, self._d, self._t = (x, y), (0.0, 0.0), t
            return x, y
        dt = min(MAX_DT, max(MIN_DT, t - self._t))
        self._t = t
        ad = _alpha(self.d_cutoff, dt)
        px, py = self._p
        dx = self._d[0] + ad * ((x - px) / dt - self._d[0])
        dy = self._d[1] + ad * ((y - py) / dt - self._d[1])
        self._d = (dx, dy)
        a = _alpha(self.min_cutoff + self.beta * math.hypot(dx, dy), dt)
        self._p = (px + a * (x - px), py + a * (y - py))
        return self._p
