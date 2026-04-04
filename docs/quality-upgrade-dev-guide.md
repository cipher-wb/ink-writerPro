# ink-writer 写作质量提升 — 开发执行文档

> **版本**: v1.0 | **创建���期**: 2026-04-04 | **状态**: Phase 1 未开始
>
> **本文档是 AI 可执行的开发指南**。每个任务带有唯一ID、依赖关系、验收标准和测试方法。
> 上下文断开后，AI 应读取本文档的「进度追踪」章节，从最后完成的任务继续。

---

## 0. 项目概述

### 0.1 背景
ink-writer 工程化能力强（10个审查器、三大铁律），但产出的小说未通过起点编辑审核、番茄点击率低。内部评分86-92分但距离商业发表有差距。

### 0.2 核心诊断
系统是**约束满足型**架构 — LLM在写给检查器看而不是写给读者看。规则越多AI味越重。

### 0.3 目标
1. 短期：新书通过起点编辑审核
2. 长期：系统性提升全书写作质量
3. 量化：审查评分≥88、人工阅读无明显AI感

### 0.4 策略
**爬取标杆数据 → 数据驱动优化 → 从"约束满足型"转向"读者体验型"**

---

## 1. Harness 工程架构

### 1.1 质量门禁体系

每个Phase完成后必须通过对应的质量门禁（Quality Gate），才能进入下一Phase。

```
Phase 1 (标杆数据) ──── QG1: 数据完整性+分析质量验证 ────►
Phase 2 (Writer重构) ── QG2: 写作对比测试 ────────────────►
Phase 3 (商业包装) ──── QG3: 10秒扫读测试 ────────────────►
Phase 4 (反AI味) ────── QG4: AI检测+人工盲审 ─────────────►
Phase 5 (角色声音) ──── QG5: 角色区分度测试 ───────────────►
                                                          │
                              最终验证: 写新书前3万字投稿起点
```

### 1.2 测试层级

| 层级 | 说明 | 执行时机 |
|------|------|---------|
| L0-单元测试 | 单个脚本/模块的功能正确性 | 每个任务完成后 |
| L1-集成测试 | 模块间数据流通性 | 每个Phase完成后 |
| L2-质量对比测试 | ink-writer产出 vs 标杆小说对比 | Phase 2/4完成后 |
| L3-端到端测试 | 用完整流程写测试章节 | 全部Phase完成后 |
| L4-人工验收 | 人工阅读+起点投稿 | 最终验证 |

### 1.3 回归测试

每个Phase的改动不能破坏现有功能：
- 改动 writer-agent.md 后：运行 `ink-write` 写一章测试，确认不报错
- 改动 checker 后：运行 `ink-review` 审查现有章节，确认评分不异常下降
- 改动 init 流程后：运行 `ink-init` 创建测试项目，确认流程完整

---

## 2. ��度追踪

> **恢复指南**：上下文断开后，读取此章节找到最后一个 `[x]` 标记的任务，从下一个 `[ ]` 任务继续。

### Phase 1: 标杆数据采集与分析
- [x] T1.1 — 爬虫开发
- [x] T1.2 — 爬虫执行 — 112本、3351章、712万字、23个题材
- [x] T1.3 — 统计层分析引擎
- [x] T1.4 — Craft层分析引擎 — 6个craft_lessons文件完成
- [x] T1.5 — 差距报告生成 — 基于112本标杆数据
- [x] T1.6 — **QG1: PASS ✅ (12/12)**

### Phase 2: Writer-Agent 核心重构
- [x] T2.1 — writer-agent prompt重构（前台层读者体验+后台层护栏，123行→185行）
- [x] T2.2 — 角色视角驱动模式（融入T2.1的writer-agent重构中）
- [x] T2.3 — 场景Craft指导文档（5个文件：combat/dialogue/emotion/suspense/climax）
- [x] T2.4 — writing_guidance_builder 升级（场景类型检测+Craft提示注入）
- [x] T2.5 — context-agent 升级（新增第8.5板块：角色视角与场景类型）
- [x] T2.6 — **QG2: 写作对比测试** — 部分通过。Craft层面显著改进（配角互动、减少解释、情感标点↑），统计层面句长问题已识别并追加修复（句式节奏指导强化）

### Phase 3: 商业包装 + 黄金三章
- [ ] T3.1 — 商业包装系统
- [ ] T3.2 — 黄金三章checker升级
- [ ] T3.3 — 审核模式大纲约束
- [ ] T3.4 — 开篇模式库
- [ ] T3.5 — **QG3: 10秒扫读测试**

### Phase 4: 反AI味根治
- [x] T4.1 — 重写anti-detection-writing.md（从机械规则→内化风格原则，7条硬规则→7条风格原则+AI词表）
- [ ] T4.2 — AI高频词黑名单
- [ ] T4.3 — anti-detection-checker升级
- [ ] T4.4 — polish-agent升级
- [ ] T4.5 — **QG4: AI检测+人工盲审**

### Phase 5: 角色声音系统
- [ ] T5.1 — 角��卡schema扩展
- [ ] T5.2 — ooc-checker升级
- [ ] T5.3 — **QG5: 角色区��度测试**

### 最终验证
- [ ] T6.1 — 端到端写作测试
- [ ] T6.2 — 起点投稿验证

---

## 3. Phase 1 详细任务

### T1.1 — 爬虫开发

**任务ID**: T1.1
**依赖**: 无
**状态**: [ ] 未开始

#### 描述
开发 Python 爬虫脚本，从起点中文网各题材排行榜爬取热门小说的免费章节。

#### 输入
- 起点排行榜URL（月票榜/推荐榜/畅销榜）
- 目标题材：玄幻、都市、科幻、仙侠、历史、游戏、悬疑 等主要品类

#### 输出
```
benchmark/
├── scraper.py                    # 爬虫主脚本
├── config.py                     # 爬虫配置（URL、间隔、分类等）
├── corpus/                       # 语料库
│   ├── {书名}/
│   │   ├── metadata.json         # 书籍元数据
│   │   │   {
���   │   │     "title": "xxx",
│   │   │     "author": "xxx",
│   │   │     "genre": "玄幻",
│   │   │     "tags": ["系统", "升级"],
│   │   │     "total_words": 2000000,
│   │   │     "collections": 50000,
│   │   │     "recommendations": 100000,
│   │   │     "rating": 8.5,
│   │   │     "synopsis": "xxx",
│   │   │     "url": "https://...",
│   │   │     "scraped_at": "2026-04-04"
│   │   │   }
│   │   ├── chapters/
│   │   │   ├── ch001.txt         # 章节纯文本
│   │   │   ├── ch002.txt
│   │   │   └── ...
│   │   └── reviews/
│   │       └── top_reviews.json  # 高赞书���
│   └── ...
└── corpus_index.json             # 全部书籍索引
```

