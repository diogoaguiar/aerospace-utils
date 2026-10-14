import pytest

from aerospace_utils.client import Aerospace
from fake_aerospace import FakeAerospace


@pytest.fixture
def fake():
    return FakeAerospace(
        windows=[
            (101, "1", "Browser", "Docs"),
            (201, "2", "Terminal", "build"),
            (202, "2", "Terminal", "logs"),
            (203, "2", "Editor", "main.py"),
            (301, "3", "Chat", "general"),
        ],
        workspaces=[
            ("1", "Left"),
            ("2", "Main"),
            ("3", "Main"),
            ("4", "Main"),
            ("10", "Main"),
        ],
        focused_workspace="2",
        focused_window=201,
    )


@pytest.fixture
def client(fake):
    return Aerospace(runner=fake)
