"""GenreNoveltyReport — genre-novelty-checker 的输出结构。

spec §3.1：把当前书的题材标签 + 主线一句话与起点 top200 逐条比对，
取 top5 最相似 → score = 1.0 - max(sim)，block_threshold=0.40（直接对应 spec §1.3
"题材老套" 扣分项）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenreNoveltyReport:
    score: float
    blocked: bool
    top5_similar: list[dict[str, Any]]
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "top5_similar": [dict(item) for item in self.top5_similar],
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
