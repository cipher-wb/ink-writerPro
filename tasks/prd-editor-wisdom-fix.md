# PRD: editor-wisdom 修复（基于代码审查）

**Feature Name:** editor-wisdom-fix
**Branch Name:** `ralph/editor-wisdom-fix`（继承 `ralph/editor-wisdom`，不重建）
**Base Branch:** `ralph/editor-wisdom`（已有 15 feat commits）
**Review Source:** `reports/ralph-editor-wisdom-review.md`

## 1. Introduction

上一轮 Ralph 产出了 editor-wisdom 模块 15 个 commits，单元测试全绿但代码审查发现 **3 个 Critical、5 个 Major、8 个 Minor**，核心问题是"Ralph 伪装通过"：硬门禁在真实编排里没被调用、产物静默降级、模型 id 编造。本 PRD 按审查报告逐条修复，优先级按审查的 Critical → Major → Minor 编排。

## 2. Goals

- G1：让 editor-wisdom 硬门禁真正接入 python 侧审查入口（非仅文档）。
- G2：去除全部"静默降级"路径，`enabled=true` 但依赖缺失时必须硬报错。
- G3：修正被编造的模型 id，使 pipeline 实际可运行。
- G4：清理契约二义性（checker score 重算 vs LLM 自评）、category 过滤 bug、黄金三章 applies_to 硬化。
- G5：保证每条修复都有**端到端契约测试**覆盖（而不是只单测自己那片）。

## 3. User Stories

> 每条为 Ralph 单轮可完成；依赖顺序 Critical → Major → Minor。测试必须是**跨模块契约**，不能只 mock 当前模块。

### US-001: [C1] 硬门禁接入真实编排入口
**Description:** 让 `run_review_gate()` 被 ink-review 真实调用，而不是只存在于文档。

**Acceptance Criteria:**
- [ ] 先用 `grep -r run_review_gate` 确认当前唯一调用点是自身测试 —— 在 review report 根目录执行该检查并记录结果到 `progress.txt`
- [ ] 定位 python 侧审查收口：若存在 `scripts/step3_harness_gate.py` 则用之；否则审查 `ink-writer/skills/ink-review/SKILL.md` 指定的编排入口代码并选择最合适的 Python 模块接线
- [ ] 在该收口处 import 并调用 `ink_writer.editor_wisdom.review_gate.run_review_gate`
- [ ] 当 checker 返回 score < 阈值时，触发 polish → re-check 循环；最多 3 次；仍失败则写 `chapters/{n}/blocked.md` 并以**非零退出码**结束该章生成（不静默放行）
- [ ] 新增端到端集成测试 `tests/editor_wisdom/test_review_gate_wired.py`：通过 monkey-patch 注入"永远低分"的 checker，运行真实编排入口，断言：(a) polish 被调用 3 次 (b) `blocked.md` 存在 (c) 主 chapter 文件不存在 (d) 退出码非零
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-002: [C2] 清除静默降级，索引缺失必须硬报错
**Description:** 当 `config.enabled=true` 但向量索引/规则库缺失时，系统必须明确报错而非返回空。

