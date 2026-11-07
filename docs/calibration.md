# Calibração espacial — plano da Fase 2

**Status:** etapas 2.1–2.3 implementadas e testadas em simulação (2026-11-06). Falta o teste real (Mac + TV + celular). Critério de precisão provisório: o proposto no §6, até ser medido.
**Base:** `PROJECT_CONTEXT.md` §9 e Fase 2; decisão proposta D014; Fase 1 com o processamento no notebook (D013).

**Objetivo:** o cursor aparece **sob a ponta do dedo** na superfície projetada, com precisão suficiente para selecionar as ferramentas flutuantes.

---

## 1. Por que o cursor hoje fica "perto", mas não na ponta

Na Fase 1, o `StretchMapper` estica a imagem **inteira** da câmera sobre a tela. Mas a projeção ocupa só uma parte da imagem da câmera, e a câmera a vê de lado, como um trapézio e não como um retângulo. A calibração descobre onde a projeção está na imagem e corrige posição, escala, rotação e perspectiva de uma vez, por **homografia**.

## 2. Abordagem escolhida: o professor marca os cantos com o próprio dedo, com tempo (definida pelo usuário em 2026-11-06)

1. Ao **abrir o programa**, ou quando o professor aciona **Calibrar perspectiva da tela** (tecla **C**; botão na interface futura), entra o modo de calibração.
   - Calibra-se **sempre que o programa abre**, decisão do usuário. Não há calibração salva entre sessões.
2. **Na lousa** aparece o 1º alvo em cruz, a 5% da borda, com um **relógio de contagem regressiva** ao lado.
3. O professor encosta a ponta do indicador no centro do alvo e **mantém o dedo ali até o tempo acabar**.
4. Quando o tempo acaba, o sistema registra a posição da ponta do indicador na imagem da câmera e passa ao próximo alvo, que já inicia a própria contagem.
5. **Ordem** definida pelo usuário: **superior esquerdo → inferior esquerdo → inferior direito → superior direito**.
6. Com os 4 pares (ponta do dedo na câmera ↔ alvo na tela), o notebook calcula a homografia (`cv2.getPerspectiveTransform`).
7. **Verificação:** um 5º alvo aparece no centro, com a mesma contagem. O erro entre o ponto previsto e o alvo vai para a tela e para o log. **Acima de 5% da tela, a calibração recomeça automaticamente.** Esse limite foi acrescentado depois do 1º teste real, em que um erro de 54% tinha sido aceito.
8. **Janela de diagnóstico** na tela do notebook: imagem da câmera ao vivo, ponta detectada, cantos capturados e contorno calibrado. A imagem não é gravada.

**Vantagens:**
- O professor não sai da lousa.
- A calibração usa a mesma coisa que vai ser rastreada depois, a ponta do indicador encostada na superfície. Assim, a diferença entre a ponta real do dedo e o ponto que o MediaPipe chama de "ponta" é absorvida pela própria calibração.

### 2.1. Como cada ponto é capturado (detalhes técnicos, a validar)

- **Duração da contagem:** **7 s por alvo**, definida pelo usuário e ajustável em `config.py` (`CALIBRATION_COUNTDOWN_S`).
- **Coleta:** nos últimos 0,5 s da contagem, o sistema junta as posições da ponta do indicador e usa a **mediana**, mais robusta a um quadro errado que o último quadro isolado.
- **Ponto aceito somente se:**
  - a mão foi detectada em pelo menos 70% dos quadros da janela de coleta;
  - o dedo esteve parado: dispersão abaixo de um limite em `camera_norm`.
- **Ponto rejeitado:** aparece um aviso na lousa ("não vi o dedo parado no alvo") e **a contagem do mesmo alvo recomeça**.
- **Retorno visual na lousa:**
  - título com o canto (por exemplo, "canto 3 de 4 (inferior direito)");
  - anel de progresso em volta da cruz, que fica verde na coleta;
  - contagem em números grandes ao lado do alvo;
  - "Dedo visto pela câmera ✓" ou "Dedo não visto";
  - cantos já aceitos em verde.
- **Por que não mostrar a posição do dedo:** antes da calibração ela cairia no lugar errado da tela e confundiria o professor.
- **Escape:** se a câmera não enxergar o dedo em algum canto (por oclusão, por exemplo), a **marcação manual** com clique na imagem da câmera, no notebook, continua disponível como reserva. Ela é a versão anterior desta proposta.

### 2.2. Telas envolvidas

