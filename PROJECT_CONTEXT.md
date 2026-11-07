# SMARTBOARD CLASSROOM

**Lousa Branca Inteligente com Interação por Visão Computacional**

- **Arquivo:** PROJECT_CONTEXT.md
- **Versão:** 1.0
- **Status:** Especificação inicial do projeto
- **Categoria:** Tecnologia educacional, visão computacional e interação humano-computador

> Este documento define **o que** construir (produto, funcionalidades e decisões de experiência).
> As regras de **como** construir estão em [`CLAUDE.md`](CLAUDE.md).

---

## 1. Visão geral do projeto

A SmartBoard Classroom é uma solução educacional que tem como objetivo transformar uma superfície de projeção convencional em uma lousa branca inteligente e interativa.

O sistema utilizará a câmera de um celular, posicionada em um ângulo estratégico em relação à superfície projetada, para identificar os movimentos das mãos do professor.

Uma aplicação executada no notebook será responsável por processar as informações, interpretar os movimentos, controlar as ferramentas e executar as ações solicitadas.

O professor poderá interagir diretamente com o conteúdo projetado, utilizando os movimentos das mãos para:

- Escrever.
- Desenhar.
- Apagar.
- Criar formas geométricas.
- Selecionar ferramentas.
- Desfazer e refazer ações.
- Avançar e retroceder apresentações.
- Limpar as anotações.

A comunicação entre celular e notebook ocorrerá por rede sem fio, preferencialmente na rede Wi-Fi local.

A proposta é oferecer uma alternativa de baixo custo às lousas digitais interativas comerciais, aproveitando equipamentos convencionais já disponíveis nas instituições de ensino.

## 2. Objetivo principal

Desenvolver uma plataforma de interação educacional capaz de transformar um projetor convencional, um notebook e um celular em uma lousa digital interativa.

O professor deverá conseguir controlar as ferramentas projetadas por meio de movimentos naturais das mãos, sem precisar utilizar mouse, teclado, controle remoto ou tocar fisicamente no notebook.

A experiência deverá ser simples, intuitiva e adequada à dinâmica real de uma sala de aula.

## 3. Conceito de funcionamento

O sistema será dividido em três componentes principais.

### 3.1. Notebook

Responsável por:

- Executar a aplicação principal.
- Receber os dados enviados pelo celular.
- Processar as coordenadas recebidas.
- Gerenciar as ferramentas da lousa.
- Executar os comandos reconhecidos.
- Renderizar as anotações.
- Controlar a interface projetada.
- Gerenciar a comunicação com os dispositivos.

### 3.2. Celular

Funcionará como câmera inteligente. Responsabilidades:

- Capturar os movimentos das mãos.
- Identificar os pontos de referência da mão.
- Rastrear a ponta do indicador.
- Identificar gestos configurados.
- Enviar coordenadas e eventos ao notebook.
- Exibir o estado da conexão.

O acesso inicial deverá ocorrer por meio de uma aplicação web aberta no navegador do celular, sem exigir instalação de aplicativo nativo.

### 3.3. Projetor

Responsável por exibir:

- Conteúdo das apresentações.
- Interface da lousa.
- Barra de ferramentas.
- Anotações.
- Formas geométricas.
- Indicadores visuais das interações.

## 4. Fluxo de funcionamento

1. O professor inicia a aplicação no notebook.
2. O notebook disponibiliza um endereço de acesso na rede local.
3. O professor conecta o celular por meio do navegador.
4. A câmera é posicionada em um ângulo favorável para visualizar a superfície projetada.
5. O sistema inicia a identificação das mãos.
6. A posição do indicador é detectada.
7. As coordenadas são transmitidas ao notebook.
8. O notebook converte as coordenadas para o espaço correspondente à projeção.
9. O sistema interpreta a ação realizada.
10. A ferramenta selecionada executa a ação.
11. O resultado aparece na projeção em tempo real.

