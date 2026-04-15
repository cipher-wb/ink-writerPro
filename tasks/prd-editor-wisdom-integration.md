# PRD: 编辑星河写作智慧集成到 ink-writer

**Feature Name:** editor-wisdom-integration
**Branch Name:** `feat/editor-wisdom`
**Target Runner:** Ralph autonomous loop (Claude Code)
**Data Source:** `/Users/cipher/Desktop/星河编辑/` (288 个纯文本 `.md`，两个子目录：`编辑星河/`、`编辑星河_抖音/`)

---

## 1. Introduction / Overview

起点中文网金牌编辑"编辑星河"在小红书/抖音上发布了大量关于网文写作的实操建议。目前这些建议已被抓取为 288 个 `.md` 文件，分布在两个子目录中，内容混乱且未结构化，**无法被 ink-writer 的 AI 写作链路消费**。

本特性要做的事：
1. **整理**：把 288 份散文式建议归类、去重、结构化，产出人类可读的知识库 + 机器可消费的规则库 + 本地 RAG 召回库。
2. **融入**：把编辑智慧作为**硬约束**嵌入 ink-writer 全链路（context → writer → review → polish），其中**黄金三章**使用最严格门禁。
3. **向前生效**：只约束新生成章节，不回写已有章节；纯文本流水线，不引入付费 embedding、不做音视频转写。

---

## 2. Goals

- G1：把 288 份文件归类为 6-10 个写作主题域（开篇 / 钩子 / 金手指 / 人设 / 节奏 / 爽点 / 雷区 / 题材 / 数据运营 / 其他），每域产出一份人类可读 Markdown。
- G2：从文本中抽取 **结构化规则 JSON**（每条规则含：`id`、`category`、`rule`、`why`、`severity`、`applies_to`、`source_file`），供 checker / writer / polish 直接消费。
- G3：构建**本地 RAG 向量库**（sentence-transformers 本地模型，不走外部 API），支持按章节场景召回 Top-K 编辑建议。
- G4：新增 `editor-wisdom-checker` agent，作为**硬门禁**接入 review 阶段，评分低于阈值必须 polish 修复后才能出章。
- G5：改造 `context-agent` / `writer-agent` / `polish-agent` 三个现有 agent，在其 prompt 中注入召回到的编辑建议。
- G6：**黄金三章特别加强**：在 `golden-three-checker` 中叠加编辑智慧维度，阈值比普通章节更严。
- G7：提供 config 开关（`config/editor-wisdom.yaml`），允许整体开关、阈值调参、分级策略切换。

---

## 3. User Stories

> 每个 story 设计为 Ralph 单轮可完成（≤1 上下文窗口）。按优先级排序，先做数据基础设施，再做 agent 接入，最后做门禁与配置。

---

### US-001: 扫描数据源并生成原始清单
**Description:** 作为开发者，我需要一份完整清单，把 288 个 `.md` 文件的路径、标题、字数、来源平台（小红书/抖音）全部列出来，作为后续所有处理的输入。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/01_scan.py` 读取 `/Users/cipher/Desktop/星河编辑/` 下两个子目录。
- [ ] 产出 `data/editor-wisdom/raw_index.json`，含字段：`path`、`filename`、`title`、`platform`（`xhs` / `douyin`）、`word_count`、`file_hash`。
- [ ] 至少处理 288 个文件（允许因编码问题丢弃，但需在 `skipped.log` 记录原因与数量）。
- [ ] Typecheck / lint passes（`ruff check` + `mypy` 若项目已配）。

---

### US-002: 去重与噪音过滤
**Description:** 作为开发者，我要过滤掉重复内容、纯登录页（例如 `001_手机号登录.md`）、纯标题无正文等噪音。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/02_clean.py` 读 `raw_index.json`。
- [ ] 过滤规则：正文字符 < 50、文件名含"登录/手机号/验证码"、与已保留文件 MinHash 相似度 > 0.9 视为重复。
- [ ] 产出 `data/editor-wisdom/clean_index.json` 与 `cleanup_report.md`（列出丢弃数量+样例）。
- [ ] Typecheck / lint passes。

---

