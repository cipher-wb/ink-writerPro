# PRD: 爽点密集化与主线加速 — ink-writer 架构级改造

## Introduction

起点编辑对 ink-writer 生成的前三章给出 30 分（满分100），核心问题：
1. **摄像头主角**：主角只能被动观察能力效果，不交代能力能帮主角干什么，读者没有"代入爽感"
2. **主线进入太慢**：引子之后仍在铺垫，没有快速回到主线剧情
3. **爽点稀疏**：章节缺乏明确的大卖点和小卖点，读者没有持续兴奋感
4. **人物反应失真**：主角看到孕妇倒下竟然不去管，违反人类本能
5. **遣词造句弱**：编辑原话"遣词造句也得练练"，句子平淡、动词无力、感官细节缺失、表达套路化

本 PRD 不修改任何小说内容，而是改造 ink-writer 的**大纲生成、正文写作、审查检测**三层架构，从根源上杜绝上述问题。

## Goals

- 强制每章至少 1 个大卖点 + 2 个小卖点，不满足则 hard block
- 第1章内必须完成"能力展示→危机→能力产生收益"的完整小闭环
- 全链路（大纲→正文→审查）强制主角能动性检测，杜绝"摄像头主角"
- 扩展 OOC-checker + writer-agent 铁律，预防+检测人物反应失真
- 将"审核优化模式"的里程碑约束升级为所有新项目的默认行为
- 强制提升遣词造句质量：强动词替换弱动词、感官细节密度硬约束、禁止空洞形容词
- 所有改动向后兼容，已有项目不受影响（仅新章节写作时生效）

## User Stories

---

### US-001: 爽点密度硬约束 — 大纲层

**Description:** As a 作者, I want 大纲生成时每章必须规划 1 个大卖点 + 2 个小卖点, so that 爽点密度在结构设计阶段就被锁定。

**Acceptance Criteria:**
- [ ] 修改 `ink-plan/SKILL.md` Step 6（卷纲生成）和 Step 7（章纲批量生成），每章大纲新增必填字段：`大卖点`（1个，≤80字）、`小卖点`（2个，各≤40字）
- [ ] `大卖点` 必须是以下类型之一：装逼打脸 / 扮猪吃虎 / 越级反杀 / 打脸权威 / 反派翻车 / 甜蜜超预期 / 迪化误解 / 身份掉马 / 能力升级 / 关键情报获取 / 危机逆转
- [ ] `小卖点` 必须是以下类型之一：微兑现（信息/关系/能力/资源/认可/情绪/线索）/ 角色魅力展示 / 世界观趣味细节 / 关系推进 / 小悬念设置 / 能力小应用
- [ ] 大纲验证（Step 8）中，任何章节缺失 `大卖点` 或 `小卖点` 数量 < 2 → hard fail，阻断保存
- [ ] 大卖点不得与前3章重复同一类型（如连续4章都是"装逼打脸"→ hard fail）
- [ ] 更新 `templates/output/` 中相关大纲模板，加入新字段
- [ ] Typecheck/lint passes

---

### US-002: 爽点密度硬约束 — 正文写作层

**Description:** As a 作者, I want writer-agent 在起草正文时被强制要求写出 1 大 + 2 小卖点, so that 大纲规划的爽点在正文中真正落地。

**Acceptance Criteria:**
- [ ] 修改 `agents/writer-agent.md`，在"写作铁律"中新增铁律 L7：**卖点落地律** — 每章必须包含大纲规定的 1 个大卖点场景 + 2 个小卖点场景
- [ ] L7 执行细则：大卖点必须有完整的"铺垫→爆发→反应"三段式（不能只写爆发没有反应）；小卖点必须有可识别的读者情绪触发点
- [ ] 修改 `ink-write/SKILL.md` Step 2A.1（语义自检），新增第5项检查：`卖点覆盖检查` — writer-agent 自检是否覆盖了大纲要求的所有卖点
- [ ] 如果自检发现遗漏卖点，必须在 Step 2A 内自行补充，不得留到 Step 4（润色）
- [ ] Typecheck/lint passes

---

### US-003: 爽点密度硬约束 — 审查层

**Description:** As a 作者, I want high-point-checker 强制检测每章是否达到 1 大 + 2 小卖点标准, so that 任何遗漏都能在审查阶段被拦截。

