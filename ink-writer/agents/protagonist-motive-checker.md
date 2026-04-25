---
name: protagonist-motive-checker
description: M4 ink-init 策划期主角动机检查 — LLM 3 维度评估主角动机描述（resonance/specific_goal/inner_conflict），mean → score，block_threshold=0.65；description < 20 字直接阻断
tools: Read
model: inherit
---

# protagonist-motive-checker (策划期主角动机检查)

> **职责**：用 LLM 从 3 个维度评估当前书的主角核心动机描述质量，算术平均得到
> score；在策划期阻断 spec §1.3 "主角动机牵强 / 空喊口号" 扣分项。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.4
- PRD：`tasks/prd-m4-p0-planning.md` US-006
- 实现：`ink_writer/checkers/protagonist_motive/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/protagonist_motive/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.protagonist_motive import check_protagonist_motive

report = check_protagonist_motive(
    description="顾望安是战争遗孤……他想找到当年放走幸存者的那位敌国军官……",
    llm_client=llm_client,            # 兼容 .messages.create() 的对象
    block_threshold=0.65,             # 默认 0.65，由 thresholds_loader 注入
    model="glm-4.6",
    max_retries=2,
)
```

## 输出 ProtagonistMotiveReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `mean(3 dim)` |
| `blocked` | bool | `score < block_threshold` |
| `dim_scores` | dict[str, float] | 3 个维度各 0-1：`resonance / specific_goal / inner_conflict` |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | LLM 的简短中文说明；`description_too_short` 或 `checker_failed: <err>` |

## 评估维度

1. **resonance（情感共鸣度）**：动机是否能让普通读者代入或理解（恐惧、爱、复仇、
   守护、不甘等普世情感）。空洞口号、无情感锚点扣分。
2. **specific_goal（具体目标）**：是否给出可被场景化的近期目标（"找到失踪的妹妹"
   而不是"称霸天下"）。
3. **inner_conflict（内在矛盾）**：动机内部是否有张力或代价（让选择本身有纠结感）。
   单向无阻力的行动扣分。

## 阻断行为

- **description 短文本豁免**：`description` 缺失或 strip 后 < 20 字 → 直接返回
  `score=0.0, blocked=True, notes="description_too_short"`，不调 LLM
  （拦截"主角想变强"这种空描述强迫策划期补全主角动机）。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
  notes="checker_failed: <err>"`（保守降级，让 planning_review 拿到失败信号阻断策划期）。
- 含 markdown ``` 代码块的 LLM 响应自动剥离再解析。

## 阈值

- `block_threshold = 0.65`，配置在 `config/checker-thresholds.yaml` 的
  `protagonist_motive` 段（由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()`
  加载）。

## 与下游的衔接

- `ink_writer.planning_review.ink_init_review.run_ink_init_review(...)` 把
  `ProtagonistMotiveReport.to_dict()` 写入 `<base_dir>/<book>/planning_evidence_chain.json`
  （phase=planning, stage=ink-init）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0004"]`（来自 thresholds_loader 的
  `protagonist_motive.case_ids`）。
