# Gemini CLI Tool Mapping

Skills 使用 Claude Code 工具名称编写。在 Gemini CLI 中遇到这些引用时，请使用对应的平台工具：

| Skill 中引用 | Gemini CLI 等价工具 |
|--------------|---------------------|
| `Read`（读取文件） | `read_file` |
| `Write`（创建/写入文件） | `write_file` |
| `Edit`（编辑文件） | `replace` |
| `Bash`（执行命令） | `run_shell_command` |
| `Grep`（搜索文件内容） | `grep_search` |
| `Glob`（按文件名搜索） | `glob` |
| `WebSearch` | `google_web_search` |
| `WebFetch` | `web_fetch` |
| `AskUserQuestion`（向用户提问） | `ask_user` |
| `Task`（派发子 Agent） | **无等价工具** — 见下方说明 |
| `Skill`（调用 skill） | `activate_skill` |

## 路径变量映射

| Skill 中引用 | Gemini CLI 替代 |
|--------------|-----------------|
| `${CLAUDE_PLUGIN_ROOT}` | `${INK_PLUGIN_ROOT}`（ink-writer 安装目录） |
| `${CLAUDE_PROJECT_DIR}` | 当前工作目录 `$PWD` |
| `${SCRIPTS_DIR}` | `${INK_PLUGIN_ROOT}/scripts` |

在执行 skill 中的 bash 脚本时，先设置环境变量：
```bash
export CLAUDE_PLUGIN_ROOT="${INK_PLUGIN_ROOT}"
export SCRIPTS_DIR="${INK_PLUGIN_ROOT}/scripts"
```

这样 skill 中的原始路径引用无需修改即可正常工作。

## 子 Agent 不可用

Gemini CLI 没有 Claude Code `Task` 工具的等价物。涉及子 Agent 派发的功能需要调整：

### ink-write 流程适配

原流程中 Step 2A（writer-agent）、Step 2B（polish-agent）、Step 3（checker agents）、Step 5（data-agent）均通过 `Task` 派发子 Agent。在 Gemini CLI 中：

1. **Step 2A（起草）**：直接在当前会话中按 `agents/writer-agent.md` 的指令执行
2. **Step 2B（润色）**：直接在当前会话中按 `agents/polish-agent.md` 的指令执行
3. **Step 3（审查）**：逐个读取 checker agent 的 `.md` 文件，按其指令串行审查
4. **Step 5（数据回写）**：直接在当前会话中按 `agents/data-agent.md` 的指令执行

### ink-review 流程适配

原流程并发派发 10 个 checker agent。在 Gemini CLI 中串行执行每个 checker。

## Gemini CLI 额外可用工具

以下工具在 Gemini CLI 中可用，但 Skills 中未引用：

| 工具 | 用途 |
|------|------|
| `list_directory` | 列出文件和子目录 |
| `save_memory` | 跨会话持久化信息到 GEMINI.md |
| `tracker_create_task` | 任务管理（创建、更新、可视化） |
| `enter_plan_mode` / `exit_plan_mode` | 切换到只读研究模式 |
