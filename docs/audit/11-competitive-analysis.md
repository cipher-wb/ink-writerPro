# US-012 开源同类项目横向对比与优化建议

> ink-writer v13.8.0 深度健康审计 · 审计编号 US-012
> 审计日期：2026-04-17
> 审计方法：公开文档 + GitHub 元数据 + 产品官网，仅基于可公开获取的信息

---

## Executive Summary

ink-writer 在"**中文网文商业连载 + 终端式 CLI + 硬门禁质检**"这个交叉赛道上**几乎无直接对手**。国际商业 SaaS（Sudowrite/Novelcrafter）在 Story Bible 与 UX 打磨上领先，但主服英文作家、不理解网文平台（起点/番茄）审核规则；国内开源项目（AI_NovelGenerator/NovelForge/AI_Gen_Novel）在记忆与多 agent 上有相似思路，但**无一引入"编辑规则硬门禁 + 检查点闭环 + 防 AI 检测"三位一体**。学术端 Dramatron/Wordcraft 贡献了"分层生成"与"co-writing 交互"的理论范式。

**ink-writer 的独特竞争位**：起点/番茄同级编辑反馈 288 条 → RAG 硬规则 + v13.2 Logic Fortress 双层审查 + v13.0 追读力/爽点调度 + 30+ 张状态表 + Anti-Detection 统计层。在"**300 章不崩、过起点审核**"这件事上，它把别的工具当玩具。

**三大优化方向**：
1. 借鉴 AutoNovel 的**5 层共同演化（协作修订触发上游更新）**和 LibriScribe 的**双 CLI+web 呈现**
2. 借鉴 Novelcrafter 的 **Progressions（角色随时间变化追踪）**，补齐 `ink_writer/foreshadow/` 纵向维度
3. 借鉴 Sudowrite **Series Folder**、为多书作者准备跨项目知识继承

---

## 参照系 One-Pager

### 1. Sudowrite（商业 SaaS，美国）

| 维度 | 内容 |
|------|------|
| 多 agent | **否**（单模型 Muse 1.5 + 20+ 外部模型切换为"Prose Mode"，非 agent 分工） |
| RAG/记忆 | **Story Bible**（角色/情节线/世界观知识库，自动索引） |
| 长篇一致性 | Story Bible + **Series Folder**（多本书跨书一致性），明确支持 100k+ 字 |
| 交互 | Web 富文本编辑器，inline suggestion（Describe/Expand/Rewrite/Brainstorm） |
| 可定制 | Style Examples 学用户文风；1000+ 社区插件；但不能自带 API Key |
| 部署 | 云端 SaaS（editor.sudowrite.com） |
| 活跃度 | 商业公司运营，Muse 1.5 发布 2025-06；Story Engine 持续迭代 |
| 定价 | $10/$22/$44 月档（credit 制） |
| 定位 | **小说作者辅助**。核心 USP：唯一专训小说模型 + Story Bible |

### 2. Novelcrafter（商业 SaaS，独立开发）

| 维度 | 内容 |
|------|------|
| 多 agent | **否**（单调用管线） |
| RAG/记忆 | **Codex**（结构化实体库：角色/地点/事件/派系/物品 + 别名 + Tags 智能匹配） |
| 长篇一致性 | Codex 自动注入相关实体到 prompt + **Progressions**（动态进展追踪：年龄/关系/政治变化） |
| 交互 | Web 富文本 + Grid/Matrix 大纲 + Scene Beats 卡片 + Chat with Scene |
| 可定制 | **BYO API Key**（OpenAI/Anthropic/Gemini 全支持）+ **本地 AI 支持**（重要） |
| 部署 | 云 Web + 移动端；Local AI support 表明 offline inference 可选 |
| 活跃度 | 2023 起活跃迭代，独立开发者但功能极深 |
| 定价 | Subscription（未详述） |
| 定位 | **长篇结构化写作平台**，最接近"严肃作家+Story Bible"范式 |

