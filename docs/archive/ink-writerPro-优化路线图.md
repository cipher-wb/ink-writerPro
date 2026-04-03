# ink-writerPro v7.0.1 综合优化路线图

> **生成日期**: 2026-03-31  
> **当前版本**: v7.0.1  
> **当前评分**: 7.25/10 (B级)  
> **目标评分**: 8.5+/10 (A级)  
> **信息来源**: 桌面4份分析文档 + 3轮深度代码审计 + 关键代码行级验证  

---

## 一、现状总结

### 系统强项
1. **工程化质量基线** — 9步流水线 + 10个 Checker + Canary 预检，从流程层面防住基础错误
2. **量化叙事承诺追踪** — narrative_commitments 表 + chase_debt 利息模型，业界首创的"欠债记账"系统
3. **工业化题材适配** — 38套题材模板 + 9套反套路库 + Strand Weave 三线编织

### 三大核心短板
1. **"像人写的"只实现了75%** — POV泄露权重仅5%（过低）；缺"潜台词层"和"叙事声音层"检测
2. **200万字+规模性能退化** — O(N)向量检索、单字BM25分词、上下文预算硬编码8000
3. **Agent规范缺失** — Writer Agent(Step 2A) 和 Polish Agent(Step 4) 无正式定义文件

---

## 二、优化总览

| 批次 | 定位 | 项数 | 预估工期 | 风险等级 |
|------|------|------|----------|----------|
| B0 | 预检：规范/文档修补 | 10项 | 1-3天 | 零风险 |
| B1 | 速赢：小改动大收益 | 6项 | 3-5天 | 零/低风险 |
| B2 | 中等：迁移/逻辑变更 | 7项 | 1-2周 | 低/中风险 |
| B3 | 架构：系统级改进 | 6项 | 1月+ | 中风险 |
| B4 | 远景：长期规划 | 5项 | 远期 | 待评估 |
| **合计** | | **34项** | | |

---

## 三、Batch 0：预检 — 规范/文档修补（零风险）

> 本批次全部为文档变更，不改任何运行时代码，不影响任何现有项目。可并行执行。

### B0-1：创建 Writer Agent 正式规范

| 维度 | 内容 |
|------|------|
| **改什么** | 新建 `agents/writer-agent.md`，将 Step 2A 的行为从 `ink-write/SKILL.md`（约第741-800行）中提取为独立 Agent 规范 |
| **为什么** | 12个 Agent 中，最核心的创作步骤（Step 2A）是唯一没有独立定义文件的。对审计、维护、新贡献者理解系统都是障碍 |
| **具体内容** | Role定义、Input（创作执行包）、Output（章节草稿）、Tools（Write）、防幻觉三定律约束、反AI检测写作指南引用、中文优先约束、字数底线（≥2200字） |
| **文件** | 新建：`ink-writer/agents/writer-agent.md` |
| **风险** | 零 — 纯新增文件 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-2：创建 Polish Agent 正式规范

| 维度 | 内容 |
|------|------|
| **改什么** | 新建 `agents/polish-agent.md`，将 Step 4 的润色/去AI味行为从 `ink-write/SKILL.md`（约第943-1006行）和 `references/polish-guide.md` 中整合为独立 Agent 规范 |
| **为什么** | Step 4 是质量门控的最后防线（修问题 + 去AI味），但其决策逻辑、工具使用、与 Step 4.5 安全校验的关系均无正式定义 |
| **具体内容** | Role定义、Input（Review报告 + Step 2B文本）、Output（润色终稿）、修复优先级逻辑、反AI修复协议、Step 4.5集成方式 |
| **文件** | 新建：`ink-writer/agents/polish-agent.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-3：Style Adapter (Step 2B) 角色澄清

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `references/style-adapter.md` 头部添加元数据和角色定位说明，明确 Step 2B 是内联执行（非独立 Agent） |
| **为什么** | 当前 `ink-write/SKILL.md` 说"执行前加载"暗示内联，但 Agent/子流程边界从未正式声明 |
| **文件** | 修改：`ink-writer/references/style-adapter.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-4：严重度术语统一

