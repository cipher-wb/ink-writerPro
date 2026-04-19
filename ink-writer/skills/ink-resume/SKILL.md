---
name: ink-resume
description: Recovers interrupted ink tasks with precise workflow state tracking. Detects interruption point and provides safe recovery options. Activates when user wants to resume or /ink-resume.
allowed-tools: Read Bash AskUserQuestion
---

# Task Resume Skill

## Project Root Guard（必须先确认）

- Claude Code 的“工作区根目录”不一定等于“书项目根目录”。常见结构：工作区为 `D:\wk\xiaoshuo`，书项目为 `D:\wk\xiaoshuo\凡人资本论`。
- 必须先解析真实书项目根（必须包含 `.ink/state.json`），后续所有读写路径都以该目录为准。

环境设置（bash 命令执行前）：
```bash
export INK_SKILL_NAME="ink-resume"
source "${CLAUDE_PLUGIN_ROOT}/scripts/env-setup.sh"
```
<!-- windows-ps1-sibling -->
Windows（PowerShell，与上方 bash 块等价，由 ink-auto.ps1 / env-setup.ps1 提供）：

```powershell
. "$env:CLAUDE_PLUGIN_ROOT/scripts/env-setup.ps1"
```


## Workflow Checklist

Copy and track progress:

```
任务恢复进度：
- [ ] Step 1: 加载恢复协议 (cat "${SKILL_ROOT}/references/workflow-resume.md")
- [ ] Step 2: 加载数据规范 (cat "${SKILL_ROOT}/references/system-data-flow.md")
- [ ] Step 3: 确认上下文充足
- [ ] Step 4: 检测中断状态
- [ ] Step 5: 展示恢复选项 (AskUserQuestion)
- [ ] Step 6: 执行恢复
- [ ] Step 7: 继续任务 (可选)
```

---

## Reference Loading Levels (strict, lazy)

- L0: 不加载任何参考，直到确认存在中断恢复需求。
- L1: 只加载恢复协议主文件。
- L2: 仅在数据一致性检查时加载数据规范。

### L1 (minimum)
- [workflow-resume.md](references/workflow-resume.md)

### L2 (conditional)
- [system-data-flow.md](references/system-data-flow.md)（仅在需要核对状态字段/恢复策略时）

## Step 1: 加载恢复协议（必须执行）

```bash
cat "${SKILL_ROOT}/references/workflow-resume.md"
```

**核心原则**（读取后应用）：
- **禁止智能续写**: 上下文丢失风险高
- **必须检测后恢复**: 不猜测中断点
- **必须用户确认**: 不自动恢复

## Step 2: 加载数据规范

```bash
cat "${SKILL_ROOT}/references/system-data-flow.md"
```

## Step 3: 确认上下文充足

**检查清单**：
- [ ] 恢复协议已理解
- [ ] Step 难度分级已知
- [ ] 状态结构已理解
- [ ] "删除重来" vs "智能续写" 原则已明确

**如有缺失 → 返回对应 Step**

## Step 2A 中断自动决策树（与 ink-write Step 0.6 对齐）

> Step 2A 是最常见的中断点。以下决策树确保 ink-resume 和 ink-write Step 0.6 的处理逻辑一致。

```
IF 章节文件不存在 OR 文件 < 200 字:
    → 从 Step 1 重新开始（视为未实质性开始）

ELIF 章节文件 200-1500 字:
    → 删除已有内容，从 Step 1 重新开始（重建上下文后重写）
    → 理由：内容太少，续写不如重写

ELIF 章节文件 > 1500 字 AND 距上次写入 < 2 小时:
    → 先重建上下文（必须执行 Step 1），再继续追写
    → 理由：新会话上下文已丢失，必须重建后才能保证续写风格一致

ELIF 章节文件 > 1500 字 AND 距上次写入 >= 2 小时:
    → 用 AskUserQuestion 询问用户：
    → "已有 {字数} 字内容，距上次写入 {时间}。选择：A) 重建上下文后继续追写 B) 删除重写"

ELSE:
    → 从 Step 1 重新开始
```

**续写前上下文重建（铁律）**：
> 无论选择续写还是重写，**必须先执行 Step 1（上下文构建）**。新会话中 Claude 没有任何前序上下文，直接续写会导致风格突变、设定遗忘、角色OOC。

续写专用流程：
1. 执行 Step 1（extract-context 或 context-agent）构建完整创作执行包
2. 读取已有正文（作为续写前提）
3. 基于创作执行包 + 已有正文，从断点继续 Step 2A
4. 续写完成后正常执行 Step 2A.5（字数校验）及后续步骤

**判断方法**：
- 文件大小：`wc -m < 章节文件`
- 上次写入时间：`stat -f %m 章节文件`（macOS）或 `stat -c %Y 章节文件`（Linux）

---

## Step 难度分级（来自 workflow-resume.md）

| Step | 难度 | 恢复策略 |
|------|------|---------|
| Step 1 | ⭐ | 直接重新执行 |
| Step 1.5 | ⭐ | 重新设计 |
| Step 2A | ⭐⭐ | **按上方决策树自动判断** |
| Step 2B | ⭐⭐ | 继续适配或回到 2A |
| Step 3 | ⭐⭐⭐ | 用户决定：重审或跳过 |
| Step 4 | ⭐⭐ | 继续润色或删除重写 |
| Step 5 | ⭐⭐ | 重新运行（幂等） |
| Step 6 | ⭐⭐⭐ | 检查暂存区，决定提交/回滚 |

