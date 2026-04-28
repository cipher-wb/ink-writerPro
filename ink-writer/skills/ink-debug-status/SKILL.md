---
name: ink-debug-status
description: 显示 Debug Mode 当前状态——4 个上游层开关 / 最近 24h 各 severity 计数 / top3 频发 kind。Activates when user asks /ink-debug-status or wants to inspect debug mode state.
allowed-tools: Bash
---

# Debug Mode — Status

显示当前项目的 debug 模式状态：

- master / layer_a / layer_b / layer_c / layer_d 5 个开关
- 最近 24 小时 info / warn / error 计数
- top3 频发 kind

## 执行

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
bash "${SCRIPTS_DIR}/debug/ink-debug-status.sh"
```

<!-- windows-ps1-sibling -->
Windows（PowerShell）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
& "$env:SCRIPTS_DIR/debug/ink-debug-status.ps1"
```

## 详细说明

参见 `docs/USER_MANUAL_DEBUG.md` 第 2.1 节。
