import subprocess

import pytest

from aerospace_utils import client as client_module
from aerospace_utils.client import Aerospace, AerospaceError, Window


def test_list_windows_parses_json(client):
    windows = client.list_windows()

    assert Window(101, "1", "Browser", "Docs", "h_tiles") in windows
    assert len(windows) == 5


def test_list_workspaces_parses_flags(client):
    workspaces = {ws.name: ws for ws in client.list_workspaces()}

    assert workspaces["2"].focused is True
    assert workspaces["2"].visible is True
    assert workspaces["1"].focused is False
    assert workspaces["1"].monitor == "Left"


def test_focused_workspace(client):
    assert client.focused_workspace() == "2"


def test_focused_window_id_is_none_when_nothing_is_focused(fake, client):
    fake.focused_window = None

    assert client.focused_window_id() is None


def test_move_window_sends_window_id_and_target(fake, client):
    client.move_window(301, "4")

    assert fake.moves() == [["move-node-to-workspace", "--window-id", "301", "--", "4"]]


def test_missing_binary_raises_helpful_error(monkeypatch):
    monkeypatch.setattr(client_module.shutil, "which", lambda _: None)

    with pytest.raises(AerospaceError, match="not found"):
        Aerospace().list_windows()


def test_failed_command_raises_with_output(monkeypatch):
    monkeypatch.setattr(client_module.shutil, "which", lambda _: "/usr/local/bin/aerospace")

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="Invalid <window-id> 9\n")

    monkeypatch.setattr(client_module.subprocess, "run", fake_run)

    with pytest.raises(AerospaceError, match="Invalid <window-id> 9"):
        Aerospace().move_window(9, "1")


def test_list_windows_for_one_workspace(client):
    assert [w.id for w in client.list_windows("2")] == [203, 201, 202]


def test_floating_windows_are_not_tiled(fake, client):
    fake.make_floating(202)

    tiled = {w.id: w.tiled for w in client.list_windows("2")}

    assert tiled == {203: True, 201: True, 202: False}


def test_workspace_size_comes_from_its_screen(client):
    assert client.workspace_size("2") == (1200.0, 800.0)


def test_workspace_size_unknown_without_screens(fake):
    assert Aerospace(runner=fake, screens=lambda: []).workspace_size("2") is None
