#!/usr/bin/env python3
"""Live layout checks against the real AeroSpace.

WARNING: this changes your desktop while it runs. It opens throwaway test
windows (a tiny app built from probe_app.swift), lays them out on a temporary
workspace with `aeroutils layout`, briefly shows that workspace to read where
the windows really are, and compares that with what each layout should look
like. Your own windows are not moved, but the screen that shows the test
workspace flips to it for about half a second per check, and focus and the
mouse can jump. Focus is put back at the end.

Needs Xcode command line tools (swiftc). Run from the repository root with
the development environment:

    .venv/bin/python tests/live/run_live_checks.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from aerospace_utils.layouts import load_layouts, unit_rects, slots  # noqa: E402

TEST_WS = "aeroutils-test"
PARK_WS = "aeroutils-park"
WINDOWS = 6
TOLERANCE = 0.02  # fraction of the workspace size; covers gaps and rounding
WORK = Path(tempfile.gettempdir()) / "aeroutils-live"
FRAMES = WORK / "frames.json"
CUSTOM = {"uneven": "h[1:w, 3:v[1:w, 3:w]]", "ratios": "h[1:w, 2:w, 3:w]"}

# (layout, tiled windows, how): "hidden" builds while the test workspace is off screen.
CASES = [
    ("columns", 3, "hidden"),
    ("rows", 3, "hidden"),
    ("grid", 5, "hidden"),
    ("main-left", 4, "hidden"),
    ("main-left", 4, "visible"),
    ("main-right", 3, "hidden"),
    ("main-top", 3, "hidden"),
    ("main-center", 5, "hidden"),
    ("main-center", 5, "visible"),
    ("2x2", 4, "hidden"),
    ("3x2", 6, "hidden"),
    ("2x3", 6, "hidden"),
    ("grid", 6, "reapply"),  # rebuild over the 2x3 just applied
    ("uneven", 3, "hidden"),
    ("ratios", 3, "visible"),
    ("columns", 5, "floating"),  # probe-6 floating must stay untouched
]


def aero(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["aerospace", *args], capture_output=True, text=True)
    if check and proc.returncode:
        raise RuntimeError(f"aerospace {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def aeroutils(*args: str) -> None:
    env = dict(os.environ, XDG_CONFIG_HOME=str(WORK / "config"), PYTHONPATH=str(ROOT / "src"))
    proc = subprocess.run([sys.executable, "-m", "aerospace_utils", *args], capture_output=True, text=True, env=env)
    if proc.returncode:
        raise RuntimeError(f"aeroutils {' '.join(args)} failed: {proc.stderr.strip()}")


def build_probe_app() -> Path:
    app = WORK / "AeroProbe.app" / "Contents"
    binary = app / "MacOS" / "aeroprobe"
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        (app / "Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            "<key>CFBundleIdentifier</key><string>dev.aeroutils.probe</string>"
            "<key>CFBundleName</key><string>AeroProbe</string>"
            "<key>CFBundleExecutable</key><string>aeroprobe</string>"
            "<key>CFBundlePackageType</key><string>APPL</string></dict></plist>\n"
        )
        subprocess.run(["swiftc", "-O", "-o", str(binary), str(Path(__file__).with_name("probe_app.swift"))], check=True)
    return binary


def probe_windows() -> dict[int, str]:
    """probe number -> window id"""
    out = aero("list-windows", "--all", "--format", "%{window-id}|%{window-title}")
    return {
        int(title.rsplit("-", 1)[1]): wid
        for wid, title in (line.split("|", 1) for line in out.splitlines())
        if title.startswith("probe-")
    }


def frames() -> dict[int, tuple[float, float, float, float]]:
    """probe number -> (x, top, width, height), top measured downward."""
    data = json.loads(FRAMES.read_text())
    return {int(f["title"].rsplit("-", 1)[1]): (f["x"], -(f["y"] + f["h"]), f["w"], f["h"]) for f in data}


def show(workspace: str, back_to: str) -> dict:
    aero("workspace", workspace)
    time.sleep(0.6)
    seen = frames()
    aero("workspace", back_to)
    return seen


def expected(layout_name: str, count: int) -> dict[int, tuple[float, float, float, float]]:
    tree = load_layouts()[layout_name].tree(count)
    return {slot.index: rect for slot, rect in zip(slots(tree), unit_rects(tree))}


def compare(want: dict, seen: dict, numbers: list[int]) -> list[str]:
    boxes = [seen[n] for n in numbers]
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    width = max(b[0] + b[2] for b in boxes) - left
    height = max(b[1] + b[3] for b in boxes) - top
    problems = []
    for slot, number in enumerate(numbers, start=1):
        x, y, w, h = seen[number]
        got = ((x - left) / width, (y - top) / height, w / width, h / height)
        if any(abs(g - e) > TOLERANCE for g, e in zip(got, want[slot])):
            problems.append(
                f"slot {slot} (probe-{number}): expected {tuple(round(v, 2) for v in want[slot])}, "
                f"got {tuple(round(v, 2) for v in got)}"
            )
    return problems


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "config" / "aeroutils").mkdir(parents=True, exist_ok=True)
    (WORK / "config" / "aeroutils" / "layouts.toml").write_text(
        "".join(f'[{name}]\nlayout = "{expr}"\n' for name, expr in CUSTOM.items())
    )
    binary = build_probe_app()

    home_ws = aero("list-workspaces", "--focused").strip()
    home_win = aero("list-windows", "--focused", "--format", "%{window-id}", check=False).strip()
    app = subprocess.Popen([str(binary), str(WINDOWS), str(FRAMES)])
    results = []
    try:
        ids: dict[int, str] = {}
        for _ in range(100):
            time.sleep(0.1)
            for number, wid in probe_windows().items():
                if number not in ids:
                    ids[number] = wid
                    aero("move-node-to-workspace", "--window-id", wid, "--", PARK_WS)
            if len(ids) == WINDOWS:
                break
        if len(ids) != WINDOWS:
            raise RuntimeError(f"only {len(ids)} of {WINDOWS} test windows appeared")
        aero("workspace", home_ws)
        if home_win:
            aero("focus", "--window-id", home_win, check=False)

        for name, count, how in CASES:
            wanted = list(range(1, count + 1)) if how != "floating" else list(range(1, 6))
            if how != "reapply":
                for number in range(1, WINDOWS + 1):
                    target = TEST_WS if number in wanted or how == "floating" else PARK_WS
                    aero("move-node-to-workspace", "--window-id", ids[number], "--", target)
                aero("flatten-workspace-tree", "--workspace", TEST_WS, check=False)
            if how == "floating":
                aero("layout", "--window-id", ids[6], "floating")
            if how == "visible":
                aero("workspace", TEST_WS)
                time.sleep(0.3)
            # Pin slot k to probe-k, whatever window happens to be focused.
            aeroutils("layout", name, TEST_WS, "--order", ",".join(ids[n] for n in wanted))
            seen = show(TEST_WS, home_ws)
            problems = compare(expected(name, count), seen, wanted)
            if how == "floating":
                layout = aero("list-windows", "--workspace", TEST_WS, "--format", "%{window-title}=%{window-layout}")
                if "probe-6=floating" not in layout:
                    problems.append("probe-6 is no longer floating")
                aero("layout", "--window-id", ids[6], "tiling")
            results.append((f"{name} ({count} windows, {how})", problems))
    finally:
        app.terminate()
        app.wait(timeout=5)
        aero("workspace", home_ws, check=False)
        if home_win:
            aero("focus", "--window-id", home_win, check=False)

    failed = 0
    for label, problems in results:
        print(("FAIL " if problems else "ok   ") + label)
        for problem in problems:
            print("       " + problem)
        failed += bool(problems)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
