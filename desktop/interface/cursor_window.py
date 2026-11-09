"""Janela do cursor da Fase 1 (PySide6).

Mostra:
- o cursor na posição da ponta do indicador (mapeamento provisório da Fase 1);
- um painel com URL de acesso, conexão, câmera, FPS do celular, msg/s e RTT.

Não é o overlay transparente da lousa (Fase 3): é uma janela comum, para
validar o caminho celular → notebook. Teclas: F = tela cheia, Esc = sai da
tela cheia (ou cancela a calibração), P = mostra/esconde o painel,
C = calibrar a perspectiva da tela (Fase 2, D014), G = teste de precisão
com grade de 9 pontos (depois de calibrar; também ajusta a correção dos 9
pontos), O = recuperar a última aula, E = exportar PDF, H = gestos de movimento, L = laboratório de gestos, A = assistente de calibração (cantos → V → G → V), K = caneta por pinça ou indicador, V = verificação em 4 pontos entre os do G, M = malha virtual, R = liga/desliga a correção dos 9 pontos,
S = liga/desliga o filtro One Euro, Q = fechar.

Marcadores (D015): fora da calibração com o dedo, 4 marcadores ArUco ficam nos
cantos. Logo depois da calibração, a posição deles na câmera vira a
referência; daí em diante, se o celular se mover, a perspectiva é corrigida
sozinha (markers.py).

Calibração: enquanto ativa, a janela mostra só os alvos e a contagem
(calibration_overlay.py). Depois dela, o cursor passa pela homografia e some
quando o dedo sai da área projetada. Sem calibração, o mapeamento provisório
da Fase 1 continua, apenas para diagnóstico.
"""

from __future__ import annotations

import dataclasses
import math
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from desktop.communication.message_protocol import HandState
from desktop.communication.server import ConnectionState
from desktop.core.hand_selection import HandSelector
from desktop.interaction.dwell import DwellTracker, Rect
from desktop.interface.sidebar_model import Action, SidebarModel, SidebarState, Tool
from desktop.interaction.confirm import NO, YES, ConfirmPrompt
from desktop.interaction.pen_state import PenState
from desktop.interaction.pen_gate import GateState, PenGate
from desktop.interaction.gesture_lab import GestureLab
from desktop.interaction.touch_study import TouchStudy
from desktop.interaction.motions import MotionDetector, Sample, TwoHandZoom, pinch_strength
from desktop.drawing.board import Board
from desktop.drawing.tools import ToolController
from desktop.interface import drawing_view
from desktop.interface.sidebar_view import draw_sidebar, draw_style_panel
from desktop.interface.style_panel import StylePanel, is_style_key
from desktop.drawing.style import DrawingStyle
from desktop.presentation.keys import NEXT, PREV, KeySender
from desktop.presentation.slides import SlideBook
from desktop.drawing import persistence
from desktop.core.coordinate_mapper import CameraToUiMapper, StretchMapper, UiSize
from desktop.calibration.accuracy_test import AccuracyTest, verify_targets
from desktop.calibration.guided import GuidedSetup
from desktop.calibration.calibration_state import CalibrationSession, Phase
from desktop.calibration.homography import Homography, HomographyMapper, SurfacePoint
from desktop.calibration.residual import ResidualCorrection
from desktop.core.one_euro import OneEuro2D
from desktop.core.coordinate_mapper import CameraNormPoint
from desktop.interface.grid_view import draw_grid
from desktop.interface.connect_card import draw_connect_card, qr_matrix
from desktop.communication.server import ConnectionState
from desktop.calibration.markers import (
    CompensatedMapper, MarkerLayout, MotionCompensator, homography_from_markers, marker_image)
from desktop import config
from desktop.interface import ui_prefs
from desktop.calibration import calibration_store
from desktop.interface.touch_study_view import draw_touch_study
from desktop.interface.calibration_overlay import draw_calibration, draw_guided_card
from desktop.interface.cursor_state import CursorState
from desktop.interface.qt_bridge import QtServerBridge

#: Atualização do painel de métricas (ms). O cursor redesenha a cada mensagem.
PANEL_REFRESH_MS = 250

#: Atualização da contagem durante a calibração (ms).
CALIBRATION_REFRESH_MS = 50

#: Tempo que o resultado da calibração fica na tela (s).
CALIBRATION_BANNER_S = 4.0

CURSOR_RADIUS_PX = 18

#: Ferramentas que riscam a lousa (a caneta "prende" o dedo na lousa enquanto risca).
DRAWING_TOOLS = (Tool.BRUSH, Tool.ERASER, Tool.CIRCLE, Tool.RECTANGLE, Tool.SELECT)
BACKGROUND = QColor("#12161c")
GRID = QColor("#1e252f")
TEXT = QColor("#e8ecf1")
MUTED = QColor("#8a94a3")
OK = QColor("#3ccf8e")
WAIT = QColor("#f0b429")
CURSOR = QColor("#ff5a5f")

_CONNECTION_LABELS = {
    ConnectionState.CONNECTED: ("Conectado", OK),
    ConnectionState.DISCONNECTED: ("Aguardando celular", WAIT),
}


