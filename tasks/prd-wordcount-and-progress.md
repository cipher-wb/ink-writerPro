# PRD: 字数上限收紧 + 双层进度条

## Introduction

ink-writer 当前存在两个用户体验问题：

1. **字数过长**：高潮章/关键章允许上浮 50%（最高 4500 字），但读者在免费阅读平台（起点/番茄）的阅读耐心有限，单章超过 4000 字信息密度稀释、读者负担大。需要将所有章节类型的硬上限统一收紧到 4000 字。

2. **写作过程无进度反馈**：单章写作流程 12 个 Step，耗时可达 10-15 分钟。用户在终端看到命令执行后长时间无输出，不知道进度，常误以为死机。需要实时进度条展示当前执行阶段。

## Goals

- **G1**: 所有章节类型的硬上限从 4500 收紧到 4000 字，高潮章上浮比例从 50% 降到 33%
- **G2**: ink-write 单章模式下，终端实时展示 12 步进度条，每完成一步打勾并更新百分比
- **G3**: ink-auto 批量模式下，外层展示「总进度 3/10 章」，内层（独立 CLI 进程）展示步骤进度条
- **G4**: 进度条不影响现有日志输出和审查报告生成

---

## User Stories

### US-001: Writer-Agent 字数上限收紧

**Description:** 作为 writer-agent 规格文件，我需要将高潮章/关键章的字数上浮比例从 50% 降到 33%，确保所有章节不超过 4000 字。

**Acceptance Criteria:**
- [ ] writer-agent.md 中「关键章/高潮章/卷末章：可上浮 50%」改为「可上浮 33%（硬上限 4000 字）」
- [ ] writer-agent.md 硬性指标中「默认 2200-3000，关键章可上浮50%」改为「默认 2200-3000，关键章可上浮33%，硬上限 4000」
- [ ] 不修改硬下限 2200 字
- [ ] 不破坏现有的字数校验逻辑框架

---

### US-002: SKILL.md Step 2A.5 字数校验阈值更新

**Description:** 作为 ink-write 主流程，我需要更新 Step 2A.5 的字数校验表，将超标阈值从 4500 收紧到 4000。

**Acceptance Criteria:**
- [ ] SKILL.md Step 2A.5 字数校验表更新：
  - 3501-4000 字：偏长，建议精简（关键战斗章/高潮章/卷末章可放行）
  - \> 4000 字：严重超标，必须精简回 ≤ 4000 字
- [ ] 删除原来的 4500 阈值相关描述
- [ ] 上浮描述从「上浮 50%」改为「上浮 33%（不超过 4000）」
- [ ] 不修改 Step 2A.5 的精简规则（删冗余/合并/压缩过渡，禁止删关键剧情点）

---

### US-003: ink-write 单章进度条实现

**Description:** 作为 ink-write 用户，我需要在终端看到每一步的实时进度条，以便知道当前写作进展和预计剩余时间。

**Acceptance Criteria:**
- [ ] 在 SKILL.md 中定义进度输出规范：每个 Step 开始和完成时，必须输出标准化进度信息
- [ ] 进度输出格式定义（12 步）：

```
━━━━━━━━━━━━━━━━━━━━ 0% 第42章
☐ Step 1   上下文收集
☐ Step 2A  正文起草
☐ Step 2A.5 字数校验
☐ Step 2B  风格适配
☐ Step 2C  计算闸门
☐ Step 3   质量审查
☐ Step 4   润色修复
☐ Step 4.5 安全校验
☐ Step 5   数据回写
☐ Step 5.5 数据修复
☐ Step 6   Git备份
☐ 完成
```

每完成一步更新为：

```
████████░░░░░░░░░░░░ 42% 第42章
✅ Step 1   上下文收集
✅ Step 2A  正文起草
✅ Step 2A.5 字数校验
✅ Step 2B  风格适配
✅ Step 2C  计算闸门
☐ Step 3   质量审查      ← 执行中...
☐ Step 4   润色修复
☐ Step 4.5 安全校验
☐ Step 5   数据回写
☐ Step 5.5 数据修复
☐ Step 6   Git备份
☐ 完成
```

