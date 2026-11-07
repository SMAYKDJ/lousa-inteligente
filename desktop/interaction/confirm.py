"""Pergunta de confirmação acionada por permanência (Fase 4: "Limpar tudo?").

Limpar apaga todas as anotações; um disparo acidental custaria caro, então
pede-se "Sim" explícito. Some sozinha depois de config.CLEAR_CONFIRM_S.
Puro (sem Qt): só retângulos em ui_px.
"""

from __future__ import annotations

from desktop import config
from desktop.interaction.dwell import Rect, Target

YES, NO = "confirm_yes", "confirm_no"


class ConfirmPrompt:
    def __init__(self, question: str, width: float, height: float, now: float,
                 timeout_s: float = config.CLEAR_CONFIRM_S) -> None:
        self.question = question
        self.expires_at = now + timeout_s
        button = config.SIDEBAR_BUTTON_FRAC * height * 1.4
        gap = button * 0.6
        box_w, box_h = 2 * button + 3 * gap, button + gap * 2 + button * 0.6
        self.box = Rect((width - box_w) / 2, (height - box_h) / 2, box_w, box_h)
        top = self.box.y + self.box.h - gap - button
        self.yes = Rect(self.box.x + gap, top, button, button)
        self.no = Rect(self.box.x + 2 * gap + button, top, button, button)

    def expired(self, now: float) -> bool:
        return now >= self.expires_at

    def targets(self) -> list[Target]:
        return [Target(YES, self.yes), Target(NO, self.no)]

    def contains(self, point: tuple[float, float] | None) -> bool:
        return point is not None and self.box.contains(*point)
