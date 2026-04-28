#!/bin/bash
# check_plugin_version_consistency.sh — Mac/Linux release pre-flight 入口
#
# 校验 ink-writer/.claude-plugin/plugin.json 与 .claude-plugin/marketplace.json
# 的版本号一致；不一致返回非零退出码，便于挂入 pre-commit / CI。
#
# 用法:
#   scripts/maintenance/check_plugin_version_consistency.sh
#   scripts/maintenance/check_plugin_version_consistency.sh --plugin-json other.json

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$THIS_DIR/../.." && pwd)"
SCRIPT="$THIS_DIR/check_plugin_version_consistency.py"

PYTHON_LAUNCHER="${PYTHON_LAUNCHER:-python3}"

cd "$REPO_ROOT"
exec $PYTHON_LAUNCHER -X utf8 "$SCRIPT" "$@"
