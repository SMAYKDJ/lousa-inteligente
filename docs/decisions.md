# Registro de decisões

Formato de cada entrada: problema → alternativas → decisão → impactos → data (ver `CLAUDE.md` §14).

## D001 — Separação entre especificação do produto e regras de desenvolvimento

- **Problema:** evitar que regras de programação se misturem com funcionalidades do produto à medida que o projeto cresce.
- **Decisão:** manter dois documentos independentes na raiz do repositório: `PROJECT_CONTEXT.md` (o que construir) e `CLAUDE.md` (como construir).
- **Impacto:** o Claude Code tem referência clara para ambos; alterações em um não afetam o outro.
- **Data:** 2026-11-06

---

> As decisões D002–D007 abaixo são da Fase 1 e estão **propostas, não validadas**. Cada uma passa a "validada" quando a etapa da Fase 1 correspondente for testada com equipamento real.

## D002 — Rastreamento da mão no celular

- **Problema:** decidir onde rodar a detecção de landmarks.
- **Alternativas:** (a) MediaPipe Tasks Vision no navegador do celular, enviando só coordenadas; (b) transmitir vídeo por WebRTC e rodar o MediaPipe Python no notebook.
- **Decisão:** (a), conforme a recomendação inicial do `PROJECT_CONTEXT.md` §10.1.
- **Impactos:** tráfego mínimo e imagem que não sai do celular. Em compensação, o desempenho depende do aparelho e precisa ser medido. O protocolo de coordenadas permite migrar para (b) sem mudar o notebook.
- **Status:** substituída pela D013 como modo padrão (2026-11-06); continua disponível como modo `local` · **Data:** 2026-11-06

## D003 — aiohttp como servidor único (HTTPS + WebSocket)

- **Problema:** o celular precisa carregar a página e abrir o WebSocket, ambos em contexto seguro.
- **Alternativas:** (a) `websockets` + servidor HTTP separado (duas portas, dois avisos de certificado); (b) `aiohttp` (estáticos + WebSocket na mesma porta); (c) FastAPI + uvicorn (mais dependências).
- **Decisão:** (b). Substitui `websockets` por `aiohttp` no `requirements.txt`.
- **Impactos:** uma origem, um certificado e uma dependência de rede.
- **Status:** proposta · **Data:** 2026-11-06

## D004 — Certificado autoassinado gerado localmente

- **Problema:** `getUserMedia()` só funciona em HTTPS ou `localhost`, e o celular acessa o notebook pelo IP da rede local.
- **Alternativas:** (a) certificado autoassinado gerado pela aplicação (`cryptography`); (b) `mkcert` com CA instalada no celular; (c) túnel externo (ngrok etc.), descartado porque depende de internet e de serviço externo.
- **Decisão:** (a) como padrão; (b) como plano B se o iOS recusar WSS autoassinado (risco R1).
- **Impactos:** o professor aceita um aviso de segurança na primeira conexão. Adiciona a dependência `cryptography`.
- **Status:** proposta · **Data:** 2026-11-06

## D005 — Rede em thread separada, ligada ao Qt por Signal

- **Problema:** o laço asyncio do servidor e o laço de eventos do Qt não podem bloquear um ao outro.
- **Alternativas:** (a) thread de rede + `Signal` do Qt; (b) `qasync` (um laço só); (c) processos separados.
- **Decisão:** (a). Não exige dependência extra, e a separação interface/rede fica explícita (`CLAUDE.md` §16).
- **Impactos:** os dados passam entre threads só por sinais enfileirados, nunca por estado compartilhado.
- **Status:** proposta · **Data:** 2026-11-06

## D006 — MediaPipe e modelo servidos localmente

- **Problema:** os exemplos oficiais carregam o MediaPipe por CDN, e o projeto não pode depender de internet (`CLAUDE.md` §6.2).
- **Decisão:** baixar uma versão **fixada** de `@mediapipe/tasks-vision` (bundle JS + pasta `wasm/`) e o modelo `hand_landmarker.task` para `mobile/vendor/`, servidos pelo notebook.
- **Versão fixada:** `@mediapipe/tasks-vision` **1.2.2** (Apache-2.0), baixada em 2026-11-06. Hashes em `mobile/vendor/README.md`. Modelo `hand_landmarker.task` baixado em 2026-11-06, SHA-256 `fbc2a300…7cde1`.
- **Impactos:** precisa de internet só na preparação. Atualizações do MediaPipe passam a ser decisões explícitas.
- **Status:** proposta · **Data:** 2026-11-06

## D007 — Token de sessão na URL

- **Problema:** outros aparelhos da mesma rede não podem enviar comandos para o notebook (`CLAUDE.md` §11).
- **Decisão:** gerar um token aleatório por sessão. Sem token, a resposta é HTTP 403.
- **Impactos:** proteção básica contra acesso casual. Não é segurança forte, o que fica documentado como limitação.
- **Status:** proposta · **Data:** 2026-11-06

## D008 — Plataformas de referência da Fase 1

- **Problema:** definir em quais equipamentos a Fase 1 será desenvolvida e validada (`CLAUDE.md` §12).
- **Decisão (do usuário):** celular **Android**. Notebook **macOS** para desenvolvimento e primeiro teste; notebook **Windows** do professor como destino, com validação obrigatória antes do uso em aula.
- **Impactos:**
  - O risco R1 (WSS autoassinado no iOS) deixa de bloquear a Fase 1. O suporte a iPhone não é declarado até ser testado.
  - O risco R7 (diferenças entre macOS e Windows) sobe para alto. Entra a etapa 1.7 (validação no Windows) no roteiro.
  - O código evita APIs específicas de um sistema operacional desde a primeira linha.
- **Status:** aprovada pelo usuário · **Data:** 2026-11-06

## D009 — Python 3.11 no ambiente virtual do projeto

- **Problema:** o `python3` padrão do Mac é o 3.15.0. O projeto precisa de uma versão que funcione igual no Mac e no Windows do professor.
- **Verificação (2026-11-06):** o PySide6 6.12.0 declara suporte a Python 3.10–3.15 (`Requires-Python: >=3.10,<3.16`), e há wheels para macOS (universal2) e Windows. As versões até a 6.11.x exigem Python < 3.15. O aiohttp também tem wheel para 3.15 no macOS arm64.
- **Alternativas:** (a) 3.15, já é o padrão do Mac, mas é muito recente e só funciona com o PySide6 a partir da 6.12; (b) **3.11**, já instalado no Mac, com o histórico mais longo de wheels de todas as bibliotecas e fácil de instalar no Windows; (c) instalar 3.12 ou 3.13.
- **Decisão:** (b) Python **3.11** no `.venv` do projeto, e a **mesma versão** no Windows.
- **Impactos:** o Python global do Mac não é alterado. Se o notebook do professor não puder ter o 3.11, a decisão é revista com base no `check_env.ps1`.
- **Status:** proposta · **Data:** 2026-11-06

## D010 — PySide6-Essentials no lugar do PySide6 completo

- **Problema:** `pip install PySide6` instalou também PySide6_Addons (90 MB), PySide6_WebEngine (250 MB) e PySide6_Pdf, que o projeto não usa. Isso pesa na instalação do notebook do professor e no empacotamento futuro (PyInstaller).
- **Verificação (2026-11-06):** o wheel `PySide6_Essentials` 6.12.0 contém QtCore, QtGui, QtWidgets e QtNetwork, suficientes para a janela do cursor e, mais adiante, para o overlay.
- **Decisão:** usar `PySide6-Essentials==6.12.0` no `requirements.txt`. Os imports continuam `from PySide6 import ...`.
- **Impactos:** a instalação fica algumas centenas de MB menor. Se algum módulo de Addons for necessário no futuro (ex.: QtMultimedia), a inclusão será uma nova decisão registrada.
- **Status:** proposta · **Data:** 2026-11-06

## D011 — Projeto fora das pastas protegidas do macOS

