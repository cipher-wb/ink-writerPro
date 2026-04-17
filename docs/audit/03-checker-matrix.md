# US-003: 14+ Checker 职责矩阵 + 去重分析

**审计者**: US-003 执行者
**日期**: 2026-04-17
**只读审计**，未修改任何文件
**证据基线**: ink-writer v13.8.0（HEAD=349f651）

---

## Executive Summary

项目宣称「14+ checker」，实际扫描发现 **16 个 checker 规格文件** + **3 个 tracker 规格文件**（其中 2 个已合并为 1）+ 1 个未实现的 `voice-fingerprint`（polish-agent 引用但无对应规格）。

核心发现：

1. **多层硬门禁并行执行**，实际拦截机制分布在 3 处：
   - `ink_writer/editor_wisdom/review_gate.py`（editor-wisdom 独立 retry-3 loop）
   - `ink-writer/scripts/step3_harness_gate.py`（读 review 报告做 Python 级硬拦截）
   - `step-3-review-gate.md` 内 **9 个门禁规则**（逻辑 / 大纲合规 / 卖点密度 / 主角能动性 / 人类本能反应 / 文笔工艺 / 文笔冲击力 / 自然流畅度 / 时间线）——文档级规则，由 Claude Code Task 执行时遵循

2. **严重孤儿模块**：`ink_writer/checker_pipeline/`（CheckerRunner + GateSpec）**无任何生产调用**——只有测试与自身 `__init__` 引用。v13 规划的"统一并行引擎"至今未接入 Python 层，实际并行由 Claude Code Task 调度器完成。

3. **已合并但未清理**：`foreshadow-tracker.md` 与 `plotline-tracker.md` 已由 `thread-lifecycle-tracker.md` 统一替代（thread-lifecycle-tracker.md:220 明确写"原 XX 和 YY 的输出格式仍受支持"），但两个老 agent 文件仍在 `agents/` 目录，形成僵尸规格。

4. **规格-引用名不一致**：`voice-fingerprint` 被 polish-agent.md:135、144 引用作为 "语气指纹门禁"，但 `agents/` 下无 `voice-fingerprint-checker.md`，仅在 `ink_writer/voice_fingerprint/` Python 模块存在。

5. **硬门禁不是纯"一票否决"**——采用**混合模式**：
   - 并行层：CheckerRunner 设计了 `is_hard_gate + cancel_event` 机制（首个硬门禁失败 cancel 其余），但**该代码未被调用**
   - 真实执行层：`step-3-review-gate.md` 按权重累加总分（Σ(score × weight)），同时每类 critical issue 作为 hard block 独立触发回退 Step 2A
   - 兼有 **评分累计**（overall_score cap=50/55/60）与 **一票否决**（单个 critical → 回退）两种机制

---

## 1. 完整 Checker 矩阵表

### 1.1 规格文件清单（`ink-writer/agents/*-checker.md` + 相关 tracker）

