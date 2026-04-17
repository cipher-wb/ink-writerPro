# US-004: RAG 三系统深度审查（静态）

- 审计时间：2026-04-17
- 审计范围：ink_writer/editor_wisdom、ink_writer/style_rag、ink_writer/semantic_recall
- 审计模式：静态代码 + 索引文件健康度 + 冲突/降级路径

---

## Executive Summary（每系统一句）

| 子系统 | 状态 | 一句话 |
| --- | --- | --- |
| editor_wisdom | **functional** | 364 条规则 FAISS 索引已构建，Retriever/Writer/Context/Polish 注入链路完整，硬门禁有效。 |
| style_rag | **broken-by-default** | 3295 片段存在于 SQLite，但 FAISS 索引目录 `data/style_rag/` 默认不存在；Skill/Agent 文档引用的 `build_polish_style_pack()` 在未构建时会抛 `FileNotFoundError`，需手动跑 `scripts/build_style_rag.py`；实际写作链还存在一条平行的 SQLite 直查路径（`style_sampler.get_benchmark_samples`），这使得 StyleRAGRetriever 在默认 workflow 中基本不被消费。 |
| semantic_recall | **partial** | 代码与配置链路正常，FAISS 索引按项目独立构建（`.ink/chapter_index/`），但多数既有项目尚未构建索引；数据写入仍依赖 `index.db.review_metrics` 生成 chapter memory card；流程中由 `extract_chapter_context.py` 优先尝试，失败后降级到 remote RAG API / 内存卡。 |

---

## 1. editor_wisdom（编辑星河智慧）

### 1.1 索引文件

| 项 | 值 |
| --- | --- |
| 索引目录 | `/Users/cipher/AI/ink/ink-writer/data/editor-wisdom/vector_index/` |
| FAISS 文件 | `rules.faiss`（728 KB, mtime 2026-04-15）|
| 元数据 | `metadata.json`（184 KB）|
| FAISS `ntotal` | **364** |
| metadata 条数 | **364** |
| `data/editor-wisdom/rules.json`（源） | **388 条**（比索引多 24 条，可能是部分规则在 06_build_index 阶段被过滤） |
| severity 分布 | hard 215, soft 132, info 17 |
| category 分布 | opening 102, taboo 73, ops 51, genre 42, character 30, pacing 25, hook 22, highpoint 12, misc 7 |
| embedding 维度 | 512（BAAI/bge-small-zh-v1.5） |

**数量核验结论**：PRD 口径「288 条」**不成立**——当前索引实际 364 条，规则源 388 条。差异点：
- 288 可能是早期口径（pre US-017 之前）
- 索引和源 JSON 之间有 24 条丢失，需检查 `scripts/editor-wisdom/06_build_index.py` 的过滤逻辑
- 文档（CLAUDE.md）里的 288 数字已过时

### 1.2 召回代码路径

`ink_writer/editor_wisdom/retriever.py`

- **Query 构造**：直接用 `chapter_outline` 或 `chapter_outline + scene_type` 作为查询文本（见 `context_injection.py:67-69`）
- **top-k**：由 `config.retrieval_top_k`（默认 5）控制，支持 `category` 过滤
- **排序**：FAISS `IndexFlatIP`（cosine 相似度，向量归一化后）
- **黄金三章加料**：`chapter_no <= 3` 时，额外召回 `GOLDEN_THREE_CATEGORIES = {opening, hook, golden_finger, character}` 类别各 k 条并去重合并（writer_injection.py:77-85 / context_injection.py:84-92）

### 1.3 注入 prompt 位置

| 下游 | 入口 | 文件:行 |
| --- | --- | --- |
| context-agent | `build_editor_wisdom_section()` → section 12 | `ink_writer/editor_wisdom/context_injection.py:47-96` |
| writer-agent | `build_writer_constraints()` → `### 编辑智慧硬约束` | `ink_writer/editor_wisdom/writer_injection.py:43-91` |
| polish-agent | `build_polish_violations()` + `generate_patches()` | `ink_writer/editor_wisdom/polish_injection.py:54-81, 84-111` |
| review gate | `run_review_gate()` + `check_chapter()` | `ink_writer/editor_wisdom/review_gate.py:78-168` + `checker.py:73-147` |
| step3 harness | `run_editor_wisdom_gate()` | `ink-writer/scripts/step3_harness_gate.py:106-158` |

### 1.4 硬门禁

