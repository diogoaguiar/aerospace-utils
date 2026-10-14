"""In-memory stand-in for the `aerospace` CLI.

It receives the same argv the real client sends, so tests exercise argument
building and JSON parsing as well as the operations. Workspaces hold real
tiling trees, and the tree commands follow AeroSpace's own implementation
(v0.21): appending on move-node-to-workspace, join-with, deep move into a
group after its most recent child, weight-based resize and balance, and
normalization of single-child and same-direction containers.
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

from aerospace_utils.client import AerospaceError

_AXIS = {"left": "h", "right": "h", "up": "v", "down": "v"}
_FLIP = {"h": "v", "v": "h"}


class Win:
    def __init__(self, wid: int, app: str, title: str):
        self.id, self.app, self.title = wid, app, title
        self.parent: Optional[Box] = None
        self.weight = 1.0
        self.floating_on: Optional[str] = None


class Box:
    def __init__(self, orientation: str):
        self.orientation = orientation
        self.children: list = []
        self.parent: Optional[Box] = None
        self.weight = 1.0
        self.mru = None


class FakeAerospace:
    def __init__(self, windows, workspaces, focused_workspace="1", focused_window=None):
        """
        windows: iterable of (window_id, workspace, app_name, title)
        workspaces: iterable of (name, monitor_name), in display order
        """
        self.monitors = dict(workspaces)
        self.roots: dict[str, Box] = {}
        self.wins: dict[int, Win] = {}
        for wid, ws, app, title in windows:
            self.wins[wid] = win = Win(wid, app, title)
            self._bind(win, self._root(ws))
        self.focused_workspace = focused_workspace
        self.focused_window = focused_window
        self.calls: list[list[str]] = []
        self.broken_window_ids: set[int] = set()
        self.fail_once = None  # predicate on argv; the first matching call fails

    # --- inspection helpers for tests ---

    def workspace_of(self, window_id: int) -> str:
        win = self.wins[window_id]
        if win.floating_on is not None:
            return win.floating_on
        node = win
        while node.parent is not None:
            node = node.parent
        return next(name for name, root in self.roots.items() if root is node)

    def windows_in(self, workspace: str) -> list[int]:
        return sorted(wid for wid in self.wins if self.workspace_of(wid) == workspace)

    def moves(self) -> list[list[str]]:
        return [c for c in self.calls if c[0] == "move-node-to-workspace"]

    def tree(self, workspace: str):
        """The tiling tree as nested ("h"|"v", [children]) tuples with window ids."""
        def describe(node):
            if isinstance(node, Win):
                return node.id
            return (node.orientation, [describe(c) for c in node.children])
        return describe(self._root(workspace))

    def sizes(self, workspace: str, width: float, height: float) -> dict[int, tuple[float, float]]:
        """Window sizes the way AeroSpace lays a workspace out (gaps ignored)."""
        out: dict[int, tuple[float, float]] = {}

        def layout(node, w, h):
            if isinstance(node, Win):
                out[node.id] = (w, h)
                return
            along = w if node.orientation == "h" else h
            delta = (along - sum(c.weight for c in node.children)) / len(node.children)
            for child in node.children:
                child.weight += delta
                if node.orientation == "h":
                    layout(child, child.weight, h)
                else:
                    layout(child, w, child.weight)

        layout(self._root(workspace), width, height)
        return out

    def make_floating(self, window_id: int) -> None:
        win = self.wins[window_id]
        workspace = self.workspace_of(window_id)
        self._unbind(win)
        win.floating_on = workspace

    # --- tree mechanics ---

    def _root(self, workspace: str) -> Box:
        return self.roots.setdefault(workspace, Box("h"))

    def _bind(self, node, box: Box, index: Optional[int] = None) -> None:
        if box.children:
            node.weight = sum(c.weight for c in box.children) / len(box.children)
        box.children.insert(len(box.children) if index is None else index, node)
        node.parent = box
        box.mru = node

    def _detach(self, node) -> int:
        box = node.parent
        index = box.children.index(node)
        box.children.remove(node)
        node.parent = None
        if box.mru is node:
            box.mru = box.children[-1] if box.children else None
        return index

    def _unbind(self, node) -> None:
        workspace = self.workspace_of(node.id) if isinstance(node, Win) else None
        self._detach(node)
        if workspace is not None:
            self._normalize(workspace)

    def _normalize(self, workspace: str) -> None:
        def flatten(box: Box, is_root: bool) -> None:
            if len(box.children) == 1 and (isinstance(box.children[0], Box) or not is_root):
                child = box.children[0]
                self._detach(child)
                if is_root:
                    name = next(n for n, r in self.roots.items() if r is box)
                    self.roots[name] = child
                    flatten(child, True)
                else:
                    parent = box.parent
                    index = self._detach(box)
                    child.weight = box.weight
                    parent.children.insert(index, child)
                    child.parent = parent
                    if parent.mru is None or parent.mru is box:
                        parent.mru = child
                    if isinstance(child, Box):
                        flatten(child, False)
                return
            for child in list(box.children):
                if isinstance(child, Box):
                    flatten(child, False)
            if not box.children and not is_root:
                self._detach(box)

        def alternate(box: Box) -> None:
            for child in box.children:
                if isinstance(child, Box):
                    if child.orientation == box.orientation:
                        child.orientation = _FLIP[box.orientation]
                    alternate(child)

        flatten(self.roots[workspace], True)
        alternate(self.roots[workspace])

    def _neighbor(self, win: Win, direction: str):
        """(parent, index) of the closest ancestor with a child in `direction`, like AeroSpace."""
        step = 1 if direction in ("right", "down") else -1
        node = win
        while node.parent is not None:
            box = node.parent
            index = box.children.index(node)
            if box.orientation == _AXIS[direction] and 0 <= index + step < len(box.children):
                return box, index, step
            node = box
        raise AerospaceError(f"fake aerospace: nothing {direction} of window {win.id}")

    # --- CLI dispatch ---

    def __call__(self, args: Sequence[str]) -> str:
        args = list(args)
        self.calls.append(args)
        if self.fail_once is not None and self.fail_once(args):
            self.fail_once = None
            raise AerospaceError(f"fake aerospace: injected failure for {' '.join(args)}")
        command, rest = args[0], args[1:]
        handler = getattr(self, "_" + command.replace("-", "_"), None)
        if handler is None:
            raise AerospaceError(f"fake aerospace: unsupported command {command}")
        return handler(rest)

    def _window_arg(self, rest) -> Win:
        window_id = int(rest[rest.index("--window-id") + 1])
        if window_id not in self.wins or window_id in self.broken_window_ids:
            raise AerospaceError(f"Invalid <window-id> {window_id} passed to --window-id")
        return self.wins[window_id]

    def _layout_of(self, win: Win) -> str:
        if win.floating_on is not None:
            return "floating"
        return f"{win.parent.orientation}_tiles"

    def _list_windows(self, rest):
        if "--focused" in rest:
            if self.focused_window is None:
                raise AerospaceError("No window is focused")
            selected = [self.focused_window]
        else:
            selected = sorted(self.wins, key=lambda wid: (self.wins[wid].app, self.wins[wid].title))
            if "--workspace" in rest:
                workspace = rest[rest.index("--workspace") + 1]
                selected = [wid for wid in selected if self.workspace_of(wid) == workspace]
        return json.dumps([
            {
                "window-id": wid,
                "workspace": self.workspace_of(wid),
                "app-name": self.wins[wid].app,
                "window-title": self.wins[wid].title,
                "window-layout": self._layout_of(self.wins[wid]),
            }
            for wid in selected
        ])

    def _list_workspaces(self, rest):
        names = list(self.monitors)
        names += sorted({self.workspace_of(wid) for wid in self.wins} - set(names))
        if "--focused" in rest:
            names = [self.focused_workspace]
        return json.dumps([
            {
                "workspace": name,
                "monitor-name": self.monitors.get(name, "Display"),
                "monitor-appkit-nsscreen-screens-id": 1,
                "workspace-is-focused": name == self.focused_workspace,
                "workspace-is-visible": name == self.focused_workspace,
            }
            for name in names
        ])

    def _move_node_to_workspace(self, rest):
        win = self._window_arg(rest)
        target = rest[-1]
        if win.floating_on is not None:
            win.floating_on = target
            return ""
        self._unbind(win)
        self._bind(win, self._root(target))
        self._normalize(target)
        return ""

    def _workspace(self, rest):
        self.focused_workspace = rest[-1]
        return ""

    def _focus(self, rest):
        win = self._window_arg(rest)
        self.focused_window = win.id
        self.focused_workspace = self.workspace_of(win.id)
        return ""

    def _layout(self, rest):
        assert "--workspace" in rest and "--root" in rest, "fake supports only layout --workspace W --root"
        workspace = rest[rest.index("--workspace") + 1]
        self._root(workspace).orientation = rest[-1][0]
        self._normalize(workspace)
        return ""

    def _join_with(self, rest):
        win = self._window_arg(rest)
        direction = rest[-1]
        box, index, step = self._neighbor(win, direction)
        target = box.children[index + step]
        group = Box(_FLIP[box.orientation])
        target_index = self._detach(target)
        group.weight = target.weight
        box.children.insert(target_index, group)
        group.parent = box
        self._detach(win)
        self._bind(target, group, 0)
        self._bind(win, group, 0 if step > 0 else None)
        self._normalize(self.workspace_of(win.id))
        return ""

    def _move(self, rest):
        win = self._window_arg(rest)
        direction = rest[-1]
        box, index, step = self._neighbor(win, direction)
        target = box.children[index + step]
        if isinstance(target, Win):
            box.children[index], box.children[index + step] = target, win
        else:
            while isinstance(target, Box) and target.orientation != _AXIS[direction]:
                target = target.mru
            self._detach(win)
            if isinstance(target, Box):
                self._bind(win, target, 0)
            else:
                self._bind(win, target.parent, target.parent.children.index(target) + 1)
        self._normalize(self.workspace_of(win.id))
        return ""

    def _balance_sizes(self, rest):
        def balance(box: Box):
            for child in box.children:
                child.weight = 1.0
                if isinstance(child, Box):
                    balance(child)
        balance(self._root(rest[rest.index("--workspace") + 1]))
        return ""

    def _resize(self, rest):
        win = self._window_arg(rest)
        dimension, amount = rest[-2], rest[-1]
        axis = "h" if dimension == "width" else "v"
        node = win
        while node.parent is not None and node.parent.orientation != axis:
            node = node.parent
        if node.parent is None:
            raise AerospaceError("fake aerospace: nothing to resize")
        diff = float(amount) if amount[0] in "+-" else float(amount) - node.weight
        siblings = [c for c in node.parent.children if c is not node]
        for sibling in siblings:
            sibling.weight -= diff / len(siblings)
        node.weight += diff
        return ""
