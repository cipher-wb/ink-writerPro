# M3 P1 下游闭环 — writer-self-check + 阻断重写 (Design Spec)

**Status**: ready-for-plan
**Date**: 2026-04-25
**Author**: cipher-wb（产品）+ brainstorming co-pilot
**Baseline**: v23.0.0 + M1 (`m1-foundation`) + M2 partial (`m2-data-assets-partial`)
**Target version**: v24.x（5 周 M1-M5 的第 3 步，**30 → 50 分质量拐点**）
**Quality target**: 每章自带 evidence_chain.json + 阻断重写循环跑通

---

## 1. 背景与问题陈述

### 1.1 M1/M2 已交付（前提）

- **M1** ✅：Case Library 基础设施 + Qdrant 替换 FAISS + Preflight + reference_corpus symlink 修复
- **M2** 🟡 部分完成：
  - ✅ corpus_chunking 切片管线（segmenter + tagger + indexer 三段，glm-4-flash + ZhipuAI embedding-3 + LLMClient wrapper）
  - ✅ ink corpus ingest/rebuild/watch CLI
  - ✅ rules → cases 转换器（402 cases，hard 236 / soft 147 / info 19）
  - ✅ ink case approve --batch
  - ✅ M2 e2e 测试 5 用例
  - ❌ corpus_chunks 实跑（智谱 GLM API 卡死，**deferred**）

### 1.2 M3 要解决的问题

M2 把 **403 cases 的资产**备齐了（237 active + 166 pending + zero-case），但当前产线**没有任何机制把这些 case 真正注入 writer 链路**——case 库只是"数据躺着"，writer 写章时 cases 不参与决策、不阻断、不重写。

M3 的使命：把 cases + rules 升级为**写完比对 → 阻断 → 病例驱动重写**的闭环，让产线**每章自带 evidence_chain.json**——彻底消灭 spec §1.3 诊断里的 "Q3(d) 靠感觉判断库有没有生效" 痛点。

### 1.3 与原 spec §6 + §9 M3 的偏差

| 项 | 原 spec | 实际 M3 调整 | 理由 |
|---|---|---|---|
| writer-self-check 的 chunk_borrowing 指标 | 0-1 浮点（依赖 corpus_chunks）| **null**（M2 chunks deferred）| schema 字段保留兼容 |
| LLM model | 假设 Anthropic Haiku 4.5 | glm-4.6（M2 已实测 RPM 充足）| LLM 实际可用 |
| dry-run 时长 | spec §6.1 "1 周观察" | **5 章观察**（Q10 决议）| 验收节奏更紧凑 |
| dry-run 切换 | 手动切换 | **5 章后自动切真阻断**（Q10）| 减人工干预 |

### 1.4 设计原则

1. **复用 M1+M2 已建组件**（CaseStore / ingest_case / LLMClient wrapper），不重建任何基础设施
2. **evidence_chain 强制必带**：消灭 v22 那种"产线在跑但说不清做了什么"的黑盒状态
3. **dry-run 5 章护栏**：避免 236 active cases 一次上线翻车（重写率 > 80%）
4. **一次重写一个 case**：保证 polish-agent 修复可溯源（spec §5.4）
5. **M2 chunks 缺席兼容**：chunk_borrowing 字段保留为 null，不阻塞 M3 上线

---

## 2. 整体架构

### 2.1 数据流

```
[输入] 章节请求 (book/chapter/scene_type/applicable_cases)
   │
   ▼
[现有] context-agent 召回 (cases + chunks*)
   │   *chunks 暂为空（M2 deferred），rule_compliance 主导
   ▼
[现有] writer-agent 写章 X
   │
   ▼
[NEW] writer-self-check ── 计算 compliance_report
   │    rule_compliance / chunk_borrowing(null) / cases_addressed
   │
   ▼
合规率 < 0.70 → 直接进 polish-loop（不进 review，省算力）
合规率 ≥ 0.70 → 进 checker review
   │
   ▼
[现有 升级] reader-pull / sensory-immersion / high-point  ← 加 block_threshold
[NEW]      conflict-skeleton-checker (章节级)
[NEW]      protagonist-agency-checker (章节级)
   │
   ▼
任一 < block_threshold + cases_hit → 进 polish-loop（一次一个 case，最多 3 轮）
全部 ≥ threshold → 章节交付 + 写 evidence_chain.json
   │
   ▼
[NEW] polish-agent 改造：接收 case_id 驱动重写
   │   每轮重写后回 writer-self-check
   │   3 轮仍失败 → 标 needs_human_review.jsonl（不删稿）
   ▼
最终交付：data/<book>/chapters/chXXX.txt + chXXX.evidence.json
```

### 2.2 七大组件

