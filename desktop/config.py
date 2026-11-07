"""Configurações centrais do notebook.

Valores importantes ficam aqui, e não espalhados pelo código (CLAUDE.md §4.3).
Os números são pontos de partida para teste, não metas validadas
(PROJECT_CONTEXT.md §17).
"""

from pathlib import Path

# --- Caminhos ----------------------------------------------------------------

#: Raiz do repositório (pasta que contém desktop/, mobile/, docs/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Página e scripts servidos ao celular.
MOBILE_DIR = PROJECT_ROOT / "mobile"

#: Logs de sessão (JSON Lines) para medição. Ignorado pelo Git.
LOG_DIR = PROJECT_ROOT / "logs"

#: Anotações salvas de cada aula (etapa 6.3, D027): anotacoes/aula-AAAAMMDD-HHMMSS.json e .pdf.
ANNOTATIONS_DIR = PROJECT_ROOT / "anotacoes"
#: Preferências que valem entre aulas: posição da sidebar e estilo do pincel (D031).
PREFS_PATH = PROJECT_ROOT / "preferencias.json"
#: Calibração guardada para a próxima aula (D034).
CALIBRATION_PATH = PROJECT_ROOT / "calibracao.json"
#: Intervalo mínimo entre dois salvamentos automáticos (s).
ANNOTATIONS_AUTOSAVE_S = 2.0

#: Certificado e chave gerados localmente (D004). Ignorado pelo Git.
CERT_DIR = PROJECT_ROOT / "certs"

#: Pastas do macOS protegidas por privacidade. Dentro delas o Qt não consegue
#: listar os próprios plugins e a janela não abre (D011).
MACOS_PROTECTED_FOLDERS = ("Desktop", "Documents", "Downloads")

# --- Protocolo (docs/communication-protocol.md) -----------------------------

#: Versão do protocolo celular ↔ notebook.
PROTOCOL_VERSION = 0

#: Tamanho máximo de uma mensagem recebida, em bytes. Uma mensagem
#: hand_tracking típica tem poucas centenas de bytes.
MAX_MESSAGE_BYTES = 4096

#: Taxa máxima de mensagens hand_tracking anunciada ao celular (msg/s).
MAX_TRACKING_RATE_HZ = 30

#: Tamanho máximo de um quadro de câmera binário (cabeçalho + JPEG), em bytes
#: (D013). Um JPEG de 640 px com qualidade 0,7 costuma ter 30–80 KB.
MAX_FRAME_BYTES = 512 * 1024

# --- Visão computacional no notebook (D013) ---------------------------------

#: Modelo do MediaPipe Hand Landmarker. É o mesmo arquivo servido ao celular.
HAND_MODEL_PATH = MOBILE_DIR / "vendor" / "models" / "hand_landmarker.task"

#: Até 2 mãos: com as duas visíveis, o sistema escolhe a que está junto à
#: lousa (hand_selection.py, pedido do usuário em 2026-11-06).
MAX_HANDS = 2

#: Troca de mão só quando a outra é claramente melhor (estabilidade do cursor):
#: - distância à área da lousa menor por mais que isto (surface_norm);
HAND_SWITCH_BOARD_MARGIN = 0.05
#: - ou, com as duas sobre a lousa, palma aparente menor por mais que esta fração.
HAND_SWITCH_SIZE_MARGIN = 0.2
#: Distância (camera_norm) para considerar que é "a mesma mão" do quadro anterior.
HAND_SAME_MAX_DIST = 0.08

#: Limiares do MediaPipe (iguais aos do celular, mobile/scripts/hand_tracking.js).
MIN_HAND_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

#: Intervalo do resumo de desempenho da visão computacional (s).
VISION_STATS_INTERVAL_S = 1.0

# --- Calibração (Fase 2, D014, docs/calibration.md) -------------------------

#: Contagem regressiva por alvo (s). Definido pelo usuário em 2026-11-06;
#: a ajustar depois dos testes.
CALIBRATION_COUNTDOWN_S = 7.0

#: Últimos segundos da contagem em que a posição do dedo é coletada.
CALIBRATION_COLLECT_S = 0.5

#: Fração mínima dos quadros da coleta com a mão detectada.
CALIBRATION_MIN_PRESENCE = 0.7

