"""Ponto de entrada do notebook — Fase 1.

Uso, na pasta do projeto:

    .venv/bin/python -m desktop.main              # janela do cursor (etapa 1.3)
    .venv/bin/python -m desktop.main --headless   # só terminal (etapa 1.2)
    .venv/bin/python -m desktop.main --simulate   # janela + celular simulado (desenvolvimento)
    .venv/bin/python -m desktop.main --ip 192.168.1.74 --port 8443
    .venv/bin/python -m desktop.main --screen 1   # tela cheia na 2ª tela (ex.: Smart TV)

Mostra a URL que deve ser aberta no navegador do celular.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass

from aiohttp import web
from PySide6.QtCore import Qt

from functools import partial

from desktop import config
from desktop.communication.message_protocol import HandTrackingMessage, HelloMessage, StatusMessage
from desktop.communication.server import (
    ConnectionState,
    ServerEvents,
    ServerSettings,
    create_app,
    new_session_token,
)
from desktop.communication.tls import build_ssl_context, detect_local_ip, ensure_certificate
from desktop.core.session_log import FanOutEvents, SessionLog, new_log_path
from desktop.vision.frame_processor import FrameProcessor, VisionEvents, VisionState, VisionStats

log = logging.getLogger("smartboard")


class ConsoleEvents(ServerEvents, VisionEvents):
    """Registra eventos no terminal, com resumo de taxa a cada segundo (modo --headless)."""

    def __init__(self) -> None:
        self._window_start = time.monotonic()
        self._count = 0

    def on_connection_state(self, state: ConnectionState, detail: str) -> None:
        log.info("Conexão: %s (%s)", state.value, detail)
        self._window_start, self._count = time.monotonic(), 0

    def on_hello(self, hello: HelloMessage) -> None:
        cam = hello.camera
        log.info("Câmera do celular: %dx%d, %s", cam.width, cam.height, cam.facing.value)

    def on_hand_tracking(self, message: HandTrackingMessage) -> None:
        self._count += 1
        elapsed = time.monotonic() - self._window_start
        if elapsed >= 1.0:
            rate = self._count / elapsed
            tip = message.hand.index_tip
            where = f"x={tip.x:.3f} y={tip.y:.3f}" if tip else "sem mão"
            log.info("hand_tracking: %.1f msg/s | seq=%d | %s", rate, message.seq, where)
            self._window_start, self._count = time.monotonic(), 0

    def on_status(self, status: StatusMessage) -> None:
        log.info("Celular: %.1f FPS, %s", status.fps, status.tracking_state.value)

    def on_rtt(self, rtt_ms: float) -> None:
        log.info("RTT: %.1f ms", rtt_ms)

    def on_vision_state(self, state: VisionState, detail: str) -> None:
        log.info("MediaPipe no notebook: %s %s", state.value, detail)

    def on_vision_stats(self, s: VisionStats) -> None:
        log.info("Visão: %.1f q/s processados, %d recebidos, %d descartados, "
                 "%s ms MediaPipe, %s KB/quadro", s.fps, s.received, s.dropped,
                 s.inference_ms, s.frame_kb)


@dataclass(frozen=True)
class Session:
    ip: str
    port: int
    token: str
    cert_ssl: object  # ssl.SSLContext

    @property
    def url(self) -> str:
        return f"https://{self.ip}:{self.port}/?token={self.token}"


def protected_folder_problem(project_root, platform: str = sys.platform, home=None) -> str | None:
    """Mensagem de erro se o projeto estiver numa pasta protegida do macOS (D011)."""
    from pathlib import Path

    if platform != "darwin":
        return None
    home = Path(home) if home is not None else Path.home()
    try:
        relative = Path(project_root).resolve().relative_to(home.resolve())
    except ValueError:
        return None
    if relative.parts and relative.parts[0] in config.MACOS_PROTECTED_FOLDERS:
        return (f"O projeto está em ~/{relative.parts[0]}, uma pasta protegida do macOS. "
                "Ali o Qt não encontra os próprios plugins e a janela não abre. "
                "Mova o projeto, por exemplo para ~/Projetos, e rode scripts/setup_mac.sh de novo.")
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SmartBoard Classroom — notebook")
    parser.add_argument("--ip", help="IP do notebook na rede local (padrão: detectado)")
    parser.add_argument("--port", type=int, default=config.SERVER_PORT)
    parser.add_argument("--token", help="token fixo (para testes; padrão: aleatório a cada execução)")
    parser.add_argument("--headless", action="store_true", help="sem janela; eventos no terminal")
    parser.add_argument("--no-log", action="store_true", help="não grava o log de sessão em logs/")
    parser.add_argument("--simulate", action="store_true",
                        help="conecta um celular SIMULADO (desenvolvimento; não valida a câmera real)")
    parser.add_argument("--max-hands", type=int, choices=(1, 2), default=config.MAX_HANDS,
                        help="mãos procuradas pelo MediaPipe (2: escolhe a junto à lousa; 1: mais rápido)")
    parser.add_argument("--gesture", choices=("kit", "legacy"), default=config.GESTURE_ENGINE,
                        help="reconhecimento da mão: kit (novo, D022) ou legacy (antigo, D018); "
                             "o outro roda em paralelo para comparar no log")
    parser.add_argument("--pen", choices=("pose", "pinch"), default=config.PEN_MODE,
                        help="como a caneta desce: pose (indicador esticado) ou pinch (pinça); tecla K alterna")
    parser.add_argument("--overlay", action="store_true",
                        help="lousa transparente sobre a apresentação, sem moldura e sempre por cima "
                             "(Fase 3); as teclas passam a ser digitadas na janela de diagnóstico")
    parser.add_argument("--no-markers", action="store_true",
                        help="não projeta os marcadores ArUco nos cantos (sem correção de movimento)")
    parser.add_argument("--no-preview", action="store_true",
                        help="não abre a janela de diagnóstico com a imagem da câmera")
    parser.add_argument("--record", action="store_true",
                        help="grava só os pontos da mão (sem imagem) em logs/landmarks-*.jsonl.gz, "
                             "para reproduzir com tools.replay_landmarks")
    parser.add_argument("--guided", action="store_true",
                        help="ao abrir, o assistente completo (cantos → verificação → 9 pontos → verificação); "
                             "sem esta opção, só os cantos (D032). O assistente continua na tecla A")
    parser.add_argument("--quick", action="store_true",
                        help="só os cantos ao abrir (já é o padrão desde a D032; mantida por compatibilidade)")
    parser.add_argument("--no-calibration", action="store_true",
                        help="não inicia a calibração ao abrir (padrão com --simulate)")
    parser.add_argument("--screen", type=parse_screen, metavar="N|auto",
                        help="abre a janela em tela cheia na tela N (0 = principal; ex.: 1 = Smart TV); "
                             "auto = a primeira tela que não é a do notebook (TV/projetor), ou a principal")
    return parser.parse_args(argv)


def prepare_session(args: argparse.Namespace) -> Session:
    ip = args.ip or detect_local_ip()
    if not args.ip and ip.startswith("127."):
        log.warning("Nenhuma rede detectada (IP %s). O celular não vai conseguir conectar. "
                    "Conecte o notebook ao Wi-Fi ou informe --ip.", ip)
    cert = ensure_certificate(ip)
    log.info("Certificado %s: %s", "gerado" if cert.created else "reaproveitado", cert.cert)
    return Session(ip=ip, port=args.port, token=args.token or new_session_token(),
                   cert_ssl=build_ssl_context(cert))


def print_banner(session: Session) -> None:
    print("\n" + "=" * 70)
    print("  Abra no navegador do celular (mesma rede Wi-Fi):")
    print(f"\n  {session.url}\n")
    print("  Na primeira vez o navegador avisa que a conexão não é particular:")
    print("  toque em 'Avançado' e depois em 'Ir para ... (não seguro)'.")
    print("  Para encerrar: Ctrl+C (ou Q na janela)")
    print("=" * 70 + "\n")


def open_session_log(session: Session, args: argparse.Namespace) -> SessionLog | None:
    if args.no_log:
        return None
    log_file = SessionLog(new_log_path(config.LOG_DIR))
    log_file.write("start", ip=session.ip, port=session.port,
                   mode="headless" if args.headless else ("simulate" if args.simulate else "gui"),
                   protocol_version=config.PROTOCOL_VERSION, max_hands=args.max_hands,
                   overlay=args.overlay, gesture_engine=config.GESTURE_ENGINE, pen_mode=args.pen)
    log.info("Log de sessão: %s", log_file.path)
    return log_file


def with_log(events: ServerEvents, session_log: SessionLog | None) -> FanOutEvents:
    return FanOutEvents(events, session_log) if session_log else FanOutEvents(events)


def build_pipeline(listener: ServerEvents, session_log: SessionLog | None,
                   processor_factory=None, max_hands: int = config.MAX_HANDS
                   ) -> tuple[ServerEvents, FrameProcessor]:
    """Liga servidor → processador de quadros → (janela ou terminal) + log (D013).

    Os eventos do servidor vão para os ouvintes e para o processador; o
    rastreamento que o processador produz vai para os mesmos ouvintes.
    """
    output = with_log(listener, session_log)
    processor = (processor_factory or partial(create_frame_processor, max_hands=max_hands))(output)
    return FanOutEvents(output, processor), processor


def create_frame_processor(output: VisionEvents, max_hands: int = config.MAX_HANDS) -> FrameProcessor:
    from functools import partial

    from desktop.calibration.markers import MarkerDetector
    from desktop.vision.hand_tracker import MediaPipeHandDetector, decode_jpeg_rgb

    return FrameProcessor(partial(MediaPipeHandDetector, max_hands=max_hands), output, decode_jpeg_rgb,
                          marker_detector_factory=MarkerDetector)


def run_headless(session: Session, session_log: SessionLog | None = None,
                 max_hands: int = config.MAX_HANDS) -> None:
    events, processor = build_pipeline(ConsoleEvents(), session_log, max_hands=max_hands)
    processor.start()
    app = create_app(ServerSettings(token=session.token), events)
    try:
        # access_log=None: o log de requisições mostraria o token na URL (D007).
        web.run_app(app, host=config.BIND_HOST, port=session.port,
                    ssl_context=session.cert_ssl, print=None, access_log=None)
    finally:
        processor.stop()


def configure_overlay(window) -> None:
    """Lousa transparente, sem moldura, sempre por cima e que ignora o mouse (Fase 3, etapa 3.0)."""
    from PySide6.QtCore import Qt

    window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                          | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.Tool)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def parse_screen(value: str) -> int | str:
    if value == "auto":
        return value
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use um número (0, 1, …) ou auto") from exc


def resolve_screen(screens, index: int | str | None) -> int | None:
    """"auto": a primeira tela que não é a principal (TV/projetor); sem ela, a principal (0)."""
    if index != "auto":
        return index
    return 1 if len(screens) > 1 else 0


def place_on_screen(window, screens, index: int | str | None, overlay: bool = False) -> None:
    """Lista as telas no log e, se pedido, abre a janela em tela cheia na tela `index`."""
    for i, screen in enumerate(screens):
        geo = screen.geometry()
        log.info("Tela %d: %s, %dx%d", i, screen.name(), geo.width(), geo.height())
    index = resolve_screen(screens, index)
    log.info("Lousa na tela %s", index if index is not None else "da janela")
    if overlay:
        # Enquanto aguarda o celular, o QR fica em uma janela normal e menor.
        # Assim o professor pode escolher outra janela sem a tela inteira ficar bloqueada.
        if getattr(window, "waiting_for_phone", False):
            # configure_overlay() já foi aplicado antes desta função; remova-o
            # para que o cartão não ocupe nem capture a tela inteira.
            window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint
                                  | Qt.WindowType.WindowCloseButtonHint)
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            target = screens[index] if index is not None and 0 <= index < len(screens) else screens[0]
            geo = target.availableGeometry()
            width = min(760, max(520, int(geo.width() * 0.42)))
            height = min(820, max(560, int(geo.height() * 0.78)))
            window.setGeometry(geo.left() + (geo.width() - width) // 2,
                               geo.top() + (geo.height() - height) // 2, width, height)
            window.show()
            return
        # Sem showFullScreen: no macOS ele cria um Space próprio e a lousa sairia
        # de cima da apresentação. Ocupa a tela inteira como janela comum.
        target = screens[index] if index is not None and 0 <= index < len(screens) else screens[0]
        window.setGeometry(target.geometry())
        window.show()
        from desktop.interface.overlay_platform import make_overlay_window

        applied = make_overlay_window(window)
        log.info("Ajuste de tela cheia do sistema: %s", "aplicado" if applied else "não aplicado")
        return
    if index is None:
        window.show()
        return
    if not 0 <= index < len(screens):
        log.warning("Tela %d não existe (há %d). Abrindo na principal.", index, len(screens))
        window.show()
        return
    geo = screens[index].geometry()
    window.move(geo.topLeft())
    window.resize(geo.size())
    window.showFullScreen()


def start_simulated_phone(session: Session) -> None:
    """Celular simulado numa thread, conectando pelo próprio notebook (127.0.0.1)."""
    import asyncio
    import threading

    from tools.fake_phone import run_with_friendly_errors

    url = f"https://127.0.0.1:{session.port}/?token={session.token}"
    log.warning("Modo --simulate: dados de um celular SIMULADO, não da câmera real.")
    threading.Thread(
        target=lambda: asyncio.run(run_with_friendly_errors(url, 30.0, None)),
        name="fake-phone", daemon=True,
    ).start()


def run_gui(session: Session, simulate: bool = False,
            session_log: SessionLog | None = None, screen: int | None = None,
            calibrate: bool = True, preview: bool = True, markers: bool = True,
            max_hands: int = config.MAX_HANDS, overlay: bool = False,
            pen_mode: str = config.PEN_MODE, guided: bool = True) -> int:
    problem = protected_folder_problem(config.PROJECT_ROOT)
    if problem:
        log.warning(problem)
        log.warning("Continuando mesmo assim; se o macOS solicitar permissões, autorize o Terminal/Python em Ajustes do Sistema.")

    # Imports do Qt só no modo gráfico: o modo --headless não depende do PySide6.
    import signal

    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtWidgets import QApplication

    from desktop.communication.server_thread import ServerThread
    from desktop.interface.cursor_window import CursorWindow
    from desktop.presentation.keys import create_key_sender
    from desktop.interface.qt_bridge import QtServerBridge

    qt_app = QApplication(sys.argv)
    bridge = QtServerBridge()
    keys = create_key_sender()
    keys_ok, keys_reason = keys.ready()
    if not keys_ok:
        log.warning("Troca de slides: %s", keys_reason)
    if session_log:
        session_log.write("key_sender", backend=keys.name, ready=keys_ok, reason=keys_reason)
    window = CursorWindow(bridge, session.url,
                          event_log=session_log.write if session_log else None,
                          markers=markers, overlay=overlay, key_sender=keys, pen_mode=pen_mode,
                          connect_card=not simulate,
                          annotations_dir=None if simulate else config.ANNOTATIONS_DIR,
                          prefs_path=None if simulate else config.PREFS_PATH,
                          calibration_path=None if simulate else config.CALIBRATION_PATH)
    if overlay:
        configure_overlay(window)
        if not preview:
            log.warning("--overlay sem a janela de diagnóstico: não haverá como usar as teclas "
                        "C/G/P/Q (a lousa ignora o teclado). Use Ctrl+C no terminal para sair.")

    events, processor = build_pipeline(bridge.events(), session_log, max_hands=max_hands)
    processor.start()
    window.scene_watch = processor  # celular mexido com os marcadores escondidos (D030)
    app = create_app(ServerSettings(token=session.token), events)
    server = ServerThread(app, config.BIND_HOST, session.port, session.cert_ssl)
    server.start()
    server.wait_started()
    if simulate:
        start_simulated_phone(session)

    # Ctrl+C no terminal fecha a janela. O timer devolve o controle ao Python
    # periodicamente, para o sinal ser atendido enquanto o Qt roda.
    signal.signal(signal.SIGINT, lambda *_: qt_app.quit())
    if hasattr(signal, "SIGHUP"):  # fechar a janela do Terminal (macOS/Linux)
        signal.signal(signal.SIGHUP, lambda *_: qt_app.quit())
    # Ao sair por Ctrl+C, Q ou fechando o Terminal, salva as anotações (D027).
    qt_app.aboutToQuit.connect(window.flush_annotations)
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)

    place_on_screen(window, qt_app.screens(), screen, overlay=overlay)
    if overlay:
        # macOS: reafirma a lousa na frente a cada 2 s (ao trocar de app ou de Space).
        from desktop.interface.overlay_platform import keep_on_top

        on_top_timer = QTimer()
        on_top_timer.timeout.connect(lambda: keep_on_top(window))
        on_top_timer.start(2000)
    preview_window = None
    if preview:
        from desktop.interface.camera_preview import CameraPreviewWindow

        # Na tela do notebook (não na lousa): só para o professor/desenvolvedor.
        preview_window = CameraPreviewWindow(processor, window)
        other = [s for i, s in enumerate(qt_app.screens()) if i != screen]
        if other:
            preview_window.move(other[0].geometry().topLeft() + QPoint(40, 40))
        preview_window.show()
    # Calibração a cada abertura (decisão do usuário, D014). O celular simulado
    # não segura o dedo nos alvos, por isso --simulate não calibra.
    if calibrate and not simulate:
        if guided:
            window.start_guided_setup()  # cantos → verificação → 9 pontos → verificação
        else:
            window.start_auto_calibration()  # marcadores (+1 toque) ou a da última aula (D034)
    try:
        return qt_app.exec()
    finally:
        if preview_window is not None:
            preview_window.close()
        server.stop()
        processor.stop()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    args = parse_args(argv)
    if args.headless and args.simulate:
        log.error("--simulate só funciona com a janela (sem --headless).")
        return 2
    config.GESTURE_ENGINE = args.gesture  # lido pelo detector na thread da visão
    if args.record:
        import time as _time
        config.RECORD_LANDMARKS_PATH = str(config.LOG_DIR / f"landmarks-{_time.strftime('%Y%m%d-%H%M%S')}.jsonl.gz")
        log.info("Gravando os pontos da mão (sem imagem): %s", config.RECORD_LANDMARKS_PATH)
    session = prepare_session(args)
    session_log = open_session_log(session, args)
    print_banner(session)
    try:
        if args.headless:
            run_headless(session, session_log, max_hands=args.max_hands)
            return 0
        return run_gui(session, simulate=args.simulate, session_log=session_log,
                       screen=args.screen, calibrate=not args.no_calibration,
                       preview=not args.no_preview, markers=not args.no_markers,
                       max_hands=args.max_hands, overlay=args.overlay, pen_mode=args.pen,
                       guided=args.guided and not args.quick)
    finally:
        if session_log:
            session_log.close()


if __name__ == "__main__":
    sys.exit(main())
