# Agent Topology v13

> US-401: Agent 职责重映射。基于 US-003 架构审计结果，消除职责重叠，统一 IO schema，输出清晰的拓扑图。

## Before (v12): 18 Agents, 2 Directories

```
ink-writer/agents/ (17 agents)
├── writer-agent.md          [Writing]
├── context-agent.md          [Context]
├── data-agent.md             [Data]
├── polish-agent.md           [Polish]
├── consistency-checker.md    [Review]
├── continuity-checker.md     [Review]
├── ooc-checker.md            [Review]
├── anti-detection-checker.md [Review]
├── proofreading-checker.md   [Review]
├── emotion-curve-checker.md  [Review]
├── high-point-checker.md     [Review]
├── pacing-checker.md         [Review]
├── reader-pull-checker.md    [Review]
├── reader-simulator.md       [Review]
├── golden-three-checker.md   [Review]
├── foreshadow-tracker.md     [Review/Planning] ← MERGED
└── plotline-tracker.md       [Review/Planning] ← MERGED

agents/ink-writer/ (1 agent)
└── editor-wisdom-checker.md  [Review]
```

**Issues identified by audit (US-003)**:
- 8 agent overlap pairs (mostly false positives from shared boilerplate)
- 43 repeated prompt fragments across agents
- foreshadow-tracker ↔ plotline-tracker: identical state machine, scoring model, ink-plan interaction
- Missing IO schema for 6 agents in checker-output-schema.md

## After (v13): 17 Agents, Unified Architecture

```
ink-writer/agents/ (16 agents)
├── writer-agent.md                [Writing]
├── context-agent.md               [Context]
├── data-agent.md                  [Data]
├── polish-agent.md                [Polish]
├── consistency-checker.md         [Review: Content]
├── continuity-checker.md          [Review: Content]
├── ooc-checker.md                 [Review: Content]
├── golden-three-checker.md        [Review: Content]
├── anti-detection-checker.md      [Review: Quality]
├── proofreading-checker.md        [Review: Quality]
├── emotion-curve-checker.md       [Review: Quality]
├── high-point-checker.md          [Review: Quality]
├── pacing-checker.md              [Review: Quality]
├── reader-pull-checker.md         [Review: Engagement]
├── reader-simulator.md            [Review: Engagement]
└── thread-lifecycle-tracker.md    [Review: Story] ← NEW (merged)

agents/ink-writer/ (1 agent)
└── editor-wisdom-checker.md       [Review: Quality]
```

### Changes Summary

| Change | Details |
|--------|---------|
| **Merged** | `foreshadow-tracker` + `plotline-tracker` → `thread-lifecycle-tracker` |
| **Added** | `references/shared-checker-preamble.md` (共享输入/输出/评分规则) |
| **Updated** | `checker-output-schema.md` (6 missing agent metrics added) |
| **Updated** | ink-plan SKILL.md references (foreshadow-tracker → thread-lifecycle-tracker[foreshadow]) |
| **Updated** | ink-write SKILL.md references (同上) |
| **Retained** | Old agent files kept for backward compatibility (agent name aliasing) |

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ink-write Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 0: Pre-flight                                             │
│  ├── thread-lifecycle-tracker[foreshadow] → forced_payoffs      │
│  └── Canary health scan                                         │
│                                                                 │
│  Step 1: Context Assembly                                       │
│  └── context-agent → 创作执行包 (3-layer)                       │
│                                                                 │
│  Step 2: Writing                                                │
│  └── writer-agent → 章节草稿                                    │
│                                                                 │
│  Step 3: Review Gate                                            │
│  ├── Core (always): consistency / continuity / ooc              │
│  │   + anti-detection / reader-pull                             │
│  ├── Conditional: golden-three / high-point / pacing            │
│  │   + proofreading / reader-simulator / emotion-curve          │
│  │   + editor-wisdom-checker                                    │
│  ├── Step 3.6: Hook retry gate                                  │
│  ├── Step 3.7: Emotion gate                                     │
│  ├── Step 3.8: Anti-detection gate                              │
│  ├── Step 3.9: Voice fingerprint gate                           │
│  └── Step 3.10: thread-lifecycle-tracker[plotline] gate         │
│                                                                 │
│  Step 4: Polish                                                 │
│  └── polish-agent → 润色后章节                                   │
│                                                                 │
│  Step 5: Data Extraction                                        │
│  └── data-agent → 实体/状态更新                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     ink-plan Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│  Step 2.4: thread-lifecycle-tracker[foreshadow] → forced_payoffs│
│  Step 2.5: high_point_scheduler → 爽点配方                      │
│  Step 2.7: thread-lifecycle-tracker[plotline] → forced_advances │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Responsibility Matrix