| 维度 | 内容 |
|------|------|
| **改什么** | 统一所有12个 Agent 规范中的严重度命名。当前状况：`checker-output-schema.md` 定义了标准枚举 `critical|high|medium|low`，但部分 checker 使用"严重度"列头、大写 CRITICAL 示例等不一致写法 |
| **为什么** | 不一致的严重度命名可导致下游解析失败或修复优先级误判 |
| **文件** | 修改：`ink-writer/agents/` 下全部12个 `.md` 文件 + `references/checker-output-schema.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-5：Review Bundle Schema 补充 narrative_commitments 字段

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `references/review-bundle-schema.md` 中添加 `narrative_commitments` 为可选字段 |
| **为什么** | `consistency-checker.md` Layer 4（约第135行）引用了 `review_bundle.narrative_commitments`，但 Review Bundle Schema 未定义该字段。虽然 checker 做了"如果存在"的优雅降级，但 Schema 应当记录 |
| **文件** | 修改：`ink-writer/references/review-bundle-schema.md` |
| **风险** | 零 — 可选字段添加 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-6：叙事承诺违规严重度规则细化

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `consistency-checker.md` Layer 4 中补充具体的严重度判定规则和示例 |
| **为什么** | 当前 Layer 4 的严重度规则过于简略，LLM checker 会产生不一致的严重度分配 |
| **具体规则** | `critical`：核心誓约（oath类型）被违背且文本中无任何解释/伏笔。`high`：承诺违背 或 人物原则矛盾 且无解释。`medium`：灰色地带行为（可能但反常），需标记待确认 |
| **文件** | 修改：`ink-writer/agents/consistency-checker.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | B0-5 |

### B0-7：Macro-Review Tier2/Tier3 Checker 调用逻辑文档化

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `ink-macro-review/SKILL.md` 中明确标注："Tier2/Tier3 不调用 Checker Agent，直接执行 SQL 分析" |
| **为什么** | 当前文本对是否调用 Checker Agent 存在歧义 |
| **文件** | 修改：`ink-writer/skills/ink-macro-review/SKILL.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-8：ink-query 角色定位澄清

| 维度 | 内容 |
|------|------|
| **改什么** | 确认 `/ink-query` 是 Skill（非 Agent），在架构文档中标注"ink-query 通过 Skill 直接执行查询路由，无独立 Agent 定义" |
| **为什么** | 探索中曾误判"Query Agent 规范缺失"，实际 `ink-query/SKILL.md` 已有完整定义（Project Root Guard + 查询路由 + 工具调用），只是不走 Agent 架构 |
| **文件** | 修改：可在项目 README 或架构说明中补充说明 |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-9：Step 依赖关系 DAG 图文档化

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `ink-write/SKILL.md` 或 `references/` 中添加正式的步骤依赖关系 DAG |
| **为什么** | 当前各步骤的硬门控关系散布在 SKILL.md 的 "Step Pre-Validation Protocol"（约第615-639行）中，但无系统化的视觉/形式化表达 |
| **具体DAG** | `Step0 → Step0.5 → Step0.6 → Step0.7 → Step0.8 → Step1 → Step2A → Step2A.5(硬门) → Step2B → Step3 → Step4 → Step4.5(硬门) → Step5 → Step6` |
| **文件** | 修改：`ink-writer/skills/ink-write/SKILL.md` 或新建 `references/pipeline-dag.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B0-10：Golden-Three 与 Proofreading 在第1-3章的覆盖范围澄清

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `step-3-review-gate.md` 中明确 Golden-Three 在前3章覆盖的维度（开篇抓取力、读者承诺、可见变化）与 Proofreading 覆盖的维度（修辞重复、段落结构、代称混乱、文化禁忌）的关系 |
| **为什么** | 当前规则 `proofreading-checker` 条件为 `chapter > 3`，但 Golden-Three 并不覆盖所有 Proofreading 维度。前3章存在文笔质量检查盲区 |
| **建议** | 改为：前3章同时运行 Golden-Three（叙事质量）+ Proofreading（文笔质量），而非互斥 |
| **文件** | 修改：`ink-writer/references/step-3-review-gate.md` |
| **风险** | 零 |
| **兼容性** | 无影响 — 增加检查覆盖度 |
| **依赖** | 无 |

---

## 四、Batch 1：速赢 — 小改动大收益（3-5天）

> 本批次主要是 Agent 规范的参数调整和文档补充，改动小但对检查质量影响显著。

### B1-1：POV 泄露权重 5% → 15% + weights_version

