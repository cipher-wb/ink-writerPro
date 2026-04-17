# PRD: Ink Writer v13.8.0 深度架构健康审计（Step 1 · 诊断报告）

## Introduction / Overview

Ink Writer Pro 经过 v8 → v13.8 共 15+ 次大改造，功能不断叠加：从 14 Agent 全规范化 (v8) 到 Harness-First (v9)、Style RAG (v11)、编辑星河 (v12)、Logic Fortress (v13.2)、Narrative Coherence (v13.5)、爽点密集化 (v13.6)、文笔沉浸感 (v13.7)、创意生成架构 (v13.8)。

用户（项目作者）担心：
1. **架构可能已"叠屋架"**：新功能是否真落地？旧模块是否还在用？是否有死代码 / 死数据 / 死规格？
2. **当前水平未知**：缺乏一份客观、系统的诊断，不清楚项目实际处于"商业可用" / "原型" / "叠积木" 哪个阶段。

本 PRD 定义一次**只诊断、不修复**的深度架构健康审计。产出一份分级诊断报告（`docs/engineering-review-report-v5.md`），作为后续修复 PRD 的输入。

> **关键约束**：本次审计**不修改任何源码**。所有写操作仅限于产出报告和扫描工具脚本（位于 `scripts/audit/`，可复用可保留）。

---

## Goals

- **G1** 识别"叠屋架"痕迹：相同功能的不同实现、已废弃但未清理的模块、被新版本覆盖的旧规格
- **G2** 追踪主写作链路（context → writer → review → fix → polish）的真实数据流，验证每个节点衔接是否正确
- **G3** 审查三套 RAG 系统（editor_wisdom / style_rag / semantic_recall）是否真在运行时发挥作用、是否存在冲突
- **G4** 审查创意生成系统（ink-init --quick 三层体系 + 种子库 + 扰动引擎）是否真的驱动方案产出
- **G5** 工程质量体检：测试覆盖、错误处理、配置管理、日志、依赖、文档一致性
- **G6** 扫描未使用资源：`references/`、`data/`、`archive/`、`docs/archive/` 下哪些文件从未被代码或 agent 规格加载
- **G7** 对照 README 每项承诺（8 层反 AI 检测、288 条编辑规则、跨章语义检索、过起点审核等）逐条溯源到代码
- **G8** 输出分级诊断报告：每个发现带文件路径、行号（若适用）、证据、严重度、推荐优先级

---

## User Stories

### US-001: 项目全景快照与版本演进考古
**Description:** As 审计员, I want 梳理 v8 → v13.8 的功能迭代在代码里留下的实际痕迹, so that 识别"功能叠加但旧实现未清理"的架构问题。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/01-version-archaeology.md`，列出每个主版本（v8/v9/v11/v12/v13.0/v13.2/v13.5/v13.6/v13.7/v13.8）的核心改造 vs 代码里仍可见的痕迹
- [ ] 识别至少 3 类潜在"叠屋架"：同一能力的多个实现、相同概念的多处 schema、被新 agent 覆盖的旧 agent 规格
- [ ] 目录结构分析：`ink_writer/`（Python 包）、`ink-writer/`（plugin 配置）、根级文件的职责划分是否清晰，是否存在误放
- [ ] 产出目录图（文字版树状图）并标注每个顶层目录的"当前用途 / 疑似废弃 / 需确认"

### US-002: 主写作链路端到端数据流追踪
**Description:** As 审计员, I want 沿 `/ink-auto` 命令追踪从入口到产出章节的完整执行链路, so that 验证每个 agent/step 的衔接是否正确、是否有"规格定义了但运行时被跳过"的节点。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/02-writing-pipeline-trace.md`
- [ ] 绘制主流程 DAG（Mermaid 或 ASCII）：`ink-auto` → `ink-write` → `context-agent` → `writer-agent` → `checker_pipeline` (14 checker) → `ink-fix` → `polish-agent` → `data-agent` → `ink-audit`
- [ ] 对每条边标注：**传递什么数据**（字段名级别）、**在哪段代码**（文件:行号）、**是否存在**
- [ ] 识别"断边"：上游产出但下游未消费、下游需要但上游未提供的字段
- [ ] 对照 `references/pipeline-dag.md` 验证实际链路与规格是否一致

