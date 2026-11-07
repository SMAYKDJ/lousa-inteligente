"""Anotações por slide (Fase 6, escolha do usuário em 2026-11-06).

Cada slide tem a sua lousa (com o próprio histórico de Voltar/Avançar). Ao
avançar, aparece a lousa daquele slide (vazia na primeira vez); ao voltar,
reaparece o que foi escrito.

Limitação: o número do slide é contado pelos botões da sidebar. Se o slide for
trocado por outro meio (teclado, clique, controle remoto), a contagem fica
desencontrada. No primeiro slide, "anterior" não diminui a contagem.
"""

from __future__ import annotations

from desktop.drawing.board import Board


class SlideBook:
    def __init__(self) -> None:
        self.index = 0
        self._boards: dict[int, Board] = {0: Board()}

    @property
    def current(self) -> Board:
        return self._boards[self.index]

    def go(self, delta: int) -> Board:
        self.index = max(0, self.index + delta)
        return self._boards.setdefault(self.index, Board())

    def annotated(self) -> list[int]:
        """Slides (contando de 1) que têm anotações."""
        return [i + 1 for i, b in sorted(self._boards.items()) if b.items]