| 维度 | 内容 |
|------|------|
| **改什么** | anti-detection-checker 评分公式中 POV 泄露权重从5%提升至15%；段落结构权重从15%降至5%。添加 `weights_version: "v2"` 标记 |
| **为什么** | 桌面深度评审核心发现：POV泄露是中文AI文本检测的最高影响信号，5%权重严重偏低。段落结构对检测影响远小于POV |
| **文件** | 修改：`ink-writer/agents/anti-detection-checker.md`（评分/权重部分） |
| **风险** | 低 — 仅影响未来 Review 评分，不影响已有数据 |
| **兼容性** | 已写项目重新 review 会看到不同分数。`review_metrics` 表中的历史分数为 v1 版本，不可直接与 v2 比较。需在文档中标注 |
| **依赖** | B0-4 |

### B1-2：Override Contract 可覆盖性矩阵

| 维度 | 内容 |
|------|------|
| **改什么** | 在 reader-pull-checker 或 `references/context-contract-v2.md` 中添加明确矩阵，标注每个软约束是否支持 Override Contract 及允许的申诉理由类型 |
| **为什么** | 当前8种软约束的可覆盖性指引不一致。LLM 可能尝试覆盖硬约束或对合法软约束不使用 Override Contract |
| **示例格式** | `SOFT_HOOK_STRENGTH → 可覆盖 → 允许理由：TRANSITIONAL_SETUP, ARC_TIMING` / `SOFT_PATTERN_REPEAT → 不可覆盖` |
| **文件** | 修改：`ink-writer/agents/reader-pull-checker.md` 或 `ink-writer/references/context-contract-v2.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B1-3：读者模拟器复合题材映射规则

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `reader-simulator.md` 中添加常见复合题材的容忍度映射表 |
| **为什么** | 当前仅有一句"若题材为复合型（A+B），取容忍度更低的那个"，缺乏具体映射。修仙+虐恋、都市+系统、末世+爽文、悬疑+言情等组合需明确 |
| **文件** | 修改：`ink-writer/agents/reader-simulator.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B1-4：高潮检查器质量评级具体示例

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `high-point-checker.md` 中为"迪化误解"、"身份掉马"等复杂爽点模式添加 A/B/C 级的具体判定示例 |
| **为什么** | 质量评估过于抽象（"脑补合理"vs"脑补太刻意"），无法实现一致性评分 |
| **示例** | A级：主角用破布包裹秘宝→配角脑补"此人必是隐世高手"→读者知道只是懒（信息优越感强）。C级：主角打喷嚏→配角脑补"定在思考深邃哲理"→读者觉得配角蠢 |
| **文件** | 修改：`ink-writer/agents/high-point-checker.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

### B1-5：anti-detection-checker 输出格式对齐

| 维度 | 内容 |
|------|------|
| **改什么** | 验证 `anti-detection-checker.md` 的 `fix_priority` 数组结构是否兼容 `checker-output-schema.md` 的统一 `issues` 数组格式，不兼容则对齐或标记为扩展字段 |
| **为什么** | 输出格式不匹配意味着 Step 4 的 Polish 可能无法正确消费 anti-detection 的修复建议 |
| **文件** | 修改：`ink-writer/agents/anti-detection-checker.md`、`ink-writer/references/checker-output-schema.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | B0-4 |

### B1-6：债务交互规则补充

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `references/step-5-debt-switch.md` 中补充：(a) 同一章可否同时创建新债务和偿还旧债务？(b) 逾期债务与新 Override 理由的交互规则？(c) payback_plan 的 due_chapter 已过期时的处理？ |
| **为什么** | 缺少交互规则导致债务追踪可能出现不一致状态 |
| **文件** | 修改：`ink-writer/references/step-5-debt-switch.md` |
| **风险** | 零 |
| **兼容性** | 无影响 |
| **依赖** | 无 |

---

## 五、Batch 2：中等投入 — 迁移/逻辑变更（1-2周）

> 本批次涉及代码修改和数据迁移，每项均包含回退方案和兼容性保证。

### B2-1：BM25 分词引擎升级（jieba替换单字分词）