### 3. NovelAI（商业，原 AI Dungeon 同源）

| 维度 | 内容 |
|------|------|
| 多 agent | **否**（生成+lorebook 激活机制） |
| RAG/记忆 | **Lorebook**（Activation Keys 触发条目注入） + **Memory** 常驻段 + **Author's Note** |
| 长篇一致性 | 128k 上下文窗口；**但官方承认：超过 8,192 tokens 后记忆退化**，需手动重复关键点 |
| 交互 | Text editor，续写/改写/扩展 |
| 可定制 | Kayra-XL 专训模型；Lorebook 自写；不可换底层 LLM |
| 部署 | 云端 SaaS |
| 活跃度 | 2021 至今活跃；以二次元/成人向小众立稳 |
| 定价 | $10/月起 |
| 定位 | **娱乐 + 短中篇 + ACGN 风**。长篇正统写作不强 |

### 4. AI Dungeon（商业，互动冒险范式）

| 维度 | 内容 |
|------|------|
| 多 agent | **否** |
| RAG/记忆 | **Memory Bank（嵌入式自动摘要）** + **Story Cards（前身 World Info，关键词触发）** |
| 长篇一致性 | Auto Summarization 压缩过往 6 个动作 → 嵌入存储 → 关键点检索 |
| 交互 | **互动叙事**（Do/Say/Story），非线性写作 |
| 可定制 | Scenarios（模板化世界）+ Story Cards 自定义 |
| 部署 | 云 Web + 移动 |
| 活跃度 | 老牌（2019-），持续更新 Memory 系统 |
| 定位 | **互动故事 / GameBook**，非传统小说创作 |

### 5. Dramatron（学术，DeepMind 2022）

| 维度 | 内容 |
|------|------|
| 多 agent | **否**（prompt-chaining） |
| RAG/记忆 | 无持久化，纯 prompt context |
| 长篇一致性 | **分层生成**：log line → 角色/地点/情节点 → 对白 |
| 交互 | Co-writing，Colab notebook |
| 可定制 | 自接 LLM（70B）；纯研究脚本 |
| 部署 | Colab notebook |
| 活跃度 | 1.1k stars，学术代码库，无商业迭代 |
| 定位 | **剧本/戏剧生成 PoC**。贡献："分层"成为长篇范式基石 |

### 6. Wordcraft（学术，Google PAIR 2021）

| 维度 | 内容 |
|------|------|
| 多 agent | **否**（单 LaMDA + few-shot） |
| RAG/记忆 | 无 |
| 长篇一致性 | **不追求**。核心发现：*"LaMDA 写完整故事是死路，当调料用才有效"* |
| 交互 | Continuation / Infill / Elaboration / Rewriting 四种插件式操作 |
| 定位 | **Human-AI 协同编辑器**。贡献：证明"短插件式交互 > 端到端生成" |

### 7. 开源：AI_NovelGenerator（YILING0013，中文）

| 维度 | 内容 |
|------|------|
| 多 agent | 4 步管线：Settings → Directory → Draft → Finalize |
| RAG/记忆 | `global_summary.txt` + `character_state.txt` + `plot_arcs.txt` + 本地 vectorstore |
| 长篇一致性 | embedding_retrieval_k 召回过往片段；一致性 proofreader 检测矛盾 |
| 交互 | GUI workbench（Tkinter）+ PyInstaller 打包 |
| 可定制 | 支持 OpenAI/Ollama/DeepSeek；1-120 章，单章 4000 字 |
| 部署 | 本地 Python/exe |
| 活跃度 | **4.4k stars**（国内最高）；v1.4.4 (2025-03)；AGPL-3.0 |
| 定位 | **中文开源长篇生成器标杆**。但审查薄弱、无编辑规则层 |

### 8. 开源：NovelForge（RhythmicWave，中文）

