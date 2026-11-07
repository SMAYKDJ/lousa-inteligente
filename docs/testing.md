# Testes e resultados

Registro de testes executados (`CLAUDE.md` §9 e §18). Cada entrada traz data, ambiente e resultado. Resultados de simulação são marcados como tal e **não** validam funcionalidade com equipamento real (§9.4).

---

## Etapa 1.1 — Protocolo de mensagens (testes unitários)

Arquivo: `tests/test_message_protocol.py` · Módulo: `desktop/communication/message_protocol.py`

**Cobertura:** mensagens válidas dos 5 tipos (hello, hand_tracking, ping, pong, status); limites inclusivos de coordenadas; campos desconhecidos ignorados; JSON inválido; mensagem acima do tamanho máximo; tipo desconhecido; versão não suportada; os 10 campos obrigatórios de `hand_tracking` ausentes; valores fora de faixa; tipos errados (incluindo `true` usado como número); NaN/Infinity; `hello` e `status` inválidos; descarte de `seq` antigo ou repetido; mensagens enviadas pelo notebook.

| Data | Ambiente | Comando | Resultado |
|---|---|---|---|
| 2026-11-06 | Linux (ambiente de desenvolvimento do Claude), Python 3.13.18, pytest 9.2.0 | `python -m pytest` | **60 passed** |
| 2026-11-06 | macOS 26.5.2 (arm64), Python 3.11.18 (`.venv`), pytest 9.2.0 | `.venv/bin/python -m pytest` | **60 passed** (aviso de configuração do pytest-asyncio, sem relação com o protocolo; corrigido no `pytest.ini`) |
| — | Windows (notebook do professor) | — | pendente (etapa 1.7) |

---

## Etapa 1.2 — Servidor HTTPS + WebSocket

### Testes automatizados

Arquivos: `tests/test_server.py` (20 testes), `tests/test_tls.py` (8 testes).

**Cobertura do servidor:** token obrigatório na página e no `/ws` (403 sem token ou com token errado); arquivos estáticos públicos e sem escapar da pasta `mobile/`; `hello` → `welcome`; primeira mensagem diferente de `hello` é recusada; conexão sem `hello` é encerrada por tempo; `hand_tracking` repassado com descarte de `seq` antigo/repetido; mensagem inválida recebe `error` sem derrubar a conexão; excesso de mensagens inválidas encerra a conexão; mensagens binárias recusadas; ping ↔ pong nos dois sentidos com RTT medido; `status` repassado; conexão nova substitui a anterior; reconexão com `seq` recomeçando.

**Cobertura do TLS:** certificado com o IP no SAN; reaproveitamento para o mesmo IP; regeneração quando o IP muda, quando está perto de expirar ou quando o arquivo está corrompido; chave privada só com permissão do dono; contexto SSL com TLS ≥ 1.2; detecção de IP local.

| Data | Ambiente | Resultado |
|---|---|---|
| 2026-11-06 | Linux (ambiente do Claude), Python 3.13.18, aiohttp 3.14.5, cryptography 50.0.2 | **88 passed** (60 protocolo + 20 servidor + 8 TLS), 5 execuções seguidas sem falha |
| 2026-11-06 | macOS 26.5.2, Python 3.11.18 (`.venv`) | **88 passed** |
| 2026-11-06 | Linux (ambiente do Claude), após as correções acima | **91 passed** (+3: orientação `unknown`, código de fechamento 4000, troca sem "desconectado" falso) |
| 2026-11-06 13:52 | macOS 26.5.2, Python 3.11.18 (`.venv`), após as correções | **91 passed** em 0,73 s. Servidor reiniciado com o código novo; celular reconectado (sessão `bf397c07`) |

### Teste ponta a ponta com HTTPS real (simulado, sem celular)

`desktop.main` rodando com certificado real em `127.0.0.1:18443`, acessado por `curl` e por um cliente Python (aiohttp) — 2026-11-06, ambiente do Claude:

- Página sem token → **403**; com token → **200**.
- `vision_bundle.mjs` → 200, `text/javascript`; `vision_wasm_internal.wasm` → 200, `application/wasm`.
- WSS: `hello` → `welcome`; 39 mensagens `hand_tracking` a ~30/s → servidor registrou **28,9 msg/s**; RTT medido (≈1 ms, local).
- Desconexão registrada como `client_closed`.

> Simulação no mesmo computador: o RTT de ~1 ms **não** representa o Wi-Fi.

### Cliente do celular (`websocket_client.js`) executado no Node 22 contra o servidor real

- Conexão, `welcome`, `status` e RTT: funcionando.
- **Falha encontrada e corrigida:** quando a conexão falhava antes de abrir, o cliente parava de tentar. O Node dispara só `error` nesse caso, e o cliente esperava `close`. Agora cada tentativa termina uma única vez, seja por `error`, `close` ou tempo limite.
- Servidor derrubado e religado (mesmo token): o cliente tentou após 0,5 s → 1 s → 2 s → 5 s e **reconectou sozinho**.
- Servidor que aceita a conexão e não responde (simula rede que descarta pacotes): o cliente desistiu da tentativa após **5 s** e tentou de novo.

> O comportamento no Chrome do Android ainda precisa ser confirmado no teste real abaixo.

### Teste real com o Android

**Aparelho de referência (D008):** Motorola **moto g54 5G**, Android 15 (build V1TDS35H.83-20-5-8-2-1-3), **Chrome 156.0.8078.79**. Notebook: macOS 26.5.2, IP 192.168.1.74.

**Resultado (2026-11-06, 13:06–13:27).** Fontes: log do terminal do Mac e print da página no celular (sessão `f528b540`, mesma do log).

| Passo | Resultado |
|---|---|
| Servidor + URL no Chrome + aceitar certificado | ✅ |
| Contexto seguro | ✅ "Sim (HTTPS)" |
| Câmera traseira | ✅ **720×1280** — frame em **retrato** (celular na vertical) |
| Conexão | ✅ "Conectado"; o notebook registrou o celular como `192.168.1.68` |
| RTT pelo Wi-Fi (celular, 117 medições) | mín. **4,6 ms** · mediana **10,7 ms** · p90 **83,9 ms** · máx. **364,3 ms** |
| Reconexão automática | ✅ observada 3 vezes: o celular saiu da página ou ela ficou em segundo plano, e a conexão voltou sozinha (13:22:01→13:22:03, 13:25:26→13:26:03, 13:26:56→13:27:03) |
| Reconexão com o Wi-Fi do celular desligado e religado | não confirmada explicitamente; refazer na etapa 1.6 |

**Descobertas do log:**

1. **Entre 13:06 e 13:21 o cliente conectado era o próprio Mac, não o celular.** O endereço de origem era `192.168.1.74`, o mesmo do notebook, com câmera 1280×720 (webcam do Mac) e RTT de ~1,6 ms (máquina local). Uma aba no navegador do Mac estava com a página aberta. A página informava a webcam do Mac como "traseira" porque o código assumia "traseira" quando o navegador não informa a orientação. **Corrigido:** agora a página informa `unknown`, e o protocolo aceita esse valor.
2. **Bug: dois aparelhos se derrubando em ciclo.** Às 13:21:34 o celular conectou, e a aba do Mac continuava aberta. Pela política "conexão nova substitui a anterior", cada um derrubava o outro, e a reconexão automática fazia o derrubado voltar. Foram **22 trocas em 20 s**, até a aba do Mac ser fechada às 13:21:54. **Corrigido:**
   - o notebook fecha a conexão substituída com o código `4000` (`WS_CLOSE_REPLACED`);
   - a página que recebe esse código **não reconecta sozinha**. Ela avisa que outro aparelho assumiu e oferece o botão "Reconectar";
   - a nova conexão passa a ser a ativa antes de a antiga ser fechada. Assim o notebook não registra um "desconectado" falso durante a troca.

   Reproduzido em simulação com dois clientes reais (Node): **1 troca** em vez de um ciclo. Teste automatizado atualizado. **Confirmar no próximo teste real.**
3. **RTT pelo Wi-Fi varia muito** (mediana ~11 ms, mas 10% das medições acima de ~84 ms e pico de 364 ms). É compatível com a economia de energia do Wi-Fi do Android e com interferência. Na etapa 1.5 isso pode aparecer como travadas do cursor. Novo risco **R8** em `architecture.md`. A medição sob carga real (30 msg/s) fica para a 1.6.

Roteiro usado:

1. No Mac: `cd ~/Projetos/smartboard-classroom && .venv/bin/python -m desktop.main`
2. No Android, conectado ao **mesmo Wi-Fi**, abrir no Chrome a URL mostrada no terminal.
3. Aceitar o aviso de certificado (Avançado → continuar).
4. Conferir na página: **Contexto seguro = Sim (HTTPS)**.
5. Tocar em **Iniciar câmera e conectar** e permitir a câmera.
6. Conferir: câmera traseira com imagem e resolução; **Conexão = Conectado**; RTT atualizando a cada 2 s.
7. No terminal do Mac: `Conexão: connected`, a resolução da câmera e o RTT.
8. Reconexão: desligar o Wi-Fi do celular por ~10 s e religar. A página deve mostrar "Reconectando…" e voltar a "Conectado" sozinha.

Registrar: modelo do Android, versão do Chrome, resolução da câmera, faixa de RTT e se cada passo funcionou.

---

## Etapa 1.3 — Janela do cursor + celular simulado

> **Tudo nesta seção é simulação** (celular simulado `tools/fake_phone.py`). Valida o caminho dentro do notebook (rede → thread → Qt → cursor), **não** o rastreamento real (`CLAUDE.md` §9.4). O teste com a mão real é a etapa 1.5.