### US-003: 14+ Checker 职责矩阵与去重分析
**Description:** As 审计员, I want 梳理所有 checker agent 的检测维度, so that 识别重复检测、遗漏检测、以及硬门禁是否真能阻断。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/03-checker-matrix.md`
- [ ] 建立矩阵：行 = 20+ checker（anti-detection / consistency / continuity / editor-wisdom / emotion-curve / flow-naturalness / foreshadow / golden-three / high-point / logic / ooc / outline-compliance / pacing / plotline / proofreading / prose-impact / reader-pull / sensory-immersion 等），列 = 检测维度（句式/情节/角色/文笔/结构/反AI/伏笔/节奏/爽点/情绪）
- [ ] 标注每个 checker 的：输入契约、输出 schema、硬门禁条件、被哪个上游调用、产出如何流向 polish
- [ ] 识别重复检测（两个 checker 看同一维度）和孤儿 checker（规格存在但主流程未调用）
- [ ] 验证"硬阻断门禁"实际实现：是一票否决还是评分累计？代码在哪？

### US-004: RAG 三系统深度审查 ★
**Description:** As 审计员, I want 验证 editor_wisdom / style_rag / semantic_recall 三套 RAG 是否真的在运行时被召回并影响产出, so that 排除"建了但没用"的假 RAG。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/04-rag-audit.md`
- [ ] 对每个 RAG 子系统输出：索引文件位置 / 大小 / 最后更新时间、召回代码路径、注入 prompt 的位置、回退机制（Embedding→BM25）
- [ ] editor_wisdom：288 条规则 / 364 条原子规则是否在 FAISS 索引里、运行时能否召回、召回结果是否真的出现在 writer/checker 的 prompt 里
- [ ] style_rag：3295 片段是否建立索引、writer-agent 是否消费
- [ ] semantic_recall：跨章检索代码路径、`incremental_extract` 模块的协作
- [ ] 三套 RAG 的**冲突检测**：是否出现"editor_wisdom 要求 A，style_rag 检索到 B"的潜在冲突、是否有统一的优先级协议
- [ ] API Key 缺失 / 模型加载失败时的降级路径验证
- [ ] **[运行时实测]** 跑一次 `/ink-write`（单章）并开启日志，在运行时抓取三套 RAG 的实际召回内容（query / top-k 命中 / 注入 prompt 的片段），写入 `docs/audit/04-rag-live-trace.md`。若 API Key 不可用则仅跑 BM25 fallback 路径

### US-005: 创意生成系统审查（ink-init --quick）
**Description:** As 审计员, I want 验证 v13.8 宣称的三层创意体系（元规则库 M01-M10 + 种子库 schema + 扰动引擎）是否真的驱动方案生成, so that 判断新功能是"硬编码 prompt" 还是"结构化系统"。