#: Dispersão máxima da ponta do dedo durante a coleta (camera_norm, percentil 80).
#: 0,015 ≈ 10 px num quadro de 640 px.
CALIBRATION_MAX_SPREAD = 0.015

#: Erro máximo aceito no alvo de verificação (distância em surface_norm).
#: Acima disso a calibração é refeita em vez de aceita.
CALIBRATION_MAX_VERIFY_ERROR = 0.05

#: Distância dos alvos à borda da projeção (fração do lado). Aprovado: 5%.
CALIBRATION_TARGET_MARGIN = 0.05

# --- Calibração automática pelos marcadores (D034) ------------------------------

#: Ao abrir: perspectiva pelos marcadores + 1 toque no centro (ou a da última aula,
#: se o celular não mudou de lugar). Sem marcadores, os 4 cantos.
CALIB_AUTO = True
#: Segundos procurando os marcadores (depois de o celular conectar) antes de pedir os cantos.
CALIB_AUTO_WAIT_S = 20.0  # 6 s não bastou no 1º teste real: o celular ainda estava sendo posicionado
#: Leituras seguidas dos marcadores que precisam concordar antes de usar.
CALIB_AUTO_READINGS = 3
#: Maior deslocamento aceito entre o dedo e o alvo no toque do centro (fração da tela).
#: Mais que isso não é a ponta do dedo: algo está errado e a calibração vai para os cantos.
CALIB_AUTO_MAX_OFFSET = 0.06
#: Reaproveitar a calibração anterior se os marcadores estão no mesmo lugar na câmera
#: (maior diferença por canto, fração da imagem).
CALIB_REUSE_TOLERANCE = 0.008

# --- Marcadores ArUco (D015) ------------------------------------------------

#: Lado do marcador, como fração do menor lado da lousa. 0,12 ≈ 130 px numa
#: tela de 1080 px. Menor que isso a câmera pode não ler (a medir).
MARKER_SIZE_FRAC = 0.12

#: Margem branca em volta do marcador (fração do lado do marcador). O ArUco
#: precisa de ~1 célula de margem (1/6 do lado, 4x4 + borda); 0,17 cobre isso.
#: Em simulação (19–26 px de lado, JPEG, perspectiva) a detecção ficou igual
#: à de 0,25 e a área ocupada caiu ~20% (D028).
MARKER_QUIET_FRAC = 0.17

#: Esconder os marcadores depois que a referência é registrada (D028). Eles
#: voltam na calibração, nos testes G/V, no assistente e com a tecla N.
MARKERS_HIDE_AFTER_CALIBRATION = True

#: Segundos que os marcadores continuam na tela depois da referência ok.
MARKER_HIDE_DELAY_S = 1.0

# --- Celular mexido com os marcadores escondidos (D030) -------------------------

#: Liga a vigilância da cena: o celular mexeu → os marcadores voltam sozinhos.
SCENE_MOTION_ENABLED = True
#: Largura (px) da imagem reduzida comparada com a referência.
SCENE_MOTION_WIDTH = 160
#: A lousa (onde o slide muda) é excluída, crescida desta fração em volta.
SCENE_MASK_MARGIN = 0.08
#: Fração mínima da imagem fora da lousa para excluí-la (senão usa a imagem toda).
SCENE_MIN_MASK = 0.15
#: Textura mínima (gradiente médio, níveis de cinza) fora da lousa para excluí-la.
SCENE_MIN_TEXTURE = 2.0
#: Deslocamento da cena (fração da imagem) que conta como celular mexido.
SCENE_MOVED_SHIFT = 0.008
#: Nitidez mínima do pico da correlação para confiar na medida.
SCENE_MIN_RESPONSE = 0.08
#: Medidas seguidas (a cada 3 quadros) acima do limite e concordando entre si.
#: Uma pessoa passando muda a medida a cada quadro; o celular mexido a mantém.
SCENE_MOVED_CONFIRMATIONS = 3
#: Quanto as medidas seguidas podem discordar (fração da imagem).
SCENE_AGREE = 0.006
#: Com os marcadores de volta: leituras boas seguidas para considerar o celular parado.
SCENE_SETTLE_CHECKS = 6
#: Tempo mínimo com os marcadores de volta antes de escondê-los de novo (s).
SCENE_SETTLE_MIN_S = 1.0

