"""The `aeroutils` command-line interface."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__, ops
from .client import Aerospace, AerospaceError

PROG = "aeroutils"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Utilities for the AeroSpace tiling window manager.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(metavar="COMMAND", required=True)

    commands.add_parser(
        "list", aliases=["ls"],
        help="show workspaces and their windows",
        description="Show every workspace with its monitor and windows. "
        "'*' marks the focused workspace, '+' the other visible ones.",
    )

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
        command.add_argument(
            "-n", "--dry-run", action="store_true",
            help="show what would move without moving anything",
        )
        command.add_argument(
            "-f", "--follow", action="store_true",
            help="focus follows your windows to their new workspace "
            "(default: stay on the current workspace)",
        )
    return parser


def show_list(client: Aerospace) -> int:
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


def run_remap(client: Aerospace, args: argparse.Namespace, mapping: dict[str, str]) -> int:
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


def main(argv: Optional[Sequence[str]] = None, client: Optional[Aerospace] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    mapping = None
    if "mapping" in args:
        try:
            mapping = args.mapping(args)
        except ValueError as error:
            print(f"{PROG}: error: {error}", file=sys.stderr)
            return 2

    client = client or Aerospace()
    try:
        if mapping is None:
            return show_list(client)
        return run_remap(client, args, mapping)
    except AerospaceError as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return 1