### US-003: 主题分类（6-10 个主题域）
**Description:** 作为开发者，我要把清洗后的文件用 LLM 分类到 6-10 个主题域，每份文件可多标签。

**Acceptance Criteria:**
- [ ] 主题域固定为：`opening`（开篇）、`hook`（钩子/悬念）、`golden_finger`（金手指）、`character`（人设）、`pacing`（节奏）、`highpoint`（爽点）、`taboo`（雷区/禁忌）、`genre`（题材）、`ops`（数据与运营）、`misc`（杂项）。
- [ ] 新脚本 `scripts/editor-wisdom/03_classify.py` 用 Claude Haiku 4.5 批量打标签（含缓存，可断点续跑）。
- [ ] 产出 `data/editor-wisdom/classified.json`（每条加 `categories: string[]`、`summary: string`）。
- [ ] 分类准确率抽检（随机抽 20 条人工核验），≥ 17 条正确即合格（报告写入 `classify_report.md`）。
- [ ] Typecheck / lint passes。

---

### US-004: 分类知识库（10 份人类可读 Markdown）
**Description:** 作为用户（人），我想按主题域阅读编辑星河的全部建议，每个主题一份 Markdown。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/04_build_kb.py` 把 `classified.json` 合并输出到 `docs/editor-wisdom/{category}.md`。
- [ ] 每份 Markdown 结构：`# 主题名` → `## 核心原则`（从文件 summary 聚合，≤10 条） → `## 详细建议`（每条建议含原文引用 + source_file 超链接）。
- [ ] 顶部总索引 `docs/editor-wisdom/README.md` 链接全部 10 份。
- [ ] Typecheck / lint passes（Markdown 结构通过 `markdownlint` 若项目已配）。

---

### US-005: 结构化规则抽取（JSON 规则库）
**Description:** 作为开发者，我要从分类后的建议中抽出可被机器消费的原子规则。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/05_extract_rules.py` 用 Claude Sonnet 4.6 抽规则。
- [ ] 产出 `data/editor-wisdom/rules.json`，数组元素 schema：
    ```
    {id, category, rule, why, severity: "hard"|"soft"|"info",
     applies_to: ["opening"|"any_chapter"|"golden_three"|...],
     source_files: string[]}
    ```
- [ ] 至少抽出 80 条规则；每条 `rule` 字段 ≤ 120 字、祈使句。
- [ ] JSON 通过 `jsonschema` 校验（新增 `schemas/editor-rules.schema.json`）。
- [ ] Typecheck / lint passes。

---

### US-006: 本地 RAG 向量库构建
**Description:** 作为开发者，我要让 ink-writer 在写章节时能按场景召回最相关的编辑建议。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/06_build_index.py` 使用 `sentence-transformers` 的 `BAAI/bge-small-zh-v1.5`（本地，不走外部 API）。
- [ ] 索引持久化到 `data/editor-wisdom/vector_index/`（FAISS 或 chroma 本地文件均可）。
- [ ] 新模块 `ink_writer/editor_wisdom/retriever.py` 暴露 `retrieve(query: str, k: int = 5, category: str | None = None) -> list[Rule]`。
- [ ] 单元测试覆盖召回接口（`tests/editor_wisdom/test_retriever.py`），验证召回结果 category 过滤正确。
- [ ] Typecheck / lint / test passes。

---

### US-007: 配置文件与全局开关
**Description:** 作为用户，我希望能一键开关编辑智慧模块、调阈值、切分级策略。

**Acceptance Criteria:**
- [ ] 新增 `config/editor-wisdom.yaml`，字段：`enabled: bool`、`retrieval_top_k: int`、`hard_gate_threshold: float`、`golden_three_threshold: float`、`inject_into: {context, writer, polish}`。
- [ ] 新模块 `ink_writer/editor_wisdom/config.py` 读取并以 dataclass 暴露。
- [ ] 默认值：`enabled=true`、`top_k=5`、`hard_gate_threshold=0.75`、`golden_three_threshold=0.85`。
- [ ] 单元测试验证 yaml 加载与字段默认值。
- [ ] Typecheck / lint / test passes。

---