| 维度 | 内容 |
|------|------|
| 多 agent | 双 agent：**Inspiration Assistant** + **Workflow Agent**（自然语言生成工作流代码） |
| RAG/记忆 | **知识图谱（SQLite/Neo4j）**+ **@DSL 上下文注入**（`[previous]`/`[sibling]`/`[filter:...]`） |
| 长篇一致性 | JSON Schema **逐字段生成 + 用户确认**（非整段输出）；自动注入相关实体 |
| 交互 | FastAPI + Vue 3 + Electron 桌面应用；**卡片式创作** |
| 可定制 | 用户可定义 Schema + 工作流 |
| 部署 | 本地 Electron |
| 活跃度 | 657 stars；v0.9.4 (2026-03)；AGPLv3 |
| 定位 | **卡片/结构化创作新范式**。Schema 驱动是亮点 |

### 9. 开源：AutoNovel（NousResearch）

| 维度 | 内容 |
|------|------|
| 多 agent | **27 个专用 Python 脚本**（foundation/first-draft/revision/export 四相） |
| RAG/记忆 | **5 层共同演化**（voice/world/character/outline/prose 双向传播）+ `state.json` 追 propagation debts + `canon.md` 集中硬事实 |
| 长篇一致性 | **双免疫**：regex 机械扫描（禁词/陈词）+ LLM Judge 评分；foundation loop 阈值 ≥7.5 |
| 交互 | CLI 全自动（已出产 79,456 字完整小说） |
| 部署 | 本地 Python |
| 活跃度 | 656 stars；Python 94.8%；Hermes 团队 |
| 定位 | **与 ink-writer 最相似的开源竞品**。优势：5 层反向传播；劣势：英文为主、无中文网文规则 |

### 10. 开源：AI_Gen_Novel（cjyyx，中文）

| 维度 | 内容 |
|------|------|
| 多 agent | 多 agent 协作讨论（灵感激发） |
| RAG/记忆 | **借鉴 RecurrentGPT**：LLM 压缩长文本为几句 memory，递归延展 |
| 交互 | Gradio Web |
| 活跃度 | 411 stars；MIT；较早的网文专题项目（作者明确写"当前 LLM 能力不够写完整长篇"） |
| 定位 | **中文网文 RecurrentGPT 实验**。理论贡献，工程已被 AI_NovelGenerator 超越 |

### 11. 开源：LibriScribe（英文多 agent 基准）

| 维度 | 内容 |
|------|------|
| 多 agent | concept/outline/character/world/write/edit/QA 专业 agent |
| RAG/记忆 | JSON 状态文件（无向量）；roadmap 有 ChromaDB |
| 活跃度 | 71 stars；MIT；CLI + 规划 Web 前端 |
| 定位 | **学术级多 agent PoC**。单薄，但展示了 full pipeline 骨架 |

---

## 横向对比矩阵（7 维度）

| 项目 | 多 Agent | 长篇记忆 | 中文网文适配 | 编辑规则硬门禁 | 反 AI 检测 | 开源 | 成熟度 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **ink-writer v13.8** | **17 agents** | state.json+25 表+vectors.db+Style RAG | **原生（起点/番茄）** | **288 条 RAG 硬门禁** | **8 层统计+校准** | GPL-3 | 生产级 |
| Sudowrite | 无 | Story Bible + Series Folder | 弱（英文主） | 无 | 无 | 闭源 | 商业成熟 |
| Novelcrafter | 无 | Codex + Progressions | 弱 | 无 | 无 | 闭源 | 商业成熟 |
| NovelAI | 无 | Lorebook + Memory（8k 后退化） | 弱 | 无 | 无 | 闭源 | 商业成熟 |
| AI Dungeon | 无 | Memory Bank + Story Cards | 弱 | 无 | 无 | 闭源 | 商业成熟 |
| Dramatron | 无（分层链） | 无 | 无 | 无 | 无 | Apache-2 | PoC |
| Wordcraft | 无 | 无 | 无 | 无 | 无 | 研究 | PoC |
| AutoNovel | 27 脚本 | 5 层共演化+canon.md | 无 | regex + LLM judge | 弱 | 无 license | 实验 |
| AI_NovelGenerator | 4 步 | 3 状态文件+vectorstore | **是（基础）** | proofreader | 无 | AGPL-3 | 活跃 |
| NovelForge | 双 agent | 知识图谱+@DSL | **是** | Schema 校验 | 无 | AGPL-3 | 活跃 |
| AI_Gen_Novel | 多 agent | RecurrentGPT | **是** | 无 | 无 | MIT | 早期 |
| LibriScribe | 7 agents | JSON 状态 | 无 | 无 | 无 | MIT | 早期 |

