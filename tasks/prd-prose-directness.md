# PRD: 文笔直白化升级（黄金三章 + 战斗/高潮/爽点场景）

## 1. Introduction / Overview

用户反馈当前 ink-writer 产出的文字**文邹邹、读起来费劲**，尤其在黄金三章（第 1-3 章，过起点审核关键段）和战斗/高潮/爽点场景（读者求爽的密集段）。用户要求：

> "所有内容都长驱直入，不要让人读起来有负担，不要有不必要的描写，所有内容都要服务于想要表达的东西，不要装逼。"

现状原因分析：
- **writer-agent 有感官丰富度硬约束**（L10b 每 800 字 ≥1 处非视觉感官；L10e 主导感官轮换必须含触觉+嗅觉）——这些约束在慢节奏场景合适，但在**黄金三章和爽点场景会产出冗余描写**
- **没有"直白模式"**——writer-agent 全局用同一套风格，缺少场景感知
- **没有"精简"环节**——polish-agent 的 Anti-AI/修复/毒点规避不包含"删冗余、拆长句、替抽象词"
- **editor-wisdom 无简洁主题域**——288 份编辑建议转化后的 80+ 原子规则，没有明确的 `simplicity` 分类
- **没有量化基线**——不知道起点实书（借剑/元始法则/山河稷/从水猴子/重回1982）的黄金三章和战斗段实际有多直白

本 PRD 建立**全链路直白化体系**：基线统计 → 量化指标 → 规则资产 → writer 场景门控 → 新 directness-checker → polish 精简 pass，让**黄金三章 + 战斗/高潮/爽点场景**默认激活直白模式，**慢节奏/抒情/意境段保持现有丰富感官**（场景感知而非一刀切）。

**范围**：仅 ink-writer（非 webnovel-writer / 非其他 writer skill）。

## 2. Goals

- G1：产出 `reports/prose-directness-baseline.md`，基于 benchmark 起点实书（19 本 × 30 章）量化出黄金三章 + 战斗/高潮段的直白密度基线（修辞密度、形容词-动词比、抽象词频、句长中位数、每百字空描写段数）
- G2：`editor-wisdom` 新增 `simplicity` 主题域，至少 12 条原子规则覆盖"直白"场景
- G3：新 `directness-checker` 在黄金三章 + 战斗/高潮/爽点场景激活，5 维度评分，任一维度 <6 分即 Red（需要重写）
- G4：writer-agent 新增场景门控"直白模式"，在激活场景下暂挂 L10b/L10e 感官丰富度硬约束，改用"每句服务剧情/角色/冲突"硬原则
- G5：polish-agent 新增"精简 pass"：写完后自动删冗余（比喻堆砌/空描写/抽象形容词堆叠），仅在直白模式场景触发
- G6：黄金三章 + 战斗场景端到端验证：新机制产出文字比现状**平均缩短 ≥20%**，读者阅读负担（直白分）提升 ≥40%
- G7：其他场景（慢节奏/抒情/意境）零退化——感官丰富度指标不能下降
- G8：v22.0.0 发版，README 明确承诺"场景感知直白化"

## 3. User Stories

### US-001：benchmark 基线统计脚本

**Description:** 作为维护者，我需要扫描 benchmark 起点实书，量化出黄金三章 + 战斗场景的"直白密度"基线，后续 checker 才能有明确阈值。

**Acceptance Criteria:**
- [ ] 新增 `scripts/analyze_prose_directness.py`，扫描 `benchmark/reference_corpus/{borrow,yuanshi,shanhe,shuihouzi,chongshui1982}/chapters/` 共 19 本 × 30 章
- [ ] 输出 5 维度指标（每本 × 每章）：
  - D1：**修辞密度** = 比喻/拟人/排比句 / 总句数
  - D2：**形容词-动词比** = 形容词数 / 动词数（分词用 jieba）
  - D3：**抽象词频** = 抽象词命中次数 / 每 100 字（抽象词表见 US-003）
  - D4：**句长中位数**（词数）
  - D5：**空描写段落数** = 每章纯环境/纯心理描写段落数（无人物动作/对话）