### Testes automatizados

| Arquivo | Testes | Cobre |
|---|---|---|
| `tests/test_coordinate_mapper.py` | 7 | cantos e centro do frame → janela; eixos sem inversão; limite nas bordas; acompanha o tamanho da janela |
| `tests/test_cursor_state.py` | 5 | cursor aparece/some com a mão; desconexão limpa cursor, FPS, RTT e câmera; msg/s só do último segundo |
| `tests/test_gui_integration.py` | 3 | servidor em thread com **TLS real** + ponte Qt + janela (Qt offscreen): WSS → cursor na posição esperada (0,75; 0,25) × 1000×500 = (750; 125); desconexão esconde o cursor; janela renderiza |

| Data | Ambiente | Resultado |
|---|---|---|
| 2026-11-06 | Linux (ambiente do Claude), Python 3.13.18, PySide6-Essentials 6.12.0, Qt offscreen | **106 passed**, 5 execuções seguidas sem falha |
| — | macOS, Python 3.11.18 (`.venv`) | **pendente** |

### Problemas encontrados e corrigidos durante a etapa

1. **Servidor "pronto" antes de abrir a porta.** O evento interno da `ServerThread` se chamava `_started`, mesmo nome de um atributo interno do `threading.Thread` do Python, que o sinaliza sozinho ao iniciar a thread. A janela poderia abrir antes de o servidor aceitar conexões. Renomeado para `_ready`, com comentário explicando.
2. **Crash (segmentation fault) do Qt entre testes.** Os slots eram closures, que criavam um ciclo de referências. O widget só era liberado pelo coletor de lixo do Python num momento imprevisível, dentro do processamento de eventos do Qt. Corrigido de duas formas: slots passaram a ser métodos (sem ciclo), e os testes destroem os objetos Qt de forma determinística.
3. **Cursor escondido pelo painel** no canto superior esquerdo. Agora o cursor é desenhado por último.
4. **Dados velhos na tela** depois da desconexão (RTT e câmera da sessão anterior). Agora são limpos.

### Execução da janela com o celular simulado (capturas da janela, Qt offscreen)

- 146 mensagens em 6 s a 30/s → janela mostrou **28–29 msg/s**, RTT ~1 ms (local), cursor percorrendo o círculo, "detectada"/"sem mão" alternando.
- Ao encerrar o simulador: "Aguardando celular · client_closed", sem cursor, 0 msg/s, RTT e câmera limpos.
- Modo `--headless` conferido com o mesmo simulador: 29 msg/s no terminal.

### Ajustes de uso após a primeira tentativa no Mac (2026-11-06)

- A primeira tentativa falhou por uso, não por defeito: o simulador recebeu o texto literal `"URL"`, depois um token de exemplo, e o servidor não estava rodando. O simulador mostrava só um traceback.
- **Melhorias:** (1) opção `desktop.main --simulate`, que conecta o celular simulado sem copiar token; (2) o simulador explica em português três casos: URL inválida, servidor desligado e token recusado (403). Conferidos aqui nos três casos, e o `--simulate` conectou.

### Janela não abria no Mac: diagnóstico e correção (2026-11-06)

- `desktop.main --simulate` encerrava ao iniciar o Qt: `Could not find the Qt platform plugin "cocoa"` (relatório de crash do macOS: `abort` dentro de `QGuiApplicationPrivate::createPlatformIntegration`).
- Com `QT_DEBUG_PLUGINS=1`, o Qt examinava a pasta de plugins e não via nenhum arquivo. O Python listava os três normalmente. Com o plugin copiado para `/tmp`, apareceu **"Qt OK fora da Mesa"**.
- **Causa:** o projeto estava em `~/Desktop`, uma pasta protegida do macOS. **Correção:** o projeto foi movido para `~/Projetos` e o `.venv` recriado (D011). Foram adicionadas proteções no `setup_mac.sh` e no `desktop.main`, com 8 testes novos em `tests/test_main.py`.
- **Também encontrado:** um envio de arquivos para o Mac relatou sucesso, mas deixou a versão antiga do `main.py`. Depois disso, todo envio passou a ser conferido no Mac por SHA-256.

| Data | Ambiente | Resultado |
|---|---|---|
| 2026-11-06 | Linux (ambiente do Claude), Qt offscreen | **114 passed**, 3 execuções seguidas |
| 2026-11-06 14:47 | macOS 26.5.2, Python 3.11.18, `~/Projetos/smartboard-classroom` | **114 passed** (inclui os 3 testes de janela Qt) |

**Execuções reais no Mac após a correção (2026-11-06):**
- `desktop.main --simulate` (14:47 e 14:52): a janela abriu sem erro, o celular simulado conectou (`fake-phone 0.1.0`), e o programa encerrou normalmente (`server_shutdown`) depois de 31 s e 9 s.
- `desktop.main --token sala1` (14:55): o Android real (`192.168.1.68`, `mobile-web 0.1.0`) conectou à janela às 14:56:23.
- Print do celular às 14:57 (token `sala1`): contexto seguro "Sim (HTTPS)", câmera **720×1280 (traseira)**, **Conectado** (sessão `2564800e`), RTT **6,5 ms**.
- **Janela do notebook com o Android real (print às 14:58):** "Conectado 192.168.1.68 (sessão 2564800e)", câmera **720×1280 (environment)**, rastreamento "inactive · sem mão", 0 msg/s (esperado: o celular ainda não envia a mão), RTT 97,8 ms naquele instante.
- **Confirmado pelo usuário (`--simulate`):** o cursor vermelho girou em círculo; as teclas **F**, **Esc** e **Q** funcionaram.
- **Etapa 1.3 concluída.**

### Teste no Mac (roteiro)

**Status: pendente.**

1. `.venv/bin/python -m desktop.main --simulate` → abre a janela do cursor já com o celular simulado conectado (sem copiar token).
2. (Alternativa com dois terminais: `desktop.main` num e `tools.fake_phone "URL-COMPLETA-COM-TOKEN"` no outro.)
3. Conferir na janela: "Conectado", cursor girando em círculo, sumindo por ~1 s a cada 6 s, ~29 msg/s.
4. Teclas: **F** (tela cheia e volta), **Esc**, **Q** (fecha). Conferir se o cursor acompanha o novo tamanho em tela cheia.
5. Sem `--simulate`, com o celular real aberto na URL nova: a janela mostra "Conectado", a câmera **720×1280 (environment)** e o RTT. O cursor ainda não aparece, porque o rastreamento da mão é a etapa 1.4.

---

## Etapa 1.4 — MediaPipe no celular

**Implementado:** `mobile/scripts/hand_tracking.js`, um `HandTracker` que:
- usa o MediaPipe 1.2.2 e o modelo locais (D006);
- tenta a GPU e, se falhar, a CPU;
- roda em modo VIDEO com `numHands: 1`;
- extrai o landmark 8 e limita x e y a [0, 1].

A página `app.js` desenha a mão sobre o vídeo, mostra FPS e tempo por quadro, pede a tela sempre ligada (Wake Lock, risco R6) e envia FPS e estado reais no `status`. A ponta do indicador **ainda não** é enviada ao notebook; isso é a etapa 1.5.

### Teste no Chrome sem tela, com câmera falsa (2026-11-06, ambiente do Claude) — simulação

Servidor real com HTTPS + Chrome 1xx headless (Playwright) + câmera falsa do Chrome (padrão de teste, **sem mão**):

| Item | Resultado |
|---|---|
| Requisições da página | **todas para o próprio notebook** (`127.0.0.1:18460`); nenhuma para CDN ou internet ✅ |
| MediaPipe | carregou com **delegate GPU** em **1,1 s** ✅ |
| Laço de rastreamento | 66+ quadros processados; estado `tracking_lost` (correto: não há mão na câmera falsa) ✅ |
| `status` no notebook | recebido a cada 1 s com FPS e estado reais ✅ |
| FPS / tempo por quadro | 1,8 FPS · 545 ms. **Não representa o celular:** aqui a "GPU" é emulada por software (sem placa de vídeo) |
| Wake Lock | `NotAllowedError`, esperado no Chrome sem tela. Testar no celular |
| Console | avisos internos do MediaPipe (WebGL `ReadPixels`, `NORM_RECT`), sem erro. Um 404 isolado (provável `favicon.ico`) não se repetiu; a página agora declara um ícone vazio |

### Teste real no Android — 2026-11-06 15:07 (print do usuário)

moto g54 5G · Chrome 156 · câmera traseira 720×1280 · padrão (GPU, 720p):

| Item | Resultado |
|---|---|
| MediaPipe carregado | ✅ **GPU**, em **14,8 s** (primeira carga: download de ~8 MB do modelo + WASM pelo Wi-Fi + preparo da GPU) |
| Detecção da mão | ✅ esqueleto sobre a mão; **ponto na ponta do indicador** (x=0,35 y=0,50, confiança 99%) |
| Desempenho | **8,5 FPS · 98 ms/quadro**. Baixo para um cursor fluido (risco **R2** confirmado) |
| Tela ativa (Wake Lock) | ✅ "ativa" (R6) |
| RTT no momento | 102 ms |

**Log de sessão (a pedido do usuário: medir por log, não por anotação).** O notebook grava cada sessão em `logs/session-AAAAMMDD-HHMMSS.jsonl`: conexões, câmera, e a cada segundo FPS, ms/quadro (média), delegate, tempo de carga, estado do rastreamento, além de RTT e mensagens recusadas. `tools/log_summary.py` gera a tabela por conexão. Conferido ponta a ponta no Chrome sem tela, com as 4 variantes seguidas: 4 linhas na tabela com câmera, delegate, carga, FPS, ms/quadro e RTT corretos. Testes: `tests/test_session_log.py` (4) e 3 novos no protocolo → **123 passed**.