> **背景注释**：最近 10 个 commit 的 **Phase-Seed-1 Batch 1-10**（共 ~1000 条种子）即本 US 中种子库 v2.0 的构建阶段，作为普通模块审查即可。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/05-creativity-audit.md`
- [ ] 定位元规则库 M01-M10 的具体文件、数据结构、加载代码
- [ ] 定位种子库（最近 commit 显示 Batch 1-10 共 ~1000 条种子）的存储格式、索引方式、调用路径
- [ ] 扰动引擎：代码在哪？输入输出？是否真的被 `/ink-init --quick` 调用？
- [ ] 金手指三重硬约束（非战力维度 / 代价可视化 / 一句话爆点）的检测代码定位
- [ ] 4 档激进度 / 3 档语言风格的分档逻辑实现
- [ ] 江湖绰号库 110 条 / 书名模板 170 条 / 陈词黑名单是否被实际消费
- [ ] 起点番茄榜单"90 天缓存"的抓取代码、缓存路径、失效处理

### US-006: 数据层与记忆系统审查
**Description:** As 审计员, I want 审查 30+ SQLite 表 + state.json + JSON 混用的数据架构, so that 识别 schema 漂移、冗余字段、未使用的表。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/06-data-layer-audit.md`
- [ ] 列出所有 SQLite 表（从 schemas/ 和 migration 文件提取）+ 实际 insert 来源 + 实际 select 用户
- [ ] 识别"定义了但从未写入" / "写入了但从未读取"的表
- [ ] state.json 与 index.db 的字段对齐情况（对照 `docs/state-sqlite-migration-guide.md`）
- [ ] 伏笔生命周期（foreshadow 模块）、明暗线追踪（plotline 模块）的表设计与代码对齐
- [ ] 实体消歧机制（`ink-resolve`）的数据流
- [ ] 增量抽取（`incremental_extract`）的增量边界定义