| # | Agent 名 | 文件路径 | 大小 | 最后修改 | 状态 |
|---|---------|---------|------|---------|------|
| 1 | anti-detection-checker | ink-writer/agents/anti-detection-checker.md | 13KB | 04-11 | 活跃 |
| 2 | consistency-checker | ink-writer/agents/consistency-checker.md | 12KB | 04-16 | 活跃 |
| 3 | continuity-checker | ink-writer/agents/continuity-checker.md | 9KB | 04-16 | 活跃 |
| 4 | editor-wisdom-checker | ink-writer/agents/editor-wisdom-checker.md | 5KB | 04-17 | 活跃（独立门禁） |
| 5 | emotion-curve-checker | ink-writer/agents/emotion-curve-checker.md | 4KB | 04-16 | 活跃 |
| 6 | flow-naturalness-checker | ink-writer/agents/flow-naturalness-checker.md | 20KB | 04-17 | 活跃（US-014 核心） |
| 7 | golden-three-checker | ink-writer/agents/golden-three-checker.md | 11KB | 04-17 | 活跃 |
| 8 | high-point-checker | ink-writer/agents/high-point-checker.md | 21KB | 04-17 | 活跃 |
| 9 | logic-checker | ink-writer/agents/logic-checker.md | 26KB | 04-16 | 活跃 |
| 10 | ooc-checker | ink-writer/agents/ooc-checker.md | 17KB | 04-17 | 活跃 |
| 11 | outline-compliance-checker | ink-writer/agents/outline-compliance-checker.md | 24KB | 04-16 | 活跃 |
| 12 | pacing-checker | ink-writer/agents/pacing-checker.md | 9KB | 04-16 | 活跃 |
| 13 | proofreading-checker | ink-writer/agents/proofreading-checker.md | 19KB | 04-17 | 活跃 |
| 14 | prose-impact-checker | ink-writer/agents/prose-impact-checker.md | 15KB | 04-17 | 活跃（US-014） |
| 15 | reader-pull-checker | ink-writer/agents/reader-pull-checker.md | 14KB | 04-16 | 活跃 |
| 16 | sensory-immersion-checker | ink-writer/agents/sensory-immersion-checker.md | 14KB | 04-17 | 活跃（US-014） |
| T1 | thread-lifecycle-tracker | ink-writer/agents/thread-lifecycle-tracker.md | — | 04-16 | 活跃（合并 F+P） |
| T2 | foreshadow-tracker | ink-writer/agents/foreshadow-tracker.md | — | 04-16 | **僵尸**（已并入 T1） |
| T3 | plotline-tracker | ink-writer/agents/plotline-tracker.md | — | 04-16 | **僵尸**（已并入 T1） |
| T4 | reader-simulator | ink-writer/agents/reader-simulator.md | — | — | 活跃（Core 快速模式） |
| V | voice-fingerprint | （无对应 .md） | — | — | **文档引用但无规格** |

### 1.2 Checker × 检测维度矩阵

列：**句**=句式/句长节奏；**情**=情节推进/大纲合规；**角**=角色/OOC/voice；**文**=文笔质量/修辞；**构**=段落/章节结构；**AI**=AI味/反检测；**伏**=伏笔/线程生命周期；**节**=节奏/strand平衡；**爽**=爽点/读者期待；**感**=感官/情绪曲线；**逻**=章内逻辑自洽；**设**=跨章设定一致性

| Checker | 句 | 情 | 角 | 文 | 构 | AI | 伏 | 节 | 爽 | 感 | 逻 | 设 |
|---------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| consistency-checker | | P | Y | | | | | | | | P | **Y** |
| continuity-checker | | **Y** | | | P | | P | | | | P | P |
| ooc-checker | | | **Y** | | | | | | | | | P |
| logic-checker | | P | P | | | | | | | | **Y** | |
| outline-compliance-checker | | **Y** | P | | | | P | | | | | |
| reader-pull-checker | | | | | | | | | **Y** | P | | |
| anti-detection-checker | **Y** | | | P | P | **Y** | | | | | | |
| flow-naturalness-checker | Y | | Y | P | P | P | | | | | | |
| golden-three-checker | | P | P | P | P | | | | P | | | |
| high-point-checker | | P | P | | | | | P | **Y** | P | | |
| pacing-checker | | P | | | | | | **Y** | | | | |
| proofreading-checker | P | | P | **Y** | **Y** | | | | | P | | |
| prose-impact-checker | **Y** | | | **Y** | | | | | | **Y** | | |
| sensory-immersion-checker | | | | P | | | | | | **Y** | | |
| emotion-curve-checker | | | | | | | | | | **Y** | | |
| editor-wisdom-checker | P | P | P | P | P | P | | | | | | |
| thread-lifecycle-tracker | | P | | | | | **Y** | | | | | |
| reader-simulator | | | P | | | | | | P | **Y** | | |

图例：**Y**=主要维度；P=次要/局部覆盖；空=不覆盖。