| # | 组件 | 类型 |
|---|---|---|
| 1 | `writer-self-check` agent | 新建 |
| 2 | `conflict-skeleton-checker` agent | 新建 |
| 3 | `protagonist-agency-checker` agent | 新建 |
| 4 | `polish-agent` 改造（case_id 驱动）| 改造现有 |
| 5 | reader-pull / sensory-immersion / high-point 加 `block_threshold` | 改造现有 3 个 |
| 6 | `evidence_chain.json` schema + 写入工具 | 新建 |
| 7 | `config/checker-thresholds.yaml` + dry-run 控制 | 新建 |

### 2.3 与 M1/M2 资产复用

| 已有资产 | M3 中的角色 | 改不改 |
|---|---|---|
| `ink_writer/case_library/{store, ingest, models}` | writer-self-check 读 case；polish-agent 接收 case_id | 不动 |
| `data/case_library/cases/` 403 cases | 阻断驱动 + cases_addressed 评估的输入 | 不动 |
| `ink_writer/qdrant/CORPUS_CHUNKS_SPEC` | 占位（M2 chunks 实际为 0；schema 仍用 2048 维） | 不动 |
| `scripts/corpus_chunking/llm_client.LLMClient` | M3 全部 LLM 调用复用 | 不动 |
| `~/.claude/ink-writer/.env` 的 `LLM_MODEL=glm-4-flash` | M3 默认改 `glm-4.6` | 改 .env 一行 |
| `ink-writer/agents/{writer-agent, polish-agent, ...}` 23 个 | writer-agent 末尾加 self-check 调用；polish-agent 改 prompt；3 个升级阻断 | 改 ≤ 5 个 |
| `ink-writer/skills/ink-write/SKILL.md` | 流程加"合规→阻断→重写"循环 | 加章节 |

### 2.4 边界（明确不做的事）

- ❌ 不补 corpus_chunks（M2 deferred 状态保持；chunk_borrowing 字段 = null）
- ❌ 不做病例反向召回的实际接线（router.py case_aware 模式）→ M3 之外的 follow-up
- ❌ 不做 P0 上游策划层 → M4
- ❌ 不做 dashboard / 自进化 → M5
- ❌ 不退役 FAISS（M2 双写策略保持）
- ❌ 不动 v22 的 simplicity 域 / 场景感知召回（已 OK）
- ❌ 不做 interactive review（M5 dashboard 配套）
- ❌ 不动现有 20 个其他 checker（仅 3 个升级阻断）

---

## 3. writer-self-check 详细设计

### 3.1 输入 / 输出

```python
def writer_self_check(
    *,
    chapter_text: str,
    injected_rules: list[Rule],
    injected_chunks: list[Chunk] | None,
    applicable_cases: list[Case],
    book: str,
    chapter: str,
    llm_client: LLMClient,
) -> ComplianceReport:
```

```python
@dataclass
class ComplianceReport:
    rule_compliance: float
    chunk_borrowing: float | None       # M3 期 = None
    cases_addressed: list[str]
    cases_violated: list[str]
    raw_scores: dict[str, float]
    overall_passed: bool
    notes: str
```

### 3.2 prompt 模板

新建 `ink-writer/agents/writer-self-check.md` + `ink_writer/writer_self_check/prompts/self_check.txt`：

```
你是写作合规自查助手。给定一段章节 + 写作前注入的"规则/病例"清单，
评估章节是否遵守每条规则、规避每个病例。

输入：
- 章节正文（约 2000-3500 字）
- injected_rules: [
    {rule_id: "EW-0042", rule: "...", category: "..."},
    ...（典型 12 条）
  ]
- applicable_cases: [
    {case_id: "CASE-2026-0042", title: "...", failure_pattern.description: "..."},
    ...（典型 5-10 条）
  ]

要求严格 JSON 输出：
{
  "rule_scores": {
    "EW-0042": 0.85,
    ...
  },
  "case_evaluation": {
    "CASE-2026-0042": {"addressed": true, "evidence": "第 3 段已加入主角心理缓冲"},
    "CASE-2026-0017": {"addressed": false, "evidence": "主角全章被动观察，无主动决策"},
    ...
  },
  "notes": "..."
}

不要包裹 markdown。
```

### 3.3 计算

- `rule_compliance = mean(rule_scores.values())` — 简单算术平均
- `cases_addressed = [cid for cid, ev in case_evaluation.items() if ev.get("addressed")]`
- `cases_violated = [cid for cid, ev in case_evaluation.items() if not ev.get("addressed")]`
- `chunk_borrowing = None`（M3 期；M2 chunks 缺）
- `overall_passed = rule_compliance >= 0.70 and len(cases_violated) == 0`

### 3.4 失败处理

| 场景 | 处理 |
|---|---|
| LLM JSON 解析失败 | 重试 3 次（LLMClient 内置 retry）→ `overall_passed=False, notes="self_check_failed"` |
| LLM 漏给某条 rule_score | 该条按 0 计入 mean + `raw_scores["missing"]: ["EW-XXXX"]` |
| LLM 漏给某个 case_evaluation | 该 case 默认 `addressed=False`（保守，触发 polish）|
| `applicable_cases=[]` | 跳过 case 部分；仅评 rule_compliance |
| `injected_rules=[]` | `rule_compliance=1.0` + `notes="no_rules_injected"` |