- [ ] 每个 Step 完成时输出一行：`✅ Step {id} {名称} ({耗时}s)`
- [ ] 当前执行中的 Step 标记为 `⏳ Step {id} {名称} ← 执行中...`
- [ ] 进度百分比 = 已完成步数 / 总步数 × 100
- [ ] 进度条使用 Unicode 块字符（█░）绘制，宽度 20 字符
- [ ] 若某步骤被跳过（如 Step 5.5 无需修复），标记为 `⏭ Step {id} {名称} (跳过)`，仍计入进度
- [ ] 若某步骤触发回退重写（如 Step 3 硬阻断），标记为 `🔄 Step 3 → 回退 Step 2A`，进度条回退对应百分比
- [ ] 全部完成后输出汇总：`✅ 第42章完成 | 2856字 | 总耗时 8m32s | 审查分 78`

---

### US-004: workflow_manager.py 增加进度事件钩子

**Description:** 作为 workflow_manager，我需要在每个 step 开始/完成时触发进度事件，以便上层（ink-write SKILL.md）可以输出进度条。

**Acceptance Criteria:**
- [ ] workflow_manager.py 的 `complete-step` 命令执行时，向 stdout 输出标准化进度行：`[INK-PROGRESS] step_completed {step_id} {elapsed_seconds}`
- [ ] workflow_manager.py 新增 `start-step` 命令（或在现有 `complete-step` 中推断），输出：`[INK-PROGRESS] step_started {step_id}`
- [ ] `complete-task` 命令输出：`[INK-PROGRESS] chapter_completed {chapter_num} {word_count} {overall_score} {total_seconds}`
- [ ] 进度行以 `[INK-PROGRESS]` 前缀标识，便于上层脚本解析
- [ ] 不破坏现有的 workflow_state.json 写入逻辑
- [ ] 单元测试覆盖进度事件输出

---

### US-005: ink-auto.sh 外层章节进度条

**Description:** 作为 ink-auto 批量写作用户，我需要在外层进程看到「总进度 3/10 章」的进度条，以便了解整体写作进展。

**Acceptance Criteria:**
- [ ] ink-auto.sh 在每章开始前输出章节级进度条：

```
═══════════════════════════════════════════════
  📖 总进度 [███████░░░░░░░░░░░░░] 3/10 章 (30%)
  ⏱️  已耗时 24m | 预计剩余 56m
═══════════════════════════════════════════════
```

- [ ] 进度条使用 Unicode 块字符（█░），宽度 20 字符
- [ ] 预计剩余时间 = 已耗时 / 已完成章数 × 剩余章数
- [ ] 每章完成后刷新进度条（章数+1，时间更新）
- [ ] 检查点操作展示详细子步骤进度，每个子步骤有独立状态标记：
  - 每 5 章检查点：`🔍 检查点 [第5-10章] ✅审查 ⏳修复 ☐...`
  - 每 10 章检查点（累加）：`🔍 检查点 [第10-15章] ✅审查 ✅修复 ⏳审计 ☐审计修复`
  - 每 20 章检查点（累加）：`🔍 检查点 [第20-25章] ✅审查 ✅修复 ✅审计 ✅审计修复 ⏳宏观审查 ☐宏观修复 ☐消歧检查`
  - 每个子步骤：开始时 ⏳，完成时 ✅，跳过时 ⏭
- [ ] 不修改现有的 `[$i/$N]` 日志格式（进度条是额外新增，不替代）
- [ ] 进度条在终端宽度不足时优雅降级（只显示文字，不显示 bar）

---

### US-006: ink-auto.sh 解析内层进度事件

**Description:** 作为 ink-auto.sh，我需要从子进程的 stdout 中解析 `[INK-PROGRESS]` 事件，实时展示内层步骤进度。

**Acceptance Criteria:**
- [ ] ink-auto.sh 在启动每章的 CLI 子进程时，通过管道或 tee 捕获 stdout
- [ ] 解析 `[INK-PROGRESS] step_started {step_id}` 事件，在外层终端展示当前步骤
- [ ] 解析 `[INK-PROGRESS] step_completed {step_id} {seconds}` 事件，更新步骤完成状态
- [ ] 解析 `[INK-PROGRESS] chapter_completed {chapter_num} {word_count} {score} {seconds}` 事件，更新章节进度
- [ ] 内层进度展示格式（缩进 4 格，区别于外层）：

```
═══════════════════════════════════════════════
  📖 总进度 [███████░░░░░░░░░░░░░] 3/10 章 (30%)
  ⏱️  已耗时 24m | 预计剩余 56m
═══════════════════════════════════════════════
    ████████████░░░░░░░░ 58% 第28章
    ✅ Step 1   上下文收集 (12s)
    ✅ Step 2A  正文起草 (145s)
    ✅ Step 2A.5 字数校验 (3s)
    ✅ Step 2B  风格适配 (42s)
    ✅ Step 2C  计算闸门 (8s)
    ✅ Step 3   质量审查 (89s)
    ⏳ Step 4   润色修复 ← 执行中...
```

