# M4 启动 Checklist & Brainstorm 准备

**Status**: 待 M3 完成后启动（已可启动 — M3 ✅ 2026-04-25）
**M4 目标**: P0 上游策划层 — 让 ink-init / ink-plan 阶段强制走策划期审查（解决 spec §1.3 的 5/8 上游扣分）
**预计周期**: 1 周（≈ 14-16 user stories）
**Origin spec**: `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` §3 P0 上游 + §9 M4

> ⚠️ **本文件用途**：M3 完成期间预先准备的 M4 brainstorm 输入，让 M4 启动时无需从零思考。**当用户说"开 M4"或"接着推"时**，按"M3 收尾仪式确认"→"M4 brainstorm 启动"顺序执行。

---

## Part A — M3 收尾仪式确认（已完成，仅核对）

### A.1 验收 6 项已全过（2026-04-25 12:50 PM）

```bash
# (1) 全量 pytest 全绿 + 覆盖率 ≥ 70  ✅ (实际 82.75%)
pytest -q

# (2) M3 全部模块导入成功  ✅
python3 -c "from ink_writer.writer_self_check import writer_self_check; ..."

# (3) load_thresholds() OK  ✅
python3 -c "from ink_writer.checker_pipeline.thresholds_loader import load_thresholds; ..."

# (4) 4 个新 agent.md 存在  ✅
ls ink-writer/agents/{writer-self-check,conflict-skeleton-checker,protagonist-agency-checker}.md

# (5) ink-write SKILL.md 集成 ✅
grep -c "rewrite_loop\|require_evidence_chain" ink-writer/skills/ink-write/SKILL.md  # ≥ 3

# (6) git tag m3-p1-loop ✅
git tag -l | grep m3-p1-loop
```

### A.2 Master 已合并 + push（已完成）

```
master HEAD: 3e5dc19 fix(M3-followup): sync baseline doc/test claims
tag m3-p1-loop 已 push 到 origin
```

---

## Part B — M3 实际产出对 M4 的影响

### B.1 M4 复用的 M3 资产

| M3 已建 | M4 中的角色 |
|---|---|
| `ink_writer/case_library/`（M1）| M4 ink-init checker 也通过 case_library 命中 case |
| `scripts/corpus_chunking/llm_client.LLMClient`（M2 wrapper）| M4 全部 LLM 调用复用 |
| `config/checker-thresholds.yaml`（M3 新建）| M4 新增 7 个 checker 配置加到这个 yaml |
| `evidence_chain.json` schema（M3）| M4 产 `planning_evidence_chain.json`（与 chapter evidence 平行）|
| `thresholds_loader.py`（M3）| M4 复用加载 |

### B.2 M4 不依赖的事

- ❌ M4 不依赖 M2 corpus_chunks（chunks 仍可缺席）
- ❌ M4 不依赖 M3 dry-run 章节（M4 是 ink-init/ink-plan 阶段，不是 ink-write 写章阶段）
- ❌ M4 不动 M3 的 5 个 checker（reader-pull / sensory / high-point / conflict-skeleton / protagonist-agency 是章节级；M4 是策划期级）

### B.3 M3 与 M4 可并行

M3 dry-run 跑下游章节验证质量；M4 跑上游策划期审查 ink-init/ink-plan。两者互不干扰，可同时跑。

---

## Part C — M4 brainstorm 关键问题（≈ 15 题）

### C.1 ink-init checker 范围

**Q1**：ink-init 阶段加几个 checker？
- a) **4 个**：genre-novelty / golden-finger-spec / naming-style / protagonist-motive（spec §3.4 默认）⭐
- b) 6 个：再加 worldbuilding-coherence + plot-archetype-novelty
- c) 3 个：去掉 protagonist-motive（合并到 ink-plan 阶段）

### C.2 起点 top200 简介库

**Q2**：起点 top200 简介库（genre-novelty checker 的依赖）怎么获取？
- a) **写爬虫一次性爬**（合规：简介是公开数据；半天工作）⭐
- b) 用 Claude Code 联网搜索分批爬（无需爬虫但慢）
- c) 复用 reference_corpus 的 manifest.json + LLM 生成简介（不准但零外部依赖）
- d) 跳过这个依赖，genre-novelty 用 reference_corpus 30 本简介代替（精度低但 M4 当下能跑）

### C.3 LLM 高频起名词典

**Q3**：naming-style checker 的 LLM 高频起名词典（≈ 300 条）怎么建？
- a) **手工汇总 + LLM 扩充**（半天工作；包含"林夜""叶凡""陈青山""李逍遥""沈墨"等 AI 模板名）⭐
- b) 全 LLM 生成（让 GLM-4.6 生成 300 条 + 字根模式，0 人工）
- c) 用现成开源数据集（如有）