#### 技术要求
- 使用 `httpx` + `asyncio` 异步爬取
- 反反爬策略：
  - 请求间隔 3-5秒（随机）
  - UA池轮换（≥10个不同UA）
  - Cookie管理
  - 失败重试（3次，指数退避）
- 仅爬取免费公开章节
- 支持断点续爬（已爬取的书跳过）
- 日志记录（爬取进度、失败原因）

#### 验收标准
1. 成功爬取 ≥5个题材、每题材 ≥10本、每本 ≥10章
2. metadata.json 字段完整无空值
3. 章节文本无HTML标签残留、无乱码
4. corpus_index.json 正确索引所有书籍

#### 测试方法（L0）
```bash
# 1. 先用单本测试模式验证
cd /Users/cipher/AI/ink/ink-writer
python benchmark/scraper.py --test --limit 1

# 2. 检查输出格式
python -c "
import json, pathlib
corpus = pathlib.Path('benchmark/corpus')
for book_dir in corpus.iterdir():
    if book_dir.is_dir():
        meta = json.loads((book_dir / 'metadata.json').read_text())
        assert meta.get('title'), f'{book_dir.name}: missing title'
        assert meta.get('genre'), f'{book_dir.name}: missing genre'
        chapters = list((book_dir / 'chapters').glob('ch*.txt'))
        assert len(chapters) >= 1, f'{book_dir.name}: no chapters'
        for ch in chapters:
            text = ch.read_text()
            assert '<' not in text[:100], f'{ch}: HTML residue'
            assert len(text) > 500, f'{ch}: too short'
print('All checks passed')
"

# 3. 检查无重复
python -c "
import json
index = json.loads(open('benchmark/corpus_index.json').read())
titles = [b['title'] for b in index]
assert len(titles) == len(set(titles)), 'Duplicate books found'
print(f'Total unique books: {len(titles)}')
"
```

---

### T1.2 — 爬虫执行

**任务ID**: T1.2
**依赖**: T1.1
**状态**: [ ] 未开始

#### 描述
执行爬虫，爬取完整语料库。

#### 执行命令
```bash
cd /Users/cipher/AI/ink/ink-writer
python benchmark/scraper.py --all

# 预计耗时：取决于目标数量和请求间隔
# 建议分批执行，每次一个题材
python benchmark/scraper.py --genre 玄幻
python benchmark/scraper.py --genre 都市
python benchmark/scraper.py --genre 科幻
# ... 依次执行
```

#### 验收标准
1. corpus_index.json 包含 ≥50本书
2. 覆盖 ≥5个不同题材
3. 总章节数 ≥500章
4. 无爬取失败的书籍（或已记录失败原因）

#### 测试方法（L0）
```bash
python -c "
import json
index = json.loads(open('benchmark/corpus_index.json').read())
genres = set(b['genre'] for b in index)
total_chapters = sum(b.get('chapter_count', 0) for b in index)
print(f'Books: {len(index)}, Genres: {len(genres)}, Chapters: {total_chapters}')
assert len(index) >= 50, f'Need ≥50 books, got {len(index)}'
assert len(genres) >= 5, f'Need ≥5 genres, got {len(genres)}'
assert total_chapters >= 500, f'Need ≥500 chapters, got {total_chapters}'
print('Corpus validation passed')
"
```

---

### T1.3 — 统计层分析引擎

**任务ID**: T1.3
**依赖**: T1.2
**状态**: [ ] 未开始

#### 描述
开发统计分析脚本，对语料库进行多维量化分析，生成风格基线。

#### 输出
```
benchmark/
├── stat_analyzer.py              # 统计分析引擎
├── style_benchmark.json          # 行业风格基线（核心输出）
│   {
│     "overall": {                # 全题材平均值
│       "sentence_length_mean": 18.5,
│       "sentence_length_std": 12.3,
│       "sentence_length_variance_coeff": 0.52,
│       "short_sentence_ratio": 0.28,    # ≤8字句占比
│       "long_sentence_ratio": 0.12,     # ≥35字句占比
│       "dialogue_ratio": 0.42,
│       "paragraph_length_mean": 85,
│       "sensory_word_density": 0.015,   # 感官词/总词
│       "colloquial_ratio": 0.08,        # 口语词占比
│       "exclamation_density": 0.003,
│       "question_density": 0.005
│     },
│     "by_genre": {               # 分题材统计
│       "玄幻": { ... },
│       "都市": { ... }
│     },
│     "by_chapter_position": {    # 分位置统计（前3章 vs 中间 vs 后面）
│       "opening_3": { ... },
│       "middle": { ... }
│     },
│     "ai_word_frequency": {      # AI高频词在人类作品中的使用率
│       "缓缓": 0.001,
│       "不由得": 0.0005,
│       "微微": 0.002,
│       ...
│     }
│   }
└── per_book_stats/               # 每本书的统计数据
    └── {书名}_stats.json
```

#### 分析维度

| 维度 | 指标 | 计算方法 |
|------|------|---------|
| 句式 | 句长均值/标准差/方差系数 | jieba分句后统计字符数 |
| 句式 | 短句占比（≤8字）/ 长句占比（≥35字） | 分类统计 |
| 段落 | 段落长度均值/分布 | 按换行分段 |
| 段落 | 对话占比 | 检测引号/冒号对话标记 |
| 词汇 | 感官词密度 | 维护五感词表，统计命中率 |
| 词汇 | 口语词占比 | 维护口语词表 |
| 词汇 | AI高频词使用率 | 维护AI词表，统计在人类作品中的真实使用频率 |
| 标点 | 感叹号/问号密度 | 每千字标点统计 |
| 节奏 | 每500字情绪标签分布 | 简单规则（冲突词/情感词/描写词占比） |

#### 技术要求
- 使用 `jieba` 分词
- 五感词表、口语词表、AI高频词表需预先构建（可作为 T1.3 的子任务）
- 支持增量分析（新增书籍后只分析新增部分）
- 输出数值精确到小数点后3位

#### 验收标准
1. style_benchmark.json 包含 overall + 至少5个 genre 的数据
2. 每个数值字段非空、非NaN
3. 分析结果与人工抽检一致（随机抽1本，手动统计3个指标，误差≤10%）

#### 测试方法（L0）
```bash
cd /Users/cipher/AI/ink/ink-writer
python benchmark/stat_analyzer.py --input benchmark/corpus --output benchmark/style_benchmark.json

# 验证输出格式
python -c "
import json
data = json.loads(open('benchmark/style_benchmark.json').read())
assert 'overall' in data, 'Missing overall stats'
assert 'by_genre' in data, 'Missing genre breakdown'
overall = data['overall']
required_keys = ['sentence_length_mean', 'sentence_length_std', 
                 'dialogue_ratio', 'sensory_word_density']
for k in required_keys:
    assert k in overall, f'Missing key: {k}'
    assert isinstance(overall[k], (int, float)), f'{k} is not numeric'
    assert overall[k] == overall[k], f'{k} is NaN'  # NaN check
print('Stats validation passed')
"

# 人工抽检：随机选一本书，对比手动统计
python benchmark/stat_analyzer.py --input benchmark/corpus/《某本书》 --verbose
# 手动检查输出是否合理
```

