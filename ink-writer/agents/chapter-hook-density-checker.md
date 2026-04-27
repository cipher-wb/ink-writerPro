---
name: chapter-hook-density-checker
description: M4 ink-plan 策划期卷骨架钩子密度检查 — LLM 对每章 summary 打 hook_strength 0-1，density = strong_count/total_count（strong threshold=0.5），block_threshold=0.70；空 skeleton 直接阻断
tools: Read
model: inherit
---

# chapter-hook-density-checker (策划期卷骨架钩子密度检查)

> **职责**：用 LLM 对当前书"卷大纲骨架"逐章评估章末钩子强度
> （每章 summary 一行），按 `hook_strength >= 0.5` 二值化为 strong / weak，
> density = `strong_count / total_count`；在策划期阻断 spec §1.3
> "卷骨架阶段每章 summary 都仅交代过程、缺乏悬念 / 反转"扣分项。
> **与 M3 章节级 reader-pull / opening-hook 不同**：本 checker 只看 summary 一行，
> 不需要章节正文，专门拦截卷骨架阶段的钩子稀疏问题。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.7
- PRD：`tasks/prd-m4-p0-planning.md` US-011
- 实现：`ink_writer/checkers/chapter_hook_density/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/chapter_hook_density/prompts/check.txt`
- JSON 输出规则（所有 checker 统一）：[json-output-rules.md](shared/json-output-rules.md)

## 输入（Python 调用）

```python
from ink_writer.checkers.chapter_hook_density import check_chapter_hook_density

report = check_chapter_hook_density(
    outline_volume_skeleton=[
        {"chapter_idx": 1, "summary": "顾望安发现古卷一角，遭黑衣人围杀，悬崖坠落生死未卜。"},
        {"chapter_idx": 2, "summary": "醒来发现自己被裴惊戎所救，却被告知本派已遭灭门。"},
        # ...
    ],
    llm_client=llm_client,            # 兼容 .messages.create() 的对象
    block_threshold=0.70,             # 默认 0.70，由 thresholds_loader 注入
    model="auto",  # glm-4.6 / deepseek-v4-pro / claude — 由调用方注入
    max_retries=2,
)
```

## 输出 ChapterHookDensityReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `strong_count / total_count` |
| `blocked` | bool | `score < block_threshold` |
| `per_chapter` | list[dict] | 每章 `{chapter_idx, hook_strength, strong, reason}`；strong = hook_strength ≥ 0.5 |
| `strong_count` | int | `sum(1 for c in per_chapter if c["strong"])` |
| `total_count` | int | `len(per_chapter)` |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | `empty_skeleton` 或 `checker_failed: <err>`；正常路径为空字符串 |

## 评分标尺

- `hook_strength >= 0.5`（strong）：结尾出现强反转 / 高危机 / 关键谜底 / 显著信息差
- `hook_strength < 0.5`（weak）：仅交代过程或结果、无悬念 / 无新信息差
- 二值化后取 strong 占比作为 score（不取 mean，避免高分章节稀释）

## 阻断行为

- **空 skeleton**：`outline_volume_skeleton` 为空列表 → 直接返回
  `score=0.0, blocked=True, notes="empty_skeleton"`，不调 LLM
  （拦截"卷大纲未填"强迫策划期补全卷骨架）。
- **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
  notes="checker_failed: <err>"`（保守降级，让 planning_review 拿到失败信号阻断策划期）。
- **per_chapter 全部条目无法解析**：返回 `score=0.0, blocked=True,
  notes="checker_failed: no valid per_chapter entries"`。
- 含 markdown \`\`\` 代码块的 LLM 响应自动剥离再解析（3 级容错：直接 parse → regex 提取 → strip fence 后 parse）。
- LLM prompt 包含模型无关的 JSON 输出硬规则（见 [json-output-rules.md](shared/json-output-rules.md)）：
  Do NOT wrap JSON in markdown fences；仅输出裸 JSON 数组；首次失败后重试时追加 raw-JSON-only 指令。

## 阈值

- `block_threshold = 0.70`（即 strong 占比 < 70% 阻断），配置在
  `config/checker-thresholds.yaml` 的 `chapter_hook_density` 段
  （由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()` 加载）。
- `strong threshold = 0.5`（hook_strength 二值化阈值），写死在 checker 内
  （`_STRONG_THRESHOLD` 常量）。

## 与下游的衔接

- `ink_writer.planning_review.ink_plan_review.run_ink_plan_review(...)` 把
  `ChapterHookDensityReport.to_dict()` 写入 `<base_dir>/<book>/planning_evidence_chain.json`
  （phase=planning, stage=ink-plan）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0007"]`（来自 thresholds_loader 的
  `chapter_hook_density.case_ids`）。
