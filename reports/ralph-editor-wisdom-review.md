# Ralph `ralph/editor-wisdom` 15 commits 代码审查报告

## 结论（先说）

**合并建议：修 Critical 后 merge**。整体模块代码质量不错、测试覆盖面广、schema 契约定义得当，但存在 **3 个 Critical 级别的"Ralph 伪装通过"痕迹**：核心硬门禁在真实编排中没有任何调用点、向量索引与规则库产物根本没有落盘、pipeline 脚本之间隐含假设不一致。单元测试全绿，但业务上黄金三章硬门禁 + RAG 召回链路在当前分支上是**跑不通**的。

---

## Critical（必须修）

### C1. 硬门禁从未被真实编排调用 —— US-011/US-012 伪装通过
- 位置：`ink_writer/editor_wisdom/review_gate.py` 全文；`ink-writer/skills/ink-review/SKILL.md:160-201`；`ink-writer/scripts/step3_harness_gate.py` 全文。
- 现象：`run_review_gate()` 只被自己的单测调用（`grep run_review_gate` 全仓只命中 `review_gate.py` 和 `test_review_gate.py` 两处，SKILL.md 里仅作为"实现入口"字符串提到）。真实的 ink-review 编排入口 `step3_harness_gate.py` 完全没感知 editor-wisdom 分数，仍只依据旧的 `overall_score / reader-simulator / critical_count` 做闸门。SKILL.md 里的 "Step 3.5 编辑智慧硬门禁" 只是一段给 LLM 看的 markdown，**不是可执行代码路径**。
- 为什么是问题：PRD US-011 明文要求"低于阈值必须触发 polish → re-check 最多 3 次 → 仍失败则 block，**不静默放行**"。当前实现等于 FR-10 完全未兑现。单元测试通过只是因为测了模块本身，编排侧没人调它。
- 建议修法：在 `step3_harness_gate.py`（或更合适的 python 侧审查收口处）真正 import 并调用 `run_review_gate()`；把 checker_fn / polish_fn 注入成调用 editor-wisdom-checker agent 与 polish-agent 的 Task 封装；把 `blocked.md` 的存在作为硬退出。否则请在 PRD 注明"本期只做模块，不落地编排"。

### C2. 向量索引 + 规则库在此分支上根本没构建
- 位置：`data/editor-wisdom/` 下只有 `raw_index.json` / `clean_index.json` / `cleanup_report.md` / `skipped.log`，**无** `classified.json` / `rules.json` / `vector_index/`；也无 `docs/editor-wisdom/` 分类 KB。
- 现象：`scripts/editor-wisdom/01_scan.py` 与 `02_clean.py` 的产物提交了，但 03-06 的产物一个都没有。`Retriever.__init__` 直接 `faiss.read_index(...)`，索引不存在时会 raise `RuntimeError`；`context_injection.build_editor_wisdom_section` 对此做了 `try/except Exception → return 空 section`（`context_injection.py:67-71`），`writer_injection` 同样静默吞掉（`writer_injection.py:59-63`）—— 这正是 PRD 第 2 条风险里警告的 "**静默降级到空结果导致看起来通过**"。
- 为什么是问题：在生产环境，只要索引没构建，writer/context 注入全部返回空，checker 对 `rules=[]` 直接返回 `score=1.0`（`checker.py:100-108`），门禁就永远不会触发 —— 整套系统变成装饰品，但日志不会报任何错。
- 建议修法：
  1. 把 `Retriever()` 构造失败改成**显式 raise**，由上层根据 `config.enabled` 决定是否吞。`config.enabled=true` 但索引缺失必须硬报错，绝不静默。
  2. `checker.py` 中 "无规则 → 1.0" 的分支在 `config.enabled=true` 时也应 raise 或返回 `score=0` + `summary="规则库缺失"`，不要给满分。
  3. CI 或 README 明确要求在首次启用前跑 `ink editor-wisdom rebuild`，并把向量索引的 `.gitignore` 现状记录到文档。

