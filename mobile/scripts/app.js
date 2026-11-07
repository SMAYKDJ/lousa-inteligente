// SmartBoard Classroom — página do celular, etapa 1.5.
// Abre a câmera e conecta ao notebook. Dois modos (D013), escolhidos pela URL:
//   stream (padrão): envia quadros JPEG; o MediaPipe roda no notebook.
//   local (&mode=local): roda o MediaPipe aqui e envia só a ponta do
//   indicador (hand_tracking), como na etapa 1.4 (D002).

import { cameraAvailable, openRearCamera, CameraError } from "./camera.js";
import { FrameSender, MainThreadEncoder, WorkerEncoder } from "./frame_sender.js";
import { ConnState, SmartboardSocket, defaultSocketUrl } from "./websocket_client.js";

const CLIENT_VERSION = "0.4.0";
const STATUS_INTERVAL_MS = 1000;
const FPS_WINDOW_MS = 1000;

// Parâmetros de medição pela URL (etapa 1.4, risco R2), ex.: &res=480&delegate=CPU
// res: altura pedida à câmera (480, 720 ou 1080). delegate: GPU (padrão) ou CPU.
const params = new URLSearchParams(window.location.search);
const RESOLUTIONS = { 480: [640, 480], 720: [1280, 720], 1080: [1920, 1080] };
const [REQ_WIDTH, REQ_HEIGHT] = RESOLUTIONS[params.get("res")] ?? RESOLUTIONS[720];
const PREFERRED_DELEGATE = params.get("delegate")?.toUpperCase() === "CPU" ? "CPU" : "GPU";
// mode: stream (padrão) ou local. Modo stream: &side=640 (lado maior do JPEG),
// &q=0.7 (qualidade JPEG), &fps=30 (teto de envio).
const MODE = params.get("mode") === "local" ? "local" : "stream";
const numberParam = (name, fallback, min, max) => {
  const v = Number(params.get(name));
  return Number.isFinite(v) && v >= min && v <= max ? v : fallback;
};
const STREAM_OPTIONS = {
  maxSide: numberParam("side", 640, 160, 1920),
  quality: numberParam("q", 0.7, 0.3, 0.95),
  maxFps: numberParam("fps", 30, 1, 60),
};
// &enc=main: gera o JPEG na própria página (como até a 0.3.x), para comparar.
const ENCODER_PARAM = params.get("enc") === "main" ? "main" : "worker";

const FACING_LABELS = { environment: "traseira", user: "frontal", unknown: "orientação não informada" };
const CONN_LABELS = {
  [ConnState.DISCONNECTED]: "Desconectado",
  [ConnState.CONNECTING]: "Conectando…",
  [ConnState.CONNECTED]: "Conectado",
  [ConnState.RECONNECTING]: "Reconectando…",
  [ConnState.ERROR]: "Erro",
};

const ui = {
  secure: document.getElementById("secure"),
  camera: document.getElementById("camera"),
  conn: document.getElementById("conn"),
  connDetail: document.getElementById("conn-detail"),
  rtt: document.getElementById("rtt"),
  model: document.getElementById("model"),
  fps: document.getElementById("fps"),
  hand: document.getElementById("hand"),
  wake: document.getElementById("wake"),
  error: document.getElementById("error"),
  start: document.getElementById("start"),
  video: document.getElementById("preview"),
  overlay: document.getElementById("overlay"),
};

// Estado exposto para diagnóstico (inclusive testes automatizados da página).
const state = {
  mode: MODE,
  trackingState: "inactive", // inactive | initializing | tracking_active | tracking_lost
  fps: 0,
  inferenceMs: null,
  frames: 0,
  delegate: null,
  loadMs: null,
  tip: null,
  stream: null, // modo stream: resumo do FrameSender (fps, encodeMs, frameKb, skipped)
};
window.smartboard = state;

function showError(text) {
  ui.error.textContent = text;
  ui.error.hidden = !text;
}

function setText(el, text, cls) {
  el.textContent = text;
  if (cls !== undefined) el.className = cls;
}

// --- Tela sempre ligada (risco R6) ------------------------------------------

let wakeLock = null;
async function keepScreenOn() {
  if (!("wakeLock" in navigator)) {
    setText(ui.wake, "não suportado", "bad");
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    setText(ui.wake, "ativa", "ok");
    wakeLock.addEventListener("release", () => setText(ui.wake, "liberada", "wait"));
  } catch (err) {
    setText(ui.wake, `negada (${err.name})`, "bad");
  }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && wakeLock !== null) keepScreenOn();
});

// --- Desenho da mão sobre o vídeo -------------------------------------------