#: Distância da margem branca até a borda da lousa (fração do menor lado).
MARKER_EDGE_PAD_FRAC = 0.01

#: Mínimo de marcadores visíveis para recalcular a perspectiva. Com só 2,
#: eles precisam estar em cantos opostos (2 do mesmo lado definem mal a
#: perspectiva: observado no teste real de 2026-11-06 19:24).
MARKER_MIN_VISIBLE = 2

#: Mínimo de marcadores para tomar a referência logo após a calibração.
MARKER_REFERENCE_MIN_VISIBLE = 3

#: Diferença (camera_norm) até a qual uma nova leitura é só ajuste fino e
#: entra direto. Acima disso é um salto: só é aceito depois de
#: MARKER_JUMP_CONFIRMATIONS leituras seguidas que concordam entre si.
MARKER_STABLE_DELTA = 0.02
MARKER_JUMP_CONFIRMATIONS = 3

#: Intervalo mínimo entre registros "camera_moved" no log (s).
CAMERA_MOVED_LOG_INTERVAL_S = 1.0

#: Procurar marcadores a cada N quadros processados (a câmera raramente se move).
MARKER_DETECT_EVERY_N = 3

#: Suavização dos cantos detectados (0–1; maior = responde mais rápido).
MARKER_SMOOTHING = 0.5

#: Deslocamento de um canto (camera_norm) a partir do qual é movimento, não ruído.
MARKER_JUMP = 0.01

#: Tempo para ver os marcadores depois da calibração e guardar a referência (s).
MARKER_REFERENCE_TIMEOUT_S = 3.0

#: Deslocamento da câmera (camera_norm) a partir do qual o log registra "câmera movida".
CAMERA_MOVED_THRESHOLD = 0.01

# --- Pose da mão e caneta (Fase 4, D018) -------------------------------------

#: Dedo "esticado" quando a ponta está mais longe do pulso que a articulação
#: do meio (PIP) por esta razão; "dobrado" abaixo de FINGER_CURLED_RATIO.
FINGER_EXTENDED_RATIO = 1.15
FINGER_CURLED_RATIO = 1.05

#: Quadros seguidos para baixar a caneta (pose de apontar) e para levantá-la
#: (outra pose ou mão perdida). Evita traço quebrado por um quadro ruim.
PEN_DOWN_FRAMES = 2
PEN_UP_FRAMES = 3

# --- Precisão: correção pelos 9 pontos, filtro One Euro, malha virtual ----------

#: Correção residual (docs/calibration.md §10): o teste G mede o erro nos 9 pontos
#: e a correção passa a compensá-lo. Ignorada se algum ponto errar mais que isto
#: (fração da superfície): seria uma medida ruim, não um erro sistemático.
RESIDUAL_MAX_ERROR = 0.05

#: Filtro One Euro no dedo (camera_norm). Menor min_cutoff = mais estável parado;
#: maior beta = menos atraso em movimentos rápidos. Simulação (30 Hz, ruído de
#: 0,002): tremor parado 0,0020 → 0,0008; atraso na escrita (0,5/s) 0,004;
#: um salto assenta em 2 quadros. Ajustar com testes reais.
ONE_EURO_ENABLED = True
ONE_EURO_MIN_CUTOFF_HZ = 1.0
ONE_EURO_BETA = 30.0
ONE_EURO_D_CUTOFF_HZ = 1.0

#: Malha virtual sobre a lousa (tecla M): colunas; as linhas acompanham a
#: proporção da tela para as células ficarem quadradas.
GRID_COLUMNS = 20
GRID_MAJOR_EVERY = 5

# --- Gestos de movimento (D024, desktop/interaction/motions.py) -----------------
# Valores do open-source-hands (MIT, src/kit/motions.ts), em coordenadas da lousa.