**Acceptance Criteria:**
- [ ] 修改 `agents/high-point-checker.md`，新增检测规则 `SELLING_POINT_DEFICIT`：
  - 大卖点数量 < 1 → severity: critical, hard block
  - 小卖点数量 < 2 → severity: critical, hard block
  - 大卖点有爆发但无"反应段"（围观/对手/读者共鸣）→ severity: high
  - 小卖点无可识别情绪触发点 → severity: medium
- [ ] 新增检测规则 `SELLING_POINT_FRONT_LOADING`：章节前1/3必须至少出现1个小卖点，否则 severity: high（防止"慢热"）
- [ ] 将现有 rolling window 规则从"3章连续零爽点"收紧为"2章连续大卖点缺失"→ critical
- [ ] 修改 `ink-review` Step 3 review gate：当 `SELLING_POINT_DEFICIT` severity=critical 时，强制回退到 Step 2A（重写），而非 Step 4（润色）
- [ ] Typecheck/lint passes

---

### US-004: 第1章完整小闭环 — 大纲层强制

**Description:** As a 作者, I want 第1章大纲必须包含"能力展示→危机→能力收益"完整闭环, so that 读者在第1章内就能看到金手指的实际价值。

**Acceptance Criteria:**
- [ ] 修改 `ink-plan/SKILL.md` Step 7 中第1章的额外验证规则：
  - 第1章必须包含新字段 `第1章闭环`，格式：`能力展示={事件} → 危机={事件} → 能力收益={具体结果}`
  - 三个子字段任一为空 → hard fail
  - `能力收益` 必须是具体的、可感知的变化（如"获得报酬""地位提升""新能力解锁""危机解除后的奖励"），不能是抽象描述（如"主角有了新认知"）→ hard fail
- [ ] 修改 `scripts/data_modules/golden_three.py` 的 `build_golden_three_plan()`，将上述闭环要求写入 `golden_three_plan.json` 的 ch1 contract
- [ ] 第1章大纲的 `章末未闭合问题` 必须指向主线大冲突（不能还在"主角在想这个能力是什么"这种层级）→ hard fail
- [ ] 修改现有的"前3万字里程碑"约束，从"审核优化模式"专属改为**所有项目默认启用**
- [ ] Typecheck/lint passes

---

### US-005: 第1章完整小闭环 — 审查层强制

**Description:** As a 作者, I want golden-three-checker 验证第1章正文是否完成了闭环, so that 不合格的第1章无法通过审查。

**Acceptance Criteria:**
- [ ] 修改 `agents/golden-three-checker.md` 第1章检测规则，新增：
  - `CH1_NO_ABILITY_BENEFIT`: 第1章结束时主角的能力未产生任何具体收益 → severity: critical
  - `CH1_PASSIVE_PROTAGONIST`: 第1章主角仅观察/思考能力，未主动使用能力做出行动 → severity: critical
  - `CH1_ABSTRACT_PAYOFF`: 第1章的能力收益是认知层面的（"主角理解了……"）而非行动/结果层面的 → severity: high
  - `CH1_LATE_CRISIS`: 第1章前60%无危机事件触发 → severity: high
- [ ] 以上 critical 级别触发 hard block → 回退到 Step 2A 重写
- [ ] Typecheck/lint passes

---

### US-006: 主角能动性检测 — 大纲层

**Description:** As a 作者, I want 大纲生成时每章必须明确主角的主动行为, so that "摄像头主角"在规划阶段就被杜绝。

**Acceptance Criteria:**
- [ ] 修改 `ink-plan/SKILL.md` Step 7，每章大纲新增必填字段：`主角行动` — 主角在本章做出的关键主动行为（≤30字，必须是动词开头的行为描述，如"潜入仓库偷取证据"）
- [ ] 验证规则：`主角行动` 不能是被动描述（如"被告知""发现了""意识到""感受到"）→ hard fail
  - 允许的动词白名单前缀：决定/冲向/使用/对抗/说服/欺骗/逃离/交换/挑战/保护/破坏/窃取/调查/伪装/拒绝/选择/牺牲/激活/召唤/反击……
  - 禁止的动词黑名单前缀：被/发现/意识到/感受到/想到/回忆/观察/注意到/看到/听到……
- [ ] 连续2章 `主角行动` 类型相同（如都是"调查"）→ severity: medium warning
- [ ] 更新大纲模板加入 `主角行动` 字段
- [ ] Typecheck/lint passes