> **Princípio fundamental:** a interação deve ocorrer naturalmente, como se o professor estivesse utilizando uma lousa digital comercial.

## 5. Interface da lousa inteligente

A aplicação deverá possuir uma interface visual independente do conteúdo da apresentação.

Essa interface funcionará como uma camada transparente (overlay), posicionada sobre a tela de apresentação.

O conteúdo didático deverá permanecer visível, enquanto as ferramentas serão exibidas somente quando necessário.

A interface deverá ser minimalista, funcional e adaptada à projeção em sala de aula.

## 6. Ferramentas iniciais

| Ferramenta | Função |
|---|---|
| Ponteiro | Destacar elementos da apresentação |
| Selecionar | Selecionar ferramentas e elementos |
| Pincel | Escrever e desenhar livremente |
| Borracha | Apagar partes específicas dos desenhos |
| Círculo | Criar formas circulares |
| Retângulo | Criar formas retangulares |
| Voltar | Desfazer a última ação |
| Avançar | Refazer uma ação desfeita |
| Limpar | Remover todas as anotações |
| Navegação | Avançar ou retroceder slides |

### 6.1. Pincel

- Escrita livre.
- Desenho à mão livre.
- Configuração de cores.
- Ajuste de espessura.
- Rastreamento contínuo do indicador.
- Visualização imediata do traçado.

### 6.2. Borracha

- Apagar partes específicas dos desenhos.
- Ajustar o tamanho da área de apagamento.
- Visualizar a região que será apagada.
- Preservar os elementos que não forem atingidos.

### 6.3. Círculo

1. Selecionar a ferramenta.
2. Definir o ponto inicial.
3. Movimentar o indicador para definir as dimensões.
4. Visualizar uma prévia.
5. Confirmar a forma.

### 6.4. Retângulo

1. Selecionar a ferramenta.
2. Definir o primeiro vértice.
3. Movimentar até o vértice oposto.
4. Visualizar a prévia.
5. Confirmar o desenho.

### 6.5. Voltar e avançar

Deverão permitir desfazer e refazer as operações de desenho e edição.

### 6.6. Limpar

Deverá remover todas as anotações da superfície. Recomenda-se solicitar confirmação antes de executar essa operação.

## 7. Sidebar inteligente — painel flutuante

### 7.1. Conceito aprovado

A SmartBoard Classroom utilizará uma sidebar flutuante, semitransparente e retrátil, encaixada na borda da área de projeção.

O acesso às ferramentas será realizado por meio de um pequeno botão circular semitransparente, que funcionará como uma alça lateral para abrir e recolher o painel.

A sidebar será uma camada independente sobre a apresentação.

> **Regra fundamental:** abrir ou fechar a sidebar não poderá deslocar, redimensionar ou interromper o conteúdo da apresentação.

### 7.2. Botão circular de acesso

- Formato circular.
- Aparência semitransparente.
- Design minimalista.
- Posicionamento inicial em uma das laterais da projeção.
- Parcialmente encaixado na borda da tela.
- Área de interação adequada ao reconhecimento pela câmera.
- Possibilidade de movimentação pelo professor.
- Indicação visual quando estiver disponível para interação.

O botão deverá permanecer acessível mesmo quando a sidebar estiver recolhida.

### 7.3. Animação lateral

Quando o professor interagir com o botão circular, a sidebar deverá deslizar suavemente para dentro da área projetada. Quando recolhida, deverá executar a animação inversa, retornando à borda e deixando somente o botão circular visível.

Estados da sidebar:

1. Recolhida.
2. Abrindo.
3. Expandida.
4. Recolhendo.

A animação deverá ser rápida, suave e não bloquear a apresentação.

### 7.4. Organização vertical e horizontal

**Modo vertical:** ferramentas em uma coluna, ícones um abaixo do outro, ocupação lateral da projeção.

