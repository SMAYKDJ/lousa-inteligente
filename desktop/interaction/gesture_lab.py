"""Laboratório de gestos (tecla L, D024): mede a confiabilidade do reconhecimento.

Ideia do open-source-hands (MIT, "reliability test" do lab.html): o programa
pede cada gesto em sequência e mede, para o reconhecimento novo (D022) e o
antigo (D018), nos mesmos quadros:
- **acerto**: fração dos quadros com o gesto pedido, depois de 1 s (tempo para trocar a mão);
- **reação**: quanto tempo até o gesto ficar firme por 0,2 s;
- **confusões**: o que foi reconhecido no lugar.
A pinça é medida pela distância polegar↔indicador (só no novo; D021).

Serve para decidir com números: pinça × indicador esticado, mão de frente × de lado.

Puro (sem Qt): a janela entrega as amostras e desenha `view()`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from desktop import config

PROMPTS = (
    ("pointing", "Aponte só o indicador", "Indicador esticado, os outros dedos dobrados, como para escrever."),
    ("open", "Mão aberta", "Todos os dedos esticados."),
    ("fist", "Mão fechada", "Feche a mão."),
    ("pinch", "Pinça", "Encoste a ponta do polegar na ponta do indicador."),
    ("pointing", "Aponte de novo, com a mão de lado", "Como se escrevesse na lousa, de lado para a câmera."),
    ("open", "Mão aberta, de lado", "Todos os dedos esticados, de lado para a câmera."),
)
NAMES = {"pointing": "Apontar", "open": "Mão aberta", "fist": "Mão fechada", "pinch": "Pinça",
         "other": "outra", None: "sem mão"}


@dataclass
class _Prompt:
    target: str
    start: float
    samples: list[tuple[float, str | None, str | None]] = field(default_factory=list)  # (t, novo, antigo)


def _is_pinch(gap: float | None) -> bool:
    return gap is not None and gap < config.PINCH_ON_RATIO


@dataclass(frozen=True)
class LabView:
    kind: str  # "intro" (gesto pedido) ou "summary"
    title: str
    text: str
    step: int
    total: int
    seconds_left: float
    lines: tuple[str, ...] = ()


class GestureLab:
    def __init__(self, prompts=PROMPTS) -> None:
        self.prompts = prompts
        self.phase = "idle"  # idle, prompt, summary
        self.index = 0
        self.until = 0.0
        self.current: _Prompt | None = None
        self.results: list[dict] = []
        self.live: str | None = None  # gesto reconhecido agora (novo)

    @property
    def active(self) -> bool:
        return self.phase != "idle"

    def start(self, now: float) -> list[dict]:
        self.phase, self.index, self.results = "prompt", 0, []
        self._begin(now)
        return [{"event": "lab_start", "prompts": [p[0] for p in self.prompts]}]

    def _begin(self, now: float) -> None:
        self.current = _Prompt(self.prompts[self.index][0], now)
        self.until = now + config.LAB_PROMPT_S

    def on_sample(self, t: float, pose: str | None, pose_alt: str | None, pinch_gap: float | None) -> None:
        if self.phase != "prompt" or self.current is None:
            return
        if self.current.target == "pinch":
            pose = "pinch" if _is_pinch(pinch_gap) else pose
            pose_alt = None  # o antigo não mede pinça
        self.live = pose
        self.current.samples.append((t, pose, pose_alt))

    def tick(self, now: float) -> list[dict]:
        if self.phase == "summary" and now >= self.until:
            self.phase = "idle"
            return []
        if self.phase != "prompt" or now < self.until:
            return []
        result = self._score(self.current)
        self.results.append(result)
        events = [{"event": "lab_prompt", **result}]
        self.index += 1
        if self.index < len(self.prompts):
            self._begin(now)
        else:
            self.phase, self.until, self.current = "summary", now + config.LAB_SUMMARY_S, None
            events.append({"event": "lab_done", "results": self.results})
        return events

    def cancel(self) -> list[dict]:
        if not self.active:
            return []
        self.phase = "idle"
        return [{"event": "lab_cancel", "index": self.index}]

    def _score(self, p: _Prompt) -> dict:
        out = {"target": p.target}
        for engine, k in (("novo", 1), ("antigo", 2)):
            if p.target == "pinch" and engine == "antigo":
                continue
            window = [s for s in p.samples if s[0] - p.start >= config.LAB_SETTLE_S]
            hits = sum(1 for s in window if s[k] == p.target)
            reaction = None
            held_since = None
            for s in p.samples:
                if s[k] == p.target:
                    held_since = s[0] if held_since is None else held_since
                    if s[0] - held_since >= 0.2:
                        reaction = round(held_since - p.start, 2)
                        break
                else:
                    held_since = None
            confusions = Counter(s[k] for s in window if s[k] != p.target)
            out[engine] = {"hit": round(hits / len(window), 3) if window else None, "reaction_s": reaction,
                           "confusions": {str(c): n for c, n in confusions.most_common(3)}}
        return out

    def view(self, now: float) -> LabView | None:
        n = len(self.prompts)
        if self.phase == "prompt":
            target, title, text = self.prompts[self.index]
            now_text = NAMES.get(self.live, self.live)
            ok = "✓" if self.live == target else ""
            return LabView("intro", title, f"{text}\nReconhecido agora: {now_text} {ok}",
                           self.index + 1, n, max(0.0, self.until - now))
        if self.phase == "summary":
            lines = []
            for r in self.results:
                def fmt(x):
                    if x is None or x["hit"] is None:
                        return "—"
                    reaction = "—" if x["reaction_s"] is None else f"{x['reaction_s']:.1f} s"
                    return f"{100 * x['hit']:.0f}% ({reaction})"
                alt = f" · antigo {fmt(r.get('antigo'))}" if "antigo" in r else ""
                lines.append(f"{NAMES[r['target']]}: novo {fmt(r.get('novo'))}{alt}")
            return LabView("summary", "Laboratório de gestos — resultado",
                           "Acerto (tempo de reação), nos mesmos quadros.", 0, n, max(0.0, self.until - now),
                           tuple(lines))
        return None
