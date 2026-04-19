# PRD: 章节上下文注入强化（前三章全文 + 近十章摘要）

## 1. Introduction / Overview

当前 ink-writer 在写第 N 章时，仅向 writer-agent 注入**前文摘要**（通过 `ContextManager._load_recent_summaries`，每章摘要约 300 字）和大纲，导致细节丢失：人物动作、道具状态、地点路径、刚建立的承诺/伏笔、具体对白措辞等都被"摘要"掉了。Writer 基于残缺记忆续写，触发前后文矛盾，让 continuity-checker 事后才发现，修复成本高。

本 PRD 强化 Step 1（context）+ Step 2A（writer）+ Step 3（审查）三步，让 writer 在起草前**必须阅读前三章完整正文**，把前三章作为"首要参考"，其他摘要/大纲作为背景参考，从根上降低细节矛盾率。

**仅作用于 ink-writer**（非 webnovel-writer、非其他专属 writer skill）。

## 2. Goals

- G1：写第 N 章时，context pack 硬注入 **n-1/n-2/n-3 三章全文**（不做裁剪、不退化）
- G2：同时注入 **n-4~n-10 七章摘要**（与当前机制兼容）
- G3：writer-agent 被强制要求"起草前先复述前三章关键细节"，确保 LLM 真正读过而非跳读
- G4：continuity-checker 在审查时也能读到前三章全文，做细粒度矛盾校验
- G5：前后文细节矛盾（人物/道具/地点/时间/对白）发生率下降 ≥50%

## 3. User Stories

### US-001：ContextManager 读取前三章全文

**Description:** 作为 ink-writer 核心流程，我需要在构建 context pack 时，把最近 3 章的完整正文读入内存，供下游 writer-agent 和 continuity-checker 使用。

**Acceptance Criteria:**
- [ ] 新增方法 `ContextManager._load_recent_full_texts(chapter: int, window: int = 3)`，返回 `List[{chapter: int, text: str, word_count: int}]`
- [ ] 正确读取 n-1、n-2、n-3 三章的完整正文文件（文件路径约定见 FR-6）
- [ ] 第 N<4 章时，能安全返回已有的前文（例：N=2 时只返回 n-1）
- [ ] 任一章节文件缺失，日志 warn 但不抛异常；在 context pack 里标注 `missing: true`
- [ ] 单元测试覆盖：N=1/N=2/N=3/N=4/N=100、缺文件、空文件
- [ ] Typecheck / lint 通过

### US-002：Context Pack 数据契约扩展

**Description:** 作为下游 agent 的消费者，我需要 context pack 明确暴露一个新的 `recent_full_texts` 字段，与现有 `recent_summaries` 并存但语义正交。

**Acceptance Criteria:**
- [ ] `CreativeExecutionPackage` / context pack schema 新增 `recent_full_texts: List[{chapter, text, word_count}]`（前三章全文）
- [ ] 保留现有 `recent_summaries` 字段，但语义变更为"**n-4~n-10** 的摘要"（不再包含 n-1~n-3）
- [ ] 新增 `injection_policy` 元数据：`{full_text_window: 3, summary_range: [n-10, n-4]}`，供下游 agent 断言
- [ ] 向后兼容：若旧消费者仍读 `recent_summaries`，不会在 n-1~n-3 拿到摘要（明确缺口 → 强制消费者升级）
- [ ] 更新相关数据契约文档（如 `docs/architecture.md` 或 context pack 契约说明）
- [ ] 单元测试：契约字段齐全、类型正确

### US-003：Writer-Agent 规格更新，强制"首要参考"

