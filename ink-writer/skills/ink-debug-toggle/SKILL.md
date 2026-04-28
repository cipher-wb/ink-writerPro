---
name: ink-debug-toggle
description: 临时切换 Debug Mode 开关（master / layer_a / layer_b / layer_c / layer_d / invariants.<name>）on|off，无需手编 yaml。Activates when user asks /ink-debug-toggle or wants to flip a debug switch quickly.
allowed-tools: Bash
---

# Debug Mode — Toggle

临时切换 debug 模式的某个开关。底层是写到 `<project>/.ink-debug/config.local.yaml`，不污染仓库 yaml。

## 执行

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
bash "${SCRIPTS_DIR}/debug/ink-debug-toggle.sh" "$@"
```

<!-- windows-ps1-sibling -->
Windows（PowerShell）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
& "$env:SCRIPTS_DIR/debug/ink-debug-toggle.ps1" @args
```

## 参数

```
/ink-debug-toggle <key> on|off
```

可用 key：
- `master` — 总开关（等同 INK_DEBUG_OFF）
- `layer_a` — Claude Code hooks
- `layer_b` — checker 输出标准化
- `layer_c` — 5 个 invariant
- `layer_d` — LLM 对抗复核（v1.0 才开）
- `invariants.<name>` — 单个 invariant（如 `invariants.polish_diff`）

## 示例

```
/ink-debug-toggle layer_d on              # 开启 v1.0 对抗复核
/ink-debug-toggle layer_a off             # 临时关掉 hooks 层
/ink-debug-toggle master off              # 全关（等同 INK_DEBUG_OFF=1）
/ink-debug-toggle invariants.polish_diff off
```

详见 `docs/USER_MANUAL_DEBUG.md` 第 2.3 节。