### 3.5 测试策略（7 个用例）

| 测试 | 覆盖 |
|---|---|
| `test_self_check_happy_path` | mock LLM happy JSON → rule_compliance + cases 二分正确 |
| `test_self_check_threshold_passes_at_0_70` | 0.70 → True；0.69 → False |
| `test_self_check_case_violated_blocks_pass` | 全 rule 1.0 但 case_violated → False |
| `test_self_check_chunk_borrowing_is_none_in_m3` | injected_chunks=None → chunk_borrowing=None |
| `test_self_check_llm_failure_returns_failed_report` | LLM 持续 JSON 错误 → notes="self_check_failed" |
| `test_self_check_missing_rule_score_treated_as_zero` | LLM 漏给 EW-XXXX → 该条按 0 计 |
| `test_self_check_empty_cases_skips_case_block` | applicable_cases=[] → 只评 rules |

### 3.6 钩子插入点

| 文件 | 改动 |
|---|---|
| `ink_writer/writer_self_check/__init__.py` | 新增 |
| `ink_writer/writer_self_check/checker.py` | 新增 `writer_self_check()` |
| `ink_writer/writer_self_check/models.py` | 新增 `ComplianceReport` |
| `ink_writer/writer_self_check/prompts/self_check.txt` | 新增 |
| `ink-writer/agents/writer-self-check.md` | 新增 agent spec |
| `tests/writer_self_check/__init__.py` | 新增 |
| `tests/writer_self_check/test_checker.py` | 新增 7 用例 |

---

## 4. 2 个新章节级 checker

### 4.1 conflict-skeleton-checker

#### 输入 / 输出

```python
def check_conflict_skeleton(
    *,
    chapter_text: str,
    book: str,
    chapter: str,
    llm_client: LLMClient,
) -> ConflictReport:
```

```python
@dataclass
class ConflictReport:
    has_explicit_conflict: bool
    conflict_count: int
    has_three_stage_structure: bool
    conflict_summaries: list[dict]
    score: float
    block_threshold: float           # 0.60
    blocked: bool
    cases_hit: list[str]
    notes: str
```

#### prompt（`ink_writer/checkers/conflict_skeleton/prompts/check.txt`）

```
你是网文章节冲突骨架检查器。给定一章正文，判断：

1. 是否有 ≥ 1 个显式冲突？
   显式冲突 = 人物立场对立 / 利益冲突 / 价值观碰撞（任一）
   注意：氛围紧张 ≠ 冲突；环境描写 ≠ 冲突
   必须是人与人/势力之间的对抗，明确可指认

2. 该冲突是否有三段结构？
   - 摩擦点：冲突触发的具体事件
   - 升级：冲突激化（语言/行动/筹码升级）
   - 临时收尾：本章节段落对该冲突的暂停（解决/搁置/转入下章）

输出严格 JSON：
{
  "has_explicit_conflict": true,
  "conflict_count": 1,
  "has_three_stage_structure": true,
  "conflicts": [
    {
      "summary": "...",
      "friction_point": "...",
      "escalation": "...",
      "interim_resolution": "..."
    }
  ],
  "notes": "..."
}
```

#### score 计算

```python
score = (
    0.5 if has_explicit_conflict else 0.0
) + (
    0.3 if has_three_stage_structure else 0.0
) + (
    min(conflict_count / 2, 1.0) * 0.2
)
# block_threshold = 0.60
```

### 4.2 protagonist-agency-checker

#### 输入 / 输出

```python
def check_protagonist_agency(
    *,
    chapter_text: str,
    protagonist_name: str,
    book: str,
    chapter: str,
    llm_client: LLMClient,
) -> AgencyReport:
```

```python
@dataclass
class AgencyReport:
    has_active_decision: bool
    has_plot_drive: bool
    decision_count: int
    decision_summaries: list[dict]
    score: float
    block_threshold: float           # 0.60
    blocked: bool
    cases_hit: list[str]
    notes: str
```

#### prompt 关键约束

```
你是网文主角主动性检查器。给定一章正文 + 主角姓名 {protagonist_name}，判断：

1. 主角是否做出 ≥ 1 个主动决策？
   主动决策 = 主角基于自己判断选择行动方向（非被命运/巧合/他人推着走）
   反例：被告知"你必须做 X"然后说"好" / 被攻击后被动反击 / 旁观他人决策然后跟随

2. 主角是否 ≥ 1 次推动剧情？
   推动剧情 = 主角的主动行为直接导致下一段情节展开
   反例：全章观察他人对话/打斗（俗称"当摄像头"）

输出严格 JSON：
{
  "has_active_decision": true,
  "has_plot_drive": true,
  "decision_count": 2,
  "decisions": [...],
  "notes": "..."
}
```