**Achado do log (risco R10):** o RTT sobe quando o MediaPipe está pesado, porque ele bloqueia a página. No celular: 6,5 ms (etapa 1.2) → 102 ms com o rastreamento. No Chrome sem tela: 11 ms (CPU, 46 ms/quadro) contra 257 ms (GPU emulada, 580 ms/quadro).

**Medição de alternativas (R2), sem otimizar às cegas (`CLAUDE.md` §10).** A página aceita parâmetros na URL: `&res=480|720|1080` (resolução pedida à câmera) e `&delegate=GPU|CPU`. Conferidos no Chrome sem tela (no ambiente do Claude, a CPU rendeu 20,8 FPS contra 1,9 da GPU emulada, **o que não prevê o celular**). Combinações a medir no Android:

**Resultado (2026-11-06 15:38–15:46, log `logs/session-20261106-153753.jsonl`, 580 linhas, resumido por `tools/log_summary.py`).** moto g54 5G, Chrome 156, mão diante da câmera traseira. FPS e ms/quadro = medianas dos segundos **com mão**:

| Variante | Câmera | Delegate | Carga | FPS c/ mão | ms/quadro c/ mão | RTT mediana / p90 |
|---|---|---|---|---|---|---|
| padrão | 720×1280 | GPU | 15,0 s | **11,2** | **79** | 74 / 189 ms |
| `&res=480` | 480×640 | GPU | 13,4 s | 10,9 | 80 | 72 / 171 ms |
| `&delegate=CPU` | 720×1280 | CPU | 12,9 s | 8,2 | 118 | 100 / 218 ms |
| `&res=480&delegate=CPU` | 480×640 | CPU | 8,5 s | 9,2 | 106 | 44 / 157 ms |

**Conclusões (D012):**
1. **GPU é melhor** que CPU neste aparelho: ~79 ms contra ~110 ms por quadro.
2. **A resolução da câmera não muda o desempenho** (79 contra 80 ms). O MediaPipe reduz a imagem internamente antes de processar. Mantém-se 720p, que dá mais precisão de posição para a calibração (Fase 2) sem custo medido.
3. **Teto atual: ~11 FPS no celular.** O gargalo é o tempo do próprio MediaPipe (~80 ms por quadro na GPU do moto g54), não a câmera nem a rede.
4. **R10 confirmado:** com o rastreamento ligado, o RTT mediano fica em 44–100 ms (contra 6,5 ms sem rastreamento, na etapa 1.2), porque o MediaPipe bloqueia a página.
5. O tempo de carga (8,5–15 s) caiu ao longo das recargas, um efeito provável do cache do navegador. A primeira abertura em sala deve ficar perto de 15 s.

### Roteiro do teste no Android

1. Mac: `.venv/bin/python -m desktop.main --token sala1`
2. Android: abrir `https://192.168.1.74:8443/?token=sala1` → **Iniciar câmera e conectar**.
3. Esperar "MediaPipe: pronto (GPU…)" e anotar o tempo de carga.
4. Colocar a mão na frente da câmera traseira: esqueleto verde sobre a mão e **ponto vermelho na ponta do indicador**, acompanhando o dedo.
5. Anotar **FPS e ms/quadro** com a mão parada e em movimento.
6. Conferir "Tela ativa: ativa" e se a tela não apaga em ~2 min parado.
7. Na janela do notebook: "FPS do celular" igual ao do celular e "Rastreamento: tracking_active" com a mão.


## Etapa 1.5 — Quadros do celular processados no notebook (D013)

### Testes automatizados (2026-11-06, ambiente do Claude, Linux, Python 3.13): **162 passando**

| Arquivo | O que cobre |
|---|---|
| `test_frame_protocol.py` | Envelope `SBF1`: ida e volta, cabeçalho little-endian de 16 bytes, magic errado, curto, não-JPEG, `t_client_ms` negativo/NaN/∞, limite de tamanho |
| `test_server.py` | Quadro válido entregue; inválido → `error` sem entregar; `seq` antigo descartado (5, 3, 6 → 5, 6); quadro grande → `message_too_large` sem derrubar a conexão |
| `test_frame_processor.py` | Com detector falso: quadro → `hand_tracking`; **vaga única** (1 em processamento, 2/3/4 chegando → processa 1 e 4, conta 2 descartados); erro de JPEG contado sem parar; carimbos estritamente crescentes com relógio parado; desconexão descarta o quadro pendente; falha ao carregar → estado `error` |
| `test_hand_tracker.py` | Conversão do resultado do MediaPipe (clamp, lateralidade). Com o **MediaPipe real** e `tests/fixtures/hand_thumbs_up.jpg`: mão encontrada, ponta do indicador na região esperada; imagem cinza → sem mão |
| `test_frame_pipeline.py` | Integração: 20 quadros JPEG reais pelo WebSocket → servidor → MediaPipe → 100% com mão; log com `vision_state`, `vision`, `tracking_rate` e **nenhuma imagem** |
| `test_cursor_state.py`, `test_session_log.py`, `test_message_protocol.py` | Painel "Visão (notebook)", limpeza ao desconectar, tabela do modo stream no `log_summary`, campos novos do `status` |

Dependências verificadas: `mediapipe==1.2.2` tem rodas para Python 3.11 em **macOS arm64** (39,6 MB) e **Windows x64** (25,3 MB). Com as dependências, o total é ≈ 110 MB (numpy 2.4.6, opencv-contrib-python 5.0.0.93, matplotlib). O numpy 2.5 não suporta Python 3.11.

MediaPipe Python nesta máquina (2 núcleos, CPU, sem GPU), imagem 640×427: carga em ~2 s; JPEG→RGB 1,6 ms; inferência ~12 ms (mediana de 30 quadros). **Esses números não valem para o Mac nem para o Windows**: precisam ser medidos lá (log `vision`).

### Ensaio ponta a ponta com Chrome sem tela e câmera falsa — simulação (2026-11-06)

Montagem:
- **Câmera:** `--use-file-for-fake-video-capture` com um vídeo MJPEG de 90 quadros, a mão de `hand_thumbs_up.jpg` subindo e descendo.
- **Notebook:** servidor real (`desktop.main --headless`), MediaPipe real, HTTPS e WSS.
- **Página:** a página real do celular.

O Chrome entregou 720×720, e não 720×1280.

**Modo stream** (padrão):

| Início | Câmera | Quadro | Enviados q/s | KB/quadro | JPEG ms | Pulados (celular) | Processados q/s | MediaPipe ms | Espera ms | Descartados (notebook) | Com mão | RTT mediana / p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16:09:22 | 720×720 | 640×640 | 19,5 | 17 | 7 | 0 | 19,7 | 13 | 0,2 | 0/288 | 100% | 1,5 / 4,9 ms |

- Coordenadas acompanharam o movimento (y de 0,16 a 0,82 no terminal).
- O celular só baixou `app.js`, `camera.js`, `frame_sender.js`, `websocket_client.js` e o CSS. **O MediaPipe (~10 MB) não é mais baixado no modo stream.**

**Modo local** (`&mode=local&delegate=CPU`), que agora também envia `hand_tracking`:
- 18,9 FPS a 49 ms/quadro, 18–20 msg/s no notebook;
- RTT 38 / 51 ms, contra 1,5 ms no modo stream. Isso **reproduz o R10**: o MediaPipe na página atrasa a resposta.

**Limites deste ensaio:** é localhost, sem Wi-Fi; o vídeo é falso e a CPU é a do servidor de testes. O ensaio prova que a cadeia funciona. **Não** mede o desempenho real, que fica para o moto g54 + Mac (abaixo).

### Roteiro do teste real (moto g54 + Mac + Smart TV)

1. Mac: `bash scripts/setup_mac.sh` (instala MediaPipe/OpenCV, ~110 MB).
2. Smart TV como **segunda tela** do Mac (HDMI de preferência; AirPlay acrescenta atraso de imagem, R12). Em Ajustes > Telas, usar "Estender", não "Espelhar".
3. `.venv/bin/python -m desktop.main --token sala1 --screen 1`. O terminal lista as telas; se a TV não for a 1, trocar o número.
4. Android: `https://<ip>:8443/?token=sala1`, depois **Iniciar câmera e conectar**. O celular deve mostrar "MediaPipe: no notebook" e "Quadros: enviando … q/s".
5. Na TV: o painel mostra "Visão (notebook): pronto"; com a mão diante da câmera, o **cursor vermelho segue a ponta do indicador**. P esconde o painel.
6. Variações, ~20 s cada:
   - o padrão;
   - `&side=480&q=0.6`;
   - `&mode=local`, para comparação.
7. Ctrl+C e `.venv/bin/python -m tools.log_summary`.

### Primeiro teste real — moto g54 + MacBook Air + TV Toshiba (2026-11-06 16:33, log `session-20261106-163255.jsonl`)

Mac:
- **162 testes passando**;
- MediaPipe Python carregado em **1,5 s**;
- telas detectadas: `Tela 0: Built-in Retina Display 1470×956` e `Tela 1: TOSHIBA-TV 1920×1080`, com a janela aberta com `--screen 1`.

A URL ainda tinha `&res=480&delegate=CPU` do teste anterior, por isso a câmera ficou em 480×640. Primeiro conectou por 3 s a página antiga em cache (0.2.0, modo local), depois a 0.3.0.

