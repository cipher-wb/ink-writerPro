"""M3/M4 evidence_chain 模块：每章/每书产 evidence_chain 强制必带（spec §6 + M4 P0）。"""

from __future__ import annotations

from ink_writer.evidence_chain.models import EvidenceChain
from ink_writer.evidence_chain.planning_writer import (
    PlanningEvidenceChainMissingError,
    require_planning_evidence_chain,
    write_planning_evidence_chain,
)
from ink_writer.evidence_chain.writer import (
    EvidenceChainMissingError,
    require_evidence_chain,
    write_evidence_chain,
)

__all__ = [
    "EvidenceChain",
    "EvidenceChainMissingError",
    "PlanningEvidenceChainMissingError",
    "require_evidence_chain",
    "require_planning_evidence_chain",
    "write_evidence_chain",
    "write_planning_evidence_chain",
]
