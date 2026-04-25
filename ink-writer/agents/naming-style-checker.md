---
name: naming-style-checker
description: M4 ink-init 策划期角色起名风格检查 — 纯规则（无 LLM）：用 data/market_intelligence/llm_naming_blacklist.json 词典对每个角色名打分（exact/双字/单字/clean），mean → score，block_threshold=0.70；词典缺失直接阻断
tools: Read
model: inherit
---

# naming-style-checker (策划期角色起名风格检查)

> **职责**：对当前书的主角 / 重要配角名做"AI 模板味"打分，在策划期阻断
> spec §1.3 "角色名 AI 味重（叶凡 / 林夜 / 陈青山）" 扣分项。
>
> **本 checker 不调 LLM**，纯规则匹配，毫秒级可重入。

## 来源 spec / PRD

- spec：`docs/superpowers/specs/2026-04-25-m4-p0-planning-design.md` §3.3
- PRD：`tasks/prd-m4-p0-planning.md` US-005
- 实现：`ink_writer/checkers/naming_style/{__init__,models,checker}.py`
- 词典：`data/market_intelligence/llm_naming_blacklist.json`（US-008 落档）

## 输入（Python 调用）

```python
from ink_writer.checkers.naming_style import check_naming_style

report = check_naming_style(
    character_names=[
        {"role": "主角", "name": "顾望安"},
        {"role": "女主", "name": "蓝漪"},
    ],
    blacklist_path=None,           # 默认 data/market_intelligence/llm_naming_blacklist.json
    block_threshold=0.70,          # 默认 0.70，由 thresholds_loader 注入
)
```

## 输出 NamingStyleReport

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | float | `mean(per_name_scores)` |
| `blocked` | bool | `score < block_threshold` |
| `per_name_scores` | list[dict] | 每个名字一条 `{role, name, score, hit_type}` |
| `cases_hit` | list[str] | 由 planning_review 在阻断时按 config case_ids 注入；本 agent 不主动填充 |
| `notes` | str | `no_names` / `blacklist_missing: <path> (<err>)` / 空字符串 |

## 评分规则（按优先级短路）

| 优先级 | 命中条件 | score | hit_type |
|---|---|---|---|
| 1 | name ∈ `exact_blacklist` | 0.0 | `exact` |
| 2 | 首字 ∈ `first_char_overused` **且** 末字 ∈ `second_char_overused` | 0.4 | `double_char` |
| 3 | 首字 ∈ `first_char_overused` **或** 末字 ∈ `second_char_overused` | 0.7 | `single_char` |
| 4 | 全无命中 | 1.0 | `clean` |

## 词典格式

```json
{
  "version": "1.0",
  "exact_blacklist": ["叶凡", "林夜", "陈青山", ...],
  "char_patterns": {
    "first_char_overused": ["叶", "林", "沈", "陈", "苏", ...],
    "second_char_overused": ["凡", "夜", "尘", "墨", "辰", ...]
  },
  "notes": "..."
}
```

US-008 落档要求 `exact_blacklist ≥ 250`、`first_char_overused ≥ 24`、
`second_char_overused ≥ 24`，全部中文字符。

## 阻断行为

- **空名单豁免**：`character_names=[]` → 直接 `score=1.0, blocked=False, notes='no_names'`，不读词典。
- **词典缺失保守阻断**：默认或自定义路径文件不存在 / JSON 解析失败 →
  `score=0.0, blocked=True, notes='blacklist_missing: <path> (<ErrClass>)'`
  （拒绝在没有真相源的情况下放行）。
- **单 entry 容错**：name 缺失 / 空字符串 / 非 dict → 跳过该 entry 不计入 mean；
  全跳过则等同空名单。

## 阈值

- `block_threshold = 0.70`，配置在 `config/checker-thresholds.yaml` 的
  `naming_style` 段（由 `ink_writer.checker_pipeline.thresholds_loader.load_thresholds()`
  加载）。语义：容忍 1-2 个字根模式（0.7 边界），禁止 exact match。

## 与下游的衔接

- `ink_writer.planning_review.ink_init_review.run_ink_init_review(...)` 把
  `NamingStyleReport.to_dict()` 写入 `<base_dir>/<book>/planning_evidence_chain.json`
  （phase=planning, stage=ink-init）。
- 阻断时 `cases_hit` 注入 `["CASE-2026-M4-0003"]`（来自 thresholds_loader 的
  `naming_style.case_ids`）。