| 维度 | 内容 |
|------|------|
| **改什么** | 替换 `rag_adapter.py` 第520-529行的 `_tokenize()` 方法：将中文单字分词改为 jieba 词级分词，将英文全匹配 `[a-zA-Z]+` 收窄为行首控制匹配 |
| **当前代码** | `chinese_chars = list("".join(chinese))` — 将"萧炎"拆为["萧","炎"]两个独立字符，丧失词频信号 |
| **目标代码** | `tokens = list(jieba.cut(text))` + 停用词过滤 — 将"萧炎"保留为完整词 |
| **为什么** | 单字BM25分词是200万字+规模性能退化的根因之一。桌面评审和代码审计双重确认 |
| **迁移步骤** | 1. `requirements.txt` 添加 `jieba`<br>2. 备份现有 `vectors.db`<br>3. 执行迁移脚本：清空并重建 `bm25_index` + `doc_stats` 表<br>4. 验证检索质量<br>5. 失败时恢复备份 |
| **文件** | 修改：`ink-writer/scripts/data_modules/rag_adapter.py`（第520-529行）、`ink-writer/scripts/requirements.txt` |
| **风险** | 中 — 改变搜索行为，需迁移，可能影响已有项目检索质量 |
| **兼容性** | 已有项目需运行迁移脚本重建索引。新项目无影响。提供回退方案 |
| **依赖** | 无 |

### B2-2：Mini-Audit 叙事指标增强

| 维度 | 内容 |
|------|------|
| **改什么** | 在 Step 5 数据写入后添加"最近5章平均 Review 分数趋势"检查。查询 `index.db.review_metrics`，计算趋势（上升/稳定/下降），连续3章以上下降时输出警告 |
| **为什么** | 当前系统仅在25/50/200章里程碑检测质量问题，25章的 Quick Audit 间隔是最大的叙事质量盲区（桌面评审核心发现） |
| **文件** | 修改：`ink-writer/skills/ink-write/SKILL.md`（Step 5之后）、可能涉及 `ink-writer/scripts/data_modules/index_reading_mixin.py` |
| **风险** | 低 — 增量功能，非阻塞警告 |
| **兼容性** | 无影响（纯增量） |
| **依赖** | 无 |

### B2-3：Canary 增量模式

| 维度 | 内容 |
|------|------|
| **改什么** | 添加 `--canary-mode incremental` 标志。启用时跳过 A.2（角色停滞，40章窗口）和 A.3（冲突模式重复，30章窗口），保留 A.1（主角同步，不可跳过）、A.4（歧义积压）、A.5（时间线链）、A.6（遗忘伏笔） |
| **为什么** | A.2和A.3查询扫描30-40章窗口，增加每章延迟。快速5章批量写作时，全扫冗余（1章前刚检查过同样的窗口） |
| **性能收益** | 约节省30%的 Canary 扫描时间 |
| **文件** | 修改：`ink-writer/skills/ink-write/SKILL.md`（Step 0.7部分，约第310-577行） |
| **风险** | 低 — 可选模式，默认行为不变 |
| **兼容性** | 无影响（新标志） |
| **依赖** | 无 |

### B2-4：伏笔数据源优先级修正

| 维度 | 内容 |
|------|------|
| **改什么** | 修正 `context-agent.md` 的伏笔读取优先级：从"先读 state.json → 降级读 index.db"改为"优先读 index.db（权威源）→ index.db 不可用时降级读 state.json 快照（标注'可能过期'）" |
| **为什么** | `index.db.plot_thread_registry` 是伏笔的权威数据源（被 Canary、Macro-Review、Audit 统一使用），但 context-agent 当前先读 state.json 快照，可能导致遗漏紧急伏笔 |
| **文件** | 修改：`ink-writer/agents/context-agent.md`（Step 3部分，约第260-282行），可能涉及 `ink-writer/scripts/data_modules/context_manager.py` |
| **风险** | 中 — 改变关键流水线输入的数据源优先级 |
| **兼容性** | state.json 中有伏笔但 index.db 中无的已有项目需要优雅降级（已设计） |
| **依赖** | 无 |

### B2-5：Strand Tracker 更新时序修正

| 维度 | 内容 |
|------|------|
| **改什么** | 在 Review Bundle Schema 中添加 `projected_strand` 字段（当前章的预判 strand 分类），使 Step 3 的 pacing-checker 能看到当前章的 strand 信息（而非总是滞后一章） |
| **为什么** | strand_tracker 在 Step 5（Data Agent）写入，但在 Step 3（pacing-checker）读取 → pacing 分析总是滞后一章，可能漏检 strand 失衡 |
| **文件** | 修改：`ink-writer/references/review-bundle-schema.md`（添加字段）、`ink-writer/agents/pacing-checker.md` |
| **风险** | 低 — 增量可选字段 |
| **兼容性** | 无影响 |
| **依赖** | B0-5 |

