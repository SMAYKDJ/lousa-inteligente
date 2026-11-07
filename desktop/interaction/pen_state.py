"""Estado da caneta a partir da pose da mão (Fase 4, D018) ou da pinça (D021).

Escolha do usuário (2026-11-06): só o indicador esticado ("pointing") escreve;
mão aberta ou fechada move sem riscar. Ainda não detectamos o toque na
superfície (R5), então a pose é o sinal de "caneta na lousa".

Confirmação em quadros seguidos (config.PEN_DOWN_FRAMES / PEN_UP_FRAMES): um
quadro com a pose errada não quebra o traço, e um quadro isolado de "apontar"
não começa um risco.
"""

from __future__ import annotations

from desktop import config


class PenState:
    def __init__(self, down_frames: int = config.PEN_DOWN_FRAMES,
                 up_frames: int = config.PEN_UP_FRAMES, mode: str = config.PEN_MODE,
                 hold_on_other: bool | None = None) -> None:
        self.down_frames, self.up_frames = down_frames, up_frames
        self.mode = mode  # "pose" (D018) ou "pinch" (D021)
        # "other" mantém a caneta descida só com o reconhecimento antigo (5.1). Com o
        # novo (D022), a histerese já está na pose; manter a caneta com "other" a
        # deixava presa por 18–63 s (teste real 2026-11-07 13:59): a mão relaxada
        # fica "sem pose" e a caneta não subia.
        self.hold_on_other = (config.GESTURE_ENGINE == "legacy") if hold_on_other is None else hold_on_other
        self.down = False
        self._streak = 0

    def reset(self) -> None:
        self.down, self._streak = False, 0

    def update(self, pose: str | None, pinch: float | None = None) -> bool:
        """Nova pose (None = sem mão). Devolve se a caneta está na lousa.

        Com a caneta descida, "other" (pose ambígua, comum na transição dos
        dedos ao escrever) é neutra: não conta para levantar. Só mão aberta,
        fechada ou perdida levantam. Teste real de 2026-11-06 22:57: traços se
        partiam em pedaços de 2 a 13 pontos.
        """
        if self.mode == "pinch":
            # Pinça (D021): histerese — desce abaixo de ON, só sobe acima de OFF.
            # Mão fechada nunca é pinça: o polegar fica perto do indicador (teste real 2026-11-07).
            if pinch is None or pose == "fist":
                wants_down = False
            elif self.down:
                wants_down = pinch < config.PINCH_OFF_RATIO
            else:
                wants_down = pinch < config.PINCH_ON_RATIO
        else:
            if self.down and pose == "other" and self.hold_on_other:
                return self.down
            wants_down = pose == "pointing"
        if wants_down == self.down:
            self._streak = 0
            return self.down
        self._streak += 1
        if self._streak >= (self.down_frames if wants_down else self.up_frames):
            self.down, self._streak = wants_down, 0
        return self.down
