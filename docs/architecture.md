# Arquitetura — Prova de Conceito (Fase 1)

**Status:** implementada até a etapa 1.5 (em validação). Desde a D013, o modo padrão processa a mão **no notebook**.
**Escopo:** somente a Fase 1 (`PROJECT_CONTEXT.md` §16 e §19). Não inclui calibração, sidebar, ferramentas de desenho nem integração com apresentações.

**Critério de sucesso da Fase 1:** ao mover o indicador diante da câmera do celular, um cursor acompanha o movimento no notebook em tempo real.

---

## 1. Visão geral

### 1.1. Modo `stream`, o padrão desde a D013: MediaPipe no notebook

```
┌──────────────────────── CELULAR (navegador) ────────────────────────┐
│ getUserMedia (câmera traseira)                                       │
│        │ quadro novo (requestVideoFrameCallback)                     │
│        ▼                                                             │
│ frame_sender.js: reduz (lado maior 640 px) → JPEG 0,7                │
│   contrapressão: pula se bufferedAmount > 64 KB ou JPEG em andamento │
│        │ binário: cabeçalho SBF1 (16 B) + JPEG, ≤ 30 q/s             │
└────────┼─────────────────────────────────────────────────────────────┘
         │  WSS (Wi-Fi local)
┌────────┼──────────────── NOTEBOOK (Python) ──────────────────────────┐
│        ▼                                                             │
│ Thread de rede (aiohttp): valida o envelope (frame_protocol), descarta│
│   seq antigo → on_frame                                              │
│        │                                                             │
│        ▼                                                             │
│ Thread de visão (frame_processor): vaga única, o quadro novo         │
│   substitui o que esperava → JPEG→RGB (OpenCV) → MediaPipe Python    │
│   (VIDEO) → HandTrackingMessage + métricas (evento `vision`)         │
│        │ Qt Signal                                                   │
│        ▼                                                             │
│ Thread principal (PySide6): cursor + painel (tela cheia na TV: --screen) │
│ Log de sessão (JSONL): rede + visão, nunca imagens                   │
└──────────────────────────────────────────────────────────────────────┘
```

No desenvolvimento, a "lousa" é a Smart TV do usuário, ligada ao Mac como segunda tela (D013). Na sala de aula, é o projetor.

### 1.2. Modo `local` (`&mode=local`, D002): MediaPipe no celular

