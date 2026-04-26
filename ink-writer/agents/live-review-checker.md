---
name: live-review-checker
description: 起点编辑星河直播稿训练的网文审查器，基于 174 份直播 × 10+ 本/份的病例库对章节进行评分，输出 violations 与命中案例。
tools: Read
model: inherit
---

# live-review-checker

> 对任意章节可用。基于 live-review 病例库 (CASE-LR-*.yaml) 通过 FAISS 语义召回 Top-K 相似病例，逐条比对正文，输出结构化评分与违规列表。与 `editor-wisdom-checker` OR 并列（两者都不通过才阻断；任一通过即放行）。

{{PROMPT_TEMPLATE:checker-input-rules.md}}

**本 agent 默认数据源**: 审查包中的正文、`data/case_library/cases/live_review/` 下的 CASE-LR-*.yaml、`data/live-review/genre_acceptance.json`、`data/live-review/vector_index/`。

## Purpose

- 把 174 份起点编辑星河 B 站直播稿沉淀的"作品病例 + 题材接受度信号"作为硬约束注入审查链路。
- 与 editor-wisdom-checker 互补：editor-wisdom 来自小红书/抖音 288 份原子规则，live-review 来自直播逐稿点评（更接近最终签约决策），两者 OR 并列降低误阻断。
- 黄金三章（chapter ≤ 3）使用更高阈值 `golden_three_threshold`（默认 0.75）；其他章节使用 `hard_gate_threshold`（默认 0.65）。

## Input

- `chapter_text`: 章节正文（必填）
- `chapter_no`: 章节号（必填）
- `genre_tags`: 题材标签列表（如 `['都市', '重生']`），用于 FAISS 检索 query 拼接
- `config`: `LiveReviewConfig`（含阈值与开关，由 `ink_writer.live_review.config.load_config` 加载）

## Retrieval

1. 拼接检索 query：`" ".join(genre_tags) + " " + chapter_text[:500]`。
2. 加载 `data/live-review/vector_index/index.faiss + meta.jsonl`（由 `scripts/live-review/build_vector_index.py` 构建）。
3. bge-small-zh-v1.5 编码 query → IndexFlatIP cosine top-K（默认 K=5）→ 返回元数据列表（含 `case_id` / `verdict` / `score` / `overall_comment`）。
4. 检索结果作为 LLM prompt 的"相似病例"段输入，并用作 `cases_hit` 字段的默认填充。

## Scoring

- 综合 `score = (1 - violation_density) × verdict_pass_rate_of_top5`。
  - `violation_density`：被命中规则数 / Top-K 数；
  - `verdict_pass_rate_of_top5`：Top-K 中 `verdict=='pass'` 的占比；
  - 两者皆 ∈ [0, 1]，乘积亦在 [0, 1]。
- 输出额外的 `dimensions`（如 `opening / pacing / golden_finger / character / hook` 等子维度评分），由 LLM 按命中维度分别打分（0-1，无该维度违规默认 1.0）。
- 阈值由调用方根据 `chapter_no` 选择：
  - `chapter_no <= 3` → `golden_three_threshold`（默认 0.75）；
  - `chapter_no > 3` → `hard_gate_threshold`（默认 0.65）；
- 违反阈值后调用方触发 `polish-agent` 修复循环（最多 2 次重试），与 `editor-wisdom-checker` 复用同一 polish 接口。

## Output

```json
{
  "score": 0.45,
  "dimensions": {
    "opening": 0.4,
    "pacing": 0.3,
    "golden_finger": 0.5,
    "character": 0.6
  },
  "violations": [
    {
      "case_id": "CASE-LR-2026-0001",
      "dimension": "opening",
      "evidence_quote": "公元前 4570 年，原始大陆的地脉之力在地壳深处涌动……",
      "severity": "negative"
    }
  ],
  "cases_hit": [
    "CASE-LR-2026-0001",
    "CASE-LR-2026-0005",
    "CASE-LR-2026-0009"
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float (0-1) | 综合评分；`< threshold` 触发 polish |
| `dimensions` | dict[str, float] | 各子维度评分（0-1，1.0 = 无违规） |
| `violations` | list[dict] | 命中违规列表，每条含 case_id / dimension / evidence_quote / severity |
| `cases_hit` | list[str] | 检索 + LLM 判定相关的 case_id 列表 |

## 判定规则

### violations[].severity 三档

- `negative`：明显违反对应病例的失败模式（计入 violation_density）。
- `neutral`：触发但情节自洽（仅记录，不计 violation_density）。
- `positive`：刻意模仿病例的成功模式（不计入 violation_density）。

### evidence_quote 引用

- 必须引用正文中违规的具体段落（不超过 100 字）。
- 多段同类违规取最显眼一段；不要拼接多段（拼接会破坏定位 anchoring）。

## 与 editor-wisdom-checker 的关系（OR 并列）

- 两 checker 数据源独立：editor-wisdom 用原子规则库，live-review 用病例库。
- 调用方 OR 合并判定：`editor_wisdom_passed OR live_review_passed → 放行`。
- 两者都不通过才阻断（写 `chapters/{n}/blocked.md`）。
- polish-agent 接收两路 violations 合集，统一修复一轮。

## 关闭开关

- `config/live-review.yaml:inject_into.review: false` → 本 checker 短路（不调用 LLM、不阻断）。
- `config/live-review.yaml:enabled: false` → master switch，全模块短路。
- 测试链路通过 `mock_response` 注入跳过 retriever 与 LLM 加载（避免 bge ~30s）。