### B2-6：角色演化去重规则定义

| 维度 | 内容 |
|------|------|
| **改什么** | 在 `data-agent.md` Step B.7 中明确：(a) 每章每角色最多1条 character_evolution 记录；(b) 若同一章检测到多种变化（如境界提升 + 关系转变），合并为单条记录（`personality_delta` 和 `relationship_delta` 为数组，非标量）；(c) 检测到矛盾变化时标记警告，取最显著变化 |
| **为什么** | 当前"最多1条记录"约束缺乏合并逻辑，可能导致重要变化被静默丢弃或重复条目累积 |
| **文件** | 修改：`ink-writer/agents/data-agent.md`（Step B.7），可能涉及 `ink-writer/scripts/data_modules/index_entity_mixin.py` |
| **风险** | 低 — 规范澄清 + 小幅代码修改 |
| **兼容性** | 已有数据不受影响（增量） |
| **依赖** | 无 |

### B2-7：上下文预算代码与规范对齐

| 维度 | 内容 |
|------|------|
| **改什么** | `context_manager.py` 第148行 `max_chars = max_chars or 8000` 是硬编码默认值，但 `context-agent.md`（第162-197行）定义了动态分层预算：ch1-3=8000、ch4-30=7000、ch31-100=9000、ch101+=11000 + 动态增量（每活跃伏笔+30、每角色出场+50、每未偿债务+100，上限15000）。代码未实现此逻辑 |
| **为什么** | 代码-规范不一致。Agent 规范承诺动态预算，但 Python 后端忽略章节号 → 后期章节上下文不足（9000/11000被截为8000） |
| **注意** | ch4-30 的基础预算为 7000，低于当前硬编码的 8000。这是规范的设计意图（开篇期世界观已加载完毕，信息密度较低）。实施时应尊重规范设计，同时通过动态加分项（伏笔+30、角色+50等）补偿。实际预算 = min(7000 + 动态加分, 15000)，大多数情况下不会低于 8000 |
| **文件** | 修改：`ink-writer/scripts/data_modules/context_manager.py`（第148行及预算逻辑） |
| **风险** | 中 — 改变所有章节的上下文装配行为 |
| **兼容性** | 已有项目可能看到不同的上下文装配结果。ch31+章节质量提升，ch4-30理论上预算降低但动态加分通常补偿 |
| **依赖** | 无 |

---

## 六、Batch 3：架构改进 — 系统级（1月+）

> 本批次涉及新依赖引入、架构变更、流程新增，需要完整测试后上线。

### B3-1：ANN 索引替换暴力向量扫描

| 维度 | 内容 |
|------|------|
| **改什么** | 将 `rag_adapter.py` 中 `_vector_search_rows()` 和 `vector_search()` 的 O(N) 暴力余弦相似度扫描替换为 FAISS IVF-Flat 近似最近邻索引 |
| **当前问题** | 每次查询加载所有向量并逐一计算余弦相似度。200万字/1000+章的项目可能有10K+向量块 |
| **实现方案** | 1. 添加 `faiss-cpu` 依赖<br>2. 在 `vectors.db` 旁创建 FAISS 索引文件<br>3. `store_chunks` 时同时更新 SQLite 和 FAISS<br>4. `vector_search` 使用 FAISS 做 ANN，再从 SQLite 取元数据<br>5. FAISS 索引缺失时回退到暴力扫描（向后兼容） |
| **文件** | 修改：`ink-writer/scripts/data_modules/rag_adapter.py`、`ink-writer/scripts/requirements.txt` |
| **风险** | 中高 — 新依赖，改变搜索路径，需充分测试 |
| **兼容性** | 已有项目通过回退机制兼容。FAISS 索引在首次搜索或迁移命令时构建 |
| **依赖** | B2-1（BM25修复应先于ANN） |

### B3-2：ink-resume 批量级恢复

