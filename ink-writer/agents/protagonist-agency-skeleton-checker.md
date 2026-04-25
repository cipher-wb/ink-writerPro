---
name: protagonist-agency-skeleton-checker
description: M4 ink-plan 策划期主角能动性骨架检查 — LLM 对每章 summary 打 agency_score 0-1，平均 → score，block_threshold=0.55；空 skeleton 直接阻断
tools: Read
model: inherit
---

# protagonist-agency-skeleton-checker (策划期主角能动性骨架检查)

> **职责**：用 LLM 对当前书"卷大纲骨架"逐章评估主角能动性
> （每章 summary 一行），算术平均得到 score；在策划期阻断 spec §1.3
> "卷骨架阶段主角全程被动 / 工具人"扣分项。
> **与 M3 章节级 protagonist-agency 不同**：本 checker 只看 summary 一行，
> 不需要章节正文，专门拦截卷骨架阶段的能动性问题。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.6
- PRD：`tasks/prd-m4-p0-planning.md` US-010
- 实现：`ink_writer/checkers/protagonist_agency_skeleton/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/protagonist_agency_skeleton/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.protagonist_agency_skeleton import (
    check_protagonist_agency_skeleton,
)

report = check_protagonist_agency_skeleton(
    outline_volume_skeleton=[
        {"chapter_idx": 1, "summary": "顾望安主动潜入敌国军营寻找当年放走幸存者的军官。"},
        {"chapter_idx": 2, "summary": "顾望安做出关键决定：放弃复仇路径，转而保护战时孤儿。"},
        # ...
    ],
    llm_client=llm_client,            # 兼容 .messages.create() 的对象
    block_threshold=0.55,             # 默认 0.55，由 thresholds_loader 注入
    model="glm-4.6",
    max_retries=2,
)
```

## 输出 ProtagonistAgencySkeletonReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `mean(per_chapter agency_score)` |
| `blocked` | bool | `score < block_threshold` |
| `per_chapter` | list[dict] | 每章 `{chapter_idx, agency_score, reason}`；agency_score 0-1 |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | `empty_skeleton` 或 `checker_failed: <err>`；正常路径为空字符串 |

## 评分标尺

- `agency_score >= 0.7`：主角明确主动决策且承担后果驱动剧情
- `0.4 < agency_score < 0.7`：半主动 / 部分被动
- `agency_score <= 0.4`：完全被动 / 工具人 / NPC 拉去办事

## 阻断行为

- **空 skeleton**：`outline_volume_skeleton` 为空列表 → 直接返回
  `score=0.0, blocked=True, notes="empty_skeleton"`，不调 LLM
  （拦截"卷大纲未填"强迫策划期补全卷骨架）。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
  notes="checker_failed: <err>"`（保守降级，让 planning_review 拿到失败信号阻断策划期）。
- **per_chapter 全部条目无法解析**：返回 `score=0.0, blocked=True,
  notes="checker_failed: no valid per_chapter entries"`。
- 含 markdown ``` 代码块的 LLM 响应自动剥离再解析。

## 阈值

- `block_threshold = 0.55`，配置在 `config/checker-thresholds.yaml` 的
  `protagonist_agency_skeleton` 段（由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()`
  加载）。

## 与下游的衔接

- `ink_writer.planning_review.ink_plan_review.run_ink_plan_review(...)` 把
  `ProtagonistAgencySkeletonReport.to_dict()` 写入 `<base_dir>/<book>/planning_evidence_chain.json`
  （phase=planning, stage=ink-plan）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0006"]`（来自 thresholds_loader 的
  `protagonist_agency_skeleton.case_ids`）。
