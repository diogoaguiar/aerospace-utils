"""Workspace operations, independent of any user interface.

Every operation is a mapping from source workspace to target workspace:
all windows on a source move to its target. Windows are listed once, before
anything moves, so swaps and rotations need no temporary workspace.

AeroSpace has no command to move a workspace's tiling tree, so windows are
moved one by one and re-tiled on arrival. Nested splits and window order
inside a workspace are not preserved.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .client import Aerospace, AerospaceError, Window

__all__ = [
    "Move",
    "Result",
    "Window",
    "move_mapping",
    "natural_key",
    "plan",
    "remap",
    "reorder_mapping",
    "summarize_apps",
    "swap_mapping",
]


@dataclass(frozen=True)
class Move:
    window: Window
    target: str


@dataclass
class Result:
    mapping: dict[str, str]
    moves: list[Move]
    failures: list[tuple[Move, str]] = field(default_factory=list)


def natural_key(name: str) -> tuple:
    """Sort numeric workspace names numerically, before any named ones."""
    return (0, int(name), "") if name.isdigit() else (1, 0, name.lower())


def swap_mapping(a: str, b: str) -> dict[str, str]:
    if a == b:
        raise ValueError(f"cannot swap workspace {a} with itself")
    return {a: b, b: a}


def move_mapping(source: str, target: str) -> dict[str, str]:
    if source == target:
        raise ValueError(f"cannot move workspace {source} onto itself")
    return {source: target}


def reorder_mapping(order: Sequence[str]) -> dict[str, str]:
    """Give the listed workspaces' contents a new order.

    The listed workspace numbers, sorted, are the slots. The contents of the
    first listed workspace go to the lowest slot, the second to the next, and
    so on: `reorder_mapping(["3", "1", "2"])` moves 3 -> 1, 1 -> 2, 2 -> 3.
    """
    if len(order) < 2:
        raise ValueError("reorder needs at least two workspaces")
    duplicates = sorted({ws for ws in order if order.count(ws) > 1}, key=natural_key)
    if duplicates:
        raise ValueError(f"workspace listed more than once: {', '.join(duplicates)}")
    slots = sorted(order, key=natural_key)
    return {source: slot for source, slot in zip(order, slots) if source != slot}


def plan(mapping: dict[str, str], windows: Iterable[Window]) -> list[Move]:
    return [Move(w, mapping[w.workspace]) for w in windows if w.workspace in mapping]


def summarize_apps(windows: Iterable[Window]) -> str:
    counts = Counter(w.app for w in windows)
    return ", ".join(app if n == 1 else f"{app} ({n})" for app, n in counts.most_common())


def remap(
    client: Aerospace,
    mapping: dict[str, str],
    *,
    dry_run: bool = False,
    follow: bool = False,
) -> Result:
    """Move every window on each source workspace to its target.

    Focus stays on the workspace that was focused before. With `follow`,
    focus goes wherever that workspace's windows went instead.
    """
    result = Result(mapping, plan(mapping, client.list_windows()))
    if dry_run or not result.moves:
        return result

    focused_workspace = client.focused_workspace()
    focused_window = client.focused_window_id() if follow else None

    for move in result.moves:
        try:
            client.move_window(move.window.id, move.target)
        except AerospaceError as error:
            result.failures.append((move, str(error)))

    if focused_workspace is not None:
        target = mapping.get(focused_workspace, focused_workspace) if follow else focused_workspace
        client.focus_workspace(target)
    failed_ids = {move.window.id for move, _ in result.failures}
    if focused_window is not None and focused_window not in failed_ids:
        client.focus_window(focused_window)
    return result