#### score 计算

与 conflict-skeleton 同结构（0.5 + 0.3 + 0.2 加权），block_threshold = 0.60。

### 4.3 protagonist_name 来源

```python
protagonist_name = read_book_metadata(book)["protagonist"]
# 默认从 .ink/project.yaml 读
# 失败时降级：让 LLM 自己识别"谁是主角"（多 1 次 LLM 调用）
```

### 4.4 通用 cases_hit 计算

```python
applicable_cases = case_store.query_by_tag([
    "no_explicit_conflict",       # for conflict-skeleton
    "protagonist_passive",         # for protagonist-agency
])
```

cases_hit 为空 + score < threshold 也仍 blocked（评分本身就是阻断依据）。

### 4.5 失败处理

| 场景 | 处理 |
|---|---|
| LLM JSON 解析失败 | 重试 3 次 → score=0, blocked=True, notes="checker_failed" |
| LLM 输出冲突描述空 | conflict_count=0, has_explicit_conflict=False |
| 章节字数 < 500 字（异常短）| 跳过检查 + 警告 |

### 4.6 测试策略（每个 checker 6 个用例）

| 测试 | 覆盖 |
|---|---|
| `test_happy_path` | mock LLM happy JSON → blocked=False, score>=0.6 |
| `test_no_explicit_conflict_blocks` | LLM 返 has_explicit_conflict=False → blocked=True |
| `test_partial_three_stage_structure` | 有冲突但缺升级 → score=0.7（pass）|
| `test_score_threshold_boundary` | score=0.60 → not blocked；=0.59 → blocked |
| `test_llm_json_failure_blocks_with_score_zero` | LLM 持续错误 → score=0, blocked=True |
| `test_short_chapter_skips_check` | < 500 字 → 跳过 + 警告 |

protagonist-agency 6 个用例对称结构。

### 4.7 钩子插入点

| 文件 | 改动 |
|---|---|
| `ink_writer/checkers/conflict_skeleton/{__init__,checker,models}.py` | 新增 |
| `ink_writer/checkers/conflict_skeleton/prompts/check.txt` | 新增 |
| `ink_writer/checkers/protagonist_agency/{__init__,checker,models}.py` | 新增（同结构）|
| `ink-writer/agents/conflict-skeleton-checker.md` | 新增 |
| `ink-writer/agents/protagonist-agency-checker.md` | 新增 |
| `tests/checkers/{conflict_skeleton,protagonist_agency}/test_checker.py` | 新增（6 + 6 = 12 用例）|
| `pytest.ini` | testpaths 追加 `tests/writer_self_check tests/checkers tests/rewrite_loop tests/evidence_chain` |

---

## 5. polish-loop 编排 + 现有 3 checker 升级

### 5.1 现有 3 checker 阈值升级（reader-pull / sensory-immersion / high-point）

读 `config/checker-thresholds.yaml` → checker 输出加 `block_threshold / blocked / cases_hit` 字段（不动算法）：

```python
# ink_writer/checkers/reader_pull/checker.py 末尾加
def check_reader_pull(*, chapter_text, ...) -> ReaderPullReport:
    # ... existing 算分逻辑保持不变
    cfg = load_thresholds()["reader_pull"]
    blocked = (
        score < cfg["block_threshold"]
        and not _is_dry_run()  # dry-run 期间 blocked 仍标记但不真阻断
    )
    cases_hit = _query_cases_by_tags(cfg["bound_cases"])
    return ReaderPullReport(score=score, blocked=blocked, cases_hit=cases_hit, ...)
```

类似改造 sensory_immersion / high_point（共 3 处文件改 ≤ 20 行/处）。

### 5.2 阻断重写循环（核心调度）

新增 `ink_writer/rewrite_loop/orchestrator.py`：

```python
def run_rewrite_loop(
    *,
    book: str,
    chapter: str,
    chapter_text: str,
    cfg: dict,
) -> tuple[str, EvidenceChain]:
    evidence = EvidenceChain(book=book, chapter=chapter, dry_run=_is_dry_run())
    current_text = chapter_text
    
    for round_idx in range(cfg["rewrite_loop"]["max_rounds"] + 1):
        compliance = writer_self_check(chapter_text=current_text, ...)
        evidence.record_self_check(round_idx, compliance)
        
        check_results = run_all_checkers(current_text, cfg)
        evidence.record_checkers(round_idx, check_results)
        
        blocking_cases = _collect_blocking_cases(compliance, check_results)
        if not blocking_cases:
            evidence.outcome = "delivered"
            break
        
        if round_idx >= cfg["rewrite_loop"]["max_rounds"]:
            evidence.outcome = "needs_human_review"
            _write_human_review_jsonl(book, chapter, blocking_cases, evidence)
            break
        
        target_case = blocking_cases[0]  # 按 severity 排序后第一个
        rewrite_input = _build_polish_prompt(
            chapter_text=current_text,
            case_id=target_case.case_id,
            case_failure_pattern=target_case.failure_pattern,
            related_chunks=None,
        )
        current_text = polish_agent_rewrite(rewrite_input)
        evidence.record_polish(round_idx, target_case.case_id, "rewrite_for_single_case")
    
    return current_text, evidence
```

