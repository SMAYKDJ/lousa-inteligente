"""Assistente de calibração: as etapas em ordem, uma de cada vez (pedido do usuário, 2026-11-07).

Ao abrir o programa:
  1. Cantos (C): calibração dos 4 cantos.
  2. Verificação sem correção (V): erro em 4 pontos entre os da grade.
  3. Correção pelos 9 pontos (G): mede e cria a correção.
  4. Verificação com correção (V): mede de novo nos mesmos 4 pontos.
  Resumo: antes × depois.

Antes de cada etapa, um cartão com a instrução fica na tela por config.GUIDED_INTRO_S.
A etapa seguinte só começa quando a anterior termina. Esc cancela o assistente.

Puro (sem Qt): a janela pergunta `tick()` qual etapa iniciar e avisa `step_done()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop import config


@dataclass(frozen=True)
class Step:
    key: str  # "corners", "verify_before", "grid", "verify_after"
    title: str
    instruction: str


STEPS = (
    Step("corners", "Calibrar os cantos da tela",
         "Encoste a ponta do indicador em cada alvo dos 4 cantos e segure parado até o círculo completar."),
    Step("verify_before", "Medir a precisão (sem correção)",
         "4 alvos entre os pontos da grade. Encoste e segure como antes: o sistema só mede, não muda nada."),
    Step("grid", "Corrigir pelos 9 pontos",
         "9 alvos pela tela. O erro medido em cada um vira a correção. Se o dedo ficar longe do alvo, o ponto é repetido."),
    Step("verify_after", "Medir a precisão (com correção)",
         "Os mesmos 4 alvos do passo 2, agora com a correção ligada: mostra quanto melhorou."),
)


@dataclass(frozen=True)
class GuidedView:
    kind: str  # "intro" ou "summary"
    title: str
    text: str
    step: int  # 1..N (0 no resumo)
    total: int
    seconds_left: float
    lines: tuple[str, ...] = ()


@dataclass
class GuidedSetup:
    steps: tuple[Step, ...] = STEPS
    phase: str = "idle"  # idle, intro, running, summary
    index: int = 0
    until: float = 0.0
    results: dict[str, dict] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.phase != "idle"

    @property
    def current(self) -> Step | None:
        return self.steps[self.index] if self.phase in ("intro", "running") else None

    def start(self, now: float) -> list[dict]:
        self.phase, self.index, self.results = "intro", 0, {}
        self.until = now + config.GUIDED_INTRO_S
        return [{"event": "guided_start", "steps": [s.key for s in self.steps]}]

    def tick(self, now: float) -> str | None:
        """Etapa a iniciar agora (fim do cartão de instrução), ou None."""
        if self.phase == "intro" and now >= self.until:
            self.phase = "running"
            return self.steps[self.index].key
        if self.phase == "summary" and now >= self.until:
            self.phase = "idle"
        return None

    def step_done(self, key: str, result: dict, now: float) -> list[dict]:
        if self.phase != "running" or self.steps[self.index].key != key:
            return []  # teste avulso (tecla), fora do assistente
        self.results[key] = result
        events = [{"event": "guided_step", "step": key, **result}]
        self.index += 1
        if self.index < len(self.steps):
            self.phase, self.until = "intro", now + config.GUIDED_INTRO_S
        else:
            self.phase, self.until = "summary", now + config.GUIDED_SUMMARY_S
            events.append({"event": "guided_done", **self.summary_numbers()})
        return events

    def cancel(self) -> list[dict]:
        if not self.active:
            return []
        step = self.steps[self.index].key if self.index < len(self.steps) else None
        self.phase = "idle"
        return [{"event": "guided_cancel", "step": step}]

    def summary_numbers(self) -> dict:
        before = self.results.get("verify_before", {}).get("median_px")
        after = self.results.get("verify_after", {}).get("median_px")
        out = {"corners_error_px": self.results.get("corners", {}).get("error_px"),
               "verify_before_px": before, "verify_after_px": after,
               "grid_median_px": self.results.get("grid", {}).get("median_px"),
               "correction": self.results.get("grid", {}).get("correction")}
        if before is not None and after is not None:
            if before > 0:
                out["improvement_pct"] = round(100 * (before - after) / before)
            else:  # erro zero antes: qualquer erro depois é piora
                out["improvement_pct"] = 0 if after <= 0 else -100
        return out

    def view(self, now: float) -> GuidedView | None:
        n = len(self.steps)
        if self.phase == "intro":
            s = self.steps[self.index]
            return GuidedView("intro", s.title, s.instruction, self.index + 1, n, max(0.0, self.until - now))
        if self.phase == "summary":
            return GuidedView("summary", "Calibração concluída", "A lousa está pronta para uso.",
                              0, n, max(0.0, self.until - now), tuple(self._summary_lines()))
        return None

    def _summary_lines(self) -> list[str]:
        r = self.summary_numbers()

        def px(v):
            return "—" if v is None else f"{v:.0f} px"
        lines = [f"Cantos: erro no centro {px(r['corners_error_px'])}",
                 f"Antes da correção: erro típico {px(r['verify_before_px'])}",
                 f"Depois da correção: erro típico {px(r['verify_after_px'])}"]
        if "improvement_pct" in r:
            change = r["improvement_pct"]
            if change >= 0:
                lines.append(f"Melhora: {change}%")
            else:
                lines.append(f"A correção piorou {-change}% e foi desligada (R liga de novo)")
        if r["correction"] == "recusada":
            lines.append("A correção dos 9 pontos não foi aplicada")
        return lines
