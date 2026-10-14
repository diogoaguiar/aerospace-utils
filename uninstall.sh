#!/usr/bin/env bash
# Remove the `aeroutils` command installed by install.sh.
set -euo pipefail

command -v pipx >/dev/null || { echo "error: pipx not found" >&2; exit 1; }
pipx uninstall aerospace-utils