- **Problema (2026-11-06):** com o projeto em `~/Desktop`, a janela não abria. O Qt encerrava o processo com `Could not find the Qt platform plugin "cocoa"`, embora o arquivo `libqcocoa.dylib` estivesse no lugar certo.
- **Diagnóstico:** com `QT_DEBUG_PLUGINS=1`, o Qt examinou a pasta `.../PySide6/Qt/plugins/platforms` e não listou nenhum arquivo. O Python listou os três plugins normalmente. Com o mesmo plugin copiado para `/tmp`, o Qt abriu ("Qt OK fora da Mesa"). Conclusão: dentro da Mesa, que tem proteção de privacidade do macOS, o Qt não consegue listar os próprios plugins.
- **Alternativas:** (a) mover o projeto para uma pasta não protegida; (b) copiar os plugins para fora a cada execução e apontar `QT_QPA_PLATFORM_PLUGIN_PATH`, um contorno frágil; (c) dar ao Terminal "Acesso total ao disco", que exige mudar permissões do sistema do professor.
- **Decisão:** (a). O projeto passa a ficar em `~/Projetos/smartboard-classroom`. O `setup_mac.sh` se recusa a instalar dentro de Mesa, Documentos ou Downloads, e o `desktop.main` mostra uma mensagem clara em vez de travar. Os testes ficam em `tests/test_main.py`.
- **Impactos:** o problema não aparece no Linux. No Windows, a pasta Área de Trabalho pode ter equivalentes (OneDrive), o que deve ser verificado na etapa 1.7.
- **Status:** aplicada · **Data:** 2026-11-06

## D012 — Configuração do MediaPipe no celular (medida, não suposta)

- **Problema:** 8,5–11 FPS no moto g54 (etapa 1.4), abaixo do desejável para um cursor fluido (risco R2).
- **Medição (2026-11-06, log de sessão):** GPU 720p 11,2 FPS / 79 ms; GPU 480p 10,9 / 80 ms; CPU 720p 8,2 / 118 ms; CPU 480p 9,2 / 106 ms. Tabela completa em `testing.md`.
- **Decisão:** manter **GPU** como padrão (com CPU de reserva automática) e **720p**. Os parâmetros `&res=` e `&delegate=` continuam disponíveis para medir outros aparelhos.
- **Impactos:** o teto no aparelho de referência é ~11 FPS, limitado pelo MediaPipe. O próximo passo é atacar o R10 (MediaPipe bloqueando a página) com um **Web Worker** na etapa 1.5 e medir de novo pelo log. Se o resultado não bastar para o critério da Fase 1, a alternativa (b) da D002 (processar no notebook) volta à mesa para decisão com o usuário.
- **Status:** aplicada · **Data:** 2026-11-06

## D013 — Processamento da mão no notebook; o celular envia quadros JPEG

- **Problema:** com o MediaPipe no celular (D002), o moto g54 chega a ~11 FPS (D012), e o MediaPipe trava a página: o RTT sobe de 6,5 ms para 44–100 ms (R10). O cursor fica lento e atrasado.
- **Alternativas:**
  - (a) manter no celular e mover o MediaPipe para um Web Worker. Resolve o R10, mas não o teto de ~11 FPS do aparelho.
  - (b) celular envia quadros e o notebook roda o MediaPipe Python, a alternativa (b) da D002. Transporte avaliado:
    - **JPEG pelo WebSocket já existente:** sem dependência nova; o tamanho e a taxa ficam sob controle; dá para descartar quadros velhos.
    - **WebRTC:** menor latência teórica, mas exige servidor de sinalização e `aiortc` com ffmpeg, e decodificação de vídeo no notebook. Complexidade alta para a prova de conceito (CLAUDE.md §16: validar o simples antes).
- **Decisão:** (b), com JPEG pelo WebSocket (aprovado pelo usuário em 2026-11-06). Detalhes:
  - Envelope binário de 16 bytes, com magic, `seq` e `t_client_ms`, mais o JPEG (`communication-protocol.md` §2.7).
  - Lado maior de 640 px e qualidade 0,7 por padrão, ajustáveis na URL (`&side=`, `&q=`, `&fps=`).
  - **Contrapressão nos dois lados:**
    - o celular pula quadros se a fila do WebSocket passar de 64 KB ou se ainda houver JPEG em geração;
    - o notebook tem uma vaga única, e um quadro novo substitui o que esperava.
  - O MediaPipe Python (`mediapipe==1.2.2`) roda em thread própria, em modo VIDEO, com o mesmo `hand_landmarker.task` servido ao celular.
  - A saída é a mesma `HandTrackingMessage`, então a janela, o log e o mapeamento não mudaram.
  - O modo antigo continua disponível com `&mode=local` e agora também envia `hand_tracking`.
- **Ambiente de desenvolvimento:**
  - a "lousa" é a Smart TV do usuário, ligada ao Mac como segunda tela (não há projetor no setup);
  - a janela abre em tela cheia nela com `--screen N`;
  - a sala de aula real continua sendo notebook + projetor.
- **Impactos:**
  - ≈ 110 MB de dependências no notebook (MediaPipe, OpenCV, numpy, matplotlib). Rodas verificadas para Python 3.11 em macOS arm64 e Windows x64.
  - Tráfego de ~0,3–1,5 MB/s na rede local; precisa ser medido no Wi-Fi da escola (R11).
  - A imagem da câmera passa a sair do celular. Ela trafega só pela rede local, cifrada (WSS), e nunca é gravada (CLAUDE.md §11).
  - O desempenho passa a depender do notebook, o que precisa ser medido no Windows do professor (etapa 1.7).
  - A calibração da Fase 2 ganha acesso à imagem no notebook, onde o OpenCV já está.
- **Status:** aplicada (desenvolvimento) · validação no celular real pendente · **Data:** 2026-11-06


## D014 — Calibração com o dedo do professor sobre 4 alvos, com contagem regressiva

- **Problema:** o cursor fica "perto", mas não sob a ponta do dedo (2º teste real). As ferramentas flutuantes exigem exatidão.
- **Alternativas:**
  - (a) detecção automática da área projetada pela luminosidade (tela branca − tela preta);
  - (b) marcadores ArUco projetados;
  - (c) clique manual nos alvos sobre a imagem da câmera, no notebook;
  - (d) o professor encosta o indicador em cada alvo projetado até o fim de uma contagem regressiva.
- **Decisão:** (d), definida pelo usuário em 2026-11-06.
  - Ordem: superior esquerdo → inferior esquerdo → inferior direito → superior direito, com alvos a 5% da borda.
  - Calibração **a cada abertura** do programa, ou pelo modo "Calibrar perspectiva da tela".
  - Captura pela mediana da posição nos últimos 0,5 s, aceita só com mão detectada e dedo parado.
  - (c) fica como reserva; (a) e (b) ficam como atalhos futuros.
- **Impactos:**
  - o professor calibra sem sair da lousa;
  - a diferença entre a ponta real do dedo e o ponto do MediaPipe é absorvida pela calibração;
  - depende do rastreamento funcionar nos cantos (limitação 6 em `calibration.md`);
  - surge o sistema `surface_norm`;
  - a paralaxe do dedo afastado da superfície continua a ser medida (R5).
- **Detalhes:** `docs/calibration.md`.
- **Status:** abordagem aprovada; critério de precisão pendente · **Data:** 2026-11-06

## D015 — Marcadores ArUco fixos nos cantos para corrigir o movimento da câmera

- **Problema:** depois da calibração, qualquer movimento do celular desloca o cursor. O usuário perguntou se a visão poderia continuar achando a TV mesmo com o celular em outra perspectiva.
- **Alternativas:**
  - (1) detectar o movimento e pedir recalibração;
  - (2) estimar o movimento pelos detalhes da cena. Pouco confiável: a lousa é lisa e o conteúdo projetado muda;
  - (3) projetar 4 marcadores ArUco fixos nos cantos e recalcular a perspectiva continuamente.
