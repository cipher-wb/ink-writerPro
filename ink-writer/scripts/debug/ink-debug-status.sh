#!/usr/bin/env bash
# Plugin-internal shim for ink-debug-status.
# Tries dev-environment ink_writer first; falls back to plugin-bundled _pyshim.
set -euo pipefail
SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)/_pyshim"
PROJECT="${INK_PROJECT_ROOT:-$PWD}"
if python3 -c 'import ink_writer.debug.cli' >/dev/null 2>&1; then
  exec python3 -m ink_writer.debug.cli --project-root "$PROJECT" status "$@"
fi
exec env PYTHONPATH="$SHIM_DIR:${PYTHONPATH:-}" python3 -m ink_writer.debug.cli --project-root "$PROJECT" status "$@"