---

### T1.4 — Craft层分析引擎

**任务ID**: T1.4
**依赖**: T1.2
**状态**: [ ] 未开始

#### 描述
开发 LLM 辅助的 Craft 分析脚本，用 Claude 对标杆小说做深度写作技巧分析。这是 Phase 1 的**核心价值**产出。

#### 输出
```
benchmark/
├── craft_analyzer.py             # Craft分析引擎
├── craft_prompts/                # 分析用的prompt模板
│   ├── opening_analysis.md       # 开篇分析prompt
│   ├─�� scene_analysis.md         # 场景分析prompt
│   ├── character_analysis.md     # 角色分析prompt
│   └── comparison_analysis.md    # 对比分析prompt
├── craft_lessons/                # Craft提取结果（核心产出）
│   ├── opening_patterns.md       # 开篇技巧提取
│   │   - 各题材最有效的开篇模式（具体示例+注释）
│   │   - 10秒抓住编辑的关键要素
│   │   - 好开篇vs坏开篇对比
│   ├── combat_craft.md           # 战斗场景技巧
│   ├── dialogue_craft.md         # 对话技巧
│   ├── emotion_craft.md          # 情感场景技巧
│   ├── suspense_craft.md         # 悬念技巧
│   ├── character_voice.md        # 角色声音技巧
│   └── pacing_craft.md           # 节奏控制技巧
├── per_book_craft/               # 每本书的Craft分析
│   └── {书名}_craft.json
└── craft_lessons_summary.md      # 所有Craft教训的汇总摘要
```

#### 分析内容（每本标杆小说的前3章）

**开篇分析**（craft_prompts/opening_analysis.md）：
```
请分析以下小说的第1章开篇（前300字）：
[插入文本]

回答以下问题：
1. 第1句话用了什么技巧来抓住读者？（动作/危机/悬念/对话/感官冲击？）
2. 前300字传递了哪些关键信息？（主角身份/困境/世界观/金手指？）
3. 编辑在10秒扫读中能获取什么？（是否足够判断题材和质量？）
4. 与[银针破武林第1章]相比，craft差异是什么？
5. 提取1-2条可复用的开篇写法原则。

输出格式：JSON
{
  "hook_technique": "描述使用的钩子技巧",
  "info_density": "300字内传递的关键信息列表",
  "10s_impression": "编辑10秒能感知到的内容",
  "craft_vs_inkwriter": "与ink-writer产出的关键差异",
  "reusable_principles": ["原则1", "原则2"]
}
```

**场景分析**（对每本书的战斗/对话/情感场景各分析1个）：
```
请分析以下[战斗/对话/情感]场景：
[插入场景文本]

回答：
1. 这个场景的节奏是如何控制的？（快/慢/交替？转折点在哪？）
2. 用了哪些感官描写？服务于什么目的？
3. 角色的内心活动如何与外在行动配合？
4. 这个场景中最有效的1-2个写作技巧是什么？
5. 提取可复用的场景写法原则。

输出格式：JSON
{
  "pacing_analysis": "节奏分析",
  "sensory_usage": "感官描写分析",
  "inner_outer_balance": "内外配合分析",
  "top_techniques": ["技巧1", "技巧2"],
  "reusable_principles": ["原则1", "原则2"]
}
```

**角色声音分析**：
```
请分析以下小说中主要角色的对话风格差异：
[插入包含2-3个角色对话的场景]

回答：
1. 每个角色的说话方式有什么特征？（用词/句长/语气/口癖）
2. 仅凭对话内容（不看"XX说"），能否区分是谁在说话？
3. 角色的内心独白和说出的话有什么差异？
4. 提取角色声音分化的可复用原则。
```

#### 技术要求
- 使用 Anthropic API（`anthropic` SDK）调用 Claude
- 每本书分析前3章，每章分析3个维度（开篇/场景/角色）
- 分析结果缓存到 per_book_craft/ 避免重复调用
- 最终汇总到 craft_lessons/ 各主题文件
- 支持增量分析（新增书籍只分析新增部分）

#### 验收标准
1. craft_lessons/ 目录包含 ≥6个主题文件
2. 每个主题文件包含 ≥5条可复用的写作原则
3. 每条原则附有具体示例（从标杆小说摘取）
4. craft_lessons_summary.md 涵盖所有主题的精华

#### 测试方法（L0）
```bash
# 1. 用单本测试模式
python benchmark/craft_analyzer.py --book "《某本书》" --test

# 2. 验证输出格式
python -c "
import pathlib
lessons_dir = pathlib.Path('benchmark/craft_lessons')
assert lessons_dir.exists(), 'craft_lessons directory missing'
files = list(lessons_dir.glob('*.md'))
assert len(files) >= 6, f'Need ≥6 lesson files, got {len(files)}'
for f in files:
    content = f.read_text()
    assert len(content) > 500, f'{f.name}: too short, likely empty'
print(f'Craft lessons: {len(files)} files, all non-empty')
"
```

---

### T1.5 — 差距报告生成

**任务ID**: T1.5
**依赖**: T1.3, T1.4
**状态**: [ ] 未开始

#### 描述
将 ink-writer 现有产出（银针破武林前10章）与标杆数据对比，生成综合差距报告。

#### 输出
```
benchmark/
├── compare.py                    # 对比分析脚本
└── gap_analysis.md               # 综合差距报告
    内容结构：
    1. 统计差距（数值对比表）
       - ink-writer句长方差 vs 标杆句长方差
       - ink-writer对话占比 vs 标杆对话占比
       - ... 所有统计维度
    2. Craft差距（定性对比）
       - 开篇：ink-writer的开篇 vs 标杆的开篇（具体差异）
       - 战斗场景：ink-writer的战斗 vs 标杆的战斗
       - 对话：ink-writer的对话 vs 标杆的对话
       - 角色声音：ink-writer的角色 vs 标杆的角色
    3. 改进优先级排序
       - 基于差距大小和影响程度排序
       - 每个改进项标注对应的后续Phase和任务ID
    4. 具体改进建议
       - 统计建议：各checker阈值应调整为多少
       - Craft建议：writer-agent需要增加哪些写作指导
       - 商业建议：书名/简介应参考哪些模式
```

#### 验收标准
1. gap_analysis.md 包含统计差距+Craft差距+优先级排序+改进建议
2. 每个差距项都有具体数值或示例支撑
3. 改进建议可直接对应到后续Phase的任务