| Enviados q/s | KB/quadro | JPEG ms (celular) | Pulados (celular) | Processados q/s | MediaPipe ms (Mac) | Espera ms | Descartados (Mac) | Com mão | RTT mediana / p90 |
|---|---|---|---|---|---|---|---|---|---|
| 17,8 | 13 | 25 | 73 em ~207 s | 17,9 | **18** | 0,3 | 23/3697 (0,6%) | 36% | 10,0 / 56,7 ms |

**Leitura:**
- **Mac com folga:** 18 ms por quadro comporta ~50 q/s. Quase nenhum quadro foi descartado.
- **Gargalo no envio do celular:** ~18 q/s. A hipótese é que o limitador de taxa pulava, sem contar, os quadros que chegavam poucos ms antes de 33,3 ms. Com a câmera a 30 q/s, isso derruba a taxa para perto da metade.
  - Corrigido no cliente 0.3.1 com folga de 25% no intervalo.
  - Na simulação, o envio foi de **19,5 → 29,8 q/s**, com 29,2 processados.
  - **Falta confirmar no moto g54.**
- **"Com mão" de 36%:** é a fração de quadros com mão durante toda a sessão, inclusive quando não havia mão diante da câmera. Não é taxa de acerto.
- **RTT:** mediana de 10 ms, contra 44–100 ms com o MediaPipe no celular (R10). Isso confirma o ganho da D013.
- **Aviso do MediaPipe** "Using NORM_RECT without IMAGE_DIMENSIONS…": apareceu uma vez, no primeiro quadro. Também aparece no ambiente de testes, onde a detecção foi correta. A posição do dedo na imagem retangular ainda vai ser conferida na calibração (Fase 2).
- **Ainda não registrado:** a impressão visual do cursor na TV (se acompanha, atraso percebido, tremor). O log não mede isso.

### Segundo teste real — cliente 0.3.1, URL limpa (2026-11-06 16:50, log `session-20261106-165042.jsonl`)

| Câmera | Quadro | Enviados q/s | KB/quadro | JPEG ms (celular) | Pulados (celular) | Processados q/s | MediaPipe ms (Mac) | Espera ms | Descartados (Mac) | Com mão | RTT mediana / p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 720×1280 | 360×640 | **25,0** | 15 | 27 | 218 em ~97 s | **24,1** | **14** | 1,6 | 101/2386 (4%) | 53% | 27,4 / 70,4 ms |

**Leitura:**
- **Correção da folga confirmada:** envio de 17,8 → 25,0 q/s (mediana), com segundos chegando a 29–30 q/s.
- **Mão contínua:** com a mão diante da câmera (≈ s 26–79), o MediaPipe encontrou a mão em praticamente todos os quadros, 16–31 por segundo. Os zeros antes e depois são do tempo sem mão.
- **Gargalo atual no celular:** o JPEG leva 27 ms, perto dos 33 ms de um quadro a 30 q/s. Os pulos se concentram no início e no fim (10–15/s), provavelmente com a página em segundo plano ou a câmera ajustando exposição. Hipótese ainda não verificada.
- **RTT mais alto que no 1º teste** (27 contra 10 ms): mais tráfego no Wi-Fi, 25 q/s × 15 KB ≈ 0,4 MB/s. Continua abaixo do modo local (44–100 ms).
- **Mac:** 14 ms por quadro, com folga. Os descartados (4%) são quadros que chegaram juntos depois de oscilações do Wi-Fi.

### Avaliação visual do 2º teste (relato do usuário, 2026-11-06 16:56) e medição de latência

Relato do usuário, com TV por **HDMI**:
- **Precisão:** o cursor ficou "próximo" da ponta do dedo, mas não exato. As ferramentas flutuantes vão exigir exatidão.
- **Atraso:** **incomodou**.
- **Tremor:** o cursor **não** tremeu com a mão parada.

**Precisão — causa conhecida:** não há calibração na Fase 1. O `StretchMapper` estica a imagem da câmera (retrato, 360×640) sobre a TV (paisagem, 1920×1080). O cursor representa a posição na imagem da câmera, não a posição na superfície. A exatidão é o objetivo da Fase 2 (homografia, `calibration.md`).

**Atraso — medição acrescentada** (cliente 0.3.2, 171 testes):
- os relógios do celular e do notebook passam a ser sincronizados pelo ping (`clock_sync.py`);
- o log `vision` ganhou `to_arrival_ms` (captura → chegada ao notebook, incluindo o JPEG) e `to_result_ms` (captura → resultado do MediaPipe);
- o `log_summary` mostra as duas colunas, com o erro da estimativa;
- simulação local: 12 ms até a chegada e 25 ms até o resultado.

Ficam **fora** dessa medição o desenho na janela (≤ 1 quadro de tela, ~16 ms) e o **atraso de entrada da TV**, que pode passar de 50 ms fora do "modo jogo".

### Terceiro teste real — latência ponta a ponta (cliente 0.3.2, 2026-11-06 17:05, log `session-20261106-170106.jsonl`)

TV por HDMI. O Modo Jogo ficou ligado em parte do teste e desligado em outra; o atraso da TV não aparece no log.
- **Taxas:** 23,7 q/s enviados, 22,7 q/s processados.
- **Mac:** MediaPipe a 15 ms por quadro; 4% dos quadros descartados.
- **Sincronia de relógios:** erro de ±2–3 ms, que é desprezível.

**Onde está o atraso (medianas):**

| Trecho | ms | Fonte |
|---|---|---|
| Câmera → início do JPEG (captura, entrega do quadro à página) | ~25 | por diferença: 60 − 27 − 8 |
| JPEG no celular | ~27 | `encode_ms` do `status` |
| Wi-Fi, ida | ~8 | RTT/2 (RTT mediano 16,6 ms) |
| **Captura → chegada ao Mac** | **60** | `to_arrival_ms` |
| Mac: espera + JPEG→RGB + MediaPipe | ~17 | `to_result_ms − to_arrival_ms` |
| **Captura → resultado no Mac** | **77 (±3)** | `to_result_ms` |
| Desenho na janela + atraso de entrada da TV | não medido | — |

- **Picos:** segundos isolados de 150–178 ms, coincidindo com oscilações do Wi-Fi e queda na taxa de envio. Por exemplo, às 17:06:52 a taxa caiu para 10 q/s e o JPEG chegou a 55 ms.
- **Maior parcela controlável:** o JPEG no celular, 27 ms. A segunda é a captura da câmera (~25 ms), que depende do aparelho e não é controlável pela página.
- O Mac responde por só ~17 ms do total.

**Modo Jogo da TV (relato do usuário, 17:35):** com o Modo Jogo ligado, o atraso diminuiu de forma perceptível em relação a desligado. Parte do atraso sentido no 2º teste vinha da TV. Para os próximos testes, a regra é **Modo Jogo sempre ligado**. No projetor da sala de aula, verificar se existe um modo equivalente (baixa latência).

## Fase 2 — etapas 2.0 a 2.3 (2026-11-06, ambiente do Claude) — simulação

**Automatizados: 196 testes passando.** Novos:
- `test_calibration.py` (19):
  - homografia de ida e volta com uma "câmera" inclinada;
  - pontos fora da área;
  - quadriláteros inválidos (pontos repetidos, cruzados, juntos);
  - coleta pela mediana, que ignora um quadro errado;
  - rejeição sem mão e com o dedo em movimento;
  - máquina de estados: ordem SE → IE → ID → SD, 7 s, repetição do mesmo canto, recomeço quando os cantos não formam um quadrilátero, cancelamento, erro de verificação.
- `test_calibration_gui.py` (5), em Qt offscreen com relógio falso:
  - calibração completa;
  - cursor no ponto certo (erro < 1 px) e oculto fora da área;
  - Esc cancela e C recomeça;
  - mensagem de rejeição;
  - mapeamento da Fase 1 enquanto não há calibração.

**Capturas da tela de calibração** conferidas visualmente. Problemas corrigidos:
- texto cortado nas laterais;
- anel do alvo passando da borda da tela;
- alvo central coberto pelo texto e pelo rodapé.

**JPEG em worker (2.0), Chrome sem tela:**
- worker: 10 ms por JPEG, 30 q/s, captura → resultado em 30 ms;
- página: 7 ms, 24 q/s, 31 ms.

Nesta CPU de servidor o worker não ficou mais rápido por quadro. **A decisão depende da medição no moto g54.**

### Primeiro teste real da calibração (2026-11-06 18:07, log `session-20261106-180721.jsonl`) — **falhou, diagnosticado em parte**

**Fluxo:**
- A calibração começou ao abrir o programa.
- Antes de o celular conectar: 4 rejeições "nenhuma imagem", como previsto.
- Cliente 0.4.0, com o JPEG no worker.

**Resultado:**
- Duração: 141 s, com **12 rejeições**: 8 por "dedo não visto" e 1 por "dedo se moveu".
- 1ª tentativa: o sistema detectou cantos cruzados e recomeçou.
- 2ª tentativa: os cantos passaram na validação geométrica, mas o **erro no centro foi de 1028 px (54% da largura)**. Sem um limite de verificação, a calibração foi aceita como "calibrada".

**Cantos capturados** (camera_norm, ordem SE, IE, ID, SD):
- (0,87, 0,69), (0,15, 0,45), (0,16, 0,69), (0,28, 0,71);
- o "superior esquerdo" saiu na direita da imagem, e os quatro ficaram numa faixa estreita da imagem.

Hipóteses, a confirmar com a janela de diagnóstico:
1. A câmera não enxerga a TV inteira, ou a mão encobre o indicador perto das bordas.
2. O MediaPipe pega a outra mão ou o dedo errado.
3. A ponta do dedo não estava no alvo no último meio segundo.

