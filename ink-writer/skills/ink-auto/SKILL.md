---
name: ink-auto
description: 跨会话无人值守批量写作。每章独立 CLI 会话，自动清理上下文，适用于小上下文模型。用法：/ink-auto [章数]
allowed-tools: Bash Read
---

# 跨会话无人值守批量写作（ink-auto）

## 解决的问题

使用小上下文模型（如 200k）时，单章写作消耗 60-70% 上下文。`/ink-5` 在同一会话连写 5 章会导致上下文溢出和降智。

## 原理

每章启动全新 CLI 进程，进程退出 = 上下文自然清零。等价于手动：
```
/ink-write → /clear → /ink-write → /clear → ...
```

但完全自动化，无需人工介入。

## 用法

```
/ink-auto        → 默认写 5 章
/ink-auto 10     → 写 10 章
/ink-auto 1      → 写 1 章（测试用）
```

## 执行方式

调用 `ink-auto.sh` shell 脚本。脚本自动检测项目路径和 CLI 平台。

```bash
export WORKSPACE_ROOT="${INK_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "${CLAUDE_PLUGIN_ROOT}/scripts" ]; then
  if [ -d "$PWD/scripts" ] && [ -d "$PWD/skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$PWD"
  elif [ -d "$PWD/../scripts" ] && [ -d "$PWD/../skills" ]; then
    export CLAUDE_PLUGIN_ROOT="$(cd "$PWD/.." && pwd)"
  else
    echo "ERROR: 未设置 CLAUDE_PLUGIN_ROOT" >&2
    exit 1
  fi
fi

export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"
```

解析用户参数（章数），然后执行：

```bash
bash "${SCRIPTS_DIR}/ink-auto.sh" ${章数:-5}
```

## 脚本运行过程（只读参考）

脚本内部循环 N 次，每次：

1. 从 `state.json` 读取当前章节号，计算下一章
2. 清理上一轮的 workflow 残留状态（`workflow clear`）
3. 启动全新 CLI 进程执行完整 ink-write 流程
4. 等待进程退出（阻塞调用，保证串行）
5. 冷却 10 秒（确保 git/index 异步操作完成）
6. 多重验证：章节文件 + 字数 ≥ 2200 + state 更新 + 摘要
7. 验证失败则用 ink-resume 重试一次
8. 仍失败则中止，已完成章节不受影响

## 关键保证

- **与 /ink-write 完全等价**：每个 CLI 会话通过 Skill 工具正式加载 ink-write SKILL.md
- **严格串行**：上一章完成并验证通过后才开始下一章
- **多实例安全**：可同时在不同终端运行不同小说，互不干扰
- **优雅中断**：Ctrl+C 终止当前会话，已完成章节不回滚

## 环境变量（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `INK_AUTO_COOLDOWN` | 章节间冷却秒数 | 10 |

## 支持平台

自动检测 PATH 中可用的 CLI 工具：

| 平台 | 调用方式 |
|------|----------|
| Claude Code | `claude -p` + `--permission-mode bypassPermissions` |
| Gemini CLI | `gemini --yolo` |
| Codex CLI | `codex --approval-mode full-auto` |

## 日志

每章的完整 CLI 输出保存在：
```
{PROJECT_ROOT}/.ink/logs/auto/ch{NNNN}-{timestamp}.log
```