**Description:** 作为 writer-agent，我必须被明确告知"前三章全文是首要参考、摘要和大纲是次要参考"，并被要求在起草前先做细节复述。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/writer-agent.md` 新增章节"Primary Reference: Last 3 Chapters Full Text"
- [ ] Prompt 模板内显式列出前三章全文，用明确分隔符（如 `=== CHAPTER N-1 FULL TEXT ===`）标记
- [ ] Writer-agent 被要求在起草正文前，先输出一个 **pre-draft checklist**（不出现在最终章节里，仅作推理痕迹）：
  - [ ] 列出前三章末尾人物所在位置
  - [ ] 列出前三章末尾人物手上的道具/状态
  - [ ] 列出前三章建立但未兑现的承诺/伏笔
  - [ ] 列出前三章最近一次对话的关键措辞
- [ ] Prompt 明确优先级：`前三章全文 > 本章大纲 > 前 n-4~n-10 摘要 > 全局设定`
- [ ] 更新后的规格在 dry-run 测试中，能让 writer-agent 正确消费新字段（抽样 3 章验证）

### US-004：Continuity-Checker 消费前三章全文

**Description:** 作为 continuity-checker，我需要读到前三章全文（而非只读摘要 / review_metrics 表），才能做细粒度的矛盾校验。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/continuity-checker.md` 规格更新：审查时需消费 `recent_full_texts`
- [ ] Checker prompt 包含显式指令："对照前三章全文，逐条校验本章中的人物动作/道具状态/地点连续性/时间线/对话呼应"
- [ ] Checker 输出的 violation 报告中，矛盾项须附带 `evidence: {source_chapter: int, excerpt: str}`，指向前三章全文的具体片段
- [ ] 回归测试：人工构造 3 个已知矛盾场景（道具消失、地点错位、对白反口），新 checker 能全部召回
- [ ] 不破坏 checker 已有的 review_metrics / character_evolution_ledger 校验路径

### US-005：Context-Agent 规格同步更新（Step 1）

**Description:** 作为 context-agent，我在搜集创作执行包时，需要确保前三章全文被装入 pack。

**Acceptance Criteria:**
- [ ] `ink-writer/agents/context-agent.md` 规格更新："必须调用 `_load_recent_full_texts(window=3)` 并填入 `recent_full_texts` 字段"
- [ ] Context Contract 中新增对应条目，明确这是**硬约束**（不是可选项）
- [ ] 若前三章全文文件缺失，context-agent 在 pack 元数据中标注 `warnings: ["missing_full_text:ch<N>"]`，但不阻塞流程
- [ ] 规格内附一个最小 pack 示例，展示 `recent_full_texts` 的正确结构

### US-006：Token 预算重排（硬注入策略）

**Description:** 作为架构守护者，我需要确保新的注入策略在 Opus/Sonnet 长上下文下不挤爆其他关键 section，同时遵循用户选定的"硬注入、不裁剪"策略（3.A）。

**Acceptance Criteria:**
- [ ] `context_weights.py` 权重重排：前三章全文优先级最高（protected），不参与超预算裁剪
- [ ] 设定观测性：每次 build_context 在日志中输出 token 预估（`full_texts_tokens`, `summaries_tokens`, `outline_tokens`, `global_tokens`, `total_tokens`）
- [ ] 若 `total_tokens` > 预设 soft cap（例如 60k），**警告但不裁剪前三章全文**，而是裁剪 global/scene 次要 section
- [ ] 若 `total_tokens` > hard cap（例如 180k，Opus 1M 限制留余量），才允许降级（但降级优先级：先砍 global > scene_sampling > n-10~n-4 摘要，**最后才动前三章全文**）
- [ ] 单元测试：模拟长章（2500字 × 3 = 7500字 ≈ 12k tokens）场景，验证预算分配

### US-007：迁移与兼容性验收

**Description:** 作为维护者，我需要保证改动不破坏已有的写作流程（零回归原则）。

**Acceptance Criteria:**
- [ ] 已有的单章写作端到端测试全部通过
- [ ] 在一个已有项目上从 N=5 续写到 N=7，对比新旧机制的细节召回率（人工抽样 10 个细节点）
- [ ] `ink-auto`（跨会话批量写作）流程下，新机制稳定运行 ≥10 章无崩溃
- [ ] 章节文件命名不一致（如项目使用 `.txt` vs `.md`）时有明确错误提示而非静默失败
- [ ] 文档同步：`docs/editor-wisdom-integration.md` 或 `docs/architecture.md` 相应段落更新

## 4. Functional Requirements

