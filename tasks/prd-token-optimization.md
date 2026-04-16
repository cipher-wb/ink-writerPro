# PRD: Token & Time 优化 — 不降质量的效率提升

## Introduction

ink-writer 当前单章写作耗时 **30 分钟以上**，核心瓶颈是 Step 3（7 个核心 checker 并行审查），占总 token 消耗约 47%。同一篇正文被 7 个 checker 各读一遍，审查包中 30-40% 的字段对特定 checker 无用。

本 PRD 的所有优化都是**纯机械层面**的：减少重复数据传输、用 Python 计算替代部分 LLM 判断、跳过可证明冗余的步骤。**核心承诺：传给 AI 的创作信息量和审查标准零削减**。

### 质量保障机制

每项优化都附带**质量验证协议**：优化前后使用同一章大纲、同一 context 执行包，对比审查分数。若优化后 overall_score 下降超过 2 分，该优化自动回滚。

---

## Goals

- **G1**: 单章写作时间从 30+ 分钟降到 **20 分钟以内**（目标 -33%）
- **G2**: 单章 token 消耗降低 **30-40%**（主要节省在 Step 3）
- **G3**: 写作质量零下降 — 优化前后 overall_score 偏差 ≤ 2 分
- **G4**: 所有优化可独立开关，任一项出问题可单独关闭

---

## 优化分析：6 项措施的安全性论证

### A. Prompt 结构优化（最大化 Cache 命中）

**原理**：Claude Code CLI 内置 prompt cache（5 分钟 TTL）。在一个写作会话中，Step 1 → Step 2A → ... → Step 6 共享同一会话。如果 system prompt 中静态内容放在前面、动态内容放在后面，cache 命中率更高。

**为什么不影响质量**：AI 收到的内容完全相同，只是顺序调整让 cache 更有效。

### B. 审查包按 Checker 瘦身

**实测数据**（从 checker spec 逐一验证）：

| 字段 | 被消费 | 未消费 | 可安全移除的 checker |
|------|--------|--------|---------------------|
| `reader_signal` | reader-pull | 其他 6 个 | ✅ 从非 reader-pull 的包中移除 |
| `golden_three_contract` | reader-pull | 其他 6 个 | ✅ 从非 reader-pull 的包中移除 |
| `narrative_commitments` | consistency | 其他 6 个 | ✅ 从非 consistency 的包中移除 |
| `memory_context` | 4 个 checker | anti-detection, logic, outline | ✅ 从不需要的 3 个 checker 中移除 |

**为什么不影响质量**：每个 checker 收到的数据**不减少**——只是不再收到它根本不读的字段。

### C. 计算型预检替代部分 LLM 判断

**原理**：logic-checker 的 L1（数字算术）和 L3（属性一致）中，有些检查可以用 Python 正则 + 字符串匹配完成（如提取所有数字序列、检查角色名前后属性是否矛盾）。Python 预检通过 → 告知 LLM "L1/L3 已预检通过，重点检查 L2/L4-L8"，减少 LLM 需要分析的范围。

**为什么不影响质量**：LLM 仍然执行全部 8 层检查，只是对预检已通过的层可以快速确认而非逐行分析。如果 Python 预检漏报（false negative），LLM 仍会在自己的分析中发现问题。**双保险，不是替代**。

### D. Step 2B 降级为定向检查

**实测分析**：Step 2B（风格适配）的 style-adapter.md 自身已承认：

> "若 writer-agent 已内化风格参考样本，且产出文本的句长均值 > 20字、对话占比 > 10%，则 Step 2B 可简化为'仅检查红线清单'"

Writer-Agent 已有的覆盖：句长硬约束、对话占比硬约束、情感标点密度、风格参考样本内化。

Step 2B 的**残留独立价值**仅 3 项：超长句拆分（>55字）、总结式旁白删除、模板腔清除。

**优化方案**：先用 Python 计算句长均值和对话占比，若达标则 Step 2B 降级为"3 项红线定向检查"（从全文改写变为定向修复），省去重新生成全文的 output token。

**为什么不影响质量**：Step 2B 的 3 项残留职责全部保留。只是不再做 writer-agent 已经做过的工作（句式改写、对话标签优化等）。

