import pytest

from aerospace_utils import __version__
from aerospace_utils.cli import main


def test_swap(fake, client, capsys):
    assert main(["swap", "1", "2"], client=client) == 0

    assert fake.windows_in("1") == [201, 202, 203]
    out = capsys.readouterr().out
    assert "Swapped workspaces 1 and 2" in out
    assert "2 -> 1" in out
    assert "Terminal (2), Editor" in out


def test_swap_dry_run(fake, client, capsys):
    assert main(["swap", "--dry-run", "1", "2"], client=client) == 0

    assert fake.moves() == []
    assert "Would swap workspaces 1 and 2" in capsys.readouterr().out


def test_move_alias(fake, client):
    assert main(["mv", "3", "1"], client=client) == 0

    assert fake.windows_in("1") == [101, 301]


def test_reorder(fake, client, capsys):
    assert main(["reorder", "3", "1", "2"], client=client) == 0

    assert fake.windows_in("1") == [301]
    assert "Reordered workspaces 1 2 3" in capsys.readouterr().out


def test_follow_flag(fake, client):
    main(["swap", "--follow", "1", "2"], client=client)

    assert fake.focused_workspace == "1"


def test_nothing_to_move(fake, client, capsys):
    assert main(["swap", "4", "10"], client=client) == 0

    assert "Nothing to move" in capsys.readouterr().out


def test_invalid_arguments_exit_with_usage_error(client, capsys):
    assert main(["swap", "1", "1"], client=client) == 2

    assert "itself" in capsys.readouterr().err


def test_partial_failure_exits_nonzero(fake, client, capsys):
    fake.broken_window_ids.add(301)

    assert main(["move", "3", "1"], client=client) == 1

    assert "could not move window 301" in capsys.readouterr().err


def test_list(client, capsys):
    assert main(["list"], client=client) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["WS", "MONITOR", "WINDOWS"]
    assert lines[2].split() == ["*", "2", "Main", "3", "Terminal", "(2),", "Editor"]
    assert lines[4].split() == ["4", "Main", "0"]


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_reorder_already_in_order(fake, client, capsys):
    assert main(["reorder", "1", "2", "3"], client=client) == 0

    assert fake.moves() == []
    assert "already in that order" in capsys.readouterr().out
