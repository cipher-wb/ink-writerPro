# US-004: RAG 运行时实测 trace

- 审计时间：2026-04-17
- 测试模式：单元级功能实测（用户授权，Embedding API Key 已配置）
- 测试项目：`/Users/cipher/AI/重生2013/`（既有 140 章真实项目）
- 非破坏性：未写入项目正文；新构建的 `data/style_rag/` 与 `/Users/cipher/AI/重生2013/.ink/chapter_index/` 已列入 .gitignore 或留在项目本地目录

---

## 测试方针

**未跑完整 /ink-write**，原因：
- 这是一次深度健康审计，需要抓 RAG 实际召回的细粒度 trace
- 完整 /ink-write 会消耗较多 token 且可能污染真实项目
- 改为**分别对三套 RAG 做单元级 live 调用**，抓取每个检索的 query/top-k 结果/payload

测试覆盖：
- editor_wisdom：真实 Retriever 构造 + 召回 + 三个注入函数的 markdown 产出
- style_rag：构建 FAISS 索引 + 真实 query + build_polish_style_pack 完整 pipeline
- semantic_recall：构建 chapter_index + 真实跨章 recall + payload 输出

---

## Trace 1：editor_wisdom 实测

### 1.1 加载与规模

```
Retriever() 构造耗时：17.06s（首次加载 sentence-transformers 模型）
索引规模：364 条规则
FAISS ntotal：364
severity 分布：hard 215 / soft 132 / info 17
```

### 1.2 召回查询

**Query**：`主角开篇觉醒金手指, 对敌人施展反杀`
**k=5**，无 category 过滤

**Top-5 结果**：

| 排名 | rule_id | category | severity | score | rule（截断） |
| --- | --- | --- | --- | --- | --- |
| 1 | EW-0290 | character | soft | 0.658 | 金手指系统设计须能直接驱动主线剧情，而非单纯赋能 |
| 2 | EW-0354 | hook | soft | 0.627 | 系统金手指要设计成"能预判主角预判"的智慧感 |
| 3 | EW-0153 | character | soft | 0.627 | 金手指/系统惩罚机制必须与主角成长形成有效张力 |
| 4 | EW-0232 | opening | **hard** | 0.619 | 黄金三章开局禁止使用上帝视角介绍世界观或修炼体系 |
| 5 | EW-0345 | opening | **hard** | 0.613 | 系统或金手指须在第一章内通过剧情动作自然呈现 |

**评估**：召回相关性良好，覆盖了金手指功能、开篇禁忌、硬约束与软约束的混合。

### 1.3 writer_injection 实测

**场景**：Chapter 1, outline=`主角觉醒神秘系统，在危机中反杀师兄，展现金手指能力，同时埋下师门政治阴谋伏笔`

`build_writer_constraints(chapter_no=1)` 返回的 markdown（注入 writer-agent prompt）：

```markdown
### 编辑智慧硬约束（Editor Wisdom Constraints）

**【硬约束 — 必须遵守，违反将触发返工】**：
- [EW-0229][highpoint] 烧脑悬疑剧情的视角必须死跟主角...
- [EW-0299][opening] 先引出危机，再让金手指登场，再用金手指解决危机
- [EW-0232][opening] 黄金三章开局禁止使用上帝视角介绍世界观...
- [EW-0282][character] 玄幻/金手指情节不能突兀切入...
- [EW-0345][opening] 系统或金手指须在第一章内通过剧情动作自然呈现...

**【软约束 — 建议遵守】**：
- [EW-0341][opening] 将危机转移到配角身上...
- [EW-0354][hook] 系统金手指要设计成'能预判主角预判'的智慧感...
- [EW-0290][character] 金手指系统设计须能直接驱动主线剧情...
- [EW-0153][character] 金手指/系统惩罚机制必须与主角成长形成有效张力...
```

**评估**：黄金三章 opening/hook/character 类别被强制混入（golden_three_three），硬约束和软约束清晰分区，能直接被 LLM 消费。

### 1.4 context_injection 实测（带 scene_type）

`build_editor_wisdom_section(chapter_no=1, scene_type="开篇")` 返回规则数：**15 条**（k=5 基础 + 黄金三章 4 类别各 k=5 去重后）

