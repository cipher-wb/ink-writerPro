"""Dataclass for a single Layer 4 recurrence event."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RecurrenceRecord:
    """One observation that a *resolved* case re-appeared in evidence.

    ``chapter`` is ``None`` when the hit comes from a planning-stage evidence
    chain (``data/<book>/planning_evidence_chain.json``).
    """

    case_id: str
    book: str
    chapter: str | None
    evidence_chain_path: str
    resolved_at: str
    regressed_at: str
    severity_before: str
    severity_after: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "book": self.book,
            "chapter": self.chapter,
            "evidence_chain_path": self.evidence_chain_path,
            "resolved_at": self.resolved_at,
            "regressed_at": self.regressed_at,
            "severity_before": self.severity_before,
            "severity_after": self.severity_after,
        }