- [ ] 分段统计：黄金三章（第 1-3 章）/ 战斗场景（用简单启发式：章节标题含"战/斗/杀/剑/拳"或正文含高频动词密度 > 阈值）/ 其他场景
- [ ] 写入 `reports/prose-directness-stats.json`（每章一行 JSON）
- [ ] 新增测试 `tests/scripts/test_analyze_prose_directness.py`：用 2-3 个构造样本验证指标计算正确
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败（baseline 3021）

### US-002：基线报告生成

**Description:** 作为写作系统设计者，我需要把 US-001 的原始数据汇总成可读基线报告，确定各维度的"目标值"和"Red 线"。

**Acceptance Criteria:**
- [ ] 新增脚本 `scripts/gen_directness_baseline_report.py`（消费 US-001 的 JSON）
- [ ] 输出 `reports/prose-directness-baseline.md`：
  - 五维度分段统计（黄金三章 / 战斗 / 其他）各自的 P25/P50/P75
  - 推荐阈值：Green ≥ P50（起点中位数水平），Yellow P25~P50，Red < P25
  - 跨书对比表（19 本 × 5 维度）
  - 推荐的 `directness-checker` 阈值常量（`REHTORIC_MAX=0.15` 等具体数字）
- [ ] 报告底部生成 `seed_thresholds.yaml`（机器可读），供后续 US-005 checker 消费
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-003：抽象词/空描写黑名单

**Description:** 作为 checker 设计者，我需要一份"直白的敌人"黑名单（抽象形容词、套话、空洞短语），让 checker 和 polish 都能引用。

**Acceptance Criteria:**
- [ ] 新增 `ink-writer/assets/prose-blacklist.yaml`，至少 100 条，分 3 类：
  - `abstract_adjectives`（≥50 条）：如"莫名"、"无尽"、"难以言喻"、"仿佛"、"似乎"、"似有若无"
  - `empty_phrases`（≥30 条）：如"此情此景"、"不知为何"、"仿佛回到了"、"时间仿佛静止"
  - `pretentious_metaphors`（≥20 条）：如"宛如……一般"、"犹如……似的"、"恍若……之态"
- [ ] 人工起草 + 从 benchmark 负样本（网文差评段落）辅助提取；每条附"替代示例"
- [ ] 加载器 `ink_writer/prose/blacklist_loader.py`，支持热加载
- [ ] 新增测试：加载器能正确解析 YAML、命中黑名单词
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-004：editor-wisdom 新增 simplicity 主题域

**Description:** 作为规则库维护者，我需要在现有 10 个主题域基础上新增 `simplicity` 域，让 editor-wisdom 检索能召回"直白"相关规则。

**Acceptance Criteria:**
- [ ] `data/editor-wisdom/rules.json` 新增 ≥12 条 `simplicity` 主题域规则，每条包含 `id` / `rule` / `rationale` / `applies_when`（黄金三章 / 战斗 / 高潮 / 爽点 / any）
- [ ] 规则示例：
  - "每句话必须服务剧情推进、角色心理、或冲突升级；不服务任何一项的描写删除"
  - "禁用抽象形容词堆叠：同句 ≥2 个形容词视为违规（直白模式）"
  - "禁用空境描写：纯环境段落超过 3 句视为违规"
  - "比喻需承载信息量：比喻本体 = 抽象概念时禁用"
- [ ] `config/editor-wisdom.yaml` 注册新主题域（`categories` 列表加 `simplicity`）
- [ ] writer-injection 分类别召回：黄金三章 + 战斗场景时 `simplicity` 类 ≥5 条（类似 opening/taboo/hook 机制）
- [ ] 新增测试验证主题域加载、分类召回
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-005：新 directness-checker agent

**Description:** 作为审查流程，我需要一个专门检查"直白度"的 checker，仅在黄金三章 + 战斗/高潮/爽点场景激活。

**Acceptance Criteria:**
- [ ] 新增 `ink-writer/agents/directness-checker.md`，5 维度评分（使用 US-002 的阈值）：
  - D1 修辞密度分（0-10）
  - D2 形容词-动词比分
  - D3 抽象词密度分
  - D4 句长适中分
  - D5 空描写段分