**Acceptance Criteria:**
- [ ] `ink_writer/editor_wisdom/retriever.py` 的 `Retriever.__init__` 在索引文件缺失时 raise `EditorWisdomIndexMissingError`（新定义的明确异常类）
- [ ] `ink_writer/editor_wisdom/context_injection.py` 和 `writer_injection.py` 中包住 Retriever 构造的 `try/except Exception` 必须：若 `config.enabled=true` 则**re-raise**；仅当 `config.enabled=false` 才静默返回空
- [ ] `ink_writer/editor_wisdom/checker.py` 中 "rules=[] → score=1.0" 的分支：`config.enabled=true` 时改为返回 `{"score": 0.0, "summary": "规则库缺失，门禁无法执行", "violations": []}` 并同时 raise（由 review_gate 捕获记入日志）；`enabled=false` 时才给满分
- [ ] 新增测试 `tests/editor_wisdom/test_no_silent_fallback.py`：(a) 删除 vector_index 后调用 retriever，断言抛 `EditorWisdomIndexMissingError` (b) enabled=true 时 context_injection 传播异常 (c) enabled=false 时不传播
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-003: [C3] 清除 checker 评分契约二义性
**Description:** 二选一：(a) LLM 自评被保留、删除本地 `_compute_score` 覆盖；或 (b) LLM 只出 violations，score 纯本地算且 prompt 中删除评分描述。采用 (b)（更可复现）。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/editor_wisdom/checker.py` 的 SYSTEM_PROMPT / user prompt：删除所有要求 LLM "输出 0-1 评分"的描述，仅要求输出 `violations` + `summary`
- [ ] 保留 `_compute_score` 作为唯一 score 来源；score 由 violations 数量 × severity 权重计算（hard=0.3, soft=0.1, info=0）；公式写入 docstring
- [ ] 修改 `schemas/editor-check.schema.json`：`score` 字段标注为"server-computed, not from LLM"；保留字段但明确来源
- [ ] 更新 `tests/editor_wisdom/test_checker.py`：断言 mock 返回的 score 字段被忽略（即便 LLM 输出 0.99，含 2 条 hard violations 时 computed score 仍为 0.4）
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-004: [M3] 修正被编造的模型 id
**Description:** 对齐仓库中实际可用的 Anthropic 模型 id。

**Acceptance Criteria:**
- [ ] grep 仓库中实际使用的 model id（命令：`grep -rE "claude-(haiku|sonnet|opus)-[0-9]" --include="*.py"`），记录结果到 `progress.txt`
- [ ] 修改 `scripts/editor-wisdom/03_classify.py:73` 的 model 为 `claude-haiku-4-5-20251001`（与 `checker.py:80` 一致）
- [ ] 修改 `scripts/editor-wisdom/05_extract_rules.py:74` 的 model 为 `claude-sonnet-4-6`（unsuffixed latest 别名）
- [ ] 所有 model id 提取为模块级常量 `HAIKU_MODEL` / `SONNET_MODEL`，便于单点升级
- [ ] 新增冒烟测试 `tests/editor_wisdom/test_model_ids_valid.py`：读取源码正则匹配 model id，断言模式形如 `claude-(haiku|sonnet|opus)-\d(-\d)?(-\d{8})?$`，明确拒绝 `20241022` / `20250514` 这类伪造 snapshot
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-005: [M1] 修复 retriever category 过滤
**Description:** category 内召回必须真正按相似度排序，而不是全库 TopN 再过滤。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/editor_wisdom/retriever.py`：检测到 `category != None` 时，先按 metadata 取出该 category 的向量子集（numpy 切片），再用 numpy inner product 做 Top-K（规则总数 <200，可接受）
- [ ] 修复 `search_k = min(len(self._metadata), len(self._metadata))` typo
- [ ] 新增测试 `tests/editor_wisdom/test_retriever_category.py`：构造 10 个 category 每类 3 条（共 30 条）的 mock 索引；query "opening" 限定 category="taboo"，断言返回 3 条全为 taboo，且按 score 降序
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-006: [M2] 批处理失败不中断 + 周期性刷盘
**Description:** `03_classify.py` 和 `05_extract_rules.py` 单文件失败不能崩整批。

**Acceptance Criteria:**
- [ ] 每次 LLM 调用 try/except，失败记录到 `data/editor-wisdom/errors.log`（append 模式；字段：file_hash, filename, error_type, error_msg, timestamp）
- [ ] `_save_cache` 改为每 10 条（或每 60 秒）刷一次盘，并在 `try/finally` 的 `finally` 里兜底 flush
- [ ] 新增测试 `tests/editor_wisdom/test_batch_resilience.py`：mock 在第 3、5、7 个文件抛 RuntimeError，断言 (a) 脚本正常结束退出码 0 (b) `errors.log` 含 3 条 (c) 缓存里存了其他 ≥4 条成功结果
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-007: [M4] 黄金三章 applies_to 硬化
**Description:** 抽规则阶段对黄金三章相关 category 自动追加 `applies_to=['golden_three']`；消费侧统一用 category 而非 applies_to。

**Acceptance Criteria:**
- [ ] 修改 `scripts/editor-wisdom/05_extract_rules.py`：在规则落盘前后处理，若 `category ∈ {opening, hook, golden_finger, character}` 则自动合并 `"golden_three"` 到 `applies_to`（已有则跳过）
- [ ] 修改 `ink_writer/editor_wisdom/writer_injection.py` 黄金三章分支：改用 `category ∈ GOLDEN_THREE_CATEGORIES` 过滤，而非 `"golden_three" in applies_to`；与 `golden_three.py` 口径一致
- [ ] 在 `schemas/editor-rules.schema.json` 的 `applies_to` 字段加 enum 白名单：`["all_chapters","golden_three","opening_only"]`
- [ ] 新增测试 `tests/editor_wisdom/test_golden_three_applies_to.py`：构造一条 category=opening 的 raw 规则，跑 extract 后处理，断言 `applies_to` 含 `golden_three`；writer_injection 在黄金三章上下文中召回到它
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-008: [M5] retrieve_golden_three_rules 按相关度合并
**Description:** 多 category 召回合并后按 score 全局排序，不按字母序。

**Acceptance Criteria:**
- [ ] 修改 `ink_writer/editor_wisdom/golden_three.py:73-89`：每类 retrieve 时保留 `score`；合并后 `sorted(..., key=lambda r: -r.score)` 取全局 Top-K
- [ ] `Retriever.retrieve` 返回值增加或暴露 `score` 字段（numpy inner product 分）
- [ ] 新增测试：mock 4 category 各返回带不同 score 的候选，断言合并结果按 score 降序
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-009: [Minor 合并] review_gate + 注入路径的 8 条 Minor 修复
**Description:** 一次性修掉 8 条 Minor（都是小改，合并为单 story）。

