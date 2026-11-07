# Roteiro de desenvolvimento

Status de cada fase. Uma fase só muda para "Validada" depois de cumprir a Definição de Concluído (`CLAUDE.md` §18).

| Fase | Objetivo | Status |
|---|---|---|
| 1 | Prova de conceito de rastreamento (celular → WebSocket → cursor no notebook) | Validada no Mac; falta Windows (1.7) |
| 2 | Calibração espacial (homografia por 4 pontos) | Validada no Mac (2.1–2.4, 2.6); falta 2.5 (ângulos e paralaxe) |
| 3 | Interface da lousa (overlay, sidebar, botão circular) | Validada no Mac (overlay sobre o navegador) |
| 4 | Ferramentas de desenho | Validada no Mac (4.1–4.6); comparação pinça × indicador pendente |
| 5 | Reconhecimento de interações (gestos → comandos; toque na superfície) | Em andamento: 5.1–5.2 testadas (pytest); 5.3 instrumento pronto (tecla T), coleta real pendente (`gesture-system.md`) |
| 6 | Integração com apresentações (troca de slides) | 6.1 validada no Mac; 6.2–6.4 a fazer/testar |
| 7 | Testes em ambiente real (sala de aula) | Pronta para começar: roteiro em `field-test.md` (D031) |

Detalhes de cada fase: `PROJECT_CONTEXT.md` §16. Arquitetura da Fase 1: `docs/architecture.md`.

---

## Plano de implementação da Fase 1

Cada etapa é pequena, tem critério de aceitação próprio e só começa depois que a anterior foi validada (`CLAUDE.md` §4.1). As etapas que dependem de equipamento real estão marcadas com 📱.

### 1.0 — Preparação do ambiente ✅ concluída no Mac em 2026-11-06
- Rodar `scripts/check_env.sh` e registrar o resultado em `docs/environment.md`.
- Criar `.venv`, instalar `aiohttp`, `cryptography`, `PySide6`, `pytest` e fixar as versões em `requirements.txt`.
- Baixar o MediaPipe (versão fixada) e o modelo para `mobile/vendor/` e registrar a versão na D006.

**Aceite:** `python -c "import aiohttp, cryptography, PySide6"` sem erro, e os arquivos de `mobile/vendor/` presentes.

### 1.1 — Protocolo e validação (sem rede) ✅ concluída em 2026-11-06 (60 testes passando no Mac/3.11)
- `desktop/communication/message_protocol.py` implementa o esquema de `docs/communication-protocol.md`.
- `tests/test_message_protocol.py` cobre mensagens válidas, campos ausentes, valores fora de [0,1], `seq` antigo e tipo desconhecido.

**Aceite:** `pytest` passa.

### 1.2 — Servidor HTTPS + WSS com página de teste 📱 ✅ concluída em 2026-11-06 (moto g54 5G + Chrome 156; ver `testing.md`). Correção do ciclo entre dois aparelhos a confirmar no próximo teste real.
- `tls.py` gera o certificado com o IP local, `server.py` serve uma página mínima e `/ws` com token, e o `ping/pong` funciona.
- `tests/test_server.py` cobre: 403 sem token, `hello` → `welcome`, mensagem inválida → `error`.
- **Teste real:** abrir a URL no celular, aceitar o certificado e confirmar o estado "Conectado" com RTT exibido.
- Verificar os riscos **R1** (WSS no iOS) e **R3** (isolamento de clientes) e registrar o resultado.

**Aceite:** testes automatizados passando e conexão real confirmada em pelo menos um celular.

### 1.3 — Janela do cursor + simulador ✅ concluída em 2026-11-06 (114 testes no Mac; janela validada com o simulador e com o Android)
- `cursor_window.py` (PySide6) desenha o cursor e o painel de status (conexão, msg/s, RTT).
- `coordinate_mapper.py` faz o mapeamento provisório `camera_norm → ui_px`, testado em `tests/test_coordinate_mapper.py`.
- `tools/fake_phone.py` envia um movimento circular simulado.