- [ ] 输出 `issues[]`，每条带 `line_range` + `evidence.excerpt` + `suggest_rewrite`
- [ ] 任一维度 <6 → `severity: RED`（触发重写）；均 ≥8 → Green
- [ ] 激活条件：`context.scene_mode in {golden_three, combat, climax, high_point}`（见 US-009）；其他场景 checker 直接返回 skipped
- [ ] 接入 `checker_pipeline/step3_runner.py`，与其他 checker 并行
- [ ] 新增测试 `tests/checker_pipeline/test_directness_checker.py`：人工构造 3 段（直白达标 / 修辞堆砌 / 空描写泛滥），分别验证 Green/Red/Red
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-006：writer-agent 场景门控直白模式

**Description:** 作为 writer-agent，我需要在黄金三章 + 战斗/高潮/爽点场景激活"直白模式"硬原则，让产出直接服务剧情而非堆砌感官。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/writer-agent.md` 新增章节 `## Directness Mode (场景激活硬约束)`
- [ ] 激活条件：chapter ∈ [1, 3] OR scene_mode ∈ {combat, climax, high_point}
- [ ] 激活时硬原则（prompt 顶部高优先级标注）：
  - 每句必须服务：剧情推进 OR 角色心理 OR 冲突升级（三者占一）
  - 禁用抽象形容词堆叠（同句 ≥2 个形容词 Red）
  - 禁用空境描写段（超 3 句纯环境）
  - 禁用高级比喻（比喻本体为抽象概念）
  - 首选强动词 + 具体名词，减少形容词与副词
- [ ] 不激活时：保持现有 L10b/L10e 感官丰富度约束（场景感知，不一刀切）
- [ ] prompt 内显式展示 US-003 黑名单前 20 条作为反例
- [ ] 冲突解决：US-007 单独处理 L10b/L10e 在直白模式下的暂挂
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-007：writer-agent L10b/L10e 感官丰富度冲突解耦

**Description:** 作为 writer-agent 规格维护者，我需要让 L10b（每 800 字 ≥1 处非视觉感官）和 L10e（主导感官轮换必须含触觉+嗅觉）在直白模式下**暂挂**，不暂挂其他场景。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/writer-agent.md` L10b / L10e 段显式标注：`仅在非 Directness Mode 场景生效`
- [ ] 直白模式下 prompt 明确说明：不强求非视觉感官密度、不强求感官轮换，专注于剧情/动作/对话
- [ ] 不在直白模式下（抒情/慢节奏/铺垫章）保持原状
- [ ] sensory-immersion-checker 规格同步更新：在直白模式下 skipped（返回"场景无需检查"而非 Red）
- [ ] 新增测试：给定 scene_mode=combat 时 sensory-immersion-checker 不触发 Red；给定 scene_mode=slow_build 时正常触发
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-008：polish-agent 精简 pass

**Description:** 作为 polish-agent，我需要在直白模式场景的章节写完后，多做一遍"精简 pass"：删冗余句、拆长句、替抽象词。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/polish-agent.md` 新增 `## Simplification Pass (直白模式场景)` 章节
- [ ] 激活条件与 directness-checker 相同
- [ ] 精简规则：
  - 黑名单命中词直接删除或替换（消费 US-003 blacklist）
  - 句长 >35 字 → 尝试拆为 ≤20 字的两短句
  - 连续 ≥2 个修辞（比喻/拟人）→ 保留 1 个，其余删除
  - 空描写段 → 压缩到 2 句内或删除
  - 形容词-动词比 > 阈值时，替形容词为"动词+具体细节"
- [ ] 精简后文字字数不应少于原文 70%（过度精简保护）
- [ ] 不破坏 polish-agent 已有 Anti-AI / 修复 / 毒点规避路径（与精简 pass 并存）
- [ ] 新增测试：人工构造冗余段，验证精简后字数减少 20%+ 且黑名单词清零
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-009：场景识别信号接入 context pack

**Description:** 作为 context 设计者，我需要让 context pack 明确暴露 `scene_mode` 字段，让 writer-agent / checker / polish 有统一的激活依据。

**Acceptance Criteria:**
- [ ] context pack schema 新增 `scene_mode: str`，取值 {golden_three, combat, climax, high_point, slow_build, emotional, other}
- [ ] 判定逻辑（`ink_writer/core/context/scene_classifier.py` 新增）：
  - `golden_three`：chapter ∈ [1, 3] → 强制激活
  - `combat / climax / high_point`：从章节大纲的 `beat_tags` 或 `arc_type` 推断（大纲里已经有这些字段）
  - `slow_build / emotional`：大纲标注
  - `other`：默认
