#!/usr/bin/env bash
# ============================================================
# ink-writer 共享环境初始化脚本
# 所有 Skill 通过 source 引入，消除重复的 Project Root Guard
#
# 输入环境变量（可选，按需设置后再 source）：
#   INK_SKILL_NAME   — 设置后自动导出 SKILL_ROOT
#   INK_PREFLIGHT=1  — 设置后自动运行 preflight 校验
#   INK_DASHBOARD=1  — 设置后校验并导出 DASHBOARD_DIR
#
# 输出环境变量：
#   WORKSPACE_ROOT, CLAUDE_PLUGIN_ROOT, SCRIPTS_DIR, PROJECT_ROOT
#   SKILL_ROOT (如果设置了 INK_SKILL_NAME)
#   DASHBOARD_DIR (如果设置了 INK_DASHBOARD=1)
# ============================================================

# Step 1: Workspace root
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

# Step 2: Resolve CLAUDE_PLUGIN_ROOT (if not already set by Claude Code)
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  else
    # Fallback: 从本脚本自身路径反推插件根目录 (scripts/ 的父目录)
    _ENV_SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
    if [ -d "${_ENV_SETUP_DIR}" ] && [ -d "${_ENV_SETUP_DIR}/../skills" ]; then
      export CLAUDE_PLUGIN_ROOT="$(cd "${_ENV_SETUP_DIR}/.." && pwd)"
    else
      echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT，且无法从当前目录推断插件根目录" >&2
      return 1 2>/dev/null || exit 1
    fi
    unset _ENV_SETUP_DIR
  fi
fi

# Step 3: Core paths
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"

if [ ! -d "${SCRIPTS_DIR}" ]; then
  echo "ERROR: 脚本目录不存在: ${SCRIPTS_DIR}" >&2
  return 1 2>/dev/null || exit 1
fi

# Step 4: SKILL_ROOT (optional, driven by INK_SKILL_NAME)
if [ -n "${INK_SKILL_NAME:-}" ]; then
  export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT}/skills/${INK_SKILL_NAME}"
fi

# Step 5: Dashboard mode (optional, driven by INK_DASHBOARD=1)
if [ "${INK_DASHBOARD:-0}" = "1" ]; then
  if [ ! -d "${CLAUDE_PLUGIN_ROOT}/dashboard" ]; then
    echo "ERROR: 未找到 dashboard 模块: ${CLAUDE_PLUGIN_ROOT}/dashboard" >&2
    return 1 2>/dev/null || exit 1
  fi
  export DASHBOARD_DIR="${CLAUDE_PLUGIN_ROOT}/dashboard"
fi

# Step 6: Preflight check (optional, driven by INK_PREFLIGHT=1)
if [ "${INK_PREFLIGHT:-0}" = "1" ]; then
  python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" preflight
fi

# Step 7: Resolve PROJECT_ROOT via ink.py
export PROJECT_ROOT="$(python3 -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