class CursorWindow(QWidget):
    def __init__(
        self,
        bridge: QtServerBridge,
        access_url: str,
        state: CursorState | None = None,
        mapper: CameraToUiMapper | None = None,
        event_log: Callable[..., None] | None = None,
        calibration: CalibrationSession | None = None,
        clock: Callable[[], float] = time.monotonic,
        markers: bool = True,
        overlay: bool = False,
        key_sender: KeySender | None = None,
        pen_mode: str = config.PEN_MODE,
        connect_card: bool = False,
        annotations_dir: Path | None = None,
        prefs_path: Path | None = None,
        calibration_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.state = state or CursorState()
        self._fallback_mapper = mapper or StretchMapper()
        self._mapper = self._fallback_mapper
        self._url = access_url
        # Cartão "Conecte o celular" com QR enquanto nenhum celular está conectado (D025).
        self.connect_card = connect_card
        self._qr = qr_matrix(access_url) if connect_card else None
        self._log = event_log or (lambda event, **fields: None)
        self._clock = clock
        self.calibration = calibration or CalibrationSession()
        self.calibrated = False
        self.calibration_summary = "não calibrada"
        # Calibração automática ao abrir (D034): marcadores + 1 toque, ou a da última aula.
        self._calib_path = calibration_path
        self._auto: dict | None = None  # procurando os marcadores: {"until", "readings"}
        self._banner_until = 0.0
        self._banner_text = ""
        self.accuracy: AccuracyTest | None = None
        # Precisão: correção dos 9 pontos (teste G), filtro One Euro e malha virtual.
        self.residual: ResidualCorrection | None = None
        self.residual_enabled = True
        self.filter_enabled = config.ONE_EURO_ENABLED
        self._tip_filter = OneEuro2D()
        self.smooth_tip: CameraNormPoint | None = None
        self.grid_visible = False
        self.accuracy_summary = ""
        self.verify_summary = ""
        self._accuracy_kind = "grid"  # "grid" (G, 9 pontos) ou "verify" (V, 4 pontos entre eles)
        self.guided = GuidedSetup()  # assistente: cantos → V → G → V, uma etapa de cada vez
        self.lab = GestureLab()  # laboratório de gestos (tecla L): acerto novo × antigo
        self.touch = TouchStudy()  # estudo do toque (tecla T, etapa 5.3)

        # Marcadores (D015)
        self.markers_enabled = markers
        self.last_markers: dict = {}
        self.marker_status = "aguardando calibração" if markers else "desligados"
        self._finger_homography = None
        self._compensator: MotionCompensator | None = None
        self._awaiting_reference_until: float | None = None
        self._last_logged_shift = 0.0
        self._last_shift_log_at = -1e9
        self._marker_images: dict[tuple[int, int], QImage] = {}
        self._markers_pinned = False  # tecla N: mostrar até apertar de novo
        self._markers_hide_at: float | None = None  # referência ok → some depois disso
        # Celular mexido com os marcadores escondidos (D030): a visão compara a cena.
        self.scene_watch = None  # FrameProcessor (watch_scene / stop_watching_scene), ligado no main
        self._scene_armed = False
        self._scene_hits: list = []
        self._markers_auto = False  # voltaram sozinhos porque o celular mexeu
        self._auto_since = 0.0
        self._auto_ok = 0

        # Sidebar (Fase 3): acionada por permanência do dedo (dwell.py).
        self.sidebar: SidebarModel | None = None
        self._dwell = DwellTracker()
        self._mouse_point: tuple[float, float] | None = None
        if not overlay:
            self.setMouseTracking(True)  # sem câmera, o mouse faz o papel do dedo (desenvolvimento)
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._ui_tick)
        self._ui_timer.start(33)

        # Desenho (Fase 4): anotações em surface_norm; caneta = pose da mão (D018).
        self.slides = SlideBook()  # cada slide guarda as suas anotações (Fase 6)
        # Guardar as anotações (6.3, D027): arquivo da aula, salvo a cada mudança e ao fechar.
        self.annotations_path = (annotations_dir / f"aula-{time.strftime('%Y%m%d-%H%M%S')}.json"
                                 if annotations_dir is not None else None)
        self._annot_sig: tuple = ()
        self._annot_dirty_at: float | None = None
        self._annot_saved_at = 0.0
        self.board = self.slides.current
        self._keys = key_sender or KeySender()
        self.style = DrawingStyle()
        # Preferências entre aulas: sidebar e estilo (D031, RF30).
        self._prefs_path = prefs_path
        self._prefs = ui_prefs.load(prefs_path)
        ui_prefs.apply_style(self._prefs, self.style)
        self._prefs_saved: dict | None = self._prefs  # igual ao arquivo: não regrava
        self._tools = ToolController(self.board, self.style)
        self.style_panel = StylePanel()  # cor/espessura/borracha ao lado da sidebar (RF20, RF21)
        self._style_away_since: float | None = None
        self._pen = PenState(mode=pen_mode)
        self._pinch: float | None = None
        self._pen_pose: str | None = None
        self._openness: float | None = None  # sinal do redimensionar: tamanho da mão (D035) ou abertura
        self._mouse_down = False
        self.pen_gate = PenGate()  # quando a caneta risca e quando a interface reage (pen_gate.py)
        # Gestos de movimento (D024): deslizar troca slide, toque de pinça clica, duas mãos dão zoom.
        self.motions_enabled = config.MOTIONS_ENABLED
        self._motion = MotionDetector()
        self._zoom = TwoHandZoom()
        self._two_hand_zoom: float | None = None
        self._pen_since: float | None = None
        self._confirm: ConfirmPrompt | None = None

        # Duas mãos: escolhe a que está junto à lousa (hand_selection.py).
        self._hand_selector = HandSelector()
        self.last_candidates: tuple = ()

        self.setWindowTitle("SmartBoard Classroom — cursor (Fase 1)")
        self.resize(1280, 720)
        self.setMinimumSize(640, 360)

        # Slots são métodos (não closures): closures criariam um ciclo de
        # referências e o widget seria liberado pelo coletor de lixo num
        # momento imprevisível, o que derruba o Qt.
        bridge.connection_changed.connect(self._on_connection)
        bridge.hello_received.connect(self._on_hello)
        bridge.hand_tracking_received.connect(self._on_hand_tracking)
        bridge.status_received.connect(self._on_status)
        bridge.rtt_measured.connect(self._on_rtt)
        bridge.vision_state_changed.connect(self._on_vision_state)
        bridge.vision_stats_received.connect(self._on_vision_stats)
        bridge.markers_detected.connect(self._on_markers)
        bridge.scene_moved.connect(self._on_scene_motion)
        # Overlay (Fase 3, etapa 3.0): fundo transparente sobre a apresentação.
        self.overlay = overlay
        self.panel_visible = not overlay

        self._panel_timer = QTimer(self)
        self._panel_timer.timeout.connect(self.update)
        self._panel_timer.start(PANEL_REFRESH_MS)

        self._calibration_timer = QTimer(self)
        self._calibration_timer.timeout.connect(self._calibration_tick)

    # --- calibração ------------------------------------------------------------

    # --- sidebar (Fase 3) -------------------------------------------------------

    def _forbidden_rects(self) -> list[Rect]:
        if not self.markers_visible:
            return []
        return [Rect(m.x - m.quiet, m.y - m.quiet, m.size + 2 * m.quiet, m.size + 2 * m.quiet)
                for m in self.marker_layout().rects]

    def ensure_sidebar(self) -> SidebarModel:
        """Cria a sidebar (ou refaz no novo tamanho, preservando posição, orientação e ferramenta)."""
        old = self.sidebar
        if old is not None and (old.width, old.height) == (self.width(), self.height()):
            return old
        new = SidebarModel(self.width(), self.height(), self._forbidden_rects())
        if old is None:
            ui_prefs.apply_sidebar(self._prefs, new)  # onde o professor a deixou na última aula
        if old is not None:
            new.edge, new.offset, new.orientation, new.tool = old.edge, old.offset, old.orientation, old.tool
            if old.state in (SidebarState.EXPANDED, SidebarState.OPENING, SidebarState.DRAGGING):
                new.state = SidebarState.EXPANDED
        self.sidebar = new
        self._dwell = DwellTracker(tolerance_px=config.DWELL_TOLERANCE_FRAC * self.width())
        return new

    def finger_point(self) -> tuple[float, float] | None:
        """Ponto do dedo na lousa (ui_px); sem dedo e fora do overlay, o mouse."""
        pos = self.cursor_position()
        if pos is not None:
            return (pos.x(), pos.y())
        return None if self.overlay else self._mouse_point

    def pen_down(self) -> bool:
        """Caneta na lousa: indicador esticado (D018) ou, sem câmera, botão do mouse."""
        if self.state.tip is not None:
            return self._pen.down
        return False if self.overlay else self._mouse_down

    def _over_ui(self, point: tuple[float, float] | None, now: float) -> bool:
        if point is None or self.sidebar is None:
            return False
        if self._confirm is not None:
            return True  # com a pergunta aberta, nada risca
        layout = self.sidebar.layout(now)
        margin = config.DWELL_TOLERANCE_FRAC * self.width()
        style = self.style_panel.layout(self.sidebar, now)
        if style is not None and style.panel.contains(*point, margin=margin):
            return True
        if layout.handle.contains(*point, margin=margin):
            return True
        return layout.panel is not None and layout.panel.contains(*point, margin=margin)

    def _ui_tick(self) -> None:
        w, h = self.width(), self.height()
        now = self._clock()
        self._sync_scene_watch()
        self._save_prefs_if_changed()
        if self._overlay_session() is not None or self.lab.active or self.touch.active:
            self._dwell.reset()
            self._emit(self._tools.update(self._current_tool(), False, None, False, (w, h), now))
            return
        sidebar = self.ensure_sidebar()
        sidebar.tick(now)
        point = self.finger_point()
        if self._confirm is not None and self._confirm.expired(now):
            self._log("ui_confirm", action="clear", answer="timeout")
            self._confirm = None
            self._dwell.reset()

        over_ui = self._over_ui(point, now)
        # Com as duas mãos pegando (zoom), a caneta fica levantada (a pinça do zoom não risca).
        gate = self.pen_gate.update(self.pen_down() and self._two_hand_zoom is None, over_ui, point is not None,
                                    sidebar.tool in DRAWING_TOOLS)
        pen = gate.pen
        if gate.started:
            self.style_panel.close()  # começou a riscar: o painel de estilo sai do caminho
        if sidebar.state is not SidebarState.EXPANDED:
            self.style_panel.close()
        # Fecha também quando o dedo vai para a lousa e fica longe do painel.
        if self.style_panel.open and point is not None and not over_ui:
            if self._style_away_since is None:
                self._style_away_since = now
            elif now - self._style_away_since >= config.STYLE_PANEL_AWAY_S:
                self.style_panel.close()
        else:
            self._style_away_since = None

        before = (sidebar.state, self._dwell.current, len(self.board.items), self._confirm)
        surface = None if point is None else (point[0] / w, point[1] / h)
        openness = self._openness if self.state.tip is not None else None
        draw_events = self._tools.update(sidebar.tool, pen, surface, over_ui, (w, h), now, openness)
        draw_events += self._tools.two_hand(self._two_hand_zoom, now, (w, h))
        self._emit(draw_events)
        if any(e["event"] == "draw_shape" for e in draw_events):
            # Uma forma por seleção: para outro círculo/retângulo, escolher de novo na sidebar.
            sidebar.tool = Tool.POINTER
            self._log("ui_tool_auto", tool=Tool.POINTER.value, reason="shape_done")

        dwell_point = point if gate.dwell else None
        if sidebar.state is SidebarState.DRAGGING:
            self._emit(sidebar.drag_update(point, now))
        else:
            targets = (self._confirm.targets() if self._confirm is not None
                       else sidebar.targets(now) + self.style_panel.targets(sidebar, now))
            event = self._dwell.update(now, dwell_point, targets)
            if event is not None and event.kind == "fire":
                self._on_fire(event.key, now, point)
            elif event is not None:
                self._log("ui_cancel", key=getattr(event.key, "value", str(event.key)),
                          progress=event.progress)
        self._autosave(now)
        busy = (sidebar.state in (SidebarState.OPENING, SidebarState.CLOSING, SidebarState.DRAGGING)
                or self._dwell.current is not None or self._confirm is not None
                or self._tools.preview is not None or bool(self._tools.trail)
                or self._tools.selected is not None or self._tools.resizing is not None
                or (sidebar.tool is Tool.ERASER and point is not None))
        if busy or before != (sidebar.state, self._dwell.current, len(self.board.items), self._confirm):
            self.update()

    def _current_tool(self) -> Tool:
        return self.sidebar.tool if self.sidebar is not None else Tool.POINTER

    def _on_fire(self, key, now: float, point) -> None:
        if key in (YES, NO):
            answer = "yes" if key == YES else "no"
            if key == YES:
                self.board.clear()
            self._confirm = None
            self._dwell.reset()
            self._log("ui_confirm", action="clear", answer=answer, items=len(self.board.items))
            return
        if is_style_key(key):
            self._emit([self.style.apply(*key)])
            self.update()
            return
        events = self.sidebar.on_fire(key, now, point)
        self._emit(events)
        for record in events:
            if record["event"] == "ui_action":
                self.do_action(Action(record["action"]), now)
            elif record["event"] == "ui_tool":
                self.style_panel.on_tool(Tool(record["tool"]))

    def do_action(self, action: Action, now: float) -> None:
        """Voltar / Avançar / Limpar (com confirmação). Navegação de slides: Fase 6."""
        if action is Action.UNDO:
            self._log("draw_undo", ok=self.board.undo(), items=len(self.board.items))
        elif action is Action.REDO:
            self._log("draw_redo", ok=self.board.redo(), items=len(self.board.items))
        elif action in (Action.NEXT_SLIDE, Action.PREV_SLIDE):
            self.change_slide(NEXT if action is Action.NEXT_SLIDE else PREV, now)
        elif action is Action.EXPORT:
            self.export_annotations()
        elif action is Action.CLEAR:
            if self.board.items:
                self._confirm = ConfirmPrompt("Limpar tudo?", self.width(), self.height(), now)
                self._dwell.reset()
        self.update()

    def change_slide(self, direction: str, now: float) -> None:
        """Envia a seta para a apresentação e troca para a lousa do outro slide.

        Se a tecla não puder ser enviada, a apresentação não muda: a lousa
        também não, para a contagem de slides não se desencontrar.
        """
        sent, reason = self._keys.send(direction)
        before = self.slides.index
        if sent:
            # Termina o que estava em construção na lousa do slide atual.
            self._emit(self._tools.update(self._current_tool(), False, None, False,
                                          (self.width(), self.height()), now))
            self.board = self.slides.go(1 if direction == NEXT else -1)
            self._tools.board = self.board
            self._confirm = None
        else:
            short = ("libere o Terminal em Acessibilidade (Ajustes do Sistema)"
                     if "Acessibilidade" in reason else reason)
            self._show_banner(f"Slide não trocado: {short}")
        self._log("slide_change", direction=direction, sent=sent, reason=reason,
                  slide=self.slides.index + 1, previous=before + 1, items=len(self.board.items))
        self.update()

    # --- Guardar, recuperar e exportar as anotações (6.3, D027) -------------------

    def _annotations_signature(self) -> tuple:
        # Os itens de cada lousa são uma tupla nova a cada mudança: basta comparar a identidade.
        return tuple((i, id(b.items)) for i, b in sorted(self.slides._boards.items()))

    def _autosave(self, now: float) -> None:
        if self.annotations_path is None:
            return
        sig = self._annotations_signature()
        if sig != self._annot_sig:
            self._annot_sig = sig
            self._annot_dirty_at = now
        if self._annot_dirty_at is not None and now - self._annot_saved_at >= config.ANNOTATIONS_AUTOSAVE_S:
            self.save_annotations()

    def save_annotations(self) -> bool:
        if self.annotations_path is None or not self.slides.annotated() and not self.annotations_path.exists():
            self._annot_dirty_at = None
            return False
        try:
            persistence.save(self.slides, self.annotations_path)
        except OSError as exc:
            self._log("annotations_save_error", error=str(exc))
            return False
        self._annot_dirty_at, self._annot_saved_at = None, self._clock()
        self._log("annotations_saved", slides=self.slides.annotated(), file=self.annotations_path.name)
        return True

    def restore_last_class(self) -> None:
        """Tecla O: traz as anotações da aula salva mais recente (sem contar a atual)."""
        if self.annotations_path is None:
            return
        path = persistence.latest(self.annotations_path.parent, exclude=self.annotations_path)
        if path is None:
            self._show_banner("Nenhuma aula salva para recuperar")
            return
        try:
            book = persistence.load(path)
        except (OSError, ValueError) as exc:
            self._log("annotations_restore_error", file=path.name, error=str(exc))
            self._show_banner(f"Não foi possível abrir {path.name}")
            return
        self._emit(self._tools.update(self._current_tool(), False, None, False, (self.width(), self.height()),
                                      self._clock()))
        self.slides = book
        self.board = book.current
        self._tools.board = self.board
        self._log("annotations_restored", file=path.name, slides=book.annotated())
        self._show_banner(f"Aula recuperada ({len(book.annotated())} slides anotados). "
                          "Volte a apresentação ao 1º slide.")
        self.update()

    def export_annotations(self) -> Path | None:
        """Tecla E ou botão "Salvar PDF": uma página por slide anotado, ao lado do arquivo da aula."""
        if self.annotations_path is None:
            self._show_banner("Salvar PDF indisponível nesta sessão (anotações não são guardadas)")
            return None
        from desktop.interface.export_pdf import export_pdf
        self.save_annotations()
        pdf = self.annotations_path.with_suffix(".pdf")
        pages = export_pdf(self.slides, pdf, self.width() / max(1, self.height()),
                           title=time.strftime("Aula de %d/%m/%Y %H:%M"))
        if not pages:
            self._show_banner("Nada para exportar: a lousa está sem anotações")
            return None
        self._log("annotations_exported", file=pdf.name, pages=pages)
        self._show_banner(f"PDF salvo: anotacoes/{pdf.name} ({pages} página{'s' if pages > 1 else ''})")
        return pdf

    def closeEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        self.flush_annotations()
        super().closeEvent(event)

    def flush_annotations(self) -> None:
        """Salva já o que mudou desde o último salvamento (ao fechar o programa)."""
        if self.annotations_path is None:
            return
        if self._annotations_signature() != self._annot_sig or self._annot_dirty_at is not None:
            self._annot_sig = self._annotations_signature()
            self.save_annotations()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_down = True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_down = False

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        self._mouse_point = (event.position().x(), event.position().y())

    def leaveEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        self._mouse_point = None
        super().leaveEvent(event)

    # --- marcadores (D015) -----------------------------------------------------

    def marker_layout(self) -> MarkerLayout:
        return MarkerLayout.for_screen(self.width(), self.height())

    @property
    def markers_visible(self) -> bool:
        """Os marcadores estão na tela agora? (D028)

        Ficam visíveis antes da calibração, enquanto a referência é procurada,
        durante calibração/testes/assistente e quando o professor aperta N.
        Fora disso somem, e a última correção de movimento fica valendo.
        """
        if not self.markers_enabled:
            return False
        if not config.MARKERS_HIDE_AFTER_CALIBRATION or self._markers_pinned or self._markers_auto:
            return True
        if not self.calibrated or self._awaiting_reference_until is not None:
            return True
        if self._overlay_session() is not None or self.guided.active:
            return True
        return self._markers_hide_at is not None and self._clock() < self._markers_hide_at

    def toggle_markers(self) -> None:
        """Tecla N: mostra os marcadores (o celular se mexeu?) ou volta a escondê-los."""
        if not self.markers_enabled:
            self._show_banner("Marcadores desligados (--no-markers)")
            return
        self._markers_pinned = not self._markers_pinned
        self._log("markers_toggle", shown=self._markers_pinned)
        if (self._markers_pinned and self.calibrated
                and (self._compensator is None or not self._compensator.has_reference)):
            self._await_marker_reference()  # a referência tinha falhado: tenta de novo
        if not self._markers_pinned:
            self.marker_status = "ocultos · última correção mantida (N mostra)"
        self._show_banner("Marcadores visíveis: a correção de movimento acompanha o celular · N esconde"
                          if self._markers_pinned else "Marcadores ocultos · N mostra de novo")
        self.update()

    def _save_prefs_if_changed(self) -> None:
        if self._prefs_path is None or self.sidebar is None or self.sidebar.state is SidebarState.DRAGGING:
            return
        snap = ui_prefs.snapshot(self.sidebar, self.style)
        if snap == self._prefs_saved:
            return
        try:
            ui_prefs.save(self._prefs_path, snap)
            self._prefs_saved = snap
        except OSError as exc:
            self._prefs_path = None  # não insiste a cada quadro
            self._log("prefs_error", error=str(exc))

    # --- celular mexido com os marcadores escondidos (D030) ---------------------------

    def _sync_scene_watch(self) -> None:
        """Vigia a cena só quando os marcadores estão escondidos e há uma correção valendo."""
        if self.scene_watch is None:
            return
        comp = self._compensator
        want = (config.SCENE_MOTION_ENABLED and self.markers_enabled and not self.markers_visible
                and comp is not None and comp.has_reference)
        if want and not self._scene_armed:
            self.scene_watch.watch_scene(comp.surface_quad)
            self._scene_armed, self._scene_hits = True, []
        elif not want and self._scene_armed:
            self.scene_watch.stop_watching_scene()
            self._scene_armed, self._scene_hits = False, []

    def _on_scene_motion(self, shift) -> None:
        if not self._scene_armed or self.markers_visible:
            return
        if self._tools.selected is not None or self._tools.resizing is not None:
            # Segurando um desenho, a mão chega perto da câmera e ocupa a imagem: no 1º
            # teste real isso trouxe os cantos de volta duas vezes sem o celular mexer.
            self._scene_hits = []
            return
        if shift.magnitude >= config.SCENE_MOVED_SHIFT and shift.response >= config.SCENE_MIN_RESPONSE:
            hits = self._scene_hits
            if hits and math.hypot(shift.dx - hits[-1].dx, shift.dy - hits[-1].dy) > config.SCENE_AGREE:
                hits.clear()  # medidas que não concordam: alguém passando, não o celular
            hits.append(shift)
        else:
            self._scene_hits = []
        if len(self._scene_hits) >= config.SCENE_MOVED_CONFIRMATIONS:
            self._reveal_markers_for_reframe(shift)

    def _reveal_markers_for_reframe(self, shift) -> None:
        self._markers_auto, self._auto_since, self._auto_ok = True, self._clock(), 0
        self._log("phone_moved", shift=round(shift.magnitude, 4), response=round(shift.response, 3))
        self.marker_status = "celular mexeu · reenquadrando…"
        self._show_banner("O celular mexeu: marcadores de volta para reenquadrar")
        self._sync_scene_watch()
        self.update()

    def _check_reframed(self, updated: bool, seen: int) -> None:
        """Com os marcadores de volta: o celular parou quando as leituras ficam firmes."""
        comp = self._compensator
        good = updated and comp.settled and seen >= config.MARKER_MIN_VISIBLE
        self._auto_ok = self._auto_ok + 1 if good else 0
        now = self._clock()
        if self._auto_ok >= config.SCENE_SETTLE_CHECKS and now - self._auto_since >= config.SCENE_SETTLE_MIN_S:
            self._markers_auto = False
            self._log("phone_reframed", shift=round(comp.shift, 4), seconds=round(now - self._auto_since, 2))
            self.marker_status = f"ocultos · reenquadrado ({100 * comp.shift:.1f}%) · N mostra"
            self._sync_scene_watch()

    def _schedule_marker_hide(self) -> None:
        if not config.MARKERS_HIDE_AFTER_CALIBRATION:
            return
        self._markers_hide_at = self._clock() + config.MARKER_HIDE_DELAY_S
        QTimer.singleShot(int(config.MARKER_HIDE_DELAY_S * 1000) + 50, self._after_marker_hide)

    def _after_marker_hide(self) -> None:
        if self.markers_enabled and not self.markers_visible and self._compensator is not None \
                and self._compensator.has_reference:
            self.marker_status = "ocultos · última correção mantida (N mostra)"
        self.update()

    def _await_marker_reference(self) -> None:
        if not self.markers_enabled or self._finger_homography is None:
            return
        self._compensator = MotionCompensator(self.marker_layout())
        self._mapper = HomographyMapper(self._finger_homography)
        self._awaiting_reference_until = self._clock() + config.MARKER_REFERENCE_TIMEOUT_S
        self.marker_status = "procurando os marcadores…"
        QTimer.singleShot(int(config.MARKER_REFERENCE_TIMEOUT_S * 1000) + 100,
                          self._check_reference_timeout)

    def _save_calibration(self, observation: dict) -> None:
        """Guarda para a próxima aula (D034): conversão do dedo + onde os marcadores estão."""
        if self._calib_path is None or self._finger_homography is None:
            return
        try:
            calibration_store.save(self._calib_path, self._finger_homography.matrix, observation,
                                   (self.width(), self.height()))
        except OSError as exc:
            self._log("calibration_save_error", error=str(exc))

    def _check_reference_timeout(self) -> None:
        if self._awaiting_reference_until is None or self._clock() < self._awaiting_reference_until:
            return
        self._awaiting_reference_until = None
        self.marker_status = "não vistos: correção automática desligada"
        self._log("marker_reference", ok=False, seen=sorted(self.last_markers))
        self._show_banner("Marcadores não vistos pela câmera: se o celular se mover, recalibre (C)")

    def _on_markers(self, observation: dict) -> None:
        self.last_markers = observation
        if self._auto is not None:
            self._auto_markers(observation)
            return
        if not self.markers_enabled or self.calibration.active or self._compensator is None:
            return
        comp = self._compensator
        if self._awaiting_reference_until is not None:
            if comp.set_reference(observation):
                self._awaiting_reference_until = None
                self._mapper = CompensatedMapper(self._finger_homography, comp)
                self._last_logged_shift = 0.0
                self.marker_status = f"referência ok ({len(observation)}/4 vistos)"
                self._log("marker_reference", ok=True, seen=sorted(observation))
                self._schedule_marker_hide()
                self._save_calibration(observation)
            return
        if not self.markers_visible:
            return  # escondidos: nada para ver; a última correção continua valendo
        updated = comp.has_reference and comp.update(observation)
        if self._markers_auto and comp.has_reference:
            self._check_reframed(updated, len(observation))  # celular parou? esconde de novo
            self.update()
            return
        if updated:
            self.marker_status = (f"{len(observation)}/4 vistos · câmera deslocada "
                                  f"{100 * comp.shift:.1f}% · corrigido")
            now = self._clock()
            if (abs(comp.shift - self._last_logged_shift) >= config.CAMERA_MOVED_THRESHOLD
                    and now - self._last_shift_log_at >= config.CAMERA_MOVED_LOG_INTERVAL_S):
                self._last_logged_shift, self._last_shift_log_at = comp.shift, now
                self._log("camera_moved", shift=round(comp.shift, 4), seen=sorted(observation))
        elif comp.has_reference:
            self.marker_status = f"{len(observation)}/4 vistos · mantendo a última correção"
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        super().resizeEvent(event)
        # O desenho dos marcadores mudou: a referência antiga não vale mais.
        if self._compensator is not None and self.calibrated:
            self._await_marker_reference()

    def _marker_qimage(self, marker_id: int, size: int) -> QImage:
        key = (marker_id, size)
        if key not in self._marker_images:
            img = marker_image(marker_id, size)
            self._marker_images[key] = QImage(img.data, size, size, size,
                                              QImage.Format.Format_Grayscale8).copy()
        return self._marker_images[key]

    def _draw_markers(self, painter: QPainter) -> None:
        for rect in self.marker_layout().rects:
            q = rect.quiet
            painter.fillRect(QRectF(rect.x - q, rect.y - q, rect.size + 2 * q, rect.size + 2 * q),
                             QColor("white"))
            size = int(round(rect.size))
            painter.drawImage(QRectF(rect.x, rect.y, size, size), self._marker_qimage(rect.marker_id, size))

    # --- calibração ------------------------------------------------------------

    def start_auto_calibration(self) -> None:
        """Ao abrir (D034): procura os marcadores. Se estão onde estavam na última aula,
        reaproveita a calibração; senão, perspectiva pelos marcadores + 1 toque no centro.
        Sem marcadores (ou sem resposta), os 4 cantos."""
        if not (config.CALIB_AUTO and self.markers_enabled):
            self.start_calibration()
            return
        self._auto = {"until": self._clock() + config.CALIB_AUTO_WAIT_S, "readings": []}
        self._log("calibration_auto_start")
        self.marker_status = "procurando os marcadores para calibrar…"
        self._show_banner("Calibrando pelos cantos da tela… aponte a câmera do celular para a tela (C: tocar os 4 cantos)")
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def _auto_markers(self, observation: dict) -> None:
        if len(observation) < config.MARKER_REFERENCE_MIN_VISIBLE:
            self._auto["readings"] = []
            return
        readings = self._auto["readings"]
        if readings:
            last = readings[-1]
            common = set(last) & set(observation)
            jump = max((abs(a.x - b.x) + abs(a.y - b.y) for i in common
                        for a, b in zip(last[i], observation[i])), default=1.0)
            if len(common) < config.MARKER_REFERENCE_MIN_VISIBLE or jump > config.CALIB_REUSE_TOLERANCE:
                readings.clear()  # câmera ainda se mexendo
        readings.append(observation)
        if len(readings) < config.CALIB_AUTO_READINGS:
            return
        now = self._clock()
        screen = (self.width(), self.height())
        saved = calibration_store.load(self._calib_path)
        if saved is not None and saved.matches(observation, screen):
            self._auto = None
            shift, common = saved.marker_shift(observation)
            self._finger_homography = Homography(saved.matrix)
            self._mapper = HomographyMapper(self._finger_homography)
            self.calibrated = True
            self.residual = None
            self.calibration_summary = f"da última aula ({saved.saved_at})"
            self._log("calibration_reused", shift=round(shift, 4), markers=common, saved_at=saved.saved_at)
            self._await_marker_reference()
            self._show_banner("Calibração da última aula reaproveitada: o celular está no mesmo lugar"
                              " · precisão ruim? tecla A")
            return
        homography = homography_from_markers(observation, self.marker_layout(),
                                             min_markers=config.MARKER_REFERENCE_MIN_VISIBLE)
        if homography is None:
            readings.clear()
            return
        self._auto = None
        self._awaiting_reference_until = None
        self._emit(self.calibration.start_from_markers(homography, now))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def _auto_timeout(self) -> None:
        self._auto = None
        self._log("calibration_auto_fallback", reason="marcadores não vistos")
        self.start_calibration()
        self.calibration.message = "Não vi os cantos da tela pela câmera: toque nos 4 cantos."

    def start_calibration(self) -> None:
        self._auto = None
        self._awaiting_reference_until = None
        self._emit(self.calibration.start(self._clock()))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def cancel_calibration(self) -> None:
        self._emit(self.calibration.cancel())
        self._calibration_timer.stop()
        self.update()

    def start_accuracy_test(self) -> None:
        if not self.calibrated:
            self._show_banner("Calibre a tela primeiro (tecla C)")
            return
        self._accuracy_kind = "grid"
        self.accuracy = AccuracyTest(self._mapper.homography, to_surface=self.surface_of)
        self._emit(self.accuracy.start(self._clock()))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def start_verify_test(self) -> None:
        """Tecla V: mede o erro em 4 pontos entre os do G (com a correção como estiver)."""
        if not self.calibrated:
            self._show_banner("Calibre a tela primeiro (tecla C)")
            return
        self._accuracy_kind = "verify"
        self.accuracy = AccuracyTest(self._mapper.homography, to_surface=self.surface_of,
                                     targets=verify_targets(), name="Verificação")
        self._emit(self.accuracy.start(self._clock()))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def start_guided_setup(self) -> None:
        """Assistente de calibração (tecla A e ao abrir o programa): etapas em ordem."""
        if self._overlay_session() is not None:
            self._emit(self._overlay_session().cancel())
        self._emit(self.guided.start(self._clock()))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def _guided_start_step(self, key: str) -> None:
        if key == "corners":
            self.start_calibration()
        elif key in ("verify_before", "verify_after"):
            self.start_verify_test()
        elif key == "grid":
            self.start_accuracy_test()

    def _guided_done(self, key: str, **result) -> None:
        self._emit(self.guided.step_done(key, result, self._clock()))

    def _show_banner(self, text: str) -> None:
        if self.guided.active and not text.startswith("Slide"):
            return  # durante o assistente, o cartão de cada etapa já informa
        self._banner_text = text
        self._banner_until = self._clock() + CALIBRATION_BANNER_S
        self.update()

    def _overlay_session(self):
        """Sessão que ocupa a tela agora: calibração ou teste de precisão (o cartão do
        assistente é desenhado à parte)."""
        if self.calibration.active:
            return self.calibration
        if self.accuracy is not None and self.accuracy.active:
            return self.accuracy
        return None

    @property
    def waiting_for_phone(self) -> bool:
        return self.connect_card and self.state.connection is not ConnectionState.CONNECTED

    def start_gesture_lab(self) -> None:
        """Tecla L: pede cada gesto e mede o acerto dos dois reconhecimentos."""
        if self._overlay_session() is not None or self.guided.active:
            return
        self._emit(self.lab.start(self._clock()))
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def start_touch_study(self) -> None:
        """Tecla T: estudo do toque (5.3). Liga a gravação dos pontos da mão, se não estava."""
        if self._overlay_session() is not None or self.guided.active or self.lab.active:
            return
        if config.RECORD_LANDMARKS_PATH is None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            config.RECORD_LANDMARKS_PATH = str(config.LOG_DIR / f"landmarks-{stamp}.jsonl.gz")
        events = self.touch.start(self._clock())
        events[0]["recording"] = Path(config.RECORD_LANDMARKS_PATH).name
        self._emit(events)
        self._calibration_timer.start(CALIBRATION_REFRESH_MS)
        self.update()

    def _calibration_tick(self) -> None:
        now = self._clock()
        if self._auto is not None:
            if self.waiting_for_phone:
                self._auto["until"] = now + config.CALIB_AUTO_WAIT_S  # espera o celular conectar
            elif now >= self._auto["until"]:
                self._auto_timeout()
        if self.lab.active:
            self._emit(self.lab.tick(now))
        if self.touch.active:
            self._emit(self.touch.tick(now))
        if self.guided.active and self.waiting_for_phone and self.guided.phase == "intro":
            self.guided.until = now + config.GUIDED_INTRO_S  # espera o celular para começar
        if self.guided.active:
            key = self.guided.tick(now)
            if key is not None:
                self._guided_start_step(key)
        if self.calibration.active:
            self._emit(self.calibration.tick(now))
            if self.calibration.phase is Phase.DONE:
                self._apply_calibration()
        elif self.accuracy is not None and self.accuracy.active:
            self._emit(self.accuracy.tick(now))
            if self.accuracy.phase is Phase.DONE:
                self._finish_accuracy()
        if (self._overlay_session() is None and not self.guided.active and not self.lab.active
                and not self.touch.active and self._auto is None):
            self._calibration_timer.stop()
        self.update()

    def _finish_accuracy(self) -> None:
        report = self.accuracy.summary.report(self.width(), self.height())
        if self._accuracy_kind == "verify":
            correction = ("ligada" if self.residual is not None and self.residual_enabled
                          else "desligada" if self.residual is not None else "nenhuma")
            self.verify_summary = (f"mediana {report['median_px']:.0f} px ({report['median_pct']:.1f}%), "
                                   f"máx {report['max_px']:.0f} px · correção {correction}")
            self._log("verify_result", surface_width_px=self.width(), surface_height_px=self.height(),
                      correction=correction, **report)
            self._show_banner(f"Verificação: {self.verify_summary}")
            step = self.guided.current.key if self.guided.current else ""
            if step == "verify_after" and self.residual is not None:
                before = self.guided.results.get("verify_before", {}).get("median_px")
                if before is not None and report["median_px"] > before:
                    # A correção piorou o erro entre os pontos (teste real 2026-11-07 13:41:
                    # 11,7 → 19,6 px): fica desligada. R liga de novo.
                    self.residual_enabled = False
                    self._log("residual_auto_off", before_px=before, after_px=report["median_px"])
            self._guided_done(step if step.startswith("verify") else "verify",
                              median_px=report["median_px"], max_px=report["max_px"], correction=correction)
            return
        self.accuracy_summary = (f"mediana {report['median_px']:.0f} px ({report['median_pct']:.1f}%), "
                                 f"máx {report['max_px']:.0f} px ({report['max_pct']:.1f}%)")
        self._log("accuracy_result", surface_width_px=self.width(),
                  surface_height_px=self.height(), **report)
        try:
            self.residual = ResidualCorrection.from_errors(self.accuracy.summary.errors,
                                                           previous=self.residual)
            self.residual_enabled = True
            max_px = self.residual.max_offset() * self.width()
            self._log("residual_update", max_offset_px=round(max_px, 1),
                      offsets=[[round(v, 4) for v in node[2:]] for node in self.residual.nodes()])
            self._show_banner(f"Precisão: {self.accuracy_summary} · correção aplicada (G de novo mede)")
            self._guided_done("grid", median_px=report["median_px"], max_px=report["max_px"],
                              correction="aplicada", max_offset_px=round(max_px, 1))
        except ValueError as exc:
            self._log("residual_rejected", reason=str(exc))
            self._show_banner(f"Precisão: {self.accuracy_summary} · sem correção: {exc}")
            self._guided_done("grid", median_px=report["median_px"], max_px=report["max_px"],
                              correction="recusada")

    def _apply_calibration(self) -> None:
        result = self.calibration.result
        self._finger_homography = result.homography
        self._mapper = HomographyMapper(result.homography)
        self.calibrated = True
        self.residual = None  # nova calibração: a correção dos 9 pontos precisa de outro teste G
        self._await_marker_reference()
        dx, dy = result.verify_error
        error_px = math.hypot(dx * self.width(), dy * self.height())
        error_pct = 100 * error_px / max(1, self.width())
        self.calibration_summary = f"calibrada · erro no centro {error_px:.0f} px ({error_pct:.1f}% da largura)"
        hint = "" if self.guided.active else " · precisão ruim? tecla A faz o ajuste completo"
        if result.mode == "markers":
            # O "erro" aqui é o deslocamento do dedo medido no toque, já corrigido.
            self.calibration_summary = f"pelos marcadores · ajuste do dedo {error_px:.0f} px"
            self._show_banner(f"Tela calibrada pelos marcadores (ajuste do dedo {error_px:.0f} px){hint}")
        else:
            self._show_banner(f"Tela calibrada — erro no centro {error_px:.0f} px ({error_pct:.1f}% da largura){hint}")
        self._log("calibration_result", error_px=round(error_px, 1), error_pct=round(error_pct, 2),
                  surface_width_px=self.width(), surface_height_px=self.height())
        self._guided_done("corners", error_px=round(error_px, 1))

    def _emit(self, events: list[dict[str, Any]]) -> None:
        for record in events:
            fields = dict(record)
            self._log(fields.pop("event"), **fields)

    # --- eventos -------------------------------------------------------------

    def _on_hello(self, hello) -> None:
        self.state.on_hello(hello)
        self.update()

    def surface_of(self, tip: CameraNormPoint | None) -> SurfacePoint | None:
        """camera_norm → surface_norm: homografia (com marcadores) + correção dos 9 pontos.

        None sem calibração ou se o ponto cair atrás do plano.
        """
        homography = getattr(self._mapper, "homography", None)
        if tip is None or homography is None or not self.calibrated:
            return None
        s = homography.to_surface(tip)
        if s is None:
            return None
        if self.residual is not None and self.residual_enabled:
            return SurfacePoint(*self.residual.apply(s.x, s.y))
        return s

    def _to_surface(self):
        """camera_norm → (x, y) surface_norm com a calibração atual, ou None sem calibração."""
        if not self.calibrated or getattr(self._mapper, "homography", None) is None:
            return None

        def convert(point):
            s = self.surface_of(point)
            return None if s is None else (s.x, s.y)
        return convert

    def _on_hand_tracking(self, message) -> None:
        self.last_candidates = message.candidates
        if len(message.candidates) >= 2:
            chosen = self._hand_selector.select(message.candidates, self._to_surface(),
                                                aspect=self.width() / max(1, self.height()))
            message = dataclasses.replace(message, hand=chosen or HandState(present=False))
        else:
            self._hand_selector.select(message.candidates or (
                [message.hand] if message.hand.present else []))
        self.state.on_hand_tracking(message)
        tip = self.state.tip
        if tip is None or not self.filter_enabled:
            self._tip_filter.reset()
            self.smooth_tip = tip
        else:
            self.smooth_tip = CameraNormPoint(*self._tip_filter(tip.x, tip.y, self._clock()))
        self._pen_pose = message.hand.pose if message.hand.present else None
        # Sinal do redimensionar (D035): tamanho da mão na câmera ou abertura da mão.
        if not message.hand.present:
            self._openness = None
        elif config.RESIZE_SIGNAL == "size":
            self._openness = message.hand.palm_size_px
        else:
            self._openness = message.hand.openness
        self._pinch = message.hand.pinch if message.hand.present else None
        was_down = self._pen.down
        if self._pen.update(self._pen_pose, self._pinch) != was_down:
            now = self._clock()
            if was_down and self._pen_since is not None:
                # Diagnóstico da caneta (Fase 5): quanto ficou descida e o que a levantou.
                self._log("pen_up", held_s=round(now - self._pen_since, 2),
                          pose=self._pen_pose or "sem_mao", gate=self.pen_gate.state.value,
                          mode=self._pen.mode,
                          pinch=None if self._pinch is None else round(self._pinch, 2))
            self._pen_since = now if not was_down else None
        self.touch.on_sample(message.hand.present)
        if self.lab.active:
            hand = message.hand
            self.lab.on_sample(self._clock(), hand.pose if hand.present else None,
                               hand.pose_alt if hand.present else None, hand.pinch if hand.present else None)
        self._handle_motions(message)
        self.calibration.on_tip(self.state.tip, self._clock())
        if self.accuracy is not None:
            self.accuracy.on_tip(self.state.tip, self._clock())
        self.update()

    def _handle_motions(self, message) -> None:
        """Gestos de movimento (D024), em coordenadas da lousa. Só com a lousa calibrada e livre."""
        if (not self.motions_enabled or self._overlay_session() is not None or self.guided.active
                or self.touch.active):
            self._motion.reset()
            self._two_hand_zoom = self._zoom.update([])
            return
        now = self._clock()
        hands = []
        if len(message.candidates) >= 2:
            for c in message.candidates[:2]:
                s = self._surface_point(c.index_tip)
                if s is not None:
                    hands.append((s[0], s[1], c.pose, pinch_strength(c.pinch)))
        # Dois indicadores num desenho selecionado = zoom de dois dedos (D038). Sem desenho
        # selecionado, apontar com as duas mãos continua sendo só apontar.
        holding = (self.sidebar is not None and self.sidebar.tool is Tool.SELECT
                   and (self._tools.selected is not None or self._tools.resizing is not None))
        self._two_hand_zoom = self._zoom.update(hands, allow_pointing=holding)
        pos = self.cursor_position()
        sample = None if pos is None else Sample(now, pos.x() / max(1, self.width()), pos.y() / max(1, self.height()),
                                                 self._pen_pose, pinch_strength(self._pinch), self._pinch)
        busy = self._two_hand_zoom is not None or self.pen_gate.state is GateState.DRAWING
        for event in self._motion.update(sample, busy):
            self._emit([event])
            if event["event"] == "motion_swipe" and self._confirm is None:
                # deslizar para a esquerda avança (como virar a página no celular)
                self.change_slide(NEXT if event["direction"] == "left" else PREV, now)
            elif event["event"] == "motion_tap":
                self._tap_click(now)

    def _surface_point(self, tip) -> tuple[float, float] | None:
        """camera_norm → surface_norm: pela calibração, ou pelo mapeamento padrão sem ela."""
        if tip is None:
            return None
        if self.calibrated:
            s = self.surface_of(tip)
            return None if s is None else (s.x, s.y)
        p = self._mapper.map(tip, UiSize(self.width(), self.height()))
        return None if p is None else (p.x / max(1, self.width()), p.y / max(1, self.height()))

    def _tap_click(self, now: float) -> None:
        """Toque de pinça: aciona na hora o botão sob o dedo, sem esperar a permanência."""
        point = self.finger_point()
        if point is None or self.sidebar is None:
            return
        targets = (self._confirm.targets() if self._confirm is not None
                   else self.sidebar.targets(now) + self.style_panel.targets(self.sidebar, now))
        for target in targets:
            if target.rect.contains(*point):
                self._log("motion_click", key=getattr(target.key, "value", str(target.key)))
                self._dwell.reset()
                self._on_fire(target.key, now, point)
                self.update()
                return

    def _on_status(self, status) -> None:
        self.state.on_status(status)
        self.update()

    def _on_rtt(self, rtt_ms: float) -> None:
        self.state.on_rtt(rtt_ms)
        self.update()

    def _on_vision_state(self, state, detail: str) -> None:
        self.state.on_vision_state(state, detail)
        self.update()

    def _on_vision_stats(self, stats) -> None:
        self.state.on_vision_stats(stats)

    def _on_connection(self, state: ConnectionState, detail: str) -> None:
        self.state.on_connection(state, detail)
        if (state is ConnectionState.CONNECTED and self.overlay
                and self.waiting_for_phone is False and self.windowFlags() & Qt.WindowType.Window):
            # O cartão QR começa como janela comum; só ativamos o overlay quando
            # o celular conectar, preservando a seleção de outras janelas antes disso.
            from desktop.interface.overlay_platform import make_overlay_window
            target = self.screen()
            if target is not None:
                self.setGeometry(target.geometry())
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                                | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.Tool)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            make_overlay_window(self)
            self.show()
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (API do Qt)
        key = event.key()
        if key == Qt.Key.Key_F:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif key == Qt.Key.Key_Escape and self._auto is not None:
            self._auto = None
            self._log("calibration_auto_cancel")
            self.update()
        elif key == Qt.Key.Key_Escape and (self._overlay_session() is not None or self.guided.active
                                           or self.lab.active or self.touch.active):
            if self._overlay_session() is not None:
                self._emit(self._overlay_session().cancel())
            self._emit(self.guided.cancel())
            self._emit(self.lab.cancel())
            self._emit(self.touch.cancel())
            self._calibration_timer.stop()
            self.update()
        elif key == Qt.Key.Key_A:
            self.start_guided_setup()
        elif key == Qt.Key.Key_O:
            self.restore_last_class()
        elif key == Qt.Key.Key_E:
            self.export_annotations()
        elif key == Qt.Key.Key_L:
            self.start_gesture_lab()
        elif key == Qt.Key.Key_T:
            self.start_touch_study()
        elif key == Qt.Key.Key_H:
            self.motions_enabled = not self.motions_enabled
            self._log("motions_toggle", enabled=self.motions_enabled)
            self._show_banner(f"Gestos de movimento {'ligados' if self.motions_enabled else 'desligados'}"
                              " (deslizar, toque de pinça, duas mãos)")
        elif key == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif key == Qt.Key.Key_C:
            self.start_calibration()
        elif key == Qt.Key.Key_G:
            self.start_accuracy_test()
        elif key == Qt.Key.Key_K:
            self.set_pen_mode("pinch" if self._pen.mode == "pose" else "pose")
        elif key == Qt.Key.Key_V:
            self.start_verify_test()
        elif key == Qt.Key.Key_M:
            self.grid_visible = not self.grid_visible
            self._log("grid_toggle", visible=self.grid_visible)
            self.update()
        elif key == Qt.Key.Key_R:
            if self.residual is None:
                self._show_banner("Sem correção dos 9 pontos: faça o teste G")
            else:
                self.residual_enabled = not self.residual_enabled
                self._log("residual_toggle", enabled=self.residual_enabled)
                self._show_banner(f"Correção dos 9 pontos {'ligada' if self.residual_enabled else 'desligada'}")
        elif key == Qt.Key.Key_S:
            self.filter_enabled = not self.filter_enabled
            self._log("filter_toggle", enabled=self.filter_enabled)
            self._show_banner(f"Filtro One Euro {'ligado' if self.filter_enabled else 'desligado'}")
        elif key == Qt.Key.Key_N:
            self.toggle_markers()
        elif key == Qt.Key.Key_P:
            self.panel_visible = not self.panel_visible
            self.update()
        elif key == Qt.Key.Key_Q:
            self.close()
        else:
            super().keyPressEvent(event)

    # --- desenho -------------------------------------------------------------

    def cursor_position(self) -> QPointF | None:
        """Posição do cursor em ui_px (dedo filtrado e corrigido), ou None se não há mão."""
        if self.state.tip is None:  # sem mão (ou celular desconectado): sem cursor
            return None
        tip = self.smooth_tip if self.smooth_tip is not None else self.state.tip
        if self.calibrated and getattr(self._mapper, "homography", None) is not None:
            s = self.surface_of(tip)
            if s is None or not s.inside:  # fora da área projetada
                return None
            return QPointF(s.x * self.width(), s.y * self.height())
        point = self._mapper.map(tip, UiSize(self.width(), self.height()))
        if point is None:
            return None
        return QPointF(point.x, point.y)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API do Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.waiting_for_phone:
            draw_connect_card(painter, self._url, self._qr, self.width(), self.height())
            painter.end()
            return
        session = self._overlay_session()
        touch = self.touch.view(self._clock())
        if touch is not None:
            draw_touch_study(painter, touch, self.width(), self.height(), self.cursor_position())
            painter.end()
            return
        lab = self.lab.view(self._clock())
        if lab is not None:
            draw_guided_card(painter, lab, self.width(), self.height(), "Esc cancela o laboratório · L recomeça")
            painter.end()
            return
        card = self.guided.view(self._clock())
        if card is not None and session is None:
            draw_guided_card(painter, card, self.width(), self.height())
            if self.markers_visible and self.calibrated:
                self._draw_markers(painter)
            painter.end()
            return
        if session is not None:
            step = self.guided.current
            prefix = (f"Etapa {self.guided.index + 1} de {len(self.guided.steps)} · "
                      if step is not None and self.guided.phase == "running" else "")
            draw_calibration(painter, session.view(self._clock()), self.width(), self.height(), prefix)
            # Na calibração com o dedo, os marcadores somem: os alvos ficam a 5% da borda.
            if self.markers_visible and not self.calibration.active:
                self._draw_markers(painter)
            painter.end()
            return
        if self.overlay:
            # Transparente: o slide aparece por baixo. Só o que a lousa desenha fica visível.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        else:
            painter.fillRect(self.rect(), BACKGROUND)
            self._draw_grid(painter)
        if self.markers_visible:
            self._draw_markers(painter)
        if self.grid_visible:
            pos = self.cursor_position()
            draw_grid(painter, self.width(), self.height(),
                      None if pos is None else (pos.x(), pos.y()),
                      self.residual if self.residual_enabled else None)
        now = self._clock()
        w, h = self.width(), self.height()
        drawing_view.draw_board(painter, self.board.items, self._tools.preview, w, h)
        drawing_view.draw_pointer_trail(painter, self._tools.trail, now, w, h)
        if self._tools.selected is not None and self._tools.selected < len(self.board.items):
            r = self._tools.resizing
            drawing_view.draw_selection(painter, self.board.items[self._tools.selected], w, h,
                                        scale=None if r is None else r["scale"],
                                        progress=self._tools.resize_progress(now))
        sidebar = self.ensure_sidebar()
        if sidebar.tool is Tool.ERASER and self._confirm is None:
            drawing_view.draw_eraser(painter, self.finger_point(), h, self.style.eraser_frac)
        draw_sidebar(painter, sidebar, now,
                     hover_key=None if self._confirm is not None else self._dwell.current,
                     hover_progress=self._dwell.progress(now))
        if self._confirm is None:
            draw_style_panel(painter, self.style_panel.layout(sidebar, now), self.style, sidebar.button,
                             hover_key=self._dwell.current, hover_progress=self._dwell.progress(now))
        if self._confirm is not None:
            drawing_view.draw_confirm(painter, self._confirm, self._dwell.current,
                                      self._dwell.progress(now))
        if self.panel_visible:
            self._draw_panel(painter)
        if self._clock() < self._banner_until:
            self._draw_banner(painter, self._banner_text)
        self._draw_cursor(painter)  # por último: o cursor nunca fica escondido pelo painel
        painter.end()

    def _draw_banner(self, painter: QPainter, text: str) -> None:
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        box = QRectF(self.width() * 0.15, self.height() * 0.44, self.width() * 0.7, 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRoundedRect(box, 10, 10)
        painter.setPen(OK)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_grid(self, painter: QPainter) -> None:
        painter.setPen(QPen(GRID, 1))
        for i in range(1, 10):
            x = self.width() * i / 10
            y = self.height() * i / 10
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))

    def _draw_cursor(self, painter: QPainter) -> None:
        pos = self.cursor_position()
        if pos is None:
            return
        painter.setPen(QPen(CURSOR, 3))
        painter.setBrush(QColor(CURSOR.red(), CURSOR.green(), CURSOR.blue(), 70))
        painter.drawEllipse(pos, CURSOR_RADIUS_PX, CURSOR_RADIUS_PX)
        painter.drawLine(pos + QPointF(-6, 0), pos + QPointF(6, 0))
        painter.drawLine(pos + QPointF(0, -6), pos + QPointF(0, 6))

    def _panel_lines(self) -> list[tuple[str, str, QColor]]:
        s = self.state
        conn_label, conn_color = _CONNECTION_LABELS[s.connection]
        hand = "detectada" if s.tip is not None else "sem mão"
        return [
            ("Abrir no celular", self._url, TEXT),
            ("Calibração", f"{self.calibration_summary}  (C recalibra)", OK if self.calibrated else WAIT),
            ("Precisão (G)", self.accuracy_summary or "não medida", TEXT),
            ("Verificação (V)", self.verify_summary or "não medida", TEXT),
            ("Correção 9 pts", self._residual_label() + "  (R liga/desliga)", TEXT),
            ("Gestos (H)", "ligados: deslizar ← →, toque de pinça, duas mãos" if self.motions_enabled
                           else "desligados", TEXT),
            ("Filtro / malha", f"One Euro {'ligado' if self.filter_enabled else 'desligado'} (S)"
                               f" · malha {'visível' if self.grid_visible else 'oculta'} (M)", TEXT),
            ("Marcadores", self.marker_status, TEXT),
            ("Ferramenta", self.sidebar.tool.value if self.sidebar else "—", TEXT),
            ("Slide", f"{self.slides.index + 1} · com anotações: "
                      f"{', '.join(map(str, self.slides.annotated())) or 'nenhum'}", TEXT),
            ("Caneta", f"{'pinça' if self._pen.mode == 'pinch' else 'indicador'} (K) · "
                       f"{self.pen_gate.state.value} · pose {self._pose_label()}"
                       f" · {len(self.board.items)} itens", TEXT),
            ("Conexão", f"{conn_label}  {s.connection_detail}".rstrip(), conn_color),
            ("Câmera", s.camera, TEXT),
            ("Rastreamento", f"{s.tracking_state} · {hand}", TEXT),
            ("Modo do celular", s.phone_mode, TEXT),
            ("FPS do celular", "—" if s.phone_fps is None else f"{s.phone_fps:.1f}", TEXT),
            ("Visão (notebook)", s.vision_summary(), TEXT),
            ("Mensagens/s", f"{s.messages_per_second():.1f}", TEXT),
            ("RTT", "—" if s.rtt_ms is None else f"{s.rtt_ms:.1f} ms", TEXT),
            ("Último seq", "—" if s.last_seq is None else str(s.last_seq), MUTED),
        ]

    def set_pen_mode(self, mode: str) -> None:
        """Troca como a caneta desce: "pose" (indicador esticado) ou "pinch" (pinça)."""
        self._pen.mode = mode
        self._pen.reset()
        self._log("pen_mode", mode=mode)
        label = "pinça (polegar no indicador)" if mode == "pinch" else "indicador esticado"
        self._show_banner(f"Caneta: {label}")
        self.update()

    def _residual_label(self) -> str:
        if self.residual is None:
            return "nenhuma (faça o teste G)"
        state = "ligada" if self.residual_enabled else "desligada"
        return f"{state} · maior ajuste {self.residual.max_offset() * self.width():.0f} px"

    def _pose_label(self) -> str:
        labels = {"pointing": "indicador", "open": "aberta", "fist": "fechada", "other": "outra"}
        hand = self.state.tip is not None
        return labels.get(self._pen_pose, "—") if hand else "—"

    def _draw_panel(self, painter: QPainter) -> None:
        lines = self._panel_lines()
        line_h, pad = 22, 12
        # Com marcadores, o painel começa à direita do marcador superior esquerdo.
        left = 12
        if self.markers_visible:
            first = self.marker_layout().rects[0]
            left = first.x + first.size + first.quiet + 12
        panel = QRectF(left, 12, min(620, self.width() - left - 12), pad * 2 + line_h * len(lines))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(panel, 8, 8)

        font = QFont()
        font.setPointSize(11)
        painter.setFont(font)
        for i, (label, value, color) in enumerate(lines):
            y = panel.top() + pad + line_h * i
            painter.setPen(MUTED)
            painter.drawText(QRectF(panel.left() + pad, y, 130, line_h),
                             Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(color)
            painter.drawText(QRectF(panel.left() + pad + 135, y, panel.width() - 150, line_h),
                             Qt.AlignmentFlag.AlignVCenter, value)
