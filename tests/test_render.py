from aerospace_utils import render
from aerospace_utils.layouts import builtin_layouts

LAYOUTS = {layout.name: layout for layout in builtin_layouts()}


def test_draw_main_left_with_labels():
    lines = render.draw(LAYOUTS["main-left"].tree(3), {1: "Terminal", 2: "Browser"}, (21, 7))

    assert lines == [
        "┌───────────┬───────┐",
        "│           │2 Brow…│",
        "│           │       │",
        "│1 Terminal ├───────┤",
        "│           │   3   │",
        "│           │       │",
        "└───────────┴───────┘",
    ]


def test_draw_grows_to_fit_many_windows():
    lines = render.draw(LAYOUTS["rows"].tree(12), {}, (20, 6))

    assert len(lines) == 25
    assert all(len(line) == len(lines[0]) for line in lines)


def test_draw_uses_junctions_for_a_grid():
    lines = render.draw(LAYOUTS["2x2"].tree(4), {}, (9, 5))

    assert lines[2] == "├───┼───┤"


def test_side_by_side_wraps_to_width():
    assert render.side_by_side([["ab", "cd"], ["efg"], ["h"]], 8) == ["ab   efg", "cd", "", "h"]


def test_canvas_size_follows_screen_shape():
    wide_width, wide_height = render.canvas_size(3440 / 1410)
    tall_width, tall_height = render.canvas_size(1080 / 1920)

    assert wide_width > wide_height
    assert tall_height > tall_width / render._CELL_ASPECT