### E. 早期章节 Context 预算自适应

**现状**：ch1 的 context 预算是 8000 tokens，但 ch1 没有任何历史数据（无前序摘要、无伏笔、无角色历史）。实际有效数据可能只有 2000-3000 tokens，剩下 5000 tokens 是空数组和 null 字段的 JSON 开销。

**优化方案**：context-agent 输出执行包时，自动裁剪值为空/null/空数组的字段，不输出冗余 JSON 结构。

**为什么不影响质量**：裁剪的是空数据，不是有内容的数据。`required_entities: []` 和不输出这个字段，对 writer 来说信息量相同。

### F. Data-Agent 结构化输出

**现状**：Data-Agent 输出自由格式文本，然后再解析为 JSON。有时输出冗余解释文字。

**优化方案**：在 data-agent prompt 中明确要求 JSON-only 输出（不含解释文字），减少 output token。

**为什么不影响质量**：提取的实体、关系、状态完全相同，只是格式更紧凑。

---

## User Stories

### US-001: 审查包按 Checker 生成专用瘦身版

**Description:** 作为 Step 3 审查流程，我需要为每个 checker 生成只包含其实际消费字段的专用审查包，而非传递完整包。

**Acceptance Criteria:**
- [ ] `step-3-review-gate.md` 新增 checker 输入 profile 映射表，定义每个核心 checker 需要的字段清单
- [ ] 审查包生成脚本（`ink.py extract-context --format review-pack-json`）支持 `--checker` 参数，按 profile 裁剪字段
- [ ] 7 个核心 checker 的专用包字段清单（从上方分析表直接映射）：
  - anti-detection: chapter_text + meta.chapter（最轻量，约 4KB）
  - logic: chapter_text + character_snapshot + setting_snapshot + mcc（约 8KB）
  - outline-compliance: chapter_text + outline_excerpt + character_snapshot + mcc（约 7KB）
  - continuity: chapter_text + previous_summary + memory_context + outline_excerpt（约 9KB）
  - consistency: chapter_text + setting_snapshot + character_snapshot + previous_summary + memory_context + narrative_commitments（约 11KB，最完整）
  - ooc: chapter_text + character_snapshot + previous_summary + setting_snapshot（约 8KB）
  - reader-pull: chapter_text + reader_signal + memory_context + outline_excerpt + golden_three_contract（约 8KB）
- [ ] 条件 checker 复用核心 checker 相近的 profile（如 golden-three-checker 复用 reader-pull profile）
- [ ] **降级兜底**：`--checker` 参数缺失时，退回完整包（向后兼容）
- [ ] 质量验证：对比裁剪前后同一章的 7 个 checker 输出，issues 列表必须完全一致

---

### US-002: logic-checker 计算型预检模块

**Description:** 作为 logic-checker 的前置优化，我需要一个 Python 脚本对 L1（数字算术）和 L3（属性一致）做快速预检，将结果注入 checker prompt 减少 LLM 分析范围。

**Acceptance Criteria:**
- [ ] 新建 `ink-writer/scripts/logic_precheck.py`，包含两个函数：
  - `precheck_arithmetic(chapter_text) -> dict`：提取章内所有数字序列（倒计时、金额、距离等），检查相邻数值的算术一致性
  - `precheck_attributes(chapter_text, character_snapshot) -> dict`：提取同一角色的所有属性描述，交叉验证一致性
- [ ] 预检结果为 JSON：`{"l1_precheck": "pass|issues_found", "l1_issues": [...], "l3_precheck": "pass|issues_found", "l3_issues": [...]}`
- [ ] 预检结果注入 logic-checker 的审查包（新增 `precheck_results` 字段）
- [ ] logic-checker.md 更新：当 `precheck_results.l1_precheck == "pass"` 时，L1 层可快速确认（但仍必须过一遍，作为双保险）
- [ ] Python 预检执行时间 < 1 秒
- [ ] 单元测试：至少 5 个测试用例（含第一章的实际 bug 作为回归测试）

---

### US-003: Step 2B 降级为定向红线检查

