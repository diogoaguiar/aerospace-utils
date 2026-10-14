"""Layout definitions: a small tree language, the built-in catalog and user layouts.

A layout is a tree of splits:

    w             one window
    *             every remaining window (at most once per layout)
    h[a, b, ...]  children side by side
    v[a, b, ...]  children stacked top to bottom
    3:x           child x gets a relative size of 3 (default 1)

`h[3:w, 2:v[*]]` is a main window taking 60% of the width, with every other
window stacked on the right. Slots are numbered biggest first, so slot 1 is the
main one; equal slots are numbered in reading order.

AeroSpace nests containers in alternating directions, and aeroutils builds
layouts at most one level deep: a top-level split whose children are windows
or groups of windows.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from .errors import UsageError

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib


class LayoutError(UsageError):
    """A layout is malformed or doesn't fit the number of windows."""


@dataclass(frozen=True)
class Slot:
    index: int


@dataclass(frozen=True)
class Split:
    orientation: str  # "h" or "v"
    children: tuple  # ((weight, Slot | Split), ...)


Node = Union[Slot, Split]


# --- Parsing -----------------------------------------------------------------

@dataclass(frozen=True)
class _Window:
    pass


@dataclass(frozen=True)
class _Rest:
    pass


@dataclass(frozen=True)
class _Group:
    orientation: str
    children: tuple


_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*:")


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self):
        node = self.node()
        if self.peek():
            self.fail("unexpected text")
        return node

    def peek(self) -> str:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, char: str) -> None:
        if self.peek() != char:
            self.fail(f"expected '{char}'")
        self.pos += 1

    def node(self):
        char = self.peek()
        if char in ("w", "*"):
            self.pos += 1
            return _Window() if char == "w" else _Rest()
        if char in ("h", "v"):
            self.pos += 1
            self.expect("[")
            children = [self.child()]
            while self.peek() == ",":
                self.pos += 1
                children.append(self.child())
            self.expect("]")
            return _Group(char, tuple(children))
        self.fail("expected w, *, h[...] or v[...]")

    def child(self):
        self.peek()
        weight = 1.0
        match = _WEIGHT.match(self.text, self.pos)
        if match:
            weight = float(match.group(1))
            if weight <= 0:
                self.fail("sizes must be positive")
            self.pos = match.end()
        return weight, self.node()

    def fail(self, message: str):
        raise LayoutError(f"{message} at position {self.pos + 1} of '{self.text}'")


def _count(node) -> tuple[int, int]:
    """(fixed windows, rest markers) in a parsed expression."""
    if isinstance(node, _Window):
        return 1, 0
    if isinstance(node, _Rest):
        return 0, 1
    counts = [_count(child) for _, child in node.children]
    return sum(c[0] for c in counts), sum(c[1] for c in counts)


def window_range(expression: str) -> tuple[int, Optional[int]]:
    """Smallest and largest window count an expression fits (None: no limit)."""
    fixed, rest = _count(_Parser(expression).parse())
    if rest > 1:
        raise LayoutError(f"'*' can appear only once in '{expression}'")
    return (fixed + 1, None) if rest else (fixed, fixed)


# --- Resolving an expression for a window count ------------------------------

def _expand(node, rest_count: int) -> list:
    """Expand into (weight, node) children, with '*' replaced by slots."""
    if isinstance(node, _Window):
        return [Slot(0)]
    if isinstance(node, _Rest):
        return [Slot(0)] * rest_count
    children = []
    for weight, child in node.children:
        for expanded in _expand(child, rest_count):
            children.append((weight, expanded))
    return [Split(node.orientation, tuple(children))]


def _normalize(node: Node) -> Node:
    """Collapse single-child splits and merge splits nested in the same direction."""
    if isinstance(node, Slot):
        return node
    children = []
    for weight, child in node.children:
        child = _normalize(child)
        if isinstance(child, Split) and child.orientation == node.orientation:
            total = sum(w for w, _ in child.children)
            children.extend((weight * w / total, c) for w, c in child.children)
        else:
            children.append((weight, child))
    if len(children) == 1:
        return children[0][1]
    return Split(node.orientation, tuple(children))


def unit_rects(node: Node, x=0.0, y=0.0, w=1.0, h=1.0) -> list[tuple[float, float, float, float]]:
    """Rectangles of the slots in tree order, inside a unit square."""
    if isinstance(node, Slot):
        return [(x, y, w, h)]
    total = sum(weight for weight, _ in node.children)
    rects = []
    for weight, child in node.children:
        share = weight / total
        if node.orientation == "h":
            rects += unit_rects(child, x, y, w * share, h)
            x += w * share
        else:
            rects += unit_rects(child, x, y, w, h * share)
            y += h * share
    return rects


def _number(node: Node, numbers: list[int]) -> Node:
    if isinstance(node, Slot):
        return Slot(numbers.pop(0))
    return Split(node.orientation, tuple((w, _number(c, numbers)) for w, c in node.children))


