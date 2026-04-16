# PRD: Narrative Coherence Engine — 叙事连贯性引擎

## Introduction

ink-writer 反复出现一类逻辑错误：**凭空发明前文不存在的事实**（如"加了微信"但前文根本没有加微信的机会）、**前面出现的人后面没了**、**前面没交代的人后面突然出现**、**前文的观察在后文的统计中被遗漏**。

这些问题的根因不是审查不够严格，而是**信息管线本身有结构性缺陷**：

### 根因 1：摘要只记录正面事实，不记录否定约束

Data-Agent 生成摘要时记录"发生了什么"，但不记录"什么没有发生"。例如：
- 第3章：悦悦妈妈从远处喊走悦悦，程予安与妈妈**没有任何接触**
- 摘要只记录了"程予安决定不走了"，没有记录"程予安没有和悦悦妈妈交换联系方式"
- 第5章 writer-agent 需要让程予安获取悦悦近况 → 检查摘要 → 无相关记录 → 自行发明"加了微信"

**缺失信息被解读为"可以自由发挥"而不是"不存在"。**

### 根因 2：章内无自洽回扫机制

Writer-Agent 在一章（~3000字）的生成过程中，前半段和后半段的信息不严格对齐。例如：
- 前文：观察到柜台男人的倒计时"跳动不规律"
- 后文：统计数据时写"十四组数据，全部正常"——遗漏了那个异常的男人

LLM 长文本生成中对早期内容的注意力会衰减。现有的 Step 3 checker 检查的是预定义模式（数字、动作、属性），无法捕获这种**语义级因果遗漏**。

### 为什么不是"加个 checker"能解决的

Checker 是**事后审查**——text 已经写好了，checker 检查预定义模式。但这类问题：
1. 模式无法穷举（"微信没加"、"人没见过"、"数据没统计"是无限种否定事实）
2. 需要**跨章因果推理**（不是简单的字符串匹配）
3. 需要在**写作阶段就防止**，而不是写完再修

本 PRD 的方案是**改信息管线本身**，从数据提取→上下文构建→写作→自检全链路强化。

---

## Goals

- **G1**: 消除"凭空发明前文不存在的事实"类缺陷——writer 无法编造摘要中明确否定的事情
- **G2**: 消除"前面出现的人后面没了"类缺陷——context-agent 主动提醒近期出场但未在本章大纲中的角色
- **G3**: 消除"章内前后矛盾"类缺陷——writer 在输出前自行检查并修正
- **G4**: 不降低写作速度超过 10%（自洽回扫增加的时间可控）
- **G5**: 不影响现有 checker 体系、MCC 机制、审查门禁

---

## User Stories

### US-001: Data-Agent 提取否定约束（Negative Constraints）

**Description:** 作为 data-agent，我需要在每章数据提取时，除了记录发生了什么，还要记录**关键的"没有发生什么"**，以便后续章节不会凭空编造这些事实。

**Acceptance Criteria:**
- [ ] data-agent.md 在 Step B 新增 **Step B.13: 否定约束提取（Negative Constraint Extraction）**
- [ ] 提取规则——以下场景必须生成否定约束：
  - **未建立联系**：角色A和角色B在同一场景出现但没有交换联系方式/建立对话/互相认识 → `"A与B未建立任何联系方式"`
  - **未获知信息**：主角目睹某事件但未获知关键信息（如对方姓名、身份、来历）→ `"主角不知道X的身份/姓名"`
  - **未发生的关键动作**：某个读者可能期待但实际没有发生的动作 → `"主角没有追上去/没有出手相救/没有开口询问"`
  - **未揭示的设定**：某个设定相关的秘密在本章中没有被揭露 → `"X的真实身份本章未被任何人发现"`
