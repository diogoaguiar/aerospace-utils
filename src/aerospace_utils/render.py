"""Draw layouts as box diagrams for the terminal."""

from __future__ import annotations

from typing import Optional

from .layouts import Node, Slot, Split

_UP, _DOWN, _LEFT, _RIGHT = 1, 2, 4, 8
_BOX = {
    _LEFT | _RIGHT: "─",
    _UP | _DOWN: "│",
    _DOWN | _RIGHT: "┌",
    _DOWN | _LEFT: "┐",
    _UP | _RIGHT: "└",
    _UP | _LEFT: "┘",
    _UP | _DOWN | _RIGHT: "├",
    _UP | _DOWN | _LEFT: "┤",
    _DOWN | _LEFT | _RIGHT: "┬",
    _UP | _LEFT | _RIGHT: "┴",
    _UP | _DOWN | _LEFT | _RIGHT: "┼",
}

# Terminal cells are about twice as tall as they are wide.
_CELL_ASPECT = 2.0


def canvas_size(aspect: Optional[float] = None, width: int = 44, max_height: int = 18) -> tuple[int, int]:
    """Diagram width and height in characters for a screen of the given width/height ratio."""
    aspect = aspect or 16 / 9
    height = round(width / aspect / _CELL_ASPECT) + 1
    if height > max_height:
        height = max_height
        width = round((height - 1) * aspect * _CELL_ASPECT) + 1
    return max(width, 24), max(height, 5)


def _min_size(node: Node) -> tuple[int, int]:
    """Smallest (columns, rows) span a node can be drawn in."""
    if isinstance(node, Slot):
        return 3, 2
    sizes = [_min_size(child) for _, child in node.children]
    if node.orientation == "h":
        return sum(c for c, _ in sizes), max(r for _, r in sizes)
    return max(c for c, _ in sizes), sum(r for _, r in sizes)


def _distribute(total: int, weights: list[float], minimums: list[int]) -> list[int]:
    ideal = [total * w / sum(weights) for w in weights]
    sizes = [max(m, int(i)) for i, m in zip(ideal, minimums)]
    while sum(sizes) < total:
        k = max(range(len(sizes)), key=lambda i: ideal[i] - sizes[i])
        sizes[k] += 1
    while sum(sizes) > total:
        shrinkable = [i for i in range(len(sizes)) if sizes[i] > minimums[i]]
        k = max(shrinkable, key=lambda i: sizes[i] - ideal[i])
        sizes[k] -= 1
    return sizes


def _place(node: Node, x0: int, y0: int, x1: int, y1: int, out: dict) -> None:
    if isinstance(node, Slot):
        out[node.index] = (x0, y0, x1, y1)
        return
    horizontal = node.orientation == "h"
    minimums = [_min_size(child)[0 if horizontal else 1] for _, child in node.children]
    spans = _distribute(x1 - x0 if horizontal else y1 - y0, [w for w, _ in node.children], minimums)
    start = x0 if horizontal else y0
    for span, (_, child) in zip(spans, node.children):
        if horizontal:
            _place(child, start, y0, start + span, y1, out)
        else:
            _place(child, x0, start, x1, start + span, out)
        start += span


def fit(text: str, room: int) -> str:
    """Truncate text to room characters, marking the cut with an ellipsis."""
    if len(text) <= room:
        return text
    return text[: room - 1] + "…" if room > 1 else text[:room]


def draw(tree: Split, labels: Optional[dict] = None, size: tuple[int, int] = (44, 12)) -> list[str]:
    """Lines of a box diagram, every line padded to the same width."""
    labels = labels or {}
    min_cols, min_rows = _min_size(tree)
    cols, rows = max(size[0] - 1, min_cols), max(size[1] - 1, min_rows)
    rects: dict = {}
    _place(tree, 0, 0, cols, rows, rects)

    edges = [[0] * (cols + 1) for _ in range(rows + 1)]
    for x0, y0, x1, y1 in rects.values():
        for y in (y0, y1):
            for x in range(x0, x1):
                edges[y][x] |= _RIGHT
                edges[y][x + 1] |= _LEFT
        for x in (x0, x1):
            for y in range(y0, y1):
                edges[y][x] |= _DOWN
                edges[y + 1][x] |= _UP
    canvas = [[_BOX.get(cell, " ") for cell in row] for row in edges]

    for index, (x0, y0, x1, y1) in rects.items():
        room = x1 - x0 - 1
        label = labels.get(index)
        text = fit(f"{index} {label}" if label else str(index), room)
        row = (y0 + y1) // 2
        start = x0 + 1 + (room - len(text)) // 2
        canvas[row][start : start + len(text)] = list(text)
    return ["".join(row) for row in canvas]


def side_by_side(blocks: list[list[str]], max_width: int, gap: int = 3) -> list[str]:
    """Arrange blocks of lines left to right, wrapping into rows that fit max_width."""
    lines: list[str] = []
    row: list[list[str]] = []
    row_width = 0
    for block in blocks:
        width = max(len(line) for line in block)
        if row and row_width + gap + width > max_width:
            lines += _join(row, gap) + [""]
            row, row_width = [], 0
        row.append([line.ljust(width) for line in block])
        row_width += (gap if row_width else 0) + width
    if row:
        lines += _join(row, gap)
    return lines


def _join(blocks: list[list[str]], gap: int) -> list[str]:
    height = max(len(block) for block in blocks)
    padded = [block + [" " * len(block[0])] * (height - len(block)) for block in blocks]
    return [(" " * gap).join(parts).rstrip() for parts in zip(*padded)]