**Modo horizontal:** ferramentas em uma linha, ícones lado a lado, ocupação da parte superior ou inferior da projeção.

O professor poderá alternar entre os dois formatos a qualquer momento. A alteração da orientação não poderá interromper a apresentação nem remover anotações existentes.

### 7.5. Movimentação da barra

- Permitir arrastar a barra.
- Possuir uma região específica de manipulação.
- Não confundir movimentação da barra com escrita.
- Respeitar os limites da projeção.
- Evitar que os controles fiquem parcialmente fora da superfície.
- Preservar a posição durante a sessão.

### 7.6. Controles visuais da barra

- Controle para alternar orientação vertical/horizontal.
- Área específica para arrastar e reposicionar.
- Controle para recolher e expandir.
- Ferramentas de desenho e edição.
- Indicador da ferramenta selecionada.

### 7.7. Comportamento inteligente

- Preservar a ferramenta atualmente selecionada.
- Preservar as anotações durante as transições.
- Evitar abertura acidental por movimentos involuntários.
- Evitar que o movimento da barra seja confundido com escrita.
- Permitir reposicionar o botão circular.
- Permitir reposicionar a barra.
- Respeitar os limites da área projetada.
- Manter o conteúdo da apresentação independente da sidebar.

> **PADRÃO APROVADO:** sidebar flutuante + botão circular semitransparente + animação lateral + orientação vertical/horizontal + reposicionamento livre.

## 8. Reconhecimento dos movimentos das mãos

A câmera deverá utilizar visão computacional para identificar pontos de referência da mão:

- Ponta do indicador.
- Ponta do polegar.
- Pontas dos demais dedos.
- Posição do pulso.
- Orientação da mão.
- Distância entre os dedos.

### 8.1. Tecnologia candidata

**MediaPipe Hand Landmarker** — identificar mãos, detectar pontos de referência, rastrear movimentos, identificar a posição dos dedos e fornecer dados para interpretação dos gestos.

OpenCV poderá complementar o processamento, especialmente na calibração geométrica e transformação de coordenadas.

### 8.2. Diferenciação de gestos

O sistema deverá distinguir: apontar, selecionar, escrever, apagar, arrastar, confirmar e recolher a sidebar.

A seleção de uma ferramenta não deverá ocorrer simplesmente porque a mão passou sobre um botão. Deverão ser utilizados mecanismos de confirmação, como:

- Tempo mínimo de permanência sobre um botão.
- Gestos específicos.
- Controle de sensibilidade.
- Filtros para reduzir oscilações.
- Intervalo entre comandos repetidos.

## 9. Calibração da câmera e da projeção

Uma das partes mais importantes do projeto é estabelecer a correspondência entre as coordenadas da câmera e a superfície projetada. Como a câmera estará posicionada em um ângulo diferente da projeção, as coordenadas capturadas não corresponderão diretamente às coordenadas da tela.

### 9.1. Objetivos

- Identificar os limites da projeção.
- Determinar a relação entre a câmera e a superfície.
- Corrigir distorções de perspectiva.
- Converter a posição do indicador para coordenadas da interface.
- Manter precisão mesmo com a câmera posicionada lateralmente.

### 9.2. Tecnologia candidata

Homografia (Perspective Transformation) utilizando OpenCV. A calibração poderá utilizar quatro pontos de referência correspondentes aos cantos da área projetada. A aplicação deverá transformar as coordenadas identificadas pela câmera em coordenadas correspondentes à superfície da lousa.

### 9.3. Desafio técnico: estimativa do toque

Detectar a mão não significa necessariamente identificar o ponto exato em que o dedo toca a superfície. O sistema deverá investigar métodos para estimar a interação do indicador com o plano da lousa.

Possíveis abordagens:

- Estimativa geométrica da interseção do dedo com o plano da projeção.
- Rastreamento da ponta do indicador com compensação de perspectiva.
- Reconhecimento de gestos de confirmação.
- Calibração interativa com pontos de referência.