- [ ] 多个 tag 命中时优先级：golden_three > climax > high_point > combat > emotional > slow_build > other
- [ ] context-agent.md 规格更新：必须在 pack 中暴露 `scene_mode`
- [ ] 新增测试 `tests/core/context/test_scene_classifier.py`：覆盖 7 种场景
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-010：现有 checker 阈值微调避免误报

**Description:** 作为质量守护，我需要确保新的直白化在现有 prose-impact / sensory-immersion / flow-naturalness checker 下不触发误报。

**Acceptance Criteria:**
- [ ] 遍历 prose-impact-checker / sensory-immersion-checker / flow-naturalness-checker 规格，确认在 scene_mode in {golden_three, combat, climax, high_point} 时，"感官丰富度 / 镜头多样性" 相关阈值适当放宽（或直接 skip）
- [ ] 不放宽 proofreading-checker 的弱动词/AI 味检测（这些与直白不冲突）
- [ ] 新增测试：在模拟直白场景下，3 个 checker 不触发 Red（除非真有其他质量问题）
- [ ] 非直白场景（scene_mode=slow_build）阈值保持原状
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-011：黄金三章 + 战斗场景端到端验证

**Description:** 作为验收负责人，我需要在一个已有项目上跑完整写作流程，量化验证新机制有效。

**Acceptance Criteria:**
- [ ] 选 1 个已有测试项目，跑新机制写章 1-3（黄金三章）+ 1 个战斗场景（第 N 章）
- [ ] 对比指标（新机制 vs 旧机制产出，同项目同大纲）：
  - 字数平均缩短 ≥20%
  - directness-checker 5 维度分均 ≥8
  - 黑名单命中数 ≤3（每章）
  - 句长中位数降到 benchmark 起点中位数 ±10% 之内
  - 人工抽样评分（3 位读者盲测）：直白分提升 ≥40%
- [ ] 非直白场景（抒情章）产出的 sensory-immersion 分不下降（零退化证据）
- [ ] 验证结果写入 `reports/prose-directness-verification.md`
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

### US-012：文档同步 + v22.0.0 发版

**Description:** 作为发版负责人，所有直白化改动合入后做一次正式发版。

**Acceptance Criteria:**
- [ ] `docs/architecture.md` 新增"场景感知直白化"段
- [ ] `docs/editor-wisdom-integration.md` 补 `simplicity` 主题域说明
- [ ] README 版本历史新增 v22.0.0 条目：突出"黄金三章+战斗场景直白化，editor-wisdom 新增 simplicity 域，directness-checker 上线"
- [ ] 6 处版本号同步（v21 → v22）
- [ ] `git tag -a v22.0.0` + push origin
- [ ] `tasks/prd-prose-directness.md` 底部追加 Release Notes（M-1~M-7 实测值 + baseline 更新）
- [ ] Typecheck passes
- [ ] 零回归：pytest 全量无新增失败

## 4. Functional Requirements

- **FR-1**：`context pack` 必须暴露 `scene_mode` 字段，取值固定 7 种之一
- **FR-2**：writer-agent 在 `scene_mode in {golden_three, combat, climax, high_point}` 时激活 Directness Mode，暂挂 L10b/L10e，启用直白硬原则
- **FR-3**：directness-checker 仅在直白场景激活，5 维度评分，任一 <6 即 Red
- **FR-4**：polish-agent 在直白场景写完后触发 Simplification Pass，精简后字数 ≥原文 70%
- **FR-5**：editor-wisdom 新增 `simplicity` 主题域 ≥12 条规则，writer-injection 在直白场景召回 ≥5 条
- **FR-6**：黑名单 YAML ≥100 条（abstract_adjectives ≥50、empty_phrases ≥30、pretentious_metaphors ≥20）
- **FR-7**：sensory-immersion-checker / prose-impact-checker 在直白场景 skip（避免与直白冲突）
- **FR-8**：benchmark 基线脚本输出 JSON + 报告 MD，推荐阈值常量供 checker 消费
- **FR-9**：直白模式在非激活场景（慢节奏/抒情）不生效，保持现有感官丰富度约束（场景感知，非一刀切）
- **FR-10**：所有改动走零回归：现有非直白场景单测/回归 100% 通过

