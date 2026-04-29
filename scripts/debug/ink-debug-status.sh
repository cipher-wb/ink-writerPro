#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
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
exec $PYTHON_LAUNCHER -m ink_writer.debug.cli --project-root "${INK_PROJECT_ROOT:-$PWD}" status "$@"
