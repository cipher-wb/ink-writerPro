---
name: conflict-skeleton-checker
description: M3 章节级冲突骨架检查 — 显式冲突 + 三段结构（摩擦点→升级→临时收尾），block_threshold=0.60，短章节跳过
tools: Read
model: inherit
---

# conflict-skeleton-checker (章节级冲突骨架检查)

> **职责**：判断章节是否存在 ≥ 1 个显式冲突 + 三段结构（摩擦点 → 升级 → 临时收尾），
> 反"整章无冲突真空"（直接对应 spec §1 都市/玄幻通用扣分项）。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m3-p1-loop-design.md` §4.1
- PRD：`tasks/prd-m3-p1-loop.md` US-004
- 实现：`ink_writer/checkers/conflict_skeleton/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/conflict_skeleton/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.conflict_skeleton import check_conflict_skeleton

report = check_conflict_skeleton(
    chapter_text=chapter_text,
    book="书名",
    chapter="0001",
    llm_client=llm_client,        # 兼容 .messages.create() 的对象
    max_retries=3,
    block_threshold=0.60,         # 默认 0.60，由 thresholds_loader 注入
)
```

## 输出 ConflictReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `has_explicit_conflict` | bool | 章节中是否存在显式冲突 |
| `conflict_count` | int | 不同冲突线的数量 |
| `has_three_stage_structure` | bool | 至少一个冲突含三段（friction_point/escalation/interim_resolution） |
| `conflict_summaries` | list[str] | 每条冲突的"起点 → 升级 → 收尾"摘要 |
| `score` | float | 0.5×has_conflict + 0.3×has_three_stage + 0.2×min(count/2, 1) |
| `block_threshold` | float | 阻断阈值（默认 0.60） |
| `blocked` | bool | score < block_threshold |
| `cases_hit` | list[str] | 由 rewrite_loop 在阻断时按 tag 注入；本 agent 不主动填充 |
| `notes` | str | LLM 自评简注；短章节为 `"skipped_short_chapter"`，LLM 失败为 `"checker_failed"` |

## 阻断行为

- **短章节豁免**：章节字数 < 500 时直接返回 `score=0.0, blocked=False, notes="skipped_short_chapter"`，
  不调 LLM。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True, notes="checker_failed"`
  （保守降级，让 rewrite_loop 拿到失败信号触发 polish 或 needs_human_review）。
- `blocked=True` 时由 `rewrite_loop.orchestrator.run_rewrite_loop` 按 severity 排序后调 polish-agent。

## 阈值

- `block_threshold = 0.60`，配置在
  `config/checker-thresholds.yaml` 的 `conflict_skeleton` 段
  （由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()` 加载）。

## 与下游的衔接

- `evidence_chain.EvidenceChain.record_checkers(...)` 把 ConflictReport.to_dict() 写入 evidence 记录。
- `block_threshold_wrapper.apply_block_threshold` 把本 agent 的输出包装为 `CheckerOutcome`，
  供 dry-run 模式和 `would_have_blocked` 留痕。
