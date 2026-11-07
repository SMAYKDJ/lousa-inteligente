"""Correção residual com os 9 pontos do teste G (malha adaptativa).

Depois da homografia sobra um erro que não é igual na superfície toda: lente,
dedo à frente da parede, imprecisão dos 4 cantos. O teste G mede esse erro em
9 pontos conhecidos (3×3). Esta correção guarda, em cada ponto da grade, o
deslocamento que leva a posição medida à posição verdadeira, e interpola
(bilinear) entre eles. Fora da grade, vale o deslocamento da borda mais próxima.

Tudo em surface_norm. Sem Qt.

Limites: não corrige a profundidade em si (dedo no ar × encostado); corrige o
erro médio de quem encostou o dedo na lousa durante o teste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from desktop import config

AXIS = (0.15, 0.5, 0.85)  # mesmas posições do teste G (accuracy_test.grid_targets)


def _segment(v: float) -> tuple[int, float]:
    """Índice do intervalo da grade e posição dentro dele (0–1), com bordas constantes."""
    if v <= AXIS[0]:
        return 0, 0.0
    if v >= AXIS[-1]:
        return len(AXIS) - 2, 1.0
    i = 0 if v < AXIS[1] else 1
    return i, (v - AXIS[i]) / (AXIS[i + 1] - AXIS[i])


@dataclass(frozen=True)
class ResidualCorrection:
    """offsets[linha][coluna] = (dx, dy) a somar ao ponto medido."""
    offsets: tuple[tuple[tuple[float, float], ...], ...]

    @classmethod
    def zero(cls) -> "ResidualCorrection":
        return cls(tuple(tuple((0.0, 0.0) for _ in AXIS) for _ in AXIS))

    @classmethod
    def from_errors(cls, errors: list[tuple[float, float]],
                    previous: "ResidualCorrection | None" = None) -> "ResidualCorrection":
        """`errors`: (dx, dy) medido − alvo, 9 pontos linha a linha (accuracy_test).

        O teste G já roda com a correção atual: a nova soma a anterior ao erro
        que ainda sobrou.
        """
        if len(errors) != 9:
            raise ValueError("a correção precisa dos 9 pontos")
        bad = [e for e in errors if not all(math.isfinite(v) for v in e)
               or math.hypot(*e) > config.RESIDUAL_MAX_ERROR]
        if bad:
            raise ValueError(f"{len(bad)} ponto(s) com erro grande demais para corrigir")
        base = previous or cls.zero()
        rows = []
        for r in range(3):
            row = []
            for c in range(3):
                dx, dy = errors[r * 3 + c]
                ox, oy = base.offsets[r][c]
                row.append((ox - dx, oy - dy))
            rows.append(tuple(row))
        return cls(tuple(rows))

    def offset(self, x: float, y: float) -> tuple[float, float]:
        ci, tx = _segment(x)
        ri, ty = _segment(y)
        o = self.offsets

        def lerp(a, b, t):
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        top = lerp(o[ri][ci], o[ri][ci + 1], tx)
        bottom = lerp(o[ri + 1][ci], o[ri + 1][ci + 1], tx)
        return lerp(top, bottom, ty)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = self.offset(x, y)
        return x + dx, y + dy

    def max_offset(self) -> float:
        return max(math.hypot(*v) for row in self.offsets for v in row)

    def nodes(self) -> list[tuple[float, float, float, float]]:
        """(x, y, dx, dy) de cada ponto da grade, para desenhar as setas."""
        return [(AXIS[c], AXIS[r], *self.offsets[r][c]) for r in range(3) for c in range(3)]