#### 测试方法（L0）
```bash
python benchmark/compare.py \
  --benchmark benchmark/style_benchmark.json \
  --craft benchmark/craft_lessons/ \
  --inkwriter "/Users/cipher/AI/银针破武林/银针破武林/正文/" \
  --output benchmark/gap_analysis.md

# 验证报告结构完整
python -c "
report = open('benchmark/gap_analysis.md').read()
required_sections = ['统计差距', 'Craft差距', '改进优先级', '改进建议']
for section in required_sections:
    assert section in report, f'Missing section: {section}'
print('Gap analysis structure validated')
"
```

---

### T1.6 — QG1: 数据质量门禁

**任务ID**: T1.6
**依赖**: T1.5
**状态**: [ ] 未开始

#### 质量门禁检查清单

```
QG1 检查项：

[ ] 1. 语料库完整性
    - corpus_index.json 包含 ≥50本书
    - 覆盖 ≥5个题材
    - 每本书 ≥10章

[ ] 2. 统计数据有效性
    - style_benchmark.json 所有字段非空
    - 手动抽检3本书的统计数据，误差≤10%
    - by_genre 至少覆盖5个题材

[ ] 3. Craft分析质量
    - craft_lessons/ 包含 ≥6个主题文件
    - 每个主题包含 ≥5条可复用原则
    - 随机抽检3条原则，确认有具体示例支撑
    - craft_lessons_summary.md 涵盖所有主题

[ ] 4. 差距报告可用性
    - gap_analysis.md 包含4个完整章节
    - 改进建议可直接映射到Phase 2-5的任务
    - 至少标注了5个具体的checker阈值调整建议

[ ] 5. 数据可追溯性
    - 每本书的metadata.json有来源URL
    - 每条craft_lesson标注了来源书名和章节号
```

#### 测试方法
```bash
# 运行完整的QG1验证脚本
python benchmark/validate_qg1.py

# 该脚本应输出类似：
# QG1 Check 1: PASS - 52 books, 6 genres
# QG1 Check 2: PASS - All fields valid
# QG1 Check 3: PASS - 7 lesson files, avg 8 principles each
# QG1 Check 4: PASS - Gap analysis complete
# QG1 Check 5: PASS - All sources traceable
# ========================
# QG1 OVERALL: PASS
```

---

## 4. Phase 2 详细任务

### T2.1 — Writer-Agent Prompt 重构

**任务ID**: T2.1
**依赖**: T1.6 (需要craft_lessons作为输入)
**状态**: [ ] 未开始

#### 描述
重构 `ink-writer/agents/writer-agent.md` 的 prompt 架构，从"约束满足型"转为"读者体验型"。

#### 输入
- 当前 writer-agent.md（读取现有内容）
- benchmark/craft_lessons/（Phase 1产出的写作技巧）
- benchmark/gap_analysis.md（差距报告中的改进建议）

#### 改动原则
1. **前台层（主指令）**占 prompt 的60%以上，聚焦"如何让读者想翻页"
2. **后台层（护栏）**占 prompt 的40%以下，三大铁律作为最终检查
3. 反AI规则从显性清单变为内化风格原则
4. 引入 Phase 1 提取的 craft 原则作为具体写作指导

#### 前台层核心内容（必须包含）

```markdown
## 写作核心思维

写作时，你的每一段都在回答一个问题：
"读者此刻最想知道什么？我要满足他还是吊着他？"

你不是在执行大纲，你是在讲一个故事。区别是：
- 执行大纲：把A事件写完，然后写B事件
- 讲故事：让读者因为好奇A而不得不读B

### 每个场景的三问
开始写任何场景前，先回答：
1. **毒钩**：这个场景的什么东西会让读者不读完就难受？
2. **感知锚**：视角角色此刻最强烈的感受是什么？（不是"他感到紧张"，而是他紧张时会注意到什么、忽略什么）
3. **尾刺**：场景结束时，读者手里应该多了一个什么问题？

### 写作禁忌
- 不要"报告"事件，要"展演"事件（show don't tell）
- 不要让所有角色用同样的方式说话
- 不要让每个行为都有完美的动机解释 — 人有时就是"随手"、"突然想到"
- 不要均匀地铺陈信息 — 有些段落可以"浪费"在感官细节上，有些段落可以极度压缩
```

#### 后台层内容（护栏）

```markdown
## 约束护栏（写完后检查，不在写作时分心）

以下约束在写作完成后由审查器检查。写作阶段专注于文字吸引力，不要边写边自检这些规则：

- 大纲即法律：情节走向不得偏离章节大纲
- 设定即物理：角色能力不得超越当前境界设定
- 发明需识别：新出现的角色/地点/技能将被自动提取
- POV边界：不描写视角角色无法感知的信息
```

#### 验收标准
1. writer-agent.md 重构完成
2. 前台层（读者体验导向）占 prompt 主体（≥60%）
3. 后台层（约束）明确标注为"写完后检查"
4. 包含 Phase 1 提取的 ≥3条 craft 原则
5. **回归测试**：用修改后的 writer-agent 写1章测试，确认不报错

#### 测试方法（L0 + L1）
```bash
# L0: 检查文件结构
python -c "
content = open('ink-writer/agents/writer-agent.md').read()
assert '写作核心思维' in content or '读者体验' in content, 'Missing reader-experience section'
assert '约束护栏' in content or '护栏' in content, 'Missing guardrail section'
# 检查前台层占比
import re
total_len = len(content)
# 找到护栏部分的位置
guardrail_pos = content.find('护栏')
if guardrail_pos > 0:
    frontend_ratio = guardrail_pos / total_len
    assert frontend_ratio >= 0.5, f'Frontend ratio too low: {frontend_ratio:.0%}'
print('Writer-agent structure validated')
"

# L1: 集成测试 — 用修改后的writer-agent写1章
# 使用ink-write写一个测试章节，确认完整流程不报错
# （需要人工触发ink-write并观察输出）
```

---

### T2.2 — 角色视角驱动模式

**任务ID**: T2.2
**依赖**: T2.1
**状态**: [ ] 未开始

#### 描述
在 writer-agent 和 context-agent 中引入"角色视角驱动"写法，让 LLM 从角色心理出发生成文字。

#### 改动内容

**writer-agent.md 新增部分**：
```markdown
## 角色视角驱动

写每个场景时，先"穿上"视角角色：

你现在是 {character_name}。
- 你刚经历了：{previous_event}
- 你此刻的位置：{location}
- 你不知道：{unknown_info}
- 你最担心的：{worry}
- 你想要：{desire}
- 挡在你面前的：{obstacle}

用你的眼睛看世界：
- 你会首先注意到什么？（性格决定关注点）
- 你会忽略什么？（盲区即性格）
- 你的身体此刻什么感觉？（疲劳/饥饿/疼痛/兴奋）

然后以你的感受为主线，讲述接下来发生的事。
```