| | Desenvolvimento | Sala de aula |
|---|---|---|
| Alvos, contagem, cursor | Smart TV (`--screen 1`) | projetor |
| Estado e mensagens; marcação manual de reserva | tela do Mac | tela do notebook |

## 2.3. Correção automática do movimento da câmera — marcadores ArUco (D015)

- Fora da calibração com o dedo, a lousa mostra **4 marcadores ArUco** (ids 0–3) nos cantos, com margem branca. O tamanho é 12% do menor lado da tela (`MARKER_SIZE_FRAC`).
- Logo depois da calibração, a posição dos marcadores na câmera vira a **referência**. A janela de diagnóstico mostra os marcadores em azul.
- A cada 3 quadros, a thread de visão procura os marcadores e calcula quanto a câmera se moveu desde a referência. O cursor usa `H_dedo · T`, com `T = H_marc_ref⁻¹ · H_marc_agora`.
- A correção é atualizada com **3 ou mais** marcadores, ou com **2 em cantos opostos**. Com menos, ou com 2 do mesmo lado (mão cobrindo, por exemplo), a última correção é mantida.
- **Referência:** exige ≥ 3 marcadores.
- **Saltos** maiores que 2% só valem após 3 leituras seguidas que concordam entre si. Isso evita pulos do cursor por leituras parciais (ajuste depois do 1º teste real).
- Se os marcadores não forem vistos em 3 s após a calibração, aparece um aviso e a correção fica desligada: será preciso recalibrar (C) quando o celular se mover.
- **No log:**
  - `markers`: taxa de detecção por id e tamanho em px na câmera, por segundo;
  - `marker_reference`;
  - `camera_moved`: deslocamento.
- **Para desligar:** `--no-markers`.
- **Pendente:** marcadores mais discretos (pedido do usuário). Depende de mais resolução na câmera; ver `testing.md`.

## 3. Sistemas de coordenadas (CLAUDE.md §5.2)

| Sistema | Definição | Novo na Fase 2? |
|---|---|---|
| `camera_norm` | x, y ∈ [0, 1] sobre o quadro da câmera | não |
| `surface_norm` | x, y ∈ [0, 1] sobre a **área projetada** (0,0 = canto superior esquerdo da projeção) | **sim** |
| `ui_px` | pixels da janela de projeção | não |

Conversões, sempre explícitas:
- `camera_norm --H--> surface_norm`: homografia calibrada;
- `surface_norm × tamanho da janela --> ui_px`.

Quando o dedo está **fora** da área projetada (`surface_norm` fora de [0, 1]), o cursor some: não está "na lousa".

## 4. Módulos (separação de responsabilidades, CLAUDE.md §3)

```
desktop/calibration/
├── homography.py          # cálculo, validação e aplicação da homografia (puro, testável)
├── point_capture.py       # janela de coleta: mediana, % com mão, estabilidade (puro, testável)
└── calibration_state.py   # máquina de estados: contagem, alvo atual, aceita/rejeita, sem Qt
desktop/core/coordinate_mapper.py   # + HomographyMapper (substitui o StretchMapper quando houver calibração)
desktop/interface/
├── cursor_window.py       # + modo de calibração: alvos, contagem, anel de progresso na projeção
└── calibration_window.py  # (reserva) marcação manual na imagem da câmera, no notebook
```

**Estados da calibração** (CLAUDE.md §8): Não calibrado → Contagem no alvo *n*/4 → Coletando → (Ponto aceito → próximo alvo | Ponto rejeitado → mesma contagem) → Calculada → Verificando → Calibrado (ou Cancelada).

Sem calibração, o cursor não é mostrado como "na lousa": o mapeamento provisório da Fase 1 fica só para diagnóstico.

**Validação da homografia antes de aceitar:**
- os 4 pontos são distintos;
- o quadrilátero é convexo e está na ordem certa;
- a área é maior que um mínimo;
- a matriz não é singular.

Se algo falhar, a mensagem diz o que corrigir.

## 5. Limitações conhecidas (a medir, não supor)