- [ ] 否定约束输出为结构化 JSON：
```json
{
  "negative_constraints": [
    {
      "id": "NC-ch003-001",
      "chapter": 3,
      "type": "no_contact_exchange",
      "entities": ["程予安", "悦悦妈妈"],
      "description": "程予安与悦悦妈妈没有任何直接接触，未交换联系方式",
      "valid_until": null,
      "override_condition": "仅当后续章节明确写出两人接触的场景时可解除"
    }
  ]
}
```
- [ ] 否定约束写入 index.db 的新表 `negative_constraints`
- [ ] 每章提取 3-8 条否定约束（不贪多，只提取关键的、可能被后续章节误用的）
- [ ] 否定约束有生命周期：`valid_until` 字段标注到期章号（null = 永久有效），当后续章节正文明确建立了被否定的事实时，data-agent 将其标记为 `resolved`

---

### US-002: Index.db 新增否定约束表

**Description:** 作为 index.db schema，我需要一张新表来存储否定约束，支持按章号查询和生命周期管理。

**Acceptance Criteria:**
- [ ] index_manager.py 新增 `negative_constraints` 表：
```sql
CREATE TABLE IF NOT EXISTS negative_constraints (
    id TEXT PRIMARY KEY,
    chapter INTEGER NOT NULL,
    type TEXT NOT NULL,
    entities TEXT NOT NULL,         -- JSON array
    description TEXT NOT NULL,
    valid_until INTEGER,            -- NULL = permanent
    override_condition TEXT,
    resolved_chapter INTEGER,       -- NULL = still active
    resolved_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
- [ ] 新增 CRUD 方法：`save_negative_constraints(chapter, constraints[])`, `get_active_constraints(current_chapter)`, `resolve_constraint(id, chapter, reason)`
- [ ] `get_active_constraints` 返回所有 `resolved_chapter IS NULL` 且 `(valid_until IS NULL OR valid_until >= current_chapter)` 的约束
- [ ] Schema 版本号递增
- [ ] 至少 3 个单元测试

---

### US-003: Data-Agent 提取场景退出状态快照（Scene-Exit Snapshot）

**Description:** 作为 data-agent，我需要在每章末尾提取一个结构化的"场景退出状态"，记录每个出场角色在章末的精确状态，防止后续章节出现"人物消失"或"状态跳跃"。

**Acceptance Criteria:**
- [ ] data-agent.md 在 Step B 新增 **Step B.14: 场景退出状态快照（Scene-Exit Snapshot）**
- [ ] 对每个本章出场角色提取：
  - `entity_id`: 角色标识
  - `location_at_exit`: 章末时在哪里
  - `emotional_state`: 章末情绪状态
  - `relationship_to_protagonist`: 与主角的关系状态（陌生/初识/信任/敌对等）
  - `contact_established`: 是否与主角建立了联系方式（true/false/null）
  - `last_action`: 最后一个动作（如"转身离开"、"躺在病床上"）
  - `open_threads`: 与该角色相关的未闭合事项（如"约好明天再见"、"欠了一个人情"）
- [ ] 场景退出快照写入 index.db 的 `chapter_memory_cards` 表的新字段 `scene_exit_snapshot`（JSON）
- [ ] 不增加新表，复用现有 chapter_memory_cards
- [ ] 每个出场角色都必须有快照条目（不能遗漏）

---

### US-004: Context-Agent 注入否定约束和场景退出快照

**Description:** 作为 context-agent，我需要在构建执行包时，将前序章节的活跃否定约束和上一章的场景退出快照注入任务书，让 writer-agent 在写作时不可违反。

**Acceptance Criteria:**
- [ ] context-agent.md 新增 **板块 15: 否定约束清单（Active Negative Constraints）**
  - 从 index.db 读取 `get_active_constraints(current_chapter)`
  - 按实体分组展示
  - 标注为"writer 不可违反"的硬约束
  - 格式：`❌ [NC-ch003-001] 程予安与悦悦妈妈没有任何联系方式 — 除非本章正文中明确写出两人建立联系的完整场景`
- [ ] context-agent.md 新增 **板块 16: 上章场景退出快照（Previous Scene-Exit Snapshot）**
  - 从 chapter_memory_cards 读取上一章的 scene_exit_snapshot
  - 展示每个角色的退出状态
  - 标注为"本章若出现该角色，必须从此状态开始续写"
- [ ] 板块 15 的 token 预算：最多 20 条约束，超出按 remaining 章数排序截断
- [ ] 板块 16 的 token 预算：最多 10 个角色，超出按出场频率截断
- [ ] 两个板块在 Context Token 动态预算中各占 500-800 tokens
- [ ] 不影响现有板块 1-14 的内容

---

### US-005: Writer-Agent 否定约束执行规则

**Description:** 作为 writer-agent，我需要在写作时严格遵守否定约束清单——如果需要某个被否定的前置条件，必须在本章正文中明确写出建立该条件的完整场景，不可用补叙一笔带过。

**Acceptance Criteria:**
- [ ] writer-agent.md 逻辑自洽铁律新增 **铁律 L6: 否定即禁区**
  - 板块 15 中的每条否定约束视为硬性禁区
  - 若本章剧情需要推翻某条约束（如确实需要程予安有悦悦妈妈微信），必须在正文中写出**完整的建立过程**（不少于 3 个段落的实际场景），不可用一句补叙（"之前加了微信"）带过
  - 推翻约束后，在本章的 data-agent 提取中标记该约束为 `resolved`
- [ ] writer-agent.md MCC 自检新增第 7 项：`✅/❌ 是否违反了否定约束清单中的任何一条？`
- [ ] 违反否定约束 = MCC 自检失败，必须自行修正

---

### US-006: Writer-Agent 自洽回扫步骤（Step 2A.1）

**Description:** 作为 writer-agent，我需要在生成全文后、进入字数校验前，对自己的产出做一次结构化自洽回扫，捕获章内前后矛盾。

**Acceptance Criteria:**
- [ ] writer-agent.md 新增 **「自洽回扫（Self-Consistency Scan）」** 章节，位于 MCC 自检之后
- [ ] 回扫执行以下 4 项检查：
  1. **观察-统计完整性**：正文中角色做出的每次观察/发现，是否在后续的总结/统计/回忆中都被纳入？（如"观察到异常"但统计时遗漏）
  2. **信息引用合法性**：正文中角色引用的每个事实/关系/联系方式，在本章正文中或执行包的否定约束之外是否有合法来源？（如"打开了XX的朋友圈"但没有建立好友关系的场景）
  3. **角色存在完整性**：本章开头出场的所有角色，在结尾前是否都有交代（离开/继续在场/转到另一场景）？不可凭空消失
  4. **因果链闭合**：正文中的每个行为动机是否有前因，每个开始的动作是否有结果？
- [ ] 回扫结果为 JSON：
```json
{
  "scan_passed": false,
  "issues": [
    {
      "type": "observation_missing_from_summary",
      "location": "第61行观察到柜台男人异常",
      "expected_in": "第134行数据统计",
      "fix_suggestion": "将柜台男人纳入统计，改为15组数据"
    }
  ]
}
```
- [ ] 发现问题时 writer 自行修正（最多 2 轮），修正后重新回扫
- [ ] 回扫结果持久化：`.ink/tmp/selfcheck_scan_ch{NNNN}.json`
- [ ] 回扫超 2 轮仍有问题 → 标记为 `scan_unresolved`，进入 Step 3 时强制关注

---

### US-007: SKILL.md 新增 Step 2A.1 自洽回扫流程

**Description:** 作为 ink-write 主流程，我需要在 Step 2A（正文起草）和 Step 2A.5（字数校验）之间插入 Step 2A.1（自洽回扫）。

**Acceptance Criteria:**
- [ ] SKILL.md 流程更新：Step 2A → **Step 2A.1** → Step 2A.5 → Step 2B → ...
- [ ] 模式定义更新：`/ink-write`：Step 1 → 2A → **2A.1** → 2A.5 → 2B → 2C → 3 → 4 → 4.5 → 5 → 5.5 → 6
- [ ] Step 2A.1 定义：
  - 输入：Step 2A 产出的正文 + 执行包（含板块 15 否定约束）
  - 执行：writer-agent 自洽回扫（US-006 定义的 4 项检查）
  - 输出：修正后的正文（或标记 scan_unresolved）
  - 阻断规则：回扫不阻断（但结果注入 Step 3 审查包）
- [ ] 进度条更新：12 步变 13 步（新增 Step 2A.1 自洽回扫）
- [ ] 不影响 Step 2A 和 Step 2A.5 的现有逻辑

---

### US-008: Context-Agent 角色连续性预警

**Description:** 作为 context-agent，我需要在构建执行包时，主动检查近期出场但不在本章大纲关键实体中的角色，生成预警防止"人物消失"。

**Acceptance Criteria:**
- [ ] context-agent.md 板块 8.7（出场角色状态快照）增强：
  - 现有功能：久未出场角色标注 ⚠️（>10章）和 🔴（>20章）
  - **新增**：最近 3 章出场过但不在本章大纲 `关键实体` 中的角色，标注 `📌 近期活跃但本章无安排`
  - 标注格式：`📌 悦悦（上次出场：ch3，距今 2 章）— 本章大纲未安排出场，若需提及请确保状态连续`
- [ ] writer-agent 遇到 📌 标记的角色时：
  - 不主动让其出场（大纲没安排）
  - 但若剧情需要提及（如主角回忆），必须参照 scene_exit_snapshot 中该角色的状态
  - 禁止编造新的互动/联系方式
- [ ] 不修改大纲合规检查的逻辑（📌 角色不算"缺少关键实体"）

---

### US-009: Outline-Compliance-Checker 增加否定约束违反检测

**Description:** 作为 outline-compliance-checker，我需要在审查时检测正文是否违反了活跃的否定约束。

**Acceptance Criteria:**
- [ ] outline-compliance-checker.md 新增 **O7: 否定约束合规（Negative Constraint Compliance）**
- [ ] 检测逻辑：
  - 读取审查包中的 `active_negative_constraints`（从执行包板块 15 透传）
  - 逐条检查：正文是否引用了被否定的事实？
  - 若引用：是否在正文中有完整的建立场景（≥3 段），还是一句补叙带过？
  - 有完整场景 → PASS（约束被正当推翻）
  - 一句补叙 → severity: critical（凭空编造）
  - 直接引用无解释 → severity: critical（忽视约束）
- [ ] MUST_NOT_PASS 条件新增：O7 存在 critical
- [ ] 不影响 O1-O6 的现有逻辑

---

### US-010: Logic-Checker 增加枚举完整性检测（L9）

**Description:** 作为 logic-checker，我需要新增 L9 层检查：当正文中角色对同类事物进行枚举/统计/列表时，检查前文提到的同类事物是否全部纳入。

**Acceptance Criteria:**
- [ ] logic-checker.md 新增 **L9: 枚举完整性（Enumeration Completeness）**
- [ ] 检测模式：
  - 角色对某类事物做了统计（如"十四组数据，全部正常"）
  - 检查前文中所有同类事物是否被纳入统计
  - 若有遗漏 → 标记为 issue
- [ ] severity: high（遗漏了前文明确提到的观察/事件/人物）
- [ ] 检测示例：前文"观察到柜台男人跳动不规律" + 后文"十四组数据全部正常" → 遗漏柜台男人
- [ ] MUST_NOT_PASS 条件：L9 与 L1-L8 统一（critical 或 ≥2 high）
- [ ] 不影响 L1-L8 的现有逻辑

---

## Functional Requirements

### 数据管线增强

- **FR-01**: Data-Agent 提取否定约束（每章 3-8 条），写入 index.db
- **FR-02**: Data-Agent 提取场景退出快照（每个出场角色一条），写入 chapter_memory_cards
- **FR-03**: 否定约束有生命周期管理（创建→激活→解除）
- **FR-04**: Index.db 新增 negative_constraints 表，支持增删改查

### 上下文增强

- **FR-05**: Context-Agent 板块 15 注入活跃否定约束（≤20 条）
- **FR-06**: Context-Agent 板块 16 注入上章场景退出快照（≤10 角色）
- **FR-07**: Context-Agent 板块 8.7 增加 📌 近期活跃角色预警

### 写作增强

- **FR-08**: Writer-Agent 铁律 L6 否定即禁区
- **FR-09**: Writer-Agent MCC 自检新增否定约束检查项
- **FR-10**: Writer-Agent 自洽回扫 4 项检查（观察-统计/信息引用/角色存在/因果链）
- **FR-11**: Step 2A.1 自洽回扫流程定义

### 审查增强

- **FR-12**: Outline-Compliance-Checker O7 否定约束违反检测
- **FR-13**: Logic-Checker L9 枚举完整性检测

---

## Non-Goals

- **不修改摘要格式**：摘要仍然记录正面事实，否定约束是独立的新数据流
- **不增加新的 checker**：利用现有的 outline-compliance-checker 和 logic-checker 扩展
- **不改变 Step 3 的审查门禁规则**：新增的 O7 和 L9 复用现有的 MUST_NOT_PASS 框架
- **不影响 Token 优化**：否定约束和场景退出快照的 token 预算已在 US-004 中明确限定

---

## Technical Considerations

### 架构变更总览

```
当前管线：
  Data-Agent → [摘要 + 实体 + 关系] → Context-Agent → [执行包] → Writer-Agent