### US-007: 工程质量全面体检
**Description:** As 审计员, I want 从测试、错误处理、配置、日志、依赖、文档多维度评估工程健康度, so that 定位生产级薄弱点。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/07-engineering-quality.md`
- [ ] **测试**：`tests/` 覆盖率统计（按模块）、是否有 integration test、是否 mock 过度、pytest 能否无错跑完
- [ ] **错误处理**：识别 "except: pass" / "except Exception:" 过宽捕获、关键路径是否有超时与重试
- [ ] **配置**：`.env` / `config/` / `settings` / `hooks` 的配置来源是否统一、优先级是否清晰
- [ ] **日志**：是否使用 logging、日志级别是否合理、是否存在 print 调试残留
- [ ] **依赖**：`requirements.txt` 与 `pyproject.toml` 是否一致、是否有未使用的依赖、版本是否固定
- [ ] **文档**：docs/ 下文档与实际代码的对齐度（抽样 5 份关键文档验证）
- [ ] **CLI/入口**：各 `/ink-*` 命令是否都有入口脚本、入口是否稳定
- [ ] 识别 Top 5 工程风险点

### US-008: 死代码与未使用资源扫描 ★
**Description:** As 审计员, I want 系统化扫描所有 `references/`、`data/`、`archive/`、agent 规格、Python 模块, so that 产出可直接执行的"可删除清单"。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/08-unused-resources.md` + 扫描脚本 `scripts/audit/scan_unused.py`
- [ ] **Python 死代码**：扫描 `ink_writer/` 下所有 .py 文件，识别从未被 import 的模块、未被调用的函数（可容忍少量 false positive）
- [ ] **references/ 文件扫描**：对每个文件，在整个代码库和 agent 规格（.md）中搜索其路径/文件名，标注"被引用 / 未被引用 / 仅文档引用"
- [ ] **data/ 文件扫描**：同上，特别关注 `hook_patterns.json`、`cultural_lexicon`、`market-trends`、`naming`、`editor-wisdom` 数据
- [ ] **agent 规格扫描**：`ink-writer/agents/*.md` 每个 agent 是否被某 skill 或 checker_pipeline 调用
- [ ] **archive/ 和 docs/archive/**：**用户已确认可删除**，直接列入 🗑 清单，不深读内容，仅做路径清点 + 大小统计
- [ ] **旧 engineering-review-report v2/v3/v4**：**用户已确认可删除**，直接列入 🗑 清单
- [ ] 产出 3 档建议清单：🗑 可立即删除 / ⚠ 需确认 / 📦 归档

### US-009: 逻辑自洽性与版本承诺兑现审计
**Description:** As 审计员, I want 逐条验证 README 的承诺与 version history 里每版"大改造"是否在代码里真实兑现, so that 识别"文档宣称了但代码没做"的差距。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/09-promise-vs-reality.md`
- [ ] README FAQ 的 5 个核心承诺逐条溯源到代码证据（或标为"未兑现"）：
  - "写到 300 章不矛盾" → 跨章记忆代码在哪、测试到多少章
  - "100 章总检查点开销约 7 小时" → 是否有 benchmark 数据支撑
  - "8 层反 AI 检测" → 8 层具体是哪 8 层，代码一一定位
  - "288 条编辑建议硬约束" → 如何拦截重写，硬门禁触发条件
  - "38 种题材模板" → 模板文件在哪、如何被 ink-init 消费
- [ ] Version history v11 → v13.8 每个大版本的"声称改造"vs"代码痕迹"对照表
- [ ] 特别审查两个潜在冲突：v13.6 爽点密集化 vs v13.7 文笔沉浸感（是否有机制协调节奏 vs 文笔的张力？）、v13.5 否定约束 vs v13.2 outline-compliance（是否有重叠规则？）

### US-010: 静态 Bug 扫描与已知风险复核
**Description:** As 审计员, I want 对关键模块做静态 bug 模式扫描 + 复核 CLAUDE.md 声明的 Top 3 风险, so that 定位潜在运行时问题。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/10-bug-scan.md`
- [ ] CLAUDE.md Top 3 风险在当前代码的处理状态：
  - retriever 延迟加载机制是否健全（CLI 和 tests 里）
  - API Key 缺失检查是否全覆盖（03_classify / 05_extract_rules）
  - agent 规格双目录消除状态（US-402 声称已完成，实际验证）
- [ ] 扫描常见 Python 风险模式：裸 except、可变默认参数、None dereferencing、未关闭的文件句柄、SQL 拼接注入、race condition（并发模块 `parallel/`）
- [ ] `checker_pipeline/` 与 `parallel/` 的并发安全性
- [ ] `prompt_cache/` 的缓存一致性（是否有 stale cache 风险）
- [ ] 产出 Top 10 高风险点（按 Blocker/Critical 分级）

### US-012: 开源同类项目横向对比与优化建议
**Description:** As 审计员, I want 调研主流 AI 小说写作工具（开源 + 商业）的架构, so that 从对比中提炼 ink-writer 的独特价值、被行业证伪的做法、可借鉴的优化方向。

**Acceptance Criteria:**
- [ ] 产出 `docs/audit/11-competitive-analysis.md`
- [ ] **选取 5-7 个参照系**（覆盖不同范式）：
  - 商业 SaaS：Sudowrite / Novelcrafter / NovelAI / AI Dungeon
  - 开源：至少 2 个活跃的开源 AI 小说写作项目（通过 GitHub trending / stars 筛选）
  - 学术：Dramatron（DeepMind）、Wordcraft（Google）等参考
- [ ] **横向矩阵对比**（5-7 个维度）：多 agent 架构、RAG / 记忆设计、状态管理（长篇一致性）、用户交互模式、可定制性、部署方式、活跃度
- [ ] 识别 ink-writer 的**独特优势**（比如 288 编辑规则、中文网文场景、检查点闭环）
- [ ] 识别**可借鉴的设计**（至少 3-5 条具体优化建议，附代码落点）
- [ ] 识别**已被行业证伪或转向的做法**（若 ink-writer 还在做，标红警示）
- [ ] 结论：ink-writer 在这个生态里的定位与差距

### US-011: 最终诊断报告汇总
**Description:** As 审计员, I want 将 US-001 到 US-010 的所有发现汇总成一份总报告, so that 用户可一次性阅读全貌并决定后续修复 PRD 的范围。

**Acceptance Criteria:**
- [ ] 产出 `docs/engineering-review-report-v5.md`（延续 v2/v3/v4 的命名惯例）
- [ ] 包含以下板块：
  1. **Executive Summary**（一页纸结论 + 健康度打分 0-100）
  2. **Top 10 Findings**（按严重度排序）
  3. **分维度详细发现**（逐 US 汇总关键点，详情 link 到子报告）
  4. **"叠屋架"地图**（可视化呈现哪些模块有多个实现、哪些规格未落地）
  5. **可删除清单**（立即删除的路径列表，含估算节省空间）
  6. **修复优先级建议**（🔴 Blocker / 🟠 Critical / 🟡 Major / 🔵 Minor）
  7. **横向对比摘要**（来自 US-012，3-5 条核心建议）
  8. **下一步：建议修复 PRD 的 User Story 候选清单**（作为 Step 2 输入）
- [ ] 所有发现必须附：文件路径 + 行号（如适用）+ 具体证据（不接受"可能有问题"式的模糊描述）
- [ ] 报告长度控制：总报告 < 3000 行，详细内容放子文件

---

## Functional Requirements

- **FR-1** 审计产出目录：所有子报告统一放在 `docs/audit/`，总报告 `docs/engineering-review-report-v5.md`
- **FR-2** 扫描脚本统一放在 `scripts/audit/`，可复用，不可嵌入临时路径
- **FR-3** 证据标准：每个发现必须附 `<file>:<line>` 或 `<file>` + 引用片段（10 行内）
- **FR-4** 严重度分级：🔴 Blocker（影响核心流程不可用）/ 🟠 Critical（功能声称但未兑现）/ 🟡 Major（工程质量显著问题）/ 🔵 Minor（可优化项）/ 🟢 Info（信息性说明）
- **FR-5** 发现数量控制：每个子报告 Top 发现 ≤ 15 项，全量发现附在子报告末尾附录
- **FR-6** 可复核：每个发现用户应能 5 分钟内定位到证据
- **FR-7** 报告语言：中文，技术术语保留英文。**受众为作者自用**，语言可直接、锐利，不避讳批评（但仍要有证据）
- **FR-8** 子报告之间交叉引用使用相对路径
- **FR-9** Mermaid 图 / ASCII 图优先于自然语言描述复杂结构
- **FR-10** 审计过程发现任何 Blocker，立即在总报告 Top 提醒（不等到所有子报告完成）

---

## Non-Goals (Out of Scope)

- **不修改任何源码**（包括"顺手改个小 bug"）
- **不做运行时性能基准测试**（如 100 章耗时验证），仅查静态代码与既有 benchmark 数据
- **不跑完整 `/ink-auto 100` 验证**，仅做静态链路追踪 + 必要时跑 `/ink-write` 单章观察
- **不重构文档结构**，只评估
- **不出修复 PRD**（这是 Step 2，基于本报告讨论后另立）
- **不评估"市场需求 / 商业定位"**，只评估"代码 vs 自身声称" + "架构 vs 同类项目"
- **不深读 archive/ 和旧 engineering-review-report-v2/v3/v4 的内容**，仅做路径清点
- **不生成代码补丁或 diff**
- **不触碰 .git、.env、用户凭证**

---

## Technical Considerations

- **扫描工具选型**：
  - Python AST 分析用 stdlib `ast` 模块，不引入新依赖
  - import 分析可用 `pyan` 或手写 AST walker
  - agent 规格（.md）扫描用 grep + 正则
  - SQLite schema 用 `sqlite3 .schema` 或读 migration 文件
- **检索 RAG 索引验证**：如 FAISS 索引能加载则尝试召回 3 个 sample query，对比规则文件确认召回正确
- **CLAUDE.md 约束遵守**：不主动触发 retriever 加载（~30s）、不调用需要 ANTHROPIC_API_KEY 的脚本
- **Agent 规格目录**：记住已统一在 `ink-writer/agents/`（US-402），不要再找 `ink_writer/agents/`
- **并发审计**：可使用 subagent 并行跑 US-001/US-008/US-009 等独立任务加速
- **引用 Q1 中的"E 纯粹好奇当前水平"**：报告需要给一个**健康度总评（0-100 分 + 分档说明）**以回答这个诉求

---

## Success Metrics

- **M1** 用户读完 Executive Summary（1 页）即能回答："这个项目现在处于什么水平 / 值不值得继续投入 / 接下来最该修什么"
- **M2** 可删除清单 ≥ 10 个确定性条目（可立即执行 rm）
- **M3** 每个 Q2 关注点（RAG / 写作链路 / 创意生成 / 工程质量）至少产出 5 个具体发现
- **M4** 至少识别 3 个"叠屋架"痕迹（声称 G1）
- **M5** 至少识别 3 个"文档声称但代码未兑现"（对应 G7）
- **M6** 发现可追溯率 100%（每个都能定位到文件）
- **M7** 本次审计不引入任何新 bug（Non-Goal 遵守 = 审计前后 git diff 代码目录为空）

---

## Open Questions（已全部 Closed）

| # | Question | Decision |
|---|----------|----------|
| 1 | 运行时验证边界 | ✅ 允许跑一次 `/ink-write` 验证 RAG 召回（US-004） |
| 2 | archive/ 和旧 review-report 处理 | ✅ 跳过审计，直接标记可删除（US-008） |
| 3 | 报告受众 | ✅ 自用，语言可锐利（FR-7） |
| 4 | 是否对比开源同类 | ✅ 需要，新增 US-012 |
| 5 | Blocker 告警时机 | ✅ Blocker 即刻告警，Critical 以下进报告（FR-10） |
| 6 | 种子库 v2.0 特殊审查 | ✅ 按普通模块处理（US-005） |
| 7 | Phase-Seed-1 语义 | ✅ 确认为种子库 v2.0 Batch 1-10 构建阶段（US-005 注释） |

## New Open Questions（已全部 Closed）

| # | Question | Decision |
|---|----------|----------|
| 1 | WebFetch/WebSearch 抓竞品文档 | ✅ 允许，仅公开文档 |
| 2 | /ink-init --quick 创建临时项目用于实测 | ✅ 允许，测试后不提交 |
| 3 | 执行分派方式 | ✅ dispatching-parallel-agents 并行，11 US 一次性分派 |

---

## Execution Plan Hint（给下一步的 executor 看）

执行顺序建议（可并行部分标注）：

```
Batch A (并行，纯静态扫描)：
  US-001 全景考古
  US-008 死代码扫描
  US-010 静态 bug 扫描

Batch B (并行，链路与职责)：
  US-002 写作链路追踪
  US-003 checker 矩阵
  US-006 数据层审查

Batch C (并行，RAG 与创意 + 运行时实测)：
  US-004 RAG 审查 (含 /ink-write 实测)
  US-005 创意生成审查
  US-007 工程质量

Batch D (需联网)：
  US-009 README 承诺审计
  US-012 开源对比分析

Final：
  US-011 汇总 → engineering-review-report-v5.md
```

US-011 必须最后做。Batch A/B/C/D 之间尽量并行。

---

## Checklist（PRD 生成后自检）

- [x] 用户选择的关注点（Q2 C+D+E+F）全部有对应 US
- [x] 未使用资源扫描（Q3 B）有专门 US-008
- [x] 审计深度（Q5 C）反映为 **12 个 US** + 源码级证据要求
- [x] 两步走（Q4 B）体现为："不出修复 PRD" Non-Goal
- [x] 每个 US 有可验证的 Acceptance Criteria
- [x] Non-Goals 明确边界
- [x] 开源对比分析（Open Q4）新增 US-012
- [x] 运行时实测允许（Open Q1）体现在 US-004 AC
- [x] Phase-Seed-1 语义（Open Q7）在 US-005 注释澄清
- [x] archive/ 和旧 review 报告跳过深读（Open Q2）体现在 US-008 和 Non-Goals
- [x] 保存至 `tasks/prd-v13-health-audit.md`
