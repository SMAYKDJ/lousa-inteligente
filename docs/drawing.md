# Desenho na lousa (Fase 4)

Decisão de base: **D018**. A caneta é a pose da mão: só o indicador esticado escreve.

## Módulos

| Arquivo | Responsabilidade |
|---|---|
| `desktop/vision/hand_tracker.py` | `finger_ratios` e `classify_pose`: pose da mão ("pointing", "open", "fist", "other") a partir dos landmarks |
| `desktop/interaction/pen_state.py` | `PenState`: caneta na lousa com confirmação em quadros seguidos |
| `desktop/drawing/board.py` | `Board`: anotações (traço, círculo, retângulo), borracha, voltar/avançar, limpar. Sem Qt |
| `desktop/drawing/tools.py` | `ToolController`: o que cada ferramenta faz com a caneta e o dedo; prévia; rastro do ponteiro. Sem Qt |
| `desktop/interaction/confirm.py` | `ConfirmPrompt`: "Limpar tudo?" com Sim/Não por permanência |
| `desktop/interface/drawing_view.py` | Desenho (Qt) das anotações, da prévia, do rastro, da borracha e da confirmação |
| `desktop/interface/cursor_window.py` | Liga tudo: pose → caneta → ferramenta → lousa; ações da sidebar |

## Coordenadas (CLAUDE.md §5.2)

- Anotações em **surface_norm** (x, y ∈ [0, 1] na área projetada). Não dependem do tamanho da janela.
- Conversão para a tela só no desenho (`drawing_view.py`): `x_px = x · largura`, `y_px = y · altura`. A janela cobre exatamente a projeção.
- Espessura, raio da borracha e espaçamento são frações da **altura** da lousa.

## Ferramentas

| Ferramenta | Caneta descida (indicador esticado) | Caneta levantada |
|---|---|---|
| Ponteiro | — (não risca) | rastro vermelho que some em 0,6 s |
| Pincel | risca, com suavização leve | termina o traço |
| Borracha | apaga o que está no círculo tracejado. Traços são cortados; formas tocadas no contorno saem inteiras | — |
| Círculo | centro onde desceu, borda no dedo (prévia) | cria o círculo |
| Retângulo | vértice onde desceu, oposto no dedo (prévia) | cria o retângulo |
| Selecionar | pega o desenho sob o dedo (o mais recente, se houver vários) e o arrasta; moldura verde tracejada | solta |
| Voltar / Avançar | desfaz / refaz a última ação (um gesto de borracha conta como uma ação) | |
| Limpar | pergunta "Limpar tudo?"; Sim apaga tudo e pode ser desfeito | |

Formas menores que 1% da altura são descartadas (toque acidental).

**Uma forma por seleção** (pedido do usuário após o teste real de 2026-11-06 22:02): concluído o círculo ou o retângulo, a ferramenta volta para o Ponteiro. Para outra forma, escolhe-se de novo na sidebar. Motivo: a pose oscilava na transição da mão e criava várias formas seguidas (4 retângulos em 1,2 s no log `session-20261106-215038.jsonl`).

A forma só é concluída se a caneta ficar levantada por 0,35 s (`config.SHAPE_RELEASE_S`). Se descer antes, continua a mesma forma.

## Selecionar (etapa 4.5)

- Pega um traço tocando nele, e um círculo ou retângulo tocando no contorno ou dentro. Distância máxima: 3% da altura (`config.SELECT_RADIUS_FRAC`).
- Só pega o que está sob o dedo **quando a caneta desce**. Passar por cima de um desenho no meio do movimento não o pega.
- Cada arrasto conta como uma ação: o Voltar devolve o desenho ao lugar.
- Log: `draw_move` com a distância em px.
- Ainda não: apagar, redimensionar ou selecionar vários de uma vez.

## Selecionar → redimensionar (etapa 4.6)

Pedido do usuário (2026-11-07): com o Selecionar, depois de pegar o desenho, abrir ou fechar a mão muda o tamanho. Confirmação escolhida: mão parada por 1 s.

1. Indicador esticado sobre o desenho: pega e arrasta (como na 4.5).
2. Ao soltar (mão aberta ou fechada), o desenho **continua selecionado**, com a moldura amarela e "Tamanho 100%".
3. Depois de 0,3 s (a mão sai da pose de apontar), a abertura atual vira a referência.
4. Abrir mais amplia e fechar reduz. Escala = (abertura ÷ referência)^1,5, entre 20% e 500%, em torno do centro do desenho.
5. Abertura parada por 1 s (o anel enche): o tamanho fica. Também confirmam: apontar de novo (que já pode pegar outro desenho), perder a mão ou trocar de ferramenta.
6. Cada redimensionamento é uma ação de Voltar. Se a mão ficar parada sem mudar o tamanho, nada entra no histórico.

