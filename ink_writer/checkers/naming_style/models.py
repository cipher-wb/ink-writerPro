"""NamingStyleReport — naming-style-checker 的输出结构。

spec §3.3：依赖 `data/market_intelligence/llm_naming_blacklist.json` 词典对每个角色
名打分：exact match → 0.0；双字模式（首字 + 末字均命中）→ 0.4；单字模式 → 0.7；
clean → 1.0；多名取均值；block_threshold=0.70。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NamingStyleReport:
    score: float
    blocked: bool
    per_name_scores: list[dict[str, Any]]
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "per_name_scores": [dict(item) for item in self.per_name_scores],
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
