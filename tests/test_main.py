"""Testes do ponto de entrada (D011: projeto fora das pastas protegidas do macOS)."""

from pathlib import Path

import pytest

from desktop.main import parse_args, protected_folder_problem

HOME = Path("/Users/professor")


@pytest.mark.parametrize("folder", ["Desktop", "Documents", "Downloads"])
def test_protected_folders_are_reported_on_macos(folder, tmp_path):
    home = tmp_path
    project = home / folder / "smartboard-classroom"
    project.mkdir(parents=True)
    message = protected_folder_problem(project, platform="darwin", home=home)
    assert message is not None
    assert f"~/{folder}" in message
    assert "~/Projetos" in message


def test_projects_folder_is_fine(tmp_path):
    project = tmp_path / "Projetos" / "smartboard-classroom"
    project.mkdir(parents=True)
    assert protected_folder_problem(project, platform="darwin", home=tmp_path) is None


def test_outside_home_is_fine(tmp_path):
    assert protected_folder_problem(tmp_path, platform="darwin", home=HOME) is None


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_systems_are_not_checked(platform, tmp_path):
    project = tmp_path / "Desktop" / "smartboard-classroom"
    project.mkdir(parents=True)
    assert protected_folder_problem(project, platform=platform, home=tmp_path) is None


def test_cli_options():
    args = parse_args(["--simulate", "--port", "9000", "--ip", "10.0.0.2"])
    assert args.simulate and args.port == 9000 and args.ip == "10.0.0.2"
    assert not args.headless


def test_max_hands_option():
    assert parse_args([]).max_hands == 2
    assert parse_args(["--max-hands", "1"]).max_hands == 1
    with pytest.raises(SystemExit):
        parse_args(["--max-hands", "3"])


class FakeGeometry:
    def __init__(self, w=1920, h=1080):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h

    def topLeft(self):
        return (0, 0)

    def size(self):
        return (self._w, self._h)


class FakeScreen:
    def __init__(self, label):
        self._label = label

    def name(self):
        return self._label

    def geometry(self):
        return FakeGeometry()


class FakeWindow:
    def __init__(self):
        self.calls = []

    def setGeometry(self, geo):
        self.calls.append(("setGeometry", geo))

    def show(self):
        self.calls.append(("show",))

    def move(self, point):
        self.calls.append(("move", point))

    def resize(self, size):
        self.calls.append(("resize", size))

    def showFullScreen(self):
        self.calls.append(("showFullScreen",))


def test_overlay_on_one_screen_skips_always_on_top_trick(monkeypatch):
    """D041: sem segunda tela (projetor), não força o nível 'sempre por cima'."""
    from desktop import main

    called = []
    monkeypatch.setattr("desktop.interface.overlay_platform.make_overlay_window",
                        lambda w: called.append(w) or True)
    window = FakeWindow()
    main.place_on_screen(window, [FakeScreen("Notebook")], "auto", overlay=True)
    assert called == []
    assert ("show",) in window.calls


def test_overlay_on_two_screens_applies_always_on_top_trick(monkeypatch):
    """Com projetor conectado, o truque de ficar por cima de tudo continua valendo."""
    from desktop import main

    called = []
    monkeypatch.setattr("desktop.interface.overlay_platform.make_overlay_window",
                        lambda w: called.append(w) or True)
    window = FakeWindow()
    main.place_on_screen(window, [FakeScreen("Notebook"), FakeScreen("Projetor")],
                         "auto", overlay=True)
    assert called == [window]


def test_configure_overlay_without_second_screen_is_not_a_system_tool_window():
    """D041: sem o flag Tool/StaysOnTop, a janela entra na ordem normal do sistema
    operacional e pode ficar para trás de outras janelas."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.main import configure_overlay

    QApplication.instance() or QApplication([])
    w = QWidget()
    configure_overlay(w, always_on_top=False)
    flags = w.windowFlags()
    assert not flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.FramelessWindowHint  # continua sem moldura e clicável através


def test_configure_overlay_with_second_screen_keeps_always_on_top():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.main import configure_overlay

    QApplication.instance() or QApplication([])
    w = QWidget()
    configure_overlay(w, always_on_top=True)
    assert w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
