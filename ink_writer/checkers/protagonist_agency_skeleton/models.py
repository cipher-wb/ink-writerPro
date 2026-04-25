"""ProtagonistAgencySkeletonReport — protagonist-agency-skeleton-checker 的输出结构。

spec §3.6：用 LLM 对卷大纲每章 summary 打 agency_score 0-1，平均 → score，
block_threshold=0.55（与 M3 章节级 protagonist-agency 不同：本 checker 在 ink-plan 阶段
针对卷骨架 summary 做，不需要章节正文）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProtagonistAgencySkeletonReport:
    score: float
    blocked: bool
    per_chapter: list[dict[str, Any]]
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "per_chapter": [dict(item) for item in self.per_chapter],
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
