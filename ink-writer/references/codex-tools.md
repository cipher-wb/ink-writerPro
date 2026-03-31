# Codex CLI Tool Mapping

Skills 使用 Claude Code 工具名称编写。在 Codex CLI 中遇到这些引用时，请使用对应的平台工具：

| Skill 中引用 | Codex 等价工具 |
|--------------|----------------|
| `Read`、`Write`、`Edit`（文件操作） | 使用原生文件工具 |
| `Bash`（执行命令） | 使用原生 shell 工具 |
| `Grep`（搜索文件内容） | 使用原生搜索工具 |
| `Glob`（按文件名搜索） | 使用原生文件搜索 |
| `Task`（派发子 Agent） | `spawn_agent`（见[子 Agent 派发](#子-agent-派发)） |
| 多个 `Task` 调用（并发） | 多个 `spawn_agent` 调用 |
| Task 返回结果 | `wait` |
| Task 完成后 | `close_agent` 释放槽位 |
| `Skill`（调用 skill） | Skills 原生加载 — 直接按指令执行 |
| `AskUserQuestion`（向用户提问） | 直接向用户输出问题 |

## 路径变量映射

| Skill 中引用 | Codex 替代 |
|--------------|------------|
| `${CLAUDE_PLUGIN_ROOT}` | `${INK_PLUGIN_ROOT}` 或 `${CLAUDE_PLUGIN_ROOT}`（安装时已设置） |
| `${CLAUDE_PROJECT_DIR}` | 当前工作目录 `$PWD` |
| `${SCRIPTS_DIR}` | `${INK_PLUGIN_ROOT}/scripts` |

安装时已将 `CLAUDE_PLUGIN_ROOT` 设为 `INK_PLUGIN_ROOT`，因此 skill 中的原始路径引用无需修改。

## 子 Agent 派发

Codex 的 `spawn_agent` 替代 Claude Code 的 `Task` 工具。需要在 `~/.codex/config.toml` 中启用：

```toml
[features]
multi_agent = true
```

### 命名 Agent 映射

ink-writer 的 skills 通过 `Task` 派发命名 Agent（如 `ink-writer:writer-agent`）。在 Codex 中：

1. 找到对应的 agent prompt 文件（如 `agents/writer-agent.md`）
2. 读取 prompt 内容
3. 填充模板占位符（`{chapter_num}`、`{project_root}` 等）
4. 使用 `spawn_agent` 派发 worker

| Skill 指令 | Codex 等价 |
|------------|-----------|
| `Task tool (ink-writer:writer-agent)` | `spawn_agent(agent_type="worker", message=...)` + `writer-agent.md` 内容 |
| `Task tool (ink-writer:data-agent)` | `spawn_agent(agent_type="worker", message=...)` + `data-agent.md` 内容 |
| `Task tool (ink-writer:polish-agent)` | `spawn_agent(agent_type="worker", message=...)` + `polish-agent.md` 内容 |
| `Task tool (ink-writer:*-checker)` | `spawn_agent(agent_type="worker", message=...)` + 对应 checker `.md` 内容 |

### Message 格式

`message` 参数是用户级输入。建议格式：

```
Your task is to perform the following. Follow the instructions below exactly.

<agent-instructions>
[从 agent .md 文件填充的 prompt 内容]
</agent-instructions>

Execute this now. Output ONLY the structured response following the format
specified in the instructions above.
```

### ink-write 流程中的 Agent 派发

| 步骤 | Agent | 调度方式 |
|------|-------|----------|
| Step 1（上下文构建） | `context-agent` | `spawn_agent` |
| Step 2A（起草） | `writer-agent` | `spawn_agent` |
| Step 2B（风格润色） | `polish-agent` | `spawn_agent` |
| Step 3（审查） | 10 个 checker agents | 多个 `spawn_agent`（可并发） |
| Step 5（数据回写） | `data-agent` | `spawn_agent` |

### ink-review 流程

原流程并发派发 10 个 checker agent。在 Codex 中可以通过多个 `spawn_agent` 调用实现并发，使用 `wait` 等待结果。

## 环境检测

执行涉及 git 操作的 skill 时，先检测环境：

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

- `GIT_DIR != GIT_COMMON` → 已在 worktree 中
- `BRANCH` 为空 → detached HEAD