#: Liga os gestos de movimento (tecla H alterna durante o uso).
MOTIONS_ENABLED = True
MOTION_HISTORY_S = 2.0
#: Mesmo gesto não dispara de novo antes disto (s).
MOTION_COOLDOWN_S = 0.65
#: Deslizar: percorrer SWIPE_DISTANCE da largura da lousa em SWIPE_WINDOW_S, com o eixo
#: horizontal SWIPE_AXIS_RATIO vezes maior que o vertical, com a mão aberta.
SWIPE_DISTANCE = 0.20
SWIPE_WINDOW_S = 0.38
SWIPE_AXIS_RATIO = 1.8
#: Toque de pinça: fechar (distância < TAP_CLOSE_GAP) e abrir (> TAP_OPEN_GAP) em até
#: TAP_MAX_S, sem a mão fechada no meio. Gravação real de 2026-11-07 12:22: pela força
#: da pinça do kit, fechar a mão gerou 11 toques falsos; com estas regras, 0.
TAP_MAX_S = 0.35
TAP_CLOSE_GAP = 0.18
TAP_OPEN_GAP = 0.33
#: A pinça precisa aparecer fechada em pelo menos este número de quadros. Gravação real
#: de 2026-11-07 13:35: falhas de 1 quadro do rastreamento (polegar "colado" no indicador
#: no meio de um apontar) geravam 17 toques falsos; com 2 quadros, 0.
TAP_MIN_CLOSED_FRAMES = 2

#: Caminho da gravação dos pontos da mão (--record); None = não grava.
RECORD_LANDMARKS_PATH: str | None = None

# --- Laboratório de gestos (tecla L, desktop/interaction/gesture_lab.py) --------
LAB_PROMPT_S = 5.0  # tempo de cada gesto pedido
LAB_SETTLE_S = 1.0  # o acerto só conta depois disto (tempo para trocar a mão)
LAB_SUMMARY_S = 25.0

# --- Assistente de calibração (desktop/calibration/guided.py) -------------------

#: Cartão com a instrução antes de cada etapa e resumo final (s).
GUIDED_INTRO_S = 5.0
GUIDED_SUMMARY_S = 12.0

# --- Esqueleto da mão na janela da câmera (D036) ---------------------------------

#: A imagem do celular chega espelhada? A câmera traseira não espelha; a frontal, sim.
#: O MediaPipe nomeia a mão supondo imagem espelhada, então isso decide palma × dorso.
CAMERA_MIRRORED = False
#: Abaixo disto (|produto vetorial| ÷ palma²) a mão está de lado: nem palma nem dorso.
HAND_SIDE_EDGE = 0.25

# --- Estudo do toque (etapa 5.3, tecla T) ---------------------------------------

#: Rodadas (cada uma: encostado/no ar, parado/arrastando, em outro lugar da lousa).
TOUCH_STUDY_ROUNDS = 3
#: Segundos para posicionar a mão antes de cada gravação.
TOUCH_STUDY_PREPARE_S = 3.0
#: Segundos gravados por etapa.
TOUCH_STUDY_RECORD_S = 5.0
#: Segundos do cartão final.
TOUCH_STUDY_SUMMARY_S = 20.0
#: Segundos descartados no início de cada etapa no relatório (a mão ainda se acomoda).
TOUCH_STUDY_SETTLE_S = 0.8

# --- Reconhecimento de poses com nota e histerese (D022, desktop/vision/gestures.py) ----
# Valores do open-source-hands (MIT, src/kit/engine.ts), salvo indicação.

#: "kit" = reconhecimento novo (D022); "legacy" = razões de distância (D018).
#: O outro é calculado em paralelo nos mesmos quadros, para comparar no log.
GESTURE_ENGINE = "kit"

#: Filtro One Euro nos 63 valores da mão antes de medir a forma.
GESTURE_FILTER_MIN_CUTOFF_HZ = 2.2
GESTURE_FILTER_BETA = 8.0
GESTURE_FILTER_D_CUTOFF_HZ = 1.0

#: A pose entra com nota ≥ ENTER e só sai abaixo de EXIT; outra pose só toma o
#: lugar se passar a atual por MARGIN; a troca precisa durar DEBOUNCE (×1,6
#: para "nenhuma pose"). Mão sumida por mais de LOST encerra a pose.
GESTURE_ENTER = 0.62
GESTURE_EXIT = 0.42
GESTURE_MARGIN = 0.08
GESTURE_DEBOUNCE_S = 0.070
GESTURE_LOST_S = 0.25

# --- Desenho (Fase 4, docs/drawing.md) -----------------------------------------

#: Como a caneta desce (D021): "pose" = só o indicador esticado (D018);
#: "pinch" = pinça, ponta do polegar encostada na ponta do indicador (como no
#: projeto ECE 445 da Univ. de Illinois). A tecla K alterna durante o uso.
PEN_MODE = "pose"