---

### US-007: 主角能动性检测 — 正文写作层

**Description:** As a 作者, I want writer-agent 在写作时确保主角有主动行为, so that 正文不会退化为主角的内心独白或旁观记录。

**Acceptance Criteria:**
- [ ] 修改 `agents/writer-agent.md`，在"写作铁律"中新增铁律 L8：**主角能动律** — 每章主角必须做出至少1个改变局面的主动行为，该行为必须产生可观察的后果
- [ ] L8 执行细则：
  - "主角只观察/思考/感受"的场景连续超过 800 字 → 必须插入主角行动
  - 主角的行动必须对剧情产生因果影响（不能是"主角说了一句话但没人理"这种无效行动）
  - 章节结尾时，主角的处境必须因为自己的行动而发生了变化（不能和章节开头一样）
- [ ] 修改 `ink-write/SKILL.md` Step 2A.1（语义自检），新增第6项检查：`主角能动性检查` — 检查主角是否有改变局面的主动行为
- [ ] Typecheck/lint passes

---

### US-008: 主角能动性检测 — 审查层

**Description:** As a 作者, I want 审查阶段能检测出"摄像头主角"问题, so that 被动主角的章节无法通过审查。

**Acceptance Criteria:**
- [ ] 修改 `agents/high-point-checker.md`（或新建专用检测模块，视实现复杂度决定），新增检测规则：
  - `CAMERA_PROTAGONIST`: 全章主角无主动改变局面的行为 → severity: critical, hard block
  - `PASSIVE_STREAK`: 主角连续 800+ 字仅观察/思考/感受 → severity: high
  - `NO_CONSEQUENCE`: 主角有行动但行动未产生任何可观察后果 → severity: high
  - `STATIC_SITUATION`: 章末主角处境与章首相同（排除"刻意留悬念"的标记章节）→ severity: high
- [ ] 黄金三章（ch1-3）中，`CAMERA_PROTAGONIST` 和 `PASSIVE_STREAK` 直接 hard block → 回退 Step 2A
- [ ] 普通章节中，`CAMERA_PROTAGONIST` → hard block；`PASSIVE_STREAK` → high severity（允许润色修复）
- [ ] Typecheck/lint passes

---

### US-009: 人物反应真实性 — 预防层（writer-agent 铁律）

**Description:** As a 作者, I want writer-agent 在写作时自动遵守人类本能反应规则, so that 不会写出"看到有人倒下不去管"这种违反常识的情节。

**Acceptance Criteria:**
- [ ] 修改 `agents/writer-agent.md`，在"写作铁律"中新增铁律 L9：**人类本能反应律** — 当场景中出现以下情况时，主角（或在场角色）必须做出符合人类本能的反应：
  - 有人受伤/倒下/求救 → 必须有反应（帮助/犹豫后帮助/想帮但被阻止/因特殊原因无法帮助并内心挣扎）
  - 面临生命威胁 → 必须有恐惧/紧张/战斗本能反应
  - 目睹极端事件（爆炸/车祸/死亡）→ 必须有震惊/应激反应
  - 被侮辱/欺压 → 必须有情绪反应（愤怒/隐忍但计划反击/当场反击）
  - 获得重大好处 → 必须有兴奋/谨慎/怀疑等合理情绪
- [ ] L9 允许角色因**已建立的人设特征**做出非典型反应（如冷血杀手不帮人），但必须在设定集中有对应标签，否则视为 OOC
- [ ] 修改 `ink-write/SKILL.md` Step 1.5（Contract），新增 `本章人类本能触发场景` 字段：context-agent 提前标注本章大纲中可能触发人类本能反应的场景，writer-agent 必须在正文中回应
- [ ] Typecheck/lint passes

---

### US-010: 人物反应真实性 — 检测层（OOC-checker 扩展）

**Description:** As a 作者, I want OOC-checker 能检测出违反人类常识反应的情节, so that 失真的人物反应在审查阶段被拦截。

**Acceptance Criteria:**
- [ ] 修改 `agents/ooc-checker.md`，新增检测层 `HUMAN_INSTINCT_VIOLATION`：
  - 场景中有人受伤/危险但在场角色完全无反应 → severity: critical
  - 主角获得重大好处但无任何情绪表现 → severity: high
  - 主角面临生命威胁但表现平静无波动 → severity: high
  - 路人/配角在危险场景中表现完全不合理 → severity: medium