**Aceite:** com o simulador, o cursor percorre a trajetória esperada e os testes passam. *(Simulação: isso não valida a Fase 1.)*

### 1.4 — Câmera + MediaPipe no celular 📱 ✅ concluída em 2026-11-06 (moto g54: ponta do indicador detectada; ~11 FPS na GPU, D012)
- `camera.js` (câmera traseira), `hand_tracking.js` (landmark 8, `numHands: 1`, modo VIDEO), pré-visualização com o ponto do indicador desenhado.
- FPS e tempo de inferência exibidos na tela do celular. Testar a Screen Wake Lock (R6).

**Aceite:** com a mão diante da câmera, o ponto acompanha o indicador na tela do próprio celular. FPS medido e registrado.

### 1.5 — Integração ponta a ponta 📱 ✅ validada no moto g54 + MacBook Air + TV Toshiba por HDMI (2026-11-06). O cursor acompanha o dedo; captura → resultado em 77 ms; ver `testing.md`
Replanejada pela **D013**: o celular envia quadros JPEG e o notebook roda o MediaPipe.

- **Notebook:**
  - quadros binários no servidor (`frame_protocol.py`);
  - thread de visão com vaga única (`vision/frame_processor.py`);
  - MediaPipe Python (`vision/hand_tracker.py`);
  - métricas `vision` no log.
- **Celular:** `frame_sender.js` (JPEG com lado maior de 640 px e qualidade 0,7, com contrapressão). O modo `&mode=local` agora também envia `hand_tracking`.
- **Lousa de desenvolvimento:** Smart TV como 2ª tela do Mac, com a janela em tela cheia via `--screen N`. Tecla P esconde o painel.
- **Feito:** 162 testes automatizados. Ensaio com o Chrome sem tela e câmera falsa: 19,5 q/s, mão em 100% dos quadros, nenhum descarte. Ver `testing.md`.

**Aceite (critério da Fase 1):** ao mover o indicador diante da câmera do celular, o cursor acompanha o movimento na TV em tempo real. A conferência usa o log (`tools.log_summary`) com o moto g54 no Mac.

### 1.6 — Medição e robustez 📱
- Medir as métricas de `docs/architecture.md` §6 e registrá-las em `docs/testing.md` (aparelho, rede, iluminação, data).
- Testar a queda e a volta do Wi-Fi e o fechamento e reabertura da página no celular.
- Registrar limitações encontradas.

**Aceite:** `docs/testing.md` preenchido com medições reais no macOS + Android.

### 1.7 — Validação no notebook Windows do professor 📱
- Rodar `scripts/check_env.ps1` e registrar o resultado em `docs/environment.md`.
- Instalar o ambiente com o mesmo `requirements.txt` (versões fixadas na 1.0).
- Repetir os testes da 1.2 (conexão, certificado, firewall do Windows) e da 1.5 (cursor ponta a ponta) com o mesmo Android.
- Repetir as medições da 1.6 e comparar com o macOS.
- Verificar a escala de tela (DPI) da janela do cursor e o IP correto quando houver mais de uma placa de rede.

**Aceite:** critério da Fase 1 atingido também no Windows, com as medições registradas em `docs/testing.md`. Só então a Fase 1 é marcada como **Validada** e a Fase 2 é liberada.

---

## Situação da Fase 1 (2026-11-06)

- **Critério de sucesso atingido no Mac**: o cursor acompanha o indicador, a ~23 q/s.
- **Etapa 1.6** (medições): feita em grande parte, com taxa, latência por trecho e o Modo Jogo da TV. Faltam testes de queda de Wi-Fi.
- **Etapa 1.7** (Windows do professor): **pendente**, até haver acesso ao notebook. Com a aprovação do usuário, a Fase 2 começou no Mac sem esperar por ela.

## Fase 2 — Calibração espacial (plano em `calibration.md`, decisão D014)

### 2.0 — JPEG em Web Worker 🔶 implementado (cliente 0.4.0); falta medir no celular
- O padrão passa a ser o worker; `&enc=main` gera na página, para comparar.
- O log registra o codificador (coluna JPEG do `log_summary`).
- Simulação: worker 10 ms e 30 q/s; página 7 ms e 24 q/s. Não vale para o celular.