### US-008: 新增 editor-wisdom-checker agent
**Description:** 作为 reviewer 链路，我需要一个专门基于编辑星河规则评分的 checker。

**Acceptance Criteria:**
- [ ] 新 agent 定义 `agents/ink-writer/editor-wisdom-checker.md`（参照现有 `golden-three-checker` 结构）。
- [ ] agent prompt 输入：当前章节文本 + retriever 召回的 Top-K 规则（含 severity）。
- [ ] agent 输出 JSON：`{score: 0-1, violations: [{rule_id, quote, severity, fix_suggestion}], summary}`。
- [ ] 接入 `ink-review` 编排：对每章自动调用；score 写入章节元数据。
- [ ] 单测：mock LLM 响应，验证输出 JSON 结构通过 `schemas/editor-check.schema.json` 校验。
- [ ] Typecheck / lint / test passes。

---

### US-009: 改造 context-agent — 注入召回规则
**Description:** 作为写作链路，context-agent 组装创作执行包时应附带该场景下 Top-K 编辑建议。

**Acceptance Criteria:**
- [ ] 修改 `agents/ink-writer/context-agent.md` prompt，新增"编辑建议"段，内容由 retriever 以章节大纲 + 场景类型为 query 检索。
- [ ] 当 `config.enabled=false` 或召回为空时，保持原有行为不变（无建议段）。
- [ ] 新增集成测试：给定一份"开篇章节大纲"，断言执行包中包含 `opening` category 的规则至少 1 条。
- [ ] Typecheck / lint / test passes。

---

### US-010: 改造 writer-agent — prompt 注入
**Description:** 作为写作链路，writer-agent 起草时必须在 system/user prompt 中显式看到召回规则并被要求遵守。

**Acceptance Criteria:**
- [ ] 修改 `agents/ink-writer/writer-agent.md`，在提示词中加入"硬约束：以下规则必须遵守，违反将被打回"段落。
- [ ] 规则按 severity 分组呈现（hard 置顶，soft 次之，info 省略或末尾）。
- [ ] 对黄金三章（chapter_no ≤ 3），额外注入 `golden_three` applies_to 的规则。
- [ ] 集成测试：截获发送给 LLM 的 prompt，断言包含至少 1 条 hard 规则文本。
- [ ] Typecheck / lint / test passes。

---

### US-011: 硬门禁接入 —— 未达阈值必须走 polish 修复
**Description:** 作为质量保障，editor-wisdom-checker 打分 < `hard_gate_threshold` 时必须进入修复循环，修复后重评，通过才能出章。

**Acceptance Criteria:**
- [ ] 修改 `ink-review` 编排：读 checker score，低于阈值触发 `polish-agent`，polish 输入含 violations 列表。
- [ ] polish 后自动 re-check；最多 3 次重试，仍不通过则写入 `chapters/{n}/blocked.md` 并中断该章生成（**不静默放行**）。
- [ ] 日志写入 `logs/editor-wisdom/{chapter}.log`。
- [ ] 集成测试：mock 一个必定低分的章节，验证触发 polish 循环且 blocked.md 正确生成。
- [ ] Typecheck / lint / test passes。

---

### US-012: 黄金三章特别加强
**Description:** 作为商业化关键，第 1-3 章门禁阈值比普通章节更高。

**Acceptance Criteria:**
- [ ] 修改 `agents/ink-writer/golden-three-checker.md`，叠加 editor-wisdom 维度（category 限定为 `opening` / `hook` / `golden_finger` / `character`）。
- [ ] 使用 `config.golden_three_threshold`（默认 0.85）替代普通阈值。
- [ ] 单独产出 `reports/golden-three-editor-wisdom.md` 报告。
- [ ] 集成测试：第 1 章用相同文本跑，当 `is_golden_three=true` 时阈值更严、触发 polish。
- [ ] Typecheck / lint / test passes。

---

### US-013: 改造 polish-agent —— 按 violations 精确修复
**Description:** 作为修复链路，polish-agent 应接收 violations 列表并逐条修复，而非泛泛润色。