### 1.3 输入契约（`review_bundle_file` 瘦身包 profile）

来源：`ink-writer/skills/ink-write/references/step-3-review-gate.md:102-133`

| Checker | 瘦身字段 |
|---------|---------|
| anti-detection-checker | chapter_text |
| logic-checker | chapter_text、scene_context、setting_snapshots、core_context、precheck_results |
| outline-compliance-checker | chapter_text、outline、scene_context、core_context、MCC 板块14 |
| continuity-checker | chapter_text、previous_chapters、memory_context、outline、narrative_commitments、plot_structure_fingerprints |
| consistency-checker | chapter_text、setting_snapshots、scene_context、previous_chapters、memory_context、narrative_commitments、plot_structure_fingerprints（最重量）|
| ooc-checker | chapter_text、scene_context、previous_chapters、setting_snapshots |
| reader-pull-checker | chapter_text、reader_signal、memory_context、outline、golden_three_contract |
| flow-naturalness-checker | chapter_text、outline、scene_context、voice_profile、info_budget |

条件 checker 复用最近核心 checker 的 profile（见 step-3-review-gate.md:124）。

### 1.4 输出 Schema

全部 checker 统一遵循 `ink-writer/references/checker-output-schema.md`：
- 必填：`agent`、`chapter`、`overall_score`、`pass`、`issues[]`、`metrics`、`summary`
- issue 必填：`type/severity/location/description/suggestion`
- 扩展字段（如 `hard_violations`、`soft_suggestions`、`fix_prompt`、`reader_verdict`）允许，但不替代必填

### 1.5 硬门禁触发条件（来自 step-3-review-gate.md:286-691）

| 门禁名称 | 依赖 Checker | Hard Block 条件 | 位置 |
|---------|-------------|----------------|------|
| 逻辑门禁 | logic-checker | 任一 critical；或 ≥2 high | step-3-review-gate.md:305-332 |
| 大纲合规门禁 | outline-compliance-checker | 任一 critical；或 ≥2 high | step-3-review-gate.md:334-360 |
| 卖点密度门禁 | high-point-checker | `SELLING_POINT_DEFICIT.critical`；连续2章缺失 | :362-396 |
| 主角能动性门禁 | high-point-checker | `CAMERA_PROTAGONIST.critical`；黄金三章 `PASSIVE_STREAK.high` | :398-446 |
| 人类本能反应门禁 | ooc-checker | `NO_RESPONSE_TO_INJURY.critical`；黄金三章 `FLAT_TO_LIFE_THREAT.high` 等 | :448-495 |
| 文笔工艺门禁 | proofreading-checker Layer 6 | `WEAK_VERB_OVERUSE.TOTAL.critical`；`SENSORY_DESERT.CHAPTER.critical` | :497-549 |
| 文笔冲击力门禁 | prose-impact-checker | 任一维度 critical；黄金三章 ≥C 升级 | :574-615 |
| 自然流畅度门禁 | flow-naturalness-checker | `INFO_OVERLOAD.CHAPTER.critical`、`DIALOGUE_INDISTINGUISHABLE.critical` 等 | :617-661 |
| 时间线闸门 | 跨 checker 聚合 | `TIMELINE_ISSUE.severity >= high` | :663-692 |
| 黄金三章硬拦截 | golden-three-checker | ch1-3 且任一 high issue | :300 |
| 反 AI 开头硬拦截 | anti-detection-checker | opening pattern critical（cap overall_score=60） | :301 |
| 读者体验阻断 | reader-simulator | ch1-3 且 `reader_verdict.verdict=="rewrite"` | :303 |
| Editor-Wisdom 门禁 | editor-wisdom-checker | score < 0.75（普通）/ 0.90（黄金三章），3 次重试 | review_gate.py:78-168 |
| Voice 指纹门禁 | voice-fingerprint（Python） | 综合评分 < 60，2 次重试 | SKILL.md:1549-1567 |
| Plotline 推进门禁 | plotline.tracker（Python） | 主线断更 >3 章未推进 | SKILL.md:1569-1587 |
| Python 后置闸 | 读 review_ch*.json | overall_score<40；critical≥3；reader-simulator rewrite | scripts/step3_harness_gate.py:18-85 |

