# Referências externas e o que aproveitar

Projetos e estudos parecidos, com o que serve para a SmartBoard Classroom. Ideias daqui não entram no código sem passar pelo fluxo do CLAUDE.md (§14): problema → alternativas → decisão registrada em `decisions.md`.

---

## open-source-hands (Meticulai) — kit de gestos sobre o MediaPipe

- **Repositório:** https://github.com/abouchedidxcode/open-source-hands. Licença MIT; o MediaPipe é Apache-2.0.
- **O que é:** cerca de 1.600 linhas de TypeScript sem dependências (`src/kit`), rodando no navegador. Transforma os 21 pontos da mão em eventos e valores contínuos para jogos. Há uma página de laboratório de gestos (`lab.html`), mãos sintéticas para testes, uma skill do Claude Code (`skills/hand-gestures`) e `AGENTS.md`.
- **Lido em:** 2026-11-07, pelo README e pelo código-fonte (`git clone`, commit `dd79fb7`, de 2026-11-02): `features.ts`, `poses.ts`, `oneEuro.ts`, `engine.ts`, `synthetic.ts`, `AGENTS.md`.

### Como funciona por dentro (valores do código)

- **Pontos 3D "do mundo" para a forma da mão.** Usam os `worldLandmarks` do MediaPipe (em metros, centrados na mão, imunes à rotação) para medir dedos e pinça. Só usam os pontos da imagem para posição e direção na tela. **Nós medimos tudo nos pontos 2D da imagem**, que se deformam quando a mão gira em relação à câmera. O MediaPipe em Python também entrega `hand_world_landmarks`; hoje o descartamos.
- **Dedo dobrado = soma dos ângulos das articulações** (0 = reto, π = dobrado para trás). A dobra na base do dedo conta pela metade ("mão espalmada dobrada na base continua aberta"). Normalização: reto até 0,45 rad, dobrado a partir de 3,1 rad (polegar: 0,35 e 1,5). Resultado: dobra de 0 a 1 por dedo.
- **Pose = nota de 0 a 1.** Cada pose tem uma regra por dedo (esticado, dobrado, meio, qualquer), com transições suaves (`smoothstep`). Nota = √(média geométrica × pior regra): um dedo claramente errado derruba a pose, pequenas oscilações só arranham. Exemplo "apontar": indicador esticado, médio/anelar/mínimo dobrados, polegar livre.
- **Histerese das poses:** entra com nota ≥ 0,62, sai abaixo de 0,42; outra pose só toma o lugar se passar a atual por 0,08; a troca precisa durar 70 ms, e para "nenhuma pose" 112 ms (×1,6), "para as poses não piscarem entre quadros". Mão sumida por mais de 250 ms encerra a pose.
- **One Euro em todos os 63 valores** (21 pontos × x, y, z), antes de calcular qualquer coisa: `minCutoff` 2,2 Hz, `beta` 8, `dCutoff` 1. Os pontos do mundo são multiplicados por 10 antes do filtro, para a velocidade ter escala parecida.
- **Cursor:** One Euro 2D com `minCutoff` 1,1, `beta` 5,5, `dCutoff` 1,2. Usa a **velocidade do vetor** (os dois eixos abrem juntos). Segundo o comentário deles, dois filtros independentes atrasam mais o eixo lento e entortam movimentos diagonais retos. **O nosso usa dois filtros independentes.** Também limitam o intervalo entre quadros a 1 ms–100 ms (protege contra travadas e carimbos de tempo repetidos).
- **Pinça:** distância ponta do polegar ↔ ponta do indicador ÷ pulso→base do médio, nos pontos do mundo. Força = 1 − smoothstep(0,20; 0,42). Parecido com a nossa D021 (0,35/0,50), mas a nossa mede na imagem 2D.
- **Abertura da mão:** 1 − média da dobra dos 4 dedos (0 a 1). A nossa é distância pulso→pontas ÷ palma (≈ 1 a 2).
- **Mãos sintéticas:** parametrizadas por dobra de cada dedo, pinça, rotação e abertura entre dedos, com flexão máxima por articulação (75°, 100°, 70°). Mais realistas que as nossas (dedo "esticado" ou "dobrado" fixo).
- **Rigor do AGENTS.md:** antes de dizer que funciona, testes e build devem passar, e é preciso "dizer claramente que nenhuma webcam real foi testada, se nenhuma foi". Mesma regra do nosso CLAUDE.md §9.4 e §16.

### Pipeline deles × o nosso