**Acceptance Criteria:**
- [ ] 修改 `agents/ink-writer/polish-agent.md`，新增"按违规列表修复"工作模式。
- [ ] 每条 violation 输入含：`rule` + `quote`（原文片段）+ `fix_suggestion`。
- [ ] polish 输出需保留 `_patches.md`（diff 形式）供 audit。
- [ ] 集成测试：给定 3 条 violations，断言输出 diff 至少覆盖其中 2 条对应段落。
- [ ] Typecheck / lint / test passes。

---

### US-014: CLI 管理命令
**Description:** 作为用户，我需要简单的命令来重建知识库、重建索引、查询规则。

**Acceptance Criteria:**
- [ ] 新 CLI 子命令 `ink editor-wisdom rebuild`（跑 US-001 → US-006 全流程）。
- [ ] `ink editor-wisdom query "开篇 3 秒钩子"` 打印 Top-5 召回规则。
- [ ] `ink editor-wisdom stats` 打印：规则总数、分类分布、索引文档数、最后更新时间。
- [ ] `--help` 完整、有使用示例。
- [ ] Typecheck / lint / test passes。

---

### US-015: 文档与 AGENTS.md 沉淀
**Description:** 作为未来迭代者（人或 AI），我需要知道这套系统怎么用、怎么扩展规则。

**Acceptance Criteria:**
- [ ] 新文档 `docs/editor-wisdom-integration.md`，含：架构图（文本 mermaid）、数据流、如何新增规则、如何调阈值、常见问题。
- [ ] 更新根 `CLAUDE.md` / `AGENTS.md`：新增 "编辑智慧模块" 段落，指向上文文档并列出关键 gotchas。
- [ ] README 顶部加一行 "Powered by 编辑星河 wisdom (本地 RAG)" 的引用声明。
- [ ] 无代码改动即可通过 CI。

---

## 4. Functional Requirements

- **FR-1:** 系统必须从 `/Users/cipher/Desktop/星河编辑/` 递归读取所有 `.md` 文件。
- **FR-2:** 系统必须过滤噪音（登录页、过短、高度重复）并保留审计日志。
- **FR-3:** 系统必须将清洗后的内容分类到固定 10 个主题域之一（或多个）。
- **FR-4:** 系统必须产出人类可读的分类 Markdown 知识库（10 份 + 1 README）。
- **FR-5:** 系统必须抽取 ≥ 80 条结构化原子规则到 `rules.json`，并通过 jsonschema 校验。
- **FR-6:** 系统必须基于本地 sentence-transformers 构建向量索引，**禁止调用外部 embedding API**。
- **FR-7:** 系统必须提供 `retrieve(query, k, category)` 接口供其他模块调用。
- **FR-8:** 系统必须新增 `editor-wisdom-checker` agent，输出结构化 violations。
- **FR-9:** 系统必须改造 `context-agent` / `writer-agent` / `polish-agent` / `golden-three-checker` 四个现有 agent，注入召回规则。
- **FR-10:** 系统必须在 checker 评分低于阈值时触发硬门禁（polish → re-check → 最多 3 次重试 → 仍失败则 block）。
- **FR-11:** 黄金三章（chapter_no ≤ 3）必须使用更严的独立阈值。
- **FR-12:** 所有行为必须由 `config/editor-wisdom.yaml` 可调可关。
- **FR-13:** 必须提供 `ink editor-wisdom {rebuild|query|stats}` CLI。

---

## 5. Non-Goals (Out of Scope)

- **NG-1:** 不做视频/音频转写（数据已是纯文本，另立项处理视频源）。
- **NG-2:** 不回写/重写已完成的历史章节（仅对新章节生效）。
- **NG-3:** 不引入付费 embedding 服务（OpenAI / Cohere / 阿里百炼等一律禁用），仅本地模型。
- **NG-4:** 不做跨作者风格迁移，仅提取"编辑偏好规则"。
- **NG-5:** 不做 Web UI（仅 CLI + 文件产物，Dashboard 集成由后续 PRD 处理）。
- **NG-6:** 不做分布式/多机部署，单机本地运行。
- **NG-7:** 不做付费版 A/B 对比实验，交付即上线。

---

## 6. Design Considerations

