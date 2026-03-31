# Ink Writer Pro

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-8.0.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple.svg)](https://claude.ai/claude-code)
[![Gemini CLI](https://img.shields.io/badge/Gemini%20CLI-Extension-4285F4.svg)](https://github.com/google-gemini/gemini-cli)
[![Codex CLI](https://img.shields.io/badge/Codex%20CLI-Skills-74AA9C.svg)](https://github.com/openai/codex)
[![Agents](https://img.shields.io/badge/Agents-14%E4%B8%AA-orange.svg)](#agent-天团14-位卷王为你打工)
[![Tables](https://img.shields.io/badge/SQLite-25%E5%BC%A0%E8%A1%A8-blue.svg)](#数据层一个比你还操心的记忆系统)

> **让 AI 帮你写网文，然后再派 14 个 AI 审查它写得像不像人。**
>
> 没错，这就是用魔法打败魔法。

---

## 这玩意儿是干啥的

一句话：**把"我要写一本 200 万字的网文"这件令人秃头的事情，变成流水线作业。**

你负责提供大纲和设定，剩下的交给 14 个 Agent 组成的血汗工厂：

- 1 个负责搬砖写正文（writer-agent，最惨的那个）
- 1 个负责给正文化妆（polish-agent，审美在线的那个）
- 1 个负责构建上下文（context-agent，记性最好的那个）
- 1 个负责记账入库（data-agent，最像打工人的那个）
- **10 个负责挑毛病**（对，写 1 个人的活要 10 个人来审）

每写一章，自动执行 9 步流水线：构建上下文 → 写正文 → 字数校验 → 风格适配 → 10 Agent 审查 → 润色去 AI 味 → 安全校验 → 数据回写 → Git 备份。

比你上班还卷。

---

## 为什么需要这么复杂

因为 AI 写长篇有三个致命问题：

| 问题 | 人话翻译 | 我们的解法 |
|------|---------|-----------|
| **记忆丧失** | 写到第 50 章忘了第 3 章女主叫啥 | 25 张 SQLite 表 + RAG 向量检索，比大象还能记 |
| **人设崩塌** | 高冷男主突然变成话痨暖男 | OOC 检查器 + 角色演化账本 + 语言档案，崩一个抓一个 |
| **AI 味太浓** | "他非常愤怒，内心五味杂陈" | 6 层反检测 + 200 词 AI 高频词库 + 句长突发度控制，写完连朱雀都认不出 |

---

## 安装（3 步，比泡面还简单）

支持三个平台：**Claude Code**（推荐，完整体验）、**Gemini CLI**、**Codex CLI**。

### 你需要先有

- **Python 3.10+** — [装这个](https://www.python.org/downloads/)
- 以及下面三个 CLI 任选其一（或全都要）

### 方式一：Claude Code（推荐，完整体验）

```bash
# 1. 加插件源
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 装插件
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 装 Python 依赖
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

Windows 同上，去掉 `--scope user`。

验证：打开 Claude Code，输入 `/ink-init`。看到引导界面 = 装好了。

### 方式二：Gemini CLI

```bash
# 1. 安装扩展
cd /path/to/ink-writerPro   # 克隆本仓库
gemini extensions install .

# 2. 装 Python 依赖
pip install -r requirements.txt
```

Gemini CLI 通过 `gemini-extension.json` 自动发现扩展，加载 `GEMINI.md` 作为上下文。

> **限制**：Gemini CLI 不支持子 Agent，审查步骤串行执行。详见 `ink-writer/references/gemini-tools.md`。

### 方式三：Codex CLI

```bash
# 1. 克隆到 Codex 目录
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer

# 2. 创建 skills 符号链接
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer

# 3. 装 Python 依赖
pip install -r ~/.codex/ink-writer/requirements.txt

# 4. 设置环境变量（加到 .bashrc / .zshrc）
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"

# 5. 重启 Codex CLI
```

需要子 Agent 支持时，在 `~/.codex/config.toml` 中添加 `[features] multi_agent = true`。

详细说明见 `.codex/INSTALL.md`。

### 可选加装：jieba 分词（推荐）

```bash
pip install jieba
```

装了 jieba 后 BM25 检索精度大幅提升（"萧炎"作为整词匹配 vs 拆成"萧"+"炎"两个字盲猜）。不装也行，系统自动回退到基础模式，不影响任何功能。

### 平台功能对比

| 功能 | Claude Code | Gemini CLI | Codex CLI |
|------|:-----------:|:----------:|:---------:|
| 12 个 Skills | 全部 | 全部 | 全部 |
| 子 Agent 并发 | 原生支持 | 不支持（串行） | spawn_agent |
| 10 Agent 审查 | 并发 | 串行 | 并发 |
| 风格锚定 | 支持 | 支持 | 支持 |
| RAG 检索 | 支持 | 支持 | 支持 |
| Dashboard | 支持 | 支持 | 支持 |

---

## 怎么用（命令速查）

```bash
/ink-init              # 开局：创建小说项目，交互式填设定
/ink-plan 1            # 规划：生成第 1 卷详细大纲
/ink-write             # 写一章：完整 9 步流水线，2200 字起步
/ink-5                 # 日常主力：连写 5 章 + Full 审查 + 自动修复（摸鱼神器）
/ink-auto 5            # 无人值守：每章独立会话，自动清上下文（小模型神器）
/ink-review 1-5        # 审查：让 10 个 Agent 围殴你的第 1-5 章
/ink-query             # 查状态：角色在哪？伏笔埋了几个？节奏歪没歪？
/ink-audit             # 体检：数据对账，检测 state.json 和 index.db 有没有打架
/ink-macro-review      # 宏观审查：每 50/200 章来一次全面复盘
/ink-resolve           # 消歧：处理 Data Agent 拿不准的实体
/ink-resume            # 续命：中断了？从断点恢复，不用从头来
/ink-dashboard         # 看板：只读可视化，适合发呆时盯着看
```

### /ink-5 vs /ink-auto — 怎么选？

| | `/ink-5` | `/ink-auto` |
|--|----------|-------------|
| **上下文** | 同一会话，共享上下文 | 每章独立会话，自动清理 |
| **适合** | 大上下文模型（1M+） | 小上下文模型（200k） |
| **审查** | 5 章写完后统一 Full 审查 | 每章内置 Step 3 审查 |
| **速度** | 更快（无进程启动开销） | 略慢（每章重启 CLI） |
| **用法** | `/ink-5`（交互模式） | `ink-auto 5`（终端）或 `/ink-auto 5`（交互） |

简单记：**模型上下文够用选 `/ink-5`，不够用选 `/ink-auto`。**

也可以终端直接运行（不需要进入 AI 会话）：
```bash
cd /你的小说项目目录
ink-auto 10        # 写 10 章，去睡觉
```

### 日常工作流（推荐）

```
早上：/ink-5 或 ink-auto 5  → 5 章自动写完，你去喝咖啡
中午：看审查报告             → 有 critical 就让它自动修，没有就继续喝
下午：/ink-5 或 ink-auto 5  → 又 5 章，今天产出 1 万字
晚上：/ink-query             → 检查一下伏笔和节奏，安心睡觉
周末：/ink-macro-review      → 50 章里程碑审查，确保没跑偏
```

---

## 写作流水线（每章 9 步，比驾考还严）

```
Step 0     预检 + 金丝雀扫描 + 权限卡     "先体检再上班"
Step 1     上下文构建（8 个板块）          "把前情提要背一遍"
Step 2A    正文起草（≥2200 字硬下限）      "开始搬砖"
Step 2A.5  字数校验                       "不够 2200 字？回去加班"
Step 2B    风格适配                       "把翻译腔改成网文腔"
Step 3     10 Agent 审查                  "10 个领导轮流审批"
Step 4     润色 + Anti-AI 去味             "把'他非常愤怒'改成'他指节捏得发白'"
Step 4.5   改写安全校验 + 情感差分         "检查润色有没有把剧情改崩"
Step 5     Data Agent 回写 + Mini-Audit    "写进档案，永久记录"
Step 6     Git 备份                       "存档，防猝死"
```

### 防幻觉三定律（铁律，违反直接毙稿）

| 定律 | 人话 |
|------|------|
| **大纲即法律** | 大纲说往东，你不能写往西 |
| **设定即物理** | 筑基期不能放金丹期的技能，物理学不答应 |
| **发明需识别** | 新角色/新地点可以写，但必须被 Data Agent 登记在册 |

---

## Agent 天团（14 位卷王为你打工）

### 核心创作组（4 位）

| Agent | 职责 | 口头禅 |
|-------|------|--------|
| **writer-agent** | Step 2A 正文起草 | "2200 字，一个字都不能少" |
| **polish-agent** | Step 4 润色去 AI 味 | "你这个'他非常愤怒'是认真的吗" |
| **context-agent** | Step 1 上下文构建 | "第 247 章埋的伏笔你还记得吗？我记得" |
| **data-agent** | Step 5 数据回写 | "又提取了 3 个实体，5 条状态变更，1 条潜台词" |

### 审查天团（10 位，专门找茬）

| Agent | 管什么 | 最狠的一刀 |
|-------|--------|-----------|
| **consistency-checker** | 设定一致性 | "筑基 3 层用金丹期技能？你在做梦" |
| **continuity-checker** | 连贯性 | "上章在天云宗，这章突然到了血煞秘境？瞬移吗？" |
| **ooc-checker** | 人物一致性 | "高冷男主突然撒娇？你确定不是被夺舍了？" |
| **anti-detection-checker** | AI 味检测 | "连续 6 句 18-22 字？人类不会这么写" |
| **reader-pull-checker** | 追读力 | "这章结尾读者凭什么点下一章？" |
| **high-point-checker** | 爽点密度 | "5 章了一个打脸都没有，读者要弃坑了" |
| **pacing-checker** | 节奏平衡 | "连续 7 章打打打，感情线呢？世界观呢？" |
| **proofreading-checker** | 文笔质量 | "同一个比喻用了 3 次，换一个行吗" |
| **golden-three-checker** | 黄金三章 | "前 300 字没有强触发？读者已经走了" |
| **reader-simulator** | 读者模拟 | "我模拟了一个修仙读者，他在第 600 字处开始走神" |

---

## 数据层（一个比你还操心的记忆系统）

```
index.db        25 张 SQLite 表，记住每一个角色、每一条伏笔、每一次境界突破
state.json      运行时状态缓存（正在向 index.db 迁移中，终极目标 < 2KB）
vectors.db      RAG 向量数据库，支持语义检索（"找到主角上次被打败的那一章"）
summaries/      每章自动生成摘要，供后续章节快速回忆
style_anchor    风格锚定指纹，防止第 1 章和第 500 章读起来像两个人写的
```

### 它能记住什么

- 萧炎现在是什么境界（精确到层）
- 李雪上次出场是第几章、说了什么话、当时什么心情
- 第 47 章埋的伏笔原定第 120 章回收，现在第 130 章了还没收 → 逾期警告
- 最近 10 章主线占比 85%，感情线断了 12 章 → 节奏失衡警告
- 你在第 200 章用 Override Contract 欠了一个微兑现的债，利息还在涨

---

## v8.0 有啥新东西

### Agent 规范化（再也不是无证上岗了）

- 新增 `writer-agent.md` 和 `polish-agent.md` — 两个最重要的 Agent 终于有了正式工牌
- 新增 `pipeline-dag.md` — 9 步流水线的依赖关系图，硬门控一目了然
- 14 个 Agent 全部通过严重度术语统一审查

### 检查能力增强（找茬水平 +50%）

- Anti-Detection 权重校准：POV 泄露权重 5% → 15%（这才是 AI 检测的命门）
- 叙事承诺违规检测：角色发过的誓、许过的诺，违反了就是 critical
- 前 3 章 proofreading + golden-three 并行启用（以前有覆盖盲区）
- 复合题材映射表（修仙+虐恋 取哪个容忍度？有答案了）

### 数据与上下文（记性更好了）

- 上下文预算分层：ch31-100 = 9000 token，ch101+ = 11000 token（以前一刀切 8000）
- BM25 分词升级：jieba 词级分词（"萧炎" 不再被拆成 "萧"+"炎"）
- Mini-Audit C.4：每章自动检查审查分数趋势，连续下降就报警

### 工业化能力（写 600 章不怕崩）

- 金丝雀增量模式：批量写作时跳过重复检查，提速 30%
- 批量失败处理：ink-5 写到第 3 章崩了？前 2 章保留不回滚
- ink-resume 批量恢复：A/B/C/D 四种恢复方案随你选
- 风格锚定：前 10 章算指纹，后续比对漂移（>2 标准差报警）
- 情感层增强：潜台词检测 + 润色后情感扁平化差分

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v8.0.0 (当前)** | 大版本升级：14 Agent 全规范化、34 项工业化优化、风格锚定、情感层、批量恢复、BM25 词级分词 |
| **v7.0.6** | BM25 分词升级：jieba 词级分词 + 自动回退 |
| **v7.0.5** | B3 架构优化：批量恢复、风格锚定、情感层 |
| **v7.0.4** | B2 中等优化：预算分层、伏笔优先级、Canary 增量 |
| **v7.0.3** | B1 速赢优化：权重校准、约束矩阵、质量示例 |
| **v7.0.2** | B0 规范预检：补全 Agent 定义、统一文档规范 |
| **v7.0.1** | 金丝雀健康扫描、里程碑强制审查 |

---

## RAG 配置（可选，不配也能用）

在项目根目录创建 `.env`，配上向量嵌入 API 就能启用语义检索：

```bash
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_key
```

不配 RAG 的话，系统用 BM25 关键词检索兜底。

---

## 架构总览

```
                        ┌─────────────┐
                        │   你（甲方）  │
                        └──────┬──────┘
                               │ /ink-write
                        ┌──────▼──────┐
                        │  ink-write   │  ← 流水线调度器
                        │  (9 Steps)   │
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ context  │    │  writer  │    │  polish  │
        │  agent   │    │  agent   │    │  agent   │
        │ "记性好" │    │ "搬砖的" │    │ "化妆师" │
        └──────────┘    └──────────┘    └──────────┘
                               │
                        ┌──────▼──────┐
                        │  Step 3     │
                        │ 10 Checkers │  ← "十人审判团"
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ data-agent  │  ← "记账的"
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ index.db │    │state.json│    │vectors.db│
        │  25 表   │    │ 运行缓存 │    │ RAG 向量 │
        └──────────┘    └──────────┘    └──────────┘
```

---

## 常见问题

**Q: 写出来的东西能过 AI 检测吗？**
A: 6 层反检测 + 200 词高频词库 + 源头防检测 + 定向去味 + 二次验证。工程极限已拉满。

**Q: 写到 300 章会不会忘了前面？**
A: 不会。25 张表记住一切，伏笔逾期自动报警，角色复出自动加载演化轨迹。

**Q: 写到 600 章呢？**
A: 上下文预算会有些紧张（15000 token 上限），但伏笔和时间约束永不截断。中期建议跑一次 state.json 迁移。

**Q: 可以写什么题材？**
A: 38 种题材模板：修仙/玄幻/都市/末世/言情/悬疑/规则怪谈/系统流/克苏鲁……

**Q: 写到一半崩了怎么办？**
A: `/ink-resume`。检测断点、展示选项、选择继续还是重来。批量崩了也能续。

---

## 文档

- [architecture.md](docs/architecture.md) — 架构与模块
- [commands.md](docs/commands.md) — 命令详解
- [rag-and-config.md](docs/rag-and-config.md) — RAG 配置
- [genres.md](docs/genres.md) — 38 种题材模板
- [operations.md](docs/operations.md) — 运维与恢复

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。

## 致谢

使用 Claude Code + Gemini CLI + Codex 配合 Vibe Coding 开发。

---

> *"我写网文的时候，有 14 个 AI 在背后盯着我。其中 10 个专门找茬。"*
>
> *—— 某不愿透露姓名的 ink-writer 用户*