**Também medido** (worker, 0.4.0):
- 28,2 q/s enviados, com o JPEG em 24 ms;
- **captura → resultado em 66 ms** (era 77 ms no cliente 0.3.2, com o JPEG na página).

**Correções** (202 testes):
- a calibração recomeça se o erro no alvo central passar de 5% (`CALIBRATION_MAX_VERIFY_ERROR`), em vez de ser aceita; há teste reproduzindo este caso real;
- cantos em ordem espelhada são rejeitados (fisicamente impossível com uma câmera real);
- **janela de diagnóstico** (`camera_preview.py`), aberta por padrão na tela do notebook, com:
  - a imagem da câmera ao vivo;
  - a ponta detectada (vermelho);
  - os cantos capturados (verde);
  - o contorno calibrado (amarelo).

  A imagem fica só na tela e não é gravada. Para não abrir: `--no-preview`.

### Segundo teste real da calibração (2026-11-06 19:02, log `session-20261106-190234.jsonl`) — **funcionou**

- **Duração:** 42 s, com uma única repetição (dedo se moveu no 4º canto).
- **Cantos** (camera_norm, ordem SE, IE, ID, SD): (0,135, 0,252), (0,125, 0,482), (0,786, 0,489), (0,828, 0,286). Formam o trapézio esperado: a TV vista pela câmera, que a enxerga um pouco de baixo.
- **Erro no alvo de verificação (centro): 4,6 px, 0,24% da largura** (meta provisória: ≤ 1%).
- **Fluxo de quadros:** 27,7 q/s enviados, 28 q/s processados; captura → resultado em **66 ms**; RTT de 8,8 ms.

**Ressalvas:**
- O erro foi medido **só no centro** e com o mesmo gesto da calibração. A precisão na superfície inteira exige a grade de 9 pontos (etapa 2.4, tecla **G**, implementada a seguir).
- **Resolução:** a TV ocupa ~250 × 150 px da imagem de 360 × 640 (câmera em retrato). Cada pixel da câmera vale ~7–8 px da TV, o que limita a precisão nas bordas.

### Etapa 2.4 — teste de precisão com grade de 9 pontos (implementado; 206 testes)

- Com a tela calibrada, a **tecla G** inicia o teste.
- 9 alvos (3 × 3, a 15% / 50% / 85%), com a mesma contagem de 7 s e a mesma regra de aceite.
- **No log:**
  - `accuracy_point`, com o erro (dx, dy) de cada alvo;
  - `accuracy_result`, com o erro de cada alvo em px, a mediana e o máximo, em px e em % da largura.
- **Na tela:** a faixa "Precisão: …" e a linha "Precisão (G)" do painel.
- Capturas conferidas: o título fica entre as fileiras de alvos.

### Marcadores ArUco (D015) — simulação (2026-11-06): 218 testes passando

- **Viabilidade (cena sintética):** 4 marcadores de 140 px numa tela de 1920×1080, vistos por uma câmera de 360×640 em perspectiva, foram detectados com **15–20 px** de lado na imagem; na horizontal (640×360), com ~30 px. Detecção em 1,5–12 ms.
- **`test_markers.py` (8):**
  - layout dentro da tela;
  - detecção dos 4;
  - homografia pelos marcadores com erro < 1%;
  - **câmera movida → o ponto volta ao lugar** (erro < 1%; sem correção, > 5%);
  - correção mantida com 2 marcadores cobertos;
  - com 1 marcador visível, mantém a correção anterior;
  - câmera parada → identidade.
- **`test_calibration_gui.py`** (marcadores):
  - a imagem **desenhada pelo próprio Qt** passa pela câmera sintética e é detectada;
  - a referência é tomada após a calibração;
  - com a câmera "movida" 8,4%, o cursor fica a menos de 1,5% do ponto certo;
  - aviso quando os marcadores não são vistos;
  - `--no-markers`.
- **Ensaio com Chrome sem tela:** a cadeia completa roda com a detecção ativa; MediaPipe a 14 ms, sem mudança. O vídeo falso não tem marcadores, por isso 0% de detecção.

**A medir no teste real:**
- taxa de detecção por marcador e tamanho deles na câmera (o `log_summary` mostra), com o celular em pé e na horizontal;
- se o cursor volta ao lugar quando o celular é movido de leve.

### Primeiro teste real dos marcadores (2026-11-06 19:24, log `session-20261106-192436.jsonl`)

**Calibração:** erro de **2,6 px (0,13%)** no centro, 105 s, 10 repetições.

**Marcadores:**
- **Lado:** ~19 px na câmera (mediana), com o tamanho padrão de 12%.
- **Detecção por id:** 0 em 43%, 1 em 65%, 2 em 24%, 3 em 59% das verificações.
- **Referência:** tomada com só **2 marcadores (1 e 3)**.
- **Celular girado para a horizontal** durante a sessão: o quadro passou a 640×360.
- **Impressão do usuário:** "ficou bom".

**Problema achado no log:**
- 521 registros de "câmera movida". A maioria era **vaivém**: a correção alternava entre ~31% e ~35% conforme o par de marcadores visível.
- Com 2 marcadores **do mesmo lado** (0 e 1, por exemplo), a perspectiva fica mal definida.
- O teste G não foi feito.

**Correções** (221 testes, com casos que reproduzem o problema):
- referência só com **≥ 3 marcadores**;
- com 2 marcadores, só se estiverem em **cantos opostos**;
- **saltos** só são aceitos após 3 leituras seguidas concordantes; ajustes finos (< 2%) entram direto;
- refinamento subpixel dos cantos dos marcadores;
- `camera_moved` no máximo 1 vez por segundo.

**Pendente** (pedido do usuário, para depois): marcadores mais discretos. A detecção já está no limite (~19 px na câmera). Para reduzir o tamanho sem perder leitura, será preciso aumentar a resolução do quadro (`&side=960`, medindo o custo na latência) ou aproximar a câmera.

### Duas mãos (D016) — simulação (2026-11-06): 231 testes passando

- **`test_hand_selection.py` (7):**
  - mão única;
  - sem calibração, a menor vence;
  - com calibração, a mão sobre a lousa vence a de fora, mesmo sendo maior;
  - as duas sobre a lousa, a menor vence;
  - estabilidade: só troca com margem;
  - mão anterior perdida.
- **`test_hand_tracker.py`:** MediaPipe real numa cena com a mesma mão em dois tamanhos (960×540). As 2 mãos foram detectadas, com palmas de ~160 px e ~97 px.
- **`test_calibration_gui.py`:** com duas mãos na mensagem, o cursor segue a mão sobre a lousa; captura da janela de diagnóstico com a mão usada em vermelho.
- **Custo medido nesta máquina** (2 núcleos, sem GPU), com a mesma cena:

  | Ajuste | 1 mão na cena | 2 mãos na cena |
  |---|---|---|
  | `MAX_HANDS = 1` | 15 ms | 11 ms |
  | `MAX_HANDS = 2` | 29 ms | 43 ms |

  No ensaio com o Chrome sem tela, o MediaPipe passou de 14 para **27 ms** por quadro, com 21 q/s processados. **Medir no Mac** (coluna "MediaPipe ms" do `log_summary`).

### Testes reais de 19:38 e 20:01 (2026-11-06): estabilização dos marcadores e duas mãos

| | 19:24 (antes) | 19:38 (estabilizado) | 20:01 (+ 2 mãos) |
|---|---|---|---|
| `camera_moved` | 524 (vaivém) | 14 | **20** |
| Referência | 2 marcadores | 3 | **4/4** |
| Detecção por marcador | 24–65% | 53–74% | 18–47% |
| Lado do marcador na câmera | 19 px | 19 px | 18 px |
| Quadros com 2 mãos | — | 0% | **32%** |
| MediaPipe (Mac) | 14 ms | 13 ms | **23 ms** (`MAX_HANDS = 2`) |
| Captura → resultado | 66 ms | 67 ms | 76 ms |
| Erro na verificação (centro) | 2,6 px (0,13%) | 10,9 px (0,57%) | **57,8 px (3,0%)** |

- **Impressão do usuário:** "ficou bom", com a escolha da mão junto à lousa funcionando.
- **Estabilização:** o vaivém de "câmera movida" desapareceu, com deslocamento máximo de 2,4% numa sessão sem mexer o celular.
- **Duas mãos:** +9 ms no MediaPipe do Mac, aceitável (26,7 q/s processados).
- **Erro de 3% na última calibração** (abaixo do limite de 5%, por isso aceita). Pode ter sido o dedo no alvo central ou a mão escolhida durante a calibração. **O teste G (grade de 9 pontos) ainda não foi feito.** Sem ele, a precisão na superfície inteira não está medida e a Fase 2 não está validada (CLAUDE.md §4.1).

## Fase 3 — etapa 3.0: viabilidade do overlay (2026-11-06) — simulação

**Implementado (`--overlay`):**
- a janela da lousa fica sem moldura, com fundo transparente, sempre por cima e **transparente para o mouse**. O mouse do notebook continua controlando a apresentação;
- não usa `showFullScreen`, que no macOS cria um Space próprio. Ocupa a tela da projeção como janela comum;
- **macOS:** `overlay_platform.py` marca a janela para aparecer em todos os Spaces, inclusive os de apresentação em tela cheia, com nível 1000 (acima da barra de menus). Usa o runtime Objective-C via `ctypes`, sem dependência nova;
- as teclas (C, G, P, Esc, Q) passam a ser digitadas na **janela de diagnóstico**, porque a lousa ignora teclado e mouse;
- a calibração continua opaca: cobre o slide enquanto dura.

