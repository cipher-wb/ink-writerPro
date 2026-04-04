# Ink Writer Pro

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-10.0.0-green.svg)](ink-writer/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple.svg)](https://claude.ai/claude-code)
[![Gemini CLI](https://img.shields.io/badge/Gemini%20CLI-Extension-4285F4.svg)](https://github.com/google-gemini/gemini-cli)
[![Codex CLI](https://img.shields.io/badge/Codex%20CLI-Skills-74AA9C.svg)](https://github.com/openai/codex)
[![Agents](https://img.shields.io/badge/Agents-14%E4%B8%AA-orange.svg)](#十四位技师为你服务)
[![Tables](https://img.shields.io/badge/SQLite-25%E5%BC%A0%E8%A1%A8-blue.svg)](#记忆系统比你前任还记仇)

> **一条指令，自动写书、自动审查、自动修复、自动规划——你只需要躺着。**
>
> 14 个 AI Agent 组成的全套服务，从头伺候到尾。

---

## 它能帮你做什么

把"我要写一本 200 万字的网文"这件令人窒息的事，变成一场无需动手的**全身服务**。

你只要提供大纲和设定——相当于脱好衣服躺上去——剩下的，14 个 Agent 会把你伺候得妥妥帖帖：

- 1 个负责用力写正文（writer-agent，干最多活的那个）
- 1 个负责精修抛光（polish-agent，让你每一寸都光滑的那个）
- 1 个负责前戏铺垫（context-agent，把前情摸得一清二楚）
- 1 个负责事后记录（data-agent，什么姿势用过都记着）
- **10 个负责挑逗你的敏感点**（审查天团，哪里不够爽都给你指出来）

每写一章，自动执行 9 步全套流程。比你想象的还要细致。

---

## 为什么要这么多花样

因为 AI 写长篇有三个**不行**：

| 毛病 | 症状 | 我们的手法 |
|------|------|-----------|
| **记忆不行** | 写到第 50 章忘了女主叫啥 | 25 张 SQLite 表 + RAG 向量检索，摸过的每一寸都记得 |
| **持久力不行** | 写着写着人设就软了 | OOC 检查器 + 角色声音区分度检测 + 角色演化账本，软一下立刻给你扶正 |
| **技巧不行** | "他非常愤怒，内心五味杂陈" | 112本起点标杆分析 + 内化风格原则 + 5类场景Craft指导，从源头写出有生命力的文字 |
| **不够商业** | 好文章没人看 | 10秒扫读测试 + 书名简介优化 + 前3万字里程碑约束，编辑一眼就想签 |

---

## 安装——脱衣服的过程

支持三种体位：**Claude Code**（正面，推荐）、**Gemini CLI**（侧面）、**Codex CLI**（背面）。

### 前提条件

- **Python 3.12+** — [先把这个穿上](https://www.python.org/downloads/)
- 以及下面三个 CLI 选一个带上（或者全都要，我们不介意）

### 体位一：Claude Code（正面全接触，推荐）

```bash
# 1. 接入
claude plugin marketplace add cipher-wb/ink-writerPro --scope user

# 2. 深入
claude plugin install ink-writer@ink-writer-marketplace --scope user

# 3. 润滑（装依赖）
pip install -r https://raw.githubusercontent.com/cipher-wb/ink-writerPro/HEAD/requirements.txt
```

验证：打开 Claude Code，输入 `/ink-init`。看到引导界面 = 进去了。

### 体位二：Gemini CLI（侧入）

```bash
# 1. 把仓库克隆下来
cd /path/to/ink-writerPro

# 2. 接入
gemini extensions install .

# 3. 润滑
pip install -r requirements.txt
```

> **注意**：Gemini 不支持多人运动（无子 Agent 并发），审查步骤只能排队一个个来。

### 体位三：Codex CLI（从后面来）

```bash
# 1. 克隆
git clone https://github.com/cipher-wb/ink-writerPro.git ~/.codex/ink-writer

# 2. 做好链接
mkdir -p ~/.agents/skills
ln -s ~/.codex/ink-writer/ink-writer/skills ~/.agents/skills/ink-writer

# 3. 润滑
pip install -r ~/.codex/ink-writer/requirements.txt

# 4. 环境配置（加到 .bashrc / .zshrc）
export CLAUDE_PLUGIN_ROOT="$HOME/.codex/ink-writer/ink-writer"

# 5. 重启
```

### 可选加装：jieba 分词（加点情趣用品）

```bash
pip install jieba
```

装了 jieba，检索快感提升 300%。"萧炎"作为整词精准命中，而不是被拆成"萧"+"炎"两个字瞎摸。不装也行，系统自动降级到基础模式。

### 三种体位对比

| 功能 | Claude Code | Gemini CLI | Codex CLI |
|------|:-----------:|:----------:|:---------:|
| 13 个 Skills | 全解锁 | 全解锁 | 全解锁 |
| 多人运动（Agent 并发） | 原生支持 | 不支持 | spawn_agent |
| 10 Agent 审查 | 并发高潮 | 排队等候 | 并发高潮 |
| 风格锚定 | ✅ | ✅ | ✅ |
| RAG 检索 | ✅ | ✅ | ✅ |
| Dashboard | ✅ | ✅ | ✅ |

---

## 怎么用——手把手教学

### 核心只有一条命令

**忘掉所有复杂的指令。你只需要记住一个：**

```bash
/ink-auto 5
```

这一条命令，自动写 5 章、自动审查、自动修复、自动生成大纲。从头爽到尾，中间不用你动一根手指。

想要更多？

```bash
/ink-auto 10     # 10 章，翻倍的快感
/ink-auto 20     # 20 章，触发一次深度高潮（全套深度审查）
/ink-auto 100    # 100 章，通宵服务，早上起来 20 万字已经躺好了
```

### 它在背后帮你做了什么

`/ink-auto` 不只是闷头写。它内置了**智能检查点**，每隔几章就帮你做一次全身检查：

| 频率 | 服务内容 | 时长 |
|------|---------|------|
| **每 5 章** | 质量审查（可读性、逻辑、伏笔、人物、追读力）+ 自动修复问题 | ~15min |
| **每 10 章** | + 数据健康检查（记忆系统有没有出错） | +2min |
| **每 20 章** | + 深度全身检查（支线健康、角色弧光、冲突去重、风格漂移）| +25min |

还有**自动大纲生成**：写到某一章发现大纲还没做？它会自己停下来，先帮你把那一卷的大纲做好，然后继续写。不需要你操心。

### 你只需要记住 4 个命令

| 命令 | 用途 | 使用频率 |
|------|------|---------|
| `/ink-init` | 创建项目——像第一次约会，交互式填写设定 | 一次 |
| `/ink-auto N` | **主力命令**——写 N 章 + 自动审查修复 + 自动规划 | 每天 |
| `/ink-resume` | 续命——中断了？从断点恢复 | 偶尔 |
| `/ink-migrate` | 迁移——旧项目升级到 v9.0 架构 | 一次 |

就这些。90% 的时间你只会用 `/ink-auto`。

### 高级命令（调试/精细控制）

<details>
<summary>展开查看全部高级命令</summary>

日常不需要这些。但如果你想手动介入某个环节：

```bash
# ═══ 手动写作 ═══
/ink-write             # 写一章：完整 9 步流水线，2200 字起步
/ink-plan 1            # 规划：生成第 1 卷详细大纲（节拍表+时间线+章纲）
/ink-plan 1            # 规划：重新生成第 1 卷详细大纲

# ═══ 手动审查 ═══
/ink-review 1-5        # 审查：10 个 Agent 仔细检查第 1-5 章
/ink-audit             # 数据对账：检查记忆系统有没有错乱
/ink-macro-review      # 宏观审查：支线、节奏、承诺的全面体检

# ═══ 数据维护 ═══
/ink-resolve           # 消歧：处理 AI 拿不准的实体（需要你亲自上手）
/ink-query             # 查状态：角色在哪？伏笔埋了几个？
/ink-learn             # 提取写作经验，越写越懂你
/ink-dashboard         # 可视化看板：适合盯着发呆
```

</details>

**结论：无脑用 `/ink-auto`。** 所有场景都用 `/ink-auto` 就对了。

### 你的第一次——从零到出文全流程

#### 第一步：创建项目（脱衣服）

```bash
/ink-init
```

系统会像一个耐心的情人一样，一步步问你：
- 你的故事叫什么？（书名）
- 什么题材？（38 种任选：修仙/都市/末世/言情/悬疑……）
- 主角是谁？什么性格？有什么金手指？
- 女主呢？反派呢？
- 世界观什么样？力量体系怎么分？
- 你想写多少章？分几卷？

回答完，它会帮你生成完整的项目骨架：总纲、设定集、数据库——所有前戏都帮你做好。

#### 第二步：规划大纲（前戏）

```bash
/ink-plan 1
```

为第 1 卷生成详细大纲：
- **节拍表**：每一个高潮、低谷、反转都安排好
- **时间线**：精确到每一章发生在哪天
- **章纲**：每一章的目标、障碍、爽点、钩子全部写明

这一步很重要。前戏做得好，后面才够爽。

#### 第三步：开始写作（正餐）

```bash
/ink-auto 20
```

然后你就可以去睡觉了。

起来的时候，4 万字已经写好了。中间还自动做了 4 次质量审查、2 次数据审计。所有审查报告和修复记录都在 `审查报告/` 目录等着你过目。

#### 第四步：日常循环

```
每天：/ink-auto 5~10  → 产出 1~2 万字
每周：看一眼审查报告  → 有问题它已经自动修了
偶尔：/ink-resolve    → 处理一下消歧积压（唯一需要你动手的事）
```

就这么简单。

### 进阶技巧

**终端直接运行（不需要进入 AI 会话）：**
```bash
cd /你的小说项目目录
ink-auto 10        # 写 10 章，去做别的事
```

**环境变量调节快感：**
```bash
export INK_AUTO_COOLDOWN=5             # 章节间冷却秒数（默认 10）
export INK_AUTO_CHECKPOINT_COOLDOWN=10 # 检查点间冷却秒数（默认 15）
```

---

## v9.0 新特性：Harness-First 架构

v9.0 采用 **Harness Engineering** 模式：不是迷信模型自己会变聪明，而是用约束、检测、状态和评估把 Agent 变成可控系统。

### 计算型闸门（Step 2C）

在昂贵的 LLM 审查之前，加了一道便宜的确定性检查：字数、命名、伏笔逾期、契约完整性。硬失败直接退回重写，省下 checker 调用费。

### Reader Agent 升格为核心裁判

`reader-simulator` 从"偶尔跑"升级为**每章必跑**。输出 7 维结构化评分：

- 开头抓取力 / 好奇心维持 / 情绪回报 / 主角吸引力 / 追更驱动 / 注水风险 / 套路重复
- 总分 ≥32 通过，25-31 自动增强，<25 退回重写

**写出来的不只是"逻辑没错的文本"，而是"真有人想追的网文"。**

### 旧项目迁移

写到一半的小说，一条命令升级：

```bash
/ink-migrate    # 3 分钟，自动备份 + 迁移 + 审计
```

不迁移也能用。详见 [v9.0 升级指南](docs/v9-upgrade-guide.md)。

---

## v9.18-9.19 新特性：写作质量革命

> 从"不犯错"到"写得好"——基于112本起点热门小说的数据驱动质量提升。

### 标杆分析系统（benchmark/）

爬取起点中文网112本热门小说、3351章、712万字，覆盖23个题材，生成量化的写作质量基线：

```
benchmark/
├── scraper.py          # 起点爬虫（支持断点续爬）
├── stat_analyzer.py    # 统计分析引擎（句式/段落/词汇/节奏/爽点）
├── craft_analyzer.py   # LLM Craft 分析框架
├── compare.py          # ink-writer vs 标杆差距报告
├── style_benchmark.json # 712万字统计基线
├── craft_lessons/      # 6个Craft分析文件（23条可复用写作原则）
└── gap_analysis.md     # 量化差距报告
```

### Writer-Agent 读者体验型重构

从"约束满足型"转为"读者体验型"——不再是"遵守100条规则写出的文字"，而是"让读者想翻下一页的文字"：

- **三问法**：每个场景动笔前先问——毒钩是什么？感知锚是什么？尾刺是什么？
- **角色视角驱动**：穿上角色，用角色的眼睛看世界。紧张时句子自然变短，放松时自然变长。
- **6条写作铁律**：用"做"代替"想"、1/3法则、对话像乒乓球、沉默比台词有力...
- **句式节奏显式控制**：标杆句长均值28字，ink-writer之前只有12字。现在显式要求日常场景20-40字长句为主。

### 反AI味：从修补到源头

废除旧版7条机械规则（"每5句插短句""单句段≥25%"），改为7条内化风格原则：

| 旧规则（已废除） | 新原则 |
|----------------|--------|
| 每5句必须有1句≤8字 | 角色状态驱动句式节奏 |
| 每300字插1句无功能感官句 | 闲笔从角色感知自然生长 |
| 单句段占比≥25% | 不完美即真实 |
| 禁止连续3句因果链 | 因果链要有"缺口" |

### 5类场景Craft指导

基于标杆小说Craft分析，新增 `references/scene-craft/`：

| 场景 | 核心原则 | 标杆示例来源 |
|------|---------|------------|
| 战斗 | 快慢交替、近战用触觉+嗅觉、战后清算身体 | 《夜无疆》ch007 |
| 对话 | 限制词汇分化角色、潜台词揭一层留一层 | 《青山》ch005 |
| 情感 | 日常→悲剧反差、小物件承载大情感 | 《夜无疆》ch006 |
| 悬念 | 1/3法则、设定寄生于行为、章末倒计时 | 《银针破武林》ch001 |
| 高潮 | 安静→爆发反差、长句末尾接冲击短句 | 《青山》ch006 |

### 商业包装 & 起点审核优化

- **书名公式**：题材标签 + 核心卖点 + 好奇心缺口
- **简介模板**：冲突 + 金手指 + 爽点承诺 + 悬念（4句话说完）
- **10秒扫读测试**：模拟编辑快速翻阅，检查书名+简介+第1段
- **前3万字里程碑**：ch1-2人设+金手指、ch3-5小胜利+配角、ch6-10小高潮、ch10-12长线冲突

---

## 全套服务流程——每章 11 步

```
Step 0     预检 + 金丝雀扫描          "先验个身，确认你是健康的"
Step 1     上下文构建（8 个维度）      "回忆一下上次到哪了"
Step 2A    正文起草（≥2200 字）        "开始深入"
Step 2A.5  字数校验                   "不够 2200 字？不行，加量"
Step 2B    风格适配                   "换个更舒服的姿势"
Step 2C    计算型闸门                 "先过一道确定性检查，省得浪费钱"     ← v9.0 新增
Step 3     10 Agent 审查              "10 个人从不同角度检查你的表现"
Step 4     润色 + 追读力增强           "把'他非常愤怒'改成'他指节捏得发白'"  ← v9.0 增强
Step 4.5   安全校验 + 情感差分         "确认润色没有把感觉搞没了"
Step 5     Data Agent 回写            "记录档案，每个细节都存下来"
Step 6     Git 备份                   "穿好衣服，保存进度"
```

---

## 十四位技师为你服务

### 核心四人组

| 技师 | 专长 | 服务承诺 |
|------|------|---------|
| **writer-agent** | 正文起草 | "不是执行大纲，是让读者想翻下一页" ← v9.18 读者体验型重构 |
| **polish-agent** | 润色去 AI 味 | "把每个粗糙的地方都打磨光滑" |
| **context-agent** | 上下文构建 | "第 247 章埋的伏笔？我记得比你清楚" ← v9.18 增加角色视角+场景类型 |
| **data-agent** | 数据回写 | "你的每一次动作，我都记录在案" |

### 审查天团（10 位，专门找你的敏感点）

| 技师 | 检查什么 | 最犀利的一句 |
|------|---------|-------------|
| **consistency-checker** | 设定一致性 | "筑基期用金丹技能？你在做白日梦" |
| **continuity-checker** | 连贯性 | "上章在天云宗，这章突然到血煞秘境？瞬移吗？" |
| **ooc-checker** | 人物一致性 | "遮住'XX说'后分不清谁在说话？角色声音同质化警报" ← v9.19 声音区分度 |
| **anti-detection-checker** | AI 味检测 | "句长方差太低？角色说话都一个调？从源头治，不是事后修补" ← v9.18 内化风格原则 |
| **reader-pull-checker** | 追读力 | "这章结尾凭什么让人翻下一章？" |
| **high-point-checker** | 爽点密度 | "5 章了一个高潮都没有，读者早走了" |
| **pacing-checker** | 节奏平衡 | "连续 7 章都在打打打，来点别的行不行" |
| **proofreading-checker** | 文笔质量 | "同一个比喻用了 3 次，换个花样" |
| **golden-three-checker** | 黄金三章 | "编辑10秒看书名+简介+第1段，你过得了吗？" ← v9.19 10秒扫读测试 |
| **reader-simulator** | 读者模拟 | "我模拟了一个读者，他在第 600 字开始走神" |

---

## 记忆系统（比你前任还记仇）

```
index.db        25 张 SQLite 表，摸过的每一寸都记着
state.json      运行时状态快照
vectors.db      RAG 向量数据库，支持语义检索
summaries/      每章自动生成摘要
style_anchor    风格指纹，防止前后判若两人
```

### 它记住了什么

- 主角现在什么境界（精确到层）
- 女配上次出场第几章、说了什么、当时什么心情
- 第 47 章埋的伏笔原定第 120 章回收，现在第 130 章了还没收 → 逾期红灯
- 最近 10 章主线占比 85%，感情线断了 12 章 → 节奏失衡警告
- 你在第 200 章欠的微兑现债，利息还在涨

---

## 智能检查点（ink-auto 的核心卖点）

`/ink-auto` 不是无脑堆章节。它内置三层检查点，像定期体检一样守护你的小说质量：

### 每 5 章：基础体检

启动 5 个核心审查 Agent（consistency + continuity + OOC + anti-detection + **reader-simulator**），发现 critical/high 问题**立即自动修复**，修复后自动验证。

覆盖：设定矛盾、连贯断裂、人设崩塌、AI 味过浓、伏笔遗漏、**追读力不足**。

### 每 10 章：数据健康检查

运行 ink-audit quick，检查：
- state.json 与 index.db 数据同步
- 过期伏笔预警
- 实体消歧积压

### 每 20 章：深度全身检查

运行 ink-audit standard + ink-macro-review Tier2，分析：
- 支线剧情健康度
- 角色弧光演化轨迹
- 冲突模式去重（同一套路用了 3 次以上就报警）
- 叙事承诺审计（许过的诺、发过的誓，有没有兑现）
- 风格漂移检测（和第一章还像同一个人写的吗）
- 消歧积压报告

### 自动大纲生成

写到某章发现该卷大纲还没做？`/ink-auto` 会：
1. 自动检测缺失
2. 启动独立进程生成完整卷大纲（节拍表 + 时间线 + 章纲）
3. 验证生成成功
4. 继续写作

全程无需人工介入。

---

## RAG 配置（可选，不配也能用）

在项目根目录创建 `.env`：

```bash
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_key
```

配了 RAG = 精准语义检索。不配 = BM25 关键词检索兜底，也能用。

---

## 架构总览

```
                        ┌─────────────┐
                        │   你（躺着） │
                        └──────┬──────┘
                               │ /ink-auto
                        ┌──────▼──────┐
                        │  ink-auto   │  ← 全自动调度
                        │  智能检查点  │
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ context  │    │  writer  │    │  polish  │
        │  agent   │    │  agent   │    │  agent   │
        │ "前戏"   │    │ "正餐"   │    │ "善后"   │
        └──────────┘    └──────────┘    └──────────┘
                               │
                        ┌──────▼──────┐
                        │  Step 3     │
                        │ 10 Checkers │  ← "十人鉴定团"
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ data-agent  │  ← "记录员"
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
A: v9.18 彻底重构了反AI策略——不再靠"写完AI文再机械修补"，而是从源头用**角色视角驱动**写出有生命力的文字。7条内化风格原则 + 15词AI高频词意识表 + 5类场景Craft指导，让句式节奏由角色状态自然决定，而非机械插入短句。基于112本起点标杆小说的统计基线校准。

**Q: 写到 300 章会不会忘了前面的事？**
A: 25 张表记着你的一切。伏笔逾期自动报警，角色复出自动加载履历。比你自己的记性好。

**Q: `/ink-auto 100` 真的不会崩？**
A: 每 5 章自检一次，每 20 章深度体检，大纲缺失自动生成。就算中间某一章写崩了，前面的全部保留，用 `/ink-resume` 从断点继续。

**Q: 可以写什么题材？**
A: 38 种模板任选：修仙 / 玄幻 / 都市 / 末世 / 言情 / 悬疑 / 规则怪谈 / 系统流 / 克苏鲁……什么 play 都能满足。

**Q: 检查点开销大吗？**
A: 100 章的写作过程中，检查点总开销约 7 小时，占总写作时间的 7-14%。用 7% 的时间换不崩的质量，值。

**Q: 消歧是什么？为什么不能自动？**
A: Data Agent 提取实体时，有些拿不准的（比如"王兄"到底是谁），会放进待定区。`/ink-resolve` 让你亲自裁决。这是唯一需要你动手的事。每 20 章 ink-auto 会报告积压数量。

---

## 版本历史

| 版本 | 说明 |
|------|------|
| **v10.0.0 (当前)** | 工程架构审查优化 — 异常处理收紧 + SQLite WAL模式 + 魔法数字收口 + ruff linter + 日志级别提升 |
| v9.19.0 | 写作质量提升 Phase 3-5 — 商业包装指南 + 黄金三章10秒扫读测试 + AI高频词黑名单 + OOC声音区分度 + 审核模式里程碑 |
| **v9.18.0** | 写作质量提升 Phase 1-2 — 112本起点标杆分析系统(712万字) + Writer-Agent读者体验型重构 + 反AI内化风格重写 + 5类场景Craft指导 + 场景类型自动检测 |
| **v9.17.0** | 工程审查优化 — SQLite 连接泄漏修复 + 静默异常补充日志 + IndexManager 实例复用 + 覆盖率 84.42% |
| **v9.16.0** | 工程审查优化 — Lock 文件 prod/dev 拆分 + 测试 sys.path hack 清除 + 发布流水线 macOS 门禁 |
| **v9.15.0** | 工程审查优化 — Python 版本声明修正 + 测试/生产依赖拆分 + CI macOS 矩阵 + SQLite 同步异常分级处理 |
| **v9.14.0** | 工程审查优化 — except Exception 精确化 + index_manager CLI 命令分发重构 + CI Python 3.12 矩阵 + 最低版本声明修正为 3.12 |
| **v9.13.0** | 工程审查优化 — context_manager SQLite 连接泄漏修复 + conftest ResourceWarning 过滤器移除 + Dashboard server/watcher 测试补齐 + CLI 路由器覆盖率 50%→74% + 覆盖率 83%→84%+ |
| **v9.12.0** | 工程审查优化 — archive_manager/init_project 测试补齐突破 70% 阈值 + 覆盖率 81.92%→83%+ + ResourceWarning 根因定位（coverage+Python3.14 兼容性问题） |
| **v9.11.0** | 工程审查优化 — MagicMock 泄漏修复 + CI 版本全对齐 + Dashboard/status_reporter/archive_manager 测试补齐 |
| **v9.10.0** | 工程审查优化：CI Python 版本与 Lock 文件对齐 3.14、migration_auditor 测试覆盖 0%→90%+、runtime_compat/security_utils pragma 标注、CI 触发路径覆盖 Agent/Skill 变更、Dashboard 纳入覆盖率统计、删除已废弃 ink-5 Skill |
| **v9.9.0** | 工程审查优化：发布流水线增加测试守门、CI 覆盖 Dashboard 变更、workflow_manager 覆盖率 58%→80%、Git Tag 补全 |
| **v9.8.0** | 工程审查优化：package-lock.json 纳入版本同步工具、发布流水线集成前端构建、版本校验覆盖 Dashboard 前端 |
| **v9.7.0** | 工程审查优化：删除死代码 golden_three_checker.py、anti_ai_scanner 补测试、Dashboard path_guard 安全测试、CI 新增 dashboard import 检查、共用 conftest.py 抽取、审查报告归档整理 |
| v9.6.0 | 工程审查优化：security_utils 测试覆盖 37%→69%、update_state 测试覆盖 39%→84%、整体覆盖率 71%→72%、jieba 可选依赖声明、历史审查报告归档 |
| v9.5.0 | 工程审查优化：活跃 Skill 中 ink-5 残留引用全部替换为 ink-auto、覆盖率门槛提升至 70%、Dashboard 版本对齐主版本、历史审查报告归档至 docs/archive/ |
| v9.4.0 | 工程审查修复：覆盖率范围扩大到 scripts 全层（data_modules→scripts）、ink.py 注册 checkpoint/report-check/disambig-check 子命令消除 Bash/Python 双写、ink-auto.sh bare except 修复、scripts/\_\_init\_\_.py 版本号纳入同步检查、docs/architecture.md 更新至 14 Skills + 14 Agents |
| v9.3.0 | 工程审查优化：统一 .coveragerc 扩大覆盖范围、核心模块补充测试（IndexManager/StateManager/EntityLinker）、ink-auto 检查点逻辑提取为可测试 Python 模块、Dashboard CORS 收窄为 localhost、ink-5 缩减为纯重定向桩、覆盖率门槛提升 |
| v9.2.0 | 工程基础设施审查修复：env-setup.sh 消除 Skill 重复、index_types 解耦循环依赖、pip-compile 锁定依赖、schema 版本追踪、dist 移出 Git |
| **v9.1.0** | 工程基础设施优化：CI 测试流水线、pytest 路径修正、三平台版本同步、Gemini/Codex 文档更新至 v9.0 |
| **v9.0.0** | Harness-First 架构改造：命令收口（4 主入口）、计算型闸门（Step 2C）、Reader Agent 升格为核心裁判（7 维评分）、ink-migrate 迁移工具、ink-auto 增强输出 |
| **v8.2.0** | 角色知识门控（Knowledge Gate）：主角视角知识边界约束 + 第四定律 + CKV 检查；爽点前置密集化：章内三段布局 + 开场速度约束 + 密度基线强化 |
| **v8.1.0** | ink-auto 智能升级：分层检查点（5/10/20章）、自动大纲生成、自动审查修复、增强完成报告 |
| **v8.0.2** | 修复大纲检查漏检，新增 check-outline 子命令 |
| **v8.0.1** | ink-auto/ink-5 大纲缺失时严禁写作 + 全面异常处理 |
| **v8.0.0** | 大版本：14 Agent 全规范化、风格锚定、情感层、批量恢复、BM25 分词 |
| **v7.0.x** | jieba 分词、架构优化、权重校准 |

---

## 文档

- [quality-upgrade-dev-guide.md](docs/quality-upgrade-dev-guide.md) — **v9.18-9.19 写作质量提升开发文档**（标杆分析+Writer重构+商业包装完整方案）
- [v9-upgrade-guide.md](docs/v9-upgrade-guide.md) — v9.0 升级与迁移指南（写到一半的项目看这个）
- [architecture.md](docs/architecture.md) — 架构与模块
- [commands.md](docs/commands.md) — 命令详解
- [rag-and-config.md](docs/rag-and-config.md) — RAG 配置
- [genres.md](docs/genres.md) — 38 种题材模板
- [operations.md](docs/operations.md) — 运维与恢复

## 开源协议

GPL v3，详见 [LICENSE](LICENSE)。

---

> *"一条指令，14 个 AI 从头伺候到尾。"*
>
> *"这辈子被服务得最彻底的一次。"*
>
> *—— 某不愿透露姓名的 ink-writer 用户*