**context-agent.md 增加字段**：
在上下文包中新增 `character_pov` 字段：
```json
{
  "character_pov": {
    "name": "陆九针",
    "previous_event": "刚用三十六针自救，伪装死亡逃出庄园",
    "current_location": "青龙山脚",
    "unknown_info": ["追杀者的真正目的", "神秘女子的身份"],
    "current_worry": "断肠散还在发作，时间不多",
    "current_desire": "找到清虚子求解药",
    "obstacle": "身体虚弱，不知道路",
    "body_state": "脱水、失血、低烧"
  }
}
```

#### 验收标准
1. writer-agent.md 包含完整的"角色视角驱动"部分
2. context-agent.md 的上下文包schema包含 character_pov 字段
3. character_pov 字���能从 state.json + 上一章摘要自动填充

#### 测试方法（L0）
```bash
# 检查writer-agent包含角色驱动部分
python -c "
content = open('ink-writer/agents/writer-agent.md').read()
assert '角色视角' in content or 'character_pov' in content
print('Character POV section found')
"

# 检查context-agent包含character_pov
python -c "
content = open('ink-writer/agents/context-agent.md').read()
assert 'character_pov' in content
print('Character POV field found in context-agent')
"
```

---

### T2.3 — 场景Craft指导文档

**任务ID**: T2.3
**依赖**: T1.4 (需要craft_lessons)
**状态**: [ ] 未开始

#### 描述
基于 Phase 1 的 craft_lessons，创建场景级写作指导文档。

#### 输出文件

在 `ink-writer/references/scene-craft/` 目录下创建以下文件：

**1. combat.md — 战斗场景**
```markdown
## 战斗场景 Craft 指导

### 核心原则
1. **快慢交替**：不是全程高速。紧张动作后跟一个"呼吸"段（角色的感受/判断）
2. **力量可视化**：不说"他很强"，而是展示强的后果（地面碎裂、空气扭曲）
3. **受伤的真实感**：不是"他受了伤"，而是"左臂失去了知觉，血从袖口滴到刀柄上，握不住了"
4. **信息差驱动紧张**：读者知道/不知道什么？角色知道/不知道什么？

### 好例子（来自标杆分析）
[从 craft_lessons/combat_craft.md 提取的具体示例 + 注释]

### 坏例子（典型AI写法）
[标注问题在哪]

### 写作自检
- [ ] 是否有快慢交替（不是全程同一节奏）？
- [ ] 受伤是否有身体感受（不只是"他受了伤"）？
- [ ] 力量差异是否可视化（不只是"他更强"）？
```

**2. dialogue.md — 对话场景**
核心原则：潜台词、信息差博弈、权力关系、插入动作

**3. emotion.md — 情感场景**
核心原则：身体反应>心理描写、留白、环境映射

**4. suspense.md — 悬念场景**
核心原则：信息控制、误导、延迟满足

**5. climax.md — 高潮场景**
核心原则：多线汇聚、期待管理、高潮后余韵

#### 验收标准
1. scene-craft/ 目录包含5个文件
2. 每个文件包含：核心原则(≥3条) + 好例子 + 坏例子 + 自检清单
3. 好例子来自 Phase 1 的 craft_lessons（有来源标注）

#### 测试方法（L0）
```bash
python -c "
import pathlib
craft_dir = pathlib.Path('ink-writer/references/scene-craft')
assert craft_dir.exists(), 'scene-craft directory missing'
expected_files = ['combat.md', 'dialogue.md', 'emotion.md', 'suspense.md', 'climax.md']
for f in expected_files:
    fpath = craft_dir / f
    assert fpath.exists(), f'Missing: {f}'
    content = fpath.read_text()
    assert '核心原则' in content, f'{f}: missing 核心原则 section'
    assert '好例子' in content or '示例' in content, f'{f}: missing examples'
    assert len(content) > 500, f'{f}: too short'
print('Scene craft docs validated')
"
```

---

### T2.4 — writing_guidance_builder 升级

**任务ID**: T2.4
**依赖**: T2.3
**状态**: [ ] 未开始

#### 描述
修改 `scripts/data_modules/writing_guidance_builder.py`，增加场景类型检测和对应 craft 指导注入。

#### 改动逻辑
1. 从章节大纲中检测主要场景类型（战斗/对话/情感/悬念/高潮）
2. 加载对应的 scene-craft 文档片段
3. 注入到上下文包的 writing_guidance 字段中

#### 验收标准
1. 能正确检测场景类型（至少识别：战斗、对话、情感）
2. 注入的 craft 指导与场景类型匹配
3. 上下文包大小不超过预算限制

#### 测试方法（L0）
```bash
# 编写单元测试验证场景检测
python -c "
# 模拟测试
test_cases = [
    ('主角与反派在山顶决战，剑气纵横', '战斗'),
    ('主角与女主在月下对话，互诉衷肠', '情感'),
    ('主角发现线索指向一个惊人的秘密', '悬念'),
]
# 实际测试需要导入writing_guidance_builder中的场景检测函数
print('Scene detection tests need implementation')
"
```

---

### T2.5 — context-agent 升级

**任务ID**: T2.5
**依赖**: T2.2, T2.4
**状态**: [ ] 未开始

#### 描述
修改 `ink-writer/agents/context-agent.md`，在上下文包中增加 character_pov 和 scene_craft 注入。

#### 改动内容
1. 上下文包新增 `character_pov` 字段（T2.2定义）
2. 上下文包新增 `scene_craft_guidance` 字段（T2.4产出）
3. 调整上下文预算分配，为新字段腾出空间

#### 验收标准
1. 上下文包包含 character_pov 和 scene_craft_guidance
2. 总上下文大小不超过预算限制
3. 现有字段不丢失

---

### T2.6 — QG2: 写作对比测试

**任务ID**: T2.6
**依赖**: T2.1-T2.5
**状态**: [ ] 未开始

#### 质量门禁检查清单

```
QG2 检查项：

[ ] 1. 功能完整性
    - writer-agent.md 重构完成，包含前台层+后台层
    - context-agent.md 包含 character_pov + scene_craft_guidance
    - scene-craft/ 目录包含5个完整的craft文档
    - writing_guidance_builder.py 能正确检测场景类型

[ ] 2. 回归测试
    - 用修改后的系统写1章测试章节，流程完整无报错
    - 现有审查器对新产出的评分不低于改动前

[ ] 3. 写作对比测试（核心）
    - 用修改后的系统重写银针破武林第1章
    - 将新旧版本做盲审对比：
      a. 新版本的"读者吸引力"是否更强？
      b. 新版本的角色感受是否更真实？
      c. 新版本的AI味是否更低？
    - 至少2项对比结果为"新版更好"

[ ] 4. craft指导注入验证
    - 战斗场景触发 combat.md 指导注入
    - 对话场景触发 dialogue.md 指导注入
    - 注入内容在上下文预算内
```

