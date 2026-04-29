#!/usr/bin/env bash
# Plugin-internal shim for ink-debug-toggle.
# Tries dev-environment ink_writer first; falls back to plugin-bundled _pyshim.
set -euo pipefail
SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)/_pyshim"
PROJECT="${INK_PROJECT_ROOT:-$PWD}"
find_python_launcher_bash() {
  if command -v python3 >/dev/null 2>&1; then # c8-ok: detector primitive
    PYTHON_LAUNCHER="python3" # c8-ok: detector primitive
  elif command -v python >/dev/null 2>&1; then
    PYTHON_LAUNCHER="python"
  else
    echo "Python launcher not found" >&2
    exit 127
  fi
}
PYTHON_LAUNCHER="${PYTHON_LAUNCHER:-}"
if [[ -z "$PYTHON_LAUNCHER" ]]; then
  find_python_launcher_bash
fi
if $PYTHON_LAUNCHER -c 'import ink_writer.debug.cli' >/dev/null 2>&1; then
  exec $PYTHON_LAUNCHER -m ink_writer.debug.cli --project-root "$PROJECT" toggle "$@"
fi
exec env PYTHONPATH="$SHIM_DIR:${PYTHONPATH:-}" $PYTHON_LAUNCHER -m ink_writer.debug.cli --project-root "$PROJECT" toggle "$@"
