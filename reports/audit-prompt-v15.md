# ink-writerPro v15.0.0 全面审查任务书（AI 执行用）

> **给人类用户的使用说明**（读完删掉本节，再喂给 AI）
>
> 1. 这份提示词专门写给**能本地访问仓库的 AI agent**（Claude Code / Cursor / Codex / Aider 等）。
>    不要喂给 Claude.ai 网页版或 ChatGPT 通用对话——它们没有读仓库的权限，会开始胡编。
> 2. 使用方式：在 Claude Code 里开一个干净会话，定位到仓库根目录，然后
>    **直接把本文件从第 1 节以下的内容整段粘进对话**（或 `@reports/audit-prompt-v15.md` 引用）。
> 3. 产出会写到 `reports/audit-v15-workflow.md` 和 `reports/audit-v15-findings.md` 两份文件。
> 4. 预计总耗时：30-60 分钟（取决于 AI 读代码的速度），产出 30-50 页详细报告。
> 5. 如果 AI 中途停下问你，参考「决策权表」一节——大多数问题它应该自己决策不问你。

---

## 1. 你的角色

你是一位**资深软件架构审查专家**，同时具备以下两个专业身份：

- **（A）叙事 AI 系统架构师**：熟悉长篇生成式写作（300 万字级）的核心难题——长时记忆、人物一致性、伏笔闭环、读者留存曲线；熟悉 NovelCrafter / Sudowrite / AI Dungeon / Scrivener 的内部机制与世界书/角色卡等主流长记忆范式。
- **（B）Agent 工程专家**：熟悉 Claude Code Skills & Plugins 架构、Anthropic Agent SDK、LangGraph / CrewAI / AutoGen 等多 agent 调度框架，能从 tool use、memory、plan/act/reflect、subagent 分工等维度做横向对比。

你的任务是审查 `ink-writerPro` 这个长篇网文 AI 创作工具，**不是夸它**，是帮业主（一位不懂工程但深度依赖它产出小说的创作者）看清：它真的能做到它承诺的事吗？哪里会崩？怎么修？

**你的审查必须建立在对代码的真读**之上。任何结论都要有具体文件+行号支撑。禁止"我猜"、"通常来说"、"可能是"。

---

## 2. 审查对象

**仓库**：`ink-writerPro` （Python 3.12+，Claude Code Plugin 形态）
**当前版本**：v15.0.0（2026-04-18 刚完成 FIX-17/18/11 + 覆盖率阶梯 30 US）
**主分支**：`master`，最新 HEAD：可通过 `git log -1` 自行确认
**代码规模**：ink_writer/ 域包 17 个 + ink_writer/core/ 6 个桶（刚合并 data_modules 进来）+ 94 个测试文件 / 2420 passed / 覆盖率 81.91%

### 产品声明（创作者期望，不等于事实）

业主期望这个软件能做到：

1. **长度**：单本 300 万字（约 1000 章 × 3000 字）
2. **一致性**：
   - 人物性格、口吻、语气不崩
   - 记忆不错乱（角色不会忘记前面发生的事 / 不会莫名知道自己不可能知道的事）
   - 物品、场景、空间、时间线自洽
   - 伏笔埋了要回收，回收时间不超期
3. **商业可过审**：通过起点中文网编辑审核——特别是对标一位名为**「编辑星河」**的起点编辑的直播建议（这些建议已被抓取并融入 `ink_writer/editor_wisdom/` 模块，规则数约 288 条）
4. **结构铁律**：
   - 黄金三章（前 3 章必须抓人、展示金手指、兑现卖点）
   - 第 1 章必须闭环（一个小爽点 + 一个大悬念）
   - 章末钩子、章首承接
5. **反俗套**：不写"神帝/至尊/龙傲天"类陈词，书名/绰号/设定要有新意
6. **整体工程合理性**：架构可维护、符合 2025-2026 年 AI agent 工程的优秀实践

请用 **2** 里的期望列表作为"业主验收标准"，和你从代码里看到的"实际能力"做比对。

---

## 3. 审查目标（两份产出）

你要产出 **2 份 markdown 文件**，路径固定：

### 产出 A：`reports/audit-v15-workflow.md` — 工作流程与优势

给业主看的"这东西到底怎么工作 + 比别的同类好在哪里"。

必含章节（每节不少于给出的字数下限）：

1. **一句话定位**（50 字内）
2. **鸟瞰图**：一张 mermaid flowchart，展示 `ink-init → ink-plan → ink-write → ink-review → ink-polish → 数据回流` 的完整主循环（≥ 10 个节点）
3. **13 个核心 skill / slash command 的各自职责**（用表格，含触发词、输入、输出、依赖）
4. **20+ checker agents 的分层职责**（表格，说明每个 agent 检查什么维度）
5. **长记忆体系**（详细叙述，≥ 1500 字）：
   - SQLite `index.db` 的 schema 分工（state / index / review_metrics / entities / ...）
   - 写作时上下文如何装配（context-agent → memory_compressor → query_router 的调用链）
   - 增量实体抽取（data-agent）怎么喂回记忆
   - FIX-17 反向传播、FIX-18 Progressions 在长记忆链路中的角色