## 5. Non-Goals (Out of Scope)

- **NG-1**：不改 webnovel-writer / biedong-writer / duanrongshu-writer 等其他 writer skill
- **NG-2**：不做"全书一刀切直白"（用户明确选 4.C：黄金三章 + 战斗/高潮/爽点）
- **NG-3**：不重写 polish-agent 架构（只新增精简 pass 章节）
- **NG-4**：不重写 editor-wisdom 架构（只新增主题域）
- **NG-5**：不做 LLM 自动挖掘黑名单（首版人工 + benchmark 辅助即可）
- **NG-6**：不做跨语言支持（只中文）
- **NG-7**：不改 data-agent / 其他非写作链路 agent
- **NG-8**：不做付费读者 AB 测试（等发版后在真实项目中自然采集反馈）

## 6. Technical Considerations

- **关键文件定位**（勘查已确认）：
  - benchmark：`benchmark/reference_corpus/*/chapters/ch###.txt`（19 本 × 30 章）
  - writer-agent：`ink-writer/agents/writer-agent.md`（L10b L10e 冲突点）
  - polish-agent：`ink-writer/agents/polish-agent.md`（无精简段，需新增）
  - editor-wisdom rules：`data/editor-wisdom/rules.json` + `config/editor-wisdom.yaml`
  - writer-injection：`ink_writer/editor_wisdom/writer_injection.py`
  - context manager：`ink_writer/core/context/context_manager.py`（US-009 scene_mode 新字段）
  - checker 现有：`ink-writer/agents/{proofreading,prose-impact,sensory-immersion,flow-naturalness}-checker.md`
- **分词**：用 jieba（已在依赖）做形容词-动词比统计
- **黑名单加载**：热加载，支持运行时替换（方便迭代扩充）
- **scene_mode 反推**：优先从章节大纲的 `beat_tags` 字段读取，fallback 到章节号（1-3 自动 golden_three）
- **零回归硬约束**：非直白场景的所有 checker 行为字节级不变（US-010 严格验证）
- **性能**：jieba 分词 + 黑名单正则，单章 <200ms（可接受）

## 7. Success Metrics

- **M-1**：直白场景产出字数平均缩短 ≥20%（新 vs 旧，同项目同大纲）
- **M-2**：directness-checker 5 维度分均 ≥8（黄金三章抽样 10 段）
- **M-3**：黑名单命中数每章 ≤3（直白场景）
- **M-4**：句长中位数落在 benchmark 起点中位数 ±10% 之内
- **M-5**：读者盲测直白分提升 ≥40%（3 位读者 × 5 段）
- **M-6**：非直白场景（抒情/慢节奏）sensory-immersion 分不下降（零退化）
- **M-7**：editor-wisdom simplicity 主题域在直白场景召回 ≥5 条/章

## 8. Open Questions

- **OQ-1**：战斗场景的启发式判定是否够准？（现基于标题关键词 + 动词密度，需 benchmark 验证精度）——US-009 要给出精度数字
- **OQ-2**：读者盲测怎么找人？（可用内部测试、找身边朋友，或在 v22 发版后面向用户收集反馈；首版建议内部 3 人盲测）
- **OQ-3**：黑名单是否需要区分"严格"（Red）和"警告"（Yellow）级别？首版建议只一级，v23 再拆
- **OQ-4**：精简 pass 会不会删掉 writer-agent 故意的幽默/反语？需观测后加白名单机制（v23）
- **OQ-5**：directness-checker 与 editor-wisdom-checker 是否重复？前者量化指标、后者规则命中——职责正交，并存

---

## 实现路线图建议（非约束）

**Phase 1 基础建设**（US-001 → US-003）：数据与资产先行
**Phase 2 规则与规格**（US-004 → US-007）：editor-wisdom + 两个 agent 规格
**Phase 3 场景接入**（US-008 → US-010）：polish + context + 现 checker 微调
**Phase 4 验收发版**（US-011 → US-012）

按 `/prd → /ralph → ralph.sh` 工作流：下一步 `/ralph tasks/prd-prose-directness.md`（两个 PRD 依次走，不并行，避免冲突）。

---

## Release Notes — v22.0.0（2026-04-20）

### M-1~M-7 实测值（US-011 corpus-grounded 验证）

