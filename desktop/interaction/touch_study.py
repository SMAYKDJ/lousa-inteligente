"""Estudo do toque na superfície (etapa 5.3, tecla T).

Hoje a caneta desce no ar (pose do indicador). Para saber se dá para
reconhecer "dedo encostado na lousa" só com os pontos da mão, o estudo pede,
em sequência, o mesmo gesto **encostado** e **no ar** (≈2 cm e ≈5 cm), parado
e arrastando, em pontos diferentes da lousa. Cada etapa vira um evento
`touch_phase` no log da sessão com o relógio monotônico (`mono_ms`), o mesmo
da gravação `--record`. Depois, `python -m tools.touch_report` cruza os dois e
mede quais sinais separam encostado × no ar. A decisão sai dos números.

Nenhuma imagem é gravada (CLAUDE.md §11): só os pontos da mão.

Puro (sem Qt): a janela chama `tick()` e desenha `view()`.
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop import config

# (rótulo, movimento, título, texto). Rótulos: touch = encostado; air2 / air5 = no ar.
_ROUND = (
    ("touch", "still", "Encoste o indicador no alvo e segure parado",
     "A ponta do dedo encostada na lousa, como para escrever."),
    ("air2", "still", "Agora a uns 2 cm do alvo, parado",
     "O mesmo dedo, sem encostar: um dedo de distância da lousa."),
    ("touch", "drag", "Encoste e arraste devagar sobre a linha",
     "Siga a linha de uma ponta à outra, sempre encostado."),
    ("air2", "drag", "A mesma linha a uns 2 cm, sem encostar",
     "Mesmo movimento, no ar, perto da lousa."),
    ("air5", "still", "A uns 5 cm do alvo, parado",
     "Mais longe: a largura de três dedos."),
)
#: Posições (fração da lousa) de cada rodada: alvo e linha mudam de lugar,
#: porque a perspectiva muda os sinais entre o centro e as bordas.
_SPOTS = ((0.5, 0.5), (0.25, 0.35), (0.75, 0.65))

LABELS = {"touch": "encostado", "air2": "no ar ~2 cm", "air5": "no ar ~5 cm"}


@dataclass(frozen=True)
class Prompt:
    label: str
    motion: str
    title: str
    text: str
    spot: tuple[float, float]


def build_prompts(rounds: int = config.TOUCH_STUDY_ROUNDS) -> tuple[Prompt, ...]:
    out = []
    for r in range(rounds):
        spot = _SPOTS[r % len(_SPOTS)]
        out.extend(Prompt(label, motion, title, text, spot) for label, motion, title, text in _ROUND)
    return tuple(out)


@dataclass(frozen=True)
class TouchView:
    kind: str  # "prepare" (mude a mão), "record" (gravando) ou "summary"
    title: str
    text: str
    step: int
    total: int
    seconds_left: float
    motion: str = "still"
    spot: tuple[float, float] = (0.5, 0.5)
    lines: tuple[str, ...] = ()


class TouchStudy:
    def __init__(self, prompts: tuple[Prompt, ...] | None = None) -> None:
        self.prompts = prompts if prompts is not None else build_prompts()
        self.phase = "idle"  # idle, prepare, record, summary
        self.index = 0
        self.until = 0.0
        self._record_start = 0.0
        self.frames = 0  # quadros com mão durante "record" (para avisar se a câmera não via)
        self._counts: list[int] = []

    @property
    def active(self) -> bool:
        return self.phase != "idle"

    def start(self, now: float) -> list[dict]:
        self.index, self._counts = 0, []
        self._prepare(now)
        return [{"event": "touch_study_start", "prompts": len(self.prompts),
                 "mono_ms": int(now * 1000)}]

    def _prepare(self, now: float) -> None:
        self.phase, self.until, self.frames = "prepare", now + config.TOUCH_STUDY_PREPARE_S, 0

    def on_sample(self, hand_present: bool) -> None:
        if self.phase == "record" and hand_present:
            self.frames += 1

    def tick(self, now: float) -> list[dict]:
        if self.phase == "idle" or now < self.until:
            return []
        if self.phase == "summary":
            self.phase = "idle"
            return []
        p = self.prompts[self.index]
        if self.phase == "prepare":
            self.phase, self._record_start = "record", now
            self.until = now + config.TOUCH_STUDY_RECORD_S
            return []
        # Fim da gravação desta etapa: o intervalo vai para o log.
        self._counts.append(self.frames)
        events = [{"event": "touch_phase", "index": self.index, "label": p.label, "motion": p.motion,
                   "spot": list(p.spot), "start_ms": int(self._record_start * 1000),
                   "end_ms": int(now * 1000), "hand_frames": self.frames}]
        self.index += 1
        if self.index < len(self.prompts):
            self._prepare(now)
        else:
            self.phase, self.until = "summary", now + config.TOUCH_STUDY_SUMMARY_S
            events.append({"event": "touch_study_done", "phases": len(self.prompts),
                           "hand_frames": self._counts})
        return events

    def cancel(self) -> list[dict]:
        if not self.active:
            return []
        self.phase = "idle"
        return [{"event": "touch_study_cancel", "index": self.index}]

    def view(self, now: float) -> TouchView | None:
        n = len(self.prompts)
        left = max(0.0, self.until - now)
        if self.phase in ("prepare", "record"):
            p = self.prompts[self.index]
            if self.phase == "prepare":
                return TouchView("prepare", p.title, p.text + "\nPosicione a mão; a gravação começa em seguida.",
                                 self.index + 1, n, left, p.motion, p.spot)
            text = "Gravando… mantenha até o fim." if p.motion == "still" else "Gravando… vá e volte na linha."
            return TouchView("record", p.title, text, self.index + 1, n, left, p.motion, p.spot)
        if self.phase == "summary":
            empty = sum(1 for c in self._counts if c < 10)
            lines = [f"{n} etapas gravadas.",
                     "Agora rode no Terminal: .venv/bin/python -m tools.touch_report"]
            if empty:
                lines.insert(1, f"Atenção: {empty} etapa(s) quase sem a mão na câmera.")
            return TouchView("summary", "Estudo do toque — concluído",
                             "Os pontos da mão foram gravados (sem imagem).", n, n, left, lines=tuple(lines))
        return None