6. **黄金三章 & 网文商业护城河**（≥ 800 字）：
   - golden-three-checker 检查哪些点
   - editor_wisdom RAG 如何把 288 条编辑规则注入 prompt
   - 章末钩子、开篇抓取的具体实现位置
7. **反俗套机制**：陈词黑名单、书名/绰号库、江湖语料的位置和触达
8. **与主流对标工具的横向优势**（表格对比，≥ 3 项比 NovelCrafter / Sudowrite / 通用 LangGraph 工作流好的地方，每项要有文件路径佐证）
9. **量化指标快照**：测试数、覆盖率、模块数、代码行数、已解决的技术债（FIX-xx 清单）

### 产出 B：`reports/audit-v15-findings.md` — 问题清单与修复方案

给业主+下一个 AI 看的"哪里会崩、怎么修、修完预期如何"。

必含章节：

1. **审查摘要**：
   - 严重度分布饼图（P0 阻断 / P1 高 / P2 中 / P3 低 各几条）
   - Top 5 最危险问题的一句话清单
2. **按维度分组的问题条目**（每条用统一 schema，下面第 8 节给出）。至少覆盖以下 8 个维度：
   - D1: 长期一致性（人物/记忆/伏笔/时间线）
   - D2: 网文商业性（过审、留存、付费转化、连载节奏）
   - D3: 结构铁律（黄金三章、钩子、卖点兑现）
   - D4: 反俗套 & 创意独特性
   - D5: 工程架构（模块边界、循环依赖、agent 分工、状态管理）
   - D6: Agent 工程范式（对标 Anthropic Agent SDK / Claude Code Skills / 主流 multi-agent 框架）
   - D7: 测试与可观测性（覆盖率盲区、flaky test、监控、回滚能力）
   - D8: 安全与健壮性（API key 管理、subprocess、路径遍历、输入校验）
3. **关键架构建议**（≥ 5 条系统级建议，每条说明做/不做的代价与收益）
4. **修复路线图**：把问题条目按依赖关系排成 3-5 个 milestone，每个给出预估工期（小时级）
5. **修复后预期**：如果全部 P0+P1 修完，量化指标会变成什么样？（章节连贯度、通过率、崩坏率，给可验证的指标）
6. **对业主的 Top 3 直白建议**（用大白话写，不要工程黑话）

---

## 4. 关切维度清单（来自业主 + 你作为专家补充）

