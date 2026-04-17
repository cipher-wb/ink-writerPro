# 系统架构与模块设计

## 核心理念

### 防幻觉三定律

| 定律 | 说明 | 执行方式 |
|------|------|---------|
| **大纲即法律** | 遵循大纲，不擅自发挥 | Context Agent 强制加载章节大纲 |
| **设定即物理** | 遵守设定，不自相矛盾 | Consistency Checker 实时校验 |
| **发明需识别** | 新实体必须入库管理 | Data Agent 自动提取并消歧 |

### Strand Weave 节奏系统

| Strand | 含义 | 理想占比 | 说明 |
|--------|------|---------|------|
| **Quest** | 主线剧情 | 60% | 推动核心冲突 |
| **Fire** | 感情线 | 20% | 人物关系发展 |
| **Constellation** | 世界观扩展 | 20% | 背景/势力/设定 |

节奏红线：

- Quest 连续不超过 5 章
- Fire 断档不超过 10 章
- Constellation 断档不超过 15 章

## 总体架构图

```text
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code                           │
├─────────────────────────────────────────────────────────────┤
│  Skills (14个): init / plan / write / review / query /      │
│    resume / learn / dashboard / auto / audit / resolve /    │
│    macro-review / migrate / 5(弃用桩)                      │
├─────────────────────────────────────────────────────────────┤
│  Agents (22个, v13.8): Context / Writer / Polish / Data     │
│    + 16 Checkers (v13.2 Logic Fortress + v13.7 文笔沉浸感)  │
│    Consistency / Continuity / OOC / Golden-three /          │
│    Logic / Outline-compliance / Anti-detection /            │
│    Reader-pull / High-point / Pacing / Proofreading /       │
│    Emotion-curve / Editor-wisdom / Prose-impact /           │
│    Sensory-immersion / Flow-naturalness                     │
│    + Reader-simulator + Thread-lifecycle-tracker            │
├─────────────────────────────────────────────────────────────┤
│  Data Layer: state.json + index.db (30+ 表, v10 schema) │
│              vectors.db (RAG) / style_samples.db            │
└─────────────────────────────────────────────────────────────┘
```

## 双 Agent 架构

### Context Agent（读）

职责：在写作前构建“创作任务书”，提供本章上下文、约束和追读力策略。

### Data Agent（写）

职责：从正文提取实体与状态变化，更新 `state.json`、`index.db`、`vectors.db`，保证数据链闭环。

## 多维审查体系

| Checker | 检查重点 | 类型 |
|---------|---------|------|
| Consistency Checker | 设定一致性（战力/地点/时间线） | 核心 |
| Continuity Checker | 场景与叙事连贯性 | 核心 |
| OOC Checker | 人物行为是否偏离人设 | 核心 |
| Reader-pull Checker | 钩子强度、期待管理、追读力 | 条件 |
| High-point Checker | 爽点密度与质量 | 条件 |
| Pacing Checker | Strand 比例与断档 | 条件 |
| Golden-three Checker | 前三章抓取力与承诺兑现 | 条件 |
| Proofreading Checker | 修辞重复、段落结构、代称混乱、文化禁忌、文风一致性 | 条件 |
| Reader Simulator | 读者沉浸度、情绪曲线、弃读风险 | 条件 |