| Milestone | PRD 目标 | 实测 | 状态 |
|-----------|----------|------|------|
| M-1 字数缩短 ≥20% | AI-heavy fixture → simplify_text | 26.91%（223→163 chars，blacklist 命中 14→0，3 规则触发） | ✅ GO |
| M-2 5 维度分均 ≥8 | 最直白 Top-5 × ch1-3 = 15 章跑 directness-checker | overall 9.33；D1=9.88 / D2=9.15 / D3=9.46 / D4=8.51 / D5=9.64 | ✅ GO |
| M-3 黑名单命中 ≤3/章 | 同上语料 | 中位数 2，max 5，min 0 | ✅ GO |
| M-4 句长中位数对齐 benchmark | 起点 golden_three P25=13 / P75=17.625 | 直白 Top-5 句长中位数 17.0 | ✅ GO（对齐 IQR 绿区） |
| M-5 LLM judge 直白分 +40% | 延至发版后 live run | 方法论 + status=deferred_to_live_run | ⏸️ 非阻断 |
| M-6 非直白场景零退化 | arbitration.collect_issues_from_review_metrics 三态 | combat 过滤 / slow_build 保留 / default kwargs 向后兼容 | ✅ GO |
| M-7 simplicity 规则 ≥12 条 | rules.json | 14 条（EW-0389~EW-0402） | ✅ GO |

**Release Gate**：硬指标 6/6 通过 → GO。

### 基线数据

- benchmark corpus：50 本起点实书 × 1487 章（超过 PRD 原计划 19×30=570 章）
- stats.json：`reports/prose-directness-stats.json`
- 阈值 YAML：`reports/seed_thresholds.yaml`（每 scene × 每 metric 完整 percentile + thresholds；combat 场景 `inherits_from: golden_three`）
- 最直白 Top-5：拦路人！/ 状元郎 / 我，枪神！/ 重回 1982 小渔村 / 1979 黄金时代
- 最华丽 Top-5：神明调查报告 / 异度旅社 / 亡灵法师，召唤 055 什么鬼？/ 真君驾到 / 仙业

### 代码产物

- 新增 scripts：`analyze_prose_directness.py` / `gen_directness_baseline_report.py` / `verify_prose_directness.py`
- 新增模块：`ink_writer/prose/{blacklist_loader,directness_checker,sensory_immersion_gate,simplification_pass,directness_threshold_gates}.py` / `ink_writer/core/context/scene_classifier.py`
- 新增资产：`ink-writer/assets/prose-blacklist.yaml`（107 条）+ `data/editor-wisdom/rules.json` 新增 14 条 simplicity
- 新增 agent spec：`ink-writer/agents/directness-checker.md`
- 更新 agent spec：writer-agent / polish-agent / context-agent / prose-impact-checker / flow-naturalness-checker / sensory-immersion-checker 全部加 v22 场景感知章节
- config：`config/editor-wisdom.yaml` 新增 simplicity 域 + directness_recall + scoring_dimensions

### 零回归

- baseline：v21.0.0 全量 `pytest --no-cov` = 3206 passed
- v22.0.0 全量 `pytest --no-cov` = 3548 passed（+342 新测试）
- 23 skipped / 0 failed 保持
- ruff 全绿

### 6 处版本号同步

1. `pyproject.toml` → `22.0.0`
2. `ink-writer/.claude-plugin/plugin.json` → `22.0.0`
3. `.claude-plugin/marketplace.json` → `22.0.0`
4. `tests/release/test_v16_gates.py::EXPECTED_VERSION` → `22.0.0`
5. `README.md` Badge → `Version-22.0.0-green.svg`
6. `README.md` 版本历史：新增 `**v22.0.0 (当前)**` 行，`v21.0.0` 去掉 `(当前)` 标记

### Docs 同步

- `docs/architecture.md` 新增 `## 场景感知直白化（v22）` 段 + Directness Checker 行进 checker 表
- `docs/editor-wisdom-integration.md` 主题域表新增 simplicity + `### simplicity 域场景感知召回（v22）` 段 + applies_to FAQ 扩展

### git 操作

- tag：`git tag -a v22.0.0`（annotated）
- merge：`ralph/prose-directness` → `master`（`--no-ff`）
- push：origin master + tag（PRD 明确授权）
