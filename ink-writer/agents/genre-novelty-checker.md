---
name: genre-novelty-checker
description: M4 ink-init 策划期题材新颖度检查 — 与起点 top200 逐条比相似度，score=1.0-max(top5)，block_threshold=0.40，空 top200 跳过
tools: Read
model: inherit
---

# genre-novelty-checker (策划期题材新颖度检查)

> **职责**：把当前书的题材标签 + 主线一句话与起点 top200 榜单逐条比对，
> 取 top5 最相似 → `score = 1.0 - max(sim)`；阻断 spec §1.3 "题材老套" 扣分项
> 在策划期。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.1
- PRD：`tasks/prd-m4-p0-planning.md` US-003
- 实现：`ink_writer/checkers/genre_novelty/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/genre_novelty/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.genre_novelty import check_genre_novelty

report = check_genre_novelty(
    genre_tags=["都市", "重生"],
    main_plot_one_liner="重生回到大学，前世失意，这一世逆袭",
    top200=top200_records,           # list[dict]，缺则 [] 跳过
    llm_client=llm_client,           # 兼容 .messages.create() 的对象
    block_threshold=0.40,            # 默认 0.40，由 thresholds_loader 注入
    model="glm-4.6",
    max_retries=2,
)
```

## 输出 GenreNoveltyReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `1.0 - max(top5 similarity)` |
| `blocked` | bool | `score < block_threshold` |
| `top5_similar` | list[dict] | 每条含 `rank / title / similarity / reason` |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | 空 top200 时为 `"empty_top200_skipped"`；LLM 失败为 `"checker_failed: <err>"` |

## 阻断行为

- **空 top200 豁免**：`top200=[]` 直接返回 `score=1.0, blocked=False, notes="empty_top200_skipped"`，
  不调 LLM（数据资产缺失时不强行阻断策划期）。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
  notes="checker_failed: <err>"`（保守降级，让 planning_review 拿到失败信号阻断策划期）。
- 含 markdown ``` 代码块的 LLM 响应自动剥离再解析。

## 阈值

- `block_threshold = 0.40`，配置在 `config/checker-thresholds.yaml` 的
  `genre_novelty` 段（由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()`
  加载）。

## 与下游的衔接

- `ink_writer.planning_review.ink_init_review.run_ink_init_review(...)` 把 `GenreNoveltyReport.to_dict()`
  写入 `<base_dir>/<book>/planning_evidence_chain.json`（phase=planning, stage=ink-init）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0001"]`（来自 thresholds_loader 的 `genre_novelty.case_ids`）。