---

## ink-writer 独特优势（ONLY，非广义领先）

| 能力 | 独特性评估 | 证据 |
|------|---------|------|
| **288 条编辑规则硬门禁** | **行业独有**。无任何对标产品把起点/番茄编辑建议 RAG 化 | `ink_writer/editor_wisdom/`、`config/editor-wisdom.yaml`、editor-wisdom-checker、hard_gate_threshold=0.75 |
| **38 种中文网文题材模板** | **中文场景独家**。Sudowrite 最多通用类型，不理解"修仙/规则怪谈/系统流" | `ink-init --quick` 三套方案生成；元规则库 M01-M10 |
| **检查点闭环 + 自动修复** | **AutoNovel 有但无硬阻断**。ink-write Step 3 有 10+ 个 checker gate，3 次 check + 2 次 polish 后阻断 | `ink_writer/checker_pipeline/`、review_gate.py |
| **8 层反 AI 检测（统计层）** | **行业独有**。117 本起点标杆校准句长 CV、重复、连接词 | `ink_writer/anti_detection/` |
| **Strand Weave 节奏系统** | **具象化独家**。把"主线 60% / 感情 20% / 世界观 20%"变成硬监测 | Quest/Fire/Constellation 断档上限；pacing-checker |
| **种子库扰动引擎 v2.0** | **独家**。10 batch × 100 条种子 + 4 档激进度，对抗 LLM 套路化 | 近期 Phase-Seed-1 commits |
| **30+ 张状态表** | **最强**。NovelAI Lorebook 纯激活、Codex 注入无结构化时序。ink-writer state.json + index.db 可承载 300 章 | `state.json`, `index.db` |
| **跨章语义召回（RAG）** | 有，但不独特。与 AI_NovelGenerator、AutoNovel 思路一致 | `ink_writer/semantic_recall/`、vectors.db |
| **Logic Fortress v13.2 双层审查** | **独家**。MCC 强制合规清单 + logic-checker（8 层）+ outline-compliance-checker（6 层） | v13.2.0 CHANGELOG |
| **v13.0 追读力 + 爽点调度器 + 情绪心电图** | **中文网文独家组合** | `ink_writer/reader_pull/`、`ink_writer/emotion/` |
| **v13.7 文笔沉浸感四法则** | **独家**。电影镜头切换/感官轮换/信息密度/环境情绪共振 | v13.7.0 CHANGELOG |
| **v13.8 陈词黑名单 + 平台榜单反向建模** | **独家**。起点/番茄 90 天缓存 | v13.8.0 CHANGELOG |

---

## 可借鉴设计（5 条，附代码落点）

### 建议 1：AutoNovel 的"5 层共同演化 + 反向传播"

**对方做法**：voice/world/character/outline/prose 五层，下游发现矛盾 → 向上冒泡修订 `canon.md`。不是单向往下生成，而是双向。

**ink-writer 现状**：`ink-write` Pipeline 是**单向前进**（Step 0 → Step 5），Step 3 Review 发现问题只能在**当前章节内**修复（polish 兜底），不会冒泡回改 `state.json` 的设定或前期大纲。

**落点**：
- 新增 `ink_writer/propagation/` 模块（当前无此能力）
- 在 Step 5 data-agent 后增加 **canon-drift-detector**：若新章节数据与 `state.json` 或 `outline/volume_N.json` 存在不可协调矛盾，产出 `propagation_debt.json` 供下次 `/ink-plan` 主动消费
- `ink-macro-review` 每 50 章触发一次 **propagation 清算**，避免 debt 累积