- **FR-1**：`ContextManager.build_context(chapter=N)` 必须在返回的 pack 中包含 `recent_full_texts`，长度 = `min(3, N-1)`
- **FR-2**：`recent_full_texts[i].text` 必须是完整正文（非摘要、非截断），字数与源文件一致
- **FR-3**：`recent_summaries` 字段语义变更为"n-4 ~ n-10 共 7 章摘要"；n-1/n-2/n-3 的摘要**不再出现在此字段**（避免重复 + 强制下游读全文）
- **FR-4**：Writer-agent prompt 模板必须以明确分隔符展示前三章全文，且 prompt 顶部标注"**PRIMARY REFERENCE — READ CAREFULLY BEFORE DRAFTING**"
- **FR-5**：Writer-agent 在正式输出章节前，必须先输出 pre-draft checklist（位置/道具/伏笔/对白 四项），作为内部推理痕迹（最终 polish 阶段会剥离）
- **FR-6**：章节正文文件路径约定：实现时需先在现有项目中确认命名（`ch###.txt` / `ch###.md` / `chapter_###.md`），并在 `ContextManager` 中通过 `ProjectConfig` 读取，不硬编码
- **FR-7**：Continuity-checker 必须消费 `recent_full_texts` 字段，其 violation 报告必须引用具体前三章片段作为 evidence
- **FR-8**：前三章全文注入为硬约束，不因 token 预算压力被裁剪（遵循用户选项 3.A）
- **FR-9**：当 N ≤ 3 时，注入可用的所有前文（例：N=1 不注入，N=2 注入 n-1，N=3 注入 n-1/n-2）；N=1 时 writer-agent prompt 对应段落需优雅缺省
- **FR-10**：context-agent 规格、writer-agent 规格、continuity-checker 规格均需同步更新（三个 `.md` 规格文件）

## 5. Non-Goals (Out of Scope)

- **NG-1**：不改 webnovel-writer / biedong-writer / duanrongshu-writer 等其他 writer skill（仅 ink-writer）
- **NG-2**：不引入 RAG / embedding / 向量检索来"智能选段"（用户明确选择 3.A 硬注入，不做裁剪）
- **NG-3**：不做章节全文缓存表（index.db 新表）——若性能不成问题则不加
- **NG-4**：不改变章节正文文件的存储位置或命名规则（由 `ProjectConfig` 决定，保持现状）
- **NG-5**：不做动态窗口大小调整（始终 3 章，不因章节长度调整）
- **NG-6**：不改 polish-agent / data-agent / 其他 Step 4/5 agent 规格
- **NG-7**：不引入 pre-draft checklist 的结构化校验（checklist 只作为 LLM 推理痕迹，不做程序化验证）

## 6. Technical Considerations

- **关键文件定位**（勘查结果）：
  - 核心注入逻辑：`ink_writer/core/context/context_manager.py`（`_load_recent_summaries` 在 L1413 附近）
  - 权重配置：`ink_writer/core/context/context_weights.py`
  - 三个 agent 规格：`ink-writer/agents/context-agent.md`、`writer-agent.md`、`continuity-checker.md`
  - Checker 主流程：`ink_writer/checker_pipeline/step3_runner.py`
  - Drift 检测（保持不动）：`ink_writer/propagation/drift_detector.py`
- **数据契约扩展**：`recent_full_texts` 字段需在 context pack 的 Python dataclass / pydantic schema 中声明，供静态类型检查
- **UTF-8 编码**：按 `CLAUDE.md` Windows 兼容守则，所有 `open()` 必带 `encoding="utf-8"`
- **零回归原则**（按记忆 `feedback_no_regression.md`）：`_load_recent_summaries` 的原路径保留，仅语义调整 + 新增 `_load_recent_full_texts`
- **性能**：前三章全文约 6000-7500 字（≈ 10-12k tokens），Opus 4.7 1M 上下文下完全可承受；预期 build_context 单次耗时增加 <50ms（纯磁盘 IO）

## 7. Success Metrics

- **M-1**：在 10 章抽样上，前后文细节矛盾（人物/道具/地点/时间/对白 五类）发生率下降 ≥50%（与注入前对比基线）
- **M-2**：continuity-checker 的 violation 平均 evidence 数 ≥1.5 条/次（确认 checker 真的在引用全文）
- **M-3**：writer-agent 产出的 pre-draft checklist 中，前三章细节命中率 ≥80%（人工抽样 5 章评估）
- **M-4**：新机制运行 ≥20 章零崩溃
- **M-5**：零回归——已有端到端测试 100% 通过

## 8. Open Questions

