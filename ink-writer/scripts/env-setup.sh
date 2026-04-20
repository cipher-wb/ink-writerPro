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
#   PYTHON_LAUNCHER（Mac/Linux → "python3"；Windows git-bash → 探测 py -3/python3/python）
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

# Step 5.5: Python launcher detection
# Mac/Linux 走 "python3"（与历史行为字节级一致）；Windows git-bash / msys / cygwin
# 下探测 py -3 → python3 → python，首个成功响应 --version 的候选胜出。
# 与 env-setup.ps1:Find-PythonLauncher 保持语义对等。
find_python_launcher_bash() {
  case "${OSTYPE:-}" in
    msys*|cygwin*|win32*)
      local _cand _head
      for _cand in "py -3" "python3" "python"; do  # c8-ok: detector primitive
        _head="${_cand%% *}"
        if command -v "$_head" >/dev/null 2>&1; then
          if $_cand --version >/dev/null 2>&1; then
            PYTHON_LAUNCHER="$_cand"
            return 0
          fi
        fi
      done
      PYTHON_LAUNCHER="python"
      ;;
    *)
      PYTHON_LAUNCHER="python3"  # c8-ok: detector primitive (Mac/Linux 定值)
      ;;
  esac
}

if [ -z "${PYTHON_LAUNCHER:-}" ]; then
  find_python_launcher_bash
fi
export PYTHON_LAUNCHER

# Step 6: Preflight check (optional, driven by INK_PREFLIGHT=1)
if [ "${INK_PREFLIGHT:-0}" = "1" ]; then
  $PYTHON_LAUNCHER -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" preflight
fi

# Step 7: Resolve PROJECT_ROOT via ink.py
export PROJECT_ROOT="$($PYTHON_LAUNCHER -X utf8 "${SCRIPTS_DIR}/ink.py" --project-root "${WORKSPACE_ROOT}" where)"