- **Decisão:** (3), aprovada pelo usuário em 2026-11-06.
  - **Combinação com o dedo:** a calibração com o dedo (D014) continua e corrige a diferença entre a ponta real e a "ponta" do MediaPipe. Os marcadores medem só o movimento da câmera desde aquela calibração:
    - `H_final = H_dedo · H_marcadores_ref⁻¹ · H_marcadores_agora`.
  - **Visibilidade:** os marcadores somem durante a calibração com o dedo, porque os alvos ficam a 5% da borda, e aparecem logo depois. A referência é tomada nesse instante.
  - **Detalhes:**
    - dicionário `DICT_4X4_50`, ids 0–3 (SE, IE, ID, SD), com zona branca em volta;
    - tamanho configurável (`MARKER_SIZE_FRAC`);
    - detecção na thread de visão a cada 3 quadros, com todos os cantos detectados combinados por `findHomography`;
    - com menos de 2 marcadores visíveis (mão cobrindo, por exemplo), mantém a última correção.
- **Impactos:**
  - 4 quadrados brancos com desenho preto ficam visíveis nos cantos da lousa;
  - alguns milissegundos a mais por quadro detectado;
  - o tamanho mínimo legível depende da resolução: o celular na horizontal ajuda;
  - a imagem continua só em memória.
- **Status:** aprovada; implementação em teste · **Data:** 2026-11-06

## D016 — Com duas mãos visíveis, usar a que está junto à lousa

- **Problema** (relatado pelo usuário em 2026-11-06): explicando de lado, o professor aparece com os dois braços na câmera. O MediaPipe, com `num_hands = 1`, podia ficar com o braço afastado da lousa, e a mão que interage é a junto à superfície.
- **Decisão:**
  - `MAX_HANDS = 2`, com a escolha em `desktop/core/hand_selection.py`:
    1. prefere a mão cuja ponta está **sobre a área da lousa**, ou mais perto dela (com calibração);
    2. empate: prefere a mão que aparece **menor**. A câmera está de frente para a lousa, então a mão junto à superfície fica mais longe dela. Com calibração, o tamanho é medido na superfície;
    3. só troca de mão se a outra for claramente melhor: margens de 5% de distância ou 20% de tamanho.
  - A janela de diagnóstico mostra todas as mãos vistas (cinza) e a usada (vermelho).
  - O log ganha a fração de quadros com 2 mãos.
- **Impactos:**
  - **Custo:** com `num_hands = 2`, o MediaPipe procura a 2ª mão a cada quadro enquanto só vê uma. Nesta máquina passou de ~14 para ~27 ms por quadro. A medir no Mac; `--max-hands 1` volta ao modo anterior.
  - **Limitação:** a mão junto à lousa é a que aparece menor, e mãos pequenas na imagem podem não ser detectadas. No teste sintético em 640×360, a mão menor nem sempre foi achada. Quadros maiores (`&side=960`) ajudariam, com custo de latência.
  - **Situação que a regra não resolve:** quando só o braço errado é detectado e ele está sobre a lousa na imagem, o cursor o segue.
- **Status:** implementada; validação real pendente · **Data:** 2026-11-06

## D017 — A lousa como overlay sobre apresentações externas (opção B do §12)

- **Problema:** `PROJECT_CONTEXT.md` §12 pede uma análise técnica entre (A) apresentação própria e (B) camada transparente sobre PowerPoint, navegador etc.
- **Teste de viabilidade (etapa 3.0):**
  - **macOS:** janela Qt sem moldura, transparente, sempre por cima e transparente para o mouse. Foram precisos ajustes do sistema (`overlay_platform.py`):
    - painel que não se esconde nem rouba o foco;
    - presente em todos os Spaces e como auxiliar de tela cheia;
    - nível alto;
    - aplicativo como acessório.
  - **Resultado (2026-11-06 21:05):** a lousa ficou **por cima do navegador em tela cheia** na TV, com calibração e teste G funcionando. O mouse do notebook segue controlando a apresentação.
- **Decisão:** **(B) overlay**. Reaproveita o material que o professor já tem. (A) fica descartada por ora.
- **Impactos:**
  - comportamento específico de cada sistema;
  - **Windows ainda não validado** (etapa 1.7);
  - PowerPoint e Keynote em tela cheia no Mac não foram testados (só o navegador);
  - as teclas da lousa ficam na janela de diagnóstico.
- **Status:** aplicada (macOS + navegador) · **Data:** 2026-11-06

## D018 — Caneta pela pose da mão: só o indicador esticado escreve

- **Problema:** ainda não detectamos o toque do dedo na superfície (R5, Fase 5). Sem um sinal de "caneta na lousa", qualquer movimento da mão riscaria.
- **Alternativas apresentadas:** (A) pose da mão; (B) permanência para começar a riscar; (C) esperar a detecção de toque.
- **Decisão (usuário, 2026-11-06):** **(A) pose da mão.**
  - Indicador esticado com os outros dedos dobrados ("pointing") = caneta na lousa.
  - Mão aberta ou fechada = move sem riscar.
  - A pose vem da razão distância(pulso→ponta) ÷ distância(pulso→articulação do meio), por dedo. Não depende da rotação da mão.
  - Confirmação em quadros seguidos: 2 para descer, 3 para levantar (`config.PEN_*`). Um quadro ruim não quebra o traço.
- **Regras de segurança da interação (CLAUDE.md §7.3):**
  - a caneta só risca se **desceu fora da interface**: quem aponta um botão da sidebar precisa relaxar a mão antes de escrever, senão sairia um risco da sidebar até o ponto de escrita;
  - um traço que entra na sidebar para na borda, e a sidebar não reage até a caneta levantar;
  - perder a mão levanta a caneta;
  - "Limpar" pede "Limpar tudo?" com Sim/Não por permanência; some em 8 s. Limpar pode ser desfeito.
- **Impactos:**
  - só funciona no modo stream (processamento no notebook, D013). No modo local a pose não é calculada;
  - escrever com o indicador esticado e os outros dedos dobrados é natural, mas a pose pode falhar com a mão de lado para a câmera. A medir no teste real;
  - não substitui a detecção de toque (Fase 5): a caneta desce no ar, a alguns centímetros da lousa.
- **Status:** implementada; validação real pendente · **Data:** 2026-11-06

## D019 — Troca de slides pelas setas do teclado e anotações por slide

- **Problema:** RF19 pede navegar entre slides; a lousa é um overlay sobre apresentações externas (D017) e não conhece o slide.
- **Decisão:**
  - "Slide ant." e "Próx. slide" enviam ← e → ao aplicativo em primeiro plano. A lousa não rouba o foco, então a tecla chega à apresentação. Navegador, PowerPoint, Keynote e Impress usam essas setas.
  - Envio por ctypes, sem dependência nova: CGEventPost no macOS, keybd_event no Windows.
  - **Cada slide guarda as suas anotações** (escolha do usuário, 2026-11-06), cada um com o próprio Voltar/Avançar (`desktop/presentation/slides.py`).
  - Se a tecla não puder ser enviada, nem a apresentação nem a lousa mudam, e aparece um aviso.
- **Impactos:**
  - **macOS:** exige liberar o Terminal (ou o aplicativo que roda o Python) em Ajustes do Sistema → Privacidade e Segurança → Acessibilidade. Sem isso o sistema descarta a tecla. O programa verifica no início e registra `key_sender` no log.
  - **Limitação:** a contagem de slides vem dos botões. Trocar o slide pelo teclado, pelo clique ou pelo controle remoto desencontra as anotações. Avançar além do último slide também conta.
  - As anotações continuam só na memória.
  - Windows não validado (1.7).
- **Status:** implementada; validação real pendente · **Data:** 2026-11-06

## D020 — Precisão por correção dos 9 pontos e filtro One Euro, sem hardware novo