### 1.6 调用者（上游）

| Checker | 调用入口 | Skill | 触发条件 |
|---------|---------|-------|---------|
| 核心 8 个 | Task 并行发射 | ink-write Step 3 | 每章必跑 |
| golden-three-checker | Task | ink-write | ch <= 3 |
| high-point-checker | Task | ink-write | 关键/高潮/卷末章 |
| pacing-checker | Task | ink-write | ch >= 10 |
| proofreading-checker | Task | ink-write | ch >= 1（非过渡章）|
| reader-simulator | Task | ink-write / ink-review（Core，v9.0 升格） | 每章必跑（快速模式） |
| emotion-curve-checker | Task | ink-write | ch >= 5 + 条件 |
| prose-impact-checker | Task | ink-write | ch<=3 强制 + 战斗/高光章 |
| sensory-immersion-checker | Task | ink-write | ch<=3 强制 + 情感/悬疑/战斗 |
| editor-wisdom-checker | `run_review_gate()` | step3_harness_gate.py（Python）| 所有章节 |
| thread-lifecycle-tracker | Task | ink-write / ink-plan | 按章调度 |
| reader-pull-checker | Task | ink-write / ink-review | 始终启用 |

**注**：所有 Task 并发实际由 Claude Code 调度器控制（`max_concurrency = len(selected)`），不经过 `ink_writer/checker_pipeline/` 的 Python CheckerRunner。

### 1.7 下游消费（polish-agent 消费映射）

来源：`ink-writer/agents/polish-agent.md`

| Checker | 消费字段 | polish-agent 步骤 |
|---------|---------|------------------|
| logic-checker | logic_fix_prompt | Step 1.1 |
| outline-compliance-checker | outline_fix_prompt | Step 1.2 |
| reader-pull-checker | hook_fix_prompt | Step 1.5 |
| emotion-curve-checker | emotion_fix_prompt | Step 1.6 |
| anti-detection-checker | anti_detection_fix_prompt、fix_priority | Step 1.7、Step 3 |
| voice-fingerprint | voice_fix_prompt | Step 1.8 |
| editor-wisdom-checker | editor_wisdom_violations（hard/soft） | Step 2 |
| 其他 checker | 统一 issues[] | Step 2.5（按 priority 修复） |
| proofreading-checker Layer 6 | WEAK_VERB/SENSORY_DESERT | Step 4.5（Layer 8） |
| prose-impact-checker + sensory-immersion-checker + flow-naturalness-checker | shot_plan/sensory_plan/info_plan | Step 4.6（Layer 9） |

---

## 2. 重复检测发现（高优先级）

### 2.1 严重重复：镜头 / 感官 / 句式节奏 五重覆盖

同一组维度被多个 checker 同时检测：