### Pipeline Stage Agents (4)

| Agent | Stage | Responsibility | Input | Output |
|-------|-------|---------------|-------|--------|
| context-agent | Context | 从 DB/state 组装创作执行包 | chapter_no, project_root | 3-layer execution pack |
| writer-agent | Writing | 消费执行包生成草稿 | Execution pack | Chapter .md file |
| polish-agent | Polish | 基于审查报告修复+去AI味 | Chapter + all review reports | Polished chapter + report |
| data-agent | Data | 实体提取、索引更新 | Chapter file, project_root | Entities, state changes |

### Content Review Agents (4)

| Agent | Focus | Unique Dimension |
|-------|-------|-----------------|
| consistency-checker | 设定守卫 (power/location/timeline) | 战力矛盾、地点错误、时间线冲突 |
| continuity-checker | 叙事流守卫 (scene transitions/thread coherence) | 场景过渡、逻辑漏洞、大纲偏离 |
| ooc-checker | 角色一致性 (personality/speech/behavior) | OOC 违规、人设漂移、语气指纹偏差 |
| golden-three-checker | 前3章专审 (ch1-3 only) | 10秒扫描、承诺兑现、开篇吸引力 |

### Quality Review Agents (5)

| Agent | Focus | Unique Dimension |
|-------|-------|-----------------|
| anti-detection-checker | AI味检测 (statistical features) | 句长CV、重复模式、连接词频次 |
| proofreading-checker | 文笔质量 (rhetoric/structure) | 修辞重复、段落结构、代称混乱 |
| emotion-curve-checker | 情绪弧线 (valence/arousal) | 平淡段检测、目标曲线对齐 |
| high-point-checker | 爽点密度 (payoff modes) | 8种爽点模式覆盖、密度分布 |
| pacing-checker | 节奏平衡 (Strand Weave) | Quest/Fire/Constellation 比例 |
| editor-wisdom-checker | 编辑智慧 (288 rules RAG) | 规则违规、分类建议 |

### Engagement Review Agents (2)

| Agent | Focus | Unique Dimension |
|-------|-------|-----------------|
| reader-pull-checker | 追读力 (hook/micropayoff) | 钩子类型/强度、微兑现密度、期望值债务 |
| reader-simulator | 读者体验模拟 (immersion) | 沉浸度、弃读热点、情绪曲线(读者视角) |

### Story Tracking Agent (1, merged)

| Agent | Focus | Thread Types |
|-------|-------|-------------|
| thread-lifecycle-tracker | 线程生命周期 | foreshadow (伏笔逾期/沉默) + plotline (主线/支线/暗线断更) |

## Overlap Analysis (False Positives Documented)

The US-003 audit flagged 8 overlap pairs. After deep analysis:

| Pair | Verdict | Reason |
|------|---------|--------|
| consistency ↔ continuity | **Keep separate** | Facts (设定) vs narrative flow (叙事流) |
| consistency ↔ ooc | **Keep separate** | World rules vs character behavior |
| consistency ↔ pacing | **Keep separate** | Data consistency vs rhythm balance |
| continuity ↔ ooc | **Keep separate** | Scene transitions vs personality |
| continuity ↔ pacing | **Keep separate** | Logic flow vs strand weave |
| ooc ↔ pacing | **Keep separate** | Character vs structure |
| anti-detection ↔ proofreading | **Keep separate** | AI statistical artifacts vs prose quality |
| foreshadow ↔ plotline | **MERGED** | Identical state machine, scoring, ink-plan interaction |

## Shared Infrastructure

### Shared Checker Preamble (`references/shared-checker-preamble.md`)
All review agents share:
- Input rules: review_bundle_file first, allowed_read_files fallback, .db禁止
- Output rules: checker-output-schema.md compliance
- Scoring rules: 0-100, pass≥60, critical cap

### Unified Output Schema (`references/checker-output-schema.md`)
v13 additions:
- emotion-curve-checker metrics
- anti-detection-checker metrics
- proofreading-checker metrics
- golden-three-checker metrics
- thread-lifecycle-tracker metrics (foreshadow + plotline)
- editor-wisdom-checker metrics
- Updated summary format with all 13 checkers

## Backward Compatibility

- Old agent files (`foreshadow-tracker.md`, `plotline-tracker.md`) retained
- Python modules unchanged: `ink_writer/foreshadow/` and `ink_writer/plotline/` remain separate
- Agent output `"agent": "foreshadow-tracker"` aliased to thread-lifecycle-tracker[foreshadow]
- Agent output `"agent": "plotline-tracker"` aliased to thread-lifecycle-tracker[plotline]
- All existing tests pass without modification