- [ ] 子进程的非进度输出（错误信息、警告等）正常透传到终端
- [ ] 日志文件中同时记录原始输出（包含 `[INK-PROGRESS]` 行）供调试

---

## Functional Requirements

### 字数控制

- **FR-01**: writer-agent.md 高潮章上浮比例从 50% 改为 33%，硬上限 4000 字
- **FR-02**: SKILL.md Step 2A.5 字数校验表阈值从 4500 改为 4000
- **FR-03**: 所有章节类型的绝对硬上限统一为 4000 字

### 进度条（内层）

- **FR-04**: ink-write SKILL.md 定义每个 Step 的进度输出规范
- **FR-05**: workflow_manager.py 在 step 开始/完成时输出 `[INK-PROGRESS]` 标准化事件
- **FR-06**: 进度条包含：Unicode bar + 百分比 + 章节号 + 各步骤状态（✅/⏳/☐/⏭/🔄）
- **FR-07**: 回退重写时进度条百分比回退

### 进度条（外层）

- **FR-08**: ink-auto.sh 每章开始/完成时输出章节级进度条
- **FR-09**: ink-auto.sh 解析子进程的 `[INK-PROGRESS]` 事件展示内层步骤
- **FR-10**: 预计剩余时间基于已完成章节的平均耗时计算
- **FR-11**: 终端宽度不足时优雅降级

---

## Non-Goals

- **不改变默认字数范围** — 默认仍然是 2200-3000，只改上限
- **不改变硬下限** — 2200 字不变
- **不增加 GUI/TUI 界面** — 纯终端文本输出，不引入 curses/rich 等 TUI 库
- **不修改 ink-auto 的检查点逻辑** — 只在现有流程中插入进度输出
- **不影响 Gemini/Codex 平台** — 进度输出是 stdout 文本，所有平台兼容

---

## Technical Considerations

### 字数修改影响范围

需要修改的文件及位置（精确到行号区域）：

1. `ink-writer/agents/writer-agent.md`
   - ~L176: 「可上浮 50%」→「可上浮 33%（硬上限 4000 字）」
   - ~L331: 「关键章可上浮50%」→「关键章可上浮33%，硬上限4000」

2. `ink-writer/skills/ink-write/SKILL.md`
   - ~L870: 「3501-4500 字」→「3501-4000 字」
   - ~L871: 「> 4500 字」→「> 4000 字」
   - ~L875: 「上浮 50%」→「上浮 33%」

### 进度条实现方案

**内层进度（ink-write 侧）**：
- ink-write 是 Claude Code skill（markdown 规格文件），不是脚本。进度输出需要在 SKILL.md 中规定：每个 Step 开始和结束时 writer 必须调用 `workflow_manager.py` 的 start-step/complete-step 命令
- workflow_manager.py 在这些命令中输出 `[INK-PROGRESS]` 行到 stdout
- 这些行会被 Claude Code CLI 传递到终端

**外层进度（ink-auto.sh 侧）**：
- ink-auto.sh 已有 `[$i/$N]` 格式的章节计数
- 新增 bash 函数 `print_chapter_progress()` 输出 Unicode 进度条
- 通过 `tee` 捕获子进程 stdout，用 `grep` 过滤 `[INK-PROGRESS]` 行更新内层状态
- 子进程的完整输出仍写入日志文件

### 依赖关系

```
US-001 ──→ US-002（字数：先改 agent 规格，再改 SKILL 校验表）

US-004 ──→ US-003（进度：先实现 workflow_manager 事件钩子，再定义 SKILL 输出规范）
              ↓
           US-005 ──→ US-006（进度：先做外层进度条，再解析内层事件）
```

两条线互不依赖，可以并行实施。

---

## Success Metrics

- **M1**: 使用新流程写作 5 章，所有章节字数 ≤ 4000
- **M2**: ink-write 执行时终端每 30 秒内至少有一次进度更新（用户永远不会等超过 30 秒无反馈）
- **M3**: ink-auto 10 章批量写作时，用户能随时看到「已完成 X/10 章 + 当前章进度」
- **M4**: 进度条不影响现有日志文件的可读性（`[INK-PROGRESS]` 行可被 grep 过滤）

---

## Open Questions

无。所有关键设计决策已在提问环节确认。
