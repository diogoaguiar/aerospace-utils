"""The `aeroutils` command-line interface."""

from __future__ import annotations

import argparse
import shutil
import sys
from typing import Optional, Sequence

from . import __version__, arrange, ops, render
from .client import Aerospace, AerospaceError
from .errors import UsageError
from .layouts import Layout, load_layouts, user_layouts_path

PROG = "aeroutils"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Utilities for the AeroSpace tiling window manager.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(metavar="COMMAND", required=True)

    listing = commands.add_parser(
        "list", aliases=["ls"],
        help="show workspaces and their windows",
        description="Show every workspace with its monitor and windows. "
        "'*' marks the focused workspace, '+' the other visible ones.",
    )
    listing.set_defaults(handler=show_list)

    swap = commands.add_parser(
        "swap",
        help="exchange all windows between two workspaces",
        description="Exchange all windows between workspaces A and B.",
    )
    swap.add_argument("a", metavar="A")
    swap.add_argument("b", metavar="B")
    swap.set_defaults(
        mapping=lambda a: ops.swap_mapping(a.a, a.b),
        verbs=("Swapped", "swap"),
        subject=lambda a: f"workspaces {a.a} and {a.b}",
    )

    move = commands.add_parser(
        "move", aliases=["mv"],
        help="move all windows from one workspace to another",
        description="Move all windows on SOURCE to TARGET, joining any windows already there.",
    )
    move.add_argument("source", metavar="SOURCE")
    move.add_argument("target", metavar="TARGET")
    move.set_defaults(
        mapping=lambda a: ops.move_mapping(a.source, a.target),
        verbs=("Moved", "move"),
        subject=lambda a: f"windows from workspace {a.source} to {a.target}",
    )

    reorder = commands.add_parser(
        "reorder",
        help="give several workspaces a new order",
        description="List workspaces in the order you want their windows to appear. "
        "The listed numbers, sorted, are the slots to fill: "
        "'reorder 3 1 2' moves 3 to 1, 1 to 2 and 2 to 3.",
    )
    reorder.add_argument("order", nargs="+", metavar="WORKSPACE")
    reorder.set_defaults(
        mapping=lambda a: ops.reorder_mapping(a.order),
        verbs=("Reordered", "reorder"),
        subject=lambda a: "workspaces {} as {}".format(
            " ".join(sorted(a.order, key=ops.natural_key)), " ".join(a.order)
        ),
    )

    for command in (swap, move, reorder):
        command.set_defaults(handler=run_remap)
        command.add_argument(
            "-n", "--dry-run", action="store_true",
            help="show what would move without moving anything",
        )
        command.add_argument(
            "-f", "--follow", action="store_true",
            help="focus follows your windows to their new workspace "
            "(default: stay on the current workspace)",
        )

    catalog = commands.add_parser(
        "layouts",
        help="show the available layouts",
        description="Draw every layout. With WORKSPACE, show only the layouts that fit its "
        "tiled windows, filled with them. Custom layouts are read from "
        f"{user_layouts_path()}.",
    )
    catalog.add_argument("workspace", nargs="?", metavar="WORKSPACE")
    catalog.set_defaults(handler=show_layouts)

    layout = commands.add_parser(
        "layout",
        help="arrange a workspace's windows in a layout",
        description="Rebuild a workspace's tiling tree in the named layout. Slot 1 is the "
        "biggest; it gets the focused window unless --order says otherwise. "
        "Floating windows are left alone.",
    )
    layout.add_argument("name", metavar="NAME")
    layout.add_argument("workspace", nargs="?", metavar="WORKSPACE", help="default: the focused workspace")
    layout.add_argument(
        "-o", "--order", action="append", default=[], metavar="APP_OR_ID",
        help="fill slots in this order: an app name (substring) or window id, "
        "repeatable or comma-separated",
    )
    layout.add_argument("-n", "--dry-run", action="store_true", help="show the result without changing anything")
    layout.add_argument("-v", "--verbose", action="store_true", help="print the aerospace commands")
    layout.set_defaults(handler=apply_layout)
    return parser


def show_list(client: Aerospace, args: argparse.Namespace) -> int:
    windows: dict[str, list[ops.Window]] = {}
    for window in client.list_windows():
        windows.setdefault(window.workspace, []).append(window)

    rows = [("", "WS", "MONITOR", "WINDOWS")]
    for ws in sorted(client.list_workspaces(), key=lambda ws: ops.natural_key(ws.name)):
        marker = "*" if ws.focused else "+" if ws.visible else ""
        on_ws = windows.get(ws.name, [])
        rows.append((marker, ws.name, ws.monitor, f"{len(on_ws)}  {ops.summarize_apps(on_ws)}"))

    name_width = max(len(row[1]) for row in rows)
    monitor_width = max(len(row[2]) for row in rows)
    for marker, name, monitor, contents in rows:
        print(f"{marker:1} {name:<{name_width}}  {monitor:<{monitor_width}}  {contents}".rstrip())
    return 0