1. **Altura do dedo (paralaxe).** A homografia é exata **no plano da superfície**. Com o dedo afastado da lousa, a câmera o vê projetado sobre outro ponto. O erro cresce com a distância do dedo à superfície e com o ângulo da câmera. Esse erro será medido com o dedo encostado e a ~2 cm e ~5 cm. É o início da investigação do toque (`PROJECT_CONTEXT.md` §9.3, risco R5).
2. **Resolução.** Com quadros de 360×640, cada pixel da câmera corresponde a vários pixels da projeção. Se o erro medido for grande, é possível testar quadros maiores (`&side=960`), medindo o impacto na latência.
3. **Câmera movida.** Invalida a calibração e exige recalibrar com a tecla C. Detectar isso automaticamente fica para depois (§7).
6. **Dedo nos cantos.** Perto da borda da imagem, a mão pode sair parcialmente do quadro e o MediaPipe perder o rastreamento. A margem de 5% ajuda, e a regra de aceite (§2.1) evita registrar um ponto ruim.
4. **Oclusão.** A mão ou o corpo do professor podem esconder o indicador da câmera. A posição da câmera é parte da montagem e será documentada.
5. **Distorção da lente.** A homografia supõe uma lente sem distorção. Na grande-angular de celulares, a borda pode curvar. Isso será medido com uma grade de 9 pontos (§6) e só corrigido se fizer diferença.

## 6. Testes

**Automatizados (CLAUDE.md §9.1):**
- homografia conhecida → pontos convertidos corretamente (ida e volta);
- pontos fora da área → "fora da lousa";
- quadriláteros inválidos (repetidos, cruzados, colineares) → rejeitados com mensagem;
- coleta do ponto: mediana correta; rejeição sem mão ou com o dedo em movimento;
- máquina de estados com relógio falso: ordem dos 4 alvos, contagem, aceite, rejeição e repetição, cancelamento, verificação;
- desenho dos alvos e da contagem em Qt sem tela (offscreen).

**Reais, medidos pelo log:**
- **Precisão:** grade de **9 alvos** na projeção. O professor toca cada um, e o erro (px e % da largura) vai para o log (evento `calibration`). Medido com o dedo encostado e afastado.
- **Ângulos** (`PROJECT_CONTEXT.md`, entregas da Fase 2): câmera de frente, a ~30° e a ~45°.
- Tempo total para calibrar (com 3 s por alvo, ~15–20 s sem repetições) e quantas repetições aconteceram.

**Critério de aceite proposto para a Fase 2 (a confirmar com o usuário):** com o dedo encostado na superfície e a câmera a até ~30°, erro mediano ≤ **1% da largura da projeção** (≈ 19 px numa tela de 1920 px) e máximo ≤ **2%** nos 9 alvos. Esse é um ponto de partida: o tamanho mínimo dos botões da sidebar (Fase 3) deve ser definido a partir do erro medido aqui.

## 7. Depois (opcional, cada item com decisão própria)

- **Detecção automática dos cantos:**
  - método: projetar tela branca e tela preta e subtrair as duas (a luz ambiente se cancela), depois achar o quadrilátero e refinar os cantos;
  - alternativa: marcadores ArUco, já disponíveis no `opencv-contrib-python` instalado;
  - a marcação manual continua como reserva.
- **Câmera do notebook como fonte de quadros**, alternativa ao celular, sem passar pela rede. Vale só quando a webcam enxerga a lousa: com a mesa no canto, a webcam geralmente aponta para o professor, e o ângulo pode ser inviável.
- **Aviso de câmera movida:** comparar a imagem atual com a imagem da calibração.

## 8. Etapas propostas

| Etapa | Entrega | Validação |
|---|---|---|
| 2.0 | Fechar a Fase 1 (relatório) + JPEG em Web Worker no celular | log: `encode_ms` e latência antes/depois |
| 2.1 | `homography.py` + `point_capture.py` + máquina de estados + testes | pytest |
| 2.2 | Calibração com o dedo: alvos, contagem, coleta e aceite na projeção | Mac + TV |
| 2.3 | `HomographyMapper` no cursor; cursor some fora da área | Mac + TV: cursor sob o dedo |
| 2.4 | Verificação (alvo central) + grade de 9 pontos com erro no log | `log_summary` |
| 2.5 | Testes em 3 ângulos + medição da paralaxe + documentação das limitações | `testing.md` |

## 9. Respostas do usuário (2026-11-06) e pendências

1. Alvos a 5% da borda: **aprovado**.
2. Calibração: **sempre ao abrir**, com o professor marcando os cantos com o dedo e contagem regressiva, na ordem superior esquerdo → inferior esquerdo → inferior direito → superior direito. Também pode ser acionada depois, pelo modo "Calibrar perspectiva da tela".
3. Critério de precisão (§6): a resposta chegou cortada. Fica o proposto, **provisoriamente**, até a medição real.
4. Duração da contagem: **7 s por alvo** (usuário, 17:53), a ajustar depois.


## 10. Precisão: correção dos 9 pontos, filtro One Euro e malha virtual (2026-11-06)

