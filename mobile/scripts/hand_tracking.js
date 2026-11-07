// SmartBoard Classroom — rastreamento da mão no celular (etapa 1.4, D002/D006).
//
// Responsabilidade: rodar o MediaPipe Hand Landmarker sobre os frames da
// câmera e devolver a ponta do indicador (landmark 8) em camera_norm.
// Não conhece rede nem interface. MediaPipe e modelo vêm do notebook
// (mobile/vendor), nunca de CDN.

import { FilesetResolver, HandLandmarker } from "../vendor/mediapipe-tasks-vision-1.2.2/vision_bundle.mjs";

const WASM_PATH = new URL("../vendor/mediapipe-tasks-vision-1.2.2/wasm", import.meta.url).href;
const MODEL_PATH = new URL("../vendor/models/hand_landmarker.task", import.meta.url).href;

/** Índices dos landmarks da mão no MediaPipe. */
export const INDEX_TIP = 8;

/** Conexões entre landmarks, para desenhar o esqueleto da mão. */
export const HAND_CONNECTIONS = HandLandmarker.HAND_CONNECTIONS;

const clamp01 = (v) => Math.min(1, Math.max(0, v));

export class HandTracker {
  constructor() {
    this.landmarker = null;
    this.delegate = null;
    this.lastVideoTime = -1;
  }

  /**
   * Carrega o MediaPipe. Por padrão tenta a GPU do celular e cai para CPU se falhar.
   * @param {"GPU"|"CPU"} [preferred] delegate a tentar primeiro
   * @returns {Promise<string>} delegate em uso ("GPU" ou "CPU")
   */
  async init(preferred = "GPU") {
    const vision = await FilesetResolver.forVisionTasks(WASM_PATH);
    const order = preferred === "CPU" ? ["CPU", "GPU"] : ["GPU", "CPU"];
    for (const delegate of order) {
      try {
        this.landmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: MODEL_PATH, delegate },
          runningMode: "VIDEO",
          numHands: 1,
        });
        this.delegate = delegate;
        return delegate;
      } catch (err) {
        console.warn(`MediaPipe com ${delegate} falhou:`, err);
      }
    }
    throw new Error("Não foi possível iniciar o MediaPipe (nem GPU nem CPU).");
  }

  /**
   * Processa o frame atual do vídeo, se for novo.
   * @param {HTMLVideoElement} video
   * @returns {null | {inferenceMs: number, hand: null | {
   *   tip: {x: number, y: number, z: number}, handedness: string,
   *   confidence: number, landmarks: Array<{x: number, y: number, z: number}>}}}
   *   null quando o frame é o mesmo do processamento anterior.
   */
  detect(video) {
    if (!this.landmarker || video.readyState < 2 || video.currentTime === this.lastVideoTime) {
      return null;
    }
    this.lastVideoTime = video.currentTime;

    const t0 = performance.now();
    const result = this.landmarker.detectForVideo(video, t0);
    const inferenceMs = performance.now() - t0;

    const landmarks = result.landmarks?.[0];
    if (!landmarks) return { inferenceMs, hand: null };

    const tip = landmarks[INDEX_TIP];
    const category = result.handedness?.[0]?.[0];
    return {
      inferenceMs,
      hand: {
        // Protocolo: x, y em [0, 1]; o MediaPipe pode passar um pouco disso na borda.
        tip: { x: clamp01(tip.x), y: clamp01(tip.y), z: tip.z },
        // Observação: o MediaPipe nomeia a mão supondo imagem espelhada
        // (selfie). Com a câmera traseira, "Left"/"Right" podem vir trocados.
        handedness: category?.categoryName === "Left" ? "Left" : "Right",
        confidence: clamp01(category?.score ?? 0),
        landmarks,
      },
    };
  }
}
