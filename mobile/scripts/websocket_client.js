// SmartBoard Classroom — cliente WebSocket do celular.
// Protocolo: docs/communication-protocol.md (v0)
//
// Responsabilidades: conectar ao notebook, enviar `hello`, responder `ping`,
// medir RTT com ping próprio, reconectar sozinho após quedas.
// Não sabe nada de câmera ou MediaPipe.

export const PROTOCOL_VERSION = 0;

/** Estados de conexão do celular (CLAUDE.md §8). */
export const ConnState = Object.freeze({
  DISCONNECTED: "disconnected",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  ERROR: "error",
});

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000]; // depois repete o último
const PING_INTERVAL_MS = 2000;
// Rede que descarta pacotes (ex.: isolamento de clientes, risco R3) pode deixar
// a conexão pendurada sem nenhum evento. Desiste e tenta de novo após este tempo.
const CONNECT_TIMEOUT_MS = 5000;
// Código enviado pelo notebook quando outro aparelho assume a conexão
// (desktop/config.py: WS_CLOSE_REPLACED). Não reconectar sozinho nesse caso.
export const CLOSE_REPLACED = 4000;

/** URL do WebSocket na mesma origem da página, levando o token da página. */
export function defaultSocketUrl() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws?token=${encodeURIComponent(token)}`;
}

export class SmartboardSocket {
  /**
   * @param {object} options
   * @param {string} options.url
   * @param {() => object} options.buildHello  campos do hello (sem type/v)
   * @param {(state: string, detail?: string) => void} [options.onState]
   * @param {(rttMs: number) => void} [options.onRtt]
   * @param {(code: string, detail: string) => void} [options.onServerError]
   */
  constructor({ url, buildHello, onState, onRtt, onServerError }) {
    this.url = url;
    this.buildHello = buildHello;
    this.onState = onState ?? (() => {});
    this.onRtt = onRtt ?? (() => {});
    this.onServerError = onServerError ?? (() => {});
    this.state = ConnState.DISCONNECTED;
    this.ws = null;
    this.stopped = true;
    this.attempt = 0;
    this.pingId = 0;
    this.pingTimer = null;
    this.retryTimer = null;
  }

  start() {
    this.stopped = false;
    this.attempt = 0;
    this._open(ConnState.CONNECTING);
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.retryTimer);
    this._stopPing();
    const ws = this.ws;
    this.ws = null;
    if (ws) ws.close();
    this._setState(ConnState.DISCONNECTED);
  }

  /** Envia um objeto de protocolo. Devolve false se não estiver conectado. */
  send(fields) {
    if (this.state !== ConnState.CONNECTED || this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify({ v: PROTOCOL_VERSION, ...fields }));
    return true;
  }

  /** Envia bytes (quadro de câmera, D013). Devolve false se não estiver conectado. */
  sendBinary(buffer) {
    if (!this.connected) return false;
    this.ws.send(buffer);
    return true;
  }

  get connected() {
    return this.state === ConnState.CONNECTED && this.ws?.readyState === WebSocket.OPEN;
  }

  /** Bytes ainda na fila de saída do navegador (usado para contrapressão). */
  get bufferedAmount() {
    return this.ws?.bufferedAmount ?? 0;
  }

  _setState(state, detail) {
    this.state = state;
    this.onState(state, detail);
  }

  _open(state) {
    this._setState(state);
    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch (err) {
      this._setState(ConnState.ERROR, String(err));
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    // `error` e `close` podem chegar os dois, só um (alguns ambientes não
    // disparam `close` quando a conexão nem chega a abrir) ou nenhum (rede
    // que descarta pacotes). Cada tentativa termina uma única vez.
    let finished = false;
    const finish = (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(connectTimer);
      this._stopPing();
      if (this.ws === ws) this.ws = null;
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
        try { ws.close(); } catch { /* já fechando */ }
      }
      if (code === CLOSE_REPLACED) {
        this.stopped = true;
        clearTimeout(this.retryTimer);
        this._setState(ConnState.DISCONNECTED, "replaced");
        return;
      }
      if (!this.stopped) this._scheduleReconnect(code);
    };
    const connectTimer = setTimeout(() => {
      if (ws.readyState === WebSocket.CONNECTING) finish("timeout");
    }, CONNECT_TIMEOUT_MS);

    ws.onopen = () => {
      clearTimeout(connectTimer);
      ws.send(JSON.stringify({ type: "hello", v: PROTOCOL_VERSION, ...this.buildHello() }));
    };
    ws.onmessage = (event) => this._onMessage(event.data);
    ws.onclose = (event) => finish(event.code);
    ws.onerror = () => {
      // Antes de abrir, o erro encerra a tentativa. Depois de aberta, o
      // `close` que vem em seguida informa o código.
      if (ws.readyState !== WebSocket.OPEN) finish("erro de conexão");
    };
  }

  _onMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    switch (msg.type) {
      case "welcome":
        this.attempt = 0;
        this._setState(ConnState.CONNECTED, `sessão ${msg.session_id}`);
        this._startPing();
        break;
      case "ping":
        // t_reply_ms: horário deste aparelho, para o notebook estimar a diferença
        // entre os relógios e medir a latência ponta a ponta (clock_sync.py).
        this.ws?.send(JSON.stringify({ type: "pong", v: PROTOCOL_VERSION, id: msg.id,
          t_sender_ms: msg.t_sender_ms, t_reply_ms: performance.now() }));
        break;
      case "pong":
        this.onRtt(performance.now() - msg.t_sender_ms);
        break;
      case "error":
        this.onServerError(msg.code, msg.detail);
        break;
    }
  }

  _startPing() {
    this._stopPing();
    this.pingTimer = setInterval(() => {
      this.pingId += 1;
      this.send({ type: "ping", id: this.pingId, t_sender_ms: performance.now() });
    }, PING_INTERVAL_MS);
  }

  _stopPing() {
    clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  _scheduleReconnect(code) {
    const delay = RECONNECT_DELAYS_MS[Math.min(this.attempt, RECONNECT_DELAYS_MS.length - 1)];
    this.attempt += 1;
    this._setState(ConnState.RECONNECTING, `tentativa ${this.attempt} em ${delay} ms` + (code ? ` (${code})` : ""));
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => {
      if (!this.stopped) this._open(ConnState.RECONNECTING);
    }, delay);
  }
}
