"""GoldenFingerTimingReport — golden-finger-timing-checker 的输出结构。

spec §3.5：硬阻断（block_threshold=1.0）—— passed → 1.0，failed → 0.0。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenFingerTimingReport:
    score: float
    blocked: bool
    regex_match: bool
    llm_match: bool | None
    matched_chapter: int | None
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "blocked": self.blocked,
            "regex_match": self.regex_match,
            "llm_match": self.llm_match,
            "matched_chapter": self.matched_chapter,
            "cases_hit": list(self.cases_hit),
            "notes": self.notes,
        }
