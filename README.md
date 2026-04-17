# Ink Writer Pro

[![Version](https://img.shields.io/badge/Version-13.7.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)

**一条命令，自动写 10 章并审查修复。** AI 驱动的长篇网文写作工具，专为起点/番茄等平台的商业连载设计。

---

## 功能亮点

- **一条命令批量产出**：`/ink-auto 10` 自动写 10 章，每章 2200+ 字，写完自动审查、自动修复、大纲不够自动生成
- **写 300 章不崩**：30+ 张数据表记录角色状态、伏笔、时间线，跨章语义检索确保前后一致
- **过 AI 检测**：基于 117 本起点标杆统计校准，8 层反 AI 检测 + 场景写作技法，从源头写出人类特征文字
- **288 条编辑建议内化**：起点金牌编辑的写作建议结构化为硬约束，不符合直接拦截重写
- **快速开书**：`/ink-init --quick` 一键生成 3 套完整方案（书名/角色/冲突/金手指），选一个直接开写
- **断点续写**：中途断了用 `/ink-resume` 从断点继续，已写章节一字不丢

---

## 安装

前提：**Python 3.12+**，以下三种平台选一个。

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
cd /path/to/ink-writerPro
gemini extensions install .
pip install -r requirements.txt
```

> Gemini CLI 审查步骤串行执行，速度较慢。

### Codex CLI

```bash
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer
pip install -r ~/.codex/ink-writer/requirements.txt
# 加到 .bashrc / .zshrc：
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"
```

### RAG 配置（推荐）

写作前配置 Embedding API 可启用语义检索，大幅提升长篇记忆一致性：

```bash
# ModelScope（免费）
echo "EMBED_API_KEY=你的ModelScope密钥" >> ~/.claude/ink-writer/.env

# 或 OpenAI
echo "EMBED_BASE_URL=https://api.openai.com/v1" >> ~/.claude/ink-writer/.env
echo "EMBED_MODEL=text-embedding-3-small" >> ~/.claude/ink-writer/.env
echo "EMBED_API_KEY=你的OpenAI密钥" >> ~/.claude/ink-writer/.env
```

不配置也能写，系统自动使用 BM25 关键词检索（精度略低但完全可用）。

---

## 快速上手

### 方式一：快速模式（推荐新手）

```bash
# 1. 一键生成 3 套小说方案
/ink-init --quick

# 2. 选一个方案（输入 1/2/3），或混搭（如「1的书名+2的主角」）
# 3. 系统自动创建项目、填充设定

# 4. 规划第 1 卷大纲
/ink-plan 1

# 5. 开始写作
/ink-auto 20    # 自动写 20 章 + 审查 + 修复
```

### 方式二：深度模式（完全掌控）

```bash
# 1. 交互式采集（书名/题材/角色/世界观/金手指/创意约束）
/ink-init

# 2. 规划大纲
/ink-plan 1

# 3. 写作
/ink-auto 20
```

### 日常工作流

```bash
/ink-auto 5~10          # 每天产出 1~2 万字
# 每 5 章自动审查修复，每 20 章深度结构分析
# 大纲写完自动生成下一卷，全程无需干预

/ink-resume             # 中断了从断点继续
/ink-resolve            # 偶尔处理消歧积压
```

---

## 命令速查

| 命令 | 说明 |
|------|------|
| `/ink-init` | 创建新项目（深度交互采集设定） |
| `/ink-init --quick` | 快速模式：生成 3 套方案，选一个直接开写 |
| `/ink-auto N` | **主力命令**：写 N 章 + 自动审查修复 + 自动规划 |
| `/ink-plan N` | 规划第 N 卷大纲 |
| `/ink-write` | 手动写一章（完整流水线） |
| `/ink-review 1-5` | 手动审查指定章节 |
| `/ink-resume` | 中断恢复，从断点继续 |
| `/ink-fix` | 自动修复审查发现的问题 |
| `/ink-audit` | 数据一致性审计 |
| `/ink-macro-review` | 跨 50/200 章宏观结构分析 |
| `/ink-query` | 查询角色/伏笔/关系状态 |
| `/ink-resolve` | 处理低置信度实体消歧 |
| `/ink-learn` | 提取成功写作模式 |
| `/ink-dashboard` | 启动可视化管理面板 |
| `/ink-migrate` | 旧版项目迁移到新架构 |

---

## FAQ

**Q: 写到 300 章会不会前后矛盾？**
A: 30+ 张表记录所有角色/伏笔/时间线状态，跨章语义检索自动召回相关上下文。伏笔超期自动报警，配角再出场自动加载历史状态。

**Q: `/ink-auto 100` 中途崩了怎么办？**
A: 每 5 章自检 + 每 20 章深度检查。某章写崩不影响已完成的章节，用 `/ink-resume` 从断点继续。

**Q: 支持什么题材？**
A: 38 种模板覆盖修仙、玄幻、都市、末世、言情、悬疑、规则怪谈、系统流、电竞、历史穿越等。

**Q: 能过起点审核吗？**
A: 8 层反 AI 检测 + 117 本标杆统计校准 + 288 条编辑建议硬约束 + 场景写作技法，从句式、结构、风格多层面接近人类写作。

**Q: 检查点会不会很慢？**
A: 100 章总检查点开销约 7 小时，占总时间 7-14%。每 5 章检查约 15 分钟，不影响整体效率。

**Q: 不配置 RAG 能用吗？**
A: 能用。系统自动 fallback 到 BM25 关键词检索，精度略低但完全可用。推荐配置 Embedding API 以获得最佳效果。

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v13.7.0 (当前)** | 文笔沉浸感架构 — 电影镜头切换/感官轮换/信息密度/环境情绪共振四大法则 + prose-impact/sensory-immersion/flow-naturalness 3 个新 checker + polish Layer 9 兜底 + 24 条新文笔规则（EW-0365~0388）+ 第一章 4 项爽点硬阻断 |
| **v13.6.0** | 爽点密集化与主线加速架构级改造：大纲层爽点密度/前置原则/第1章闭环，正文层L7-L10四条新铁律，审查层卖点密度/摄像头检测/OOC本能违反/文笔工艺质量，润色层文笔工艺兜底 |
| **v13.5.0** | Narrative Coherence Engine：否定约束管线（Data→Context→Writer→Checker全链路）、场景退出快照、Writer自洽回扫(Step 2A.1)、角色连续性📌预警、O7否定约束违反检测、L9枚举完整性检测。从根源杜绝凭空编造和章内矛盾 |
| **v13.4.0** | Token & Time 优化：审查包按checker瘦身(-30% Step3)、logic计算型预检、Step 2B条件降级、Context空值裁剪、Data-Agent纯JSON输出、Prompt结构cache优化。目标30min→20min，token整体-35%，质量零下降（内置验证脚本） |
| **v13.3.0** | 字数上限收紧（4000字硬上限）+ 双层进度条（内层12步骤/外层章节级 + 检查点子步骤追踪） |
| **v13.2.0** | **Logic Fortress 逻辑防崩体系**：新增 MCC 强制合规清单、logic-checker（8层章内微观逻辑验证）、outline-compliance-checker（6层大纲合规验证），Writer-Agent 5条逻辑铁律 + MCC自检机制，Step 3 硬阻断门禁，两层防线消除大纲偏离和章内逻辑矛盾 |
| v13.1.0 | **效率优化与项目瘦身**：ink-init --quick 快速随机模式、防重复角色命名系统、项目文件清理、README 面向用户重写 |
| v13.0.0 | **Deep Review & Perfection**：27 US / 6 Phase 端到端优化。追读力+爽点调度器+情绪心电图+Style RAG+句式多样性硬门禁+SQLite记忆图谱+伏笔/明暗线生命周期追踪+人物语气指纹+双agent目录消除+章节并发+prompt cache |
| v12.0.0 | **编辑星河写作智慧集成**：288份编辑建议→364条原子规则→FAISS向量索引，editor-wisdom-checker + 硬门禁闭环 |
| v11.5.0 | 跨章遗忘bug根因修复：previous_chapters窗口扩展+伏笔空值兜底+SQL schema对齐 |
| v11.4.0 | 写作质量提升：TTR词汇多样性+首句钩子+伏笔分级+角色语气指纹+微观意外感+反套路检测 |
| v11.3.0 | 工程深度审查全量修复(22项)：计算型闸门+死亡状态标准化+mega-summary+伏笔统一+黄金三章契约 |
| v11.0.0 | Style RAG风格参考库(3295片段)+统计层修复+记忆系统升级 |
| v9.0.0 | Harness-First 架构：计算型闸门 + Reader Agent 升格 |
| v8.0.0 | 14 Agent 全规范化 + 风格锚定 + 批量恢复 |

---

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。
