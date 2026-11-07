# Interface da lousa — plano da Fase 3

**Status:** plano aprovado (permanência 0,8 s; botão à esquerda). 3.0 validada (D017). 3.2–3.4 implementadas; falta o teste real.
**Base:**
- `PROJECT_CONTEXT.md` §5 (overlay), §7 (sidebar aprovada), §8.2 (confirmação de seleção), §12 (apresentações) e Fase 3;
- `CLAUDE.md` §7 (interface) e §8 (estados).

**Objetivo da Fase 3:** a lousa passa a ser uma **camada transparente sobre a apresentação**, com a **sidebar aprovada** (botão circular, painel flutuante, animação, vertical/horizontal, reposicionamento), operada pelo dedo.

As ferramentas de desenho (pincel, borracha etc.) são da **Fase 4**. Na Fase 3, os botões existem e mudam a "ferramenta selecionada", mas ainda não desenham.

---

## 1. Pré-requisito: fechar a Fase 2

O tamanho mínimo dos botões depende da precisão medida. Antes de dimensionar a sidebar, é preciso:
- fazer o **teste G** (grade de 9 pontos) pelo menos uma vez, com o celular parado;
- registrar o erro mediano e o máximo.

**Regra proposta:** diâmetro do botão ≥ 3 × erro máximo, com mínimo de ~6% da altura da projeção (~65 px numa tela de 1080 px).

## 2. Janela da lousa: overlay transparente

Hoje a janela da lousa é opaca (fundo escuro). Na Fase 3 ela passa a ser:
- **sem moldura e com fundo transparente**: o slide fica visível por baixo;
- **sempre por cima** da apresentação;
- **transparente para o mouse**: o mouse do notebook continua controlando a apresentação por baixo. A lousa é operada só pelo dedo, via câmera;
- em tela cheia na tela da projeção (`--screen N`);
- desenhando só: a sidebar, o cursor do dedo, os marcadores ArUco (D015) e, durante a calibração, a tela de calibração (opaca).

**Risco principal (§12 do PROJECT_CONTEXT): ficar por cima de apresentações em tela cheia.**
- **macOS:** o PowerPoint e o Keynote em apresentação usam um "Space" próprio de tela cheia. Uma janela comum não aparece ali.
  - Pode exigir marcar a janela como auxiliar de tela cheia (`NSWindowCollectionBehavior`, via `pyobjc`). Isso seria uma dependência nova, a justificar.
  - A alternativa é usar a apresentação em modo janela maximizada.
- **Windows:** uma janela "topmost" costuma ficar sobre a apresentação do PowerPoint, mas isso precisa ser comprovado na etapa 1.7.

Por isso a primeira etapa é um **teste de viabilidade** (3.0), antes de qualquer interface.

## 3. Como o dedo "clica": tempo de permanência

O `PROJECT_CONTEXT.md` §8.2 exige que a seleção **não aconteça só porque a mão passou sobre o botão**. Ainda não detectamos o toque na superfície (R5, Fase 5), então a confirmação proposta é por **tempo de permanência**:

- **Ativação:** o dedo fica sobre o botão, e um **anel de progresso** se completa em **0,8 s** (configurável). Ao completar, o botão é acionado, com retorno visual (o botão "pisca" e muda de cor).
- **Tolerância:** pequenas oscilações do dedo, até ~1,5% da tela, não zeram o progresso. Sair do botão zera.
- **Repetição:** depois de acionar, o mesmo botão só aceita outro acionamento quando o dedo sair e voltar, para evitar disparo em cascata.
- **Arrastar** (barra e botão circular):
  1. permanência de 0,8 s na **alça de arrasto** "pega" a barra;
  2. a barra segue o dedo;
  3. parar ~0,8 s "solta" a barra no lugar.

  Durante o arrasto, nada mais é acionado.
- **Futuro (Fase 5):** gestos de confirmação (por exemplo, pinça) e detecção do toque podem substituir ou complementar a permanência.

## 4. Sidebar (padrão aprovado, §7)

**Estados** (CLAUDE.md §8): Recolhida → Abrindo → Expandida → Recolhendo, mais Arrastando.

| Elemento | Comportamento |
|---|---|
| **Botão circular** | Semitransparente, meio encaixado na borda; posição inicial a definir (§7). Permanência abre ou recolhe o painel. Sempre visível. |
| **Painel** | Semitransparente, desliza da borda (~200 ms) sem mexer na apresentação. Fica **vertical** (coluna) ou **horizontal** (linha). |
| **Ferramentas** | Ponteiro, Selecionar, Pincel, Borracha, Círculo, Retângulo, Voltar, Avançar, Limpar, Navegação (ícones). Na Fase 3: seleção e destaque da ferramenta atual. Voltar, Avançar e Limpar só registram o comando. |
| **Controles da barra** | Alternar vertical/horizontal; alça de arrasto; recolher. |
| **Limites** | A barra nunca fica parcialmente fora da projeção nem cobre os marcadores ArUco. |
| **Escrita × controles** | Enquanto o dedo está sobre a sidebar, nada é desenhado (regra para a Fase 4). |

A posição, a orientação e a ferramenta ficam preservadas durante a sessão.

## 5. Módulos (CLAUDE.md §3)

```
desktop/interaction/
└── dwell.py             # permanência: progresso, tolerância, acionar uma vez (puro, testável)
                         # (o arrasto ficou no sidebar_model.py: só a barra se arrasta por enquanto)
desktop/interface/
├── overlay_platform.py  # ajustes do macOS para ficar sobre a tela cheia (a janela é a cursor_window em modo overlay)
├── sidebar_model.py     # estados, orientação, posição, ferramenta, limites (sem Qt)
├── sidebar_view.py      # desenho e animação (Qt)
└── tool_icons.py        # ícones desenhados em código (sem imagens externas)
```

A janela atual (cursor + painel de métricas) continua disponível com `--debug-window`, para diagnóstico.

## 6. Etapas

| Etapa | Entrega | Validação |
|---|---|---|
| 3.0 | **Viabilidade do overlay:** janela transparente, que ignora o mouse e fica sempre por cima, sobre a apresentação em tela cheia (macOS agora; Windows na 1.7) | Mac + TV com PowerPoint/Keynote/navegador. Decisão D017 com o resultado |
| 3.1 | Lousa passa a ser o overlay: cursor, marcadores e calibração sobre o slide | Mac + TV |
| 3.2 | `dwell.py` + `drag.py` + testes | pytest |
| 3.3 | Sidebar: botão circular, abrir e recolher com animação, ferramentas, vertical/horizontal | Qt offscreen + Mac + TV |
| 3.4 | Arrastar a barra e o botão, com limites da projeção | Mac + TV |
| 3.5 | Testes de uso: acionar cada botão, falsos acionamentos, tempo para abrir e selecionar | log + relato |

**Métricas no log:**
- acionamentos por botão;
- tempo do dedo chegar até o acionamento;
- acionamentos cancelados (dedo saiu antes);
- arrastos.

## 7. Respostas do usuário (2026-11-06, 20:06)

1. **Permanência:** 0,8 s, aprovado; **reduzida para 0,6 s** depois do 1º teste (21:29).
2. **Botão circular na borda lateral esquerda**, no meio da altura. Com isso, a orientação inicial do painel é **vertical**.
3. **Programa de apresentação:** sem preferência. A etapa 3.0 testa o PowerPoint e o navegador (Google Slides) no Mac; o Windows fica para a etapa 1.7.