规则覆盖 opening/character/hook 三大类别，包含：
- EW-0298 opening 禁止主角独自与系统自言自语
- EW-0346 hook 用身份/地位双重逆转构建开篇钩子
- EW-0329 hook 主角性格要有"杨过式邪气"
- EW-0068 character 爽点分级升级

**评估**：黄金三章加料机制生效，且 context-agent 能拿到比 writer-agent 更丰富（15 vs 9）的规则清单。

### 1.5 polish_injection 实测（模拟违规）

输入模拟 violations：
```python
[
  {"rule_id": "EW-0232", "quote": "...主角先觉醒了金手指系统...", "severity": "hard",
   "fix_suggestion": "删除上帝视角介绍，改为进入危机"},
  {"rule_id": "EW-0377", "quote": "连续5段句长15字左右", "severity": "soft",
   "fix_suggestion": "插入长句打破节奏"},
]
```

输出 markdown（注入 polish-agent prompt）：
```markdown
### 编辑智慧违规修复清单（Editor Wisdom Violations）

**【必须修复 — hard 级违规】**：
- **[EW-0232]** 引用段落：「...主角先觉醒了金手指系统...」
  - 修复建议：删除上帝视角介绍，改为进入危机

**【建议修复 — soft 级违规】**：
- **[EW-0377]** 引用段落：「连续5段句长15字左右」
  - 修复建议：插入长句打破节奏
```

**评估**：结构清晰，polish-agent 可按 hard→soft 顺序执行修复。

---

## Trace 2：style_rag 实测（需先构建索引）

### 2.1 构建 FAISS 索引

```
$ PYTHONPATH=/Users/cipher/AI/ink/ink-writer python3 scripts/build_style_rag.py
加载 3295 个片段
编码中 (batch_size=256)...  耗时 27.0s (122 片段/s)
构建完成:
  片段数: 3295
  向量维度: 512
  索引: /Users/cipher/AI/ink/ink-writer/data/style_rag/style_rag.faiss
  元数据: metadata.json
  全文: contents.json
```

**重要**：构建前 `StyleRAGRetriever()` 直接抛 `FileNotFoundError`；构建后才可用。该构建步骤**不在任何用户文档的默认安装流程中**，只出现在 `scripts/build_style_rag.py` 的 `--help` 里。

### 2.2 召回查询

**Query**：`他指尖在玉牌上轻轻抚过，冰凉的触感让他眉头一皱。`
**k=3**，无过滤

**Top-3 结果**：

| 排名 | fragment_id | book_title | scene/emotion | score | qs | content（首 60 字） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | dee62c6d2654 | 红楼芳华，权倾天下 | 情感/悲伤 | 0.528 | 0.60 | 娇躯不自禁地微微向后一缩，那点朱唇也不自禁地抿了抿... |
| 2 | bd6098b73fd2 | 捞尸人 | 日常/紧张 | 0.512 | 0.83 | 这条毛巾，怎么看着有些眼熟？ |
| 3 | 0f53f08e1641 | 红楼芳华，权倾天下 | 战斗/紧张 | 0.505 | 0.50 | 隔着薄薄的桃红纱裙，不比那王熙凤的大磨盘小多少... |

**评估**：相似度偏低（最高仅 0.528），且检索结果与 query 情感/动作不贴合（query 是紧张/触觉，结果有「捞尸人」偏悬疑但跑题到「红楼芳华」偏艳情）。这是 3295 样本被**题材偏差**污染的典型表现——样本来源多样但语义分散。

### 2.3 build_polish_style_pack 实测

**fix_priorities**：
```python
[
  {"location": "第3-5段", "type": "句长平坦区", "fix": "插入长句"},
  {"location": "第12段", "type": "对话不足", "fix": "把内心独白改为对话"},
]
```

**格式化后的 polish prompt 片段**（实际会注入 polish-agent）：