A solução deverá minimizar erros de seleção e escrita.

## 10. Comunicação entre celular e notebook

A comunicação deverá ocorrer por rede Wi-Fi local. Tecnologias candidatas:

**WebSocket** — comunicação bidirecional, envio de coordenadas e eventos, baixa sobrecarga.

**WebRTC** — alternativa para transmissão de vídeo em tempo real; deve ser avaliada caso o processamento da imagem precise ocorrer no notebook.

### 10.1. Arquitetura recomendada inicialmente

O processamento dos landmarks deverá ocorrer preferencialmente no próprio celular. O celular enviará somente:

- Coordenadas normalizadas.
- Identificação da mão.
- Estado do gesto.
- Eventos de interação.
- Informações de confiança do rastreamento.

Isso reduz o tráfego de dados e pode simplificar a comunicação. A arquitetura deverá permitir migrar o processamento para o notebook caso os testes demonstrem necessidade.

## 11. Tecnologias propostas

Candidatas iniciais, a serem validadas por meio de protótipos.

| Componente | Tecnologia candidata |
|---|---|
| Linguagem principal | Python |
| Visão computacional | OpenCV |
| Rastreamento das mãos | MediaPipe |
| Interface desktop | PySide6 |
| Comunicação | WebSocket |
| Interface do celular | HTML, CSS e JavaScript |
| Captura da câmera | getUserMedia |
| Transformação geométrica | OpenCV Homography |
| Distribuição | PyInstaller |

Priorizar bibliotecas gratuitas, abertas e com boa documentação.

## 12. Gerenciamento da apresentação

A aplicação deverá funcionar sobre o conteúdo apresentado pelo professor. Duas possibilidades deverão ser investigadas.

**Opção A — Apresentação própria.** A aplicação possui seu próprio ambiente de slides.
Vantagens: integração direta com as ferramentas, maior controle da interface, menor dependência de aplicações externas.

**Opção B — Overlay sobre apresentações externas.** Camada transparente sobre Microsoft PowerPoint, LibreOffice Impress e outros softwares.
Vantagens: maior flexibilidade, aproveitamento dos materiais existentes, menor necessidade de recriar ferramentas de apresentação.

A implementação deverá investigar compatibilidade com tela cheia, janelas transparentes, foco e gerenciamento de camadas nos diferentes sistemas operacionais. A decisão definitiva deverá ocorrer após uma análise técnica.

## 13. Requisitos funcionais

**Comunicação e conexão**

- RF01: Iniciar e encerrar uma sessão.
- RF02: Conectar celular e notebook por Wi-Fi.
- RF03: Visualizar o estado da câmera.
- RF04: Identificar o estado da conexão.
- RF05: Recuperar a conexão após interrupções.

**Visão computacional**

- RF06: Detectar e rastrear as mãos.
- RF07: Identificar a posição do indicador.
- RF08: Interpretar gestos configurados.
- RF09: Converter coordenadas da câmera para a projeção.
- RF10: Permitir calibração da superfície.

**Ferramentas**

- RF11: Selecionar ferramentas.
- RF12: Escrever e desenhar livremente.
- RF13: Apagar partes específicas.
- RF14: Desenhar círculos.
- RF15: Desenhar retângulos.
- RF16: Desfazer ações.
- RF17: Refazer ações.
- RF18: Limpar anotações.
- RF19: Navegar entre slides.
- RF20: Configurar cor e espessura do pincel.
- RF21: Configurar tamanho da borracha.
- RF22: Visualizar formas geométricas antes da confirmação.

**Sidebar**

- RF23: Exibir botão circular semitransparente.
- RF24: Abrir sidebar por interação gestual.
- RF25: Recolher sidebar.
- RF26: Animar abertura e fechamento.
- RF27: Reposicionar o botão circular.
- RF28: Alternar orientação vertical/horizontal.
- RF29: Movimentar a barra dentro da projeção.
- RF30: Preservar orientação e posição escolhidas.
- RF31: Manter o botão de acesso disponível quando recolhida.
- RF32: Preservar anotações durante as transições.