#: Pinça: distância polegar↔indicador ÷ tamanho da palma. Abaixo de ON a
#: caneta desce; só sobe acima de OFF (histerese contra oscilação).
#: Com o reconhecimento novo (D022) a distância vem dos pontos 3D do mundo.
#: Ajustado com a gravação real de 2026-11-07 12:22 (5 min, nenhuma pinça feita):
#: 0,30/0,42 → caneta descida sem querer 13,5% do tempo (mão fechando parece pinça);
#: 0,15/0,30 + nunca com a mão fechada → 0,6%. Pinça de verdade ≈ 0,09.
PINCH_ON_RATIO = 0.15
PINCH_OFF_RATIO = 0.30

#: Cores do pincel (RF20, escolha do usuário em 2026-11-06: 5 cores). A primeira é a padrão.
BRUSH_COLORS = (
    ("Vermelho", "#e63946"),
    ("Azul", "#1e6fd9"),
    ("Verde", "#2a9d4f"),
    ("Amarelo", "#f4c20d"),
    ("Preto", "#111111"),
)

#: Espessuras do pincel (fração da altura da lousa): fino, médio, grosso. Padrão: médio.
BRUSH_WIDTHS_FRAC = (0.004, 0.007, 0.012)
BRUSH_WIDTH_LABELS = ("Fino", "Médio", "Grosso")

#: Raios da borracha (fração da altura da lousa), RF21. Padrão: média.
ERASER_RADII_FRAC = (0.02, 0.035, 0.06)
ERASER_LABELS = ("Pequena", "Média", "Grande")

#: O painel de estilo fecha quando o dedo fica este tempo fora dele e da sidebar (s).
STYLE_PANEL_AWAY_S = 1.0

#: Botões do painel de estilo, relativos ao botão da sidebar.
STYLE_BUTTON_SCALE = 0.85

#: Distância entre pontos guardados de um traço (fração da altura): o traço é
#: reamostrado para a borracha apagar trechos sem buracos.
STROKE_SPACING_FRAC = 0.004

#: Suavização da posição do dedo durante o traço (0–1; maior = segue mais rápido).
STROKE_SMOOTHING = 0.5

#: Tamanho mínimo de círculo/retângulo para ser criado (fração da altura).
SHAPE_MIN_FRAC = 0.01

# --- Formas desenhadas à mão viram formas perfeitas (D033) ---------------------

#: Liga o reconhecimento de formas no Pincel (círculo, retângulo, linha reta).
SHAPE_SNAP_ENABLED = True
#: Tamanho mínimo do traço para tentar reconhecer (fração do menor lado da lousa).
SNAP_MIN_FRAC = 0.06
#: Traço "fechado": fim perto do início (fração do comprimento do traço).
SNAP_CLOSED_GAP = 0.18
#: Erro médio aceito (fração do tamanho da forma). Menor = só formas bem feitas.
SNAP_LINE_ERROR = 0.035
SNAP_CIRCLE_ERROR = 0.09
SNAP_RECT_ERROR = 0.045
#: Linha: o traço não pode ser muito mais comprido que a reta (ida e volta = rabisco).
SNAP_LINE_MAX_DETOUR = 1.15
#: Retângulo: o traço passa a menos desta fração da diagonal de cada canto.
SNAP_RECT_CORNER = 0.12

#: Círculo/retângulo: a caneta precisa ficar levantada por este tempo para a
#: forma ser concluída. Se descer antes, continua a mesma forma (oscilação da pose).
SHAPE_RELEASE_S = 0.35

#: Selecionar: distância máxima do dedo até um desenho para pegá-lo (fração da altura).
SELECT_RADIUS_FRAC = 0.03