| 维度 | 内容 |
|------|------|
| **改什么** | 扩展 `ink-resume` 支持批量恢复。当前仅处理单章恢复。`ink-5` 或 `ink-write --batch N` 中途失败后，无法从失败章节续跑，需手动逐章执行或重跑整个批次 |
| **实现方案** | 1. 在 `workflow_state.json` 中添加批量元数据（batch_size、completed_chapters、failed_chapter）<br>2. `ink-resume` 检测批量上下文时，提供"从第N章继续"选项<br>3. 已完成章节不重复执行 |
| **为什么** | ink-5 是日常主力命令。任何中断都需要人工介入，降低工业化效率 |
| **文件** | 修改：`ink-writer/skills/ink-resume/SKILL.md`、`ink-writer/skills/ink-resume/references/workflow-resume.md`、`ink-writer/scripts/workflow_manager.py` |
| **风险** | 中 — 新恢复逻辑，不可损坏现有 workflow state |
| **兼容性** | 已有 workflow_state.json 格式需扩展（新增字段，旧格式正常读取） |
| **依赖** | 无 |

### B3-3：风格锚定机制

| 维度 | 内容 |
|------|------|
| **改什么** | 在前10章写完后计算聚合风格指纹（平均句长、对话比例、感官描写密度、段落长度分布），存储为 `.ink/style_anchor.json`。每100章在 Macro-Review Tier2 中比对当前指标与锚点，偏离超过2个标准差时发出警告 |
| **为什么** | 长篇小说（200+章）在跨会话写作中会出现渐进式风格漂移。无基线锚点则漂移不可检测 |
| **文件** | 修改/新建：`ink-writer/scripts/data_modules/style_sampler.py`（已有基础设施）、新建 `ink-writer/scripts/data_modules/style_anchor.py`、修改 `ink-writer/skills/ink-macro-review/SKILL.md` |
| **风险** | 中 — 新模块，非阻塞警告 |
| **兼容性** | 进行中项目需回填（只读操作，不修改已有数据）。新项目自动生成 |
| **依赖** | 无 |

### B3-4：情感层增强

| 维度 | 内容 |
|------|------|
| **改什么** | (a) Data Agent 流水线添加 Step B.10：潜台词检测器（识别角色"说了但没说"的情感）。(b) Step 4.5 添加"轻量级差分"：对比 Step 2A 草稿与 Step 4 润色稿的情感弧线，检测润色是否导致情感扁平化 |
| **为什么** | Step 4 润色在修复技术问题时可能意外抹平情感潜台词。当前系统无法检测这种"润色后情感丢失" |
| **文件** | 修改：`ink-writer/agents/data-agent.md`（新 Step B.10）、`ink-writer/skills/ink-write/SKILL.md`（Step 4.5增强） |
| **风险** | 中 — 在关键流水线中添加处理步骤 |
| **兼容性** | 无影响（增量功能） |
| **依赖** | B0-2（Polish Agent 规范） |

### B3-5：并发写保护运行时强制

| 维度 | 内容 |
|------|------|
| **改什么** | 当前并发写保护仅为文档约定（多个 Skill 写"禁止并步"但无运行时锁）。`state_manager.py` 使用 `filelock`（第28行）锁 state.json，但无全局工作流锁防止两个 `ink-write` 同时操作同一章。添加 PID 锁机制 |
| **为什么** | 仅靠文档约定不足。用户误开两个会话时可能产生数据损坏 |
| **文件** | 修改：`ink-writer/scripts/workflow_manager.py`（`start_task` 中添加锁获取）、`ink-writer/scripts/data_modules/state_manager.py` |
| **风险** | 中 — 新锁机制，崩溃恢复时可能死锁 |
| **兼容性** | 无影响（增量安全机制） |
| **依赖** | 无 |

### B3-6：批量模式失败处理形式化

| 维度 | 内容 |
|------|------|
| **改什么** | 为 `ink-write --batch N` 和 `ink-5` 定义明确的失败处理：(a) 已完成章节保留不回滚；(b) Phase 2 Review 是否在部分批次上运行；(c) 如何恢复部分批次 |
| **为什么** | 当前 `ink-5/SKILL.md` 仅定义了"唯一允许暂停的情况"，但未定义已完成章节的状态、部分批次的处理、恢复路径 |
| **文件** | 修改：`ink-writer/skills/ink-5/SKILL.md`、`ink-writer/skills/ink-write/SKILL.md`（批量部分） |
| **风险** | 低-中 — 规范 + 小幅逻辑变更 |
| **兼容性** | 无影响 |
| **依赖** | B3-2（批量恢复） |