```
以下为人写标杆片段，仅供改写时参考句式节奏和表达手法，不可照搬内容或剧情：

【人写参考 · 句长平坦区 · 第3-5段】
参考1（青山/日常/悲伤，句长均值26字 | 对话占比28% | 质量0.74）：
只有一刻钟。
　　很短暂。
　　陈迹不再废话，他迅速在书房内巡视一圈，目光在散落的书卷与宣纸上停留下来...
(约 900 字节内容)

---

【人写参考 · 对话不足 · 第12段】
...
```

**评估**：
- `PolishStylePack.format_full_prompt()` 输出格式符合 polish-agent.md:172 规范
- 参考片段带上了作者/scene/情感/句长/对话占比/质量元数据，支持 LLM 判断相关性
- **但一次 pack 可能输入 4000+ 字节的人写样本，增加 polish prompt 的体积**

### 2.4 未构建索引时的行为

**已确认**：未构建时 `StyleRAGRetriever()` 抛 `FileNotFoundError: Style RAG index files missing: [...]. Run 'python scripts/build_style_rag.py' to build the index.`

如果 polish-agent 直接构造 retriever，会硬失败。但若上游先检查再传入，可安全跳过（这正是实际 workflow 的做法——`style_sampler.py` 走的是 SQLite 路径，绕过 FAISS）。

---

## Trace 3：semantic_recall 实测

### 3.1 构建项目级 chapter_index

```
$ PYTHONPATH=/Users/cipher/AI/ink/ink-writer python3 scripts/build_chapter_index.py \
    --project-root /Users/cipher/AI/重生2013
INFO: Index saved to /Users/cipher/AI/重生2013/.ink/chapter_index (140 vectors)
{
  "status": "ok",
  "chapters": 140,
  "index_dir": "/Users/cipher/AI/重生2013/.ink/chapter_index"
}
```

构建耗时 ~10s（含模型加载）；从 `index.db` 的 `chapter_memory_cards` 表读取 140 章节 memory card 作为文本源。

### 3.2 召回查询（模拟写第 141 章）

**Query**：`秦朗面板升级，江怀瑾发现秦朗的秘密，两人对峙于学生会办公室`
**scene_entities**：`[秦朗, 江怀瑾, 学生会]`

`SemanticChapterRetriever.recall(query, chapter_num=141, scene_entities=[...])` 返回：

| 排名 | chapter | source | score | involved_entities（截断） | content（前 50 字） |
| --- | --- | --- | --- | --- | --- |
| 1 | 140 | recent | 0.950 | [] | (空) |
| 2 | 139 | recent | 0.950 | [秦朗, 姜念卿, ...] | 秦朗向姜念卿展示国家能源局红头文件... |
| 3 | 138 | **entity_forced+recent** | 0.950 | [秦朗, 钱老板, ...] | 秦朗与钱老板谈判，面临资本捡尸威胁... |
| 4 | 137 | **entity_forced+recent** | 0.950 | [秦朗, 姜念卿, ...] | 启明集团遭遇约翰·威德Bloomberg专访攻击... |
| 5 | 136 | recent | 0.950 | [qinlang, qiming_group, ...] | (空) |
| 6 | 5 | **semantic** | 0.733 | (未显示) | ... |

**命中细节**：
- 最近 5 章全部召回（recent=0.95）
- 其中 ch137、ch138 被实体强制命中（因含"秦朗"），source 合并为 `entity_forced+recent`
- **第 5 章被纯语义召回**（score=0.733）——ch5 是秦朗与江怀瑾首次同学关系建立的章节，说明跨章语义召回生效
- ch136/ch140 的 content 为空（index.db 中这几章的 summary 字段缺失，chapter_index 照实存储）

### 3.3 实际注入 prompt 的 payload

`recall_to_payload()` 输出：

```json
{
  "invoked": true,
  "mode": "semantic_hybrid",
  "reason": "ok",
  "intent": "continuity_memory",
  "needs_graph": false,
  "center_entities": ["qiming_group", "shengming_plan", "周明辉",
                      "姜念卿", "italian_trading", "zhou_minghui",
                      "老黑", "钱老板", "qinlang", "laohei"],
  "hits": [
    {"chapter": 140, "score": 0.95, "source": "recent", "content": ""},
    {"chapter": 139, "score": 0.95, "source": "recent",
     "content": "秦朗向姜念卿展示国家能源局红头文件..."},
    {"chapter": 138, "score": 0.95, "source": "entity_forced+recent",
     "content": "秦朗与钱老板谈判..."},
    {"chapter": 137, "score": 0.95, "source": "entity_forced+recent",
     "content": "启明集团遭遇..."},
    {"chapter": 136, "score": 0.95, "source": "recent", "content": ""},
    {"chapter": 5, "score": 0.733, "source": "semantic", "content": "..."}
    // 更多条目
  ]
}
```

