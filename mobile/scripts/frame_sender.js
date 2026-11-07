// SmartBoard Classroom — envio de quadros da câmera ao notebook (D013).
//
// Responsabilidade: a cada quadro novo da câmera, reduzir a imagem, gerar um
// JPEG e enviá-lo como mensagem binária. Não conhece MediaPipe nem interface.
//
// Formato (docs/communication-protocol.md, "Quadro de câmera"), little-endian:
//   0  "SBF1" · 4 seq uint32 · 8 t_client_ms float64 · 16 JPEG
//
// Contrapressão: só envia se a fila de saída do WebSocket estiver quase
// vazia e não houver outro JPEG sendo gerado. Quando a rede ou o notebook não
// dão conta, o celular pula quadros em vez de acumular atraso.
// Nada é gravado: a imagem só existe em memória até ser enviada (CLAUDE.md §11).

export const FRAME_HEADER_BYTES = 16;
const MAGIC = [0x53, 0x42, 0x46, 0x31]; // "SBF1"

/** Monta o quadro binário: cabeçalho de 16 bytes + JPEG. */
export function buildFrame(seq, tClientMs, jpegBuffer) {
  const out = new Uint8Array(FRAME_HEADER_BYTES + jpegBuffer.byteLength);
  out.set(MAGIC, 0);
  const view = new DataView(out.buffer);
  view.setUint32(4, seq >>> 0, true);
  view.setFloat64(8, tClientMs, true);
  out.set(new Uint8Array(jpegBuffer), FRAME_HEADER_BYTES);
  return out.buffer;
}

/** Tamanho reduzido mantendo a proporção; o lado maior vira no máximo maxSide. */
export function scaledSize(width, height, maxSide) {
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** Gera o JPEG na própria página (canvas.toBlob). Funciona em qualquer navegador. */
export class MainThreadEncoder {
  constructor() {
    this.name = "main";
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d", { alpha: false });
  }

  async encode(video, width, height, quality) {
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.ctx.drawImage(video, 0, 0, width, height);
    const blob = await new Promise((resolve) => this.canvas.toBlob(resolve, "image/jpeg", quality));
    return blob ? blob.arrayBuffer() : null;
  }
}

/**
 * Gera o JPEG num Web Worker (etapa 2.0). A página só reduz o quadro com
 * createImageBitmap; desenho e compressão ficam no worker (OffscreenCanvas).
 */
export class WorkerEncoder {
  /** Cria o worker e espera ele dizer se o navegador suporta. Devolve null se não. */
  static async create(timeoutMs = 2000) {
    if (typeof Worker === "undefined" || typeof createImageBitmap === "undefined") return null;
    let worker;
    try {
      worker = new Worker(new URL("./jpeg_worker.js", import.meta.url), { type: "module" });
    } catch {
      return null;
    }
    const supported = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), timeoutMs);
      worker.onmessage = ({ data }) => {
        if (data.type === "ready") { clearTimeout(timer); resolve(data.supported); }
      };
      worker.onerror = () => { clearTimeout(timer); resolve(false); };
    });
    if (!supported) { worker.terminate(); return null; }
    return new WorkerEncoder(worker);
  }

  constructor(worker) {
    this.name = "worker";
    this.worker = worker;
    this.nextId = 0;
    this.pending = new Map();
    worker.onmessage = ({ data }) => {
      const done = this.pending.get(data.id);
      if (!done) return;
      this.pending.delete(data.id);
      done(data.type === "jpeg" ? data.jpeg : null);
    };
  }

  async encode(video, width, height, quality) {
    const bitmap = await createImageBitmap(video, { resizeWidth: width, resizeHeight: height });
    const id = ++this.nextId;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.worker.postMessage({ id, bitmap, quality }, [bitmap]);
    });
  }
}