#### 选项 B：跳审恢复（仅当审查已部分完成时可用）

**适用条件**：
- `.ink/review_metrics.json` 已存在且包含当前章节的审查记录
- 或 `index.db` 的 `review_metrics` 表中已有当前章节的数据

**执行流程**：
1. 读取已有的审查指标
2. 检查 `critical_count`：
   - 若 `critical_count == 0`：直接跳入 Step 4（润色），使用已有审查结果
   - 若 `critical_count > 0`：提示用户"审查发现 critical 问题，建议选择选项 A 重新审查"
3. 在 `workflow_state.json` 中标记 `step3_recovery: "skip_review"`

**优势**：避免重复消耗审查 Agent 的调用成本（每次审查需要 2-4 个 checker 并行调用）

## Step 4: 检测中断状态

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" workflow detect
```

**输出情况**：
- 无中断 → 结束流程，通知用户
- 检测到中断 → 继续 Step 5

## Step 5: 展示恢复选项（必须执行）

**展示给用户**：
- 任务命令和参数
- 中断时间和已过时长
- 已完成步骤
- 当前（中断）步骤
- 剩余步骤
- 恢复选项及风险等级

**示例输出**：

```
🔴 检测到中断任务：

任务：/ink-write 7
中断位置：Step 2 - 章节内容生成中

已完成：
  ✅ Step 1: 上下文加载

未完成：
  ⏸️ Step 2: 章节内容（已写1500字）
  ⏹️ Step 3-7: 未开始

恢复选项：
A) 删除半成品，从Step 1重新开始（推荐）
B) 回滚到Ch6，放弃Ch7所有进度

请选择（A/B）：
```

## Step 6: 执行恢复

**选项 A - 删除重来**（推荐）：
```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" workflow cleanup --chapter {N} --confirm
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" workflow clear
```

**选项 B - Git 回滚**：
```bash
git -C "$PROJECT_ROOT" reset --hard ch{N-1:04d}
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" workflow clear
```

## Step 7: 继续任务（可选）

如用户选择立即继续：
```bash
/{original_command} {original_args}
```

---

## 特殊场景

### Step 6 中断（成本高）

```
恢复选项：
A) 重新执行双章审查（成本：~$0.15）⚠️
B) 跳过审查，继续下一章（可后续补审）
```

### Step 4 中断（部分状态）

```
⚠️ state.json 可能部分更新

A) 检查并修复 state.json
B) 回滚到上一章（安全）
```

### 长时间中断（>1小时）

```
⚠️ 中断已超过1小时

上下文丢失风险高
建议重新开始而非续写
```

---

## 批量恢复协议（v7.0.5 新增）

> 当 `workflow detect` 输出包含 `batch_meta` 字段时，说明中断发生在 `ink-auto` 或 `ink-write --batch N` 的批量执行过程中。

### 批量中断检测

```bash
python3 "${SCRIPTS_DIR}/ink.py" --project-root "$PROJECT_ROOT" workflow detect
```

检查输出中的 `batch_meta`：
```json
{
  "batch_meta": {
    "batch_size": 5,
    "batch_start": 101,
    "completed_chapters": [101, 102, 103],
    "failed_chapter": 104,
    "failure_reason": "Step 2A 字数不足，2轮补写后仍未达标",
    "current_index": 4
  }
}
```

### 批量恢复选项

当检测到 `batch_meta` 时，展示给用户：

```
🔴 检测到批量写作中断：

批次：ink-auto 第{batch_start}章 → 第{batch_end}章
已完成：{completed_chapters} ({len}章)
失败章节：第{failed_chapter}章
失败原因：{failure_reason}

恢复选项：
A) 从第{failed_chapter}章继续批量写作（完成剩余{remaining}章 + 审查）
B) 跳过失败章节，对已完成的{len}章执行 Full 审查
C) 放弃本批次，从第{failed_chapter}章开始新的 /ink-auto
D) 仅恢复第{failed_chapter}章（单章 /ink-write 模式）

请选择（A/B/C/D）：
```

### 恢复执行

- **选项 A**：清理失败章节的 workflow state → 从 failed_chapter 开始 → 继续原批次循环 → 完成后执行 Phase 2 审查（范围=全部已完成章节）
- **选项 B**：标记 batch 为完成（缩小范围）→ 执行 `ink-review {completed_start}-{completed_end}` Full 审查
- **选项 C**：清理全部 workflow state → 提示用户执行 `/ink-auto`
- **选项 D**：清理失败章节 workflow state → 提示用户执行 `/ink-write {failed_chapter}`

### 兼容性

- 若 `workflow detect` 输出不包含 `batch_meta`（旧版 workflow_state.json），按原有单章恢复逻辑处理
- `batch_meta` 为可选字段，不影响现有 workflow_state.json 的读取

## 禁止事项

- ❌ 智能续写半成品内容
- ❌ 自动选择恢复策略
- ❌ 跳过中断检测
- ❌ 不验证就修复 state.json
- ❌ 批量恢复时回滚已完成的章节（已完成章节的数据已持久化，不可回滚）
