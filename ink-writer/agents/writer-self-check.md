---
name: writer-self-check
description: M3 写完比对 agent — rule_compliance + cases_addressed/violated 二分；overall_passed = rule_compliance ≥ 0.70 且 cases_violated 为空
tools: Read
model: inherit
---

# writer-self-check (写章自检)

> **职责**：章节定稿（writer 出稿）后立即调用，对照已注入规则与适用病例自评，
> 输出 `ComplianceReport`，决定是否进入下游 checker pipeline 或直接交 polish。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m3-p1-loop-design.md` §3
- PRD：`tasks/prd-m3-p1-loop.md` US-003
- 实现：`ink_writer/writer_self_check/{__init__,models,checker}.py`
- prompt：`ink_writer/writer_self_check/prompts/self_check.txt`

## 输入（Python 调用）

```python
from ink_writer.writer_self_check import writer_self_check

report = writer_self_check(
    chapter_text=chapter_text,
    injected_rules=[{"rule_id": "RULE-001", "text": "..."}, ...],
    injected_chunks=None,                # M3 期占位（M2 chunks deferred 兼容）
    applicable_cases=[{"case_id": "CASE-2026-0001",
                       "failure_description": "...",
                       "observable": "..."}, ...],
    book="书名",
    chapter="0001",
    llm_client=llm_client,               # 兼容 .messages.create() 的对象
    max_retries=3,
)
```

## 输出 ComplianceReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `rule_compliance` | float | mean(rule_scores)；漏给的 rule_id 按 0；空规则 → 1.0 |
| `chunk_borrowing` | None | M3 期始终为 None（spec §3.5 风险 8） |
| `cases_addressed` | list[str] | LLM 显式标 addressed=True 的 case_id |
| `cases_violated` | list[str] | LLM 未提及或标 addressed=False 的 case_id（保守） |
| `raw_scores` | dict | 透传 LLM rule_scores + case_evaluation 原文，便于审计 |
| `overall_passed` | bool | rule_compliance ≥ 0.70 且 cases_violated 为空 |
| `notes` | str | LLM 自评简注；失败时为 `"self_check_failed"` |

## 阻断行为

- `overall_passed=False` 时由 `rewrite_loop.orchestrator.run_rewrite_loop` 把
  `cases_violated` 收集进 blocking_cases，按 severity P0→P3 排序后调 polish-agent。
- LLM JSON 解析失败重试 `max_retries` 次后仍失败 → 返回 failed report
  （`overall_passed=False, notes="self_check_failed"`），把全部 `applicable_cases`
  视作 violated（保守降级）。

## 阈值

- `rule_compliance_threshold = 0.70`，配置在
  `config/checker-thresholds.yaml` 的 `writer_self_check` 段
  （由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()` 加载）。

## L12 对话+动作驱动律检测（US-009）

`writer-agent.md` 铁律 L12（对话+动作驱动律）包含四条子律，起草后自检应覆盖：

- **L12a 对话/动作密度**：每 200 字 ≥ 1 句对话或 1 个具体动作
- **L12b 段首禁抽象**：段首句不以抽象名词/抽象副词开篇
- **L12c 段首优先级**：环境段首每章 ≤ 2 处
- **L12d 场景冲突**：每场景有明确冲突（人 vs 人 / 人 vs 环境 / 人 vs 自己）

检测逻辑由 `colloquial-checker`（C1-C5 白话度）与 `directness-checker`（D1-D7 直白度）联合执行，
不在 `writer-self-check` 内独立实现。writer-self-check 的 `injected_rules` 应包含 L12a-L12d
的 rule_id，由 LLM 自评打分。

## 与下游的衔接

- `evidence_chain.EvidenceChain.record_self_check(round_idx=..., compliance_report=report.to_dict())`
  把每轮自检写入 evidence 记录。
- 后续 5 个 checker（reader_pull / sensory_immersion / high_point /
  conflict_skeleton / protagonist_agency）对其 `cases_hit` 与本 agent 的
  `cases_violated` 求并集，作为 polish 的输入队列。