export class FrameSender {
  /**
   * @param {object} o
   * @param {HTMLVideoElement} o.video
   * @param {{connected: boolean, bufferedAmount: number, sendBinary: (b: ArrayBuffer) => boolean}} o.socket
   * @param {number} [o.maxSide]      lado maior do JPEG, em px
   * @param {number} [o.quality]      qualidade JPEG (0–1)
   * @param {number} [o.maxFps]       teto de envio
   * @param {number} [o.maxBuffered]  bytes na fila do WebSocket acima dos quais o quadro é pulado
   * @param {{name: string, encode: Function}} [o.encoder]  MainThreadEncoder (padrão) ou WorkerEncoder
   */
  constructor({ video, socket, maxSide = 640, quality = 0.7, maxFps = 30, maxBuffered = 64 * 1024, encoder }) {
    Object.assign(this, { video, socket, maxSide, quality, maxBuffered });
    this.encoder = encoder ?? new MainThreadEncoder();
    // Folga de 25%: com câmera a 30 q/s e teto de 30, um quadro que chega 1 ms
    // "cedo" (variação normal) seria pulado e a taxa cairia pela metade.
    this.minIntervalMs = (1000 / maxFps) * 0.75;
    this.seq = 0;
    this.encoding = false;
    this.lastSentAt = -Infinity;
    this.running = false;
    this._resetWindow(performance.now());
    /** Resumo do último segundo (para a tela e o `status`). */
    this.stats = { fps: 0, encodeMs: null, frameKb: null, skipped: 0, width: 0, height: 0 };
  }

  start() {
    this.running = true;
    this._schedule();
  }

  stop() {
    this.running = false;
  }

  _schedule() {
    if (!this.running) return;
    // Uma chamada por quadro novo da câmera; requestAnimationFrame é o plano B.
    // metadata.captureTime: instante da captura pela câmera (mesma base do
    // performance.now()), quando o navegador informa. Mede também o atraso da câmera.
    if ("requestVideoFrameCallback" in this.video) {
      this.video.requestVideoFrameCallback((_now, metadata) => this._tick(metadata?.captureTime));
    } else {
      requestAnimationFrame(() => this._tick());
    }
  }

  _resetWindow(now) {
    this.window = { start: now, sent: 0, encodeMs: 0, bytes: 0, skipped: 0 };
  }

  _tick(captureTime) {
    const now = performance.now();
    this._maybeCloseWindow(now);
    const ready = this.video.readyState >= 2 && this.video.videoWidth > 0;
    if (ready && this.socket.connected && now - this.lastSentAt >= this.minIntervalMs) {
      if (this.encoding || this.socket.bufferedAmount > this.maxBuffered) {
        this.window.skipped += 1; // contrapressão: rede, notebook ou JPEG atrasados
      } else {
        // Sem captureTime (ou valor fora do esperado), usa o momento atual.
        const valid = Number.isFinite(captureTime) && captureTime > 0 && captureTime <= now;
        this._encodeAndSend(now, valid ? captureTime : null);
      }
    }
    this._schedule();
  }

  async _encodeAndSend(startedAt, captureTime) {
    this.encoding = true;
    this.lastSentAt = startedAt;
    try {
      const { width, height } = scaledSize(this.video.videoWidth, this.video.videoHeight, this.maxSide);
      const tClientMs = captureTime ?? performance.now(); // instante da imagem
      const jpeg = await this.encoder.encode(this.video, width, height, this.quality);
      if (!jpeg) return;
      const encodeMs = performance.now() - startedAt;
      this.seq += 1;
      if (this.socket.sendBinary(buildFrame(this.seq, tClientMs, jpeg))) {
        this.window.sent += 1;
        this.window.encodeMs += encodeMs;
        this.window.bytes += jpeg.byteLength;
        this.stats.width = width;
        this.stats.height = height;
      }
    } finally {
      this.encoding = false;
    }
  }

  _maybeCloseWindow(now) {
    const elapsed = now - this.window.start;
    if (elapsed < 1000) return;
    const w = this.window;
    this.stats = {
      ...this.stats,
      fps: (w.sent * 1000) / elapsed,
      encodeMs: w.sent ? w.encodeMs / w.sent : null,
      frameKb: w.sent ? w.bytes / w.sent / 1024 : null,
      skipped: w.skipped,
    };
    this._resetWindow(now);
  }
}