**预期收益**：当下 `/ink-resolve` 只处理实体消歧，但若卷一铺的伏笔在卷三无法自圆，当前系统不会主动修正卷二的大纲。AutoNovel 的阈值 loop（foundation score ≥7.5）可直接借鉴。

---

### 建议 2：Novelcrafter "Progressions"（动态进展追踪）

**对方做法**：`Codex` 条目除静态属性外，可挂 **Progressions**——记录"角色在章节 N 后年龄/关系/立场变化"。AI 会读取"当前章节点的进展切片"而非总条目。

**ink-writer 现状**：`thread-lifecycle-tracker` 追伏笔/线索断更，但角色状态只在 `state.json` 里持最新值（或通过 index.db 历史快照推导）。缺"时间轴上的角色演变视图"。读者视角的"三十章前他说过 X，现在却说 Y"难以检测。

**落点**：
- 扩 `ink_writer/foreshadow/` → 泛化为 `ink_writer/progression/`
- 在 schema 加 `character_progressions` 表：`(character_id, chapter_no, dimension, from_value, to_value, cause)`
- `context-agent` 的 3-layer pack 增加"本章之前的角色演进摘要"
- **可立即与已存在的 `ooc-checker` 的 voice fingerprint 合并使用**

**预期收益**：解决"配角在 80 章后重新出场 OOC"问题（README FAQ 已提到 index.db 召回，但进展摘要会更高效）。

---

### 建议 3：Sudowrite "Series Folder"（多书共享知识库）

**对方做法**：Series Folder 跨越多本书，Story Bible 条目可被多本引用；续集/前传自动继承设定。

**ink-writer 现状**：每个项目（project_root）是独立的 `state.json`。作者写完一本要开续集，需要手动迁移或重新 `/ink-init`。`/ink-learn` 提取成功模式但仅在本项目内。

**落点**：
- 新增 `~/.claude/ink-writer/library/`：用户级跨项目知识库
- `ink-init` 增加 `--inherit=book_id` 参数：从 library 导入角色/世界观/文风锚点
- `ink-learn` 的成功模式可选推到 library
- **低改动高回报**：只需新增一个目录层级+两个 CLI 参数

**预期收益**：针对 ink-writer 的真实用户（商业长篇作者，一辈子写几十本），沉淀作者"个人风格资产"。

---

### 建议 4：NovelForge "JSON Schema 逐字段生成 + 用户确认"

**对方做法**：每种卡片定义 Schema，AI 逐字段填充，用户可逐字段确认/回滚，而非整段覆盖。

**ink-writer 现状**：`data-agent` 一次抽取整章数据回写 state.json + index.db，用户干预是**事后** `/ink-resolve` 处理歧义。高置信度条目用户不易审核。

**落点**：
- 在 `/ink-dashboard` 增加"待确认实体"面板（部分已有，但可借鉴 NovelForge 的 Schema 驱动交互）
- data-agent 输出中对**新实体**标 `confidence < 0.9` 的一律列入待确认队列
- 用户可在 Dashboard 端字段级修改（而非只能 accept/reject）

**预期收益**：ink-writer 的"消歧积压"（见 README「`/ink-resolve` 偶尔处理消歧积压」）可从"事后补课"变成"创作中实时协作"。

---

### 建议 5：Wordcraft 的"插件式短交互"原则反思

**对方做法（反面教材 + 警示）**：Wordcraft 论文明言：*"LaMDA 写完整故事是死路，当调料用才有效"*。

**ink-writer 现状**：`/ink-auto 20` 是全自动长篇端到端生成。这在产品上是最大卖点，也是最大风险——如果某一层出错且未被 checker 接住，连锁偏离越写越远（这也是 v13.2 Logic Fortress 要解决的事）。