---

## 5. Phase 3 详细任务

### T3.1 — 商业包装系统

**任务ID**: T3.1
**依赖**: T1.4 (需要craft_lessons中的书名/简介分析)
**状态**: [ ] 未开始

#### 描述
在 ink-init 流程中增加"商业包装"步骤，新增商业化参考文档。

#### 输出文件

**1. `references/shared/commercial-packaging.md`**
```markdown
## 网文商业包装指南

### 书名写法
- 公式：题材标签 + 核心卖点 + 好奇心缺口
- 好书名示例（来自Phase 1标杆分析）：
  - [从标杆小说提取的成功书名模式]
- 坏书名示例：
  - "银针破武林" → 传统文学感，缺网文商业信号
  - 四字成语式 → 信息量太少

### 简介写法
- 模板：核心冲突(1句) + 金手指(1句) + 爽点承诺(1句) + 悬念(1句)
- 好简介示例（从标杆分析提取）
- 禁忌：不要在简介里讲背景设定、不要用"且看XX如何..."

### 题材热度参考
[从公开渠道整理的起点各品类当前热度]
```

**2. `references/market-heat-map.md`**
各题材在起点的当前热度、签约难度、竞争程度。手动整理。

#### 改动文件
- `skills/ink-init/SKILL.md` — 在初始化流程中增加"商业包装"步骤

#### 验收标准
1. commercial-packaging.md 包含书名写法+简介写法+示例
2. market-heat-map.md 包含 ≥5个题材的热度数据
3. ink-init 流程能触发商业包装步骤

---

### T3.2 — 黄金三章 Checker 升级

**任务ID**: T3.2
**依赖**: T1.4 (需要opening_patterns)
**状态**: [ ] 未开始

#### 描述
升级 `agents/golden-three-checker.md`，增加10秒扫读测试和里程碑检查。

#### 新增检查维度

1. **10秒扫读测试**
   - 输入：书名 + 简介 + 第1段（~200字）
   - 检查：题材是否3秒内可判断？卖点是否可见？有没有继续读的冲动？
   - 输出：10s_impression 评分（1-10）

2. **里程碑检查**（前3万字=~12章）
   - ch1-2: 人设+金手指+首次危机 是否完成？
   - ch3-5: 第一个小胜利+重要配角出场 是否完成？
   - ch6-10: 第一个完整小高潮+世界观展开 是否完成？

3. **开篇模式匹配**
   - 对照 golden-opening-patterns.md 中的成功模式
   - 评估当前开篇的模式类型和有效性

#### 输出文件
- `references/shared/golden-opening-patterns.md` — 从Phase 1提取的开篇模式库

#### 验收标准
1. golden-three-checker.md 包含10秒扫读+里程碑+模式匹配三个新维度
2. golden-opening-patterns.md 包含 ≥5种成功开篇模式（有示例）
3. 回归：现有章节的审查不报错

---

### T3.3 — 审核模式大纲约束

**任务ID**: T3.3
**依赖**: T3.2
**状态**: [ ] 未开始

#### 描述
在 ink-plan 中增加"审核优化模式"，确保前3万字的大纲满足起点审核要求。

#### 改动文件
- `skills/ink-plan/SKILL.md` — 增加审核模式约束

#### 新增约束
当启用"审核优化模式"时，前12章大纲必须满足：
- ch1: 主角人设标签明确 + 核心困境出现
- ch1-2: 金手指首次展示
- ch3: 至少一个"小爽点"（读者有获得感）
- ch5内: 重要配角或女主出场
- ch10内: 第一个完整小高潮完成
- ch12: 长线冲突确立，读者知道"这本书要讲什么"

#### 验收标准
1. ink-plan 在审核模式下生成的大纲满足上述约束
2. 不影响非审核模式的正常大纲生成

---

### T3.4 — 开篇模式库

**任务ID**: T3.4
**依赖**: T1.4
**状态**: [ ] 未开始

#### 描述
从 Phase 1 的 craft_lessons/opening_patterns.md 提取内容，创建 `references/shared/golden-opening-patterns.md`。

#### 内容结构
```markdown
## 高效开篇模式库

### 模式1：危机切入
- 描述：第1句直接进入危机状态（角色正面临生死/重大选择）
- 标杆示例：[从craft分析提取]
- 为什么有效：读者被迫关心主角命运
- 使用场景：动作/冒险/玄幻类

### 模式2：反转切入
...

### 模式3：对话切入
...

### 禁忌模式
- 场景描写开头（"阳光洒在..."）
- 背景介绍开头（"大陆之上有五大宗门..."）
- 哲理独白开头（"命运从来不会..."）
```

#### 验收标准
1. 包含 ≥5种成功模式 + ≥3种禁忌模式
2. 每种模式有具体示例
3. 示例来源可追溯到标杆小说

---

### T3.5 — QG3: 10秒扫读测试

**任务ID**: T3.5
**依赖**: T3.1-T3.4
**状态**: [ ] 未开始

#### 质量门禁检查清单

```
QG3 检查项：

[ ] 1. 商业包装完整性
    - commercial-packaging.md 内容完整
    - market-heat-map.md 覆盖≥5个题材
    - ink-init 流程包含商业包装步骤

[ ] 2. 黄金三章升级验证
    - golden-three-checker 包含3个新检查维度
    - golden-opening-patterns.md 包含≥5种模式
    - ink-plan 审核模式约束可用

[ ] 3. 10秒扫读模拟测试（核心）
    - 用升级后的系统生成3组不同题材的 书名+简介+第1段
    - 每组做10秒扫读评估：
      a. 3秒内能否判断题材？
      b. 5秒内能否发现卖点？
      c. 10秒后是否想继��读？
    - ≥2组通过全部3个标准
```

---

## 6. Phase 4 详细任务

### T4.1 — 重写 anti-detection-writing.md

**任务ID**: T4.1
**依赖**: T1.3 (需要AI词频数据), T2.1
**状态**: [ ] 未开始

#### 描述
重写反AI写作指南，从"统计修补"转为"内化风格原则"。

#### 删除的内容
- ❌ "每5句插一个短句"
- ❌ "单句段落占比≥25%"
- ❌ "插入与主线无关的感官细节"
- ❌ 所有基于字数/频率的机械规则

