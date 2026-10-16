import pytest

from aerospace_utils.layouts import (
    LayoutError,
    Slot,
    Split,
    builtin_layouts,
    load_layouts,
    resolve,
    window_range,
)

BUILTINS = {layout.name: layout for layout in builtin_layouts()}


@pytest.mark.parametrize("expression", ["h[w,", "x", "h[]", "h[0:w]", "h[w w]", "h[*, v[*]]"])
def test_malformed_expressions(expression):
    with pytest.raises(LayoutError):
        window_range(expression)


@pytest.mark.parametrize(
    "expression, expected",
    [("h[*]", (1, None)), ("h[3:w, 2:v[*]]", (2, None)), ("h[v[w, w], v[w, w]]", (4, 4)), ("w", (1, 1))],
)
def test_window_range(expression, expected):
    assert window_range(expression) == expected


def test_resolve_main_left():
    assert resolve("h[3:w, 2:v[*]]", 3) == Split("h", (
        (3.0, Slot(1)),
        (2.0, Split("v", ((1.0, Slot(2)), (1.0, Slot(3))))),
    ))


def test_single_window_groups_collapse():
    assert resolve("h[3:w, 2:v[*]]", 2) == Split("h", ((3.0, Slot(1)), (2.0, Slot(2))))


def test_same_direction_groups_merge_with_shared_size():
    assert resolve("h[w, h[w, w]]", 3) == Split("h", (
        (1.0, Slot(1)), (0.5, Slot(2)), (0.5, Slot(3)),
    ))


def test_biggest_slot_is_numbered_first():
    tree = BUILTINS["main-right"].tree(3)

    assert tree.children[1] == (3.0, Slot(1))


def test_equal_slots_are_numbered_in_reading_order():
    tree = BUILTINS["2x2"].tree(4)

    assert tree == Split("h", (
        (1.0, Split("v", ((1.0, Slot(1)), (1.0, Slot(3))))),
        (1.0, Split("v", ((1.0, Slot(2)), (1.0, Slot(4))))),
    ))


def test_grid_puts_fuller_columns_last():
    tree = BUILTINS["grid"].tree(5)

    assert tree == Split("h", (
        (1.0, Slot(1)),
        (1.0, Split("v", ((1.0, Slot(2)), (1.0, Slot(4))))),
        (1.0, Split("v", ((1.0, Slot(3)), (1.0, Slot(5))))),
    ))


@pytest.mark.parametrize(
    "name, windows, expression",
    [
        ("nx2", 4, "h[v[w, w], v[w, w]]"),
        ("nx2", 7, "h[v[w], v[w, w], v[w, w], v[w, w]]"),
        ("2xn", 6, "h[v[w, w, w], v[w, w, w]]"),
        ("2xn", 5, "h[v[w, w], v[w, w, w]]"),
    ],
)
def test_two_row_and_two_column_grids(name, windows, expression):
    assert BUILTINS[name].expression(windows) == expression
    assert not BUILTINS[name].fits(3)


def test_main_center_splits_the_rest_on_both_sides():
    tree = BUILTINS["main-center"].tree(4)

    assert [weight for weight, _ in tree.children] == [1.0, 2.0, 1.0]
    assert tree.children[1][1] == Slot(1)
    assert isinstance(tree.children[2][1], Split)


def test_single_window_layout():
    assert BUILTINS["columns"].tree(1) == Split("h", ((1.0, Slot(1)),))


def test_nesting_deeper_than_one_level_is_rejected():
    with pytest.raises(LayoutError, match="more than one level"):
        resolve("h[w, v[w, h[w, w]]]", 4)


def test_fits():
    assert not BUILTINS["main-center"].fits(2)
    assert BUILTINS["main-center"].fits(9)
    assert BUILTINS["2x2"].fits(4) and not BUILTINS["2x2"].fits(5)


def test_tree_rejects_wrong_window_count():
    with pytest.raises(LayoutError, match="needs 4 windows"):
        BUILTINS["2x2"].tree(3)


def test_user_layouts_are_loaded_and_override_builtins(isolated_config):
    isolated_config.mkdir(parents=True)
    (isolated_config / "layouts.toml").write_text(
        '[dev]\ndescription = "Editor and two terminals"\nlayout = "h[3:w, 2:v[w, w]]"\n'
        '[columns]\nlayout = "h[w, w]"\n'
    )

    layouts = load_layouts()

    assert layouts["dev"].description == "Editor and two terminals"
    assert layouts["dev"].fits(3) and not layouts["dev"].fits(4)
    assert layouts["columns"].max_windows == 2
    assert "grid" in layouts


@pytest.mark.parametrize(
    "content, message",
    [("[bad]\nlayout = 'h[w,'\n", r"\[bad\]"), ("[bad]\ndescription = 'x'\n", "needs a layout"), ("not toml [", "cannot read")],
)
def test_invalid_user_layouts(isolated_config, content, message):
    isolated_config.mkdir(parents=True)
    (isolated_config / "layouts.toml").write_text(content)

    with pytest.raises(LayoutError, match=message):
        load_layouts()