#: Selecionar → redimensionar (etapa 4.6): depois de soltar o desenho, abrir ou
#: fechar a mão muda o tamanho. A abertura de referência é medida depois de a
#: mão assentar; o tamanho se confirma com a abertura parada por RESIZE_HOLD_S.
RESIZE_SETTLE_S = 0.3
RESIZE_HOLD_S = 1.0
RESIZE_STILL_TOLERANCE = 0.06  # variação de abertura considerada "parada"
RESIZE_GAIN = 1.5  # escala = (abertura / referência) ^ ganho
RESIZE_SMOOTHING = 0.3  # suavização da abertura (0–1; maior = segue mais rápido)
RESIZE_MIN_SCALE, RESIZE_MAX_SCALE = 0.2, 5.0
#: O que muda o tamanho com o Selecionar (D035): "size" = tamanho da mão visto pela
#: câmera (aproximar a mão da câmera amplia, aproximar da lousa reduz); "openness" =
#: abrir/fechar a mão (comportamento anterior, D-4.6).
RESIZE_SIGNAL = "size"
#: Com "size": escala = (tamanho da mão ÷ tamanho de referência) ^ ganho.
RESIZE_SIZE_GAIN = 1.8  # 1º teste real: a palma variou só 28 → 40 px (1,45×); com 1,8 isso dá ~1,9×
#: Com "size": variação da palma ignorada (fração). No 1º teste real, só mover já mudava
#: o tamanho em ±5% por causa do ruído da palma.
RESIZE_SIZE_DEADZONE = 0.08
#: Com "size": variação relativa do tamanho da mão considerada "parada".
RESIZE_SIZE_STILL_TOLERANCE = 0.05
#: Com "size": a palma de referência é medida este tempo depois de pegar o desenho
#: (o dedo ainda está descendo sobre ele).
SELECT_PALM_SETTLE_S = 0.15

#: Duração do rastro do ponteiro (s).
POINTER_TRAIL_S = 0.6

#: Tempo que a confirmação de "Limpar" fica na tela esperando resposta (s).
CLEAR_CONFIRM_S = 8.0

# --- Interface da lousa (Fase 3, docs/interface-guidelines.md) ---------------

#: Tempo de permanência do dedo sobre um botão para acioná-lo (s). Aprovado
#: 0,8 s; reduzido para 0,6 s após o 1º teste (usuário, 2026-11-06 21:29).
DWELL_S = 0.6

#: Oscilação tolerada sem zerar a permanência: o dedo pode sair até esta
#: distância (fração da largura da lousa) do botão.
DWELL_TOLERANCE_FRAC = 0.015

#: Diâmetro dos botões (fração da altura da lousa). 3 × erro máximo do teste G
#: (26 px em 1080 px) ≈ 80 px ≈ 7,4%.
SIDEBAR_BUTTON_FRAC = 0.074

#: Duração da animação de abrir e recolher (s).
SIDEBAR_ANIMATION_S = 0.2

#: Durante o arrasto da barra, perder o dedo por este tempo solta a barra (s).
SIDEBAR_DROP_LOST_S = 1.5

#: Opacidade do painel e do botão circular (0–255).
SIDEBAR_PANEL_ALPHA = 175
SIDEBAR_HANDLE_ALPHA = 120

# --- Servidor (D003) ---------------------------------------------------------

#: Porta HTTPS/WSS. Acima de 1024 para não exigir privilégio de administrador.
SERVER_PORT = 8443

#: Endereço em que o servidor escuta. 0.0.0.0 = todas as interfaces IPv4,
#: necessário para o celular alcançar o notebook pela rede local.
BIND_HOST = "0.0.0.0"

#: Tempo para o celular enviar `hello` depois de abrir o WebSocket (s).
HELLO_TIMEOUT_S = 5.0

#: Mensagens inválidas toleradas por conexão antes de fechá-la.
MAX_INVALID_MESSAGES = 20

#: Intervalo do ping de aplicação enviado pelo notebook para medir RTT (s).
PING_INTERVAL_S = 2.0

#: Heartbeat do WebSocket (aiohttp): detecta conexão morta sem esperar o TCP (s).
WS_HEARTBEAT_S = 5.0

#: Código de fechamento do WebSocket quando outro aparelho assume a conexão.
#: Faixa 4000–4999 é reservada para uso da aplicação (RFC 6455). O celular que
#: recebe este código NÃO reconecta sozinho, para dois aparelhos não ficarem
#: se derrubando em ciclo.
WS_CLOSE_REPLACED = 4000

#: Comprimento do token de sessão em bytes aleatórios (D007).
SESSION_TOKEN_BYTES = 16

# --- Certificado (D004) ------------------------------------------------------

#: Validade do certificado autoassinado (dias).
CERT_VALID_DAYS = 365

#: Regenera o certificado se faltar menos que isso para expirar (dias).
CERT_RENEW_BEFORE_DAYS = 30