### C.4 ink-plan checker 范围

**Q4**：ink-plan 阶段加几个 checker？
- a) **3 个**：golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density（spec §3.5 默认）⭐
- b) 5 个：再加 cliffhanger-rhythm + character-arc-skeleton
- c) 2 个：去掉 chapter-hook-density（合并到 ink-write 阶段）

### C.5 阻断策略统一

**Q5**：M4 7 个 checker 的阻断策略与 M3 一致吗？
- a) **完全一致**：P0 阻断 / P1 警告需豁免 / P2-P3 提示（spec §4.5 + Q9）⭐
- b) 更严：所有 checker 都 P0 阻断（一票否决）
- c) 更松：只 ink-init 4 个阻断，ink-plan 3 个仅警告

### C.6 planning_evidence_chain.json schema

**Q6**：planning_evidence_chain.json 与 chapter evidence_chain 同结构吗？
- a) **同结构 + dry_run 字段**（统一 schema 便于聚合分析）⭐
- b) 独立 schema（planning 字段更精简，无 polish_agent）
- c) 共用 evidence_chain.json 加 phase 字段区分

### C.7 ink-init / ink-plan SKILL.md 集成位置

**Q7**：M4 checker 调用插入到 ink-init / ink-plan SKILL.md 哪个 step？
- a) **末尾 Step 99 策划审查**（与 M3 ink-write Step 1.5 同模式）⭐
- b) 中间某个 step（与 v23 现有 ink-init 流程交错）
- c) 单独 SKILL：新增 `ink-planning-review` skill 单独跑

### C.8 上游 cases 批量编写

**Q8**：M4 阻断时命中的"上游 cases"（如 CASE 题材老套 / CASE 主角动机牵强）怎么来？
- a) **M4 期间手工写 7 个种子 case**（每个 ink-init/ink-plan checker 至少 1 个种子，用户审批后置 active）⭐
- b) 自动从 spec §1.3 描述生成 7 个 case（让 LLM 提取 + 用户审）
- c) 不预生成，让 dry-run 触发后再录入（M4 上线即翻车风险）

### C.9 dry-run 模式（M4 是否需要）

**Q9**：M4 也要 dry-run 5 章观察后切真阻断吗？
- a) **要**：与 M3 同模式（ink-init/ink-plan 阶段也跑 dry-run + planning_dry_run_counter）⭐
- b) 不要：ink-init / ink-plan 阶段错误成本低（开新书时点点点而已），直接真阻断
- c) 只 ink-init 阶段 dry-run，ink-plan 直接真阻断

### C.10 LLM model

**Q10**：M4 LLM 用什么 model？
- a) **glm-4.6**（与 M3 一致；7 个 checker 调用量小不撞 RPM）⭐
- b) glm-4-flash（与 M2 切片一致，更便宜但质量稍降）
- c) 混合：genre-novelty 用 glm-4.6（语义判断重）+ 其他 6 个用 glm-4-flash

### C.11 起点 top200 简介库的存放位置

**Q11**：起点 top200 简介库存哪里？
- a) **`data/market_intelligence/qidian_top200.jsonl`**（与 case_library 同 data/ 下，新建子目录）⭐
- b) `data/editor-wisdom/top200.jsonl`（与编辑数据同根）
- c) `benchmark/qidian_top200/`（与 reference_corpus 同根）

### C.12 LLM 高频起名词典存哪里

**Q12**：起名词典存哪里？
- a) **`data/market_intelligence/llm_naming_blacklist.json`**（与 top200 同目录）⭐
- b) `data/case_library/naming_dictionary.json`
- c) hard-code 在 naming-style-checker.py 里

### C.13 M4 与现有 ink-init/ink-plan 的兼容性

**Q13**：现有 v23 的 ink-init quick 模式（用户填几个字段就开书）会被 M4 阻断打断吗？
- a) **会**：M4 是强制阻断，开书前必须通过 7 个 checker（与 spec §3.6 一致）⭐
- b) 不会：M4 仅作为可选 review，不阻断 ink-init quick 流程
- c) 部分：硬性 checker（题材 / 起名）阻断，软性 checker（主角动机）仅警告

### C.14 M4 验收

**Q14**：M4 验收用什么数据？
- a) **跑一本测试书的 ink-init**：7 个 checker 全跑通 + 产 planning_evidence_chain.json + tag `m4-p0-planning`（与 M3 验收同模式）⭐
- b) 仅单元 + e2e 测试通过即算（不真跑 ink-init）
- c) 跑 5 本测试书的 ink-init 各种边界

### C.15 M4 整体范围

