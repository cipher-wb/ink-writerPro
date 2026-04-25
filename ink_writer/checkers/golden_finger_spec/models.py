"""GoldenFingerSpecReport — golden-finger-spec-checker 的输出结构。

spec §3.2：LLM 4 维度评估金手指描述（clarity / falsifiability / boundary /
growth_curve），算术平均 → score，block_threshold=0.65；description < 20 字直接
blocked=True、notes='description_too_short'。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenFingerSpecReport:
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
