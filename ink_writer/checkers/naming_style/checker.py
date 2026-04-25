"""check_naming_style() — M4 ink-init 策划期角色起名风格 checker（spec §3.3）。

纯规则实现（无 LLM 调用）。词典格式：

```json
{
  "version": "1.0",
  "exact_blacklist": ["叶凡", "林夜", ...],
  "char_patterns": {
    "first_char_overused": ["叶", "林", ...],
    "second_char_overused": ["凡", "夜", ...]
  },
  "notes": "..."
}
```

打分规则（按优先级短路）：

- exact match → (0.0, 'exact')
- 双字模式（首字 ∈ first_char_overused **且** 末字 ∈ second_char_overused）→ (0.4, 'double_char')
- 单字模式（首字 ∈ first_char_overused **或** 末字 ∈ second_char_overused）→ (0.7, 'single_char')
- 否则 → (1.0, 'clean')

整体 `score = mean(per_name_scores)`，`blocked = score < block_threshold`（默认 0.70）。

边界：

- `character_names` 为空 → `score=1.0, blocked=False, notes='no_names'`
- 词典文件缺失或解析失败 → `score=0.0, blocked=True, notes='blacklist_missing: <path>'`
- 单个 entry 缺 name 或 name 为空 → 跳过该 entry（不计入 mean）
- `cases_hit` 默认空列表（由 planning_review 在阻断时按 config case_ids 注入）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ink_writer.checkers.naming_style.models import NamingStyleReport

_DEFAULT_BLOCK_THRESHOLD = 0.70
_DEFAULT_BLACKLIST_PATH = Path("data/market_intelligence/llm_naming_blacklist.json")


def _load_blacklist(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("blacklist root is not a JSON object")
    return data


def _score_one_name(
    name: str,
    *,
    exact_set: set[str],
    first_set: set[str],
    second_set: set[str],
) -> tuple[float, str]:
    if not name:
        return 1.0, "clean"
    if name in exact_set:
        return 0.0, "exact"
    first_char = name[0]
    last_char = name[-1]
    first_hit = first_char in first_set
    last_hit = last_char in second_set
    if first_hit and last_hit:
        return 0.4, "double_char"
    if first_hit or last_hit:
        return 0.7, "single_char"
    return 1.0, "clean"


def check_naming_style(
    *,
    character_names: list[dict[str, Any]],
    blacklist_path: Path | str | None = None,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
) -> NamingStyleReport:
    """spec §3.3 实现 — 见模块 docstring。"""
    if not character_names:
        return NamingStyleReport(
            score=1.0,
            blocked=False,
            per_name_scores=[],
            cases_hit=[],
            notes="no_names",
        )

    path = Path(blacklist_path) if blacklist_path is not None else _DEFAULT_BLACKLIST_PATH
    try:
        blacklist = _load_blacklist(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return NamingStyleReport(
            score=0.0,
            blocked=True,
            per_name_scores=[],
            cases_hit=[],
            notes=f"blacklist_missing: {path} ({exc.__class__.__name__})",
        )

    exact_set = set(blacklist.get("exact_blacklist", []) or [])
    char_patterns = blacklist.get("char_patterns", {}) or {}
    first_set = set(char_patterns.get("first_char_overused", []) or [])
    second_set = set(char_patterns.get("second_char_overused", []) or [])

    per_name_scores: list[dict[str, Any]] = []
    for entry in character_names:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "") or "").strip()
        if not name:
            continue
        role = str(entry.get("role", "") or "")
        score, hit_type = _score_one_name(
            name,
            exact_set=exact_set,
            first_set=first_set,
            second_set=second_set,
        )
        per_name_scores.append(
            {
                "role": role,
                "name": name,
                "score": score,
                "hit_type": hit_type,
            }
        )

    if not per_name_scores:
        return NamingStyleReport(
            score=1.0,
            blocked=False,
            per_name_scores=[],
            cases_hit=[],
            notes="no_names",
        )

    score = sum(item["score"] for item in per_name_scores) / len(per_name_scores)
    blocked = score < block_threshold

    return NamingStyleReport(
        score=score,
        blocked=blocked,
        per_name_scores=per_name_scores,
        cases_hit=[],
        notes="",
    )