**落点**：
- **不是砍全自动**（它是 USP），而是**增加"插件模式"入口**：`/ink-write --mode=assist` 用户提供段落骨干，ink-writer 只做 describe/expand/rewrite 四类短操作
- 代码落点：在 `skills/ink-write/SKILL.md` 增加 mode 分支；writer-agent 加 `op_type` 参数
- 把 ink-writer 的 checker 栈复用在"人类作者的辅助写作"上，开辟**第二用户群**（愿意自己写但需要 AI 辅助的作者）

**预期收益**：产品向下兼容"抗拒全自动"的严肃作者群体，扩充用户 TAM。

---

## 需反思的做法（已被行业证伪或存在隐忧）

### 反思 1：NovelAI 的"扩大上下文窗口"路径

**现象**：NovelAI 吹 128k context，但官方自承**"8,192 tokens 后记忆退化"**，需要**用户手动每 3-4 段重复关键信息**。

**与 ink-writer 关系**：ink-writer 从未走"无脑塞大 context"路线，而是走 state.json + vectors.db 结构化 + RAG 召回，这**是正确方向**。**保持住，不要倒退**。具体而言：不要因 Claude/GPT 推出更长 context 就简化结构化层。

### 反思 2：Wordcraft 的"不追求长篇"路线

**现象**：Wordcraft 明确不做长篇，论文得出"LLM 做完整故事是死路"。

**与 ink-writer 关系**：ink-writer **做的就是 Wordcraft 判死刑的事**——全自动长篇。但 2021 年 Wordcraft 的结论基于 LaMDA + few-shot 时代。**v13 时代结论已被 ink-writer 的 288 规则硬门禁 + 检查点闭环部分证伪**——只要有足够强的质检层，全自动长篇可行。所以：**保持自动化路线，但持续加厚 checker 栈**。

### 反思 3：LibriScribe 的"纯 agent 名目"陷阱

**现象**：LibriScribe 有 7 个 agent（concept/outline/.../QA）但只有 71 stars、**RAG roadmap 未实现**。说明**agent 数量不等于能力**。

**与 ink-writer 关系**：ink-writer 有 17 个 agent，已出现"伪重叠"现象（US-003 审计发现 8 对 false overlap）。继续走**审慎合并**路线（如 US-401 foreshadow+plotline → thread-lifecycle-tracker）是对的，**切勿追求 agent 数量虚荣**。

### 反思 4：AI_NovelGenerator "单章 4000 字 + 120 章上限"硬编码

**现象**：AI_NovelGenerator 产品配置最大 120 章、单章 4000 字。对于 200 万字（400-500 章）的起点长篇是天花板。

**与 ink-writer 关系**：README 已声明"300 章不崩"，且 v13.3 字数上限 4000 字硬上限。**注意：不要向下学习 AI_NovelGenerator 给"章数上限"设硬限**。目前 ink-writer 章数理论无上限（受 SQLite + 存储约束），这是关键优势。

### 反思 5：AutoNovel "英文正统文学"定位风险

**现象**：AutoNovel 已产出 79,456 字完整小说（《The Second Son of the House of Bells》），LaTeX 排版 + 封面生成，走"高雅出版"路线，但**英文、短篇、非商业连载场景**。

**与 ink-writer 关系**：提醒 ink-writer **不要被"做出一本可读的书"引诱往正统文学偏**。起点/番茄的商业变现要求 ≠ 出版业文学性要求。v13.8 有"V1 文学狂野 / V2 烟火接地气 / V3 江湖野气"三档语言风格，这是对的方向——**商业性和文学性要分档而不是融合**。

---

## 定位结论

### ink-writer 在生态中的位置

**四象限定位图**（信息密度高的文字版）：

```
                   高自动化
                      |
                      |
     ink-writer ◆     |    AI_NovelGenerator
     AutoNovel        |    AI_Gen_Novel
                      |    LibriScribe
                      |
中文网文 --------------+-------------- 通用/英文
                      |
                      |    Sudowrite
     NovelForge       |    Novelcrafter
                      |    NovelAI
     Wordcraft ◇      |    AI Dungeon (互动)
                      |
                   低自动化 / 高人机协作
```

