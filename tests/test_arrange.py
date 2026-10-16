import pytest

from aerospace_utils import arrange
from aerospace_utils.client import AerospaceError
from aerospace_utils.layouts import LayoutError, builtin_layouts, from_expression
from fake_aerospace import FakeAerospace
from aerospace_utils.client import Aerospace

LAYOUTS = {layout.name: layout for layout in builtin_layouts()}
W, H = 1200.0, 800.0


def workspace_with(count, focused=1):
    fake = FakeAerospace(
        windows=[(n, "5", f"App{n}", "") for n in range(1, count + 1)] + [(99, "1", "Other", "")],
        workspaces=[("1", "Main"), ("5", "Main")],
        focused_workspace="5",
        focused_window=focused,
    )
    return fake, Aerospace(runner=fake, screens=lambda: [(W, H)])


def run(client, layout, workspace="5", order=()):
    arrangement = arrange.plan(client, layout, workspace, order)
    arrange.apply(client, arrangement)
    return arrangement


def rounded(sizes):
    return {wid: (round(w), round(h)) for wid, (w, h) in sizes.items()}


def test_main_left_builds_tree_and_sizes(fake, client):
    run(client, LAYOUTS["main-left"], workspace="2")

    # Focused window 201 is the main slot; the others follow in app order.
    assert fake.tree("2") == ("h", [201, ("v", [203, 202])])
    assert rounded(fake.sizes("2", W, H)) == {201: (720, 800), 203: (480, 400), 202: (480, 400)}


def test_grid_of_six_fills_in_reading_order():
    fake, client = workspace_with(6)

    run(client, LAYOUTS["nx2"])

    assert fake.tree("5") == ("h", [("v", [1, 4]), ("v", [2, 5]), ("v", [3, 6])])


def test_two_columns_with_uneven_rows():
    fake, client = workspace_with(5)

    run(client, LAYOUTS["2xn"])

    assert fake.tree("5") == ("h", [("v", [1, 2]), ("v", [3, 4, 5])])
    sizes = rounded(fake.sizes("5", W, H))
    assert sizes[1] == sizes[2] == (600, 400)
    assert sizes[3] == sizes[4] == sizes[5] == (600, 267)


def test_large_group_keeps_slot_order():
    fake, client = workspace_with(6)

    run(client, from_expression("wide", "h[w, v[*]]"))

    assert fake.tree("5") == ("h", [1, ("v", [2, 3, 4, 5, 6])])


def test_rows_use_a_vertical_root():
    fake, client = workspace_with(3)

    run(client, LAYOUTS["rows"])

    assert fake.tree("5") == ("v", [1, 2, 3])
    assert rounded(fake.sizes("5", W, H)) == {1: (1200, 267), 2: (1200, 267), 3: (1200, 267)}


def test_main_center_sizes():
    fake, client = workspace_with(5)

    run(client, LAYOUTS["main-center"])

    assert fake.tree("5") == ("h", [("v", [2, 4]), 1, ("v", [3, 5])])
    sizes = rounded(fake.sizes("5", W, H))
    assert sizes[1] == (600, 800)
    assert sizes[2] == sizes[3] == (300, 400)


def test_uneven_sizes_inside_a_group():
    fake, client = workspace_with(3)

    run(client, from_expression("x", "h[1:w, 3:v[1:w, 3:w]]"))

    # Slot 1 (the focused window) is the biggest: the 3:w inside the group.
    assert rounded(fake.sizes("5", W, H)) == {2: (300, 800), 3: (900, 200), 1: (900, 600)}


def test_uneven_sizes_across_many_columns():
    fake, client = workspace_with(3)

    run(client, from_expression("x", "h[1:w, 2:w, 3:w]"))

    assert rounded(fake.sizes("5", W, H)) == {3: (200, 800), 2: (400, 800), 1: (600, 800)}


def test_no_screen_size_still_builds_the_tree():
    fake, _ = workspace_with(3)
    client = Aerospace(runner=fake, screens=lambda: [])

    arrangement = run(client, LAYOUTS["main-left"])

    assert fake.tree("5") == ("h", [1, ("v", [2, 3])])
    assert not any(c[0] == "resize" for c in arrangement.commands)


def test_layout_can_be_reapplied():
    fake, client = workspace_with(4)
    run(client, LAYOUTS["2x2"])

    run(client, LAYOUTS["main-left"])

    assert fake.tree("5") == ("h", [1, ("v", [2, 3, 4])])


def test_floating_windows_are_left_alone():
    fake, client = workspace_with(4)
    fake.make_floating(4)

    arrangement = run(client, LAYOUTS["columns"])

    assert fake.tree("5") == ("h", [1, 2, 3])
    assert [w.id for w in arrangement.skipped] == [4]
    assert fake.workspace_of(4) == "5"


def test_order_patterns_fill_slots_first():
    fake, client = workspace_with(3)

    run(client, LAYOUTS["main-left"], order=["app3", "2"])

    assert fake.tree("5") == ("h", [3, ("v", [2, 1])])


def test_unmatched_order_pattern():
    _, client = workspace_with(3)

    with pytest.raises(LayoutError, match="nope"):
        arrange.plan(client, LAYOUTS["columns"], "5", ["nope"])


def test_wrong_window_count():
    _, client = workspace_with(3)

    with pytest.raises(LayoutError, match="needs 4 windows"):
        arrange.plan(client, LAYOUTS["2x2"], "5")


def test_empty_workspace(client):
    with pytest.raises(LayoutError, match="no tiled windows"):
        arrange.plan(client, LAYOUTS["columns"], "4")


def test_focus_returns_to_where_it_was():
    fake, client = workspace_with(3)
    fake.focused_workspace, fake.focused_window = "1", 99

    run(client, LAYOUTS["main-left"])

    assert (fake.focused_workspace, fake.focused_window) == ("1", 99)


def test_failure_moves_parked_windows_back():
    fake, client = workspace_with(3)
    arrangement = arrange.plan(client, LAYOUTS["main-left"], "5")
    fake.fail_once = lambda args: args[0] == "move-node-to-workspace" and args[-1] == "5"

    with pytest.raises(AerospaceError):
        arrange.apply(client, arrangement)

    assert fake.windows_in("5") == [1, 2, 3]
    assert fake.windows_in(arrange.TMP_WORKSPACE) == []


def test_build_commands_for_main_left():
    tree = LAYOUTS["main-left"].tree(4)

    commands = arrange.build_commands("7", tree, {1: 11, 2: 12, 3: 13, 4: 14}, (1000, 900))

    assert [" ".join(c) for c in commands] == [
        "move-node-to-workspace --window-id 11 -- aeroutils-tmp",
        "move-node-to-workspace --window-id 12 -- aeroutils-tmp",
        "move-node-to-workspace --window-id 13 -- aeroutils-tmp",
        "move-node-to-workspace --window-id 14 -- aeroutils-tmp",
        "move-node-to-workspace --window-id 11 -- 7",
        "move-node-to-workspace --window-id 12 -- 7",
        "move-node-to-workspace --window-id 14 -- 7",
        "move-node-to-workspace --window-id 13 -- 7",
        "layout --workspace 7 --root h_tiles",
        "join-with --window-id 12 right",
        "move --window-id 13 left",
        "balance-sizes --workspace 7",
        "resize --window-id 11 width +100",
    ]
