# ink-writer — 长篇网文创作系统

你已加载 ink-writer 扩展。这是一个工业化长篇网文创作系统，提供从初始化、规划、写作、审查到数据回写的全流程支持。

## 工具映射

Skills 使用 Claude Code 工具名称编写。使用 Gemini CLI 时，请参照以下映射：

@./ink-writer/references/gemini-tools.md

## 环境变量

Skills 中引用的 `${CLAUDE_PLUGIN_ROOT}` 在 Gemini CLI 中应替换为 ink-writer 插件的安装路径。

启动时请执行以下 shell 命令确定路径：

```bash
# 如果通过 gemini extensions install 安装
export INK_PLUGIN_ROOT="$(dirname "$(readlink -f "$0")")/ink-writer"
# 或手动指定
export INK_PLUGIN_ROOT="$HOME/.gemini/extensions/ink-writer/ink-writer"
```

在执行 skill 中的 bash 命令时，将 `${CLAUDE_PLUGIN_ROOT}` 替换为 `${INK_PLUGIN_ROOT}`。

## 可用 Skills

以下 skills 可通过 `activate_skill` 工具调用：

### 核心创作流程

| Skill | 说明 | 触发场景 |
|-------|------|----------|
| `ink-init` | 深度初始化网文项目 | 新建项目时 |
| `ink-plan` | 构建卷/章大纲 | 需要规划时 |
| `ink-write` | 写作单章（最低 2200 字） | 写章节时 |
| `ink-5` | 连续写 5 章 + 全量审查 | 日常批量创作 |

### 质量保障

| Skill | 说明 | 触发场景 |
|-------|------|----------|
| `ink-review` | 章节质量审查（10 个 checker） | 需要审查时 |
| `ink-macro-review` | 长篇宏观审查（每 50/200 章） | 宏观检查时 |

### 项目管理

| Skill | 说明 | 触发场景 |
|-------|------|----------|
| `ink-query` | 查询项目状态/角色/设定 | 查询信息时 |
| `ink-audit` | 数据一致性审计 | 验证数据完整性 |
| `ink-resolve` | 实体消歧 | 解决歧义条目 |
| `ink-resume` | 中断恢复 | 恢复中断任务 |
| `ink-learn` | 提取写作模式 | 学习成功经验 |
| `ink-dashboard` | 可视化管理面板 | 查看项目全局 |

## 使用方式

1. 进入你的小说项目目录（包含 `.ink/state.json` 的目录）
2. 使用 `activate_skill` 调用对应 skill
3. 按照 skill 中的步骤执行

## 重要限制

- Gemini CLI **不支持子 Agent**（无 `Task` 工具等价物）。依赖子 Agent 的步骤（如 ink-write 中的 checker 并发调用）需要在单会话中串行执行。
- 审查步骤中的 10 个 checker 需逐个执行，而非并发派发。
- `ink-5` 的批量模式同样以串行方式运行每章的完整流程。

## Python 后端

所有 skills 共享同一个 Python 后端，入口为：

```bash
python3 -X utf8 "${INK_PLUGIN_ROOT}/scripts/ink.py" --project-root "${PROJECT_ROOT}" [command]
```

确保已安装依赖：
```bash
pip install -r "${INK_PLUGIN_ROOT}/../requirements.txt"
```