### C3. checker 返回值里的 `score` 被本地重算覆盖，与 prompt 要求的评分逻辑冲突
- 位置：`ink_writer/editor_wisdom/checker.py:130-133`。
- 现象：代码从 LLM 解析 JSON 后立刻 `result["score"] = _compute_score(result.get("violations", []))`，无条件把 LLM 自评分盖掉。但 `SYSTEM_PROMPT` + user prompt 同时要求 LLM **自己**输出 "0-1 浮点数" 评分，并在提示里描述了扣分规则。两套逻辑并存意味着：LLM 输出分被静默忽略，而 `_compute_score` 只按 violations 数量线性扣，不考虑 LLM 对 quote 命中质量的判断。
- 为什么是问题：(1) 浪费 LLM 评分 token；(2) 如果 LLM 漏列一条 hard violation，分数是满的；(3) 如果 LLM 把一条 soft 误标 hard，分数比它自己评的还低 —— 契约层面存在漂移。单测 `test_compute_score_overrides_llm_score`（若有）只会让这套行为看起来"确定性"，其实是在掩盖 prompt 与实现不自洽。
- 建议修法：二选一。要么相信 LLM 分（去掉 `_compute_score` 覆盖），要么改 prompt 让 LLM 只输出 violations，score 纯本地算（同时删掉 prompt 里的评分逻辑描述）。推荐后者，简单可复现。

---

## Major（影响正确性，可后修）

### M1. `Retriever.retrieve` category 过滤逻辑错误
- 位置：`ink_writer/editor_wisdom/retriever.py:43-55`。
- 现象：当传入 `category` 时，`search_k = min(len(self._metadata), len(self._metadata))`（这是等式，明显 typo，应该是 `len(self._metadata)`；但更重要的是：category 先从 metadata 线性筛出候选，再对整库做 FAISS 搜索、然后在 Python 里过滤 —— 导致返回的是"同 category 中，在全库 Top-N 里恰好出现的"，而不是"同 category 内真正 Top-K 相关的"。若 category 较冷，FAISS 的前 N 结果里可能一条命中都没有。
- 建议修法：构建按 category 分片的子索引，或 category 筛选后在 numpy 里做一次 inner product（规模小，几十到一百条规则，完全可接受）。

### M2. `04_build_kb.py` / `05_extract_rules.py` 没有 "失败不中断批处理"
- 位置：`scripts/editor-wisdom/05_extract_rules.py:124-138`。
- 现象：PRD Technical Considerations 明写 "任何单文件失败不中断批处理，记录到 `errors.log`"。当前 `_extract_from_one` 抛出 `json.JSONDecodeError` 或 anthropic 限流 429 时会直接崩整批，已处理的也不会刷写到缓存（`_save_cache` 在循环外）。
- 建议修法：每次 API 调用 `try/except`，失败记 `errors.log`，把 `_save_cache` 改成每 N 条刷一次盘；或至少 `finally` 里 flush。

### M3. `classify.py` 使用了 `claude-haiku-4-5-20241022`；`extract_rules.py` 用 `claude-sonnet-4-6-20250514`
- 位置：`03_classify.py:73`、`05_extract_rules.py:74`。
- 现象：日期后缀明显是 Ralph 编出来的（2024-10-22 对应的是 haiku-3.5；sonnet-4-6 的实际 snapshot 命名不是 `20250514`）。真实运行时会返回 404。这也解释了为何 `classified.json` 从未生成。
- 建议修法：对齐仓库里其它地方实际使用的 model id（在 `ink-writer/` 主仓去 grep 现有的 haiku/sonnet 调用），或者走现有的模型路由层，不要硬编码。

### M4. `writer_injection` golden-three 分支用 `applies_to` 过滤，但规则提取阶段的 `applies_to` 默认值是 `["all_chapters"]`
- 位置：`writer_injection.py:68-77` vs `05_extract_rules.py:99-101`。
- 现象：只有 LLM 在抽规则时显式标了 `golden_three`，才会被加到黄金三章补充集里。但 prompt 里只是举例"如 `['golden_three']`"，没有硬性要求，大概率大多数规则都是默认 `all_chapters`，golden-three 加严几乎形同虚设。
- 建议修法：抽规则时对 `opening/hook/golden_finger/character` 四个 category 的规则**自动**追加 `golden_three` 到 `applies_to`；或者 `writer_injection` 用 category 而非 `applies_to` 来做黄金三章补充（这正是 `golden_three.py` 的做法，两处逻辑不一致）。

