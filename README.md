# Ink Writer Pro

[![Version](https://img.shields.io/badge/Version-13.1.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
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

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。
