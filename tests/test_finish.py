"""D031: botão Salvar PDF na sidebar, preferências entre aulas e consumo no log."""

from __future__ import annotations

import json

import pytest

from desktop import config
from desktop.drawing.style import DrawingStyle
from desktop.interface import ui_prefs
from desktop.interface.sidebar_model import BUTTONS, LABELS, Action, Edge, Orientation, SidebarModel


def test_export_button_in_sidebar():
    assert Action.EXPORT in BUTTONS and LABELS[Action.EXPORT] == "Salvar PDF"
    m = SidebarModel(1920, 1080)
    w, h = m.panel_size()
    assert h < 1080 * 0.9  # 14 botões em 2 colunas cabem na altura


def test_prefs_round_trip(tmp_path):
    path = tmp_path / "preferencias.json"
    sb = SidebarModel(1920, 1080)
    sb.edge, sb.offset, sb.orientation = Edge.RIGHT, 0.3, Orientation.HORIZONTAL
    style = DrawingStyle(color_index=3, width_index=2, eraser_index=0)
    ui_prefs.save(path, ui_prefs.snapshot(sb, style))

    data = ui_prefs.load(path)
    sb2, style2 = SidebarModel(1280, 720), DrawingStyle()
    ui_prefs.apply_sidebar(data, sb2)
    ui_prefs.apply_style(data, style2)
    assert (sb2.edge, sb2.offset, sb2.orientation) == (Edge.RIGHT, 0.3, Orientation.HORIZONTAL)
    assert (style2.color_index, style2.width_index, style2.eraser_index) == (3, 2, 0)


def test_bad_prefs_are_ignored(tmp_path):
    path = tmp_path / "preferencias.json"
    path.write_text("{não é json", encoding="utf-8")
    assert ui_prefs.load(path) is None
    path.write_text(json.dumps({"format": 1, "style": {"color": 99, "width": -1},
                                "sidebar": {"edge": "diagonal", "offset": 7}}), encoding="utf-8")
    data = ui_prefs.load(path)
    style, sb = DrawingStyle(), SidebarModel(800, 600)
    ui_prefs.apply_style(data, style)
    ui_prefs.apply_sidebar(data, sb)
    assert (style.color_index, style.width_index) == (0, 1)
    assert sb.edge is Edge.LEFT
    assert ui_prefs.load(tmp_path / "nao-existe.json") is None


def test_vision_stats_report_cpu_and_memory():
    from desktop.vision.frame_processor import _Window, process_usage
    cpu, mb = process_usage()
    assert cpu >= 0 and (mb is None or mb > 1)
    w = _Window(0.0)
    sum(i * i for i in range(200_000))  # gasta um pouco de CPU
    stats = w.stats(1.0)
    assert stats.cpu_pct is not None and stats.cpu_pct >= 0


def test_log_summary_shows_usage_and_phone_moves(tmp_path):
    from tools.log_summary import usage_summary
    log = tmp_path / "session-x.jsonl"
    rows = [{"event": "vision", "cpu_pct": c, "rss_peak_mb": 300 + c} for c in (40, 50, 60)]
    rows += [{"event": "phone_moved"}, {"event": "phone_reframed", "seconds": 1.4}]
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = usage_summary(log)
    assert "CPU mediana 50%" in out and "360 MB" in out
    assert "1× · reenquadrado 1×, mediana 1.4 s" in out


# --- janela -------------------------------------------------------------------------

@pytest.fixture
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(tmp_path, **kw):
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge
    log = []
    w = CursorWindow(QtServerBridge(), "https://x/?token=t",
                     event_log=lambda e, **f: log.append((e, f)), **kw)
    w.resize(1200, 700)
    w.show()
    return w, log


def test_window_remembers_sidebar_and_style_between_classes(app, tmp_path):
    path = tmp_path / "preferencias.json"
    w, _ = _window(tmp_path, prefs_path=path)
    sb = w.ensure_sidebar()
    sb.edge, sb.offset, sb.orientation = Edge.TOP, 0.7, Orientation.HORIZONTAL
    w.style.apply("color", 2)
    w._ui_tick()
    assert path.exists()
    w.close()

    w2, _ = _window(tmp_path, prefs_path=path)
    sb2 = w2.ensure_sidebar()
    assert (sb2.edge, sb2.orientation) == (Edge.TOP, Orientation.HORIZONTAL)
    assert abs(sb2.offset - 0.7) < 1e-6
    assert w2.style.color_index == 2
    mtime = path.stat().st_mtime_ns
    w2._ui_tick()  # nada mudou: não regrava
    assert path.stat().st_mtime_ns == mtime
    w2.close()


def test_export_button_saves_pdf(app, tmp_path):
    from desktop.drawing.board import Stroke
    w, log = _window(tmp_path, annotations_dir=tmp_path)
    w.board.add(Stroke(points=((10, 10), (200, 120)), color="#ff0000", width=4))
    w.do_action(Action.EXPORT, 0.0)
    assert any(e == "annotations_exported" for e, _ in log)
    assert list(tmp_path.glob("*.pdf"))
    w.close()

    w2, _ = _window(tmp_path)  # sem pasta de anotações (simulação): avisa, não quebra
    w2.do_action(Action.EXPORT, 0.0)
    assert "indisponível" in w2._banner_text
    w2.close()
