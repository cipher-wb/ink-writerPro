"""ConflictReport — conflict-skeleton-checker 的输出结构。

spec §4.1：检测章节是否存在 ≥ 1 个显式冲突 + 三段结构（摩擦点→升级→临时收尾）。

score 公式（spec §4.1 + Q6）::

    score = 0.5 * has_conflict + 0.3 * has_three_stage + 0.2 * min(count / 2, 1)

block_threshold 默认 0.60；blocked = score < threshold。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConflictReport:
    has_explicit_conflict: bool
    conflict_count: int
    has_three_stage_structure: bool
    conflict_summaries: list[str]
    score: float
    block_threshold: float
    blocked: bool
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_explicit_conflict": self.has_explicit_conflict,
            "conflict_count": self.conflict_count,
            "has_three_stage_structure": self.has_three_stage_structure,
            "conflict_summaries": list(self.conflict_summaries),
            "score": self.score,
            "block_threshold": self.block_threshold,
            "blocked": self.blocked,
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