**Testes (`test_overlay.py`, 7; total 238):**
- pixel vazio transparente (alfa 0), marcadores e cursor opacos;
- sinalizadores da janela;
- teclas repassadas pela janela de diagnóstico;
- tela de calibração opaca;
- ajuste do macOS não aplicado em outros sistemas.

Uma composição sobre um slide fictício foi conferida visualmente: só os marcadores e o cursor aparecem.

**Não verificável aqui:** se a lousa fica de fato por cima do PowerPoint ou do navegador em **tela cheia** no macOS, e se o ajuste via `ctypes` funciona no Mac. Teste real a seguir.

### Teste real do overlay e 1º teste G (2026-11-06 20:18, log `session-20261106-201802.jsonl`)

**Overlay (`--overlay`):**
- Sobre a área de trabalho comum funcionou: calibração e teste G foram feitos com a lousa transparente, e os marcadores foram vistos (referência com 0, 2 e 3).
- **Com o navegador em tela cheia na TV, a lousa não apareceu por cima** (relato do usuário).
- **Causa provável:**
  - janela `Qt.Tool` (NSPanel) se esconde quando outro aplicativo fica ativo;
  - um aplicativo comum não entra no Space de tela cheia de outro.
- **Correção** (`overlay_platform.py`), a confirmar no Mac:
  - `setHidesOnDeactivate: NO`;
  - painel não ativador;
  - app como "acessório" (sem ícone no Dock);
  - `orderFrontRegardless` reafirmado a cada 2 s.
- O terminal mostra "Ajuste de tela cheia do sistema: aplicado".

**Calibração:** 5,3 px (0,28%) no centro.

**Teste G** (grade de 9 pontos, celular parado):

| Ponto (x, y) | 0,15/0,15 | 0,5/0,15 | 0,85/0,15 | 0,15/0,5 | 0,5/0,5 | 0,85/0,5 | 0,15/0,85 | 0,5/0,85 | 0,85/0,85 |
|---|---|---|---|---|---|---|---|---|---|
| Erro (px) | 99,8 | 18,9 | 17,6 | 13,6 | 10,2 | **193,3** | 29,0 | 17,8 | 9,8 |

- **Mediana: 17,8 px (0,93%)**, dentro da meta de 1%.
- **Máximo: 193 px (10%)**, fora da meta de 2%.
- **7 de 9 pontos** ficaram entre 0,5% e 1,5%.
- **Os dois pontos ruins** (0,15/0,15 e 0,85/0,5) tiveram a ponta registrada bem à esquerda do alvo. Na câmera, o ponto 0,85/0,5 saiu em x = 0,567, contra 0,604–0,609 dos vizinhos na mesma coluna. Hipóteses:
  - dedo fora do alvo no fim da contagem;
  - a outra mão escolhida (2 mãos em 12% dos quadros da sessão).

  Repetir a grade para separar acaso de erro sistemático.
- **A TV ocupa ~38% × 40% da imagem da câmera.** Aproximar a câmera aumentaria a resolução útil.

### Overlay em tela cheia e 2º teste G (2026-11-06 21:05, log `session-20261106-205919.jsonl`) — **validados**

- **Overlay sobre o navegador em tela cheia na TV: funcionou** (relato do usuário) após os ajustes do macOS.
- **Calibração:** 6,8 px (0,35%).
- **Teste G:** erros de 8,0 / 1,0 / 26,2 / 7,5 / 15,7 / 20,7 / 7,2 / 25,7 / 4,6 px. **Mediana de 8 px (0,42%) e máximo de 26 px (1,37%).** Cumpre o critério provisório (≤ 1% e ≤ 2%). Os dois pontos ruins do 1º teste G não se repetiram.
- **Consequência para a Fase 3:** botão com diâmetro de 3 × 26 ≈ **80 px** (~7,4% da altura de 1080 px).
- **Pendente na Fase 2:** etapa 2.5, com ângulos de ~30°/45° e paralaxe do dedo afastado da superfície. Fica para quando a montagem for alterada; não bloqueia a interface.

## Fase 3 — etapas 3.2 a 3.4: permanência e sidebar (2026-11-06) — simulação

**Implementado:**
- `desktop/interaction/dwell.py`: permanência de 0,8 s, tolerância de 1,5% da largura, aciona uma vez por entrada, registra desistências com ≥ 25% de progresso.
- `desktop/interface/sidebar_model.py` (sem Qt):
  - estados Recolhida, Abrindo, Expandida, Recolhendo e Arrastando;
  - botão circular **na borda esquerda, no meio**, ~75% visível;
  - painel em grade de **2 colunas** (vertical) ou **2 linhas** (horizontal), com botões de **80 px** (regra 3 × erro máximo do teste G);
  - animação de 0,2 s;
  - painel sempre dentro da tela e **fora dos marcadores ArUco**;
  - arrastar pela alça "Mover": o painel segue o dedo e é solto quando o dedo **para por 0,8 s** (ou some por 1,5 s). Ao soltar, encaixa na **borda mais próxima**.
- `tool_icons.py`: ícones desenhados em código.
- `sidebar_view.py`: painel semitransparente, ferramenta atual em verde, anel amarelo de progresso.
- **Ferramentas:** Ponteiro, Selecionar, Pincel, Borracha, Círculo, Retângulo. **Ações:** Voltar, Avançar, Limpar, Slide anterior, Próximo slide. **Controles:** Girar barra, Mover.
- Nesta fase, ferramentas e ações só mudam o estado e vão para o log (`ui_tool`, `ui_action`). O desenho é da Fase 4 e os slides são da Fase 6.
- **Log:** `ui_open`, `ui_close`, `ui_tool`, `ui_action`, `ui_orientation`, `ui_drag_start`, `ui_drop` e `ui_cancel` (desistências).
- **Desenvolvimento:** sem `--overlay`, o **mouse faz o papel do dedo**, para testar a sidebar sem câmera.

**Testes (260 no total):**
- `test_dwell.py` (7);
- `test_sidebar_model.py` (12): inclui todas as bordas, posições e orientações sem sair da tela nem cobrir marcadores, arrasto com encaixe e fluxo completo com permanência;
- `test_sidebar_gui.py` (3): fluxo na janela com relógio falso (abrir, escolher o pincel, girar, mover para baixo, recolher), sidebar ignorada durante a calibração, redimensionamento preservando a ferramenta.

**Capturas sobre um slide fictício** conferidas visualmente. Corrigidos:
- setas de Voltar e Avançar trocadas;
- legendas pequenas (agora 17% do botão, em negrito);
- aviso "Pare o dedo para soltar" cortado quando o painel está encostado embaixo.

### Primeiro teste real da sidebar, com o mouse (2026-11-06 21:22 e 21:25, sem `--overlay`, sem celular)

- **Acionamentos:** 4 aberturas e 4 fechamentos; 3 ferramentas (pincel, ponteiro, borracha); 9 ações (voltar, avançar, limpar, slides); 2 trocas de orientação. **Mover não foi acionado.**
- **Desistências** (`ui_cancel`): 15. Oito delas com ≥ 80% do tempo cumprido (0,8 a 0,96): o cursor saiu do botão pouco antes de completar. Pode indicar que 0,8 s parece longo, ou só exploração da interface. A conferir com o relato do usuário e no teste com o dedo.
- **Teste com o dedo** (`--overlay`, câmera): ainda não aparece nos logs.

**Relato do usuário (21:29):**
- o teste com o dedo foi feito na sessão das 21:22 (celular conectado, janela sem `--overlay`);
- botões e legendas bons de ler e de acertar;
- permanência reduzida para **0,6 s** (pedido "deixa em 6s", entendido como 0,6 s).

**Etapa 3.5 encerrada**; a Fase 3 fica validada no Mac.

## Fase 4 — desenho (2026-11-06) — simulação

- `test_hand_pose.py` (11): pose em várias rotações; a foto real de "joinha" não é "pointing"; confirmação da caneta.
- `test_drawing.py` (16): reamostragem, voltar/avançar, limpar desfazível, borracha corta traços e só apaga formas tocadas no contorno, gesto de borracha = uma ação, prévia das formas, ponteiro não risca.
- `test_drawing_gui.py` (8, Qt offscreen): pincel pela sidebar; caneta descida sobre a sidebar não risca até levantar; traço que entra na sidebar para na borda e não aciona botão; "Limpar tudo?" com Não, Sim e tempo esgotado; círculo; caneta pela pose de mensagens de mão; anotações sobrevivem a redimensionar.
- Capturas sobre um slide: `fase4_desenho_sobre_slide.png`, `fase4_confirmar_limpar.png`.
- **Teste real pendente.**

### 1º teste real do desenho (2026-11-06 21:50, log `session-20261106-215038.jsonl`)

- Problema: várias formas seguidas sem querer (ex.: 4 retângulos entre 22:02:57,6 e 22:02:58,8) ao mover a mão até a sidebar.
- Correção: uma forma por seleção (volta ao Ponteiro) e 0,35 s de caneta levantada para concluir. 298 testes passando. Novo teste real pendente.

### 2º teste real do desenho (2026-11-06 22:25, log `session-20261106-222522.jsonl`) — uma forma por seleção validada

- 8 formas, cada uma seguida de `ui_tool_auto` (volta ao Ponteiro); nenhuma forma em sequência.
- 16 traços, borracha, voltar e limpar usados.

### Etapa 4.4 — cor, espessura e borracha (2026-11-06) — simulação

