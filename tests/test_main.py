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