改造后管线：
  Data-Agent → [摘要 + 实体 + 关系 + 否定约束 + 退出快照] → Context-Agent → [执行包 + 板块15否定约束 + 板块16退出快照] → Writer-Agent → [自洽回扫] → Step 3 [O7否定约束检测 + L9枚举完整性]
```

### 新增数据量

| 数据 | 每章增量 | 累积影响 |
|------|---------|---------|
| 否定约束 | 3-8 条 × ~100字 ≈ 500字 | 50章 ≈ 200条活跃（旧的会 resolve） |
| 场景退出快照 | 3-5 角色 × ~50字 ≈ 200字 | 只存最新章（覆盖更新） |
| 自洽回扫 | 1 次 LLM 调用 ≈ 5K tokens | 不累积 |

### 依赖关系

```
US-002 (DB表) ──→ US-001 (否定约束提取) ──→ US-004 (Context注入)
                  US-003 (退出快照提取) ──→ US-004 (Context注入)
                                             ↓
                                     US-005 (Writer铁律L6)
                                     US-006 (自洽回扫)
                                     US-008 (角色预警)
                                             ↓
                                     US-007 (SKILL.md流程)
                                     US-009 (O7检测)
                                     US-010 (L9检测)
```

### 实施建议顺序

Phase 1（数据层）: US-002 → US-001 → US-003
Phase 2（上下文+写作层）: US-004 → US-005 → US-006 → US-008
Phase 3（流程+审查层）: US-007 → US-009 → US-010

---

## Success Metrics

- **M1**: 使用新管线重写《你能看见我还剩多少秒吗》第3-5章，不再出现"微信"和"统计遗漏"问题
- **M2**: 连续写 10 章，0 次"凭空编造前文不存在的事实"
- **M3**: 连续写 10 章，0 次"章内观察/统计前后不一致"
- **M4**: 自洽回扫增加的时间 ≤ 30 秒/章
- **M5**: 否定约束 + 场景退出快照增加的 context token ≤ 1500/章

---

## Open Questions

无。
