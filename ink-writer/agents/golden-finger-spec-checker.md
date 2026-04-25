---
name: golden-finger-spec-checker
description: M4 ink-init 策划期金手指规格检查 — LLM 4 维度评估金手指描述（clarity/falsifiability/boundary/growth_curve），mean → score，block_threshold=0.65；description < 20 字直接阻断
tools: Read
model: inherit
---

# golden-finger-spec-checker (策划期金手指规格检查)

> **职责**：用 LLM 从 4 个维度评估当前书的金手指描述质量，算术平均得到 score；
> 在策划期阻断 spec §1.3 "金手指模糊 / 一招鲜上帝模式" 扣分项。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.2
- PRD：`tasks/prd-m4-p0-planning.md` US-004
- 实现：`ink_writer/checkers/golden_finger_spec/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/golden_finger_spec/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.golden_finger_spec import check_golden_finger_spec

report = check_golden_finger_spec(
    description="主角觉醒『万道归一』之力：可融合任意两种已掌握的功法...",
    llm_client=llm_client,            # 兼容 .messages.create() 的对象
    block_threshold=0.65,             # 默认 0.65，由 thresholds_loader 注入
    model="glm-4.6",
    max_retries=2,
)
```

## 输出 GoldenFingerSpecReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `mean(4 dim)` |
| `blocked` | bool | `score < block_threshold` |
| `dim_scores` | dict[str, float] | 4 个维度各 0-1：`clarity / falsifiability / boundary / growth_curve` |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | LLM 的简短中文说明；`description_too_short` 或 `checker_failed: <err>` |

## 评估维度

1. **clarity（清晰度）**：金手指核心机制是否表述清楚（"是什么、怎么用"）。
2. **falsifiability（可证伪性）**：是否有具体可验证的能力边界与触发条件。
3. **boundary（限制条件）**：是否有明确代价 / 冷却 / 副作用 / 失败条件。
4. **growth_curve（成长曲线）**：是否暗示从弱到强的可拆段成长路径。

## 阻断行为

- **description 短文本豁免**：`description` 缺失或 strip 后 < 20 字 → 直接返回
  `score=0.0, blocked=True, notes="description_too_short"`，不调 LLM
  （拦截"主角有金手指"这种空描述强迫策划期补全规格）。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
  notes="checker_failed: <err>"`（保守降级，让 planning_review 拿到失败信号阻断策划期）。
- 含 markdown ``` 代码块的 LLM 响应自动剥离再解析。

## 阈值

- `block_threshold = 0.65`，配置在 `config/checker-thresholds.yaml` 的
  `golden_finger_spec` 段（由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()`
  加载）。

## 与下游的衔接

- `ink_writer.planning_review.ink_init_review.run_ink_init_review(...)` 把
  `GoldenFingerSpecReport.to_dict()` 写入 `<base_dir>/<book>/planning_evidence_chain.json`
  （phase=planning, stage=ink-init）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0002"]`（来自 thresholds_loader 的
  `golden_finger_spec.case_ids`）。
