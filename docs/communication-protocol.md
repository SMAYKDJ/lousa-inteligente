# Protocolo de comunicação — v0 (Fase 1)

**Status:** implementado (etapas 1.1–1.5), validado com Android na etapa 1.4; quadros binários (D013) validados só em simulação até agora.
**Transporte:** WebSocket seguro (WSS) em `wss://<ip-do-notebook>:<porta>/ws?token=<token>`
**Formato:** JSON UTF-8, uma mensagem por frame de texto; quadros de câmera em frames binários (§2.7).

**Modos do celular (D013):**

- `stream`, o padrão: o celular envia quadros JPEG (§2.7), e o notebook detecta a mão e gera internamente as mesmas `hand_tracking`.
- `local`, com `&mode=local` na URL: o celular roda o MediaPipe e envia `hand_tracking` (§2.3).

## 1. Regras gerais

- Toda mensagem tem `type` (string) e `v` (versão do protocolo, inteiro, `0` nesta fase).
- Mensagens de rastreamento têm `seq` (inteiro crescente por conexão). O notebook **descarta** qualquer `seq` menor ou igual ao último processado. Assim, dado antigo nunca move o cursor (`CLAUDE.md` §6.2).
- Coordenadas estão sempre em `camera_norm`: x e y ∈ [0, 1], origem no canto superior esquerdo do frame, sem espelhamento.
- O MediaPipe pode devolver landmarks um pouco fora de [0, 1] quando o dedo está na borda do frame. **O celular limita (clamp) x e y a [0, 1] antes de enviar.** O notebook rejeita valores fora da faixa. Essa é uma limitação conhecida: na borda do frame, a posição fica presa ao limite.
- Campos desconhecidos são ignorados pelo notebook, e não rejeitados (ver §4).
- O notebook **rejeita** mensagens com campos ausentes, tipos errados ou valores fora da faixa. A rejeição é registrada no log e não derruba a conexão, a menos que se repita (limite configurável).
- Taxa máxima de `hand_tracking`: configurável, inicialmente 30 msg/s. Esse valor é um ponto de partida para teste, não uma meta validada.

## 2. Mensagens

### 2.1. `hello` (celular → notebook), primeira mensagem

```json
{ "type": "hello", "v": 0, "client": "mobile-web", "client_version": "0.1.0",
  "camera": { "width": 1280, "height": 720, "facing": "environment" } }
```

`facing`: `environment` (traseira), `user` (frontal) ou `unknown`, quando o navegador não informa (webcams de notebook e alguns Android). `width`/`height` são os do frame entregue: com o celular na vertical, o frame vem em retrato (ex.: 720×1280).

### 2.2. `welcome` (notebook → celular)

```json
{ "type": "welcome", "v": 0, "session_id": "a1b2c3", "max_rate_hz": 30 }
```

### 2.3. `hand_tracking` (celular → notebook)

```json
{ "type": "hand_tracking", "v": 0, "seq": 1532, "t_client_ms": 81234.5,
  "hand": { "present": true, "handedness": "Right", "confidence": 0.93,
            "index_tip": { "x": 0.52, "y": 0.43, "z": -0.04 } },
  "inference_ms": 18.2 }
```

Quando não há mão: `"hand": { "present": false }`. O celular envia isso **uma vez** ao perder o rastreamento e não repete enquanto a mão continuar ausente.

> Os valores numéricos acima são ilustrativos, não dados reais de rastreamento.

### 2.4. `ping` / `pong` (qualquer direção)

```json
{ "type": "ping", "v": 0, "id": 77, "t_sender_ms": 81300.0 }
{ "type": "pong", "v": 0, "id": 77, "t_sender_ms": 81300.0 }
```

O `pong` do celular também leva `t_reply_ms`, o horário do celular ao responder. Esse campo é opcional e foi acrescentado no cliente 0.3.2. Com ele, o notebook estima a diferença entre os dois relógios (`clock_sync.py`):

- usa a amostra de menor RTT entre as 10 últimas;
- o erro é de ± metade desse RTT.

Isso serve **só para medir** a latência da captura no celular até o resultado no notebook. O `t_client_ms` do quadro usa o `captureTime` da câmera quando o navegador o informa. Nenhum controle depende dessa estimativa.

O RTT é calculado por quem enviou o `ping`, sempre com o próprio relógio. Como os relógios do celular e do notebook não estão sincronizados, nenhuma latência é calculada subtraindo horário de um aparelho do horário do outro.

### 2.5. `status` (celular → notebook, ~1 por segundo)

```json
{ "type": "status", "v": 0, "fps": 8.5, "tracking_state": "tracking_active",
  "inference_ms": 98.0, "load_ms": 14800, "delegate": "GPU" }
```

`fps` e `tracking_state` são obrigatórios. `inference_ms` (média do último segundo), `load_ms` (tempo para o MediaPipe ficar pronto) e `delegate` (`GPU`/`CPU`) são **opcionais**: servem ao log de sessão (`logs/*.jsonl`).