### 5.3 polish-agent 改造（接收 case_id 驱动）

`ink-writer/agents/polish-agent.md` 改 prompt：

```
你是网文章节定向重写助手。给定一段章节 + 一个具体的失败模式（病例），
针对该病例重写章节，使其规避该失败模式。

输入：
- 当前章节正文
- 病例 case_id: CASE-2026-0042
- 病例失败模式: "突发事件→主角理性恢复之间缺情绪缓冲，缺生理反应描写"
- 病例修复建议（observable 字段）: ["突发事件后到理性反应之间字符数 >= 200", ...]
- 相关 corpus chunks（M3 期为空）

要求：
1. 只针对该 case 重写最小必要段落，不要全章重写
2. 保留原章节其他部分不动
3. 输出完整重写后的章节正文（不输出 diff）
4. 末尾附 1 行说明：修改了哪几段（便于溯源）

不要包裹 markdown，直接输出重写后正文。
```

### 5.4 阻断 cases 排序

```python
def _collect_blocking_cases(compliance, check_results) -> list[Case]:
    all_blockers = []
    if not compliance.overall_passed:
        all_blockers.extend(case_store.load(cid) for cid in compliance.cases_violated)
    for r in check_results:
        if r.blocked:
            all_blockers.extend(case_store.load(cid) for cid in r.cases_hit)
    
    # 去重 + 按 severity 排序（P0 优先）
    seen = set()
    unique = []
    for c in all_blockers:
        if c.case_id not in seen:
            seen.add(c.case_id)
            unique.append(c)
    unique.sort(key=lambda c: ["P0", "P1", "P2", "P3"].index(c.severity.value))
    return unique
```

### 5.5 needs_human_review.jsonl 兜底

```python
# data/<book>/needs_human_review.jsonl
{
  "book": "都市A",
  "chapter": "ch005",
  "blocking_cases": ["CASE-2026-0042", "CASE-2026-0017"],
  "rewrite_attempts": 3,
  "final_chapter_path": "data/都市A/chapters/ch005.txt",
  "rewrite_history": [
    "data/都市A/chapters/ch005.r0.txt",
    "data/都市A/chapters/ch005.r1.txt",
    "data/都市A/chapters/ch005.r2.txt",
    "data/都市A/chapters/ch005.r3.txt"
  ],
  "evidence_chain_path": "data/都市A/chapters/ch005.evidence.json",
  "marked_at": "2026-04-25T12:00:00Z"
}
```

不删稿，4 版全保留；默认交付**最佳一次**（合规率最高的那版）。

### 5.6 dry-run 模式控制

```python
def _is_dry_run() -> bool:
    cfg = load_thresholds()["dry_run"]
    if not cfg["enabled"]:
        return False
    counter_path = Path("data/.dry_run_counter")
    counter = int(counter_path.read_text()) if counter_path.is_file() else 0
    if counter >= cfg["observation_chapters"] and cfg["switch_to_block_after"]:
        return False
    return True

def _increment_dry_run_counter():
    counter_path = Path("data/.dry_run_counter")
    n = (int(counter_path.read_text()) if counter_path.is_file() else 0) + 1
    counter_path.write_text(str(n))
```

dry-run 期间 `blocked=True` 但不真触发 polish，只在 evidence_chain 标 `dry_run: true` + `would_have_blocked: true`。5 章累积后下一章自动进真阻断模式。

### 5.7 配置 (`config/checker-thresholds.yaml`)

```yaml
writer_self_check:
  rule_compliance_threshold: 0.70

reader_pull:
  block_threshold: 60
  warn_threshold: 75
  bound_cases:
    - tag: reader_immersion
    - tag: hook_weak

sensory_immersion:
  block_threshold: 65
  warn_threshold: 78
  bound_cases:
    - tag: sensory_grounding
    - tag: scene_visualization

high_point:
  block_threshold: 70
  warn_threshold: 80
  bound_cases:
    - tag: payoff_pacing
    - tag: climax_buildup

conflict_skeleton:
  block_threshold: 0.60
  bound_cases:
    - tag: no_explicit_conflict

protagonist_agency:
  block_threshold: 0.60
  bound_cases:
    - tag: protagonist_passive

rewrite_loop:
  max_rounds: 3
  needs_human_review_path: "data/<book>/needs_human_review.jsonl"

dry_run:
  enabled: true
  observation_chapters: 5
  switch_to_block_after: true
```