- `hard_gate_threshold = 0.75`（配置文件已调整为 0.75）
- 黄金三章 `golden_three_threshold = 0.92`（US-017 后从 0.85/0.90 提升）
- `check_chapter()` 打分公式：`max(0, 1 - 0.3*hard - 0.1*soft)`（checker.py:62-70）
- `run_review_gate()` 最多 3 次 polish 重试；超过则写 `chapters/{n}/blocked.md` 硬阻断

### 1.5 降级路径

- 索引缺失 → `EditorWisdomIndexMissingError`
  - `context_injection.py:73-79` 和 `writer_injection.py:62-71` 分别处理：`config.enabled=True` 时抛出，否则返回空 section
  - **风险**：默认 `enabled=True`，索引一旦缺失就硬失败，没有 BM25 降级
- API Key 缺失 → `checker.py:116` 分支：有 anthropic_client 时走 SDK，否则走 `claude -p` CLI（llm_backend.py）
  - **降级存在**，但只针对 checker，不影响 retriever

---

## 2. style_rag（人写风格参考）

### 2.1 索引文件

| 项 | 值 |
| --- | --- |
| 期望索引目录 | `/Users/cipher/AI/ink/ink-writer/data/style_rag/` |
| 索引存在？ | **默认不存在**（已被 .gitignore 新增忽略，需手动构建） |
| 源 SQLite | `benchmark/style_rag.db`（32.3 MB，表 `style_fragments`） |
| SQLite 片段数 | **3295**（与 PRD 一致） |
| 总字数 | 约 940 万字 |
| scene_type 分布 | 日常 1855 / 战斗 920 / 情感 265 / 对话 156 / 过渡 48 / 悬念 29 / 高潮 22 |
| emotion 分布 | 轻松 1214 / 紧张 1080 / 热血 705 / 悲伤 184 / 愤怒 64 / 震惊 38 / 温馨 10 |
| quality_score 范围 | 0.40 – 0.94（均值 0.65） |
| 构建脚本 | `scripts/build_style_rag.py`（实测构建成功，产出 FAISS 3295 条 × 512 维，~27 秒） |

**数量核验结论**：3295 片段确实存在于 SQLite，但 **FAISS 索引默认不存在**——这意味着 `StyleRAGRetriever` 构造会直接抛 `FileNotFoundError`。

### 2.2 召回代码路径

`ink_writer/style_rag/retriever.py`

- **Query 构造**：由 `polish_integration._extract_paragraph_text()` 从 `anti-detection-checker.fix_priority[i].location` 字段解析「第 X 段 / 第 X-Y 行」等位置，抽原文作为 query（`polish_integration.py:97-128`）
- **top-k**：默认 3，支持 `scene_type/emotion/genre/min_quality` 过滤
- **FAISS_reconstruct + dot** 实现筛选子集检索（retriever.py:116-131）

### 2.3 注入 prompt 位置（文档声明）

- **声明**：`ink-writer/agents/polish-agent.md:168-176`、`ink-writer/skills/ink-write/SKILL.md:1604-1607`
- **入口函数**：`build_polish_style_pack()`（`ink_writer/style_rag/polish_integration.py:131-190`）
- **注入点**：Step 4 polish 前的 `【人写参考】` 块，通过 `PolishStylePack.format_full_prompt()` 生成

### 2.4 平行路径（实际被使用的那条）

发现**第二条 style 采样路径**：
- `ink-writer/scripts/data_modules/style_sampler.py:418-490` 提供 `get_benchmark_samples()` / `select_benchmark_for_chapter()`
- **不走 FAISS**，直接 SQLite `ORDER BY quality_score DESC` + scene_type/emotion/genre 过滤
- 该模块是 context-agent 用于写入 `style_samples` 的路径，是**默认启用的 fallback 路径**

结果：`StyleRAGRetriever` 在项目默认配置下几乎**不会**被调用；用户要求时需显式初始化并传入，而 Skill 文档只给"应该调用"的说明，未给"如何 fallback"。

### 2.5 降级路径

- 索引缺失 → `FileNotFoundError`（retriever.py:50-54）：**没有 fallback，没有 BM25 降级**
- `polish_integration.build_polish_style_pack(retriever=None)`：不会主动构造 retriever，如果上游传 None 将遍历为空 references（因 `retriever.retrieve()` 会 NoneType 异常被 try/except catch，见 `polish_integration.py:167-180`），返回空 pack 但不抛错
- style_sampler 路径：SQLite 文件缺失时返回空列表，静默降级（style_sampler.py:430-431）

---

## 3. semantic_recall（跨章语义召回）

### 3.1 索引文件