**Description:** 作为 ink-write 流程，我需要 Step 2B 在 writer-agent 产出已达标时（句长均值>20、对话占比>10%）降级为定向检查模式，只处理 3 项残留职责。

**Acceptance Criteria:**
- [ ] Step 2B 开始前新增 Python 快速统计：
  - 计算句长均值（按句号/问号/感叹号分句）
  - 计算对话占比（「」内文字 / 总字数）
  - 若句长均值 > 20 字 且 对话占比 > 10% → 进入"定向检查模式"
  - 否则 → 执行原有的全量风格适配
- [ ] 定向检查模式只做 3 件事：
  1. 拆分超长句（>55 字的非对话句）
  2. 删除总结式旁白（"由此可见"、"换句话说"等 AI 痕迹短语）
  3. 清除模板腔（检查 ai-word-blacklist.md 中的黑名单词）
- [ ] 定向检查模式的 prompt 长度 < 原全量模式的 30%
- [ ] SKILL.md Step 2B 流程更新，新增条件分支逻辑
- [ ] style-adapter.md 更新，明确两种模式的触发条件和职责
- [ ] 质量验证：对比全量模式和定向模式对同一章的输出，anti-detection-checker 分数偏差 ≤ 3

---

### US-004: 早期章节 Context 执行包自适应裁剪

**Description:** 作为 context-agent，我需要在输出执行包时自动裁剪值为空/null/空数组的字段，减少传给 writer-agent 的冗余 JSON。

**Acceptance Criteria:**
- [ ] context-agent.md 新增输出后处理规则：
  - 值为 `null`、`""`、`[]`、`{}` 的字段不输出
  - `not_specified` 状态的 MCC 字段不输出（writer 的自检已处理 not_specified）
  - 必保留字段（chapter_num、chapter_goal、required_entities）即使为空也输出
- [ ] 预估 ch1 执行包从 ~8000 tokens 压缩到 ~3000 tokens
- [ ] ch50+ 的执行包不受影响（因为字段大多有值）
- [ ] 质量验证：裁剪前后的执行包传给 writer-agent，产出正文的 overall_score 偏差 ≤ 1

---

### US-005: Data-Agent 结构化 JSON 输出约束

**Description:** 作为 data-agent，我需要在输出时只产出结构化 JSON，不输出解释文字，减少 output token。

**Acceptance Criteria:**
- [ ] data-agent.md 输出格式章节新增硬约束：
  - 输出必须为纯 JSON（不含 markdown、不含解释段落）
  - JSON 结构遵循现有 schema（entities、relations、scene_slices、summary 等）
  - 禁止在 JSON 之外输出任何"分析过程"或"思考步骤"
- [ ] 预估 output token 减少 20-30%
- [ ] Step 5 的解析逻辑不受影响（已经是 JSON 解析）
- [ ] 质量验证：对比优化前后的实体提取结果，实体数量和关系数量偏差 ≤ 5%

---

### US-006: SKILL.md Prompt 结构优化（Cache 命中最大化）

**Description:** 作为 ink-write SKILL.md，我需要重新组织参考文件的加载顺序，将静态内容前置、动态内容后置，最大化 Claude Code CLI 的 prompt cache 命中。

**Acceptance Criteria:**
- [ ] SKILL.md 中所有 Step 的参考文件加载规则重新排序：
  - 第一批加载（静态，跨章不变）：core-constraints.md、iron-laws.md、responsibility-boundary.md、knowledge-boundary-rules.md
  - 第二批加载（半静态，跨卷不变）：style-adapter.md、anti-detection-writing.md、scene-craft-index.md
  - 第三批加载（动态，每章变化）：执行包、审查包、正文
- [ ] writer-agent.md 中 PROMPT_TEMPLATE 引用顺序调整为静态优先
- [ ] 不改变任何文件的内容，只改加载顺序
- [ ] 记录优化前后的 prompt cache 命中率对比（通过 Claude Code 的观测日志）

---

### US-007: 质量验证脚本

**Description:** 作为开发者，我需要一个自动化脚本来验证优化前后的写作质量没有下降。

