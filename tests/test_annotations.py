"""Guardar, recuperar e exportar as anotações (etapa 6.3, D027)."""

import json
import os

import pytest

from desktop import config
from desktop.drawing import persistence
from desktop.drawing.board import Ellipse, Rectangle, Stroke
from desktop.presentation.slides import SlideBook

S = Stroke(((0.1, 0.2), (0.3, 0.4), (0.35, 0.45)), "#1e6fd9", 0.007)
E = Ellipse((0.5, 0.5), (0.6, 0.5), "#e63946", 0.004)
R = Rectangle((0.1, 0.1), (0.2, 0.3), "#2a9d4f", 0.012)


def book_with_three_slides():
    book = SlideBook()
    book.current.add(S)
    book.go(1).add(E)
    book.go(1)  # slide 3 vazio
    book.go(1).add(R)
    return book


def test_round_trip_keeps_items_per_slide(tmp_path):
    book = book_with_three_slides()
    path = tmp_path / "aula-20261107-140000.json"
    persistence.save(book, path)
    data = json.loads(path.read_text())
    assert data["format"] == 1 and set(data["slides"]) == {"1", "2", "4"}  # slide vazio não ocupa espaço
    loaded = persistence.load(path)
    assert loaded.annotated() == [1, 2, 4] and loaded.index == 0
    assert loaded.current.items == (S,) and loaded.go(1).items == (E,)
    assert loaded.go(2).items == (R,)
    assert not loaded.current.can_undo  # histórico não é guardado


def test_latest_skips_current_and_empty(tmp_path):
    persistence.save(book_with_three_slides(), tmp_path / "aula-20261107-100000.json")
    persistence.save(SlideBook(), tmp_path / "aula-20261107-110000.json")  # sem anotações
    current = tmp_path / "aula-20261107-120000.json"
    persistence.save(book_with_three_slides(), current)
    assert persistence.latest(tmp_path, exclude=current).name == "aula-20261107-100000.json"
    (tmp_path / "aula-20261107-130000.json").write_text("{quebrado")
    assert persistence.latest(tmp_path, exclude=current).name == "aula-20261107-100000.json"


def test_bad_format_is_rejected(tmp_path):
    path = tmp_path / "aula-x.json"
    path.write_text(json.dumps({"format": 99, "slides": {}}))
    with pytest.raises(ValueError):
        persistence.load(path)


@pytest.fixture
def window(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge
    app = QApplication.instance() or QApplication([])

    class Clock:
        now = 100.0

        def __call__(self):
            return self.now
    clock = Clock()
    log = []
    w = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=clock, annotations_dir=tmp_path,
                     event_log=lambda e, **f: log.append((e, f)))
    w.resize(1280, 720)
    w.ensure_sidebar()
    yield w, clock, log, tmp_path
    w.close()
    w.deleteLater()
    app.processEvents()


def test_autosave_after_change_and_on_close(window):
    w, clock, log, folder = window
    w.board.add(S)
    w._ui_tick()
    assert w.annotations_path.exists()  # primeiro salvamento sai logo
    w.board.add(E)
    clock.now += 0.5
    w._ui_tick()
    assert len(persistence.load(w.annotations_path).current.items) == 1  # ainda no intervalo de 2 s
    clock.now += config.ANNOTATIONS_AUTOSAVE_S
    w._ui_tick()
    assert len(persistence.load(w.annotations_path).current.items) == 2
    w.board.add(R)
    w.flush_annotations()  # fechar o programa salva na hora
    assert len(persistence.load(w.annotations_path).current.items) == 3
    assert any(e == "annotations_saved" for e, _ in log)


def test_no_file_when_nothing_was_drawn(window):
    w, clock, log, folder = window
    for _ in range(5):
        clock.now += 1
        w._ui_tick()
    w.flush_annotations()
    assert list(folder.glob("aula-*.json")) == []


def test_restore_last_class_with_key_o(window):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    w, clock, log, folder = window
    persistence.save(book_with_three_slides(), folder / "aula-20000101-080000.json")
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_O, Qt.KeyboardModifier.NoModifier))
    assert w.slides.annotated() == [1, 2, 4] and w.board.items == (S,) and w._tools.board is w.board
    assert any(e == "annotations_restored" for e, _ in log)


def test_export_pdf_with_key_e(window):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    w, clock, log, folder = window
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier))
    assert not list(folder.glob("*.pdf"))  # nada desenhado: nada exportado
    w.slides = book_with_three_slides()
    w.board = w.slides.current
    w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier))
    pdf = w.annotations_path.with_suffix(".pdf")
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type/Page\n") in (0, 3)
    assert ("annotations_exported", {"file": pdf.name, "pages": 3}) in log
    shots = os.environ.get("CALIB_SHOTS_DIR")
    if shots:
        import shutil
        shutil.copy(pdf, os.path.join(shots, "anotacoes_exemplo.pdf"))
