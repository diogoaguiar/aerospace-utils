"""Apply a layout to a workspace by rebuilding its tiling tree.

AeroSpace has no command to load a tree, so the tree is rebuilt with the
commands it has. Their behaviour, from AeroSpace's source:

- move-node-to-workspace appends the window to the end of the workspace root;
- join-with wraps a window and its neighbour in a new perpendicular group,
  with the joining window first;
- move into a perpendicular group puts the window right after the group's
  most recently added window.

So the windows leave the workspace, come back in a computed order, and get
grouped. A group of slots s1..sk arrives as s1, sk, s2, ..., s(k-1): s1 joins
sk, then s2..s(k-1) each move in after the previous one.

Sizes use relative resizes. balance-sizes sets every weight to 1, and when
AeroSpace lays a workspace out it adds the same amount to each weight, so only
the differences between weights matter. Relative resizes only change those
differences, which is why sizing works on hidden workspaces too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from .client import Aerospace, AerospaceError, Window
from .layouts import Layout, LayoutError, Slot, Split, slots

TMP_WORKSPACE = "aeroutils-tmp"

_FORWARD = {"h": "right", "v": "down"}
_BACKWARD = {"h": "left", "v": "up"}
_DIMENSION = {"h": "width", "v": "height"}


@dataclass
class Arrangement:
    workspace: str
    layout: Layout
    tree: Split
    windows: dict[int, Window]  # slot number -> window
    skipped: list[Window] = field(default_factory=list)  # floating and other non-tiled windows
    commands: list[list[str]] = field(default_factory=list)


def _matches(window: Window, pattern: str) -> bool:
    if pattern.isdigit():
        return window.id == int(pattern)
    return pattern.lower() in window.app.lower()


def order_windows(windows: Sequence[Window], focused_id: Optional[int], patterns: Sequence[str] = ()) -> list[Window]:
    """Windows in slot order: --order matches first, then the focused window, then the rest."""
    remaining = list(windows)
    ordered = []
    for pattern in patterns:
        match = next((w for w in remaining if _matches(w, pattern)), None)
        if match is None:
            raise LayoutError(f"no window left to match '{pattern}'")
        ordered.append(match)
        remaining.remove(match)
    focused = next((w for w in remaining if w.id == focused_id), None)
    if focused is not None:
        ordered.append(focused)
        remaining.remove(focused)
    return ordered + remaining


def _group_slots(node) -> list[Slot]:
    return [node] if isinstance(node, Slot) else slots(node)


def build_commands(
    workspace: str,
    tree: Split,
    window_ids: dict[int, int],
    size: Optional[tuple[float, float]] = None,
) -> list[list[str]]:
    """The aerospace commands that turn a workspace's tiled windows into `tree`."""
    wid = lambda slot: str(window_ids[slot.index])
    commands = [
        ["move-node-to-workspace", "--window-id", wid(slot), "--", TMP_WORKSPACE] for slot in slots(tree)
    ]

    for _, child in tree.children:
        group = _group_slots(child)
        arrival = group if len(group) < 2 else [group[0], group[-1], *group[1:-1]]
        commands += [["move-node-to-workspace", "--window-id", wid(slot), "--", workspace] for slot in arrival]

    commands.append(["layout", "--workspace", workspace, "--root", f"{tree.orientation}_tiles"])
    for _, child in tree.children:
        if isinstance(child, Split):
            first, *middle, _ = child.children
            commands.append(["join-with", "--window-id", wid(first[1]), _FORWARD[tree.orientation]])
            commands += [["move", "--window-id", wid(slot), _BACKWARD[tree.orientation]] for _, slot in middle]

    commands.append(["balance-sizes", "--workspace", workspace])
    if size is not None:
        width, height = size
        commands += _resize_commands(tree, width if tree.orientation == "h" else height, wid)
        for _, child in tree.children:
            if isinstance(child, Split):
                commands += _resize_commands(child, width if child.orientation == "h" else height, wid)
    return commands


def _resize_commands(split: Split, length: float, wid) -> list[list[str]]:
    """Relative resizes that give a split's children their share of `length`.

    `resize ... +a` grows one child by a and shrinks each sibling by a/(n-1).
    Leaving the child that should end up smallest untouched (m), child k needs
    a_k = (d_k - d_m) * (n - 1) / n, where d is each child's target deviation
    from an even split. All a_k are then >= 0.
    """
    weights = [w for w, _ in split.children]
    n = len(weights)
    deviations = [length * (w / sum(weights) - 1 / n) for w in weights]
    smallest = min(range(n), key=lambda i: deviations[i])
    commands = []
    for k, (_, child) in enumerate(split.children):
        grow = round((deviations[k] - deviations[smallest]) * (n - 1) / n)
        if k != smallest and grow > 0:
            handle = _group_slots(child)[0]
            commands.append(["resize", "--window-id", wid(handle), _DIMENSION[split.orientation], f"+{grow}"])
    return commands


def plan(client: Aerospace, layout: Layout, workspace: str, order: Sequence[str] = ()) -> Arrangement:
    windows = client.list_windows(workspace)
    tiled = [w for w in windows if w.tiled]
    if not tiled:
        raise LayoutError(f"workspace {workspace} has no tiled windows")
    tree = layout.tree(len(tiled))
    ordered = order_windows(tiled, client.focused_window_id(), order)
    by_slot = {number: window for number, window in enumerate(ordered, start=1)}
    commands = build_commands(
        workspace, tree, {n: w.id for n, w in by_slot.items()}, client.workspace_size(workspace)
    )
    skipped = [w for w in windows if not w.tiled]
    return Arrangement(workspace, layout, tree, by_slot, skipped, commands)


def apply(client: Aerospace, arrangement: Arrangement) -> None:
    """Run the arrangement's commands, then put focus back where it was.

    If a command fails, windows parked on the temporary workspace are moved back
    before the error is raised.
    """
    focused_workspace = client.focused_workspace()
    focused_window = client.focused_window_id()
    try:
        for command in arrangement.commands:
            client.run(*command)
    except AerospaceError:
        _rescue(client, arrangement.workspace)
        raise
    finally:
        if focused_workspace is not None:
            client.focus_workspace(focused_workspace)
        if focused_window is not None:
            try:
                client.focus_window(focused_window)
            except AerospaceError:
                pass


def _rescue(client: Aerospace, workspace: str) -> None:
    try:
        stranded = client.list_windows(TMP_WORKSPACE)
    except AerospaceError:
        return
    for window in stranded:
        try:
            client.move_window(window.id, workspace)
        except AerospaceError:
            pass
