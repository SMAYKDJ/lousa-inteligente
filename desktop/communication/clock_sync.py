"""Estimativa da diferença entre o relógio do celular e o do notebook.

Serve só para MEDIR a latência ponta a ponta (captura no celular →
resultado no notebook). Nada de controle depende disso.

Método (o mesmo do NTP, simplificado): o notebook manda `ping` com o seu
horário t0; o celular responde `pong` com t0 e o próprio horário t_reply; o
notebook recebe em t1. Supondo ida e volta simétricas:

    offset = t_reply − (t0 + rtt/2),   rtt = t1 − t0

`offset` é "relógio do celular − relógio do notebook". Entre as últimas
amostras, vale a de menor RTT: é a menos afetada por atrasos do Wi-Fi.
Erro máximo da estimativa: ± rtt/2 dessa amostra (registrado no log).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

#: Quantas amostras recentes considerar.
SAMPLE_WINDOW = 10


@dataclass(frozen=True)
class ClockEstimate:
    offset_ms: float  # relógio do celular − relógio do notebook
    uncertainty_ms: float  # metade do RTT da amostra usada


class ClockSync:
    def __init__(self, window: int = SAMPLE_WINDOW) -> None:
        self._samples: deque[tuple[float, float]] = deque(maxlen=window)  # (rtt, offset)

    def add_sample(self, t_sent_ms: float, t_reply_ms: float, t_received_ms: float) -> None:
        rtt = t_received_ms - t_sent_ms
        if rtt < 0:
            return
        self._samples.append((rtt, t_reply_ms - (t_sent_ms + rtt / 2)))

    @property
    def estimate(self) -> ClockEstimate | None:
        if not self._samples:
            return None
        rtt, offset = min(self._samples)
        return ClockEstimate(offset_ms=offset, uncertainty_ms=rtt / 2)

    def to_local_ms(self, phone_ms: float) -> float | None:
        """Converte um horário do celular para o relógio do notebook."""
        est = self.estimate
        return None if est is None else phone_ms - est.offset_ms
