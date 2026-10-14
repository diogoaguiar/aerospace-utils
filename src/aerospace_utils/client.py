"""Thin wrapper around the `aerospace` command-line client.

All interaction with AeroSpace goes through a *runner*: a callable that takes
the argv after `aerospace` and returns stdout. The default runner shells out
to the real binary; tests pass a fake one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

Runner = Callable[[Sequence[str]], str]

INSTALL_URL = "https://github.com/nikitabobko/AeroSpace"


class AerospaceError(RuntimeError):
    """The aerospace CLI is missing or a command failed."""


@dataclass(frozen=True)
class Window:
    id: int
    workspace: str
    app: str
    title: str
    layout: str = ""  # parent container layout, e.g. h_tiles, or "floating"

    @property
    def tiled(self) -> bool:
        return self.layout.endswith(("_tiles", "_accordion"))


@dataclass(frozen=True)
class Workspace:
    name: str
    monitor: str
    focused: bool
    visible: bool


def subprocess_runner(binary: str = "aerospace") -> Runner:
    def run(args: Sequence[str]) -> str:
        path = shutil.which(binary)
        if path is None:
            raise AerospaceError(
                f"'{binary}' not found on PATH. Is AeroSpace installed? See {INSTALL_URL}"
            )
        proc = subprocess.run([path, *args], capture_output=True, text=True)
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout).strip() or f"exit status {proc.returncode}"
            raise AerospaceError(f"aerospace {' '.join(args)}: {message}")
        return proc.stdout

    return run


def screen_sizes() -> list[tuple[float, float]]:
    """Usable size of each display, in NSScreen.screens order. Empty if unavailable."""
    script = (
        'ObjC.import("AppKit"); const out = []; const screens = $.NSScreen.screens;'
        "for (let i = 0; i < screens.count; i++) {"
        " const f = screens.objectAtIndex(i).visibleFrame; out.push([f.size.width, f.size.height]); }"
        "JSON.stringify(out)"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        return [tuple(size) for size in json.loads(proc.stdout)] if proc.returncode == 0 else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


class Aerospace:
    def __init__(
        self,
        runner: Optional[Runner] = None,
        screens: Optional[Callable[[], list[tuple[float, float]]]] = None,
    ):
        self._run = runner or subprocess_runner()
        self._screens = screens or screen_sizes

    def run(self, *args: str) -> str:
        return self._run(args)

    def _json(self, *args: str) -> list:
        return json.loads(self._run(args) or "[]")

    def list_windows(self, workspace: Optional[str] = None) -> list[Window]:
        scope = ["--workspace", workspace] if workspace is not None else ["--all"]
        rows = self._json(
            "list-windows", *scope, "--json",
            "--format", "%{window-id} %{workspace} %{app-name} %{window-title} %{window-layout}",
        )
        return [
            Window(
                row["window-id"], row["workspace"], row["app-name"], row["window-title"],
                row.get("window-layout", ""),
            )
            for row in rows
        ]

    def list_workspaces(self) -> list[Workspace]:
        rows = self._json(
            "list-workspaces", "--all", "--json",
            "--format", "%{workspace} %{monitor-name} %{workspace-is-focused} %{workspace-is-visible}",
        )
        return [
            Workspace(
                row["workspace"],
                row["monitor-name"],
                row["workspace-is-focused"],
                row["workspace-is-visible"],
            )
            for row in rows
        ]

    def workspace_size(self, workspace: str) -> Optional[tuple[float, float]]:
        """Usable width and height of the display a workspace is on, if known."""
        rows = self._json(
            "list-workspaces", "--all", "--json",
            "--format", "%{workspace} %{monitor-appkit-nsscreen-screens-id}",
        )
        index = next((row["monitor-appkit-nsscreen-screens-id"] for row in rows if row["workspace"] == workspace), None)
        sizes = self._screens()
        if index is None or not 0 < index <= len(sizes):
            return None
        return sizes[index - 1]

    def focused_workspace(self) -> Optional[str]:
        rows = self._json("list-workspaces", "--focused", "--json", "--format", "%{workspace}")
        return rows[0]["workspace"] if rows else None

    def focused_window_id(self) -> Optional[int]:
        try:
            rows = self._json("list-windows", "--focused", "--json", "--format", "%{window-id}")
        except AerospaceError:
            # AeroSpace errors out when the focused workspace has no windows.
            return None
        return rows[0]["window-id"] if rows else None

    def move_window(self, window_id: int, workspace: str) -> None:
        self._run(["move-node-to-workspace", "--window-id", str(window_id), "--", workspace])

    def focus_workspace(self, workspace: str) -> None:
        self._run(["workspace", "--", workspace])

    def focus_window(self, window_id: int) -> None:
        self._run(["focus", "--window-id", str(window_id)])
