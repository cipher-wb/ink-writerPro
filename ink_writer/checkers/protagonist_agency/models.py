"""AgencyReport — protagonist-agency-checker 的输出结构。

spec §4.2：检测主角是否做出 ≥ 1 个主动决策 + ≥ 1 次推动剧情，反"主角当摄像头"
（直接对应 spec §1.3 都市书扣分项）。

score 公式（spec §4.2 + Q8，结构与 conflict_skeleton 同）::

    score = 0.5 * has_active_decision + 0.3 * has_plot_drive + 0.2 * min(count / 2, 1)

block_threshold 默认 0.60；blocked = score < threshold。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgencyReport:
    has_active_decision: bool
    has_plot_drive: bool
    decision_count: int
    decision_summaries: list[str]
    score: float
    block_threshold: float
    blocked: bool
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_active_decision": self.has_active_decision,
            "has_plot_drive": self.has_plot_drive,
            "decision_count": self.decision_count,
            "decision_summaries": list(self.decision_summaries),
            "score": self.score,
            "block_threshold": self.block_threshold,
            "blocked": self.blocked,
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
