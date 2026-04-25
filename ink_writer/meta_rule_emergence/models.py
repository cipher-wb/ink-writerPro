"""Dataclass for a single Layer 5 meta-rule proposal."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetaRuleProposal:
    """One LLM-judged proposal that N similar cases be merged into a meta-rule.

    ``proposal_id`` is allocated by :func:`_next_proposal_id` (``MR-NNNN``);
    ``status`` is always ``"pending"`` on first write — user approval flips it
    to ``approved`` (US-004) which stamps ``meta_rule_id`` onto each covered
    case.
    """

    proposal_id: str
    similarity: float
    merged_rule: str
    covered_cases: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "status": "pending",
            "similarity": self.similarity,
            "merged_rule": self.merged_rule,
            "covered_cases": list(self.covered_cases),
            "reason": self.reason,
        }