- `test_style_panel.py` (9) e 2 testes novos em `test_drawing_gui.py`: painel ao lado da sidebar em qualquer borda, dentro da tela; escolha por permanência; traço guarda a cor; não risca sobre o painel; painel fecha ao riscar e com o dedo longe. 309 testes passando.
- Captura: `fase4_painel_estilo.png`. **Teste real pendente.**

### Etapa 4.5 — Selecionar (2026-11-06) — simulação

- 4 testes novos: pega o item de cima; só pega ao descer a caneta; arrasto vira uma ação de Voltar; arrasto na janela com moldura. 313 testes passando.
- Captura: `fase4_selecionar.png`. **Teste real pendente** (junto com a 4.4, a pedido do usuário).

### Fase 6.1 — troca de slides (2026-11-06) — simulação

- `test_slides.py` (7): anotações por slide; não passa do 1º slide; sem envio de tecla a lousa não muda e aparece aviso; a janela troca a lousa junto com o slide. 320 testes passando.
- O envio real das teclas (CGEventPost no macOS) não pôde ser testado aqui (Linux). **Teste real pendente.**

### Teste real de 4.4, 4.5 e 6.1 (2026-11-06 22:50, log `session-20261106-225003.jsonl`)

- **Permissão de teclas:** `key_sender` macOS pronto (Acessibilidade liberada).
- **4.4 (cor/borracha):** cor Azul e borracha Grande escolhidas pelo painel e usadas: 11 traços, 14 apagamentos. A espessura não foi trocada. **Validado em parte.**
- **4.5 (Selecionar):** 21 arrastos, de 76 a 2.497 px. **Validado.**
- **6.1 (slides):** só um "Slide ant." no 1º slide (tecla enviada; contagem ficou no 1). "Próx. slide" não foi usado, então as anotações por slide não foram verificadas. **Pendente.**
- **Observação:** traços curtos em sequência rápida (2 a 13 pontos entre 22:57:39 e 22:57:42) sugerem a caneta subindo por oscilação da pose no meio da escrita. A confirmar com o usuário.
- **Calibração:** grade G com mediana de 25 px (1,3%) e máximo de 39 px (2,0%), pior que no teste anterior (0,42% / 1,37%). Possível mudança de posição da câmera; ver etapa 2.5.

### Fase 5.1–5.2 (2026-11-06) — simulação
- `test_pen_gate.py` (6): estados da caneta; pose ambígua não levanta nem desce a caneta. Resumo `pen_up` no log. 327 testes passando.

### Precisão: correção dos 9 pontos, One Euro e malha (2026-11-06) — simulação
- `test_precision.py` (9): correção exata nos 9 pontos; erro entre os pontos cai para menos de 15% do original; correção acumula entre testes G; medidas ruins rejeitadas; One Euro reduz o tremor à metade com atraso < 1% na escrita.
- `test_calibration_gui.py` (+2): com erro sistemático simulado, o 2º teste G mede menos de 20% do erro do 1º; R desliga a correção e o erro volta; nova calibração zera a correção; malha desenhada.
- Defeito achado pelo teste de integração: com o filtro, o cursor ficava na tela depois de o celular desconectar. Corrigido.
- 337 testes passando. **Teste real pendente.**

### Teste real de 5.1 e 6.1 (2026-11-06 23:34, log `session-20261106-233452.jsonl`)

- Rodou com a correção dos traços (5.1), mas **antes** da atualização de precisão (correção dos 9 pontos, filtro e malha chegaram ao Mac às 23:49).
- **5.1 (traços partidos): melhorou.** Pontos por traço (mediana): 40, contra 13 no teste das 22:50. A caneta desceu 81 vezes; 9 duraram menos de 0,3 s. Levantada por: mão fechada 54, aberta 19, mão perdida 8. Ainda houve 3 traços de 2 a 9 pontos às 23:48:07.
- **6.1 (slides): validado.** Os traços do slide 2 (6 itens) reapareceram ao voltar para ele às 23:48:31; o slide 1 voltou vazio, como estava. 5 trocas, todas com a tecla enviada.
- **4.4:** cores Verde e Amarelo escolhidas e usadas.

### Teste real da precisão (2026-11-06 23:54, log `session-20261106-235444.jsonl`)

- Calibração: erro no centro de 5,6 px (0,29%), a melhor até agora. O usuário sentiu a precisão "melhorar muito".
- Teste G: mediana de 13,6 px (0,71%), mas o ponto 2 (meio do alto) mediu 562 px: o dedo foi visto bem abaixo do alvo, provavelmente outra mão ou o braço. Por isso a **correção dos 9 pontos foi recusada** e não estava ativa; a melhora veio da calibração e do filtro One Euro.
- Correção: o teste G agora repete na hora um ponto a mais de 5% do alvo ("O dedo ficou longe do alvo: encoste de novo"), em vez de recusar a correção inteira. Novo teste no pytest. 338 testes passando.
- Caneta: 78 descidas, 12 com menos de 0,3 s.

### 4.6 — Redimensionar com a abertura da mão; malha M com 20 colunas (2026-11-07) — simulação
- `test_drawing.py` (+5): abrir amplia em torno do centro e a mão parada confirma; fechar reduz; mão parada sem mudar não entra no histórico; apontar de novo confirma e já pega outro desenho; sem abertura (mouse) só solta.
- `test_hand_pose.py` (+1): abertura fechada < apontando < aberta, em várias rotações.
- `test_drawing_gui.py` (+1): na janela, com mensagens de mão; captura `fase4_redimensionar.png`.
- 345 testes passando. **Teste real pendente.**

### Teste real de 4.6 e da correção (2026-11-07 00:16, log `session-20261107-001600.jsonl`) — redimensionar validado
- **4.6:** 6 redimensionamentos, de 47% a 157%; o usuário achou "muito bom". Abertura medida: 0,96 (fechada) a 2,18 (aberta), como previsto. 2 seleções sem mudar o tamanho.
- Calibração: 10,6 px no centro (0,55%). Teste G sem correção: mediana 9,0 px (0,47%), máximo 18,7 px. Correção aplicada (maior ajuste 28 px); o 2º G não foi feito, então o ganho não foi medido.

### Verificação entre os pontos (tecla V, 2026-11-07) — simulação
- 4 alvos entre os 9 do G, onde a correção só interpola; não cria nem muda a correção. Com erro sistemático simulado, a mediana caiu para menos de 30% depois do G. 346 testes passando. **Teste real pendente.**

### Pinça (D021, 2026-11-07) — simulação
- `test_hand_pose.py` (+3): pinça fechada × separada em várias rotações; histerese da caneta; foto real (joinha) não é pinça (0,82).
- `test_drawing_gui.py` (+1): K alterna; no modo pinça, o indicador esticado sem pinça não escreve e a pinça escreve.
- 350 testes passando. **Comparação real pendente.**

### D022 — reconhecimento adaptado do open-source-hands (2026-11-07) — simulação
- `test_gestures.py` (49 casos): poses sintéticas em várias rotações, com e sem pontos 3D; joinha não escreve; pinça; troca exige 70 ms, não um quadro; mão perdida esquecida; duas mãos mantêm o próprio estado; **mão de lado com tremor: antigo > 50 trocas, novo ≤ 2**; dobra e nota.
- `test_precision.py`: filtro 2D vetorial mantém a diagonal reta; intervalo longo limitado. Tremor parado 0,0020 → 0,0008; atraso na escrita 0,004.
- Foto real (joinha) pelo detector completo: novo "other", antigo "fist"; nenhum escreve.
- 409 testes passando. **Comparação com a câmera real pendente** (log: trocas de pose por minuto, novo × antigo).

### Teste real do reconhecimento D022 (2026-11-07 11:37, log `session-20261107-113743.jsonl`)
- ~7,5 min com uma mão na imagem, 23 quadros/s. **Trocas de pose: novo 254 (34/min) × antigo 706 (95/min), nos mesmos quadros — 64% a menos.** Parte das trocas é intencional: 83 descidas da caneta ≈ 166 trocas (22/min).
- Caneta: 83 descidas, 8 com menos de 0,3 s (10%; antes 11–15%); 3 delas por mão perdida. Levantada quase sempre com a mão fechada (62) ou mão perdida (20). Pontos por traço (mediana): 39.
- Desenho: 18 traços, 19 movimentos, 10 redimensionamentos, 4 trocas de slide, 7 limpezas confirmadas.
- Calibração 6,9 px (0,36%); teste G mediana 16,9 px (0,88%); correção aplicada (maior ajuste 32 px). Ganho da correção ainda não medido (falta G repetido ou V).
- Ajuste: o resumo do log passou a usar a taxa real de quadros (antes supunha 30 qps).

### Assistente de calibração (D023, 2026-11-07) — simulação
- `test_guided.py` (3): etapas em ordem com cartão e resumo; resultados fora de ordem ignorados; cancelamento; piora sinalizada.
- `test_calibration_gui.py` (+2): percurso completo na janela sem teclado (cantos → V → G → V → resumo), com erro sistemático simulado: melhora > 70%; Esc cancela. Capturas `assistente_etapa1.png`, `assistente_etapa3.png`, `assistente_resumo.png`.
- 1ª versão do cartão: texto e contagem se sobrepunham em 1200×600; refeito com layout medido pela fonte.
- 414 testes passando. **Teste real pendente.**

