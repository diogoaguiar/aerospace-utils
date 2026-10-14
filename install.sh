#!/usr/bin/env bash
# Install the `aeroutils` command with pipx.
#
# Usage:
#   ./install.sh          editable install: changes in this checkout apply immediately
#   ./install.sh --copy   regular install: a snapshot of this checkout
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

editable=1
case "${1:-}" in
  "") ;;
  --copy) editable=0 ;;
  -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) die "unknown option: $1 (see --help)" ;;
esac

[[ "$(uname -s)" == "Darwin" ]] || warn "AeroSpace only runs on macOS; installing anyway."

command -v python3 >/dev/null || die "python3 not found. Install it with: brew install python"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
  || die "Python 3.9 or newer is required, found $(python3 --version 2>&1)."

if ! command -v pipx >/dev/null; then
  command -v brew >/dev/null \
    || die "pipx not found. Install it (https://pipx.pypa.io) and run this script again."
  info "Installing pipx with Homebrew"
  brew install pipx
fi

info "Installing aeroutils from $repo_dir"
if (( editable )); then
  pipx install --force --editable "$repo_dir"
else
  pipx install --force "$repo_dir"
fi

if ! command -v aeroutils >/dev/null; then
  info "Adding the pipx bin directory to PATH"
  pipx ensurepath
  warn "Open a new terminal before running aeroutils."
fi

command -v aerospace >/dev/null \
  || warn "the aerospace CLI is not on PATH. Install AeroSpace: https://github.com/nikitabobko/AeroSpace"

info "Done. Try: aeroutils list"