---

## 七、Batch 4：远景 — 长期规划

> 本批次为"nice-to-have"的远期目标，可根据实际需求选择性实施。

### B4-1：闪回作用域语义规范化
定义正式的"闪回片段"标注格式（Writer Agent 产出 → Data Agent 消费），解决 `data-agent.md` 中"scope=flashback 的 state_changes 不写入 protagonist_state"的语义模糊问题。
**依赖**: B0-1

### B4-2：Chapter Meta 版本化系统
实现版本感知 schema，允许优雅处理旧格式 chapter_meta 条目。state.json 始终存最新版本（version=N），index.db 存历史版本。
**依赖**: B0-5

### B4-3：全链路可观测性管道
扩展现有 `observability.py` + `call_trace.jsonl`，增加：每步耗时分解、Token 用量估算、上下文预算利用率、Checker 分歧率。
**依赖**: 无

### B4-4：指令遵从持久性系统
应对桌面评审发现的"指令遵从在长会话中衰减"问题。在 ink-5 的每 N 步插入"关键约束重注入"（从 SKILL.md 重新呈现核心约束给 LLM，对抗上下文窗口漂移）。
**依赖**: 无（ink-5 已有"关键规则重申"块，但可加强）

### B4-5：跨卷状态迁移工具
小说换卷时，部分状态需重置（位置、当前目标），部分持续（境界、关系）。构建卷过渡工具自动化此流程。
**依赖**: B3-3

---

## 八、依赖关系图

```
B0（全部独立，可并行执行）
│
├── B0-1 ──────────────────────────────→ B3-4, B4-1
├── B0-2 ──────────────────────────────→ B3-4
├── B0-4 ──→ B1-1, B1-5
├── B0-5 ──→ B0-6, B2-5, B4-2
│
▼
B1（大部分独立）
│  B1-1 ← B0-4
│  B1-5 ← B0-4
│
▼
B2（大部分独立）
│  B2-5 ← B0-5
│
▼
B3
│  B3-1 ← B2-1（BM25应先于ANN修复）
│  B3-4 ← B0-2（需 Polish Agent 规范）
│  B3-6 ← B3-2（需批量恢复基础）
│
▼
B4（全部远期）
│  B4-1 ← B0-1
│  B4-2 ← B0-5
│  B4-5 ← B3-3
```

**依赖图验证：无循环依赖。所有依赖链均为单向递进。**

---

## 九、兼容性保证声明

### 对"正在写作的项目"的影响评估

| 批次 | 影响 | 说明 |
|------|------|------|
| B0 | **零影响** | 全部为文档变更，不改任何运行时代码 |
| B1 | **极低影响** | 仅影响未来 Review 评分显示，不改变已有数据。历史分数标注 v1 版本 |
| B2 | **需迁移但可回退** | B2-1（BM25）：提供完整迁移脚本+备份，失败可恢复。B2-7（上下文预算）：只增不减，后期章节质量提升。其余项增量添加 |
| B3 | **有回退机制** | B3-1（ANN）：FAISS 索引缺失时回退暴力扫描。B3-2（批量恢复）：旧 workflow_state.json 正常读取。B3-5（并发锁）：增量安全机制 |
| B4 | **待评估** | 实施前单独评估 |

### 核心原则

1. **只增不减** — 所有优化增加能力，不削减已有功能
2. **提供回退** — 涉及数据变更的项目均提供备份和恢复路径
3. **默认不变** — 新模式/标志默认关闭，需显式启用
4. **渐进迁移** — 不要求一次性全量迁移，支持增量切换

---

## 十、桌面文档12项与本路线图的对应关系

| 桌面编号 | 桌面描述 | 本路线图编号 | 变更说明 |
|----------|----------|-------------|----------|
| 1 | severity 文档统一 | B0-4 | 无变更 |
| 2 | POV权重 5%→15% | B1-1 | 无变更 |
| 3 | 英文正则行首匹配 | B2-1（合并） | 合并入BM25分词升级，非独立项 |
| 4 | BM25 jieba分词 | B2-1 | 合并了桌面项3 |
| 5 | Mini-Audit叙事指标 | B2-2 | 无变更 |
| 6 | Canary增量模式 | B2-3 | 无变更 |
| 7 | ANN索引 | B3-1 | 无变更 |
| 8 | 上下文预算动态公式 | B2-7（调整） | 桌面公式 `max(8000, 8000+log2(ch)*1500)` 与代码中已有的分层体系冲突。改为：对齐 `context-agent.md` 已有分层规范 |
| 9 | ink-resume批量恢复 | B3-2 | 无变更 |
| 10 | 风格锚定机制 | B3-3 | 无变更 |
| 11 | 情感层增强 | B3-4 | 无变更 |
| 12 | *(无第12项，桌面为11项有效)* | — | — |

