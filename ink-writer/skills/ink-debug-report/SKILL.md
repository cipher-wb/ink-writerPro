---
name: ink-debug-report
description: 生成 Debug Mode 的 markdown 双视图报告（按发生位置 / 按疑似根因）。可指定 --since 1h/1d/7d、--run-id、--severity。Activates when user asks /ink-debug-report or wants a debug summary to feed back to AI.
allowed-tools: Bash
---

# Debug Mode — Report

生成项目 debug 数据的 markdown 报告。文件落到 `<project>/.ink-debug/reports/manual-<ts>.md`。

报告包含两个视图：
1. **按发生位置**：`(skill × kind × severity)` 透视表，机器友好
2. **按疑似根因**：按 step 归并，人友好

## 执行

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
bash "${SCRIPTS_DIR}/debug/ink-debug-report.sh" "$@"
```

<!-- windows-ps1-sibling -->
Windows（PowerShell）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
& "$env:SCRIPTS_DIR/debug/ink-debug-report.ps1" @args
```

## 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--since 1h` / `--since 1d` / `--since 7d` | `1d` | 时间窗 |
| `--run-id <id>` | （全部） | 只看某次写章 / 某批 ink-auto |
| `--severity warn` | `info` | 过滤最低 severity |

## 喂给 AI 的 SOP

详见 `docs/USER_MANUAL_DEBUG.md` 第 4 节——4 步走：生成报告 → cat → 复制到新 Claude 会话 → prompt 让它分析根因 + 建议改 SKILL.md。