| 维度 | 涉及 Checker | 证据 |
|------|-------------|------|
| **镜头多样性**（SHOT_MONOTONY/SHOT_DIVERSITY） | prose-impact-checker、proofreading-checker Layer 6B、editor-wisdom-checker（shot_diversity 维度 EW-0365/0366/0369）| prose-impact-checker.md:62-78、polish-agent.md:264 "对应规则码：SHOT_MONOTONY（writer-agent L10d / prose-impact-checker 镜头多样性 / proofreading 6B.1）" |
| **感官丰富度**（SENSORY_RICHNESS/ROTATION） | prose-impact-checker、sensory-immersion-checker、proofreading-checker Layer 6A、editor-wisdom-checker（sensory_richness）| polish-agent.md:277 "对应规则码：SENSORY_DESERT（Layer 8b 已处理量的底线）+ ROTATION_STALL / NON_VISUAL_BELOW_THRESHOLD（prose-impact / sensory-immersion）" |
| **句式节奏 / CV** | anti-detection-checker（第1层）、proofreading-checker Layer 6B、prose-impact-checker、editor-wisdom-checker（sentence_rhythm）、flow-naturalness-checker | anti-detection-checker.md:46-71；prose-impact-checker.md:22；polish-agent.md:305 |
| **弱动词** | proofreading-checker Layer 6A、polish-agent Layer 8a、prose-impact-checker（动词锐度） | polish-agent.md:220-222 |
| **信息密度** | flow-naturalness-checker（维度 1 INFO_DENSITY_EVENNESS）、anti-detection-checker（第2层）、proofreading-checker Layer 6B.4 INFO_DENSITY_OVERFLOW、editor-wisdom-checker（info_density_uniformity） | flow-naturalness-checker.md:53-80；polish-agent.md:290 "INFO_DENSITY_OVERFLOW（writer-agent L11 / proofreading 6B.4 / flow-naturalness 维度 1）"；anti-detection-checker.md:72-80 |

**风险**：同一违规在一章中被 2-4 个 checker 独立标记，导致 polish-agent 收到冲突/重复的 fix_prompt；step-3-review-gate.md:332 已提到 "`merged_fix_suggestion`（Layer 6A+6B 联合合并）" 作为缓解但未覆盖跨 checker 合并。

### 2.2 明示重复：跨章 vs 章内逻辑分工清晰但存在模糊地带

- `consistency-checker` 宣称"跨章设定"、`logic-checker` 宣称"章内微观"（logic-checker.md:10），但 **L7 对话归属**（logic-checker）与 ooc-checker **speech_violations**（checker-output-schema.md:109）存在重叠；L3 属性一致（logic）与 consistency power_violations 也重叠。

### 2.3 情节/大纲重叠

- `continuity-checker` 的 `outline_deviations`（schema.md:124）与 `outline-compliance-checker` 的 O3 目标充分性覆盖同一维度——前者弱，后者强。continuity-checker.md 本身也提到"伏笔管理"（line 21），与 thread-lifecycle-tracker 直接冲突。

### 2.4 OOC 语音重叠

- `ooc-checker` 中已有 speech_profile 检测（ooc-checker.md:37-43，含 vocab_level/sentence_habit/verbal_tics），`flow-naturalness-checker` 维度 4 对话辨识 + 维度 7 voice 一致性、以及独立的 `voice-fingerprint`（SKILL.md:1549-1567）全部检测角色对话一致。三重覆盖。

---

## 3. 孤儿 Checker 发现（高优先级）

### 3.1 僵尸规格文件（Top 优先级）

| 文件 | 实际状态 | 证据 |
|------|---------|------|
| `ink-writer/agents/foreshadow-tracker.md` | 已被 thread-lifecycle-tracker 合并，文件仍存在 | thread-lifecycle-tracker.md:220 "原 foreshadow-tracker 和 plotline-tracker 的输出格式仍受支持" |
| `ink-writer/agents/plotline-tracker.md` | 已被 thread-lifecycle-tracker 合并，文件仍存在 | 同上 thread-lifecycle-tracker.md:220-222 |

**修复建议**：归档至 `archive/` 或删除，以防误调用旧 agent 名。

### 3.2 规格-引用不匹配（Top 优先级）

| 引用处 | 引用名 | 实际状态 |
|-------|--------|---------|
| polish-agent.md:40、135、144 | voice-fingerprint | **无对应 agent 规格文件** |
| SKILL.md:1560 | voice_fix_prompt 来自 voice-fingerprint 门禁 | 实际由 `ink_writer.voice_fingerprint.ooc_gate.run_voice_gate()` Python 模块实现，非 subagent |
| SKILL.md:1580 | plotline_fix_prompt 来自 plotline 门禁 | 实际由 `ink_writer.plotline.tracker.scan_plotlines()` 实现，非 subagent |