- **Problema:** depois da homografia, o erro muda pela superfície (teste G das 22:50: 3 px no centro e 39 px perto dos cantos), e o dedo treme parado.
- **Alternativas consideradas:** (A) correção residual com os 9 pontos do teste G + filtro One Euro; (B) estimativa 3D do dedo e do plano da parede; (C) câmera de profundidade ou estéreo.
- **Decisão (usuário, 2026-11-06):** (A), mais uma malha virtual de diagnóstico (tecla M).
  - (B) fica para depois do estudo do toque (5.3): com uma câmera só, as coordenadas 3D do MediaPipe são relativas à mão, não à parede.
  - (C) exigiria hardware extra antes de esgotar o que a câmera atual permite.
- **Impactos:**
  - o teste G passa a ser também um passo de calibração (≈ 60 s a mais, opcional);
  - o filtro acrescenta um atraso pequeno (~8 px na escrita, em simulação);
  - teclas novas: M (malha), R (correção), S (filtro).
- **Status:** implementada; validação real pendente · **Data:** 2026-11-06

## D021 — Pinça como alternativa à pose do indicador (em teste)

- **Origem:** o usuário quis testar o gesto do projeto ECE 445 da Univ. de Illinois (projetor + câmera RGB + ArUco + homografia + MediaPipe), em que o clique é a pinça.
- **Implementação:** a caneta desce quando a ponta do polegar (landmark 4) encosta na ponta do indicador (8). Medida: distância 4↔8 ÷ pulso→base do dedo médio. Desce abaixo de 0,35 e só sobe acima de 0,50 (histerese). O cursor continua na ponta do indicador.
- **Como usar:** tecla K alterna durante o uso; `--pen pinch` já começa assim. O padrão continua sendo a pose (D018).
- **A comparar no teste real:** traços partidos (`pen_up` com menos de 0,3 s), descidas sem querer e conforto. O log `pen_up` registra o modo e o valor da pinça.
- **Esperado, a confirmar:** a pinça é um sinal mais "binário" (dedos encostados ou não) e pode oscilar menos que a pose. Em compensação, com a mão de lado para a câmera o polegar pode ficar escondido atrás do indicador.
- **Medida na foto real (joinha):** pinça 0,82, longe de 0,35; não escreve.
- **Status:** implementada para teste; decisão depois da comparação · **Data:** 2026-11-07

## D022 — Reconhecimento da mão adaptado do open-source-hands (filtro nos pontos, forma 3D, nota com histerese)

- **Problema:** traços partidos por oscilação da pose (5.1), pior com a mão de lado para a câmera.
- **Origem:** open-source-hands (Meticulai), licença MIT, commit `dd79fb7`; o usuário decidiu (2026-11-07) copiar dele onde houver melhoria. Atribuição no topo de `desktop/vision/gestures.py` e `synthetic_hands.py`; detalhes em `docs/references.md`.
- **O que foi adaptado:**
  1. One Euro nos 63 valores da mão (imagem e mundo) antes de medir a forma: 2,2 Hz / 8 / 1.
  2. Forma pelos pontos 3D do mundo do MediaPipe (`hand_world_landmarks`, antes descartados). Dobra do dedo pela soma dos ângulos das articulações, a da base pela metade.
  3. Pose = nota 0–1 (√(média geométrica × pior regra)); entra ≥ 0,62, sai < 0,42, margem 0,08, troca confirmada em 70 ms (112 ms para "nenhuma"); mão sumida por 250 ms é esquecida.
  4. One Euro do cursor com velocidade vetorial e intervalo limitado a 1–100 ms.
  5. Mãos sintéticas 3D parametrizadas (dobra por dedo, pinça, rotação, abertura).
- **Adaptações para a lousa:** "mão aberta" não exige a palma voltada para a câmera (a câmera costuma ver as costas da mão); só as poses úteis mais as que absorvem mãos ambíguas (V, garra, OK); pinça pela distância nos pontos 3D com ON 0,30 / OFF 0,42 (antes 0,35 / 0,50 na imagem 2D).
- **Simulação (mão de 7% da imagem, tremor 0,004, 20 s):** mão a 70° com dedos relaxados — antigo 108 trocas de pose, novo 0; mão meio fechada a 50° — antigo 317, novo 0. Com o indicador meio dobrado de frente (pose ambígua), o novo prefere não escrever (30% do tempo) a piscar (antigo: 181 trocas).
- **Comparação real:** o reconhecimento antigo roda em paralelo nos mesmos quadros (`pose_alt`); o log `vision` conta as trocas de pose dos dois, e `tools.log_summary` mostra por minuto. `--gesture legacy` volta ao antigo.
- **Não copiado (por ora):** gestos de movimento e de duas mãos (mudam a experiência do professor; exigem aprovação) e o laboratório de gestos.
- **Status:** implementado; validação real pendente · **Data:** 2026-11-07

## D023 — Assistente de calibração ao abrir o programa

- **Pedido do usuário (2026-11-07):** em vez de decorar teclas (C, V, G…), a calibração deve mostrar as instruções em ordem e só passar à etapa seguinte depois de concluir a atual, automatizando os testes iniciais. Ele considerou também um botão "i" com os atalhos, mas preferiu o assistente.
- **Decisão:** ao abrir, o assistente faz 4 etapas: **cantos (C) → verificação sem correção (V) → correção pelos 9 pontos (G) → verificação com correção (V)**, e termina com um resumo antes × depois.
  - Antes de cada etapa, um cartão com a instrução fica 5 s na tela, com contagem.
  - Durante a etapa, o título mostra "Etapa n de 4 ·".
  - Os avisos de cada teste ficam ocultos, porque o cartão já informa.
  - O resumo fica 12 s na tela. Se a correção piorar o erro, o resumo avisa e sugere R.
  - Esc cancela; A recomeça; `--quick` volta ao comportamento antigo (só os 4 cantos).
- **Impacto:** abrir o programa passa a levar ~3 min, contra ~45 s antes (cantos 5 × 7 s; V 4 × 7 s; G 9 × 7 s; V 4 × 7 s; mais os cartões). Adequado na fase de testes. Para o uso diário em aula, avaliar depois `--quick` como padrão, ou o assistente só quando a câmera mudou de lugar.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D024 — Mais do open-source-hands: gestos de movimento, gravação dos pontos e laboratório

- **Pedido do usuário (2026-11-07):** aplicar as melhorias restantes do repositório. Gestos escolhidos por ele: deslizar → trocar slide; duas mãos → tamanho; toque de pinça → clique.
- **Gestos de movimento** (`desktop/interaction/motions.py`, adaptado de `motions.ts` e `engine.ts`, MIT):
  - **Deslizar ← →:** 20% da largura em 0,38 s, eixo horizontal 1,8× maior que o vertical. Deslizar para a esquerda avança o slide, para a direita volta. Diferenças em relação ao kit: medido na lousa (não na câmera), **só com a mão aberta** durante todo o movimento (um traço rápido com o indicador não troca o slide), não dispara com a caneta riscando nem com as duas mãos em uso. Intervalo mínimo de 0,65 s entre dois.
  - **Toque de pinça:** fechar (força > 0,75) e abrir (< 0,40) em até 0,35 s aciona na hora o botão sob o dedo, sem os 0,6 s de permanência.
  - **Duas mãos:** com um desenho em redimensionamento (Selecionar, 4.6), as duas mãos em pinça (ou as duas fechadas) dão zoom = distância atual ÷ inicial. Durante o zoom a abertura da mão é ignorada e a caneta fica levantada. Ao soltar, a abertura volta a valer; a mão parada por 1 s confirma. Tudo é uma ação só de Voltar.
  - Tecla **H** liga/desliga os três. Ligados por padrão nesta fase de testes.
- **Gravação dos pontos da mão** (`--record`, `desktop/vision/landmark_recorder.py`): só os 21 pontos (imagem e mundo), a lateralidade e o tempo, em `logs/landmarks-*.jsonl.gz`. **Nenhuma imagem** (CLAUDE.md §11). `python -m tools.replay_landmarks` reproduz a sessão sem câmera, compara os reconhecimentos e aceita outros limiares (`--enter`, `--exit`, `--debounce`) para ajustar com dados reais.
- **Laboratório de gestos** (tecla **L**, `desktop/interaction/gesture_lab.py`): pede 6 gestos (apontar, aberta, fechada, pinça, apontar de lado, aberta de lado), 5 s cada, e mede acerto (após 1 s), tempo de reação e confusões, novo × antigo nos mesmos quadros. Resultado na tela e no log (`lab_done`).
- **Riscos a observar:** deslizar trocar slide durante a explicação (mão aberta passando rápido); toque de pinça acionar botão sem querer. O log registra `motion_swipe`, `motion_click`, `draw_zoom`.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