### D024 — gestos de movimento, gravação e laboratório (2026-11-07) — simulação
- `test_motions.py` (8): deslizar ← → só com mão aberta, rápido, horizontal; ocupado e intervalo; toque rápido × pinça segurada; zoom com duas mãos e regras de pegada; zoom no redimensionar é uma ação de Voltar.
- `test_recording.py` (4): gravação ida e volta sem imagem; reprodução compara (antigo > 50 trocas, novo ≤ 2 na mão de lado); limiares por argumento; detector real grava pontos 3D.
- `test_gesture_lab.py` (3) e `test_drawing_gui.py` (+4): deslizar troca slide e H desliga; toque de pinça aciona o botão sem permanência; duas mãos ampliam o desenho sem riscar; laboratório na janela (captura `laboratorio_gestos.png`).
- 434 testes passando. **Teste real pendente.**

### Comparação com os testes reais do usuário (2026-11-07 12:20)

**Reconhecimento novo (D022) × antigo (D018), nos mesmos quadros:**
| Sessão | Novo | Antigo |
|---|---|---|
| 11:37 (~7,5 min) | 35 trocas de pose/min | 97/min |
| 12:00 (assistente + uso curto) | 11/min | 36/min |
→ o novo troca ~3× menos de pose, nas duas sessões.

**Caneta (descidas < 0,3 s = traço partido):** antigo com a correção 5.1 (23:34, 23:54, 00:04, 00:16): 31 de 258 = 12,0%. Novo (11:37, 12:00): 9 de 99 = 9,1%. Pontos por traço (mediana) parecidos (~40) nas sessões com escrita.

**Correção dos 9 pontos (assistente, 12:00), medida ENTRE os pontos (V):** antes 23,3 px de mediana (máx. 42,7) → depois 10,4 px (máx. 20,6): **−55%**. Os 4 pontos melhoraram (42,7→6,6; 22,3→9,6; 21,5→11,3; 24,2→20,6). Conclusão: a malha 3×3 basta; o erro restante (~10 px, 0,5%) está perto do limite físico estimado (~5–10 px). Malha 5×5 não se justifica.

**Sem dados ainda:** pinça × indicador (a tecla K nunca foi usada; todas as descidas foram no modo indicador) e os gestos de movimento (D024 chegou ao Mac depois da sessão das 12:00).

### Teste real com gravação (2026-11-07 12:22, `landmarks-20261107-122234.jsonl.gz`, 5,1 min)
- **Reprodução (`tools.replay_landmarks`):** novo 17 trocas/min e **7 piscadas** (< 200 ms); antigo 28/min e **69 piscadas**: ~10× menos piscadas. Limiares 0,55/0,35 no lugar de 0,62/0,42: praticamente igual (16/min, 8 piscadas) — mantidos.
- **Problema encontrado:** 8 toques de pinça falsos no uso (11 na reprodução), todos ao **fechar a mão** para levantar a caneta: o polegar encosta no indicador dobrado e parece pinça. Nenhum acionou botão (não havia botão sob o dedo). O mesmo afetaria a caneta no modo pinça: descida sem querer 13,5% do tempo.
- **Regras testadas na gravação:** força da pinça do kit 11 falsos; nota da pose "pinça" 12; sem punho 5; indicador < 0,5 dobrado 2; **distância < 0,18 + sem punho: 0**. Caneta-pinça: 0,30/0,42 → 13,5%; **0,15/0,30 + nunca com punho → 0,6%** (2 descidas falsas com a confirmação em quadros). Pinça real ≈ 0,09: continua funcionando.
- Aplicado; teste `test_real_recording_regression` reproduz a gravação quando ela existe (Mac). 437 testes.
- Assistente: cantos 11,2 px; verificação 30,0 → 24,9 px (−17%; na sessão das 12:00, −55%).

### Teste real (2026-11-07 13:35, `landmarks-20261107-133539.jsonl.gz`, 9,2 min)
- **Reprodução:** novo 31 trocas/min e **39 piscadas**; antigo 115/min e **716 piscadas** (~18× menos).
- **Toques de pinça falsos (9 no uso, 17 na reprodução):** falhas de **1 quadro** do rastreamento — no meio de um apontar, o polegar aparece colado no indicador por ~40 ms. Correção: a pinça precisa aparecer fechada em ≥ 2 quadros. Resultado na reprodução: 17 → 0 (e 0 na gravação das 12:22). Nenhum clique falso aconteceu (sem botão sob o dedo).
- **Deslizar:** 3 deslizes, 3 trocas de slide (← → ←), todas enviadas.
- **Assistente:** cantos 8,4 px; verificação 11,7 → **19,6 px (correção piorou 68%)**. O teste G mediu 19,0 px — pior que a verificação sem correção —, então a correção aprendeu o erro do dedo, não o do sistema. Agora o assistente **desliga a correção sozinho** quando a verificação final fica pior que a inicial (`residual_auto_off`); R liga de novo.
- Laboratório (L) e pinça (K) ainda não usados. 439 testes passando.

### D025 — abrir com dois cliques + QR (2026-11-07) — simulação
- `test_launcher.py` (5): `--screen auto` escolhe a TV quando existe; o QR gerado decodifica para o endereço (leitor de QR do OpenCV); na janela, o cartão aparece até o celular conectar, o QR **na tela** decodifica, e o assistente espera a conexão; `SmartBoard.command` executável e com sintaxe válida; `SmartBoard.bat` com CRLF e as mesmas opções.
- Captura: `conecte_o_celular.png`. 444 testes passando. **Teste real pendente; Windows não testado.**

### Teste real 13:59 e ajuste D026 (2026-11-07)
- Log: caneta descida por 18–63 s seguidos (mediana 18 s); quase nada desenhado. Reprodução: novo "sem pose" 42% do tempo; em 30% dos quadros o antigo via "apontar" e o novo não (regra mais fraca: médio/anelar dobrados; dobra mediana desses dedos ~0,55).
- Simulação da caneta nas 3 gravações (atual × apontar relaxado + caneta livre): apontar reconhecido 63→92%, 66→85%, 94→95%.
- Assistente: cantos 6,4 px; verificação 13,6 → 10,8 px (−21%).
- 448 testes passando (inclui as 3 gravações reais como regressão quando presentes).

### D027 — guardar, recuperar e exportar (2026-11-07) — simulação
- `test_annotations.py` (7): ida e volta por slide (slide vazio não ocupa espaço; histórico não salvo); "mais recente" ignora a aula atual, aulas vazias e arquivo corrompido; formato desconhecido recusado; salvamento automático com intervalo de 2 s e ao fechar; nada desenhado = nenhum arquivo; tecla O recupera; tecla E gera PDF (3 páginas para 3 slides anotados; nada desenhado = nada exportado).
- Exemplo: `anotacoes_exemplo.pdf`. 455 testes passando. **Teste real pendente.**

## Marcadores discretos (D028) — teste real pendente

1. Abrir a lousa e calibrar (A). Os marcadores devem aparecer durante a calibração e sumir ~1 s depois de "referência ok".
2. No log: `marker_reference` com `ok: true` e `mean_side_px` ~19 (borda menor não muda o tamanho visto).
3. Mexer um pouco o celular, apertar **N**: o painel deve mostrar "câmera deslocada … corrigido"; o cursor volta para baixo do dedo. Apertar **N** de novo: somem.

## Estudo do toque (D029, etapa 5.3) — coleta real pendente

1. Abrir a lousa, conectar o celular (não precisa de `--record`).
2. Na janela da câmera, apertar **T** e seguir as 15 etapas (~2 min). Use a mão de escrever, de lado para a câmera como numa aula.
3. No Terminal: `.venv/bin/python -m tools.touch_report`. Enviar a saída (ou pedir para eu ler o log).

## Cantos voltam quando o celular mexe (D030) — teste real pendente

1. Calibrar (A) e esperar os cantos sumirem.
2. Mexer o celular (empurrar ou girar um pouco) e soltar: os cantos devem voltar em menos de 1 s, a mensagem "O celular mexeu" aparecer, e sumirem ~1–2 s depois de o celular parar. O cursor deve continuar embaixo do dedo.
3. Andar na frente da câmera e trocar de slide sem mexer o celular: os cantos **não** devem voltar.
4. No log: `phone_moved` e `phone_reframed` (quantas vezes e quanto tempo levou).

## Teste real 2026-11-07 16:37 e 16:54 (D030, D034, D035)

Resultados dos logs `session-20261107-163758` e `session-20261107-165450`:

| Item | Resultado | Ação |
|---|---|---|
| Calibração automática (1ª abertura) | ❌ caiu para os 4 cantos: marcadores **não vistos** nos 6 s após conectar (o celular ainda estava sendo posicionado depois de ler o QR). Cantos ok em 43 s; referência com 3 marcadores | Espera 6 → **20 s**; aviso diz que **C** pula para os cantos |
| Reaproveitar a calibração (2ª abertura) | ✅ **sem nenhum toque**: reaproveitada 0,6 s depois de conectar (diferença dos marcadores 0,35%) | — |
| Celular mexido (cantos voltam) | ⚠️ voltou 2× e reenquadrou em 1,1–1,7 s, nos dois casos com a mão segurando/redimensionando desenhos perto da câmera (provável falso alarme: a mão grande ocupa a imagem) | Ignorado enquanto um desenho está seguro |
| Selecionar + tamanho pela mão | ⚠️ 39 movimentos, 26 redimensionamentos; a palma variou só 23–40 px; maior ampliação 1,45×, maior redução 0,79×; **22 de 26** mudaram o tamanho em ±5% só pelo ruído | Zona morta de 8% e ganho 1,0 → **1,8** |
| Deslizar → slide | ✅ 1 deslize, slide trocado | — |
| Consumo | CPU mediana 68–96% de um núcleo (p95 110–115%), memória ≤ 390 MB, 26–28 quadros/s | Acompanhar |