**风险**：文档把 Python 门禁混写为"checker"，造成读者误解门禁系统架构。

### 3.3 孤儿代码模块（最严重）

**`ink_writer/checker_pipeline/`**（runner.py + __init__.py）**未被任何生产代码 import**：

```
查询：`from ink_writer.checker_pipeline` 引用者
结果：
  - tests/checker_pipeline/test_checker_runner.py （测试）
  - ink_writer/checker_pipeline/__init__.py （自身）
```

- 设计目标：提供 asyncio.gather + 首个硬门禁失败立即 cancel 的统一并行引擎（runner.py:1-7）
- 实际状态：无任何 skill/script 调用 `CheckerRunner.run()`
- 影响：v13 规划的 "Python 统一 orchestration + 早失败" 至今**仅为未接入的原型**；所有并发由 Claude Code Task 调度器驱动
- archive 档案确认设计意图：`archive/2026-04-16-deep-review-and-perfection/prd.json:390` "CheckerRunner with asyncio parallel"

### 3.4 文档级"checker"未在实际调度列表

- `editor-wisdom-checker`：虽在 checker-output-schema.md:260 列出，但**不在 step-3-review-gate.md 的核心 8 / 条件 8 名单中**——它走独立路径（`Step 3.5` + `run_review_gate()`）
- 现象：审查文档有两个并行分类系统（常规 checker vs editor-wisdom hard gate），新人难以一眼看全

---

## 4. 硬门禁实现分析（核心问题）

### 4.1 机制并非单一，而是四重混合

**第 1 层：文档级 hard block 规则（9 个门禁）**
- 定义：step-3-review-gate.md 逐门禁明文规则
- 执行：Claude Code 在 ink-write Step 3 遵循
- 判定：每个门禁独立触发回退 Step 2A；**一票否决**
- 计数：每个门禁独立回退计数，各最多 2 次，第 3 次同章失败 → 人工干预（:546-567）

**第 2 层：综合评分 + score cap（评分累计）**
- 公式：`overall_score = Σ(checker_score × weight) / Σ(active_weights)`（:205-213）
- critical cap：任一 critical → overall_score ≤ 60；logic/outline critical → ≤ 50；prose_impact critical → ≤ 55；flow_naturalness critical → ≤ 55
- 本质是**评分累计的硬上限**，不是"任一 fail → 立刻阻断"

**第 3 层：Python 后置闸（step3_harness_gate.py）**
- 位置：`ink-writer/scripts/step3_harness_gate.py:18-85`
- 触发：`check_review_gate()`
- 规则：
  - 黄金三章 + golden-three 有 high issue → block（:50-58）
  - ch1-3 + reader-simulator rewrite → block（:60-70）
  - overall_score < 40 → block（:73-77）
  - critical_count >= 3 → block（:80-83）
- 执行路径：读取已生成的 review_ch*.json 做判定（事后检查）

**第 4 层：editor-wisdom retry loop（独立 retry-3 + polish-2）**
- 位置：`ink_writer/editor_wisdom/review_gate.py:78-168`
- 阈值：golden_three_threshold=0.90（ch1-3），hard_gate_threshold=0.75（其余）
- 逻辑：检查失败 → polish → 重试，最多 3 次 check + 2 次 polish；仍失败 → 写 blocked.md 并抛 `ChapterBlockedError`
- 调用：由 `scripts/step3_harness_gate.py:106-158 run_editor_wisdom_gate()` wire 进 main() 流程

### 4.2 "一票否决 vs 评分累计" 的真实答案

**答**：**两种机制并存，分域运作**：

- 一票否决（hard block，回退 Step 2A）：9 个文档级门禁 + Python 后置闸 4 条规则 + editor-wisdom retry loop 终态
- 评分累计（weighted overall_score）：13 个权重 checker 以 25/20/15/15/15/10/10/5/5/5/5/3 % 混合加权 + critical cap