- [ ] 检测方法：扫描场景中的"触发事件关键词"（受伤/倒下/爆炸/死亡/威胁/攻击等）→ 检查后续 200 字内是否有对应的"反应关键词"（冲过去/拨打/呼喊/颤抖/恐惧/愤怒/震惊等）
- [ ] 如果角色在设定集中有"冷血/反社会/非人类"等标签，自动降低该规则的严重度（critical → medium）
- [ ] 黄金三章中，`HUMAN_INSTINCT_VIOLATION` critical 级别 → hard block
- [ ] Typecheck/lint passes

---

### US-011: 审核模式默认化

**Description:** As a 作者, I want 现有的"审核优化模式"里程碑约束变为所有新项目的默认行为, so that 不需要手动启用就能获得编辑级别的质量保障。

**Acceptance Criteria:**
- [ ] 修改 `ink-plan/SKILL.md`，将"前3万字里程碑"（ch1-2/ch3-5/ch6-10/ch10-12 四阶段约束）从条件触发改为**默认启用**
- [ ] 里程碑约束升级（基于编辑反馈调整）：
  - ch1：能力展示 + 首次危机 + **能力产生具体收益（完整小闭环）**+ 至少2个有温度的配角
  - ch2：第一个小胜利 + 重要配角出场 + **主线冲突方向明确**
  - ch3：第一个完整小高潮 + **读者已知道"这本书要讲什么"**
  - ch4-5：世界观通过行动展开（非讲述）
  - ch6-10：第一个完整对决 + 长线冲突确立
- [ ] 修改 `golden-three-checker.md`，将 `golden_three_threshold` 从 0.85 提升为 **0.90**
- [ ] 原"审核优化模式"开关保留但改为 `audit_mode: "strict"` / `"normal"`（默认 normal = 当前 strict 级别）
- [ ] 用户可在 `state.json` 中设置 `audit_mode: "relaxed"` 手动降级回旧标准
- [ ] Typecheck/lint passes

---

### US-012: 大纲层爽点前置原则强化

**Description:** As a 作者, I want 大纲在规划卷级节拍表时就锁定爽点的前置分布, so that 不会出现"前5章全是铺垫"的问题。

**Acceptance Criteria:**
- [ ] 修改 `ink-plan/SKILL.md` Step 4（节拍表生成），新增硬约束：
  - 卷级爽点链（PC-1）的第一个爆发章不得晚于本卷的第3章
  - 前3章中，每章至少 1 个大卖点 + 2 个小卖点（与 US-001 对齐）
  - 前3章的 `压扬标记` 不能全部为"压"，至少有1章为"扬"
- [ ] 修改节拍表模板 `templates/output/大纲-卷节拍表.md`，Section 7（爽点链规划）新增约束提示
- [ ] 节拍表验证时，违反上述规则 → hard fail，阻断进入 Step 5
- [ ] Typecheck/lint passes

---

### US-013: 遣词造句质量 — 强动词替换与感官密度（writer-agent）

**Description:** As a 作者, I want writer-agent 在写作时强制使用强动词、具体名词、感官细节, so that 正文不再"平淡如水"。

**Acceptance Criteria:**
- [ ] 修改 `agents/writer-agent.md`，新增铁律 L10：**遣词造句律**，包含三条子规则：
  - **L10a 强动词法则**：禁止高频弱动词作为句子主干动词。弱动词黑名单（≤ 该章出现次数上限）：
    - `是/有/做/进行/开始/觉得/感到/看到/听到/想到` — 每个词全章 ≤ 3 次
    - 替换指引：`他是一个强壮的人` → `他的手臂粗过门框`；`她觉得害怕` → `她的指甲掐进掌心`
  - **L10b 感官锚点法则**：每 800 字内必须出现至少 1 个非视觉感官描写（听觉/嗅觉/触觉/味觉/体感），纯对话段除外
    - 要求：感官描写必须是具体的（`空气里有股铁锈味` ✓；`气氛很紧张` ✗）
  - **L10c 具象名词法则**：禁止连续使用 2 个以上空洞形容词修饰同一名词（如"巨大的可怕的恐怖的怪物"→ 选一个最精准的 + 一个具象细节）