### D024 — ajuste com a gravação real (2026-11-07 12:22)
- Toque de pinça: fecha com distância < 0,18, abre > 0,33, anulado se a mão fechar no meio (0 falsos na gravação, contra 11 com a força da pinça do kit).
- Caneta no modo pinça (D021): desce < 0,15, sobe > 0,30, nunca com a mão fechada (0,6% do tempo descida sem querer, contra 13,5%).
- (13:35) Toque de pinça: a pinça precisa aparecer fechada em ≥ 2 quadros (falhas de 1 quadro do rastreamento geravam toques falsos: 17 → 0 na gravação).
- (13:41) Assistente (D023): se a verificação com correção ficar pior que a sem correção, a correção é desligada sozinha (R liga de novo).

## D025 — Abrir com dois cliques e conectar o celular por QR code

- **Escolha do usuário (2026-11-07):** próximo passo = abrir sem terminal. No primeiro uso houve "zsh: command not found: python" por rodar fora da pasta e sem o `.venv`.
- **Decisão:**
  - `SmartBoard.command` (macOS, dois cliques no Finder): vai para a pasta do projeto; na 1ª vez roda `scripts/setup_mac.sh`; reinstala dependências só quando `requirements.txt` muda (carimbo SHA-256 em `.venv/`); abre `--overlay --screen auto`; em caso de erro, mantém a janela aberta com a mensagem.
  - `SmartBoard.bat` (Windows): o mesmo com `py -3.11`, incluindo baixar o modelo da mão. **Não testado** (etapa 1.7 pendente).
  - `--screen auto`: a primeira tela que não é a principal (TV/projetor); sem ela, a principal.
  - **Cartão "Conecte o celular"** na lousa até o celular conectar: QR code com o endereço + token, o endereço em texto e as instruções. O assistente de calibração espera o celular conectar. O token continua sorteado a cada abertura (D007); o QR elimina a digitação.
- **Dependência nova:** `segno==1.6.6` (QR code). BSD-3, Python puro, sem dependências, ~76 KB, mantida. Alternativa avaliada: `qrcode` (precisa de Pillow para gerar imagem). Sem segno, o cartão mostra só o endereço.
- **Status:** implementado; teste real pendente (Mac); Windows não testado · **Data:** 2026-11-07

## D026 — Ajuste do reconhecimento novo à mão real: apontar relaxado e caneta livre

- **Relato do usuário (2026-11-07 14:05):** "os gestos não estão bons"; sugeriu usar o projeto do GitHub por ser melhor.
- **Diagnóstico com as 3 gravações reais (12:22, 13:35, 13:59):** o problema não era o kit em si, mas dois pontos da integração:
  1. **Caneta presa (meu erro):** a regra da 5.1 ("pose indefinida não levanta a caneta") somada ao reconhecimento novo, que deixa a mão relaxada "sem pose" 42% do tempo. A caneta ficou descida por 18 a 63 s seguidos.
  2. **Apontar do kit rígido demais:** a regra exige médio/anelar/mínimo bem dobrados (> 0,74). O apontar real do professor tem esses dedos meio dobrados (mediana ~0,55). O kit reconhecia só 63–66% do tempo em que ele apontava.
- **Usar o código do GitHub direto não resolveria:** a regra de apontar já é a deles, copiada (D022), e falharia igual. O código deles é TypeScript para navegador com webcam de frente; a câmera da lousa vê a mão de lado e de longe.
- **Decisão:**
  - "Apontar" aceita os outros dedos "não esticados" (`notext`) em vez de "dobrados": reconhecimento 63% → 92% (13:59) e 66% → 85% (13:35); mão relaxada continua não sendo apontar.
  - A regra "pose indefinida mantém a caneta" vale só com o reconhecimento antigo; com o novo, a caneta sobe quando o apontar acaba (a histerese do kit já evita a oscilação).
  - Piscadas continuam muito abaixo do antigo: 21 × 178 (13:59), 40 × 716 (13:35), 8 × 69 (12:22).
- **Testes:** as gravações viraram testes de regressão no Mac (o apontar real deve ser reconhecido em > 82% dos quadros em que o antigo o vê).
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D027 — Guardar, recuperar e exportar as anotações (etapa 6.3)

- **Pedido do usuário (2026-11-07):** avançar o desenvolvimento; a 6.3 estava "a decidir". Escolhidos os padrões mais seguros, ajustáveis depois.
- **Decisão:**
  - **Salvar sozinho:** as anotações de todos os slides vão para `anotacoes/aula-AAAAMMDD-HHMMSS.json`, no máximo a cada 2 s depois de uma mudança, e ao sair (Q, Ctrl+C, fechar a janela do Terminal). A gravação usa arquivo temporário + troca, para um desligamento não corromper o arquivo. Sem anotações, nenhum arquivo é criado.
  - **Recuperar (tecla O):** traz a aula salva mais recente (sem contar a atual). **Não restaura sozinho ao abrir**, porque a próxima aula pode ser outra apresentação. A lousa volta ao slide 1; o professor deve pôr a apresentação no 1º slide.
  - **Exportar PDF (tecla E):** `anotacoes/aula-….pdf`, uma página por slide anotado, fundo branco, número do slide no rodapé. Só as anotações: o slide em si não é capturado (não capturamos a tela). Usa o `QPdfWriter` do Qt, sem dependência nova.
  - O histórico de Voltar/Avançar não é salvo. `anotacoes/` fica fora do controle de versão (dados do professor).
- **A decidir depois:** botão na sidebar para exportar; apagar aulas antigas; PDF com o slide de fundo (exigiria capturar a tela ou ler o arquivo da apresentação).
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D028 — Marcadores dos cantos mais discretos: borda menor e escondidos após calibrar

- **Pedido do usuário (antigo, retomado em 2026-11-07):** deixar os marcadores dos cantos menores e mais discretos.
- **Medição nos logs reais (12:22, 13:35, 13:59):** os marcadores chegam ao notebook com **18–20 px de lado** (o celular reduz a imagem para 640 px) e foram vistos em só 50–70% das leituras (o marcador 2 caiu para 18% numa sessão). Já estão no limite: só diminuir o tamanho quebraria a compensação de movimento do celular.
- **Simulação (DICT_4X4_50, perspectiva, desfoque, JPEG 70, 640×360):** com borda branca de 0,25 / 0,20 / 0,17 / 0,12 a detecção ficou igual dentro do ruído (19 px: 80/82/79/81%; 26 px: 99/99/100/99%). Sem borda caiu (74% a 19 px).
- **Alternativas apresentadas:** borda menor; enviar imagem maior (960 px) e marcador ~8%; esconder após calibrar; manter.
- **Decisão (usuário, 2026-11-07):** borda menor **e** esconder após calibrar.
  - `MARKER_QUIET_FRAC` 0,25 → **0,17** (≈ 1 célula do ArUco): área ocupada ~20% menor; tamanho do marcador mantido em 12%.
  - Os marcadores aparecem antes de calibrar (para mirar o celular), enquanto a referência é procurada, na calibração/testes G e V/assistente, e **somem 1 s depois da referência ok**. Escondidos, a **última correção fica valendo**.
  - **Tecla N:** mostra os marcadores (por exemplo, o celular foi mexido): a compensação volta a acompanhar e corrige o deslocamento sem recalibrar. N de novo esconde. Se a referência tinha falhado, N tenta registrá-la de novo.
  - Desliga com `MARKERS_HIDE_AFTER_CALIBRATION = False` (comportamento antigo).