- **数据目录**：所有中间产物进 `data/editor-wisdom/`；人类阅读文档进 `docs/editor-wisdom/`；向量索引进 `data/editor-wisdom/vector_index/`（`.gitignore` 掉二进制索引文件，只提交构建脚本）。
- **脚本命名**：`scripts/editor-wisdom/NN_*.py`，数字前缀表明 pipeline 顺序，便于 Ralph 单步独立跑。
- **Agent 复用**：尽量基于现有 `golden-three-checker` / `polish-agent` 结构改造，不重建轮子。
- **Prompt 可观测**：所有注入规则的 prompt 需在 `logs/editor-wisdom/` 留痕，便于调试门禁异常。

---

## 7. Technical Considerations

- **LLM 模型选择**：分类用 Haiku 4.5（便宜快），规则抽取用 Sonnet 4.6（准度更重要），checker 用 Sonnet 4.6。
- **Embedding 模型**：`BAAI/bge-small-zh-v1.5`（中文向量、本地、小于 500MB）。如无网络下载，脚本应提示用户手动放置到 `models/` 下。
- **缓存策略**：分类与规则抽取必须实现 file_hash 级缓存，未变内容不重跑。
- **并发**：pipeline 脚本支持 `--workers N`，默认 4。
- **失败处理**：任何单文件失败不中断批处理，记录到 `errors.log`。
- **集成点**：
  - `ink-review`（现有编排）→ 加入 editor-wisdom-checker
  - `context-agent` / `writer-agent` / `polish-agent` / `golden-three-checker`（现有 4 个 agent）→ prompt 改造
  - 新 `ink_writer/editor_wisdom/` 模块（retriever / config / cli）

---

## 8. Success Metrics

- **SM-1:** 规则库 ≥ 80 条，jsonschema 校验通过。
- **SM-2:** 分类准确率 ≥ 85%（20 条人工抽检 ≥ 17 条正确）。
- **SM-3:** 100% 新章节在出章前经过 editor-wisdom-checker 评分。
- **SM-4:** 黄金三章硬门禁触发后，polish 后重评通过率 ≥ 80%。
- **SM-5:** 端到端单章生成时延增幅 ≤ 30%（相比未启用编辑智慧的 baseline）。
- **SM-6:** 作者主观评估：随机挑 10 章前后对比，有 ≥ 7 章被评为"更精彩"。

---

## 9. Open Questions

- **OQ-1:** 规则抽取阶段遇到互相矛盾的建议（例如"开篇必须 3 秒金手指" vs "开篇不要直接爆金手指"）如何处理？建议：保留两条，由 `applies_to` 场景区分；无法区分的标 `severity=info` 仅供参考。
- **OQ-2:** 向量索引何时重建？建议：`rebuild` 命令手动触发；未来可加文件变更自动触发。
- **OQ-3:** 若某章节连续 3 次 polish 仍未达阈值导致 block，是否需要人工介入通道？建议：MVP 阶段直接 block + 写报告，后续再加 `--override` flag。
- **OQ-4:** Dashboard 是否需要展示当前章节的 editor-wisdom 分数？本 PRD 不做，留给后续 PRD。

---

## 10. 交付清单速查

| 产物类型 | 路径 |
|---|---|
| 原始扫描清单 | `data/editor-wisdom/raw_index.json` |
| 清洗后清单 | `data/editor-wisdom/clean_index.json` |
| 分类结果 | `data/editor-wisdom/classified.json` |
| 结构化规则库 | `data/editor-wisdom/rules.json` + `schemas/editor-rules.schema.json` |
| 向量索引 | `data/editor-wisdom/vector_index/` |
| 人类可读知识库 | `docs/editor-wisdom/{category}.md` × 10 + `README.md` |
| 配置 | `config/editor-wisdom.yaml` |
| 新模块 | `ink_writer/editor_wisdom/{retriever,config,cli}.py` |
| 新 agent | `agents/ink-writer/editor-wisdom-checker.md` |
| 改造 agent | `context-agent` / `writer-agent` / `polish-agent` / `golden-three-checker` |
| pipeline 脚本 | `scripts/editor-wisdom/0N_*.py` |
| 集成文档 | `docs/editor-wisdom-integration.md` |