## 14. Requisitos não funcionais

- Baixa latência entre movimento e resposta visual.
- Rastreamento estável.
- Interface intuitiva.
- Compatibilidade com diferentes resoluções.
- Baixo consumo de recursos.
- Comunicação segura na rede local.
- Recuperação de conexão.
- Arquitetura modular.
- Separação entre interface, comunicação e processamento.
- Compatibilidade com diferentes equipamentos.

## 15. Estrutura modular sugerida

```
smartboard-classroom/
│
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── README.md
├── requirements.txt
│
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── calibration.md
│   ├── communication-protocol.md
│   ├── gesture-system.md
│   ├── interface-guidelines.md
│   ├── testing.md
│   └── development-roadmap.md
│
├── desktop/
│   ├── main.py
│   ├── core/
│   │   ├── session_manager.py
│   │   ├── gesture_engine.py
│   │   ├── coordinate_mapper.py
│   │   └── command_manager.py
│   ├── communication/
│   │   ├── websocket_server.py
│   │   └── message_protocol.py
│   ├── interface/
│   │   ├── main_window.py
│   │   ├── presentation_overlay.py
│   │   ├── toolbar.py
│   │   ├── sidebar.py
│   │   └── drawing_canvas.py
│   └── tools/
│       ├── brush.py
│       ├── eraser.py
│       ├── circle.py
│       ├── rectangle.py
│       ├── pointer.py
│       └── history.py
│
├── mobile/
│   ├── index.html
│   ├── styles/
│   ├── scripts/
│   │   ├── camera.js
│   │   ├── hand_tracking.js
│   │   ├── gesture_detection.js
│   │   └── websocket_client.js
│   └── assets/
│
└── tests/
    ├── test_communication.py
    ├── test_coordinates.py
    ├── test_gestures.py
    └── test_drawing.py
```

Essa estrutura é uma proposta inicial. O Claude Code deverá avaliar e ajustar a organização conforme as decisões arquiteturais.

## 16. Etapas de desenvolvimento

### Fase 1 — Prova de conceito de rastreamento

**Objetivo:** comprovar que a câmera do celular consegue identificar a posição do indicador e transmitir suas coordenadas ao notebook.

Entregas: servidor no notebook; página web no celular; acesso à câmera; detecção da mão; rastreamento do indicador; comunicação via WebSocket; cursor no notebook acompanhando o movimento.

**Critério de sucesso:** movimentar o indicador diante da câmera e visualizar um cursor acompanhando o movimento em tempo real.

### Fase 2 — Calibração espacial

**Objetivo:** estabelecer correspondência entre câmera e superfície projetada.

Entregas: identificação dos cantos da projeção; calibração por quatro pontos; correção de perspectiva; conversão de coordenadas; testes em diferentes ângulos.

### Fase 3 — Interface da lousa

**Objetivo:** desenvolver a interface visual.

Entregas: overlay transparente; barra de ferramentas; sidebar inteligente; botão circular; orientação vertical/horizontal; movimentação da barra; animações.

### Fase 4 — Ferramentas de desenho

**Objetivo:** implementar as ferramentas.

Entregas: pincel; borracha; círculo; retângulo; desfazer; refazer; limpar; configuração de cores e espessuras.

### Fase 5 — Reconhecimento de interações

**Objetivo:** transformar os movimentos detectados em comandos.

Entregas: seleção de ferramentas; reconhecimento de gestos; diferenciação entre apontar e escrever; movimentação da sidebar; prevenção de comandos acidentais.

### Fase 6 — Integração com apresentações

**Objetivo:** permitir utilização durante as aulas.

Entregas: integração com apresentações; navegação entre slides; anotações sobre o conteúdo; gerenciamento de tela cheia; testes com diferentes softwares.

