#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 -m ink_writer.debug.cli --project-root "${INK_PROJECT_ROOT:-$PWD}" status "$@"