### 5.8 测试策略（8 个 e2e 用例）

| 测试 | 覆盖 |
|---|---|
| `test_orchestrator_passes_when_all_clear` | 首轮全过 → outcome="delivered" |
| `test_orchestrator_rewrites_until_pass` | 首轮 1 case 阻断 → polish 后通过 |
| `test_orchestrator_3_rounds_then_human_review` | 3 轮仍阻断 → outcome="needs_human_review" + jsonl 写入 + 4 版保留 |
| `test_orchestrator_one_case_per_round` | 2 阻断 case → 第 1 轮修 case_A、第 2 轮修 case_B（按 severity）|
| `test_orchestrator_dry_run_does_not_trigger_polish` | dry_run=true → blocked=True 但 polish 0 次 |
| `test_orchestrator_dry_run_counter_auto_switch_after_5` | 5 章后第 6 章 dry_run=False |
| `test_polish_prompt_contains_case_failure_pattern` | polish 调用 prompt 含 case 的 failure_pattern.description |
| `test_human_review_keeps_all_4_versions` | needs_human_review 时 r0-r3.txt 全保留 |

### 5.9 钩子插入点

| 文件 | 改动 |
|---|---|
| `config/checker-thresholds.yaml` | 新增 |
| `ink_writer/rewrite_loop/{__init__,orchestrator,dry_run,polish_prompt,human_review}.py` | 新增 |
| `ink_writer/checkers/{reader_pull,sensory_immersion,high_point}/checker.py` | 改造（加 block_threshold + cases_hit）|
| `ink-writer/agents/polish-agent.md` | 改 prompt |
| `ink-writer/skills/ink-write/SKILL.md` | 流程加新循环 |
| `tests/rewrite_loop/test_orchestrator.py` | 新增 8 用例 |

---

## 6. evidence_chain.json schema + dry-run 报告

### 6.1 完整 schema

```json
{
  "$schema": "https://ink-writer/evidence_chain_v1",
  "book": "都市A",
  "chapter": "ch005",
  "produced_at": "2026-04-25T12:30:00Z",
  "dry_run": false,
  "outcome": "delivered",
  
  "phase_evidence": {
    "context_agent": {
      "recalled": {"rules": 12, "chunks": 0, "cases": 8},
      "recall_quality_avg": null
    },
    
    "writer_agent": {
      "prompt_hash": "abc123def456",
      "model": "glm-4.6",
      "rounds": [
        {
          "round": 0,
          "compliance_report": {
            "rule_compliance": 0.65,
            "chunk_borrowing": null,
            "cases_addressed": ["CASE-2026-0017"],
            "cases_violated": ["CASE-2026-0042"],
            "raw_scores": {"EW-0001": 0.7, "EW-0042": 0.5, ...},
            "overall_passed": false,
            "notes": "..."
          }
        },
        {
          "round": 1,
          "compliance_report": {
            "rule_compliance": 0.78,
            "cases_violated": [],
            "overall_passed": true
          }
        }
      ]
    },
    
    "checkers": [
      {"id": "reader-pull", "score": 78, "blocked": false, "cases_hit": []},
      {"id": "sensory-immersion", "score": 81, "blocked": false, "cases_hit": []},
      {"id": "high-point", "score": 73, "blocked": false, "cases_hit": []},
      {"id": "conflict-skeleton", "score": 0.85, "blocked": false, "cases_hit": []},
      {"id": "protagonist-agency", "score": 0.70, "blocked": false, "cases_hit": []}
    ],
    
    "polish_agent": {
      "rewrite_rounds": 1,
      "rewrite_drivers": [
        {"round": 1, "case_id": "CASE-2026-0042", "result": "passed_after"}
      ]
    }
  },
  
  "case_evidence_updates": [
    {"case_id": "CASE-2026-0017", "result": "passed", "by": "writer_self_check.round_0"},
    {"case_id": "CASE-2026-0042", "result": "passed_after_polish", "by": "polish.round_1"}
  ],
  
  "human_overrides": []
}
```

### 6.2 evidence_chain 写入工具

```python
def write_evidence_chain(*, book, chapter, evidence) -> Path:
    """缺则抛 EvidenceChainMissingError 让 ink-write 退出（强制必带）。"""
    out_path = Path(f"data/{book}/chapters/{chapter}.evidence.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(evidence.to_dict(), fp, ensure_ascii=False, indent=2)
    return out_path
```

### 6.3 dry-run 切换报告

5 章 dry-run 后自动产 `data/dry_run_report_<timestamp>.md`：

