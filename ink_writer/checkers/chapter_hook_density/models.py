"""ChapterHookDensityReport — chapter-hook-density-checker 的输出结构。

spec §3.7：用 LLM 对卷大纲每章 summary 打 hook_strength 0-1，
density = strong_count / total_count（strong threshold = 0.5），
block_threshold=0.70；空 skeleton → 保守阻断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChapterHookDensityReport:
    score: float
    blocked: bool
    per_chapter: list[dict[str, Any]]
    strong_count: int
    total_count: int
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "per_chapter": [dict(item) for item in self.per_chapter],
            "strong_count": self.strong_count,
            "total_count": self.total_count,
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