### 2.1 — Núcleo da calibração ✅ testado (pytest)
- `desktop/calibration/`: homografia com validação dos 4 pontos, coleta pela mediana com aceite ou rejeição, e máquina de estados (7 s por canto, ordem SE → IE → ID → SD, verificação no centro).

### 2.2/2.3 — Calibração na lousa + cursor calibrado ✅ 2º teste real: erro de 4,6 px no centro (0,24%), em 42 s
- A calibração começa ao abrir o programa; tecla C recalibra e Esc cancela.
- Depois dela, o cursor passa pela homografia e some fora da área projetada.
- O log grava `calibration_*`.

### 2.4 — Grade de 9 pontos ✅ 2º teste real: mediana 0,42%, máximo 1,37% (2026-11-06)
### 2.6 — Marcadores ArUco: correção do movimento da câmera (D015) 🔶 implementado; testado com câmera sintética e com a janela real desenhada pelo Qt; falta o teste real
### 2.7 — Correção dos 9 pontos, filtro One Euro e malha virtual (D020) 🔶 em uso no Mac; ganho a medir com G + V
### 2.8 — Verificação entre os pontos (tecla V) 🔶 testado (pytest); 📱 teste real pendente
### 2.9 — Assistente de calibração ao abrir: cantos → V → G → V (D023) 🔶 testado (pytest); 📱 teste real pendente
### 2.5 — Ângulos (frente, ~30°, ~45°) e paralaxe (dedo encostado, ~2 cm, ~5 cm) — a fazer

## Fase 3 — Interface da lousa (plano em `interface-guidelines.md`, aprovado: permanência 0,8 s, botão à esquerda)

### 3.0 — Viabilidade do overlay ✅ por cima do navegador em tela cheia no Mac (D017); Windows na 1.7
### 3.1–3.4 — Lousa como overlay, permanência, sidebar e arrasto ✅ testados com o dedo e o mouse no Mac (2026-11-06)
### 3.5 — Testes de uso ✅ permanência ajustada para 0,6 s; botões de 80 px aprovados

## Fase 4 — Ferramentas de desenho (plano em `drawing.md`, decisão D018)

### 4.1 — Pose da mão e caneta ✅ testado (pytest): só o indicador esticado escreve
### 4.2 — Motor de desenho (traço, círculo, retângulo, borracha, voltar/avançar, limpar) ✅ testado (pytest)
### 4.3 — Integração na lousa (prévia das formas, rastro do ponteiro, "Limpar tudo?") ✅ testado com a mão (2026-11-06 22:25): uma forma por seleção
### 4.4 — Cor, espessura e tamanho da borracha (RF20/RF21) 🔶 implementado e testado (pytest); 📱 teste real pendente. Aprovado: 5 cores, 3 tamanhos, painel ao lado da sidebar
### 4.5 — Selecionar e mover anotações ✅ validado no Mac (2026-11-06 22:54, 21 arrastos)
### 4.6 — Redimensionar com a abertura da mão (Selecionar) ✅ validado no Mac (2026-11-07 00:19)

## Fase 6 — Integração com apresentações (decisão D019)

### 6.1 — Troca de slides pela sidebar e anotações por slide ✅ validada no Mac com o navegador (2026-11-06 23:44)
### 6.4 — Abrir com dois cliques + QR code para o celular (D025) 🔶 testado (pytest); 📱 teste real pendente; Windows não testado
### 6.2 — Testar com PowerPoint, Keynote e Impress em tela cheia — a fazer
### 6.3 — Guardar (automático), recuperar (O) e exportar PDF (E) as anotações (D027) 🔶 testado (pytest); 📱 teste real pendente

## Fora do escopo da Fase 1

Calibração/homografia, filtros de suavização, gestos, sidebar, ferramentas de desenho, overlay transparente sobre apresentações, empacotamento com PyInstaller e QR code de conexão.
