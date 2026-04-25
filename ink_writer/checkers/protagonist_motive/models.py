"""ProtagonistMotiveReport — protagonist-motive-checker 的输出结构。

spec §3.4：LLM 3 维度评估主角动机描述（resonance / specific_goal /
inner_conflict），算术平均 → score，block_threshold=0.65；description < 20 字
直接 blocked=True、notes='description_too_short'。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProtagonistMotiveReport:
    score: float
    blocked: bool
    dim_scores: dict[str, float]
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "dim_scores": dict(self.dim_scores),
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