- **Abertura da mão** (`hand_openness` em `vision/hand_tracker.py`): distância média do pulso às 5 pontas ÷ distância do pulso à base do dedo médio. Fechada ≈ 1, aberta ≈ 2. Não depende do tamanho aparente da mão nem da rotação.
- **Dica de uso:** soltar com a mão meio aberta deixa margem para ampliar e reduzir. Quem solta com a mão fechada só consegue ampliar.
- Sem câmera (mouse), não há abertura: soltar só termina o arrasto.
- **Log:** `draw_resize` com a escala e as aberturas de referência e final (para ajustar o ganho); `draw_resize_none` quando não mudou.
- **Limitação a observar no teste real:** se a mão demorar mais de 1 s para começar a abrir, o tamanho se confirma antes.

## Redimensionar pela distância da mão à câmera (D035)

Pedido do usuário (2026-11-07 16:43 e 16:49), com a ferramenta Selecionar:

1. **Indicador esticado sobre o desenho:** pega. Ir para os lados **move**.
2. **Ainda segurando**, aproximar a mão da câmera **amplia**; aproximar da lousa **reduz** — junto com o movimento.
3. **Abrir a mão:** solta. Posição e tamanho ficam como estão.
4. **Mão parada 1 s** (o anel enche): confirmado. Apontar de novo também confirma (e já pode pegar outro desenho).

- Sinal: tamanho aparente da palma (`palm_size_px`, pulso → base dos dedos, em px da câmera). Referência medida 0,15 s depois de pegar. Escala = (palma ÷ referência)^1,0, entre 20% e 500%, em torno do centro do desenho.
- Mover e redimensionar numa pegada só é **uma** ação de Voltar.
- Sem mão (mouse) ao soltar: confirma na hora.
- Duas mãos (D024) continua valendo durante a confirmação. Com o desenho seguro, **dois indicadores apontando** também fazem esse zoom (D038).
- Salto de mais de 18% na palma de um quadro para o outro = outra mão assumiu: o tamanho fica e a medida recomeça (D038).
- O jeito anterior (soltar e abrir/fechar a mão) volta com `RESIZE_SIGNAL = "openness"`.
- **Log:** `draw_move` e `draw_resize` com `signal: "size"`, `palm_ref` e `palm_end` (px).
- **A observar no teste real:** quando a mão vem para a câmera, a ponta do dedo também muda de lugar na imagem (perspectiva), então o desenho pode andar um pouco junto com o zoom. Girar a mão muda a palma aparente. Mão fora do quadro (perto demais): o tamanho atual fica.

## Cor, espessura e borracha (etapa 4.4, RF20/RF21)

Aprovado pelo usuário (2026-11-06): 5 cores, 3 tamanhos e um painel que abre ao lado da sidebar quando se escolhe Pincel ou Borracha.

- **Pincel:** vermelho (padrão), azul, verde, amarelo e preto; espessuras fina, média (padrão) e grossa. Círculo e retângulo usam a cor e a espessura do pincel.
- **Borracha:** pequena, média (padrão) e grande.
- Escolha por permanência, como na sidebar. O painel fecha ao começar a riscar, quando o dedo fica 1 s fora dele e da sidebar, ao trocar de ferramenta ou ao recolher a sidebar. Para mudar de novo, escolhe-se o Pincel outra vez.
- Não se risca sobre o painel.
- Cada traço guarda a cor e a espessura do momento em que foi feito.
- Módulos: `desktop/drawing/style.py` (estilo atual), `desktop/interface/style_panel.py` (layout do painel), `draw_style_panel` em `sidebar_view.py`.
- Log: `ui_style` com `color`, `width` ou `eraser`.

## Regras da interação

- A caneta só risca se **desceu fora da interface**. Quem acabou de apontar um botão da sidebar relaxa a mão antes de escrever.
- Um traço que entra na sidebar termina na borda; a sidebar não reage até a caneta levantar.
- Perder a mão levanta a caneta.
- Com "Limpar tudo?" aberta, nada risca.
- Sem câmera (sem `--overlay`), o botão esquerdo do mouse faz o papel da caneta.

## Log

`draw_stroke` (pontos), `draw_shape` (circle/rectangle), `draw_erase`, `draw_undo`/`draw_redo` (ok, itens), `ui_confirm` (yes/no/timeout).

## Limitações conhecidas

- A caneta desce no ar: não há detecção de toque (Fase 5).
- A pose só é calculada no modo stream.
- O preto some sobre slides de fundo escuro; não há cor branca.
- Anotações salvas por aula em `anotacoes/` (D027): recuperar com O, exportar PDF com E.
- Com muitos traços, o redesenho completo a cada quadro pode pesar. Medir antes de otimizar (CLAUDE.md §10).
