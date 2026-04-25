---
name: golden-finger-timing-checker
description: M4 ink-plan 策划期金手指出场时机检查 — regex 主 + LLM 回退判断金手指是否在前 3 章 summary 出现；硬阻断 block_threshold=1.0（passed→1.0 / failed→0.0）
tools: Read
model: inherit
---

# golden-finger-timing-checker (策划期金手指出场时机检查)

> **职责**：判断金手指是否在前 3 章章节梗概中出现。先用 regex 字面命中（不调 LLM），
> regex miss 时调 LLM 做语义二次判断（覆盖别名、变体、首次触发场景）。在策划期阻断
> spec §1.3 "金手指出场过晚 / 前 3 章看不到金手指" 扣分项。**硬阻断**——
> `block_threshold=1.0`，意味着只要未命中（regex+LLM 都 miss）就 100% 阻断。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.5
- PRD：`tasks/prd-m4-p0-planning.md` US-009
- 实现：`ink_writer/checkers/golden_finger_timing/{__init__,models,checker}.py`
- prompt：`ink_writer/checkers/golden_finger_timing/prompts/check.txt`

## 输入（Python 调用）

```python
from ink_writer.checkers.golden_finger_timing import check_golden_finger_timing

report = check_golden_finger_timing(
    outline_volume_skeleton=[
        {"chapter_idx": 1, "summary": "顾望安拾起古玉佩，浮现万道归一剑诀残影。"},
        {"chapter_idx": 2, "summary": "..."},
        {"chapter_idx": 3, "summary": "..."},
        # 后续章节...
    ],
    golden_finger_keywords=["万道归一", "天地同心剑诀"],
    llm_client=llm_client,            # 兼容 .messages.create() 的对象
    block_threshold=1.0,              # 默认 1.0 硬阻断，由 thresholds_loader 注入
    model="glm-4.6",
    max_retries=2,
)
```

## 输出 GoldenFingerTimingReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | 命中 `1.0`，未命中 `0.0` |
| `blocked` | bool | `score < block_threshold`（默认 1.0 → 任何未命中都阻断）|
| `regex_match` | bool | regex 是否字面命中前 3 章 summary |
| `llm_match` | `bool \| None` | regex 命中时为 `None`；regex miss 时由 LLM 决定 |
| `matched_chapter` | `int \| None` | 命中章节 1~3；未命中为 `None` |
| `cases_hit` | `list[str]` | 由 planning_review 在阻断时按 config case_ids 注入 |
| `notes` | str | 异常前缀 `outline_too_short:` / `empty_keywords` / `checker_failed:`，正常路径回填 LLM `reason` |

## 判定流水线

1. **outline 长度检查**：`outline_volume_skeleton` 不足 3 章 → 直接 blocked，
   `notes='outline_too_short: <n> < 3'`，不调 LLM。
2. **keywords 非空检查**：`golden_finger_keywords` 全空白 → 直接 blocked，
   `notes='empty_keywords'`，不调 LLM。
3. **regex 字面扫描**（前 3 章 summary）：用 `re.escape(kw)` 拼 OR pattern，扫到任一关键词
   命中 → `score=1.0, blocked=False, regex_match=True, llm_match=None,
   matched_chapter=<命中章 1~3>`，**不调 LLM**。
4. **LLM 语义二次判断**（regex miss 时）：把前 3 章 summary 与 keywords 一起送入
   LLM，要求输出 `{matched, matched_chapter, reason}`。
   - `matched=True` 且 `matched_chapter ∈ {1,2,3}` → `score=1.0, blocked=False,
     regex_match=False, llm_match=True`。
   - `matched=False` → `score=0.0, blocked=True, regex_match=False, llm_match=False,
     matched_chapter=None`。
5. **LLM/JSON 解析失败**：重试 `max_retries` 次后仍失败 → `score=0.0, blocked=True,
   notes='checker_failed: <err>'`（保守降级）。

## 阻断行为

- 硬阻断：`block_threshold=1.0`（参考 `config/checker-thresholds.yaml`
  `golden_finger_timing` 段）。任何 `score < 1.0` 都阻断，没有 warn 缓冲带。
- 含 markdown ``` 代码块的 LLM 响应自动剥离再解析。

## 与下游的衔接

- `ink_writer.planning_review.ink_plan_review.run_ink_plan_review(...)` 把
  `GoldenFingerTimingReport.to_dict()` 写入
  `<base_dir>/<book>/planning_evidence_chain.json`（phase=planning, stage=ink-plan）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0005"]`（来自 thresholds_loader 的
  `golden_finger_timing.case_ids`）。