**并非** CheckerRunner 设计的"首个硬门禁失败立即 cancel 其余"——该 Python 机制在 runner.py:174-178 存在，但未接入生产路径。

### 4.3 硬门禁 vs checker_pipeline 的割裂

CheckerRunner 定义了 `is_hard_gate` 标记与 `cancel_event`：

```
runner.py:232-233:
    if status == GateStatus.FAILED and gate.is_hard_gate:
        cancel_event.set()
```

但它从未被 import 到任何 skill/script 调用链。真实并行由 Claude Code 并发发射 Task，Claude 自主遵循 step-3-review-gate.md 的门禁规则。

---

## 5. 交叉验证：polish-agent 是否消费每个 checker 的报告？

verified via `ink-writer/agents/polish-agent.md` + `ink-writer/skills/ink-write/SKILL.md:1437-1587`：

| Checker | 有专用 fix_prompt 通道 | polish 步骤 | 通道验证 |
|---------|----------------------|-----------|---------|
| logic-checker | logic_fix_prompt | 1.1 | ✅ polish-agent.md:64-83 |
| outline-compliance-checker | outline_fix_prompt | 1.2 | ✅ polish-agent.md:85-99 |
| reader-pull-checker | hook_fix_prompt | 1.5 | ✅ polish-agent.md:101-108 |
| emotion-curve-checker | emotion_fix_prompt | 1.6 | ✅ polish-agent.md:110-118 |
| anti-detection-checker | anti_detection_fix_prompt + fix_priority | 1.7, 3 | ✅ polish-agent.md:120-131、178-193 |
| voice-fingerprint | voice_fix_prompt | 1.8 | ⚠️ 引用但无 agent 规格 |
| editor-wisdom-checker | editor_wisdom_violations | 2 | ✅ polish-agent.md:146-162 |
| prose-impact-checker + sensory-immersion-checker + flow-naturalness-checker | 合并 Layer 9 | 4.6 | ✅ polish-agent.md:250-330 |
| proofreading-checker Layer 6 | 合并 Layer 8 | 4.5 | ✅ polish-agent.md:213-248 |
| consistency-checker / continuity-checker / ooc-checker / high-point-checker / pacing-checker / golden-three-checker | 无专用通道，走通用 issues[] 修复 | 2.5 | △ 通过 polish-priority-rules.md 处理 |
| **reader-simulator** | **无 fix_prompt**；仅作为 Python 后置闸信号 | — | ❌ polish-agent 不消费，由 step3_harness_gate.py 拦截 |
| **thread-lifecycle-tracker** | **无 fix_prompt** | — | ❌ polish-agent 不消费，由 ink-plan 安排回收 |

**结论**：12/17 有直接消费，2/17（reader-simulator、thread-lifecycle-tracker）只进硬门禁不进 polish，2/17（voice-fingerprint、plotline）通道指向 Python 模块而非 subagent。

---

## 6. 结构图（文字版）

```
Claude Code Task 调度器
  │
  ├──并发发射──→ 核心 8 checker（必跑）
  │           ├→ consistency / continuity / ooc / logic / outline-compliance
  │           ├→ anti-detection / reader-pull / flow-naturalness
  │
  ├──条件发射──→ 条件 8 checker
  │           ├→ golden-three (ch<=3) / high-point / pacing / proofreading
  │           ├→ reader-simulator / emotion-curve / prose-impact / sensory-immersion
  │
  └──独立 Python 通道──→
              ├→ editor-wisdom-checker（run_review_gate retry-3）
              ├→ voice-fingerprint Python 模块（voice_fingerprint.ooc_gate）
              ├→ plotline scan（plotline.tracker）
              └→ step3_harness_gate.py（后置读 JSON 做 4 条硬规则）

结果汇总
  │
  ├──触发 9 个文档级 hard block 规则（任一触发 → 回退 Step 2A）
  │
  ├──加权 overall_score 计算（+ critical cap 50/55/60）
  │
  └──通过 → polish-agent 消费 issues[] + N 个 fix_prompt
             │
             └→ 6 层 polish（逻辑/大纲/追读/情绪/AI味/voice/毒点/文笔工艺/冲击力）
                    │
                    └→ Step 4.5 安全校验 diff → 覆盖原文件

（CheckerRunner / GateSpec 代码存在但未接入此链路 - 孤儿模块）
```