- [ ] 在 `skills/ink-write/references/` 新增 `prose-craft-rules.md`，收录弱动词黑名单 + 替换示例库（每个弱动词至少 5 个替换示例，按场景分类：战斗/日常/情感/悬疑）
- [ ] 修改 `ink-write/SKILL.md` Step 2A，writer-agent 在起草时必须加载 `prose-craft-rules.md`
- [ ] Typecheck/lint passes

---

### US-014: 遣词造句质量 — 审查层检测（proofreading-checker 扩展）

**Description:** As a 作者, I want proofreading-checker 检测弱动词密度和感官描写缺失, so that 遣词造句问题能在审查阶段被量化拦截。

**Acceptance Criteria:**
- [ ] 修改 `agents/proofreading-checker.md`，新增 Layer 6 — **Prose Craft Quality**：
  - `WEAK_VERB_OVERUSE`: 弱动词黑名单中任一词全章 > 3 次 → severity: high；全章弱动词总计 > 15 次 → severity: critical
  - `SENSORY_DESERT`: 连续 800+ 字无非视觉感官描写 → severity: high；全章非视觉感官描写 < 3 处 → severity: critical
  - `ADJECTIVE_PILE`: 同一名词前堆叠 3+ 个形容词 → severity: medium
  - `GENERIC_DESCRIPTION`: 使用空洞感官词（`气氛紧张/感觉不对/有种说不出的`等）代替具体描写 → severity: medium
- [ ] 黄金三章中，`WEAK_VERB_OVERUSE` 和 `SENSORY_DESERT` 的 critical 级别 → hard block 回退 Step 2A
- [ ] 普通章节中，critical → hard block；high → 进入 Step 4 润色修复
- [ ] Typecheck/lint passes

---

### US-015: 遣词造句质量 — 润色层强化（polish-agent）

**Description:** As a 作者, I want polish-agent 在润色时主动替换弱动词和补充感官细节, so that 即使 writer-agent 遗漏，润色阶段也能兜底。

**Acceptance Criteria:**
- [ ] 修改 `skills/ink-write/references/polish-guide.md`，在 Anti-AI rewrite layers 中新增 Layer 8：**Prose Craft Polish**
  - 扫描全文弱动词，逐个替换为强动词（保持语义不变）
  - 扫描感官沙漠区（800+字无感官），插入 1-2 个自然的感官锚点
  - 扫描形容词堆叠，精简为"1精准形容词 + 1具象细节"
- [ ] polish-agent 替换弱动词时必须保持上下文语义一致，不能为了换词而换词
- [ ] 润色后必须通过 proofreading-checker Layer 6 的重检（与 US-014 联动）
- [ ] Typecheck/lint passes

---

## Functional Requirements

- FR-1: 每章大纲新增 `大卖点`（1个）、`小卖点`（2个）、`主角行动`（1个）三个必填字段
- FR-2: 第1章大纲新增 `第1章闭环` 必填字段（能力展示→危机→能力收益）
- FR-3: writer-agent 新增 L7（卖点落地律）、L8（主角能动律）、L9（人类本能反应律）三条铁律
- FR-4: high-point-checker 新增 `SELLING_POINT_DEFICIT`、`SELLING_POINT_FRONT_LOADING`、`CAMERA_PROTAGONIST`、`PASSIVE_STREAK`、`NO_CONSEQUENCE`、`STATIC_SITUATION` 六条检测规则
- FR-5: golden-three-checker 新增 `CH1_NO_ABILITY_BENEFIT`、`CH1_PASSIVE_PROTAGONIST`、`CH1_ABSTRACT_PAYOFF`、`CH1_LATE_CRISIS` 四条检测规则
- FR-6: OOC-checker 新增 `HUMAN_INSTINCT_VIOLATION` 检测层
- FR-7: ink-write Step 2A.1 语义自检从 4 项扩展为 6 项（+卖点覆盖+主角能动性）
- FR-8: ink-write Step 1.5 Contract 新增 `本章人类本能触发场景` 字段
- FR-9: "前3万字里程碑"从审核优化模式专属改为全项目默认
- FR-10: 第1卷爽点链 PC-1 爆发章不得晚于第3章
- FR-11: 黄金三章阈值从 0.85 提升至 0.90
- FR-12: rolling window 规则从"3章连续零爽点"收紧为"2章连续大卖点缺失"
- FR-13: writer-agent 新增 L10（遣词造句律）：强动词法则 + 感官锚点法则 + 具象名词法则
- FR-14: proofreading-checker 新增 Layer 6（Prose Craft Quality）：弱动词密度 + 感官沙漠 + 形容词堆叠 + 空洞描写检测
- FR-15: polish-agent 新增 Layer 8（Prose Craft Polish）：弱动词替换 + 感官补充 + 形容词精简
- FR-16: 新增 `references/shared/prose-craft-rules.md`：弱动词黑名单 + 替换示例库