**Acceptance Criteria:**
- [ ] 新建 `scripts/verify_optimization_quality.py`
- [ ] 脚本接收两个审查报告目录（优化前/优化后），对比：
  - overall_score 差值（阈值：≤ 2 分）
  - 各 checker 分数差值（阈值：≤ 3 分）
  - issues 数量差值（优化后不得多于优化前超过 1 个）
  - 实体提取数量差值（阈值：≤ 5%）
- [ ] 输出结构化报告：`PASS` / `FAIL` + 详细对比表
- [ ] 任一指标超过阈值 → 输出 `FAIL` + 具体超标项
- [ ] 至少 3 个单元测试

---

## Functional Requirements

### 审查包优化
- **FR-01**: extract-context 脚本支持 `--checker` 参数按 profile 裁剪审查包
- **FR-02**: 7 个核心 checker 的输入 profile 定义在 step-3-review-gate.md
- **FR-03**: 降级兜底：参数缺失时返回完整包

### 计算型预检
- **FR-04**: logic_precheck.py 提供 L1/L3 预检函数
- **FR-05**: 预检结果注入 logic-checker 审查包的 `precheck_results` 字段
- **FR-06**: 预检执行时间 < 1 秒

### Step 2B 降级
- **FR-07**: Python 统计句长均值和对话占比
- **FR-08**: 达标时进入定向检查模式（3 项职责）
- **FR-09**: 未达标时执行原有全量风格适配

### Context 裁剪
- **FR-10**: 空值字段自动裁剪
- **FR-11**: 必保留字段列表硬编码

### Data-Agent 输出
- **FR-12**: 纯 JSON 输出，禁止解释文字

### Prompt 结构
- **FR-13**: 静态内容前置、动态内容后置

### 质量验证
- **FR-14**: 验证脚本对比 overall_score、checker 分数、issues 数量、实体数量
- **FR-15**: 任一指标超阈值 → FAIL

---

## Non-Goals

- **不合并或删除任何 checker** — 7 个核心 checker 全部保留
- **不降低 context token 预算** — 只裁剪空值，不减少有效数据
- **不修改 checker 的审查标准或 severity 定义**
- **不修改 writer-agent 的创作约束**
- **不减少任何 checker 的检查层数**
- **不跳过任何必要的审查步骤**

---

## Technical Considerations

### 预估效果

| 优化项 | Token 节省 | 时间节省 | 实现复杂度 |
|--------|-----------|---------|-----------|
| A. Prompt 结构优化 | ~10% 整体 | ~2 min | 低（改加载顺序）|
| B. 审查包瘦身 | ~30% Step 3 | ~3 min | 中（改脚本+配置）|
| C. 计算型预检 | ~15% Step 3 | ~1 min | 中（新 Python 脚本）|
| D. Step 2B 降级 | ~80% Step 2B | ~2 min | 低（条件分支）|
| E. Context 裁剪 | ~30% 早期章节 | ~1 min | 低（输出过滤）|
| F. Data-Agent JSON | ~20% Step 5 | ~1 min | 低（prompt 修改）|
| **合计** | **~35% 整体** | **~10 min** | - |

### 依赖关系

```
US-007 (质量验证脚本) ← 所有其他 US 都依赖它做验证

US-001 (审查包瘦身) — 独立
US-002 (计算预检) — 独立
US-003 (Step 2B 降级) — 独立
US-004 (Context 裁剪) — 独立
US-005 (Data-Agent JSON) — 独立
US-006 (Prompt 结构) — 独立
```

**US-007 应第一个实施**，其余 6 个互不依赖，可并行。

---

## Success Metrics

- **M1**: 单章写作时间 ≤ 20 分钟（从 30+ 分钟）
- **M2**: 优化前后 overall_score 偏差 ≤ 2 分（质量验证脚本自动检测）
- **M3**: 优化前后各 checker 分数偏差 ≤ 3 分
- **M4**: 优化前后实体提取数量偏差 ≤ 5%
- **M5**: 所有优化可通过环境变量单独关闭（如 `INK_OPTIMIZE_REVIEW_BUNDLE=false`）

---

## Open Questions

无。所有设计决策已在分析阶段确认。