#### 新增的内容
```markdown
## 反AI写作 — 内化风格原则

### 原则1：感知由角色决定
让角色的状态决定描写密度：
- 紧张时：只看到关键东西，感官变窄，句子变短
- 放松时：注意到环境细节，感官展开，句子变长
- 受伤时：某些感官失灵（看不清），其他感官放大（听觉变敏锐）

不是"每300字插一个感官细节"，而是"角色此刻最强烈感受到什么"。

### 原则2：节奏由情绪驱动
不是"每5句插短句"，而是：
- 紧张动作 → 句子自然变短、碎片化
- 回忆/反思 → 句子自然变长、绵延
- 冲击瞬间 → 一个短句独占一段
- 日常对话 → 句长参差不齐（像真人说话）

### 原则3：不完美即真实
- 角色偶尔做不完全理性的事（冲动、固执、心软）
- 内心独白允许跳跃、矛盾、自我打断
- 不是每个行为都需要"因为...所以..."的完美因果链
- 有时候就是"他也不知道为什么，手已经伸了出去"

### 原则4：闲笔增质感
- 与主线无关但增加真实感的细节要**有机生长**，不是强塞
- 好的闲笔：角色边说话边做的小动作（搓手指、移开目光）
- 坏的闲笔：突兀的环境描写（"暖气管发出咔的一声" ← AI最爱）
```

#### 验收标准
1. 无任何基于字数/频率的机械规则
2. 所有原则都是"风格层面"而非"统计层面"
3. 原则数量 ≤8 条（精炼，不堆砌）

---

### T4.2 — AI高频词黑名单

**任务ID**: T4.2
**依赖**: T1.3 (需要AI词频对比数据)
**状态**: [ ] 未开始

#### 描述
基于 Phase 1 的词频对比数据，创建 AI 高频词替换表。

#### 输出文件：`references/shared/ai-word-blacklist.md`

```markdown
## AI高频词替换表

### 使用方式
- polish-agent 在润色阶段扫描这些词
- 不是全部替换，而是当使用频率超过标杆小说的2倍时标记

### 替换表

| AI高频词 | ink-writer频率 | 标杆频率 | 替换建议 |
|---------|---------------|---------|---------|
| 缓缓 | 0.005 | 0.001 | 具体动作描写（"一寸一寸抬起头"） |
| 不由得 | 0.004 | 0.0005 | 直接写反应，删掉"不由得" |
| 微微 | 0.006 | 0.002 | 写具体程度或不写 |
| 仿佛 | 0.003 | 0.001 | 改用直接比喻 |
| 一股...涌上心头 | 0.002 | 0.0003 | 写具体身体反应 |
| 目光扫过 | 0.003 | 0.001 | 写具体看到了什么 |
| 深吸一口气 | 0.004 | 0.001 | 换其他应激反应 |
| ... | ... | ... | ... |

（完整列表由 Phase 1 统计对比自动生成，≥30个词条）
```

#### 验收标准
1. 包含 ≥30 个AI高频词条目
2. 每个词条有 ink-writer频率 和 标杆频率 对比数据
3. 每个词条有具体的替换建议

---

### T4.3 — anti-detection-checker 升级

**任务ID**: T4.3
**依赖**: T4.1, T4.2
**状态**: [ ] 未开始

#### 描述
在现有6层统计检测基础上，增加语义层检测。

#### 新增检测层

**第7层：语义AI味检测**
- "正确但无趣"的表达检测（形容词都是"常规搭配"，没有新意）
- "完美因果链"检测（每个行为都有因为/所以/于是 → 机器感）
- "情感点到为止"检测（用一句话概括情感，不展开）
- AI高频词密度检测（对照黑名单）

#### 验收标准
1. 第7层检测能独立运行
2. 对银针破武林的章节能检出 ≥3个语义AI味问题
3. 对标杆小说的章节检出数量 ≤1个（确认不是误报）

---

### T4.4 — polish-agent 升级

**任务ID**: T4.4
**依��**: T4.2
**状态**: [ ] 未开始

#### 描述
在 polish-agent 中增加 AI 高频词替换 pass。

#### 改动
- 在润色流程中增加一个步骤：扫描 ai-word-blacklist.md
- 当某个AI高频词的使用频率超过标杆的2倍时，标记为需替换
- 提供替换建议（从黑名单中读取）

#### 验收标准
1. polish-agent 能识别AI高频词
2. 替换建议合理，不破坏原文语义
3. 回归：现有润色流程不受影响

---

### T4.5 — QG4: AI检测+人工盲审

**任务ID**: T4.5
**依赖**: T4.1-T4.4
**状态**: [ ] 未开始

#### 质量门禁检查清单

```
QG4 检查项：

[ ] 1. 功能验证
    - anti-detection-writing.md 无机械规则
    - ai-word-blacklist.md 包含≥30个词条
    - anti-detection-checker 第7层检测可用
    - polish-agent AI词替换pass可用

[ ] 2. AI检测对比测���
    - 用旧系统写1章 + 用新系统写同一章
    - 运行 anti-detection-checker：
      a. 新版检测分数 > 旧版检测分数
      b. 新版的语义AI味问题数 < 旧版

[ ] 3. 人工盲审（核心）
    - 准备3组文本：标杆小说1段 + 旧ink-writer 1段 + 新ink-writer 1段
    - 混合后请人阅读，判断哪个是AI写的
    - 新ink-writer的"被识别为AI"概率 < 旧版
    （注：如果无法安排真人阅读，用Claude模拟即可，但需记录为模拟结果）
```

---

## 7. Phase 5 详细任务

### T5.1 — 角色卡 Schema 扩展

**任务ID**: T5.1
**依赖**: T1.4 (需要character_voice craft分析)
**状态**: [ ] 未开始

#### 描述
扩展角色卡 schema，增加 speech_profile 字段。

#### 改动文件
- `scripts/init_project.py` — 在角色收集流程中增加 speech_profile 字段

#### 新增字段
```json
{
  "speech_profile": {
    "vocab_level": "string",        // 用词层次：文雅/白话/粗犷/混合
    "sentence_habit": "string",     // 句式偏好：短促/绵长/反问多/命令多
    "verbal_tics": ["string"],      // 口癖/常用语气词
    "what_they_notice": "string",   // 性格决定关注什么
    "what_they_avoid_saying": "string", // 绝不会说什么
    "lies_about": "string",         // 对什么撒谎
    "inner_voice_style": "string"   // 内心独白风格vs说话风格的差异
  }
}
```

#### 验收标准
1. init_project.py 收集 speech_profile 字段
2. 字段能被保存到角色卡文件中
3. writer-agent 能读取并使用 speech_profile

---

### T5.2 — ooc-checker 升级

**任务ID**: T5.2
**依赖**: T5.1
**状态**: [ ] 未开始

#### 描述
在 ooc-checker 中增加"声音区分度"和"内心独白一致性"检测。

#### 新增检查维度

1. **声音区分度**
   - 提取章节中不同角色的对话
   - 评估：仅凭说话内容（不看"XX说"），能否区分是谁在说话？
   - 如果2个角色的对话风格相似度 >80% → 标记为 medium

2. **内心独白一致性**
   - 检查角色的心理活动是否符合 speech_profile.inner_voice_style
   - 内心独白和对话的差异是否体现了性格深度

#### 验收标准
1. 能检测出声音相似度过高的角色对
2. 能检测出内心独白与speech_profile不符的情况
3. 回归：现有OOC检测不受影响