Pedido do usuário depois de avaliar uma sugestão externa ("malha virtual X/Y"). Ponto de partida: no teste G das 22:50, o erro foi de 3–4 px no centro e de 30–39 px perto dos cantos. Esse erro, que muda de um lugar para outro, é o que a homografia sozinha não corrige.

### 10.1 Correção residual (`desktop/calibration/residual.py`)
- O teste G mede, nos 9 pontos, a diferença entre onde o sistema põe o dedo e onde está o alvo. Ao terminar, guarda o deslocamento inverso em cada ponto e interpola (bilinear) entre eles. Fora da grade, vale o deslocamento da borda mais próxima.
- **O teste G passa a medir com a correção ligada.** Rodar G de novo mede o erro que sobrou e refina a correção.
- Ponto a mais de 5% do alvo: o teste G o repete na hora ("encoste de novo"). Antes, um só ponto assim fazia a correção inteira ser recusada (teste real de 23:56).
- Nova calibração (C) zera a correção. A tecla R liga e desliga a correção, para comparar.
- Limite: corrige o erro médio de quem encostou o dedo durante o teste. Não resolve dedo no ar × encostado (Fase 5.3).

### 10.2 Filtro One Euro (`desktop/core/one_euro.py`)
- Aplicado à ponta do indicador antes da conversão. A calibração e o teste G usam o dedo sem filtro, porque já fazem média.
- Valores escolhidos por simulação (30 Hz, ruído de 0,002): `min_cutoff` 1,0 Hz e `beta` 30. Tremor parado 0,0020 → 0,0008; atraso na escrita a 0,5/s de 0,004 da tela (~8 px na TV); um salto assenta em 2 quadros. Os valores (1,5; 2) davam atraso de 0,021, cerca de 40 px.
- A tecla S liga e desliga o filtro.

### 10.3 Malha virtual (`desktop/interface/grid_view.py`, tecla M)
- Grade de 20 colunas sobre a lousa toda, com células quadradas (11 linhas em 16:9). Linhas fortes a cada 5, com número. A primeira versão tinha 100 colunas; o usuário pediu uma malha mais aberta (2026-11-07).
- No dedo, uma cruz e as coordenadas "X 52,3 · Y 31,0".
- Com a correção ativa, setas laranja nos 9 pontos mostram quanto e para onde cada ponto foi ajustado.
- A malha não aumenta a precisão: serve para ver onde o sistema põe o dedo e comparar com a lousa.

### 10.4 Verificação entre os pontos (tecla V)
- O G repetido mede nos mesmos 9 pontos usados para corrigir, e por isso sai otimista. A tecla V mede em 4 pontos entre eles, (32,5% e 67,5% da largura e da altura), onde a correção só interpola.
- Não cria nem muda a correção. O log registra `verify_result` com a correção ligada, desligada ou nenhuma.
- **Critério para malha 5×5:** se a mediana do V com correção ficar bem acima da mediana do G com correção, o erro varia de forma irregular entre os pontos e mais pontos ajudariam. Se ficarem parecidas, a 3×3 basta.

## 10.5 Marcadores discretos (D028)

- Borda branca de 0,17 do lado do marcador (antes 0,25); marcador continua com 12% do menor lado da tela, porque a câmera já os vê com só ~19 px.
- Somem 1 s depois que a referência é registrada; voltam na calibração, nos testes G/V, no assistente e com a tecla **N**.
- Escondidos, a última correção continua aplicada. Se o celular mexer, a visão percebe pela imagem (D030): os cantos **voltam sozinhos**, a posição é recalculada e, com o celular parado, **somem de novo**. **N** continua mostrando/escondendo à mão.

## 11. Assistente de calibração (D023)

Ao abrir o programa, ou com a tecla A: cantos → verificação sem correção → correção pelos 9 pontos → verificação com correção → resumo.
- Módulo puro `desktop/calibration/guided.py`. A janela pergunta `tick()` qual etapa iniciar e avisa `step_done()` ao fim de cada teste. Testes avulsos (teclas) durante o assistente não o fazem avançar.
- Cartão (`draw_guided_card` em `calibration_overlay.py`): layout medido pela fonte, cabe em qualquer tela.
- Log: `guided_start`, `guided_step` (resultado de cada etapa), `guided_done` (cantos, antes, depois, melhora %, correção), `guided_cancel`. `tools.log_summary` mostra a linha "Assistente de calibração".
- `--quick`: ao abrir, só os 4 cantos.