ink-writer 在 **"高自动化 × 中文网文商业连载"** 象限**几乎无对手**。最接近的 AutoNovel 在"高自动化"维度相当，但在中文网文侧几乎为零。

### 差距在哪

| 维度 | 差距 | 严重性 |
|------|------|--------|
| **UX / 非 CLI 用户体验** | 商业 SaaS（Sudowrite/Novelcrafter）的富文本编辑器 + inline 建议 UX 远超 `/ink-dashboard` | **中高**。CLI 限制了用户池 |
| **跨书知识继承** | Sudowrite Series Folder 已成熟，ink-writer 是单项目孤岛 | 中。US-Serial（未立项）可补 |
| **进展追踪（Progressions）** | Novelcrafter 把时间轴状态变化产品化，ink-writer 只有伏笔/线索层 | 中。可并入 thread-lifecycle |
| **社区生态 / 插件市场** | Sudowrite 1000+ 社区插件；ink-writer skills 是自家维护 | 低中。GPL-3 开源已铺基础 |
| **协作 / 多用户** | Novelcrafter 有 team sharing；ink-writer 纯单机 | 低。个人创作工具本就单机 |

### 一句话定位

> **ink-writer 是全球唯一把"起点/番茄编辑审核规则"作为硬约束嵌入全链路的 AI 网文写作工具，在"中文长篇商业连载 + 自动化 + 硬门禁质检"这个交叉赛道构成了无直接对手的产品矩阵。**

---

## 参考来源（Sources）

- [Sudowrite 官网及博客](https://sudowrite.com/)
- [Sudowrite Best AI Creative Writing 2026](https://sudowrite.com/blog/best-ai-for-creative-writing-in-2026-tested-compared/)
- [Novelcrafter Features](https://www.novelcrafter.com/features)
- [Novelcrafter Codex](https://www.novelcrafter.com/features/codex)
- [NovelAI Documentation - Lorebook](https://docs.novelai.net/en/text/lorebook/)
- [NovelAI Lorebook Mastery](https://www.toolify.ai/ai-news/novelai-lorebook-mastery-unlock-ai-storytelling-potential-3810203)
- [AI Dungeon Memory System](https://help.aidungeon.com/faq/the-memory-system)
- [AI Dungeon World Info Research](https://github.com/valahraban/AID-World-Info-research-sheet/blob/main/AID%20WI%20Research%20Sheet.md)
- [Dramatron - DeepMind GitHub](https://github.com/google-deepmind/dramatron)
- [Co-Writing Screenplays and Theatre Scripts with Language Models - arXiv](https://arxiv.org/abs/2209.14958)
- [Wordcraft: Story Writing With Large Language Models - ACM](https://dl.acm.org/doi/fullHtml/10.1145/3490099.3511105)
- [Wordcraft Writers Workshop](https://magenta.withgoogle.com/wordcraft-writers-workshop)
- [Wordcraft Paper - arXiv](https://arxiv.org/abs/2107.07430)
- [LibriScribe - GitHub](https://github.com/guerra2fernando/libriscribe)
- [AI_NovelGenerator - GitHub](https://github.com/YILING0013/AI_NovelGenerator)
- [NovelForge - GitHub](https://github.com/RhythmicWave/NovelForge)
- [AutoNovel - NousResearch GitHub](https://github.com/NousResearch/autonovel)
- [AI_Gen_Novel - GitHub](https://github.com/cjyyx/AI_Gen_Novel)
- [AI-Writer (BlinkDL) - GitHub](https://github.com/BlinkDL/AI-Writer)
- [Best AI for Writing Fiction 2026: 11 Tools Tested](https://blog.mylifenote.ai/the-11-best-ai-tools-for-writing-fiction-in-2026/)
