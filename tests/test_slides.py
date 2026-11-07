"""Troca de slides e anotações por slide (Fase 6)."""

import os
import sys

import pytest

from desktop.drawing.board import Stroke
from desktop.presentation import keys as keys_mod
from desktop.presentation.keys import NEXT, PREV, KeySender, create_key_sender
from desktop.presentation.slides import SlideBook


def stroke():
    return Stroke(((0.1, 0.1), (0.2, 0.2)), "#000", 0.006)


def test_slidebook_keeps_annotations_per_slide():
    book = SlideBook()
    book.current.add(stroke())
    b2 = book.go(1)
    assert b2.items == () and book.index == 1
    b2.add(stroke()); b2.add(stroke())
    assert len(book.go(-1).items) == 1
    assert len(book.go(1).items) == 2
    assert book.annotated() == [1, 2]


def test_slidebook_never_goes_below_first():
    book = SlideBook()
    book.current.add(stroke())
    assert book.go(-1) is book.current and book.index == 0 and len(book.current.items) == 1


def test_null_sender_reports_reason():
    ok, reason = KeySender().send(NEXT)
    assert not ok and reason


@pytest.mark.skipif(sys.platform in ("darwin", "win32"), reason="só em outros sistemas")
def test_factory_falls_back_elsewhere():
    assert create_key_sender().name == "nenhum"


class FakeSender(KeySender):
    name = "fake"

    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def ready(self):
        return self.ok, "ok" if self.ok else "sem permissão de Acessibilidade"

    def send(self, direction):
        self.sent.append(direction)
        return self.ready()


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def window_with(qt_app_mod):
    made = []

    def make(sender):
        from desktop.interface.cursor_window import CursorWindow
        from desktop.interface.qt_bridge import QtServerBridge
        log = []
        w = CursorWindow(QtServerBridge(), "https://x/?token=t", key_sender=sender,
                         event_log=lambda e, **f: log.append((e, f)))
        w.resize(1920, 1080)
        made.append(w)
        return w, log
    yield make
    for w in made:
        w.close()
        w.deleteLater()


@pytest.fixture(scope="module")
def qt_app_mod():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_window_switches_board_with_slide(window_with):
    from desktop.interface.sidebar_model import Action
    sender = FakeSender()
    w, log = window_with(sender)
    w.board.add(stroke())
    w.do_action(Action.NEXT_SLIDE, 1.0)
    assert sender.sent == [NEXT] and w.board.items == () and w._tools.board is w.board
    w.board.add(stroke())
    w.do_action(Action.PREV_SLIDE, 2.0)
    assert sender.sent == [NEXT, PREV] and len(w.board.items) == 1
    ev = [f for e, f in log if e == "slide_change"]
    assert ev[0]["slide"] == 2 and ev[1]["slide"] == 1 and all(f["sent"] for f in ev)


def test_window_keeps_board_when_key_not_sent(window_with):
    from desktop.interface.sidebar_model import Action
    w, log = window_with(FakeSender(ok=False))
    w.board.add(stroke())
    w.do_action(Action.NEXT_SLIDE, 1.0)
    assert w.slides.index == 0 and len(w.board.items) == 1
    assert "Acessibilidade" in w._banner_text
    assert [f["sent"] for e, f in log if e == "slide_change"] == [False]


def test_mac_sender_module_has_keycodes():
    assert keys_mod._MAC_KEYCODES == {NEXT: 124, PREV: 123}