```python
def generate_dry_run_report(book: str) -> Path:
    chapters = _collect_dry_run_chapters(book)
    return _write_markdown_report(
        chapters,
        metrics={
            "重写率": "30/50 = 60%",
            "needs_human_review 率": "5/50 = 10%",
            "checker 命中率 top10": [...],
            "case 命中率 top10": [...],
            "rule_compliance 分布": [...],
            "成本": "$X.XX",
        },
        recommendations=[
            "case CASE-2026-0042 命中率 90% → 建议退回 pending",
            "high-point block_threshold 70 → 建议调 65（命中率过高）",
        ]
    )
```

报告供作者 review，决定是否切真阻断 / 调阈值 / 退回某些 case。

### 6.4 钩子插入点

| 文件 | 改动 |
|---|---|
| `ink_writer/evidence_chain/__init__.py` | 新增 |
| `ink_writer/evidence_chain/models.py` | 新增 `EvidenceChain` dataclass |
| `ink_writer/evidence_chain/writer.py` | 新增 `write_evidence_chain` + `EvidenceChainMissingError` |
| `ink_writer/evidence_chain/dry_run_report.py` | 新增 `generate_dry_run_report` |
| `tests/evidence_chain/test_writer.py` | 新增 |
| `tests/evidence_chain/test_dry_run_report.py` | 新增 |

---

## 7. 实施计划

### 7.1 14 US 顺序（按依赖关系）

| US | 标题 | 关键依赖 |
|---|---|---|
| US-001 | `config/checker-thresholds.yaml` schema + 加载器 | M2 |
| US-002 | `evidence_chain.json` schema + 写入工具（`EvidenceChainMissingError`）| M1 |
| US-003 | `writer-self-check` agent (rule_compliance + cases_addressed/violated)| M1 + M2 |
| US-004 | `conflict-skeleton-checker` agent (3 段结构判定 + score 公式)| M1 cases |
| US-005 | `protagonist-agency-checker` agent (主动决策 + 推动剧情判定)| M1 cases |
| US-006 | reader-pull / sensory-immersion / high-point 加 block_threshold + cases_hit | 现有 checker 改造 |
| US-007 | `polish-agent` 改 prompt 接收 case_id 驱动 | M1 ingest_case |
| US-008 | rewrite_loop orchestrator (max 3 轮 + cases 排序 + needs_human_review) | US-003~007 |
| US-009 | dry-run 模式控制 + counter + auto-switch | US-008 |
| US-010 | `needs_human_review.jsonl` 兜底 + 4 版 (r0-r3) 保留 | US-008 |
| US-011 | ink-write SKILL.md 集成新循环 | US-008+009+010 |
| US-012 | dry-run 5 章 smoke + 切换报告生成 | US-011 + 真章节产出 |
| US-013 | M3 e2e 集成测试 (8-10 用例) | 全部 |
| US-014 | M3 验收 + tag `m3-p1-loop` + 更新 M-ROADMAP | US-013 |

**估时**：14 US × ~22 分钟 ≈ **5 小时**

### 7.2 工作量预估

| 类别 | 数量 |
|---|---|
| 新增 Python 模块 | 7 (writer_self_check / 2 checkers / rewrite_loop / dry_run / human_review / evidence_chain) |
| 改造 Python 模块 | 3 (reader_pull/sensory_immersion/high_point checker)|
| 新增 prompts | 4 (self_check / conflict_skeleton / protagonist_agency / polish-agent 改 prompt) |
| 新增 config | 1 (`checker-thresholds.yaml`) |
| 改造 SKILL.md | 1 (ink-write) |
| 改造 agent.md | 4 (polish-agent + 3 新)|
| 新增测试 | 12-15 测试文件 |
| 新增 testpaths | 4 个 |
| LLM 成本 | dry-run 5 章 + e2e 测试 ≈ $5（GLM-4.6）|
| ralph 跑完时间 | 14 US × ~22 分钟 ≈ **5 小时** |

### 7.3 风险与护栏

| # | 风险 | 触发 | 护栏 |
|---|---|---|---|
| 1 | 236 active hard cases 一次上线**重写率 > 80%** | dry-run 5 章 | dry-run 报告暴露 + 建议退回 case |
| 2 | rule_compliance LLM 主观判断不稳 | 任何时候 | evidence_chain 留 raw_scores 供反查 |
| 3 | 重写 3 轮成本翻 4× | 上线日 | 监控总 token；超预算自动切 dry-run |
| 4 | conflict-skeleton-checker 误判序章/插曲 | dry-run 期 | 加 case-level 豁免（命中 case.scope.chapter 例外列表）|
| 5 | protagonist-agency 误判群像章 | dry-run 期 | scope.character_focus 字段（dry-run 暴露后加）|
| 6 | evidence_chain.json 占磁盘（每章 ~5KB × 数百章 = MB 级）| 长期 | 1 年后归档 + 压缩（M5 dashboard 配套）|
| 7 | dry-run 5 章自动切真阻断**没人盯**会上线翻车 | 5 章后 | 报告自动产 + 必须人工 review；可改 yaml `switch_to_block_after: false` |
| 8 | M2 chunk_borrowing=null 让 evidence_chain 看着不完整 | 任何时候 | 字段保留 null 兼容 M2 follow-up；schema doc 注释清楚 |
| 9 | needs_human_review 4 版保留占磁盘 | 长期 | 1 年后归档；rewrite_history 字段独立目录便于清理 |

