"""ComplianceReport — writer-self-check 的输出结构。

spec §3.2：rule_compliance (mean of injected rule scores)、chunk_borrowing
（M3 期 None）、cases_addressed / cases_violated 二分、raw_scores 透传 LLM 原始数值、
overall_passed = rule_compliance >= 0.70 且 cases_violated 为空。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ComplianceReport:
    rule_compliance: float
    chunk_borrowing: float | None
    cases_addressed: list[str]
    cases_violated: list[str]
    raw_scores: dict[str, Any]
    overall_passed: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_compliance": self.rule_compliance,
            "chunk_borrowing": self.chunk_borrowing,
            "cases_addressed": list(self.cases_addressed),
            "cases_violated": list(self.cases_violated),
            "raw_scores": dict(self.raw_scores),
            "overall_passed": self.overall_passed,
            "notes": self.notes,
        }