Também opcionais:

- `mode`: `stream` ou `local`.
- No modo `stream`:
  - `encode_ms`: tempo médio para gerar o JPEG;
  - `frame_kb`: tamanho médio do quadro;
  - `skipped`: quadros pulados por contrapressão no último segundo.

Nesse modo, `fps` é a taxa de quadros **enviados** e `tracking_state` é `inactive`, porque quem rastreia é o notebook.

```json
{ "type": "status", "v": 0, "mode": "stream", "fps": 24.0, "tracking_state": "inactive",
  "encode_ms": 9.0, "frame_kb": 40.0, "skipped": 2 }
```

### 2.6. `error` (notebook → celular)

```json
{ "type": "error", "v": 0, "code": "invalid_message", "detail": "index_tip.x fora de [0,1]" }
```

### 2.7. Quadro de câmera (celular → notebook, frame **binário**, modo `stream`)

Cabeçalho de 16 bytes, little-endian, seguido do JPEG:

| Offset | Bytes | Campo | Tipo |
|---|---|---|---|
| 0 | 4 | magic `SBF1` | ASCII |
| 4 | 4 | `seq` | uint32, crescente por conexão |
| 8 | 8 | `t_client_ms` | float64, `performance.now()` do celular no momento da captura |
| 16 | … | JPEG | começa com `FF D8` |

Regras:

- **Imagem:** a cena inteira da câmera, apenas reduzida. O padrão é o lado maior com 640 px, por exemplo 360×640 com o celular em pé. Por isso, coordenadas normalizadas sobre ela valem para o quadro original (`camera_norm`).
- **Validação:** o notebook rejeita, com `error`, quadros acima de 512 KB (`MAX_FRAME_BYTES`, código `message_too_large`), com magic errado, `t_client_ms` negativo ou não finito, ou conteúdo que não começa com `FF D8`. Quadros com `seq` antigo são descartados sem erro.
- **Contrapressão no celular:** só envia se a fila de saída do WebSocket (`bufferedAmount`) estiver abaixo de 64 KB e nenhum outro JPEG estiver sendo gerado. Caso contrário, pula o quadro e conta em `skipped`.
- **Contrapressão no notebook:** há uma vaga única de processamento. Um quadro novo substitui o que esperava, que é contado como descartado no log (evento `vision`).
- **Privacidade:** o notebook só mantém a imagem em memória durante o processamento e nunca a grava (`CLAUDE.md` §11).

Exemplo de cabeçalho (`seq` = 42, `t_client_ms` = 1234,5): `53 42 46 31 2a 00 00 00 00 00 00 00 00 4a 93 40`.

## 3. Autenticação mínima

O notebook gera um `token` aleatório a cada sessão e exibe a URL completa (com o token) na tela. Conexões sem o token correto recebem HTTP 403. Isso protege contra acesso casual de outros aparelhos da mesma rede (`CLAUDE.md` §11), mas não é um mecanismo de segurança forte.

- O token é exigido na página (`/`) e no WebSocket (`/ws`). Os arquivos em `/static/` (scripts, estilos, MediaPipe) são públicos: não dão nenhum controle sobre o notebook.
- O log de requisições HTTP fica desligado para o token não aparecer no terminal.

## 3.1. Regras de conexão

- **Um celular por vez.** Uma conexão nova substitui a anterior. Assim o celular reconecta na hora, mesmo que o notebook ainda não tenha percebido a queda da conexão antiga.
- A conexão substituída é fechada com o código WebSocket **4000** (`WS_CLOSE_REPLACED`). O cliente que recebe esse código **não reconecta sozinho**: mostra um aviso e o botão "Reconectar". Sem essa regra, dois aparelhos com a página aberta se derrubam em ciclo (observado no teste real; ver `testing.md`).
- A primeira mensagem precisa ser `hello` em até 5 s (`HELLO_TIMEOUT_S`). Caso contrário, a conexão é encerrada.
- Depois de 20 mensagens inválidas (`MAX_INVALID_MESSAGES`), a conexão é encerrada.
- O celular reconecta sozinho, aguardando 0,5 s, 1 s, 2 s e depois 5 s entre tentativas. Uma tentativa que não abre em 5 s é abandonada.
- **Limitação conhecida:** o token muda toda vez que o programa do notebook é reiniciado. O celular, então, não consegue reconectar sozinho: é preciso abrir a URL nova. Uma reconexão sem reiniciar o programa (queda de Wi-Fi, por exemplo) funciona normalmente. Para testes existe a opção `--token`, que fixa o token.

## 4. Evolução

Fases futuras podem acrescentar campos (outros landmarks, `gesture`) sem quebrar a v0. Se uma mudança quebrar a compatibilidade, `v` é incrementado e a mudança é registrada em `decisions.md`.