function drawHand(ctx, landmarks, HAND_CONNECTIONS, INDEX_TIP) {
  const { width: w, height: h } = ctx.canvas;
  ctx.clearRect(0, 0, w, h);
  if (!landmarks) return;

  ctx.lineWidth = Math.max(2, w / 240);
  ctx.strokeStyle = "rgba(60, 207, 142, 0.9)";
  for (const { start, end } of HAND_CONNECTIONS) {
    const a = landmarks[start], b = landmarks[end];
    ctx.beginPath();
    ctx.moveTo(a.x * w, a.y * h);
    ctx.lineTo(b.x * w, b.y * h);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(60, 207, 142, 1)";
  for (const p of landmarks) {
    ctx.beginPath();
    ctx.arc(p.x * w, p.y * h, Math.max(3, w / 180), 0, 2 * Math.PI);
    ctx.fill();
  }
  const tip = landmarks[INDEX_TIP];
  ctx.fillStyle = "rgba(255, 90, 95, 0.95)";
  ctx.beginPath();
  ctx.arc(tip.x * w, tip.y * h, Math.max(8, w / 50), 0, 2 * Math.PI);
  ctx.fill();
}

// --- Laço de rastreamento ---------------------------------------------------

function startTrackingLoop(tracker, socket, INDEX_TIP, HAND_CONNECTIONS) {
  const ctx = ui.overlay.getContext("2d");
  let windowStart = performance.now();
  let windowFrames = 0;
  let windowInferenceMs = 0;
  let handWasPresent = true; // começa true: o notebook recebe "sem mão" logo no início

  const step = () => {
    const frame = tracker.detect(ui.video);
    if (frame) {
      if (ui.overlay.width !== ui.video.videoWidth) {
        ui.overlay.width = ui.video.videoWidth;
        ui.overlay.height = ui.video.videoHeight;
      }
      state.frames += 1;
      windowFrames += 1;
      windowInferenceMs += frame.inferenceMs;
      state.tip = frame.hand?.tip ?? null;
      state.trackingState = frame.hand ? "tracking_active" : "tracking_lost";
      drawHand(ctx, frame.hand?.landmarks, HAND_CONNECTIONS, INDEX_TIP);
      // Sem mão: envia uma vez só ao perder o rastreamento (protocolo §2.3).
      if (frame.hand || handWasPresent) socket.send({
        type: "hand_tracking",
        seq: state.frames,
        t_client_ms: performance.now(),
        hand: frame.hand
          ? { present: true, handedness: frame.hand.handedness, confidence: frame.hand.confidence,
              index_tip: frame.hand.tip }
          : { present: false },
        inference_ms: Math.round(frame.inferenceMs * 10) / 10,
      });
      handWasPresent = Boolean(frame.hand);
      setText(ui.hand, frame.hand
        ? `x=${frame.hand.tip.x.toFixed(2)} y=${frame.hand.tip.y.toFixed(2)} (${(frame.hand.confidence * 100).toFixed(0)}%)`
        : "sem mão", frame.hand ? "ok" : "wait");
    }

    const now = performance.now();
    if (now - windowStart >= FPS_WINDOW_MS) {
      state.fps = (windowFrames * 1000) / (now - windowStart);
      // Média do tempo de inferência no último segundo (não só o último quadro).
      state.inferenceMs = windowFrames ? windowInferenceMs / windowFrames : null;
      windowStart = now;
      windowFrames = 0;
      windowInferenceMs = 0;
      setText(ui.fps, `${state.fps.toFixed(1)} FPS · ${state.inferenceMs?.toFixed(0) ?? "—"} ms/quadro`);
    }

    // requestVideoFrameCallback roda uma vez por frame novo da câmera;
    // requestAnimationFrame é o plano B em navegadores sem ele.
    if ("requestVideoFrameCallback" in ui.video) ui.video.requestVideoFrameCallback(step);
    else requestAnimationFrame(step);
  };
  step();
}

// --- Início -----------------------------------------------------------------

async function start() {
  ui.start.disabled = true;
  showError("");

  let camera;
  try {
    camera = await openRearCamera(ui.video, { width: REQ_WIDTH, height: REQ_HEIGHT });
  } catch (err) {
    showError(err instanceof CameraError ? err.message : String(err));
    ui.start.disabled = false;
    return;
  }
  setText(ui.camera, `${camera.width}×${camera.height} (${FACING_LABELS[camera.facing]})`);
  keepScreenOn();

  const socket = new SmartboardSocket({
    url: defaultSocketUrl(),
    buildHello: () => ({
      client: "mobile-web",
      client_version: CLIENT_VERSION,
      camera: { width: camera.width, height: camera.height, facing: camera.facing },
    }),
    onState: (connState, detail) => {
      setText(ui.conn, CONN_LABELS[connState] ?? connState,
        connState === ConnState.CONNECTED ? "ok" : connState === ConnState.ERROR ? "bad" : "wait");
      ui.connDetail.textContent = detail === "replaced" ? "" : detail ?? "";
      if (connState === ConnState.DISCONNECTED && detail === "replaced") {
        showError("Outro aparelho se conectou ao notebook e assumiu o controle. Toque em Reconectar para retomar por este celular.");
        ui.start.textContent = "Reconectar";
        ui.start.disabled = false;
        ui.start.onclick = () => {
          showError("");
          ui.start.disabled = true;
          socket.start();
        };
      }
    },
    onRtt: (ms) => setText(ui.rtt, `${ms.toFixed(1)} ms`),
    onServerError: (code, detail) => showError(`Notebook recusou uma mensagem: ${code} — ${detail}`),
  });
  socket.start();
  // Status a cada segundo, com as métricas que o notebook grava no log de sessão.
  setInterval(() => socket.send(buildStatus()), STATUS_INTERVAL_MS);

  if (MODE === "stream") await startStreaming(socket);
  else await startLocalTracking(socket);
}

const round1 = (v) => (v == null ? undefined : Math.round(v * 10) / 10);

function buildStatus() {
  if (MODE === "stream") {
    const s = state.stream;
    return {
      type: "status", mode: "stream", tracking_state: "inactive", encoder: state.encoder,
      fps: round1(s?.fps ?? 0), encode_ms: round1(s?.encodeMs), frame_kb: round1(s?.frameKb),
      skipped: s?.skipped,
    };
  }
  return {
    type: "status", mode: "local",
    fps: round1(state.fps),
    tracking_state: state.trackingState,
    inference_ms: round1(state.inferenceMs),
    load_ms: state.loadMs == null ? undefined : Math.round(state.loadMs),
    delegate: state.delegate ?? undefined,
  };
}

// --- Modo stream: o notebook detecta a mão (D013) -----------------------------

async function startStreaming(socket) {
  setText(ui.hand, "detectado no notebook (veja a tela da lousa)", "detail");
  // Worker por padrão; se o navegador não suportar, volta ao modo da página.
  const encoder = (ENCODER_PARAM === "worker" ? await WorkerEncoder.create() : null)
    ?? new MainThreadEncoder();
  state.encoder = encoder.name;
  setText(ui.model, `no notebook · JPEG: ${encoder.name === "worker" ? "worker" : "página"}`, "ok");
  const sender = new FrameSender({ video: ui.video, socket, encoder, ...STREAM_OPTIONS });
  sender.start();
  setInterval(() => {
    const s = sender.stats;
    state.stream = s;
    state.fps = s.fps;
    setText(ui.fps, socket.connected
      ? `enviando ${s.fps.toFixed(1)} q/s · ${s.width}×${s.height} · ${s.frameKb?.toFixed(0) ?? "—"} KB · JPEG ${s.encodeMs?.toFixed(0) ?? "—"} ms · pulados ${s.skipped}`
      : "aguardando conexão", socket.connected ? "ok" : "wait");
  }, STATUS_INTERVAL_MS);
}

// --- Modo local: o celular detecta a mão (D002, etapa 1.4) -----------------------

async function startLocalTracking(socket) {
  // Importado só neste modo: no modo stream o celular não baixa o MediaPipe (≈ 10 MB).
  const { HandTracker, HAND_CONNECTIONS, INDEX_TIP } = await import("./hand_tracking.js");
  // Modelo carregado depois da conexão: o professor já vê "Conectado" enquanto o MediaPipe sobe.
  const tracker = new HandTracker();
  state.trackingState = "initializing";
  setText(ui.model, "carregando…", "wait");
  try {
    const t0 = performance.now();
    state.delegate = await tracker.init(PREFERRED_DELEGATE);
    state.loadMs = performance.now() - t0;
    setText(ui.model, `pronto (${state.delegate}, ${(state.loadMs / 1000).toFixed(1)} s)`, "ok");
  } catch (err) {
    state.trackingState = "inactive";
    setText(ui.model, "falhou", "bad");
    showError(`MediaPipe não iniciou: ${err.message ?? err}`);
    return;
  }
  startTrackingLoop(tracker, socket, INDEX_TIP, HAND_CONNECTIONS);
}

setText(ui.secure, cameraAvailable() ? "Sim (HTTPS)" : "NÃO — câmera bloqueada", cameraAvailable() ? "ok" : "bad");
ui.start.onclick = start;