def count_windows(count: int) -> str:
    return f"{count} window" if count == 1 else f"{count} windows"


def run_remap(client: Aerospace, args: argparse.Namespace) -> int:
    mapping = args.mapping(args)
    if not mapping:
        print("Nothing to move: the workspaces are already in that order.")
        return 0

    result = ops.remap(client, mapping, dry_run=args.dry_run, follow=args.follow)
    if not result.moves:
        noun, verb = ("workspace", "is") if len(mapping) == 1 else ("workspaces", "are")
        print(f"Nothing to move: {noun} {', '.join(mapping)} {verb} empty.")
        return 0

    done, planned = args.verbs
    moved = len(result.moves) - len(result.failures)
    if args.dry_run:
        print(f"Would {planned} {args.subject(args)} ({count_windows(len(result.moves))}):")
    else:
        print(f"{done} {args.subject(args)} ({count_windows(moved)}):")

    for source, target in mapping.items():
        on_source = [m.window for m in result.moves if m.window.workspace == source]
        print(f"  {source} -> {target}  {ops.summarize_apps(on_source) or '(empty)'}")

    for move, error in result.failures:
        window = move.window
        print(
            f"{PROG}: could not move window {window.id} ({window.app}) to {move.target}: {error}",
            file=sys.stderr,
        )
    return 1 if result.failures else 0


def _diagram_size(client: Aerospace, workspace: Optional[str]) -> tuple[int, int]:
    size = client.workspace_size(workspace) if workspace is not None else None
    return render.canvas_size(size[0] / size[1] if size else None)


def _block(layout: Layout, windows: int, labels: dict, size: tuple[int, int]) -> list[str]:
    diagram = render.draw(layout.tree(windows), labels, size)
    title = f"{layout.name}  ({layout.windows_label})"
    width = max(len(diagram[0]), len(title))
    return [title, render.fit(layout.description, width), *diagram]


def show_layouts(client: Aerospace, args: argparse.Namespace) -> int:
    layouts = load_layouts()
    terminal_width = shutil.get_terminal_size((100, 24)).columns
    workspace = args.workspace

    if workspace is None:
        size = _diagram_size(client, None)
        blocks = [_block(l, l.example_windows, {}, size) for l in layouts.values()]
        print("\n".join(render.side_by_side(blocks, terminal_width)))
        print(f"\nApply one with: {PROG} layout NAME [WORKSPACE]")
        return 0

    tiled = [w for w in client.list_windows(workspace) if w.tiled]
    if not tiled:
        print(f"Workspace {workspace} has no tiled windows.")
        return 0
    ordered = arrange.order_windows(tiled, client.focused_window_id())
    labels = {number: w.app for number, w in enumerate(ordered, start=1)}
    fitting = [l for l in layouts.values() if l.fits(len(tiled))]
    print(f"Workspace {workspace}: {count_windows(len(tiled))} ({ops.summarize_apps(tiled)})\n")
    size = _diagram_size(client, workspace)
    blocks = [_block(l, len(tiled), labels, size) for l in fitting]
    print("\n".join(render.side_by_side(blocks, terminal_width)))
    print(f"\nApply one with: {PROG} layout NAME {workspace}")
    return 0


def apply_layout(client: Aerospace, args: argparse.Namespace) -> int:
    layouts = load_layouts()
    layout = layouts.get(args.name)
    if layout is None:
        raise UsageError(f"unknown layout '{args.name}'. Available: {', '.join(layouts)}")
    workspace = args.workspace or client.focused_workspace()
    if workspace is None:
        raise UsageError("no focused workspace; name one")
    order = [p.strip() for value in args.order for p in value.split(",") if p.strip()]

    arrangement = arrange.plan(client, layout, workspace, order)
    if not args.dry_run:
        arrange.apply(client, arrangement)

    verb = "Would apply" if args.dry_run else "Applied"
    print(f"{verb} {layout.name} to workspace {workspace} ({count_windows(len(arrangement.windows))}):")
    labels = {number: w.app for number, w in arrangement.windows.items()}
    print("\n".join(line.rstrip() for line in render.draw(arrangement.tree, labels, _diagram_size(client, workspace))))
    if arrangement.skipped:
        print(f"Left {count_windows(len(arrangement.skipped))} alone (floating or minimized).")
    if args.verbose:
        print("\naerospace commands:")
        for command in arrangement.commands:
            print("  aerospace " + " ".join(command))
    return 0


def main(argv: Optional[Sequence[str]] = None, client: Optional[Aerospace] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(client or Aerospace(), args)
    except UsageError as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 2
    except AerospaceError as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return 1