- **Limitação (resolvida pela D030):** com os marcadores escondidos, um celular mexido não era percebido sozinho; o cursor ficava deslocado até o professor apertar N (ou recalibrar). A detecção ArUco continua rodando no notebook mesmo com eles escondidos (custo pequeno, a cada 3 quadros); desligar isso fica para depois, se a medição de CPU pedir.
- **Testes:** referência → somem após 1 s → nada é detectado nos cantos; celular mexido → N → correção acompanha (erro < 1,5% da tela); N → somem e a correção continua. 457 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D029 — Estudo do toque na superfície: coleta guiada e relatório (etapa 5.3)

- **Contexto:** a caneta desce pela pose da mão, no ar. A 5.3 pede medir, com dados reais, se dá para reconhecer "dedo encostado" só com os pontos da mão, sem decidir antes.
- **Decisão:** instrumento de medição, sem mudar o comportamento da caneta.
  - **Tecla T:** coleta guiada no estilo do assistente (D023): cada etapa mostra o alvo ou a linha, dá 3 s para posicionar a mão e grava 5 s. Em 3 lugares da lousa: encostado × ~2 cm × ~5 cm, parado e arrastando (15 etapas, ~2 min). Sidebar, desenho e gestos de movimento ficam parados durante o estudo.
  - A gravação dos pontos da mão (D024) passa a poder ser ligada no meio da sessão; T a liga se não estava. Só pontos, nenhuma imagem (CLAUDE.md §11).
  - Cada etapa vira `touch_phase` no log, com início e fim no relógio monotônico, o mesmo da gravação.
  - `tools/touch_report.py` cruza log e gravação e mede 5 sinais da mão que está na lousa (a de palma menor): dobra da ponta, dobra do meio, ponta encurtada, profundidade da ponta, tremor. Para cada um: separação (AUC) e coerência por rodada. Os quadros vizinhos são parecidos, por isso a coerência por rodada é exigida além da AUC.
- **Limites:** a sombra (só com projetor) e a 2ª câmera rasante não são medidas aqui. Os testes usam mãos sintéticas e só provam que o instrumento acha um sinal quando ele existe; a conclusão depende da coleta real.
- **Status:** implementado e testado (pytest, 466 passando); coleta real pendente · **Data:** 2026-11-07

## D030 — Celular mexido com os marcadores escondidos: os cantos voltam sozinhos

- **Relato do usuário (2026-11-07 14:49):** depois que os cantos somem (D028), ao movimentar o celular o enquadramento automático não funciona. Pedido: "quando o celular se movimenta, os cantos retornam automaticamente; quando para, somem".
- **Alternativas avaliadas:**
  1. Sensores do celular (acelerômetro/giroscópio no navegador): no iPhone exige permissão por toque e mudaria o app do celular; um celular apoiado e mexido devagar pode não acusar.
  2. Comparar a imagem que já chega ao notebook com uma foto de referência (escolhida): não muda o celular, não pede permissão e vê o que importa (o enquadramento mudou).
- **Decisão:**
  - Quando os marcadores somem e há uma correção valendo, a visão tira uma **foto de referência** (cinza, 160 px, só na memória) e, a cada leitura dos marcadores (1 em cada 3 quadros), mede o deslocamento da cena por correlação de fase.
  - A **área da lousa é excluída** (o slide e as anotações mudam ali) quando a parede em volta tem textura; numa parede lisa, usa-se a imagem toda.
  - **Celular mexido** = 3 medidas seguidas acima de 0,8% da imagem, nítidas e **concordando entre si**. Alguém passando muda a medida a cada quadro e não dispara.
  - Os cantos **voltam sozinhos** ("O celular mexeu: marcadores de volta para reenquadrar"), a compensação (D015) recalcula a posição, e quando as leituras ficam firmes por 6 leituras seguidas e pelo menos 1 s (**celular parado**), eles **somem de novo** e uma nova foto de referência é tirada.
  - Log: `phone_moved` (deslocamento, nitidez) e `phone_reframed` (deslocamento corrigido, segundos). N continua funcionando à mão.
- **Limites:** um movimento muito lento (escorregando aos poucos) só é percebido quando passa de 0,8% em relação à foto de referência; uma mudança grande de luz na sala pode disparar uma volta dos cantos (inofensiva: somem logo depois). Os limiares saem de simulação e devem ser conferidos no log real.
- **Testes:** simulação com parede, lousa e slide: deslocamento de 12×8 px medido com erro < 1%; troca de slide e pessoa passando não disparam; parede lisa usa a imagem toda; processador só mede enquanto vigia; na janela, medidas discordantes não disparam, medidas firmes trazem os cantos, a câmera vê o novo lugar, os cantos somem e o cursor volta para baixo do dedo. 472 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D031 — Fechamento das funcionalidades: Salvar PDF na barra, preferências entre aulas, consumo no log

- **Pedido do usuário (2026-11-07 14:56):** "termine o projeto e os testes ficam por último".
- **Revisão dos requisitos (PROJECT_CONTEXT §13):** RF01–RF32 têm implementação e testes automatizados. Faltavam, para usar na aula sem teclado e para a Fase 7:
  1. **Salvar PDF só pela tecla E:** o professor na lousa não alcança o teclado. → botão **Salvar PDF** na barra (14 botões, 2 colunas × 7). Sem pasta de anotações (simulação), avisa em vez de falhar.
  2. **RF30 (preservar orientação e posição):** valia só durante a sessão. → `preferencias.json` guarda borda, posição e orientação da barra e cor/espessura/borracha; gravado só quando muda, com troca atômica; arquivo inválido é ignorado. O modo da caneta continua vindo da opção `--pen`/tecla K.
  3. **Consumo (§14 "baixo consumo", CLAUDE.md §10):** não era medido. → o evento `vision` de cada segundo traz `cpu_pct` (CPU do programa ÷ tempo real) e `rss_peak_mb` (pico de memória; não disponível no Windows); `log_summary` mostra mediana/p95 e as voltas dos cantos (D030).
  4. **Teste real espalhado em vários documentos:** → `docs/field-test.md`, um roteiro em ordem com o que confirma cada item no log.
- **Não feito (depende de equipamento ou decisão):** empacotar em aplicativo (PyInstaller), validar no Windows, apagar aulas antigas, PDF com o slide de fundo.
- **Testes:** 479 passando.
- **Status:** implementado; teste real no roteiro · **Data:** 2026-11-07

## D032 — Ao abrir, só os cantos; o ajuste completo vai para a tecla A

- **Pergunta do usuário (2026-11-07 15:02):** os testes rodam sempre ao iniciar? Ao abrir, rodava o assistente completo (D023: cantos → V → G → V, ~2–3 min), longo para o começo de toda aula.
- **Decisão (usuário, 15:05):** ao abrir, **só os 4 cantos** (~30 s). O assistente completo continua na **tecla A**, para quando a precisão parecer ruim; o aviso de "Tela calibrada" lembra disso. `--guided` abre com o assistente completo; `--quick` continua aceita (agora é o padrão).
- **Efeito:** sem o teste dos 9 pontos ao abrir, a correção residual não é aplicada até o professor apertar A (ou G). Nas sessões medidas ela melhorou de −17% a −55% e piorou numa; o ganho fica disponível sob demanda.
- **Status:** implementado; teste real no roteiro (field-test, item 2) · **Data:** 2026-11-07

## D033 — Formas desenhadas à mão viram formas perfeitas (Pincel)

- **Pedido do usuário (2026-11-07 15:17):** aprovou a melhoria 2 da pesquisa (reconhecedor "$1", Wobbrock, Wilson e Li, UIST 2007, e variantes que devolvem o círculo/retângulo ajustado).
- **Decisão:** ao levantar o Pincel, o traço é testado contra três formas, por **ajuste geométrico** (sem modelos desenhados, sem biblioteca nova):
  - **linha reta:** traço aberto perto da reta entre início e fim (erro médio ≤ 3,5% do comprimento; sem ida e volta);
  - **círculo:** traço fechado (fim a ≤ 18% do comprimento do início) que dá a volta (≥ 10 de 12 setores) e com raio quase constante (ajuste de Kåsa, erro ≤ 9% do raio);
  - **retângulo:** traço fechado perto das bordas da caixa (≤ 4,5% da diagonal) e que passa perto dos 4 cantos; alinhado à tela, como a ferramenta Retângulo.
  - Escolhe a de menor erro; senão, fica o traço livre (letras, rabiscos, formas tortas).
