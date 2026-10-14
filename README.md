# aerospace-utils

Command-line utilities for the [AeroSpace](https://github.com/nikitabobko/AeroSpace) tiling window manager on macOS.

AeroSpace moves windows to other workspaces one at a time, but it has no command to swap or renumber whole workspaces. `aeroutils` does that for you: it moves every window on a workspace in one go.

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

## Calling it from an AeroSpace keybinding

AeroSpace runs `exec-and-forget` commands with a minimal `PATH` that does not include pipx's `~/.local/bin`, so use the full path:

```toml
[mode.main.binding]
alt-shift-cmd-s = 'exec-and-forget ~/.local/bin/aeroutils swap 1 2'
```

## How it works

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
  client.py   wrapper around the aerospace CLI
  ops.py      workspace operations, independent of any interface
  cli.py      the aeroutils command
tests/        pytest suite, driven by an in-memory fake of the aerospace CLI
```

New interfaces (a menu bar app, keybinding helpers) can build on `ops.py` without going through the CLI.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

The tests never call the real `aerospace`, so they run anywhere, CI included.

## License

[MIT](LICENSE)
