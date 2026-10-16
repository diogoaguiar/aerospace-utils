# aerospace-utils

Command-line utilities for the [AeroSpace](https://github.com/nikitabobko/AeroSpace) tiling window manager on macOS.

AeroSpace moves windows to other workspaces one at a time and builds layouts one split at a time. `aeroutils` works on whole workspaces instead:

- **Swap, move and reorder workspaces**, carrying every window along.
- **Apply layouts** (columns, grids, a main window with a stack, or your own) to all windows on a workspace at once, and preview them as diagrams in the terminal first.

## Requirements

- macOS with AeroSpace installed and running (the `aerospace` CLI on your `PATH`)
- Python 3.9 or newer (the macOS system `python3` is enough)
- [pipx](https://pipx.pypa.io). The install script installs it with Homebrew if it is missing.

## Install

```sh
git clone https://github.com/diogoaguiar/aerospace-utils.git
cd aerospace-utils
./install.sh
```

The default install is editable: `aeroutils` runs the code in this checkout, so a `git pull` is all an update needs. Keep the checkout where it is, or reinstall after moving it.

- `./install.sh --copy` installs a snapshot of the checkout instead.
- `./uninstall.sh` removes the command.

## Usage

```sh
aeroutils list              # workspaces, their monitors and windows
aeroutils swap 1 2          # exchange all windows between workspaces 1 and 2
aeroutils move 4 1          # move every window on 4 onto 1
aeroutils reorder 3 1 2     # 3 -> 1, 1 -> 2, 2 -> 3
aeroutils reorder 5 2 3 4   # put 5 at 2 and shift 2, 3 and 4 up by one
```

`swap`, `move` and `reorder` accept:

| Option | Effect |
| --- | --- |
| `-n`, `--dry-run` | Show what would move without moving anything. |
| `-f`, `--follow` | Focus follows your windows to their new workspace. Without it you stay on the workspace you were on. |

`ls` and `mv` are aliases for `list` and `move`. Run `aeroutils <command> --help` for details.

```text
$ aeroutils list
  WS  MONITOR    WINDOWS
+ 1   Secondary  1  Chat
* 2   Main       3  Terminal (2), Browser
  3   Main       0
$ aeroutils swap 1 2
Swapped workspaces 1 and 2 (4 windows):
  1 -> 2  Chat
  2 -> 1  Terminal (2), Browser
```

In `list`, `*` marks the focused workspace and `+` the other visible ones.

### How `reorder` reads

List the workspaces in the order you want their windows to end up. The same numbers, sorted, are the slots to fill. In `aeroutils reorder 3 1 2` the slots are 1, 2 and 3, so the windows from 3 fill slot 1, the windows from 1 fill slot 2 and the windows from 2 fill slot 3. Workspaces you don't list are left alone.

## Layouts

```sh
aeroutils layouts                    # draw every layout
aeroutils layouts 3                  # the layouts that fit workspace 3, filled with its windows
aeroutils layout main-left           # arrange the focused workspace
aeroutils layout grid 3              # arrange workspace 3
aeroutils layout main-left -o chrome # put Chrome in the main slot
```

```text
$ aeroutils layout main-left -n
Would apply main-left to workspace 2 (3 windows):
┌─────────────────────────┬────────────────┐
│                         │                │
│                         │                │
│                         │   2 Browser    │
│                         │                │
│                         │                │
│       1 Terminal        ├────────────────┤
│                         │                │
│                         │                │
│                         │     3 Chat     │
│                         │                │
│                         │                │
└─────────────────────────┴────────────────┘
```

| Layout | Windows | Shape |
| --- | --- | --- |
| `columns` | any | All windows side by side |
| `rows` | any | All windows stacked top to bottom |
| `grid` | any | Even grid, as square as possible |
| `main-left`, `main-right` | 2+ | Main window (60%) beside a stack of the rest |
| `main-top` | 2+ | Main window (60%) above a row of the rest |
| `main-center` | 3+ | Main window (50%) between two stacks |
| `2-rows` | 4+ | Two rows, with as many columns as it takes |
| `2-columns` | 4+ | Two columns, with as many rows as it takes |
| `2x2` | 4 | Four equal quarters |

When the windows don't divide evenly, `grid`, `2-rows` and `2-columns` put the bigger cells first, so slot 1 gets the extra room. For example, `2-rows` with 5 windows gives slot 1 a full-height column.

`layout` options:

| Option | Effect |
| --- | --- |
| `-o`, `--order APP_OR_ID` | Fill slots in this order. Takes an app name (any part of it, any case) or a window id. Repeat it or separate with commas. |
| `-n`, `--dry-run` | Draw the result without changing anything. |
| `-v`, `--verbose` | Also print the `aerospace` commands. |

Slots are numbered biggest first, and equal slots in reading order. Slot 1 gets the focused window unless `--order` says otherwise; the rest follow grouped by app. Floating windows are left alone.

### Your own layouts

Add them to `~/.config/aeroutils/layouts.toml` (or `$XDG_CONFIG_HOME/aeroutils/layouts.toml`). A layout with a built-in name replaces the built-in one.

```toml
[dev]
description = "Editor with two terminals on the right"
layout = "h[3:w, 2:v[w, w]]"

[wide-stack]
layout = "h[2:w, 1:v[*]]"
```

| Syntax | Meaning |
| --- | --- |
| `w` | One window |
| `*` | Every remaining window. At most once per layout; makes the layout fit any number of windows from its fixed slots + 1 up. |
| `h[a, b, ...]` | Children side by side |
| `v[a, b, ...]` | Children stacked top to bottom |
| `3:x` | Child `x` gets a relative size of 3 (default 1) |

Groups can nest one level deep: `h[w, v[w, w]]` works, `h[w, v[w, h[w, w]]]` does not.

### How layouts are applied

AeroSpace has no command to load a whole layout, so `aeroutils` rebuilds it with the commands it does have. It parks the workspace's windows on a temporary workspace, brings them back in a computed order, groups them with `join-with` and `move`, then sets sizes with `balance-sizes` and relative `resize` steps. The order matters because of how AeroSpace inserts windows, and that behaviour was taken from its source. It works whether or not the workspace is on screen.

Limits:

- **It arranges once.** AeroSpace has no layout modes, so windows opened later go wherever AeroSpace normally puts them. Run the command again to re-apply.
- **The current order isn't kept.** AeroSpace doesn't report where windows sit in the tree, so slots are filled by focus, `--order` and app name.
- **A visible workspace blinks** while its windows are parked and brought back.
- **Sizes ignore gaps**, so they can be off by a few pixels.

## Calling it from an AeroSpace keybinding

AeroSpace runs `exec-and-forget` commands with a minimal `PATH` that does not include pipx's `~/.local/bin`, so use the full path:

```toml
[mode.main.binding]
alt-shift-cmd-s = 'exec-and-forget ~/.local/bin/aeroutils swap 1 2'
alt-shift-cmd-g = 'exec-and-forget ~/.local/bin/aeroutils layout grid'
```

## How swapping works

1. List every window and its workspace once, before anything moves.
2. Move each window with `aerospace move-node-to-workspace --window-id`.
3. Put focus back on the workspace you were on, or follow your windows with `--follow`.

Because the windows are listed up front, swaps and rotations need no temporary workspace.

### Limitations

- **Layouts are not preserved.** AeroSpace has no command to move a workspace's tiling tree, so windows are re-tiled as they arrive. Nested splits, accordion groups and sizes reset, and the order of windows inside a workspace can change.
- **Monitors belong to workspaces, not windows.** If you pin workspaces to monitors with `workspace-to-monitor-force-assignment`, swapping 1 and 2 brings 2's windows to 1's monitor.
- **Windows that close mid-operation are skipped.** They are reported on stderr, the rest still move, and the exit status is 1.

## Project layout

```text
src/aerospace_utils/
  client.py    wrapper around the aerospace CLI
  ops.py       swap, move and reorder, independent of any interface
  layouts.py   layout language, built-in layouts and user layouts
  arrange.py   turns a layout into aerospace commands and runs them
  render.py    terminal diagrams
  cli.py       the aeroutils command
tests/         pytest suite, driven by a simulator of AeroSpace's window tree
tests/live/    checks against the real AeroSpace (they move windows; run by hand)
```

New interfaces (a menu bar app, keybinding helpers) can build on these modules without going through the CLI.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

The tests never call the real `aerospace`, so they run anywhere, CI included. The fake in `tests/fake_aerospace.py` simulates AeroSpace's window tree, so layout tests check the resulting tree and window sizes.

`tests/live/run_live_checks.py` checks every layout against the real AeroSpace using throwaway test windows. It changes what's on screen while it runs, so it's manual: read its docstring first.

## License

[MIT](LICENSE)