- **Voltar** devolve o traço como foi desenhado (a troca é uma ação no histórico); Voltar de novo apaga.
- **Limites:** elipses alongadas e retângulos girados continuam traço livre (os itens da lousa são círculo e retângulo alinhado). Uma letra "O" ou um "0" grande vira círculo; um "l" ou sublinhado vira linha reta (visualmente quase igual). Desliga com `SHAPE_SNAP_ENABLED = False`.
- **Testes:** círculo e retângulo tremidos (ruído até 15 px) reconhecidos em 20/20 e 19/20; meio círculo, "S", zigue-zague, ida e volta e traço minúsculo ficam livres; Voltar devolve o traço.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D034 — Calibração automática pelos marcadores e reaproveitamento da última aula

- **Pedido do usuário (2026-11-07 15:17):** aprovou a melhoria 1 da pesquisa (sistemas projetor-câmera que se calibram pela homografia entre a imagem projetada e a câmera — Sukthankar et al., ICCV 2001).
- **Por que ainda havia toques:** os marcadores (D015) dão a perspectiva da tela; mas a ponta do dedo que a câmera vê fica um pouco à frente do ponto encostado. Os 4 toques mediam isso junto.
- **Decisão — ao abrir (substitui os 4 cantos da D032):**
  1. Procura os marcadores (3 leituras seguidas concordando, com ≥ 3 marcadores).
  2. **Mesmo lugar da última aula** (cada canto dos marcadores a ≤ 0,8% da imagem, mesma tela): **reaproveita** a calibração gravada em `calibracao.json`. Nenhum toque.
  3. **Celular em outro lugar:** perspectiva pelos marcadores + **1 toque no centro**, que mede o deslocamento do dedo e o desconta em toda a tela. Se o deslocamento passar de 6% da tela, não é o dedo: vai para os 4 cantos.
  4. **Marcadores não vistos** em 6 s (contados depois de o celular conectar): os 4 cantos.
- A calibração é gravada quando a referência dos marcadores é registrada (todo modo: automático, cantos, assistente). Só números, nenhuma imagem.
- A tecla A (assistente completo) e C (cantos) continuam iguais.
- **Limites:** o deslocamento do dedo é medido num ponto só e aplicado igual na tela toda; com a câmera muito de lado, ele varia entre as bordas — o teste V mostra quanto, e A/G corrigem. A correção dos 9 pontos não é gravada (vale só na sessão).
- **Testes:** marcadores + 1 toque corrigem o deslocamento do dedo (erro < 1% em pontos fora do centro); próxima aula com o celular parado reaproveita sem toque; celular movido pede 1 toque; sem marcadores, 4 cantos; toque longe demais, 4 cantos; espera o celular conectar; arquivo inválido ou tela diferente é ignorado. 493 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D035 — Redimensionar pela distância da mão à câmera

- **Pedido do usuário (2026-11-07 16:43):** com um desenho selecionado, aproximar a mão da câmera amplia e aproximar da lousa reduz; o movimento para os lados continua igual (arrastar). Substitui abrir/fechar a mão (etapa 4.6).
- **Sinal:** tamanho aparente da palma na câmera (`palm_size_px`, já calculado para escolher entre duas mãos). Mais perto da câmera = palma maior.
- **Regra (ajustada pelo usuário às 16:49):** com o indicador segurando o desenho, os lados movem **e** a palma muda o tamanho ao mesmo tempo (escala = (palma ÷ referência)^1,0, referência 0,15 s depois de pegar). Abrir a mão solta (posição e tamanho ficam); 1 s parada confirma. Pegada inteira = uma ação de Voltar. Duas mãos (D024) continua igual.
- **Alternativa mantida:** `RESIZE_SIGNAL = "openness"` volta ao abrir/fechar.
- **Limites:** girar a mão muda a palma aparente; aproximar a mão da câmera também desloca a ponta do dedo na imagem (o desenho pode andar um pouco); ganho 1,0 a confirmar com o log (`draw_resize`).
- **Testes:** segurando, ir à direita e à câmera (60 → 90 px) move e amplia > 1,35×; soltar não muda o tamanho; 1 s confirma; Voltar desfaz a pegada inteira; levando para a lousa reduz < 0,7×; sem mão confirma na hora; os testes antigos de abertura rodam com `openness`. 497 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

### Ajustes do 1º teste real (2026-11-07 16:57) — D030, D034, D035

- **D034:** marcadores não vistos nos 6 s após conectar (celular ainda sendo posicionado) → `CALIB_AUTO_WAIT_S` = 20 s; aviso indica a tecla C. Reaproveitamento funcionou (sem toque).
- **D035:** ruído da palma mudava o tamanho em ±5% só ao mover (22 de 26 pegadas) → zona morta de 8% (`RESIZE_SIZE_DEADZONE`); alcance pequeno (palma 28 → 40 px = 1,45×) → ganho 1,8.
- **D030:** cantos voltaram 2× enquanto a mão segurava desenhos perto da câmera → vigilância da cena ignorada enquanto um desenho está seguro ou em confirmação.

## D036 — Esqueleto da mão na janela da câmera, com palma × dorso

- **Pedido do usuário (2026-11-07 20:46):** testar como na demonstração do open-source-hands: a mão com todos os pontos marcados, de frente (palma) ou de costas (dorso).
- **Decisão:** a janela da câmera (no notebook, não na lousa) desenha o **esqueleto de cada mão**: os 21 pontos do MediaPipe ligados, uma cor por dedo (polegar laranja, indicador vermelho, médio amarelo, anelar verde, mindinho azul), pontas maiores, e embaixo do pulso **qual mão é** e se a câmera vê a **palma**, o **dorso** ou a mão **de lado**.
  - Os 21 pontos passam a ir no `HandState` (`landmarks`), só no notebook; não trafegam pela rede nem vão ao log.
  - Palma × dorso: sinal do produto vetorial (pulso→base do indicador) × (pulso→base do mindinho), combinado com qual mão é. O MediaPipe nomeia a mão supondo imagem espelhada; a câmera traseira não espelha (`CAMERA_MIRRORED = False`), então "Left" é a direita de verdade.
- **Limites:** é diagnóstico; nada na lousa depende disso. Se o nome da mão ou palma/dorso aparecer trocado no teste real, é só inverter `CAMERA_MIRRORED`.
- **Testes:** palma/dorso para as duas mãos, câmera espelhada, mão de lado, os 21 pontos saindo do MediaPipe e o esqueleto desenhado na janela (cores conferidas por pixel). 503 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D037 — Celular: aba em segundo plano solta a conexão e a câmera

- **Relato do usuário (2026-11-07 20:53):** ao abrir pelo QR, a página no celular dizia "Desconectado".
- **Log (`session-20261107-205143`):** um celular **estava** conectado (20:52:04, câmera 720×1280), mas mandando **0 quadros/s** o tempo todo; a calibração não recebeu nenhum quadro. É o retrato de uma aba antiga em segundo plano: o navegador pausa a câmera dela, mas a conexão continuava aberta, ocupando a lousa. A aba nova (do QR) ainda não tinha tocado em "Iniciar" (a página começa mostrando "Desconectado") e, se tocasse, podia achar a câmera presa pela aba antiga.
- **Decisão (cliente 0.4.1):**
  - Aba escondida → fecha a conexão e solta a câmera; ao voltar para ela, a página recarrega.
  - Antes de tocar em Iniciar, o estado mostra "Toque em Iniciar" em vez de "Desconectado".
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

