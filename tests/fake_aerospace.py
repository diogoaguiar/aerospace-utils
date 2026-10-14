"""In-memory stand-in for the `aerospace` CLI.

It receives the same argv the real client would send, so tests exercise
argument building and JSON parsing as well as the operations themselves.
"""

from __future__ import annotations

import json
from typing import Sequence

from aerospace_utils.client import AerospaceError


class FakeAerospace:
    def __init__(self, windows, workspaces, focused_workspace="1", focused_window=None):
        """
        windows: iterable of (window_id, workspace, app_name, title)
        workspaces: iterable of (name, monitor_name), in display order
        """
        self.windows = {
            wid: {"workspace": ws, "app-name": app, "window-title": title}
            for wid, ws, app, title in windows
        }
        self.monitors = dict(workspaces)
        self.focused_workspace = focused_workspace
        self.focused_window = focused_window
        self.calls: list[list[str]] = []
        self.broken_window_ids: set[int] = set()

    def workspace_of(self, window_id: int) -> str:
        return self.windows[window_id]["workspace"]

    def windows_in(self, workspace: str) -> list[int]:
        return sorted(wid for wid, w in self.windows.items() if w["workspace"] == workspace)

    def moves(self) -> list[list[str]]:
        return [c for c in self.calls if c[0] == "move-node-to-workspace"]

    def __call__(self, args: Sequence[str]) -> str:
        args = list(args)
        self.calls.append(args)
        command, rest = args[0], args[1:]
        handler = getattr(self, "_" + command.replace("-", "_"), None)
        if handler is None:
            raise AerospaceError(f"fake aerospace: unsupported command {command}")
        return handler(rest)

    def _list_windows(self, rest):
        if "--focused" in rest:
            if self.focused_window is None:
                raise AerospaceError("No window is focused")
            selected = [self.focused_window]
        else:
            selected = sorted(
                self.windows,
                key=lambda wid: (self.windows[wid]["app-name"], self.windows[wid]["window-title"]),
            )
        return json.dumps([{"window-id": wid, **self.windows[wid]} for wid in selected])

    def _list_workspaces(self, rest):
        names = list(self.monitors)
        names += sorted({w["workspace"] for w in self.windows.values()} - set(names))
        if "--focused" in rest:
            names = [self.focused_workspace]
        visible = {self.focused_workspace}
        return json.dumps(
            [
                {
                    "workspace": name,
                    "monitor-name": self.monitors.get(name, "Display"),
                    "workspace-is-focused": name == self.focused_workspace,
                    "workspace-is-visible": name in visible,
                }
                for name in names
            ]
        )

    def _move_node_to_workspace(self, rest):
        window_id = int(rest[rest.index("--window-id") + 1])
        target = rest[-1]
        if window_id not in self.windows or window_id in self.broken_window_ids:
            raise AerospaceError(f"Invalid <window-id> {window_id} passed to --window-id")
        self.windows[window_id]["workspace"] = target
        return ""

    def _workspace(self, rest):
        self.focused_workspace = rest[-1]
        return ""

    def _focus(self, rest):
        window_id = int(rest[rest.index("--window-id") + 1])
        self.focused_window = window_id
        self.focused_workspace = self.windows[window_id]["workspace"]
        return ""