def resolve(expression: str, windows: int) -> Split:
    """The concrete tree an expression gives for a number of windows."""
    low, high = window_range(expression)
    if windows < low or (high is not None and windows > high):
        raise LayoutError(f"'{expression}' fits {_range_label(low, high)}, not {windows}")
    parsed = _Parser(expression).parse()
    if not isinstance(parsed, _Group):
        parsed = _Group("h", ((1.0, parsed),))
    fixed, _ = _count(parsed)
    tree = _normalize(_expand(parsed, windows - fixed)[0])
    if isinstance(tree, Slot):
        tree = Split("h", ((1.0, tree),))
    for _, child in tree.children:
        if isinstance(child, Split) and any(isinstance(c, Split) for _, c in child.children):
            raise LayoutError(f"'{expression}' nests groups more than one level deep")

    rects = unit_rects(tree)
    order = sorted(
        range(len(rects)),
        key=lambda i: (-round(rects[i][2] * rects[i][3], 9), round(rects[i][1], 9), round(rects[i][0], 9)),
    )
    numbers = [0] * len(rects)
    for slot_number, position in enumerate(order, start=1):
        numbers[position] = slot_number
    return _number(tree, numbers)


def slots(node: Node) -> list[Slot]:
    """Slots in tree order (left to right, top to bottom)."""
    if isinstance(node, Slot):
        return [node]
    return [slot for _, child in node.children for slot in slots(child)]


def _range_label(low: int, high: Optional[int]) -> str:
    if high is None:
        return f"{low}+ windows"
    return f"{low} window" if low == high == 1 else f"{low} windows" if low == high else f"{low}-{high} windows"


# --- Layouts -------------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    name: str
    description: str
    min_windows: int
    max_windows: Optional[int]
    expression: Callable[[int], str]
    example_windows: int
    source: str = "built-in"

    @property
    def windows_label(self) -> str:
        return _range_label(self.min_windows, self.max_windows)

    def fits(self, windows: int) -> bool:
        return windows >= self.min_windows and (self.max_windows is None or windows <= self.max_windows)

    def tree(self, windows: int) -> Split:
        if not self.fits(windows):
            raise LayoutError(f"{self.name} needs {self.windows_label}, not {windows}")
        return resolve(self.expression(windows), windows)


def from_expression(name: str, expression: str, description: str = "", source: str = "built-in") -> Layout:
    low, high = window_range(expression)
    resolve(expression, low)  # validate now rather than when applied
    return Layout(
        name=name,
        description=description or expression,
        min_windows=low,
        max_windows=high,
        expression=lambda _: expression,
        example_windows=high if high is not None else max(low, 3),
        source=source,
    )


def _windows(count: int) -> str:
    return ", ".join(["w"] * count)


def _grid(n: int) -> str:
    """Columns as even as possible; the fuller columns go last so bigger slots come first."""
    columns = math.ceil(math.sqrt(n))
    base, extra = divmod(n, columns)
    counts = [base] * (columns - extra) + [base + 1] * extra
    return "h[" + ", ".join(f"v[{_windows(c)}]" for c in counts) + "]"


def _main_center(n: int) -> str:
    left = (n - 1) // 2
    return f"h[1:v[{_windows(left)}], 2:w, 1:v[{_windows(n - 1 - left)}]]"


def builtin_layouts() -> list[Layout]:
    return [
        from_expression("columns", "h[*]", "All windows side by side"),
        from_expression("rows", "v[*]", "All windows stacked top to bottom"),
        Layout("grid", "Even grid, as square as possible", 1, None, _grid, 5),
        from_expression("main-left", "h[3:w, 2:v[*]]", "Main left, the rest stacked on the right"),
        from_expression("main-right", "h[2:v[*], 3:w]", "Main right, the rest stacked on the left"),
        from_expression("main-top", "v[3:w, 2:h[*]]", "Main on top, the rest side by side below"),
        Layout("main-center", "Main in the middle, the rest on both sides", 3, None, _main_center, 5),
        from_expression("2x2", "h[v[w, w], v[w, w]]", "Four equal quarters"),
        from_expression("3x2", "h[v[w, w], v[w, w], v[w, w]]", "3 columns by 2 rows"),
        from_expression("2x3", "h[v[w, w, w], v[w, w, w]]", "2 columns by 3 rows"),
    ]


def user_layouts_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "aeroutils" / "layouts.toml"


def load_layouts(path: Optional[Path] = None) -> dict[str, Layout]:
    """Built-in layouts plus the user's, which win on name clashes."""
    layouts = {layout.name: layout for layout in builtin_layouts()}
    path = path or user_layouts_path()
    if not path.exists():
        return layouts
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise LayoutError(f"cannot read {path}: {error}") from error
    for name, entry in data.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("layout"), str):
            raise LayoutError(f"{path}: [{name}] needs a layout = \"...\" entry")
        try:
            layouts[name] = from_expression(name, entry["layout"], entry.get("description", ""), str(path))
        except LayoutError as error:
            raise LayoutError(f"{path}: [{name}]: {error}") from error
    return layouts