---

### T5.3 — QG5: 角色区分度测试

**任务ID**: T5.3
**依赖**: T5.1, T5.2
**状态**: [ ] 未开始

#### 质量门禁检查清单

```
QG5 检查项：

[ ] 1. 功能验证
    - init_project.py 收集 speech_profile
    - ooc-checker 包含声音区分度+内心独白检测

[ ] 2. 角色区分度测试（核心）
    - 用新系统写包含2-3个角色对话的场景
    - 隐去"XX说"标记，评估是否能凭对话内容区分角色
    - ≥70%的对话轮次可正确归属到角色
```

---

## 8. 最终验证

### T6.1 — 端到端写作测试

**任务ID**: T6.1
**依赖**: 所有QG通过
**状态**: [ ] 未开始

#### 描述
用完整升级后的 ink-writer 系统写一本新书的前3万字（~12章），全面评估质量。

#### 执行步骤
1. 选择热门题材（参考 market-heat-map.md）
2. 运行 ink-init（含商业包装步骤）
3. 运行 ink-plan（审核优化模式）
4. 逐章运行 ink-write 写前12章
5. 运行 ink-review（Full+模式）对全部12章做审查

#### 验收标准
1. 全部12章完成，无流程报错
2. 审查评分均值 ≥88
3. anti-detection 评分均值 ≥90
4. 黄金三章评分 ≥85
5. 10秒扫读测试通过（书名+简介+第1段有吸引力）
6. 人工阅读前3章，无明显AI感

---

### T6.2 — 起点投稿验证

**任务ID**: T6.2
**依赖**: T6.1
**状态**: [ ] 未开始

#### 描述
将 T6.1 产出的新书投稿起点中文网，验证是否通过编辑审核。

#### 执行步骤
1. 检查书名/简介的商业化程度
2. 确保前3万字满足起点提交要求
3. 投稿到对应题材编辑组
4. 等待审核结果

#### 最终验收
- **通过**：起点编辑签约或给予"重点跟进"评级
- **未通过但有反馈**：记录编辑反馈，作为下一轮迭代的输入
- **未通过无反馈**：分析可能原因，调整策略

---

## 9. 文件变更清单（完整）

| 文件路径 | 操作 | 任务ID |
|---------|------|--------|
| `benchmark/scraper.py` | 新增 | T1.1 |
| `benchmark/config.py` | 新增 | T1.1 |
| `benchmark/stat_analyzer.py` | 新增 | T1.3 |
| `benchmark/craft_analyzer.py` | 新增 | T1.4 |
| `benchmark/craft_prompts/*.md` | 新增 | T1.4 |
| `benchmark/compare.py` | 新增 | T1.5 |
| `benchmark/validate_qg1.py` | 新增 | T1.6 |
| `benchmark/style_benchmark.json` | 生成 | T1.3 |
| `benchmark/craft_lessons/*.md` | 生成 | T1.4 |
| `benchmark/gap_analysis.md` | 生成 | T1.5 |
| `ink-writer/agents/writer-agent.md` | **重构** | T2.1, T2.2 |
| `ink-writer/agents/context-agent.md` | 修改 | T2.2, T2.5 |
| `ink-writer/references/scene-craft/combat.md` | 新增 | T2.3 |
| `ink-writer/references/scene-craft/dialogue.md` | 新增 | T2.3 |
| `ink-writer/references/scene-craft/emotion.md` | 新增 | T2.3 |
| `ink-writer/references/scene-craft/suspense.md` | 新增 | T2.3 |
| `ink-writer/references/scene-craft/climax.md` | 新增 | T2.3 |
| `ink-writer/scripts/data_modules/writing_guidance_builder.py` | 修改 | T2.4 |
| `ink-writer/skills/ink-init/SKILL.md` | 修改 | T3.1 |
| `ink-writer/references/shared/commercial-packaging.md` | 新增 | T3.1 |
| `ink-writer/references/market-heat-map.md` | 新增 | T3.1 |
| `ink-writer/agents/golden-three-checker.md` | 升级 | T3.2 |
| `ink-writer/skills/ink-plan/SKILL.md` | 修改 | T3.3 |
| `ink-writer/references/shared/golden-opening-patterns.md` | 新增 | T3.4 |
| `ink-writer/skills/ink-write/references/anti-detection-writing.md` | **重写** | T4.1 |
| `ink-writer/references/shared/ai-word-blacklist.md` | 新增 | T4.2 |
| `ink-writer/agents/anti-detection-checker.md` | 升级 | T4.3 |
| `ink-writer/agents/polish-agent.md` | 修改 | T4.4 |
| `ink-writer/scripts/init_project.py` | 修改 | T5.1 |
| `ink-writer/agents/ooc-checker.md` | 修改 | T5.2 |

---

## 10. 断点恢复指南

当上下文断开后，新的 AI 会话应执行以下步骤恢复：

```
1. 读取本文档: /Users/cipher/AI/ink/ink-writer/docs/quality-upgrade-dev-guide.md
2. 找到「进度追踪」章节（第2章）
3. 找到最后一个 [x] 标记的任务
4. 从下一个 [ ] 任务继续
5. 如果该任务有依赖（标注在任务详情中），先验证依赖任务的产出是否存在
6. 执行任务，完成后更新进度追踪中的 checkbox
7. 如果完成了某个Phase的最后一个任务，执行对应的QG质量门禁
```

**关键命令**：
```bash
# 快速查看当前进度
grep -n '\[x\]\|^\- \[ \]' /Users/cipher/AI/ink/ink-writer/docs/quality-upgrade-dev-guide.md

# 验证某个Phase的产出是否存在
ls -la /Users/cipher/AI/ink/ink-writer/benchmark/  # Phase 1 产出
ls -la /Users/cipher/AI/ink/ink-writer/ink-writer/references/scene-craft/  # Phase 2 产出
```

---

## 11. 使用 Superpowers 辅助开发

每个Phase的开发应使用以下 superpowers skills：

| 阶段 | Superpowers Skill | 用途 |
|------|-------------------|------|
| 开始每个Phase前 | `superpowers:brainstorming` | 确认实现方向 |
| 编写代码前 | `superpowers:writing-plans` | 细化实现方案 |
| 写代码时 | `superpowers:test-driven-development` | TDD开发 |
| 并行任务时 | `superpowers:dispatching-parallel-agents` | 并行执行独立任务 |
| 执行计划时 | `superpowers:executing-plans` | 按计划执行+检查点 |
| 完成代码后 | `superpowers:verification-before-completion` | 验证通过再声明完成 |
| 完成Phase后 | `superpowers:requesting-code-review` | 代码审查 |
| 收到审查后 | `superpowers:receiving-code-review` | 处理审查反馈 |
| 完成所有开发 | `superpowers:finishing-a-development-branch` | 分支完成流程 |
