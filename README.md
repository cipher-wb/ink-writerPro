# Ink Writer Pro

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-11.5.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple.svg)](https://claude.ai/claude-code)
[![Gemini CLI](https://img.shields.io/badge/Gemini%20CLI-Extension-4285F4.svg)](https://github.com/google-gemini/gemini-cli)
[![Codex CLI](https://img.shields.io/badge/Codex%20CLI-Skills-74AA9C.svg)](https://github.com/openai/codex)
[![Agents](https://img.shields.io/badge/Agents-14%E4%B8%AA-orange.svg)](#十四位-agent-协作)
[![Tables](https://img.shields.io/badge/SQLite-30%2B%E5%BC%A0%E8%A1%A8-blue.svg)](#记忆系统)

> **一条指令，自动写书、自动审查、自动修复、自动规划。**
>
> 14 个 AI Agent 组成的工业级网文写作流水线。

---

## 核心能力

将"写一本百万字长篇网文"这件工程量巨大的事，变成可自动化的工业流程。

你提供大纲和设定，14 个 Agent 协作完成从初稿到终稿的全部工作：

- **writer-agent**：正文起草（每章 2200+ 字，内置场景技法和风格锚定）
- **polish-agent**：质量修复（审查问题修复 + 反 AI 味处理）
- **context-agent**：上下文构建（11 板块创作执行包，含技法注入和 RAG 检索）
- **data-agent**：数据回写（实体提取、伏笔追踪、角色演化、向量索引）
- **10 个审查 Agent**：从设定一致性到追读力的 10 维度并行审查

每写一章，自动执行完整的 9 步流水线。

---

## AI 写长篇的三大痛点与解决方案

| 痛点 | 表现 | 解决方案 |
|------|------|---------|
| **记忆不足** | 写到第 50 章忘了角色设定 | 30+ 张 SQLite 表 + RAG 向量检索 + 卷级 mega-summary，确保长线记忆一致 |
| **质量不稳** | 人设崩塌、剧情流水账 | 10 个 Checker 并行审查 + 计算型闸门 + 自动修复闭环 |
| **风格偏 AI** | 句式单调、缺乏情感 | 117 本起点标杆分析 + 3295 个风格片段 + 场景技法索引（34 条可执行原则） |

> Powered by 编辑星河 wisdom (local RAG) — 288 份金牌编辑建议结构化为本地知识库，作为硬约束融入全链路。

---

## 安装

支持三种平台：**Claude Code**（推荐）、**Gemini CLI**、**Codex CLI**。

### 前提条件

- **Python 3.12+**
- 下面三个 CLI 平台选一个

### Claude Code（推荐）

```bash
# 1. 安装插件
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 启用
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 安装依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

验证：打开 Claude Code，输入 `/ink-init`，看到引导界面即安装成功。

### Gemini CLI

```bash
# 1. 克隆仓库
cd /path/to/ink-writerPro

# 2. 安装扩展
gemini extensions install .

# 3. 安装依赖
pip install -r requirements.txt
```

> Gemini CLI 不支持 Agent 并发，审查步骤串行执行。

### Codex CLI

```bash
# 1. 克隆
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer

# 2. 链接 Skills
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer

# 3. 安装依赖
pip install -r ~/.codex/ink-writer/requirements.txt

# 4. 环境变量（加到 .bashrc / .zshrc）
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"
```

### 可选依赖

```bash
pip install jieba    # 中文分词，提升 RAG 检索精度
```

### RAG 配置（必填）

v11.0 起，RAG 向量检索为**必填项**。写作前必须配置 Embedding API：

```bash
# 方式1：智谱 AI（推荐，免费额度充足）
cat >> ~/.claude/ink-writer/.env << 'EOF'
EMBED_BASE_URL=https://open.bigmodel.cn/api/paas/v4/embeddings
EMBED_MODEL=embedding-3
EMBED_API_KEY=你的智谱API密钥
EOF

# 方式2：OpenAI
cat >> ~/.claude/ink-writer/.env << 'EOF'
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=你的OpenAI密钥
EOF

# 方式3：本地部署（Ollama/vLLM）
cat >> ~/.claude/ink-writer/.env << 'EOF'
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_MODEL=nomic-embed-text
EMBED_API_KEY=placeholder
EOF
```

未配置时，`preflight` 阶段会阻断写作并提示配置方法。详见 [RAG 使用指南](ink-writer/references/shared/rag-guide.md)。

### 平台对比

| 功能 | Claude Code | Gemini CLI | Codex CLI |
|------|:-----------:|:----------:|:---------:|
| 14 个 Skills | 全部可用 | 全部可用 | 全部可用 |
| Agent 并发 | 原生支持 | 不支持 | spawn_agent |
| 10 Agent 审查 | 并发执行 | 串行执行 | 并发执行 |
| RAG 检索 | 支持 | 支持 | 支持 |
| Dashboard | 支持 | 支持 | 支持 |

---

## 快速上手

### 核心命令

```bash
/ink-auto 5     # 自动写 5 章 + 审查 + 修复
/ink-auto 20    # 写 20 章，触发深度质量检查
/ink-auto 100   # 写 100 章，全自动含检查点
```

这一条命令完成：写作、审查、修复、大纲生成。90% 的时间只需要 `/ink-auto`。

### 全部命令

| 命令 | 用途 | 使用频率 |
|------|------|---------|
| `/ink-init` | 创建项目（交互式采集设定） | 一次 |
| `/ink-auto N` | **主力命令**：写 N 章 + 自动审查修复 + 自动规划 | 每天 |
| `/ink-resume` | 中断恢复（从断点继续） | 偶尔 |
| `/ink-plan N` | 手动规划第 N 卷大纲 | 按需 |
| `/ink-write` | 手动写一章（完整 9 步流水线） | 按需 |
| `/ink-review 1-5` | 手动审查第 1-5 章 | 按需 |
| `/ink-audit` | 数据一致性审计 | 按需 |
| `/ink-macro-review` | 跨 50/200 章宏观结构分析 | 按需 |
| `/ink-fix` | 自动修复审查/审计发现的问题 | 由 ink-auto 自动调用 |
| `/ink-resolve` | 处理低置信度实体消歧（需人工确认） | 偶尔 |
| `/ink-query` | 查询角色/伏笔/关系状态 | 按需 |
| `/ink-learn` | 提取成功写作模式 | 按需 |
| `/ink-dashboard` | 启动可视化管理面板 | 按需 |
| `/ink-migrate` | 旧版项目迁移到 v9.0+ 架构 | 一次 |

### 从零到出文

```bash
# 1. 创建项目（交互式采集书名/题材/角色/世界观/金手指）
/ink-init

# 2. 规划第 1 卷大纲（节拍表 + 时间线 + 章纲）
/ink-plan 1

# 3. 开始写作（自动写 20 章 + 审查 + 修复）
/ink-auto 20

# 4. 日常循环
# 每天：/ink-auto 5~10  → 产出 1~2 万字
# 每周：看一眼审查报告  → 问题已自动修复
# 偶尔：/ink-resolve    → 处理消歧积压
```

---

## 9 步写作流水线

每章自动执行以下流程：

```
Step 0     环境预检 + 金丝雀健康扫描
Step 1     上下文构建（11 板块创作执行包 + RAG 检索 + 场景技法注入）
Step 2A    正文起草（2200+ 字，消费执行包 + 风格参考样本）
Step 2A.5  字数校验 + 编码校验（硬门控）
Step 2B    风格适配（表达层优化，不改剧情事实）
Step 2C    计算型闸门（确定性检查，零 LLM 成本）
Step 3     10 Agent 并行审查（设定/连贯/人设/AI味/追读力/爽点/节奏/文笔/开篇/读者模拟）
Step 4     润色修复 + 反 AI 味 + 改写安全校验
Step 5     Data Agent 回写（实体/伏笔/角色演化/向量索引/摘要）
Step 6     Git 备份
```

---

## 14 个 Agent

### 核心 Agent

| Agent | 职责 | 核心能力 |
|-------|------|---------|
| **writer-agent** | 正文起草 | 5 大铁律 + 场景技法索引 + 风格参考样本 + 情感深度自检 |
| **polish-agent** | 润色修复 | 严重度分级修复 + AI 味定向修复 + 毒点规避 |
| **context-agent** | 上下文构建 | Token 动态预算 v3 + RAG 检索 + 11 板块执行包 |
| **data-agent** | 数据回写 | 实体提取 + 伏笔追踪 + 角色状态更新 + 向量嵌入 |

### 审查 Agent（10 个）

| Agent | 检查维度 |
|-------|---------|
| **consistency-checker** | 设定/战力/地点/时间线/承诺一致性 + 知识边界 + 伏笔逾期 |
| **continuity-checker** | 逻辑连贯/因果链/承接关系 |
| **ooc-checker** | 角色性格/对话风格/决策一致性 |
| **anti-detection-checker** | 8 层检测：开头模式/句长/信息密度/因果链/对话存在性/段落/情感标点/视角 |
| **reader-pull-checker** | 追读力硬约束 + 软建议 + 前 500 字冲突检测 |
| **high-point-checker** | 爽点密度（8 种模式 + 迪化误解 + 身份掉马） |
| **pacing-checker** | Strand Weave 三线平衡 + 紧凑度（事件密度/空转/独白比） |
| **proofreading-checker** | 修辞重复/段落结构/代称混乱 |
| **golden-three-checker** | 黄金三章专项审查 |
| **reader-simulator** | 7 维读者体验评分 |

---

## 记忆系统

```
.ink/
├── index.db        30+ 张 SQLite 表（实体/关系/伏笔/承诺/审查指标/时间线）
├── state.json      运行时状态（进度/主角状态/strand追踪）
├── vectors.db      RAG 向量数据库（语义检索）
├── summaries/      每章自动摘要 + 卷级 mega-summary
└── style_samples.db 风格样本库
```

**记忆能力**：
- 主角状态精确到境界层级、位置、情绪
- 配角 last_seen_chapter/location/goal/emotion 自动追踪
- 伏笔逾期自动提醒（>10 章 high, >20 章 critical）
- 最近 10 章 Strand 分布实时监控
- 叙事承诺（誓言/承诺/预言）全生命周期追踪
- 追读力债务（Override Contract）利息计算

---

## 智能检查点（ink-auto 核心）

`/ink-auto` 内置三层检查点，保障长篇写作质量：

| 频率 | 操作 | 耗时 |
|------|------|------|
| **每 5 章** | 质量审查（5 核心 Checker）+ 自动修复 | ~15min |
| **每 10 章** | + 数据健康审计 | +2min |
| **每 20 章** | + 深度结构分析（支线/弧光/冲突去重/承诺/风格漂移）| +25min |

检查点发现问题会**立即自动修复**。大纲缺失时**自动触发规划**。全程无需人工介入。

---

## v11.x 新特性

### v11.5: 跨章遗忘 bug 根因修复

针对长篇连载中反复出现的"跨章细节遗忘"、"信息重复揭露"、"角色首次见面矛盾"、"伏笔逾期误报"等一系列问题，定位并修复了三个**架构层级**的根本原因：

- **`previous_chapters` 窗口从 2 章扩大到 10 章**：`extract_chapter_context.py` 中的 `build_review_pack_payload` 和 `build_chapter_context_payload` 两处 `range(chapter_num - 2, chapter_num)` 的硬编码 2 章窗口，是 writer/checker 无法"记住"跨 3-10 章细节的根本原因。扩大到 10 章后，作者 AI 写新章时能看到前 10 章的完整摘要+片段，大幅缓解"老周第一次开口 3 章重复"、"账本重复揭露同一情报"、"物资数字跨章漂移"、"裴衡首次见面矛盾"等一系列跨章 bug。
- **`plot_thread_registry.target_payoff_chapter` 空值兜底修复**：`sql_state_manager.py:583` 的 `int(item.get("target_payoff_chapter") or 0)` 会把 `None` 强制转成 `0`，导致 audit 查询把所有"未设目标章节"的活跃伏笔误判为"已逾期"（在长篇项目中可达 80+ 条假阳性）。改为 None-safe 兜底后，audit 结果回归真实数字。
- **SQL schema 与 Pydantic 对齐**：`index_manager.py` 的 `plot_thread_registry` 表中 `target_payoff_chapter` / `resolved_chapter` 从 `INTEGER DEFAULT 0` 改为 `INTEGER`（无默认值），与 Pydantic 模型 `Optional[int] = None` 对齐。避免 data-agent 写入时即使传 None 也被 schema 默认值覆盖成 0。

这三个修复对所有使用 ink-writer 的长篇项目都有显著价值——特别是已写到 50+ 章的项目。旧项目升级后建议跑一次 `ink db rebuild` 应用新 schema，然后对历史章节用 data-agent 重新 ingest 刷新元数据。

### v11.2: 工程深度审查修复

基于全项目工程审查报告，修复了 P0/P1 级别的逻辑漏洞：

- **计算型闸门实装**：角色冲突检测（已死亡/已离场角色自动拦截）、战力检测（禁用技能/已失去物品使用拦截）、对话占比分层告警（<5% hard / 5-15% soft / 15-25% info）
- **远距离记忆注入**：chapter > 50 时自动加载历史卷 mega-summary，解决长篇"记忆黑洞"
- **跨卷记忆压缩**：`ink memory auto-compress` 子命令 + ink-auto 自动检测并提示
- **SQLite 并发保护**：busy_timeout 5s + FileLock 保护 vectors.db + 写事务 BEGIN IMMEDIATE + 重试机制
- **Token 预算硬上限**：超限时按优先级裁剪（alerts → preferences → memory → story_skeleton → global）
- **审查闸门强化**：黄金三章硬拦截（回退重写而非润色）、反 AI 开头 critical 纳入总分 cap 60、读者体验 rewrite 阻断
- **元数据泄漏检测修正**：从 pass 改为 fail，确保元数据不漏入正文
- **完结标记 CLI 化**：`update-state --mark-completed` 替代内联 Python

### v11.0: 写作技法深度集成

**核心改进**：从"告诉 AI 不要做什么"（约束驱动）升级为"教 AI 怎么写"（技法驱动）。

- **scene-craft-index.md**：7 种场景类型的可执行技法清单（204 行），每种场景有必做/禁止/范例
- **8 个 craft_lessons**：情感/对话/战斗/开篇/节奏/共鸣/角色/沉浸，共 1073 行写作技法
- **writer-agent 情感深度自检**：6 条自检清单（身体反应/小物件/潜台词/沉默/不完美/环境共振）
- **context-agent 技法注入**：根据场景类型自动注入对应技法清单到创作执行包

### Style RAG 风格参考库

基于 117 本起点标杆小说构建的风格参考数据库：

- **3295 个高质量片段**，按 genre x scene_type x emotion 三维索引
- 写作时自动检索同题材同场景的标杆片段注入执行包
- 风格指标均值：句长 27.4 字、对话 24.4%、感叹号 3.9/千字（接近标杆）

### RAG 向量检索必填

v11.0 起，Embedding API 为必填配置。preflight 阶段实际调用 API 验证连通性，不通则阻断写作。

三层检索策略：向量+BM25 混合检索 → Rerank 精排 → 图谱增强（可选）。

### 统计层质量修复

基于 112 本标杆小说的数据化对比，修复了 6 项严重偏差：

| 指标 | 修复前 | 标杆值 | 修复方案 |
|------|--------|--------|---------|
| 句长均值 | 12.4 字 | 28.6 字 | 检测阈值反转，检测碎片化而非均匀化 |
| 短句占比 | 47.8% | 13.4% | 强制合并连续短句 |
| 对话占比 | 0% | 34.5% | 新增对话存在性检测（0%=critical） |
| 感叹号密度 | 0.24/千字 | 3.80/千字 | 新增情感标点密度检测 |
| 省略号密度 | 0.95/千字 | 2.83/千字 | 同上 |
| 开头模式 | "第N天"开头 | 行动/对话/感官切入 | 时间标记开头=critical |

### 记忆系统升级

- Token 预算 v3：长线期 11K→13K，角色交叉引用加分
- 卷级 mega-summary：ch>50 时自动压缩远距离摘要
- 角色状态追踪：last_seen/location/goal/emotion 全量更新
- 伏笔主动提醒：逾期伏笔执行包顶部红色警告

---

## 标杆分析系统

```
benchmark/
├── scraper.py            # 起点爬虫（断点续爬）
├── stat_analyzer.py      # 统计分析引擎
├── craft_analyzer.py     # LLM Craft 分析框架
├── style_rag_builder.py  # Style RAG 数据库构建
├── compare.py            # ink-writer vs 标杆差距报告
├── style_rag.db          # 3295 个风格片段数据库
├── corpus_index.json     # 117 本标杆小说索引
├── craft_lessons/        # 8 个 Craft 分析文件（34 条可复用原则）
│   ├── emotion_craft.md
│   ├── dialogue_craft.md
│   ├── combat_craft.md
│   ├── opening_patterns.md
│   ├── pacing_craft.md
│   ├── empathy_craft.md    ← v11.0
│   ├── character_craft.md  ← v11.0
│   └── immersion_craft.md  ← v11.0
└── gap_analysis.md
```

---

## 架构总览

```
                        ┌─────────────┐
                        │    用户     │
                        └──────┬──────┘
                               │ /ink-auto
                        ┌──────▼──────┐
                        │  ink-auto   │  ← 全自动调度 + 智能检查点
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ context  │    │  writer  │    │  polish  │
        │  agent   │    │  agent   │    │  agent   │
        └──────────┘    └──────────┘    └──────────┘
                               │
                        ┌──────▼──────┐
                        │  10 个审查  │
                        │   Agent    │
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ data-agent  │
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ index.db │    │state.json│    │vectors.db│
        │  30+ 表  │    │ 运行状态 │    │ RAG 向量 │
        └──────────┘    └──────────┘    └──────────┘
```

---

## 常见问题

**Q: 写到 300 章会不会忘了前面的事？**
A: 30+ 张表记录所有状态。伏笔逾期自动报警，配角出场自动加载状态。卷级 mega-summary 确保远距离记忆不丢失。

**Q: `/ink-auto 100` 会崩吗？**
A: 每 5 章自检，每 20 章深度检查，大纲缺失自动生成。某一章写崩了前面全部保留，用 `/ink-resume` 从断点继续。

**Q: 支持什么题材？**
A: 38 种模板：修仙/玄幻/都市/末世/言情/悬疑/规则怪谈/系统流/电竞/直播/克苏鲁/历史穿越等。

**Q: 能过 AI 检测吗？**
A: 8 层反 AI 检测 + 117 本标杆统计校准 + 场景技法索引，从源头写出符合人类写作特征的文字。

**Q: 检查点开销大吗？**
A: 100 章写作中，检查点总开销约 7 小时，占总时间 7-14%。

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v11.5.0 (当前)** | 跨章遗忘 bug 根因修复：**previous_chapters 窗口 2→10 章**（`extract_chapter_context.py` 两处硬编码）+ **plot_thread target_payoff_chapter 空值兜底从 `or 0` 改为 None-safe**（`sql_state_manager.py`，修复 audit 把未设目标伏笔误判逾期的系统性 bug）+ **SQL schema 与 Pydantic 对齐**（`index_manager.py` 的 target_payoff_chapter/resolved_chapter 从 DEFAULT 0 改为 NULL）。三个修复对长篇连载（50+ 章）项目有显著价值。 |
| v11.4.0 | 写作质量提升+LLM创造力增强：TTR词汇多样性检测 + 首句钩子检测 + 伏笔分级(10/20/30章) + 闸门阈值对齐 + 摘要窗口扩大(3→5) + 关键章摘要常驻 + 角色语言指纹(voice_fingerprint) + 微观意外感注入(Anti-Cliché) + 反套路检测 + 过渡章豁免收紧 + 简介质检 + 风格采纳度验证 + 13项计算检查(1095测试) |
| v11.3.0 | 工程深度审查全量修复(22项)：计算型闸门SQL对齐真实Schema + 死亡/离场/能力状态标准化 + mega-summary自动生成 + 伏笔数据源统一 + _write_transaction接入9个mixin + Step3 Harness闸门 + 黄金三章契约检查 + 风格样本fallback + 对话「」支持 + 句长/标点检查 + 元数据全文扫描 + Token裁剪通知 + chapters_per_volume配置化 + reader-pull始终执行 + 29个新测试(1083总) |
| v11.2.0 | 计算型闸门实装 + 远距离摘要注入 + 跨卷记忆压缩 + SQLite并发保护 + 黄金三章硬拦截 + Token预算硬上限 + 对话阈值分层 + 完结标记CLI化 |
| v11.1.0 | 计算型闸门框架 + 远距离摘要注入 + mega-summary自动触发 + Token预算硬上限 + 对话阈值分层 |
| v11.0.0 | 写作技法深度集成 + Style RAG 风格参考库(3295片段) + RAG必填 + 统计层6项修复 + 记忆系统升级 + 3个新craft分析 + P1/P2问题修复 |
| v10.5.0 | 爽点质量提升 + 完结检测 |
| v10.4.0 | 写作质量约束升级 |
| v10.3.0 | ink-fix 自动修复 + 编码校验 |
| v10.0.0 | 工程架构审查优化 |
| v9.18-19 | 112 本标杆分析 + Writer 重构 + 反 AI 内化 + 场景 Craft |
| v9.0.0 | Harness-First 架构：计算型闸门 + Reader Agent 升格 |
| v8.0.0 | 14 Agent 全规范化 + 风格锚定 + 批量恢复 |

---

## 文档

- [RAG 使用指南](ink-writer/references/shared/rag-guide.md)
- [质量升级开发文档](docs/quality-upgrade-dev-guide.md)
- [v9.0 升级指南](docs/v9-upgrade-guide.md)
- [架构与模块](docs/architecture.md)
- [命令详解](docs/commands.md)
- [38 种题材模板](docs/genres.md)
- [运维与恢复](docs/operations.md)

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。