### Fase 7 — Testes em ambiente real

**Objetivo:** validar a solução em uma sala de aula.

Testar: diferentes distâncias; diferentes ângulos da câmera; iluminação ambiente; diferentes projetores; diferentes tamanhos de projeção; precisão da escrita; latência; estabilidade da comunicação; interferência de movimentos involuntários.

## 17. Critérios de qualidade

1. Precisão do posicionamento do indicador.
2. Estabilidade do rastreamento.
3. Latência de interação.
4. Precisão da calibração.
5. Facilidade de utilização.
6. Estabilidade da conexão.
7. Qualidade da escrita.
8. Precisão da seleção das ferramentas.
9. Facilidade de abertura e recolhimento da sidebar.
10. Compatibilidade com equipamentos convencionais.

Os valores quantitativos de desempenho deverão ser definidos e medidos durante os protótipos, evitando estabelecer metas sem validação experimental.

## 18. Princípios de desenvolvimento

1. Desenvolver por etapas.
2. Validar cada componente antes de avançar.
3. Priorizar soluções gratuitas e open source.
4. Evitar dependências de serviços pagos.
5. Não adicionar complexidade antes de comprovar sua necessidade.
6. Manter os componentes independentes.
7. Documentar decisões técnicas.
8. Criar testes automatizados.
9. Priorizar a experiência real do professor.
10. Não assumir que detectar uma mão significa detectar o toque na superfície.
11. Não implementar funcionalidades sem validar suas dependências.
12. Não confundir protótipo com produto final.

## 19. Primeira missão do Claude Code

Antes de implementar o sistema completo, realizar uma análise técnica da proposta e desenvolver uma prova de conceito funcional.

O primeiro objetivo será:

1. O notebook executa a aplicação.
2. O celular acessa a aplicação pela rede Wi-Fi.
3. A câmera identifica a mão do professor.
4. O sistema reconhece a ponta do indicador.
5. As coordenadas são transmitidas ao notebook.
6. Um cursor acompanha a posição do indicador em tempo real.

Somente depois da validação dessa etapa deverá ser implementada a calibração da projeção.

**Não desenvolver inicialmente a sidebar, as ferramentas de desenho ou a integração com apresentações.**

## 20. Instrução permanente para o Claude Code

Atue como arquiteto de software, engenheiro de visão computacional e desenvolvedor de aplicações educacionais. Considere este documento como a especificação inicial do produto.

Antes de modificar a arquitetura:

- Leia a documentação existente.
- Analise as dependências.
- Identifique riscos.
- Avalie alternativas tecnológicas.
- Documente decisões relevantes.

Durante o desenvolvimento:

- Trabalhe por etapas.
- Não implemente funcionalidades fora do escopo da fase atual sem justificativa.
- Não invente resultados de testes.
- Não declare uma funcionalidade concluída sem validação.
- Preserve as decisões de produto aprovadas.
- Atualize a documentação quando houver mudanças arquiteturais.

As decisões de produto aprovadas, especialmente o comportamento da sidebar e da interface flutuante, deverão ser respeitadas nas implementações futuras.

## 21. Visão final do produto

A SmartBoard Classroom deverá proporcionar uma experiência de lousa digital inteligente, permitindo que o professor interaja com o conteúdo projetado por meio dos movimentos das mãos.

O professor deverá conseguir:

- Apresentar conteúdos.
- Escrever diretamente sobre a projeção.
- Desenhar formas geométricas.
- Apagar informações.
- Destacar elementos.
- Navegar pelas apresentações.
- Organizar as ferramentas conforme a dinâmica da aula.

A interface deverá permanecer discreta, com uma sidebar inteligente que aparece somente quando necessário.

> **Objetivo final:** transformar qualquer sala de aula equipada com notebook e projetor em um ambiente de apresentação interativo, sem exigir uma lousa digital comercial.