```
┌──────────────────────── CELULAR (navegador) ────────────────────────┐
│ getUserMedia (câmera traseira)                                       │
│        │ frames                                                      │
│        ▼                                                             │
│ MediaPipe Hand Landmarker (WASM, arquivos locais em mobile/vendor/) │
│        │ 21 landmarks normalizados [0..1]                            │
│        ▼                                                             │
│ Extrai ponta do indicador (landmark 8) + confiança                   │
│        │ JSON (≤ 30 msg/s)                                           │
└────────┼─────────────────────────────────────────────────────────────┘
         │  WSS  (Wi-Fi local, mesma origem HTTPS da página)
┌────────┼──────────────── NOTEBOOK (Python) ──────────────────────────┐
│        ▼                                                             │
│ Thread de rede (asyncio + aiohttp)                                   │
│   • serve mobile/ por HTTPS                                          │
│   • endpoint /ws (WebSocket)                                         │
│   • valida mensagens (message_protocol)                              │
│        │ Qt Signal (cross-thread, enfileirado)                       │
│        ▼                                                             │
│ Thread principal (PySide6)                                           │
│   • coordinate_mapper: câmera normalizada → janela (identidade na F1) │
│   • cursor_window: desenha o cursor + painel de status/métricas      │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Decisões técnicas da Fase 1

Cada decisão está registrada com alternativas em `docs/decisions.md`.

| # | Tema | Decisão |
|---|---|---|
| D002 | Onde roda o rastreamento | Primeiro **no celular** (MediaPipe Tasks Vision para web). Hoje é o modo `local`, substituído como padrão pela D013. |
| D013 | Onde roda o rastreamento (atual) | **No notebook** (MediaPipe Python). O celular envia quadros JPEG reduzidos pelo mesmo WebSocket, com contrapressão nos dois lados. |
| D003 | Servidor no notebook | **aiohttp** em um único processo e **uma única porta**: serve a página do celular por HTTPS e o WebSocket em `/ws`. |
| D004 | HTTPS na rede local | **Certificado autoassinado** gerado na primeira execução, com o IP local no SAN, usando a biblioteca `cryptography`. |
| D005 | Integração asyncio ↔ Qt | **Thread separada** para a rede, ligada à interface por **Signal do Qt**. Não usa `qasync`. |
| D006 | Execução sem internet | MediaPipe (JS + WASM) e o modelo `hand_landmarker.task` ficam em `mobile/vendor/`, **sem CDN**. |
| D007 | Acesso ao servidor | **Token aleatório por sessão** na URL. O servidor recusa conexões sem token. |

### 2.1. Por que HTTPS é obrigatório

Os navegadores só liberam `getUserMedia()` (acesso à câmera) em **contexto seguro**: páginas HTTPS ou `localhost`. O celular acessa o notebook pelo IP da rede local (`192.168.x.x`), que **não** é `localhost`. Em HTTP simples, `navigator.mediaDevices` fica indefinido e a câmera não abre.

**Consequência:** a página e o WebSocket precisam estar em HTTPS/WSS. Servir os dois na **mesma origem** (mesmo IP e porta) faz o professor aceitar o certificado uma única vez.

### 2.2. Por que aiohttp e não `websockets`

A biblioteca `websockets` foca em WebSocket. Servir a página HTTPS exigiria um segundo servidor, portanto uma segunda porta e um segundo aviso de certificado no celular. O `aiohttp` faz arquivos estáticos e WebSocket no mesmo servidor, com uma dependência só.

### 2.3. Onde fica o processamento: celular (D002) → notebook (D013)

A escolha inicial foi o celular, pelos motivos abaixo. A medição da etapa 1.4 mostrou um teto de ~11 FPS no moto g54 e a página travada pelo MediaPipe (R10). Por isso, a D013 passou o processamento para o notebook. Os argumentos originais ficam registrados porque ainda valem para o modo `local`:

- O tráfego cai de vídeo contínuo para algumas dezenas de mensagens JSON pequenas por segundo (`CLAUDE.md` §6.2).
- A imagem da sala de aula nunca sai do celular (`CLAUDE.md` §11).
- O notebook fica livre para a interface e, mais adiante, para a apresentação.

**Custo:** o desempenho depende do celular. O FPS da inferência precisa ser **medido** em pelo menos um Android intermediário e, se houver, em um iPhone. A migração para o notebook (WebRTC + MediaPipe Python) continua possível, porque o protocolo transporta coordenadas e não depende de onde elas são calculadas.

## 3. Sistemas de coordenadas na Fase 1

Seguindo o `CLAUDE.md` §5.2, cada sistema de coordenadas tem nome próprio e só se converte em outro de forma explícita.

| Sistema | Onde existe | Fase 1 |
|---|---|---|
| `camera_px` | celular (pixels do frame) | não trafega |
| `camera_norm` | celular → rede | x, y ∈ [0, 1], origem no canto superior esquerdo do frame, **sem espelhamento** |
| `surface_norm` | notebook | **Fase 2:** x, y ∈ [0, 1] sobre a área projetada, obtido de `camera_norm` pela homografia (`desktop/calibration/homography.py`) |
| `ui_px` | notebook (janela do cursor) | `camera_norm × tamanho da janela` |

Na Fase 1, o `coordinate_mapper` faz um mapeamento **provisório e explícito** de `camera_norm` para `ui_px`. Esse mapeamento não é calibração e será trocado pela homografia na Fase 2, sem mudar o protocolo.

## 4. Estrutura de arquivos da Fase 1

Subconjunto da estrutura do `PROJECT_CONTEXT.md` §15. Só os arquivos que a Fase 1 realmente usa.

```
desktop/
├── main.py                      # janela do cursor (padrão), --headless, --screen N (TV)
├── config.py                    # porta, limites, tempos (sem números espalhados)
├── communication/
│   ├── server.py                # aiohttp: HTTPS estático + /ws + token
│   ├── server_thread.py         # servidor num laço asyncio em thread própria (D005)
│   ├── message_protocol.py      # esquema, validação, descarte de mensagens antigas
│   ├── frame_protocol.py        # envelope binário dos quadros JPEG (D013)
│   └── tls.py                   # gera/recarrega certificado autoassinado
├── core/
│   ├── coordinate_mapper.py     # camera_norm → ui_px (StretchMapper provisório na F1)
│   └── session_log.py           # log de sessão em logs/*.jsonl (métricas, sem imagens)
├── calibration/                 # (Fase 2) homografia, coleta, estados, grade G, marcadores ArUco (D014/D015)
├── vision/                      # (D013) visão computacional no notebook
│   ├── hand_tracker.py          # MediaPipe Python (VIDEO) + decodificação JPEG
│   └── frame_processor.py       # thread própria, vaga única, métricas por segundo
└── interface/
    ├── qt_bridge.py             # eventos do servidor → sinais Qt (thread principal)
    ├── cursor_state.py          # estado e métricas da janela, sem Qt (testável)
    └── cursor_window.py         # janela com cursor + painel de status

