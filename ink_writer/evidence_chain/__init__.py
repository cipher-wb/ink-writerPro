"""M3 evidence_chain 模块：每章产 evidence_chain.json 强制必带（spec §6）。"""

from __future__ import annotations

from ink_writer.evidence_chain.models import EvidenceChain
from ink_writer.evidence_chain.writer import (
    EvidenceChainMissingError,
    require_evidence_chain,
    write_evidence_chain,
)

__all__ = [
    "EvidenceChain",
    "EvidenceChainMissingError",
    "require_evidence_chain",
    "write_evidence_chain",
]