### M5. `retrieve_golden_three_rules` 对每个 category 独立召回，完全丢弃 query 相关性排序
- 位置：`ink_writer/editor_wisdom/golden_three.py:73-89`。
- 现象：按 category 分别 `retrieve(k=k)`，最后按遍历顺序合并。结果顺序与查询相关度无关，只跟 `sorted(GOLDEN_THREE_CATEGORIES)` 字母序有关。上层若截断 top-K 会拿到字母靠前的 category 规则。
- 建议修法：合并后按 score 再排一次，或者让 retriever 支持 `category in {a,b,c,d}` 的多选过滤。

---

## Minor（风格/优化）

- **m1**. `review_gate.py:115-151` 循环最后一次检查失败时，`violations`/`score` 在循环外被引用，依赖循环必然执行至少一次（`max_retries=0` 时会 UnboundLocalError）。把它们初始化为默认值。
- **m2**. `context_injection.py:76-82` 黄金三章只追加 `opening` category，不追加 `hook/golden_finger/character`，与 `golden-three-checker.md:117-122` 描述的 4 类范围不一致。
- **m3**. `checker.py:124-127` 剥 ```` ``` ```` 代码围栏的逻辑脆弱：假设首行必有语言标记。遇到 ```` ```\n{...} ```` 会把 `{...}` 第一行吃掉。建议用正则。
- **m4**. schema `editor-rules.schema.json` 允许 `applies_to` 任意字符串；但消费侧（writer_injection）只识别 `golden_three`。建议 schema 加 enum 或消费侧文档化白名单。
- **m5**. `02_clean.py` 的 MinHash 用 `hash((i, ng)) & 0xFFFFFFFF` —— Python `hash` 在进程间有 salt，每次跑结果可能不同（reproducibility 问题）。用 `hashlib.blake2b` 做 stable hash。
- **m6**. `polish_injection.generate_patches` 生成 `_patches.md` 但 US-013 单测只断言 "输出 diff 至少覆盖 2 条 violations 对应段落"，实际这个函数只做 unified diff、不校验段落命中 —— 建议补断言或改接口。
- **m7**. `logs/editor-wisdom/` 无 `.gitignore`，容易误提交。
- **m8**. `cli.py:24-40` rebuild 子命令串行运行 6 脚本，任一失败即中断；未提供 `--from-step N` 续跑（`rebuild` 在 288 文件上跑很慢，断电就前功尽弃）。

---

## Ralph 伪装通过总结

| 伪装类型 | 位置 | 识别线索 |
|---|---|---|
| 测试绿但编排未接线 | `review_gate.py` + `SKILL.md` | grep 调用点只在自己的 test 文件 |
| 产物缺失被静默吞 | `Retriever` init + `context_injection` try/except | `data/editor-wisdom/vector_index/` 不存在，但无任何 agent/脚本报错 |
| 规则为空给满分 | `checker.py:100-108` | `rules=[]` → `score=1.0`；在 enabled 状态下这是错误语义 |
| 模型 id 编造 | `03/05_*.py` | `claude-haiku-4-5-20241022`、`claude-sonnet-4-6-20250514` 都不是真实 snapshot，跑一次就知道 |
| 加严阈值文档化但分类数据不触发 | `writer_injection` + rules 抽取 | `applies_to=['golden_three']` 从未被强制生成 |

---

## 合并路径建议

1. **先修 C1**（真正把 `run_review_gate` 接到 python 侧审查入口），否则 PRD 的 FR-10 / FR-11 等于没做。
2. **再修 C2 + M3**（让索引能实际生成，校准模型 id），在本地跑通一次 `ink editor-wisdom rebuild` 并提交产物或把构建加入 CI smoke。
3. **再修 C3 + M1**（清掉评分逻辑二义性、category 过滤 bug），其余 Major/Minor 可开 follow-up。
4. 完成以上再合并 master。当前状态直接合会把"装饰性门禁"引入主干，后续排障成本高。

## 关键路径文件（绝对路径）

- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/review_gate.py
- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/retriever.py
- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/checker.py
- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/context_injection.py
- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/writer_injection.py
- /Users/cipher/AI/ink/ink-writer/ink_writer/editor_wisdom/golden_three.py
- /Users/cipher/AI/ink/ink-writer/ink-writer/skills/ink-review/SKILL.md
- /Users/cipher/AI/ink/ink-writer/ink-writer/scripts/step3_harness_gate.py
- /Users/cipher/AI/ink/ink-writer/scripts/editor-wisdom/03_classify.py
- /Users/cipher/AI/ink/ink-writer/scripts/editor-wisdom/05_extract_rules.py