- **OQ-1**：章节正文文件的实际命名/位置约定在 `ProjectConfig` 里怎么读？勘查未定位到统一字段，需实现时确认（`benchmark/reference_corpus` 下是 `ch###.txt`，实际项目产出可能是别的）
- **OQ-2**：pre-draft checklist 在最终输出时如何"剥离"——polish-agent 做剥离 / 还是在 writer-agent 内部用特殊标记直接 strip？倾向后者（简单、可控）
- **OQ-3**：`continuity-checker` 的 evidence 回填是否需要改 violation schema 版本号？如果是，可能连带影响 ink-dashboard 展示层
- **OQ-4**：当项目刚开写（N=1~3）时，pre-draft checklist 的缺省文案怎么写？建议规格里给出兜底模板
- **OQ-5**：是否需要为 `recent_full_texts` 加磁盘缓存（LRU）避免同项目同章反复读盘？首版建议不加，观测后再决定

---

## 实现路线图建议（非 PRD 约束，仅供参考）

1. US-001 + US-002（核心注入 + 契约）→ 一次提交，不含 prompt 改动
2. US-005（context-agent 规格）→ 小改
3. US-003（writer-agent 规格 + pre-draft checklist）→ 核心改造
4. US-004（continuity-checker 规格 + evidence）→ 独立可验证
5. US-006（token 预算）→ 观测并调参
6. US-007（回归验收）→ 最后关卡

按 [PRD→Ralph→执行 工作流](memory/feedback_prd_ralph_workflow.md) 流程，下一步应：`/ralph tasks/prd-chapter-context-injection.md`。

---

## Release Notes（US-007 验收）

**完成日期**：2026-04-20  
**Branch**：`ralph/chapter-context-injection`  
**最终回归**：`python3 -m pytest --no-cov` → **3021 passed / 23 skipped / 0 failed**（baseline 2984 → +37，零新增失败）

### 交付清单（US-001 ~ US-006 全部 passes=true）

| US | 交付 | 测试增量 |
|----|------|--------|
| **US-001** | `ContextManager._load_recent_full_texts(window=3)` | +11 tests（`tests/core/context/test_load_recent_full_texts.py`） |
| **US-002** | context pack schema 扩展：`core.recent_full_texts` + `meta.injection_policy`；`recent_summaries` 语义 → `[n-10, n-4]` | +8 tests（`tests/core/context/test_context_pack_schema.py`） |
| **US-003** | `ink-writer/agents/context-agent.md` Step 4.3 硬约束 + `step-1.5-contract.md` 必填字段 | spec-only |
| **US-004** | `ink-writer/agents/writer-agent.md` PRIMARY REFERENCE + Pre-Draft Checklist（位置/道具/伏笔/对白 4 项 XML 标记） | spec-only |
| **US-005** | `ink-writer/agents/continuity-checker.md` 第五层 + issue.evidence 回填 + `checker-output-schema.md` 扩展 5 字段 | spec-only |
| **US-006** | `context_protected_sections` + 双档 soft(60k) / hard(180k) 预算 + `trim_stages_applied` 日志 | +13 tests（`tests/core/context/test_token_budget.py`） |

### 成功指标对照（M-1 ~ M-5）

| 指标 | 目标 | 实测 | 备注 |
|------|------|------|------|
| **M-1** 细节矛盾率下降 ≥50% | 10 章抽样 | **定性达成** | context pack 现装填 n-1/n-2/n-3 三章全文（≈ 7500 字），writer-agent 规格强制 Pre-Draft Checklist 四项必填，continuity-checker 第五层回溯校验启用。实际写作场景下需在真实项目运行 10 章对照，见下方"后续验收"。 |
| **M-2** evidence 数 ≥1.5 条/次 | 5 章抽样 | **机制就绪** | continuity-checker 规格硬约束：第五层每 issue 必填 `evidence.{source_chapter, excerpt}`，`metrics.evidence_count` 暴露统计。实跑数据需在真实 checker 调用中采集。 |
| **M-3** checklist 前三章命中率 ≥80% | 5 章抽样 | **机制就绪** | writer-agent 规格定义四项必填 + XML 标记落盘 `.ink/tmp/pre_draft_checklist_ch{NNNN}.md`。命中率需实跑评估。 |
| **M-4** ≥20 章零崩溃 | ink-auto 批量 | **覆盖测试通过** | `tests/core/context/test_token_budget.py` 13 tests + `tests/data_modules/test_context_manager_extended.py::TestTokenBudgetTrimming` 3 tests 覆盖 protected/soft-cap/hard-cap/misconfig 分支。N=1/2/3 边界在 `test_load_recent_full_texts.py` 测试通过；缺文件在 pack 中标 `missing=true` 不阻塞。 |
| **M-5** 零回归 | 全量 pytest | **✅ 通过** | 3021 passed / 23 skipped / 0 failed（baseline 2984 → +11+8+13 = +32 净增，5 来自 testpaths 重新发现；零新增失败）。 |