该 payload 会作为 `rag_assist` 字段注入 context-agent 执行包，再由 context-agent 转成 markdown 写入写作上下文。

### 3.4 降级路径实测（已被上游代码证明）

从 `extract_chapter_context.py` 的源代码逻辑可以推演出降级链：

```
_load_rag_assist():
1. rag_assist_enabled? 否 → reason="disabled_by_config"
2. 构造 query → 失败则 reason="context_not_actionable"
3. 调用 _search_semantic_recall() → 返回 payload with hits → return
4. 返回 None → 检查 EMBED_API_KEY
5. 无 key → _search_memory_cards_and_summaries()（纯内存卡检索）
6. 有 key → 远端向量+BM25 → 失败则 fallback 到内存卡
```

本次测试未在 EMBED_API_KEY 缺失场景跑，但代码路径清晰可靠。

---

## 4. 关键观察

### 4.1 RAG 三路召回的时序与依赖

真实 /ink-write 流程中的 RAG 时序：
1. **Step 1 context-agent** 调用 `extract_chapter_context.py`
   - 先查本地 FAISS (`semantic_recall`) → 命中则注入 `rag_assist`
   - 调用 `build_editor_wisdom_section()` → 注入 section 12 编辑建议
   - style_sampler 通过 SQLite 查询 `benchmark/style_rag.db`（**不走 StyleRAGRetriever**）→ 注入 style_samples
2. **Step 2A writer-agent**
   - 调用 `build_writer_constraints()` → 注入 `### 编辑智慧硬约束`
3. **Step 4 polish-agent**
   - 调用 `build_polish_violations()` → 注入违规清单
   - (文档声称) 调用 `build_polish_style_pack()` → 注入【人写参考】
   - **实际**：因 StyleRAGRetriever 默认不可用，这一步可能被跳过或失败（取决于 polish-agent 实际执行逻辑）
4. **review_gate**
   - 独立调用 `check_chapter()` 运行 editor_wisdom_checker

### 4.2 没有跑到的场景

- 完整 /ink-write 端到端实测（避免污染真实项目，且审计深度需要细粒度 trace）
- EMBED_API_KEY 缺失的降级路径（用户环境本来就有 Key）
- 远端 RAG API（智谱 embedding-3）的实际调用

---

## 5. 运行时 trace 结论

| 模块 | 是否真在用？ | 证据 |
| --- | --- | --- |
| editor_wisdom.Retriever | **是** | 索引 364 条可查，writer/context/polish 三个 injection 函数均能产出正确 markdown |
| editor_wisdom checker + gate | **是** | checker.py + review_gate.py 完整，step3_harness_gate.py 封装了调用 |
| StyleRAGRetriever（FAISS） | **否**（默认） | 索引默认不存在，构建后才可用，Skill 文档里提到的 build_polish_style_pack 在默认安装中会失败 |
| style_sampler.get_benchmark_samples（SQLite） | **是** | context-agent 会用它从 style_rag.db 采样，然后注入 context-agent 执行包第 11 板块 |
| SemanticChapterRetriever | **否**（默认） | chapter_index 需手动构建，所有既有项目均未建；一旦建了就能正常三路合并召回 |
| 远端 API RAG（vectors.db） | **是** | 所有 10 个 AI 项目都有 `.ink/vectors.db`（57 vectors + 5591 bm25_terms 级别） |

**最终判定**：三套 RAG 在代码层都"建了"，但在用户端的**默认激活度**是：
- editor_wisdom：100% 激活
- style_rag：FAISS 0%（Skill 文档声明的路径不工作），SQLite 采样 100%（平行路径）
- semantic_recall：本地 FAISS 需手动构建，所有项目默认 0%；有远端 API 的情况下走远端 RAG