| Etapa | open-source-hands | SmartBoard hoje |
|---|---|---|
| Câmera | webcam frontal 1280×720 no navegador | celular → JPEG via WebSocket → MediaPipe no notebook |
| Suavização | One Euro em **todos os pontos da mão**, antes de calcular os gestos | One Euro só na ponta do indicador, depois da pose (D020) |
| Dedo dobrado | **ângulos das articulações** | razão de distâncias pulso→ponta ÷ pulso→articulação (D018) |
| Poses | 20 poses com **pontuação contínua** e limiares de entrada/saída | 4 classes (pointing/open/fist/other) + confirmação em quadros |
| Pinça | "pinch gaps" e força da pinça contínua; `tap` = toque de pinça | razão polegar↔indicador ÷ palma com histerese 0,35/0,50 (D021) |
| Movimentos | 16 (deslizes, empurrar/puxar, círculos, aceno, tap, segurar…), janela de 1,6 s | nenhum (só permanência) |
| Duas mãos | palmas, zoom, volante (distância e ângulo entre palmas) | escolhe uma mão (D016) |
| Ajuste | laboratório de gestos com controles deslizantes, exporta JSON; teste de confiabilidade (taxa de detecção, tempo de reação, confusões) | constantes em `config.py`; medidas pelo log |
| Testes | mãos sintéticas (unidade e e2e) + `camera-check` com MediaPipe real sobre vídeos gravados | mãos sintéticas (pytest) + uma foto real |

### Já trazido para o projeto (D022, 2026-11-07)

Itens 1, 2, 3 e 3b abaixo, mais as mãos sintéticas 3D: `desktop/vision/gestures.py`, `desktop/vision/synthetic_hands.py`, `desktop/core/one_euro.py`.

Itens 4, 5 e 6 (D024, 2026-11-07): laboratório de gestos (tecla L), gravação só dos pontos da mão + reprodução (`--record`, `tools.replay_landmarks`), e os gestos escolhidos pelo usuário: deslizar → slide, toque de pinça → clique, duas mãos → tamanho (`desktop/interaction/motions.py`).

Não trazidos (sem uso na lousa por ora): empurrar/puxar, círculos, aceno, giro, arremesso, palmas, volante.

### Ideias candidatas, por prioridade para o projeto

1. **Suavizar todos os pontos antes da pose.** Ataca a causa dos traços partidos (oscilação da pose, 5.1). Hoje o filtro só age no cursor. Custo baixo: o One Euro já existe. Valores de partida: 2,2 / 8 / 1.
2. **Forma da mão pelos pontos 3D do mundo + dobra por ângulo das articulações.** Mais robusto com a mão inclinada em relação à câmera, que é o caso do professor de lado para a lousa. O MediaPipe em Python já entrega esses pontos. Comparar com a razão atual nos mesmos dados.
3. **Pontuação contínua com limiares de entrada (0,62) e saída (0,42)** e troca confirmada por tempo (70 ms), em vez de classe + contagem de quadros. Generaliza a histerese que fizemos na pinça (D021) para a pose. Tempo em ms não depende da taxa de quadros; contagem de quadros depende.
3b. **One Euro do cursor com velocidade vetorial** e limite de intervalo (1 ms–100 ms). Troca pequena no `one_euro.py`.
4. **Laboratório de gestos com teste de confiabilidade** (taxa de detecção, tempo de reação, confusões). É o formato certo para a etapa 5.3 (toque) e para decidir pinça × indicador (D021) com números, não impressão.
5. **Regressão com gravações:** eles rodam o MediaPipe real sobre vídeos gravados. Para nós, por privacidade (CLAUDE.md §11), o equivalente é gravar **só os pontos da mão** de uma sessão real e reproduzi-los nos testes.
6. **Gestos de movimento para comandos:** deslizar para a esquerda/direita para trocar de slide; zoom com duas mãos para redimensionar. Mudam a experiência do professor, então precisam de aprovação. Risco de disparo acidental durante a explicação.

### O que não se aplica direto

- O kit é TypeScript para o navegador. Nossa visão roda em Python no notebook (D013), então aproveitamos as ideias, não o código. Exceção possível: o modo "local" no celular, que já roda no navegador.
- O foco deles é jogo, que tolera erro. Na lousa, um disparo acidental (limpar, trocar slide) custa mais; por isso mantemos confirmações e permanência.

---

## Outros projetos parecidos (busca de 2026-11-07)

- **Projeto ECE 445, Univ. de Illinois:** projetor + câmera RGB + ArUco + homografia + MediaPipe; clique por pinça. Origem da D021.
- **ProjectorOS:** plataforma projetor + câmera com espaços de coordenadas separados e calibração ArUco.
- **preste-ai/ai_whiteboard:** parede como lousa com câmera RGB; detector próprio treinado com 12.000 imagens, em Jetson.
- **Air-Workspace:** desenho no ar (PyQt6 + MediaPipe) com máquina de estados de gestos.
- **Detecção de toque na literatura:** em geral é feita por permanência ou gesto; o toque real exige duas câmeras ou análise de sombra (só com projetor). Ver `gesture-system.md` §5.3.