mobile/
├── index.html
├── styles/app.css
├── scripts/
│   ├── app.js                   # página: modo stream (padrão) ou &mode=local
│   ├── camera.js                # getUserMedia, câmera traseira
│   ├── frame_sender.js          # (D013) JPEG + envio binário com contrapressão
│   ├── hand_tracking.js         # modo local: MediaPipe, extrai landmark 8
│   └── websocket_client.js      # conexão, reconexão, ping/pong
└── vendor/                      # MediaPipe 1.2.2 + modelo (versão fixada, D006);
                                 # o notebook usa o mesmo hand_landmarker.task

tools/
├── fake_phone.py                # celular simulado (só para desenvolvimento)
└── log_summary.py               # tabela por conexão a partir do log de sessão

tests/
├── test_message_protocol.py
├── test_server.py
├── test_tls.py
├── test_coordinate_mapper.py
├── test_cursor_state.py
├── test_frame_protocol.py
├── test_frame_processor.py      # detector falso: vaga única, descarte, métricas
├── test_hand_tracker.py         # MediaPipe real com tests/fixtures/hand_thumbs_up.jpg
├── test_frame_pipeline.py       # JPEG pelo WebSocket → MediaPipe → hand_tracking + log
└── test_gui_integration.py      # servidor em thread + TLS + Qt offscreen
```

**Simulador:** o `fake_phone.py` envia mensagens válidas e inválidas para testar o notebook sem câmera. Pelo `CLAUDE.md` §9.4, ele serve para desenvolvimento e **não substitui** o teste com celular real.

## 5. Máquinas de estado da Fase 1

**Conexão (celular e notebook):** `Desconectado → Conectando → Conectado → Reconectando → Erro`

**Rastreamento (celular):** `Inativo → Inicializando → Mão detectada ↔ Rastreamento perdido`

Na Fase 1 não existe estado de gesto. O cursor só mostra a posição. Interpretar gestos é trabalho da Fase 5.

## 6. Métricas que a Fase 1 deve medir

Nenhuma meta numérica é definida antes da medição (`PROJECT_CONTEXT.md` §17, `CLAUDE.md` §10). A Fase 1 instrumenta o sistema para coletar:

| Métrica | Onde é medida |
|---|---|
| FPS da inferência MediaPipe | celular (exibido na tela) |
| Mensagens/s recebidas | notebook (painel de status) |
| RTT da rede (ping/pong) | celular e notebook |
| Tempo de inferência por frame | celular |
| Latência ponta a ponta estimada | inferência + RTT/2 + tempo de renderização |
| Tremor do cursor com a mão parada | desvio-padrão da posição em `ui_px` durante 5 s |
| Tempo de reconexão após queda do Wi-Fi | notebook |

Os resultados vão para `docs/testing.md`, com data, aparelho e condições.

## 7. Riscos identificados

| # | Risco | Impacto | Mitigação / validação na Fase 1 |
|---|---|---|---|
| R1 | Celular recusar WSS com certificado autoassinado, mesmo depois de aceitar a página (comportamento conhecido em algumas versões do Safari no iOS) | Baixo na Fase 1 (o celular de teste é Android, ver D008). Alto se o iPhone entrar depois. | Confirmar no Chrome do Android na etapa 1.2. iPhone fica para depois da Fase 1. Plano B: CA local (`mkcert`) instalada como perfil. |
| R2 | FPS baixo do MediaPipe em celular intermediário | Médio | Medir. Opções: resolução menor, `numHands: 1`, Web Worker, ou processamento no notebook. |
| R3 | Rede da escola com **isolamento de clientes** (celular não enxerga o notebook) | Alto em sala de aula | Detectar na etapa 1.2. Plano B: hotspot do celular ou do notebook. Registrar em `docs/testing.md`. |
| R4 | Firewall do macOS/Windows bloquear a porta | Baixo | Mensagem clara na inicialização. Documentar o passo de liberação. |
| R5 | Detectar a mão **≠** detectar o toque (`PROJECT_CONTEXT.md` §9.3) | Alto (Fases 2 e 5) | Fora do escopo da Fase 1, mas o protocolo já envia `z` e `confidence` para a investigação futura. |
| R6 | A tela do celular apagar durante a aula | Médio | Testar a Screen Wake Lock API na etapa 1.5. |
| R10 | **(Contornado pela D013 no modo padrão)** **MediaPipe bloqueia a linha de execução da página** (`detectForVideo` é síncrono). Enquanto ele processa um quadro, a página não responde ao notebook: RTT de **6,5 ms → 102 ms** no moto g54 ao ligar o rastreamento; no Chrome sem tela, 11 ms (CPU, 46 ms/quadro) contra 257 ms (GPU emulada, 580 ms/quadro) | **Alto para a 1.5:** a posição do dedo herda esse atraso | Medir com o log de sessão. Candidato: rodar o MediaPipe num **Web Worker**, já previsto na documentação do MediaPipe, para liberar a página. Decidir com números. |
| R8 | **Variação do RTT no Wi-Fi** (medido no moto g54: mediana ~11 ms, p90 ~84 ms, pico 364 ms) | Médio: travadas do cursor | Medir sob carga na 1.6. Se incomodar: Wi-Fi 5 GHz, hotspot dedicado, ou suavização no notebook (Fase 5). O protocolo já descarta mensagens atrasadas (`seq`). |
| R9 | **Frame da câmera em retrato** (720×1280 com o celular na vertical): a orientação do frame depende de como o celular está preso | Baixo na Fase 1; relevante na Fase 2 | `camera_norm` é sempre relativo ao frame entregue, e a homografia da Fase 2 absorve a rotação. A resolução real é registrada no `hello`. |
| R11 | **Banda do Wi-Fi** com quadros JPEG: ~20–80 KB × até 30 q/s ≈ 0,5–2,4 MB/s | Médio na escola (Wi-Fi compartilhado) | O celular pula quadros quando a fila cresce (`skipped` no log). Ajuste por URL (`&side=`, `&q=`, `&fps=`). Medir no Wi-Fi real. |
| R12 | **Tela da lousa no desenvolvimento** (Smart TV): espelhamento sem fio (AirPlay) acrescenta atraso de imagem que o projetor por cabo não tem | Médio: pode mascarar a medição de atraso percebido | Preferir HDMI; se for AirPlay, registrar no teste. O log mede rede e processamento, não a TV. |
| R13 | **Processamento disputa CPU com a apresentação** no notebook do professor | Médio no Windows real | Medir CPU e `inference_ms` na etapa 1.7. A vaga única impede atraso acumulado; no pior caso, a taxa cai. |
| R7 | Diferenças entre macOS (desenvolvimento) e Windows (notebook do professor): firewall, interface de rede usada para descobrir o IP, escala de tela (DPI) no PySide6, caminhos de arquivo | **Alto** (o Windows é o destino real, ver D008) | Nenhuma API específica de sistema no código; IP descoberto de forma portável; caminhos via `pathlib`. Validação obrigatória no Windows na etapa 1.7. |