---

## 十一、实施建议

### 推荐执行顺序

```
第1周：B0全部（并行） + B1全部（并行）
       ↓
第2-3周：B2-1 → B2-7 → B2-2/B2-3/B2-4/B2-5/B2-6（并行）
       ↓
第4-8周：B3-1 → B3-5 → B3-2 → B3-6 → B3-3/B3-4（并行）
       ↓
远期：B4按需选择
```

### 验证检查点

| 检查点 | 时机 | 验证内容 |
|--------|------|----------|
| CP1 | B0+B1完成后 | 所有 Agent 规范内部一致性检查（交叉引用验证） |
| CP2 | B2-1完成后 | BM25检索质量A/B对比测试（新旧分词器） |
| CP3 | B2-7完成后 | 运行现有项目5章写作，验证上下文质量提升 |
| CP4 | B3-1完成后 | 向量检索性能基准测试（100/500/1000章规模） |
| CP5 | B3全部完成后 | 端到端20章写作测试（含中断恢复） |

---

## 附录A：已删除的桌面建议（经源码验证为误报）

以下3项在桌面修改清单中被标记为"删除"，本路线图不包含：

| 编号 | 描述 | 删除原因 |
|------|------|----------|
| A | pending entity patch 字段级合并 | `state_manager.py` 第942/950行已实现 `patch.current_updates.update(value)` 字段级合并 |
| B | `_sync_to_sqlite` 事务化 | `index_manager.py` 第1076行每次创建独立连接，跨连接事务会导致 `database is locked` |
| C | BM25 增量索引 | `rag_adapter.py` 第534行已实现 chunk 级增量：`DELETE FROM bm25_index WHERE chunk_id = ?` |

---

> **文档版本**: v1.0  
> **审计状态**: 已完成3轮自审（详见下方自审记录）  
> **下次更新**: 实施 B0+B1 后更新进度

---

## 附录B：三轮自审记录

### 第一轮自审：依赖关系验证
- [x] 检查所有依赖链是否有循环 → **通过**，全部单向递进
- [x] 检查被依赖项是否排在依赖项之前的批次 → **通过**
- [x] 检查 B3-6 依赖 B3-2 是否合理 → **通过**（批量失败处理需要批量恢复基础）

### 第二轮自审：风险与兼容性验证
- [x] B2-1 BM25迁移是否有数据丢失风险 → **已覆盖**：备份 + 回退方案
- [x] B2-7 上下文预算变更是否可能降低已有章节质量 → **发现问题**：ch4-30的基础预算7000低于当前硬编码8000 → **已确认**：context-agent.md 第165行明确设计为7000（开篇期世界观已加载，信息密度降低），且动态加分项（伏笔+30×N、角色+50×N）通常使实际预算 ≥ 8000 → **处理**：在B2-7正文中添加了注意说明
- [x] B3-5 并发锁崩溃时是否可能死锁 → **已标注**风险，需设计锁超时机制

### 第三轮自审：逻辑一致性验证
- [x] B0-10建议"前3章同时运行 Golden-Three + Proofreading"是否与现有 step-3-review-gate.md 的 Checker 并发限制（max 2）冲突 → **不冲突**：增加 Checker 数量但仍受 max 2 并发限制，只是排队更长
- [x] B1-1 POV权重调整后，桌面文档的评分（§3.4分数6.0）是否需要同步更新 → 桌面文档为外部参考文件，不在本项目管理范围内，不需要同步
- [x] B2-4 伏笔优先级反转后，context-agent 的 fallback 规则是否完整 → **已覆盖**："index.db 不可用时降级读 state.json 快照（标注'可能过期'）"
- [x] 第二轮发现的 B2-7 ch4-30=7000 问题 → **已在正文中添加标注**
