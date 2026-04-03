# ink-writer Harness Architecture (v9.0)

> 本文档将 Harness Engineering 的 5 类组件映射到 ink-writer 现有架构，作为系统设计的统一参考。
> 参考来源：[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)、[Martin Fowler - Harness Engineering](https://martinfowler.com/articles/harness-engineering.html)

---

## 总体架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                     用户入口（4 个主命令）                        │
│         ink-init  │  ink-auto N  │  ink-resume  │  ink-migrate   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │   Guides     │  │   Sensors    │  │  Evaluation        │    │
│  │  (前置约束)   │  │  (事后检测)   │  │  Harness (评估)    │    │
│  │              │  │              │  │                    │    │
│  │ • 大纲即法律  │  │ • 10 Checker │  │ • reader_verdict   │    │
│  │ • 设定即物理  │  │   Agents     │  │   7 维评分         │    │
│  │ • 知识门控   │  │ • 计算型闸门  │  │ • review_metrics   │    │
│  │ • 风格锚     │  │   (Step 2C)  │  │ • 趋势分析         │    │
│  │ • 计算型闸门  │  │ • Reader     │  │ • 自动返修判定      │    │
│  │   (Step 2C)  │  │   Agent 核心  │  │                    │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘    │
│         │                 │                    │                │
│  ┌──────┴─────────────────┴────────────────────┴───────────┐   │
│  │              Execution Harness（执行框架）                │   │
│  │  ink-auto.sh 跨会话编排 + workflow_manager 状态机         │   │
│  │  检查点系统: 5/10/20 章 + 自动修复 + 断点恢复             │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────┴──────────────────────────────┐   │
│  │              Durable State（持久状态）                    │   │
│  │  state.json │ index.db (25+ 表) │ summaries │ vectors.db │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Guides / Feedforward（前置约束）

在写作开始**之前**施加的约束，降低出错概率。

| 约束 | 实现位置 | 说明 |
|------|---------|------|
| 大纲即法律 | context-agent → 执行包 | 章节大纲强制加载，writer-agent 不得偏离 |
| 设定即物理 | core-constraints.md + index.db | 能力等级 ≤ 库中记录，不可越级 |
| 发明需识别 | data-agent Step 5 | 新实体自动提取入库，防止幽灵实体 |
| 知识门控 | protagonist_knowledge_gate | 主角视角不可使用未知信息 |
| 风格锚 | style_anchor.py + style-adapter.md | 首章风格指纹约束后续章节 |
| 命名规范 | context contract v2 | 实体名/地名统一用 canonical_name |
| 写作禁区 | anti-detection-writing.md | 200+ 禁用词/句式 |
| **计算型闸门** | computational_checks.py (Step 2C) | 字数/契约/命名 确定性检查 |

### Feedforward 生效时机

```
Step 0.7 (Canary) → Step 1 (Context) → Step 2A (Writing) → Step 2C (Comp Gate)
     ↑                    ↑                   ↑                    ↑
  基础预检           加载约束包         约束内化到正文       确定性验证
```

---

## 2. Sensors / Feedback（事后检测）

在正文生成**之后**执行的检测，发现并标记问题。

### 2.1 检查分层

| 层级 | 类型 | 频率 | 成本 | 示例 |
|------|------|------|------|------|
| **计算型** | 确定性规则 | 每章 | 低（~5s） | 字数、契约完整性、命名冲突、文件规范 |
| **推断型 Core** | LLM 语义判断 | 每章 | 中（~3-5min/checker） | 设定一致、叙事连贯、OOC、追读力、读者评分 |
| **推断型 Full** | LLM 深度分析 | 关键章 | 高（~5-8min/checker） | 爽点密度、节奏平衡、文笔质量、前三章 |
| **推断型 Full+** | LLM 完整模拟 | 重要节点 | 高（~8min/checker） | AI 检测、读者完整模拟（含情绪曲线+独白） |

### 2.2 Checker 分级表

| Checker | 级别 | 触发条件 |
|---------|------|---------|
| consistency-checker | Core | 每章 |
| continuity-checker | Core | 每章 |
| ooc-checker | Core | 每章 |
| reader-pull-checker | Core | 每章 |
| **reader-simulator** | **Core（快速模式）** | **每章（v9.0 升格）** |
| high-point-checker | Full | 关键章/高潮章 |
| pacing-checker | Full | 每 5 章/卷首卷末 |
| proofreading-checker | Full | 关键章 |
| golden-three-checker | Full | 前三章 |
| anti-detection-checker | Full+ | 重要节点 |
| reader-simulator（完整模式） | Full+ | 重要节点 |

### 2.3 检查节奏（Cadence）

| 触发点 | 计算型 | 推断型 Core | 推断型 Full | 推断型 Full+ |
|--------|--------|------------|------------|-------------|
| **每章** | ✅ | ✅ | - | - |
| **每 5 章** | ✅ | ✅ | ✅ | - |
| **每 10 章** | ✅ | ✅ | ✅ | + 数据审计 |
| **每 20 章** | ✅ | ✅ | ✅ | ✅ + 宏观审查 |
| **卷末** | ✅ | ✅ | ✅ | ✅ + 整卷总结 |

---

## 3. Durable State（持久状态）

所有写作过程产生的事实和状态，以结构化方式持久化。

| 存储 | 格式 | 内容 | 更新方式 |
|------|------|------|---------|
| `state.json` | JSON | 进度、主角状态、strand_tracker、chapter_meta、harness_config | 通过 ink.py CLI（原子写入） |
| `index.db` | SQLite | 25+ 表：实体、关系、状态变化、审查指标、伏笔、场景等 | 通过 IndexManager（事务写入） |
| `summaries/` | Markdown | 每章自动生成的结构化摘要 | data-agent Step 5 |
| `vectors.db` | SQLite | RAG 向量嵌入 | data-agent Step 5 |
| `workflow_state.json` | JSON | 当前任务执行状态、断点信息 | workflow_manager.py |
| `harness_evaluations`* | SQLite 表 | reader_verdict 历史、趋势数据 | v9.0 新增 |
| `computational_gate_log`* | SQLite 表 | Step 2C 检查结果日志 | v9.0 新增 |

### 状态一致性保证

- **单写入口**：state.json 所有写入必须通过 `ink.py state process-chapter` 或 `ink.py update-state`
- **事务保护**：index.db 写入使用 SQLite 事务
- **原子写入**：state.json 使用 `atomic_write_json()`（写临时文件 → rename）
- **定期审计**：ink-audit 检测 state.json ↔ index.db 不一致

---

## 4. Execution Harness（执行框架）

控制写作流程的执行顺序、失败处理和恢复。

### 4.1 单章执行管线

```
Step 0   充分性闸门 (Sufficiency Gate)
Step 0.7 健康扫描 (Canary Health Scan)
Step 1   上下文构建 (Context Agent)
Step 2A  初稿生成 (Writer Agent)
Step 2A.5 字数验证
Step 2B  风格适配 (Style Adapter)
Step 2C  计算型闸门 (Computational Gate)     ← v9.0 新增
Step 3   多维审查 (10 Checker Agents)
Step 4   润色修复 (Polish Agent)
Step 4.5 差异验证 (Diff Validation)
Step 5   数据提取 (Data Agent)
Step 6   收尾归档 (Git + Workflow Complete)
```

### 4.2 批量编排（ink-auto）

```
ink-auto N
  │
  ├─ 预检：项目结构、大纲覆盖扫描
  │
  ├─ 主循环（串行，每章独立 CLI 进程）：
  │   ├─ 大纲检查（缺失则自动 ink-plan）
  │   ├─ 清理 workflow 残留
  │   ├─ 执行完整 ink-write 管线
  │   ├─ 多重验证（文件+字数+state+摘要）
  │   ├─ 失败重试（ink-resume，一次机会）
  │   └─ 检查点评估
  │       ├─ 每 5 章：ink-review Core + 自动修复
  │       ├─ 每 10 章：+ ink-audit quick + 修复
  │       └─ 每 20 章：+ ink-audit standard + ink-macro-review Tier2 + 修复
  │
  └─ 完成报告（增强版，含质量趋势+追读力+伏笔债务）
```

### 4.3 恢复机制

| 场景 | 处理 |
|------|------|
| 章节写作中断 | workflow_state.json 记录断点 → ink-resume 从断点恢复 |
| 审查/审计失败 | 非阻断，记录警告继续写作 |
| 大纲缺失 | 自动触发 ink-plan，同卷只尝试一次 |
| 章节验证失败 | ink-resume 重试一次，仍失败则中止 |

---

## 5. Evaluation Harness（评估框架）

对写作结果进行结构化评分，驱动自动决策。

### 5.1 Reader Verdict（读者裁决）

每章由 reader-simulator 产出 7 维评分：

| 维度 | 范围 | 说明 |
|------|------|------|
| hook_strength | 0-10 | 开头抓取力 |
| curiosity_continuation | 0-10 | 中段好奇心维持 |
| emotional_reward | 0-10 | 情绪回报感 |
| protagonist_pull | 0-10 | 主角吸引力 |
| cliffhanger_drive | 0-10 | 章末追更驱动 |
| filler_risk | 0-10 | 注水风险（反向） |
| repetition_risk | 0-10 | 套路重复风险（反向） |

**总分** = (前 5 项之和) - (后 2 项之和)，范围 -20 ~ 50

| 总分 | 判定 | 动作 |
|------|------|------|
| ≥ 32 | pass | 正常流转到 Step 4 |
| 25-31 | enhance | Step 4 加入"追读力增强"修复 |
| < 25 | rewrite | 退回 Step 2A，附带问题清单 |

### 5.2 Review Metrics（审查指标）

每章审查产出存入 `index.db.review_metrics`：
- `overall_score` (0-100)
- `dimension_scores` (各 checker 分数 JSON)
- `severity_counts` (critical/high/medium/low 计数)
- `reader_verdict` (7 维评分 JSON)

### 5.3 趋势分析

ink-auto 完成后输出：
- 审查分均值与走势
- 读者评分趋势（↑/→/↓）
- 伏笔债务变化
- 套路重复预警

---

## Harness 演进原则

> 本项目不承诺"零修改上线"，但承诺采用 harness-first 架构，使系统具备可验证、可回归、可恢复、可演进能力；所有重复出现的问题，优先通过新增 guide、sensor、grader 或状态约束解决，而不是依赖人工长期盯防。

1. **错误沉淀为规则**：同类错误出现 2 次 → 新增计算型检查项或 checker 规则
2. **Guide 优先于 Sensor**：能在写之前防住的，不留到写完再检查
3. **评估驱动修复**：不靠感觉判断好不好，靠结构化评分触发自动动作
4. **状态即真相**：一切事实以 index.db + state.json 为准，不靠模型记忆