## Non-Goals

- 不修改任何已有小说内容（本 PRD 仅改架构）
- 不修改 ink-init 流程（项目初始化不受影响）
- 不新建独立 agent（所有功能通过扩展现有 agent 实现）
- 不修改数据库 schema（`index.db` 结构不变，新字段存储在大纲 markdown 中）
- 不涉及 ink-auto 的批量写作调度逻辑
- 不涉及 ink-fix 的自动修复逻辑（修复逻辑由修复工具自行适配新规则）

## Technical Considerations

- **向后兼容**：所有新字段在 Step 8 验证时检查。已有项目的旧大纲不会被重新验证，仅新生成的章节受约束
- **性能影响**：新增的检测规则均为文本模式匹配/关键词扫描，不引入新的模型调用，审查时间增长可忽略
- **动词白名单/黑名单**：US-006 中的主角行动验证需要维护动词列表。建议存储在 `references/shared/protagonist-action-verbs.md` 中，方便后续扩展
- **人类本能触发词表**：US-010 中的触发事件/反应关键词需要维护。建议存储在 `references/shared/human-instinct-triggers.md` 中
- **已有检测规则兼容**：新规则的 severity 级别需与现有 review-gate 的分级逻辑一致（critical → hard block 回退 Step 2A；high → 可润色修复；medium → 建议修复）

## Success Metrics

- 黄金三章在起点编辑处的评分从 30 分提升至 60 分以上
- 第1章内完成"能力展示→危机→收益"闭环的合规率 = 100%
- 每章 1 大 + 2 小卖点的覆盖率 = 100%（hard block 保证）
- "摄像头主角"问题（全章无主动行为）的发生率 = 0%
- 人物反应失真问题的发生率降低 90% 以上
- 弱动词密度：每章弱动词黑名单词汇总计 ≤ 15 次（当前无约束）
- 感官描写密度：每 800 字至少 1 个非视觉感官锚点

## Open Questions (已决议)

1. **动词白名单/黑名单按类型分别维护** — 共享一个基础列表 + 类型扩展层（如仙侠增加"御剑/凝气/淬体"等强动词，都市增加"撕毁/砸/摔"等）。存储在 `references/shared/protagonist-action-verbs.md`，按类型分 section。
2. **"大卖点"与"爽点配方"合并** — 将现有 `爽点配方` 字段重命名为 `大卖点类型`，新增 `大卖点描述`（≤80字）字段；`小卖点` 为全新字段。避免两套字段造成概念混乱。原有爽点执行（铺垫来源/信息差/预期情绪）保留，挂在大卖点下。
3. **人类本能触发场景按类型扩展** — 基础列表覆盖现实场景（受伤/死亡/威胁/侮辱/重大收益），类型扩展层覆盖设定内场景（仙侠: 渡劫失败/灵石争夺/宗门驱逐；都市: 职场霸凌/车祸/商业背叛）。存储在 `references/shared/human-instinct-triggers.md`。
4. **`golden_three_threshold` 直接提至 0.90** — 不设过渡期。黄金三章决定读者留存，必须一步到位。若实测中频繁触发 hard block 导致写作效率骤降，再回调至 0.88。

## Implementation Priority

建议按以下顺序实施（依据对编辑评分影响的大小排序）：

| 优先级 | User Story | 理由 |
|--------|-----------|------|
| P0 | US-004, US-005 | 第1章闭环是编辑评分最直接的提升点 |
| P0 | US-001, US-002, US-003 | 1大+2小卖点是用户明确要求的核心改动 |
| P0 | US-011 | 审核模式默认化，一次性解决"可选约束没人开"的问题 |
| P1 | US-006, US-007, US-008 | 摄像头主角检测，防止结构性问题 |
| P1 | US-012 | 大纲层爽点前置，从源头保证节奏 |
| P1 | US-013, US-014, US-015 | 遣词造句质量提升，编辑明确指出的短板 |
| P2 | US-009, US-010 | 人物反应真实性，重要但频率较低 |