| 项 | 值 |
| --- | --- |
| 期望位置（项目级） | `<project_root>/.ink/chapter_index/chapters.faiss` + `chapters_meta.json` |
| 全局索引 | **无**（每个小说项目独立构建） |
| 构建脚本 | `scripts/build_chapter_index.py` |
| 现有项目实例 | `/Users/cipher/AI/重生2013/.ink/chapter_index/`（本次审计新建，140 章 × 512 维） |
| 其他 AI 项目检查 | 10 个 ink 项目均有 `vectors.db`（远端 API RAG），但**均无 `chapter_index/`**（即本地语义召回索引） |

**数量核验结论**：本地 FAISS 语义召回索引**默认没被建**——用户环境中所有项目仅有 `.ink/vectors.db`（remote embedding RAG），但 `.ink/chapter_index/`（本地 FAISS）缺失。也就是说 US-302 声明的"无需 API Key 的本地语义召回"需要用户手动跑一次 `build_chapter_index.py` 才能激活。

### 3.2 召回代码路径

`ink_writer/semantic_recall/retriever.py`

- **Query 构造**：由上游 `_build_rag_query()` 从 outline/memory 提取查询文本（`extract_chapter_context.py` 中的 `_build_rag_query`）
- **三路合并**：
  1. `semantic_top_k=8` 纯语义（FAISS cosine）
  2. `entity_forced_max=10` 当前场景实体在历史章节出现过的，强制纳入
  3. `recent_n=5` 最近 N 章强制保留
- **去重与 boost**：同章节多来源合并，`entity_boost_weight=0.15 * min(overlap,3)` 加分；最终 `final_top_k=10` 返回
- **`before_chapter`** 过滤：只召回当前章之前的 chapter card，防止时序泄露（chapter_index.py:197-212）
- **最小分数过滤**：`min_semantic_score=0.3`

### 3.3 注入 prompt 位置

- `extract_chapter_context.py:378-416` 定义 `_search_semantic_recall()`
- `extract_chapter_context.py:459-469` 在 `_load_rag_assist()` 中优先调用本地语义召回；若 payload 空，再走远端 API RAG 或内存卡降级
- 最终 payload 作为 `rag_assist` 字段塞进 context-agent 的执行包（payload 结构见 retriever.py:143-179）

### 3.4 降级路径

```
_load_rag_assist() 决策树：
├── 本地语义召回（.ink/chapter_index/chapters.faiss）存在 & 返回 hits → 使用
├── EMBED_API_KEY 未配置 → _search_memory_cards_and_summaries()（纯本地内存卡）
├── 有 Key → 远端向量+BM25 混合检索
└── 全部失败 → 空 rag_assist，流程继续（不阻断）
```

- **降级链健壮**：三层保障（本地 FAISS → 远端 API → 本地内存卡），任一失败静默降级
- 但 `preflight` RAG 硬门控（SKILL.md:284）**会阻断**：如果 `EMBED_API_KEY` 未配置或 API 不可达，/ink-write 无法启动——这实际上绕过了降级链，强制要求远端 key

---

## 4. 冲突检测

### 4.1 三套 RAG 的作用边界

| 系统 | 作用 | 注入位置 | 强制度 |
| --- | --- | --- | --- |
| editor_wisdom | 编辑规则硬约束 | context/writer/polish prompt + review_gate 硬阻断 | hard（规则违反触发返工） |
| style_rag | 人写参考文风 | polish-agent Step 2.8 的【人写参考】块 | soft（「不可照搬」） |
| semantic_recall | 跨章记忆连续性 | context-agent 执行包的 rag_assist 字段 | soft（continuity_memory intent） |

### 4.2 潜在冲突

**冲突 1：开头风格规则 vs. 人写样本模板**
- editor_wisdom EW-0232（hard）禁止上帝视角开头 / user preference 禁"第 xx 日"时间标记开头
- style_rag 样本中存在「第二天天亮，张来福被一阵喊声吵醒了」这类时间标记开头（`万生痴魔`、`方寸道主` 等）
- 风险：polish 同时接受编辑规则"禁止时间开头"和 style_rag 人写样本"以第二天开头"，LLM 的指令解析可能偏向样本风格
- 缓解：当前 polish-agent 提示词写有"仅供参考句式节奏，不可照搬内容"——属语义约束，不是结构约束