---

## 7. Top 3 重复或孤儿（按影响面排序）

### #1 孤儿：`ink_writer/checker_pipeline/`（整个模块）
- 文件：`ink_writer/checker_pipeline/__init__.py`、`ink_writer/checker_pipeline/runner.py`（249 行）
- 生产调用：0 处
- 测试调用：1 处（tests/checker_pipeline/test_checker_runner.py）
- 影响：浪费了 25 个单元测试维护成本；"统一并行 + 早失败"设计理念未真正兑现

### #2 重复：镜头 / 感官 / 句式节奏 4-5 重覆盖
- Checker：prose-impact-checker、sensory-immersion-checker、proofreading-checker Layer 6、flow-naturalness-checker、editor-wisdom-checker（prose_* 维度）
- 证据：polish-agent.md:264、277、290 显式写 "对应规则码 X / Y / Z"——同一问题被多个 checker 标记
- 影响：polish-agent 可能收到冲突 fix_prompt；token 预算膨胀；修复优先级难仲裁
- 现有缓解：step-3-review-gate.md:332 提到 "merged_fix_suggestion"（仅 Layer 6A+6B），未覆盖跨 checker 合并

### #3 僵尸：`foreshadow-tracker.md` + `plotline-tracker.md`
- 文件：`ink-writer/agents/foreshadow-tracker.md`、`ink-writer/agents/plotline-tracker.md`
- 状态：已被 thread-lifecycle-tracker 合并但文件仍存在
- 证据：thread-lifecycle-tracker.md:220-222 明确承接
- 影响：可能被误调度；agent 列表膨胀导致枚举困惑；部分文档（SKILL.md:1569-1587）仍引用 plotline 门禁但底层是 thread-lifecycle-tracker

---

## 8. Checker 系统整体连贯度（一句话总结）

**Checker 系统维度覆盖完整（12 大维度全覆盖）但连贯度 6/10**——核心链路（subagent → review bundle → hard gate → polish）清晰可运作，但存在 1 个未接入的并行引擎孤儿模块（`ink_writer/checker_pipeline/`）、2 个僵尸 tracker 规格、4-5 重的镜头/感官/句式节奏维度叠加检测（缺跨 checker fix 合并机制）、以及 "checker vs Python 门禁" 的双轨文档混用（voice-fingerprint/plotline 被文档称为 checker 实为 Python 模块），导致新人无法从规格文件一眼看全硬门禁触发图。

---

## 附录：证据文件索引

| 主题 | 关键文件 |
|------|---------|
| 并行引擎（孤儿） | ink_writer/checker_pipeline/runner.py、__init__.py |
| editor-wisdom hard gate | ink_writer/editor_wisdom/review_gate.py |
| Python 后置闸 | ink-writer/scripts/step3_harness_gate.py |
| Checker 调度文档 | ink-writer/skills/ink-write/references/step-3-review-gate.md |
| Checker 统一 schema | ink-writer/references/checker-output-schema.md |
| Polish 消费契约 | ink-writer/agents/polish-agent.md |
| 写作 Step 3 触发 | ink-writer/skills/ink-write/SKILL.md:1136-1587 |
| 审查 Skill 调用入口 | ink-writer/skills/ink-review/SKILL.md:125-200 |
| 合并 tracker | ink-writer/agents/thread-lifecycle-tracker.md |
| 僵尸 tracker | ink-writer/agents/foreshadow-tracker.md、plotline-tracker.md |
| voice-fingerprint Python | ink_writer/voice_fingerprint/ooc_gate.py（引用未读） |