## D038 — Dois indicadores num desenho selecionado: zoom, sem a palma da outra mão encolher

- **Relato do usuário (2026-11-07 21:10):** com um desenho selecionado, ao colocar o segundo dedo para aumentar com os dois, assim que entrava o dedo mais longe da câmera a aplicação dava prioridade ao dedo mais perto da lousa e **reduzia** o desenho.
- **Log (`session-20261107-210959`, sem gravação de landmarks):**
  - Redimensionamento aos 204 s: **duas mãos visíveis em todos os quadros** de 202,8 a 209 s; palma de referência 39,3 px → final 30,6 px → desenho a 0,74×. O seletor de mãos (`hand_selection`) escolhe a mão mais perto da lousa, a de palma menor; o sinal de tamanho (D035) passou a ler a palma **dessa outra mão** e entendeu "mão foi para a lousa" → encolheu. Confirma o relato.
  - Aos 186 s (0,53×, palma 44,9 → 28,9) só uma mão foi detectada: troca de identidade do MediaPipe com as mãos sobrepostas ou movimento real (sem landmarks gravados, não dá para afirmar).
  - Dois indicadores apontando **não eram** gesto de zoom: o zoom de duas mãos (D024) só aceitava pinça ou punho.
- **Decisão:**
  - Com um desenho seguro ou em confirmação na ferramenta Selecionar, **dois indicadores apontando** também fazem o zoom de duas mãos (afastar amplia, aproximar reduz). Fora disso continua só pinça/punho, para não confundir com o professor apontando com as duas mãos.
  - Salto da palma maior que 18% de um quadro para o outro (`RESIZE_PALM_JUMP`) é tratado como **troca de mão**, não como aproximação: o tamanho atual fica e a medida recomeça a partir da mão nova.
  - Enquanto as duas mãos seguram, a confirmação de 1 s não corre; se uma mão sai e a outra volta a apontar (confirma), o zoom é registrado (`draw_zoom`) antes de fechar.
- **Testes:** dois indicadores só fazem zoom quando permitido; outra mão assumindo não redimensiona; teste da janela com o desenho seguro, a segunda mão (palma menor) entrando e as duas se afastando → desenho maior, `draw_zoom` no log, e não encolhe ao soltar. 506 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-07

### Resultado do estudo do toque (D029) — teste real 2026-11-07 21:28

- Sessão `session-20261107-212518`, gravação `landmarks-20261107-212801` · 15 etapas, 95–124 quadros cada. Calibração por cantos antes do estudo: erro 9 px (0,48%).
- **Encostado × no ar a ~5 cm:** a profundidade da ponta do dedo separa bem (0,94–0,96, coerente nas 3 rodadas); `ponta_curta` 0,80–0,86.
- **Encostado × no ar a ~2 cm:** nenhum sinal passa do critério (separação ≥ 0,8 e todas as rodadas coerentes). O melhor, a profundidade da ponta arrastando, chega a 0,82 mas só arrastando; parado fica em 0,53.
- **Conclusão:** só com a câmera do celular não dá para saber com segurança se o dedo encostou na lousa ou está a 2 cm dela. A caneta continua descendo pela pose da mão. Profundidade da ponta poderia, no máximo, ajudar a recusar o dedo bem afastado (≥ 5 cm), com um único teste até agora.
- **Observado na mesma sessão:**
  - a calibração automática não viu os marcadores nos 20 s e caiu para os cantos: em 367 verificações, só 13 viram algum marcador;
  - durante o estudo, um falso "celular mexeu" (resposta 0,11, perto do mínimo 0,08) deixou os cantos visíveis por 139 s.
  - Os dois ficam para investigar.

## D039 — Confirmação por gesto: "aberta" e "fechada" mais lentas que "apontar"

- **Pergunta do usuário (2026-11-10):** ao ver um laboratório de mão/OSC de terceiros (Meta Quest 3) que usa tempos de confirmação diferentes por gesto (42/72/96/340 ms), se valeria ajustar aqui.
- **Medido nos logs reais** (6 gravações com `--record`, 32 min de mão única): com a confirmação atual (70 ms para todas as poses), "fechada" pisca (dura < 0,2 s) em 14% das trocas e "aberta" em 9%; "apontar", a pose mais usada (escrever, selecionar), já piscava só 6% — e continuava em 6–7% mesmo testando 50 a 200 ms, ou seja, mais tempo não ajudava nela.
- **Decisão:** confirmação por gesto (`GESTURE_DEBOUNCE_BY_POSE_S`): "aberta" e "fechada" passam a confirmar em 150 ms; "apontar" continua em 70 ms (`GESTURE_DEBOUNCE_S`), sem o atraso que não trazia ganho. Com isso, nos mesmos logs, "fechada" caiu de 14% para 7% de piscada e "aberta" de 9% para 8%, sem atrasar o apontar.
- **Por que só essas duas:** "fechada" controla o zoom de duas mãos (D038) e "aberta" solta o desenho segurado (D035); um atraso de 80 ms além do antigo é imperceptível para soltar, e evita trocar de gesto por acidente no meio do movimento.
- **Testes:** `test_open_and_fist_need_longer_debounce_than_point` (133 ms de punho ainda não confirma; depois de 150 ms confirma). 507 testes passando.
- **Status:** implementado; teste real pendente · **Data:** 2026-11-10

## D040 — Caneta física (mouse sem fio) como entrada alternativa, convivendo com a mão (proposta)

- **Ideia do usuário (2026-11-10):** transformar um mouse sem fio numa caneta, com um leitor (acionado por um botão/microchave) na ponta, para escrever na lousa.
- **Problema que resolve:** o estudo do toque (D029) mostrou que a câmera do celular sozinha não distingue com segurança dedo encostado de dedo a ~2 cm. Um clique de mouse é um sinal elétrico sem ambiguidade — resolvido ou não resolvido, sem "quase".
- **Decisões do usuário, entre as alternativas apresentadas:**
  - **Posição:** pelo sensor óptico do próprio mouse arrastando na lousa (movimento relativo), não pela câmera enxergando a ponta.
  - **Caneta × mão:** convivem; o professor escolhe a cada momento qual usar, sem travar modo.
- **Como as duas entradas se encaixam:** a mão continua dando a posição absoluta (aponta, "teletransporta" o cursor para onde quiser, abre a sidebar). A caneta, com o mouse arrastando, só soma movimento relativo a partir de onde o cursor já está — o que funciona bem exatamente porque a mão resolve o "pular para um ponto novo" antes de a caneta assumir o traço fino.
- **Regra proposta para não ler ruído:** só aplicar o movimento do mouse ao cursor enquanto a chave da ponta estiver pressionada (tocando a lousa); solto, o sensor pode captar nada ou lixo e isso não deve mexer no cursor. Mantém o princípio de não tratar toda leitura como interação válida (§5.4 do CLAUDE.md).
- **Riscos a validar antes de montar a caneta:**
  1. Sensor óptico em lousa branca (superfície lisa/brilhante) pode não rastrear bem — mouses ópticos variam muito nisso; alguns a laser rastreiam pior em superfície muito lisa.
  2. Contagens do mouse (DPI) precisam de uma escala para que arrastar X cm reais na lousa mova o traço X cm na projeção — provavelmente um passo de calibração novo (arrastar de uma borda a outra uma vez).
  3. Construção física (microchave na ponta, ignorar o sensor de movimento quando não há contato) é trabalho de hardware do usuário; o lado de software (ler o mouse como uma entrada nova, paralela à câmera) fica para depois da validação.
- **Primeiro passo proposto (sem solda, 2 minutos):** antes de montar a caneta, testar o mouse sem fio comum arrastando a mão com ele encostado na lousa, vendo se o cursor acompanha de forma suave ou se trava/pula. Se não rastrear bem na lousa como está, vale testar com uma fita adesiva texturizada ou um pad fino colado na ponta.
- **Status:** proposta registrada; aguardando o teste da superfície antes de qualquer modificação física ou código novo · **Data:** 2026-11-10