### 7.4 验收标准（M3 结束）

| 指标 | 验收线 |
|---|---|
| `pytest -q` 全绿 | 必过 + 覆盖率 ≥ 70（M2 baseline 82.72%）|
| M3 新增测试 | ≥ 30 个全绿 |
| dry-run 5 章产出 | `data/dry_run_report_*.md` 生成 + 含 metrics + recommendations |
| evidence_chain.json 强制 | 任意章节交付必带；缺则 ink-write 抛错 |
| 重写循环最多 3 轮 | needs_human_review.jsonl 兜底；4 版保留 |
| `git tag m3-p1-loop` | 已打 |
| `M-ROADMAP.md` M3 行 | ⚪ → ✅ + 完成日期 |

### 7.5 不在本期范围

- ❌ chunk_borrowing 实际计算（chunks=0，留 M2 follow-up）
- ❌ Layer 4 复发追踪 → M5
- ❌ Layer 5 元规则浮现 → M5
- ❌ A/B 通道 → M5
- ❌ ink dashboard 扩展 → M5
- ❌ P0 上游策划层 → M4
- ❌ 现有 23 checker 全部加 block_threshold（仅 3 个）

---

## 8. 关键决议记录

| 决议 | 选择 | 决议依据 |
|---|---|---|
| writer-self-check 时机 | 章末整章评 + 整章重写（Q1）| 与 ralph fresh context 节奏一致 |
| rule_compliance 阈值 | 0.70（Q2）| spec §5.1 默认 |
| 重写最大轮数 | 3 次（Q3）| 平衡质量与成本 |
| 3 轮失败处置 | needs_human_review.jsonl 不删稿（Q4）| 保留 4 版让作者决定 |
| evidence_chain.json | 强制必带（Q5）| 消灭"靠感觉"痛点 |
| conflict-skeleton 触发 | 每章必跑（Q6）| 简单可靠 |
| conflict 判定方式 | LLM 主观判断 + 三段结构（Q7）| 语义任务非客观规则 |
| protagonist-agency 判定 | LLM 主观判断主动性（Q8）| 同 Q7 |
| 现有 checker 升级 | reader-pull / sensory-immersion / high-point 3 个（Q9）| 直接对应 30 分扣分项 |
| dry-run 时长 | 5 章观察后自动切真阻断（Q10）| 节奏紧凑且可调阈值 |
| dry-run 产物 | evidence_chain + dry_run:true 字段（Q11）| 与正式产物同结构便对比 |
| polish 重写策略 | 一次一个 case，按 severity 排序（Q12）| 隔离干扰 + 可溯源 |
| 配置热更新 | 启动时读一次（Q13）| 最简，符合 ralph 节奏 |
| LLM model | glm-4.6（Q14）| 调用量小不撞 RPM |
| chunk_borrowing 处理 | 字段保留 null（Q15）| 兼容 M2 follow-up |
| 整体范围 | 方案 A 完整 14 US | dry-run 是 spec 强制护栏 |

---

## 9. 后续步骤

1. 用户 review 本 spec
2. 调用 `superpowers:writing-plans` 生成 14-task implementation plan
3. `/prd` → `tasks/prd-m3-p1-loop.md`
4. `/ralph` → `prd.json` + branch `ralph/m3-p1-loop`
5. 后台启动 ralph：`bash scripts/ralph/ralph.sh --tool claude 14`
6. M3 跑完后：验收 + 打 tag `m3-p1-loop` + 更新 `M-ROADMAP.md`（M3 ✅）
7. 进入 M4（P0 上游策划层；与 M3 并行的另一条线，不依赖 M3 完成）

---

## 附录 A：关联文档

- `docs/superpowers/specs/2026-04-23-case-library-driven-quality-overhaul-design.md` — M1-M5 总 spec（§5 P1 + §9 M3）
- `docs/superpowers/M-ROADMAP.md` — 5 周 milestone 进度跟踪
- `docs/superpowers/M3-PREPARATION-NOTES.md` — M3 brainstorm 准备材料（14 题草拟）
- `docs/superpowers/M2-FOLLOWUP-NOTES.md` — M2 corpus_chunks deferred 调研报告
- `docs/superpowers/specs/2026-04-24-m2-data-assets-design.md` — M2 spec
- `docs/superpowers/plans/2026-04-24-m2-data-assets.md` — M2 plan
- `data/case_library/cases/*.yaml` — 403 cases（M3 评估的输入）
- `~/.claude/ink-writer/.env` — LLM 配置
- `progress.txt` / `prd.json` — ralph 当前 PRD 与跨迭代记忆
