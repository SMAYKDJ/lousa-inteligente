# Sistema de gestos e interação (Fase 5)

`PROJECT_CONTEXT.md` §16 pede para a Fase 5: seleção de ferramentas, reconhecimento de gestos, diferenciação entre apontar e escrever, movimentação da sidebar e prevenção de comandos acidentais.

## O que já existe (Fases 3 e 4)

| Necessidade | Como é atendida | Onde |
|---|---|---|
| Selecionar ferramentas sem disparo acidental | permanência de 0,6 s com tolerância; aciona uma vez por entrada | `interaction/dwell.py` |
| Apontar × escrever | pose da mão: só o indicador esticado escreve (D018) | `vision/hand_tracker.py`, `interaction/pen_state.py` |
| Movimentar a sidebar | botão Mover + arrasto até o dedo parar | `interface/sidebar_model.py` |
| Comandos acidentais | "Limpar tudo?"; uma forma por seleção; caneta descida sobre a sidebar não risca | `interaction/confirm.py`, `drawing/tools.py`, `interaction/pen_gate.py` |
| Duas mãos | usa a que está junto à lousa (D016) | `core/hand_selection.py` |

## Cadeia de estados (CLAUDE.md §5.4)

1. Mão detectada (MediaPipe) → 2. mão escolhida (D016) → 3. pose classificada → 4. caneta confirmada em quadros seguidos (`PenState`) → 5. estado da interação (`PenGate`) → 6. ferramenta executa (`ToolController`) ou a interface reage (permanência).

### Estados da caneta (`interaction/pen_gate.py`)

| Estado | Quando | Risca? | Interface reage? |
|---|---|---|---|
| levantada | caneta no ar | não | sim |
| na_interface | desceu sobre a sidebar ou um painel | não | sim |
| bloqueada | continua descida depois de sair da interface | não | sim |
| riscando | desceu sobre a lousa com ferramenta de desenho | sim | não, até levantar |
| apontando | descida sobre a lousa com o Ponteiro | — | sim |

## Etapas

### 5.1 — Traços partidos ✅ testado (pytest); 📱 teste real pendente
- Problema (log `session-20261106-225003.jsonl`): 5 traços de 2 a 13 pontos em 3 s. A pose oscilava durante a escrita e levantava a caneta.
- Correção: com a caneta descida, a pose ambígua ("other") não levanta. Só mão aberta, fechada ou perdida levantam.
- Novo diagnóstico no log: `pen_up` com tempo descida, pose que levantou e estado. `tools.log_summary` mostra quantas descidas duraram menos de 0,3 s.
- Risco: se a mão sair da lousa numa pose ambígua, o traço continua até a mão abrir, fechar ou sumir.

### 5.2 — Estados explícitos ✅ testado (pytest)
- As regras da caneta saíram da janela para `PenGate`, com estados nomeados e testes próprios. O painel de diagnóstico mostra o estado.

### 5.3 — Estudo do toque na superfície (§9.3) — a fazer, com o usuário
Hoje a caneta desce no ar. Hipóteses a medir com dados reais, sem decidir antes:
- **Parada do dedo:** ao encostar, a ponta para na direção da lousa e o movimento fica mais estável.
- **Achatamento do dedo:** encostado, o indicador se dobra na ponta; a razão entre os segmentos do dedo muda.
- **Sombra (só com projetor):** a ponta encontra a própria sombra quando encosta.
- **2ª câmera rasante (hardware extra):** um celular na borda da lousa vê o dedo cruzar o plano.

Método: gravar sessões rotuladas ("encostado" × "no ar") pelo teclado, guardar só landmarks (sem imagens, CLAUDE.md §11) e comparar os sinais. A decisão sai dos números.

**Instrumento pronto (D029, 2026-11-07), 🔶 testado (pytest); 📱 coleta real pendente:**
- **Tecla T** na lousa: 15 etapas (~2 min). Em 3 lugares da lousa: encostado parado, ~2 cm parado, encostado arrastando, ~2 cm arrastando, ~5 cm parado. 3 s para posicionar a mão, 5 s gravando.
- A gravação dos pontos da mão liga sozinha (não precisa de `--record`); cada etapa vira `touch_phase` no log com o relógio da gravação.
- `python -m tools.touch_report`: para cada sinal (dobra da ponta, dobra do meio, ponta encurtada, profundidade da ponta, tremor) mostra a separação (AUC) e em quantas rodadas encostado ficou do mesmo lado que no ar. "Promissor" = AUC ≥ 0,8 e todas as rodadas coerentes.
- A sombra do dedo não entra: exigiria imagem, e não gravamos imagens.

### 5.4 — Pinça × indicador esticado (D021) — 🔶 testado (pytest); 📱 comparação real pendente
- Tecla K alterna; `--pen pinch` começa na pinça. Pinça: polegar↔indicador ÷ palma < 0,35 desce; > 0,50 sobe.
- Comparar no log (`tools.log_summary`, linha "Caneta"): descidas de menos de 0,3 s em cada modo.

### 5.5 — Reconhecimento adaptado do open-source-hands (D022) — 🔶 testado (pytest + simulação); 📱 comparação real pendente
- Filtro nos 21 pontos, forma 3D, dobra por ângulo, nota com histerese em ms. Cadeia de estados: mão → filtro → forma → nota por pose → pose estável → `PenState` → `PenGate`.
- O antigo roda em paralelo; `tools.log_summary` mostra trocas de pose por minuto de cada um.

### 5.6 — Gestos de movimento, gravação e laboratório (D024) — 🔶 testado (pytest); 📱 teste real pendente
- Deslizar ← → troca o slide (só mão aberta); toque de pinça clica; duas mãos em pinça/punho dão zoom no desenho selecionado. Tecla H.
- `--record` grava só os pontos da mão; `python -m tools.replay_landmarks` reproduz e compara.
- Tecla L: laboratório de gestos, com acerto e reação de cada reconhecimento.