**冲突 2：情感强度规则 vs. 风格样本密度**
- editor_wisdom 可能有"去情感标点"类规则；style_rag 的「红楼芳华」等样本使用大量感叹号
- 当 fix_priority 命中"情感标点不足"时，editor_wisdom 无矛盾；但如果 editor_wisdom 同时有"避免情绪过饱和"规则，就会产生对冲指令
- **未发现统一优先级协议**：没有代码显式定义 editor_wisdom > style_rag 或反之

**冲突 3：semantic_recall 命中旧章剧情与大纲新剧情差异**
- 若跨章 recall 把旧章"主角拒绝合作"的 summary 塞进 prompt，但本章大纲要求"主角接受合作"，可能误导写作
- 缓解：`semantic_recall` 使用 `before_chapter` 过滤（不召回未来章节），但对 outline 剧情翻转没有校验

### 4.3 优先级协议评估

- **没有代码层的 RAG 优先级声明**
- 文档层仅 polish-agent 有文字描述：editor_wisdom violations 按 `hard → soft` 排序处理，style_rag 参考"不可照搬"
- 三套 RAG 各自走独立注入链，没有冲突检测或合并层

---

## 5. 降级路径综合评估

| 场景 | editor_wisdom | style_rag | semantic_recall |
| --- | --- | --- | --- |
| FAISS 索引缺失 | 抛 `EditorWisdomIndexMissingError`（若 enabled=True 硬失败） | 抛 `FileNotFoundError` 无降级 | 静默返回 None，走下一层 |
| sentence-transformers 加载失败 | 抛异常（首次加载 ~15-30s） | 抛异常 | 延迟加载（`_get_model()`），首次用时才加载 |
| ANTHROPIC_API_KEY 缺失 | checker 走 `claude -p` CLI fallback | N/A | N/A |
| EMBED_API_KEY 缺失 | N/A | N/A | 走本地 FAISS，失败再走内存卡 |
| 规则/样本为空 | `check_chapter` 抛 `EditorWisdomIndexMissingError`（enabled=True）或返回 score=1.0 | 返回空 pack | 返回空 hits |

**健壮性评分**：
- editor_wisdom：8/10（有明确异常 + CLI fallback，但索引缺失时无 BM25 降级）
- style_rag：4/10（FAISS 缺失无降级；但平行 SQLite 路径在 style_sampler 里做了事实兜底）
- semantic_recall：9/10（三层降级 + 静默 fallback + 永不阻断主流程）

---

## 6. 关键差异与文档矛盾

### 6.1 数量声明矛盾

| 口径 | 声明 | 实际 |
| --- | --- | --- |
| PRD（本任务） | editor_wisdom 288 条 | 索引 364 条（源 JSON 388） |
| CLAUDE.md | editor_wisdom 288 份写作建议 | 索引 364 条 |
| archive/progress.txt | style_rag 3295 片段 | SQLite 3295（FAISS 默认 0） |

### 6.2 「三套 RAG 协同」的事实真相

PRD 描述「三套 RAG 协同工作」，真实情况：
- editor_wisdom：**真在工作**（索引齐全、注入链完整、硬门禁生效）
- style_rag：**规格完成但未激活**（索引默认缺失、平行 SQLite 路径绕过，LLM 很可能从未见过 StyleRAGRetriever 的 `format_full_prompt()` 输出）
- semantic_recall：**代码完备但索引未建**（每个项目需手动跑 build_chapter_index.py，所有 10 个 AI 项目都没有建）

---

## 7. 整体状态评估

| 维度 | 评分 | 说明 |
| --- | --- | --- |
| 代码完整度 | 9/10 | 三个模块的 Retriever/注入/配置均已实现 |
| 索引就绪度 | 4/10 | editor_wisdom OK；style_rag 默认缺失；semantic_recall 每项目需手动建 |
| 注入链清晰度 | 8/10 | editor_wisdom 完整；style_rag 有平行 SQLite 路径造成歧义；semantic_recall 层次清晰 |
| 降级健壮度 | 7/10 | editor_wisdom 缺 BM25 fallback；style_rag 缺 FAISS fallback；semantic_recall 完整 |
| 冲突协议 | 3/10 | 无代码层协议，仅靠 LLM 语义遵守「不可照搬」 |
| 文档一致性 | 5/10 | 规则条数口径过时；style_rag 双路径未明说；semantic_recall 需手动构建没写在用户指南 |

**综合结论**：`partial`——单个 RAG 子系统质量参差，editor_wisdom 稳健运行，但 style_rag 和 semantic_recall 在用户端默认未激活，「三套协同」在绝大多数实际章节写作中实际是「单套（editor_wisdom）+ 内存卡 + 风格采样器」。