| # | 维度 | 业主原话 / 你的补充 | 最低检查项 |
|---|---|---|---|
| 1 | 剧情连贯 | 300 万字不崩 | 追一遍 continuity-checker、plotline-tracker、foreshadow-tracker 的实现；看它们消费什么、产出什么、谁消费产出 |
| 2 | 人物不崩 | 口吻/性格/记忆不乱 | ooc-checker、voice_fingerprint、character_progressions；特别看 FIX-18 的 progression_events 是否真的闭环 |
| 3 | 逻辑自洽 | 不出现物品/场景/时间 bug | logic-checker、logic_precheck、computational_checks、consistency-checker |
| 4 | 网文商业可过审 | 过起点编辑审核 | editor_wisdom RAG（288 条规则）、reader-pull-checker、high-point-checker、golden-three-checker |
| 5 | 黄金三章硬约束 | 前 3 章抓人+金手指 | golden-three-checker、ink-init 的金手指三重约束、style-voice 档位 |
| 6 | 反俗套 | 书名/设定/陈词 | 陈词黑名单、书名模板库、L0-L3 敏感词档位；搜 `blacklist` / `cliches` |
| 7 | 工程合理性 | 架构优秀 | 循环依赖、`sys.path.insert` 是否真的清除干净、ink_writer/core/ 和 ink_writer/* 边界是否清晰 |
| 8 | 最新 AI agent 范式 | 对标最新 | 见第 5 节 |

---

## 5. 对标基准（三向对比）

**这是业主特别要求的**。你要在产出 B 的 D6 维度里，做以下三向横评：

### 对标 1：Claude Code Skill / Plugin 架构

- 官方规范：`.claude-plugin/plugin.json`、`skills/*/SKILL.md`、`agents/*.md`、hooks
- 评分点：
  - ink-writer 的 14 个 skill 是否都有清晰的 description（让主 agent 知道何时调用）？
  - SKILL.md 里的流程是否精确、可被 AI 照着执行？
  - agents/*.md 的工具权限 (`allowed-tools`) 是否最小化？
  - 有没有滥用 skill/agent 做本该用简单脚本做的事？
  - hook 使用是否得当？

### 对标 2：Anthropic Agent SDK（2025 版）

- 参考：`tool_use`、`prompt caching`、`extended thinking`、`memory tool`、`computer use`、`batch API`
- 评分点：
  - prompt_cache/ 模块有没有真正利用 5 分钟 TTL / 1 小时 prompt cache？命中率可观测吗？
  - api_client 用了 claude-opus-4-7 / claude-sonnet-4-6 / claude-haiku-4-5 中哪些模型？有没有为不同任务选错型号（杀鸡用牛刀 or 反之）？
  - 长任务有没有用 batch API / async？
  - 有没有正确处理 rate limit、token usage 观测？

### 对标 3：小说 AI 长记忆范式

- 参考：NovelCrafter 的 Codex/WorldBook、Sudowrite 的 Story Bible、AI Dungeon 的 World Info、学界的 Generative Agents / MemGPT
- 评分点：
  - ink-writer 的 index.db + entity extraction 是否等价于"世界书 + 自动更新"？
  - context 装配时有没有做相关性检索（embedding / BM25 / 混合）？看 `semantic_recall/` 和 `style_rag/`
  - 有没有"记忆压缩 + 长程召回"的双层结构？（MemGPT 范式）
  - 对人物心理状态的建模（Generative Agents 的 reflection）vs ink-writer 的 progression_events，差距在哪？

---

## 6. 审查方法论（严格按此步骤）

### Step 0：热身（不动笔，只读）

读完下列文件后再开始动笔，跳过此步的任何结论都不可信：

```
CLAUDE.md                                    # 仓库级开发指南（短）
README.md                                    # 版本历史、顶层介绍
ink-writer/.claude-plugin/plugin.json        # plugin 清单
docs/architecture.md                         # 架构文档（必读）
docs/agent_topology_v13.md                   # agent 拓扑
docs/memory_architecture_v13.md              # 记忆架构
docs/editor-wisdom-integration.md            # 编辑智慧模块
docs/engineering-review-report-v5.md         # 历史工程评审
docs/skill_systems_decision.md               # skill 系统决策
ralph/prd.json                               # 最新一轮 30 US PRD
tasks/design-fix-11-python-pkg-merge.md      # FIX-11 合并设计稿
reports/architecture_audit.md                # 既有架构审计
ink_writer/__init__.py                       # 域包入口
pyproject.toml                               # 依赖与打包
```

另外快速 `ls` 一遍：

```
ink-writer/skills/                # 14 个 slash command
ink-writer/agents/                # 20+ checker agents
ink_writer/                       # 17 个域子包
ink_writer/core/                  # 6 个基础设施桶（state/index/context/cli/extract/infra）
tests/                            # 94 个测试文件
```

### Step 1：建立工作流地图

基于 `ink-writer/skills/ink-auto/SKILL.md`、`ink-write/SKILL.md`、`ink-plan/SKILL.md`、`ink-review/SKILL.md`，把主循环画成 mermaid flowchart。**必须标出每个节点读什么写什么**。

### Step 2：追三条端到端链路

对每条链路，从入口追到出口，记录每个被调用的函数 / agent / 数据落点。三条：

- **链路 A：一章诞生** — `ink-write` 被触发 → context → draft → review → polish → 数据回流
- **链路 B：长期记忆读写** — 某个实体状态被更新 → data-agent → index.db → 下一章被 context-agent 检索回去
- **链路 C：检查失败 → 修复** — checker 报告问题 → ink-fix / polish-agent 消费 → 正文修改

### Step 3：评分矩阵

针对第 4 节 8 个维度 × 每个维度下列 5 级：

- 🟢 优秀（> 主流工具平均水平）
- 🟡 合格（达预期，但有优化空间）
- 🟠 有缺陷（业主期望 vs 实际能力有明显 gap）
- 🔴 危险（某些场景会直接崩坏业主承诺）
- ⚫ 未实现 / 看不到证据

### Step 4：反向验证

对你认为是"优势"的地方，**主动去找反例**——用 `grep` 搜 `TODO` / `FIXME` / `XXX` / `HACK` / `workaround`，看是不是吹牛。

### Step 5：对标差距

按第 5 节三向做横评，每一向各列 3 条差距（差在哪 + 差多少 + 补哪里可以补上）。

### Step 6：产出清理

产出 A 和产出 B 各走一遍自检：
- 每一条论断是否有文件+行号引用？
- mermaid 图是否能渲染（语法正确）？
- 表格列是否对齐？
- 有没有重复、自相矛盾的条目？

### Step 7：交付

把两份 md 写到指定路径，在对话里只需给业主**一段 300 字以内的 executive summary**（不是复述报告，是给他"看什么"的导读）。

---

## 7. 输出格式规范（严格遵守）

### 7.1 问题条目 schema

每条问题（产出 B）按以下 schema：

```markdown
### F-XXX: <一句话标题>

| 字段 | 值 |
|---|---|
| 维度 | D1 / D2 / ... |
| 严重度 | 🔴 P0 / 🟠 P1 / 🟡 P2 / 🟢 P3 |
| 可重现性 | 总是 / 偶发 / 特定条件 |
| 触发场景 | <什么情况下会炸> |

**证据**（必须有文件 + 行号）：
- `ink_writer/propagation/debt_store.py:42` ——（引用代码或描述）
- `tests/harness/test_xxx.py` 里没有覆盖这种情况

**根因**：<一段话解释为什么会这样>

**影响**：<业主视角，不用工程黑话>

**修复方案**：
1. <step 1>
2. <step 2>

**预期结果**：修复后 `xxx` 指标从 A 变成 B；复现场景不再出现。

**预估工期**：<小时>

**依赖**：<前置条件 / 其它 F-XXX>
```

### 7.2 代码引用格式

一律用 `path:line_number` 格式，便于 IDE / Claude Code 点击跳转。例子：

- ✅ `ink_writer/core/state/state_manager.py:1234`
- ✅ `ink-writer/skills/ink-write/SKILL.md:56-72`
- ❌ "state_manager 里" / "在 skill 文件中"

### 7.3 mermaid 要求

- 工作流图用 `flowchart TD` 或 `flowchart LR`
- 节点含中文，用 `A["中文标签"]` 包裹
- 每张图 ≤ 25 节点，超出要拆子图

### 7.4 表格列统一

- 对比表至少 3 列（项 / 当前实现 / 对标标杆）
- 问题表至少 4 列（ID / 维度 / 严重度 / 一句话）

---

## 8. 质量门禁（自检清单，提交前必过）

- [ ] 我读了第 6 节 Step 0 列出的全部文件（不是摘要，是完整读过）
- [ ] 我的每一条结论都有 `path:line` 引用，没有"一般来说"
- [ ] 产出 A 包含的 mermaid 图在 mermaid.live 可以渲染
- [ ] 产出 B 的每条问题都按 7.1 schema 完整填写（没有空字段）
- [ ] 我主动对"优势"做了反向验证（Step 4），没被代码标语欺骗
- [ ] 对标三向（Claude Code / Agent SDK / 小说 AI）各自至少 3 条对比
- [ ] 我没有建议"重写整个项目"这种不可执行的话；所有修复方案都在当前架构内可落地
- [ ] 产出 B 的 Top 3 业主建议是大白话（给不懂工程的人看）
- [ ] 总字数产出 A ≥ 8000 字、产出 B ≥ 15000 字

---

## 9. 决策权表（什么你自己决策、什么问业主）

| 情况 | 你该做 |
|---|---|
| 读到半途发现某模块文档和代码不一致 | 以代码为准，在 findings 里记 F-XXX |
| 不确定某个架构选择的原因 | 先翻 git blame / commit message / progress.txt，找不到再在 findings 里标"动机不明，建议补文档" |
| 对标 Claude Code Skill 官方规范时信息不足 | 用你知道的（SKILL.md yaml 头的 name/description/allowed-tools 字段是官方约定），不清楚的明确标注"按 2026-Q1 官方实现推断" |
| 发现 P0 级危险问题 | **不中断审查**，记录后继续；所有发现在产出 B 里统一呈现 |
| 业主的期望（第 2 节）和代码实现有矛盾 | 这正是 findings 要抓的核心——记下来 |
| 审查中想开新对话问业主 | 不要。直到产出 A 和 B 写完，一次性在对话里交付 |

---

## 10. 交付约束（硬性）

- **必须** 真读代码（Read / Grep / Glob），不允许凭记忆或训练数据推断
- **必须** 产出两个 md 文件到指定路径
- **禁止** 修改业务代码（你是审查员，不是修复员；修复方案写在文档里即可）
- **禁止** 创建除 `reports/audit-v15-workflow.md` 和 `reports/audit-v15-findings.md` 之外的文件
- **禁止** 在报告里植入"作为 AI 模型我建议..."之类的套话
- **允许** 在审查过程中使用 `git log`、`git blame`、运行只读命令辅助判断
- **不允许** 运行 `pytest` 或任何会改状态的命令

---

## 11. 开工确认（你的第一条回复必须包含以下内容）

在你开始动笔前，第一条回复给业主：

1. 复述审查目标（2 份产出的路径）
2. 列出你将按顺序读的 14 个"Step 0 必读文件"清单
3. 预估总耗时（区间，例如 "35-50 分钟"）
4. 说明你将如何处理"业主期望 vs 实际代码"的冲突（以代码为准，记入 findings）

然后立即开始 Step 0，不需要等业主批准。

---

**任务开始**。现在：从 Step 0 开始。
