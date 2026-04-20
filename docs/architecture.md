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
│  Agents (23个, v22.0): Context / Writer / Polish / Data     │
│    + 17 Checkers (v13.2 Logic + v13.7 文笔 + v22 直白)      │
│    Consistency / Continuity / OOC / Golden-three /          │
│    Logic / Outline-compliance / Anti-detection /            │
│    Reader-pull / High-point / Pacing / Proofreading /       │
│    Emotion-curve / Editor-wisdom / Prose-impact /           │
│    Sensory-immersion / Flow-naturalness / Directness        │
│    + Reader-simulator + Thread-lifecycle-tracker            │
├─────────────────────────────────────────────────────────────┤
│  Data Layer: state.json + index.db (30+ 表, v10 schema) │
│              vectors.db (RAG) / style_samples.db            │
└─────────────────────────────────────────────────────────────┘
```

## 双 Agent 架构

### Context Agent（读）

职责：在写作前构建“创作任务书”，提供本章上下文、约束和追读力策略。

章节上下文硬注入（US-002）：context pack 的 `core` 段新增 `recent_full_texts`
字段，默认装填最近 3 章完整正文（`context_recent_full_texts_window=3`）；
`recent_summaries` 语义同步变更为 `[n-10, n-4]` 共 7 章摘要，与全文范围严格正交；
`meta.injection_policy` 暴露 `{full_text_window, summary_window, summary_range,
hard_inject}` 元数据供下游 agent 校验。详见
`ink-writer/references/context-contract-v2.md` Phase J。

Token 预算 protected 机制（US-006）：assemble_context 将 `recent_full_texts`
抬升为独立 top-level section，加入 `context_protected_sections=("recent_full_texts",)`
白名单永不参与字符级裁剪。双档预算：`context_soft_token_limit=60000`（warn 级）
超额按 `context_soft_cap_trim_order=(alerts, preferences, memory, story_skeleton)`
逐段裁剪；`context_hard_token_limit=180000`（降级级）超额按
`context_hard_cap_trim_order=(global, scene, recent_summaries, recent_full_texts)`
降级，其中 protected 字段在 `_trim_section` 入口 short-circuit 跳过。每次 build
日志输出 `total / soft / hard / token_breakdown`，`meta` 暴露同构字段 +
`trim_stages_applied`（形如 `["soft:alerts", "hard:global"]`）便于运维观测。

Writer-Agent 首要参考（US-004）：`ink-writer/agents/writer-agent.md` 规定
前三章全文为 PRIMARY REFERENCE，优先级高于本章大纲；起草前必须先产出
Pre-Draft Checklist（位置/道具状态/未兑现伏笔/对白关键措辞四项，XML 标记
`<pre-draft-checklist chapter="N">` 包裹），落盘至
`.ink/tmp/pre_draft_checklist_ch{NNNN}.md`，由 polish-agent 在成稿前剥离。
N=1/2/3 与文件缺失提供兜底模板。

Continuity-Checker 证据回填（US-005）：`continuity-checker.md` 将审查结构
升级为五层（前四层保持不变 + 第五层 "前三章全文回溯校验"），第五层 issue 强制
附带 `evidence: {source_chapter ∈ {N-1, N-2, N-3}, excerpt: 30~200 字原文}`。
`evidence_source` 字段传递降级状态：`ok` / `degraded:no_full_texts` /
`n1_no_prior`。与 review_metrics / character_evolution_ledger / active_threads
等既有指标 additive 共存，不 bump `context_contract_version`。

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