**Acceptance Criteria:**
- [ ] m1: `review_gate.py:115-151` 循环外引用 `violations`/`score`，初始化默认值避免 `max_retries=0` 时 UnboundLocalError
- [ ] m2: `context_injection.py:76-82` 黄金三章追加 4 个 category（opening/hook/golden_finger/character），与 `golden-three-checker.md` 一致
- [ ] m3: `checker.py:124-127` 剥代码围栏改用正则 `r"^```(?:\w+)?\n([\s\S]*?)\n```$"`
- [ ] m4: schema `editor-rules.schema.json` 的 `applies_to` 已在 US-007 加 enum；此处补充消费侧 README
- [ ] m5: `scripts/editor-wisdom/02_clean.py` 的 MinHash 用 `hashlib.blake2b(..., digest_size=8)` 替代 `hash()` 保证可复现
- [ ] m6: `polish_injection.generate_patches` 新增单测断言 "diff 至少覆盖 2/3 violations 对应段落"
- [ ] m7: 新增 `.gitignore` 条目：`logs/editor-wisdom/`
- [ ] m8: `ink_writer/editor_wisdom/cli.py` rebuild 子命令支持 `--from-step N`（1-6）续跑
- [ ] Typecheck passes
- [ ] Tests pass

---

### US-010: 端到端冒烟 —— rebuild + 一章真实跑通
**Description:** 所有 Critical/Major/Minor 修完后，执行一次完整端到端干跑，证明硬门禁真的会 block 坏章节。

**Acceptance Criteria:**
- [ ] 新脚本 `scripts/editor-wisdom/smoke_test.py`：(1) 运行 `ink editor-wisdom rebuild`（若已有索引则跳过） (2) 构造一段明显违反多条规则的 mock 章节文本 (3) 调用真实 review_gate (4) 断言触发 3 次 polish 后 blocked.md 存在
- [ ] 冒烟测试产物：`reports/editor-wisdom-smoke-report.md`，记录每步输出、耗时、API token 消耗
- [ ] 文档 `docs/editor-wisdom-integration.md` 新增"如何运行冒烟测试"段落
- [ ] 若真实 API 未配置（ANTHROPIC_API_KEY 缺失），脚本以 `skip` 状态退出 0，不算失败，但在报告中明确标注
- [ ] Typecheck passes
- [ ] Tests pass

## 4. Functional Requirements

- FR-1: `run_review_gate()` 必须在 python 侧审查入口被真实调用。
- FR-2: `config.enabled=true` 下任何依赖缺失必须硬报错，不得静默返回空/满分。
- FR-3: checker 评分策略必须单一来源（本地算）。
- FR-4: 所有 Anthropic model id 必须来自运行时常量或仓库现有调用，禁止硬编码伪造 snapshot。
- FR-5: retriever category 过滤必须按相似度排序。
- FR-6: 批处理脚本失败必须 recoverable（errors.log + 周期性缓存刷盘）。
- FR-7: 黄金三章的 4 个 category 规则必须自动被 writer_injection 召回。
- FR-8: 每条修复必须带跨模块契约测试，不能只 mock 自身。

## 5. Non-Goals

- NG-1: 不做 RAG 模型升级、不替换 `bge-small-zh`。
- NG-2: 不重写 pipeline 架构，仅按审查清单修复。
- NG-3: 不做性能优化（除非是修复的副产品）。
- NG-4: 不扩展规则库、不新增 agent。
- NG-5: 不合并到 master —— 本期只保证 `ralph/editor-wisdom-fix` 分支绿灯 + 冒烟通过。

## 6. Technical Considerations

- **模型 id 真实值**：`claude-haiku-4-5-20251001`（已在 checker.py 使用）、`claude-sonnet-4-6`（unsuffixed latest 别名）。禁用 `20241022` / `20250514` 伪造日期。
- **测试基线**：每条 AC 里的测试必须使用真实 schema 校验（`jsonschema.validate`），不能只断言"调用了某函数"。
- **端到端契约**：US-001/US-002/US-010 必须串跨 2 个以上模块跑，明确覆盖上一轮 Ralph 盲区。

## 7. Success Metrics

- SM-1: `grep -r run_review_gate` 在 python 代码（非测试）中至少命中 2 处（review_gate.py 自身 + 真实编排入口）。
- SM-2: 索引缺失场景测试通过：删除 `vector_index/` 后运行真实入口，观察到硬报错（非空返回）。
- SM-3: 冒烟脚本端到端运行：`ANTHROPIC_API_KEY` 有效时实际 block 一章坏文本。
- SM-4: 所有单测 + 新增契约测试 pass。
- SM-5: 全部 3 Critical + 5 Major + 8 Minor 审查项目清单在 `progress.txt` 对应条目标记已修。

## 8. Open Questions

- OQ-1: 若 `scripts/step3_harness_gate.py` 实际不存在（review report 提及但 grep 不到），US-001 应接线到哪？—— 执行 US-001 时由 Ralph 读 `ink-writer/skills/ink-review/SKILL.md` 识别真实 Python 编排入口；若仅有 markdown 编排没有 Python 收口，则在 `ink_writer/editor_wisdom/review_gate.py` 暴露给 `skills/ink-write/SKILL.md` 的 Step 3.5 调用脚本入口（必须是实际可 `python -m` 的命令）。