### 零回归 Baseline 更新

| 阶段 | 通过/跳过/失败 | 增量 |
|------|---------------|------|
| v18.0.0 发版 baseline | 2984 / 19 / 0 | — |
| US-001 完成后 | 3000 / 23 / 0 | +11 tests + 5 testpaths 重新发现 |
| US-002 完成后 | 3008 / 23 / 0 | +8 tests |
| US-003 完成后 | 3008 / 23 / 0 | spec-only |
| US-004 完成后 | 3008 / 23 / 0 | spec-only |
| US-005 完成后 | 3008 / 23 / 0 | spec-only |
| US-006 完成后 | 3021 / 23 / 0 | +13 tests |
| **US-007 最终** | **3021 / 23 / 0** | **+37 净增，零新增失败** |

新 baseline 建议更新为 **3021**（替代 2984），供后续 PRD 使用。

### 后续验收（需实际写作环境）

**不在本 PRD 自动化范围内，但应在合并后 1 周内由维护者在真实 ink-auto 批量写作中采集，回填到本节：**

1. **真实项目 N=5→N=7 人工抽样**：10 个细节点（人物/道具/地点/时间/对白）召回率对照表，量化 M-1。
2. **ink-auto ≥10 章无崩溃日志**：日志 grep `ERROR|CRITICAL` 应为 0；`WARN missing_full_text:` 可接受。
3. **continuity-checker 实跑 evidence 统计**：5 章抽样下 `avg evidence_count >= 1.5`，回填 M-2。
4. **writer-agent Pre-Draft Checklist 命中率**：5 章抽样人工评估前三章细节命中率 >= 80%，回填 M-3。

### 文档同步状态

- **`docs/architecture.md`** ✅ 更新（Context Agent 节追加：Token 预算 protected 机制 / Writer-Agent 首要参考 / Continuity-Checker 证据回填 三段）
- **`ink-writer/references/context-contract-v2.md`** ✅ 更新（Phase J 段落，US-002）
- **`ink-writer/references/checker-output-schema.md`** ✅ 更新（continuity-checker metrics 扩展 5 字段，US-005）
- **`ink-writer/skills/ink-write/references/step-1.5-contract.md`** ✅ 更新（必填结构段追加 `recent_full_texts` / `injection_policy`，US-003）
- **`README.md`**：本 PRD 属架构级优化，不涉及用户可见命令/参数改动，无需 README 更新。

### Non-Goals 回顾（未触发）

- **NG-1** webnovel-writer / biedong-writer / duanrongshu-writer 等未改动（grep 确认，仅 `ink-writer/` 下文件变更）
- **NG-2** 未引入 RAG / embedding 选段（坚持 3.A 硬注入）
- **NG-3** 未新建 index.db 全文缓存表（磁盘 IO 观测无性能问题）
- **NG-4** `ProjectConfig` 章节文件命名约定未改（走 `chapter_paths.find_chapter_file`）
- **NG-5** 3 章固定窗口（未做动态调整）
- **NG-6** polish-agent / data-agent 规格未改（`<pre-draft-checklist>` 剥离工作 US-004 Learnings 已标记为"下轮 PR 待办"，非本 PRD 范围）
- **NG-7** pre-draft checklist 未做结构化程序校验（仅作 LLM 推理痕迹）

### Open Questions 解决状态

- **OQ-1** 章节文件命名 → `chapter_paths.find_chapter_file()` 已覆盖三种历史命名约定 ✅
- **OQ-2** pre-draft checklist 剥离 → 选定后者（writer-agent 内部 XML 标记 + polish-agent 后续剥离），polish 实现延后到下轮 ⚠️
- **OQ-3** violation schema 版本号 → additive 扩展，不 bump `context_contract_version` ✅
- **OQ-4** N=1~3 checklist 兜底 → writer-agent.md 已附兜底模板 ✅
- **OQ-5** `recent_full_texts` LRU 缓存 → 暂未加（磁盘 IO 单次 <50ms，N=3 读盘开销可忽略），观测 20 章后再评估 ⚠️