**Q15**：M4 整体范围用方案 A/B/C？
- a) **A 完整版 14-15 US**（按 PRE-NOTES Part D；与 M1/M2/M3 节奏一致；估 5 小时）⭐
- b) MVP 9 US（去掉起点 top200 + 起名词典，留 follow-up）
- c) 双阶段（M4a ink-init checker / M4b ink-plan checker，分两次 ralph 循环）

---

## Part D — M4 预期 user story 草拟（≈ 14 个）

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | M4 config 段加到 `config/checker-thresholds.yaml` | M3 |
| US-002 | `planning_evidence_chain.json` schema + 写入工具 | M3 evidence_chain pattern |
| US-003 | `genre-novelty-checker` (起点 top200 相似度比对) | US-007 数据依赖 |
| US-004 | `golden-finger-spec-checker` (4 维度评分) | M3 |
| US-005 | `naming-style-checker` (LLM 高频起名词典比对) | US-008 数据依赖 |
| US-006 | `protagonist-motive-checker` (主角动机 3 维度) | M3 |
| US-007 | 起点 top200 简介库爬虫 + `data/market_intelligence/qidian_top200.jsonl` | 独立 |
| US-008 | LLM 高频起名词典 ≈ 300 条 + `data/market_intelligence/llm_naming_blacklist.json` | 独立 |
| US-009 | `golden-finger-timing-checker` (前 3 章必出) | M3 |
| US-010 | `protagonist-agency-skeleton-checker` (大纲骨架级) | M3 |
| US-011 | `chapter-hook-density-checker` | M3 |
| US-012 | ink-init / ink-plan SKILL.md 加 Step 99 策划审查 | US-003~011 |
| US-013 | 7+ 个上游种子 cases 编写 + ink case approve --batch 批量 active | M2 case_library |
| US-014 | M4 e2e 测试 + 验收 + tag m4-p0-planning + ROADMAP ✅ | 全部 |

**估时**：14 US × ~6 分钟（M3 节奏）≈ **1.5 小时**（如果 ralph 节奏继续提速；保守 ~3 小时）

---

## Part E — M4 风险与护栏

| # | 风险 | 缓解 |
|---|---|---|
| 1 | 起点 top200 爬虫合规风险 | 简介是公开数据；遵守 robots.txt + UA 礼貌 + 限速 1 req/s |
| 2 | LLM 起名词典 300 条覆盖不全 | M4 dry-run 阶段如发现新 AI 模板名，加入词典持续扩充 |
| 3 | naming-style-checker 误判（中文姓名重复率高，如"李明"既是 AI 起名又是真名）| 阈值不设太严 (0.7+) + dry-run 阶段调阈值 |
| 4 | M4 阻断 ink-init quick 模式让用户体验下降 | 提供 `--skip-planning-review` flag 紧急绕过（但记入 evidence_chain warn）|
| 5 | 7 个种子 case 不够 dry-run 触发 | M4 dry-run 后基于实际触发样本扩充 case 库 |
| 6 | ink-init 与 ink-plan SKILL.md 改动可能与 v23 现有流程冲突 | 改动前先 cat 现有 SKILL.md 全文 + 增量加 Step 99（不改 v23 现有 step）|
| 7 | M4 与 M3 dry-run 计数器混淆 | 用独立 `data/.planning_dry_run_counter` 与 M3 章节计数器区分 |

---

## Part F — M4 启动命令清单

```
# 步骤 1：用户在新会话或本会话里说：
"按 M4-PREPARATION-NOTES 推 M4" 或 "开 M4" 或 "继续推"

# 我会自动：
1. cat docs/superpowers/M-ROADMAP.md 确认 M3 ✅
2. cat docs/superpowers/M-SESSION-HANDOFF.md 确认 catch-up
3. 进入 brainstorming skill，逐题问 Part C 的 15 个问题
4. 写 docs/superpowers/specs/<日期>-m4-p0-planning-design.md
5. 写 docs/superpowers/plans/<日期>-m4-p0-planning.md
6. /prd → tasks/prd-m4-p0-planning.md
7. /ralph → prd.json + branch ralph/m4-p0-planning + archive M3
8. bash scripts/ralph/ralph.sh --tool claude 14（后台启动）
```

---

## Part G — 故意不预设的事

1. genre-novelty-checker 的相似度算法（向量 cosine vs LLM 主观判断）
2. golden-finger-spec 4 维度的具体打分 prompt
3. naming-style 的字根模式 regex
4. ink-init SKILL.md Step 99 的具体调用代码（依赖 v23 现有 SKILL.md 结构）
5. 7 个种子 case 的具体 failure_pattern.observable 文本（M4 brainstorm 时与用户共同设计）
