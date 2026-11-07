"""Quando a caneta pode riscar e quando a interface pode reagir (Fase 5, CLAUDE.md §5.4 e §8).

Estados explícitos. "Caneta" aqui é o sinal já confirmado em quadros seguidos
(pen_state.py): indicador esticado ou, sem câmera, o botão do mouse.

- LEVANTADA: caneta no ar; a sidebar reage ao dedo (permanência).
- NA_INTERFACE: desceu sobre a sidebar ou um painel; não risca. Quem aponta um
  botão precisa relaxar a mão antes de escrever, senão sairia um risco da
  sidebar até o ponto de escrita.
- BLOQUEADA: continua descida depois de sair da interface; não risca até levantar.
- RISCANDO: desceu sobre a lousa com uma ferramenta de desenho; a interface
  não reage até levantar (um traço que passa pela sidebar não aciona botão).
- APONTANDO: descida sobre a lousa com uma ferramenta que não risca (Ponteiro).

Puro: sem Qt, testável isoladamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateState(str, Enum):
    UP = "levantada"
    ON_UI = "na_interface"
    BLOCKED = "bloqueada"
    DRAWING = "riscando"
    POINTING = "apontando"


@dataclass(frozen=True)
class GateResult:
    pen: bool  # caneta efetiva para as ferramentas
    dwell: bool  # a interface pode reagir ao dedo
    started: bool = False  # começou a riscar neste quadro
    ended: bool = False  # parou de riscar neste quadro


class PenGate:
    def __init__(self) -> None:
        self.state = GateState.UP

    def update(self, raw_pen: bool, over_ui: bool, has_point: bool, drawing_tool: bool) -> GateResult:
        previous = self.state
        if not raw_pen:
            self.state = GateState.UP
            return GateResult(pen=False, dwell=True, ended=previous is GateState.DRAWING)
        if previous is GateState.DRAWING:
            return GateResult(pen=True, dwell=False)
        if previous in (GateState.ON_UI, GateState.BLOCKED) or over_ui:
            self.state = GateState.ON_UI if over_ui else GateState.BLOCKED
            return GateResult(pen=False, dwell=True)
        if drawing_tool and has_point:
            self.state = GateState.DRAWING
            return GateResult(pen=True, dwell=False, started=True)
        self.state = GateState.POINTING
        return GateResult(pen=True, dwell=True)
