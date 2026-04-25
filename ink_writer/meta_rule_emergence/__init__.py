"""Layer 5 meta-rule emergence — propose merging N similar cases into one rule.

Public surface used by ink CLI / dashboard:

- :func:`find_similar_clusters` — pure function: scan cases → candidate
  clusters → LLM verdict → proposals (no I/O).
- :func:`write_meta_rule_proposal` — persist one proposal as YAML under
  ``data/case_library/meta_rules/MR-NNNN.yaml`` (status=pending).
- :class:`MetaRuleProposal` — dataclass payload.

Spec §5 / §7.2 Layer 5: ``sovereign=True`` cases and cases that already carry
``meta_rule_id`` are excluded from clustering.
"""
from ink_writer.meta_rule_emergence.emerger import (
    find_similar_clusters,
    write_meta_rule_proposal,
)
from ink_writer.meta_rule_emergence.models import MetaRuleProposal

__all__ = [
    "MetaRuleProposal",
    "find_similar_clusters",
    "write_meta_rule_proposal",
]
