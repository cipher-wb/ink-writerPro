"""Prose-level tooling for the directness (US-003..US-010) pipeline."""

from ink_writer.prose.blacklist_loader import (
    Blacklist,
    BlacklistEntry,
    clear_cache,
    load_blacklist,
)
from ink_writer.prose.directness_threshold_gates import (
    FLOW_NATURALNESS_CHECKER_NAME,
    FLOW_NATURALNESS_RELAXED_RULES,
    PROSE_IMPACT_CHECKER_NAME,
    PROSE_IMPACT_RELAXED_RULES,
    is_relaxed_issue,
    should_relax_flow_naturalness,
    should_relax_prose_impact,
)
from ink_writer.prose.sensory_immersion_gate import (
    SENSORY_IMMERSION_CHECKER_NAME,
    should_skip_sensory_immersion,
)
from ink_writer.prose.simplification_pass import (
    SimplificationReport,
    should_activate_simplification,
    simplify_text,
)

__all__ = [
    "Blacklist",
    "BlacklistEntry",
    "FLOW_NATURALNESS_CHECKER_NAME",
    "FLOW_NATURALNESS_RELAXED_RULES",
    "PROSE_IMPACT_CHECKER_NAME",
    "PROSE_IMPACT_RELAXED_RULES",
    "SENSORY_IMMERSION_CHECKER_NAME",
    "SimplificationReport",
    "clear_cache",
    "is_relaxed_issue",
    "load_blacklist",
    "should_activate_simplification",
    "should_relax_flow_naturalness",
    "should_relax_prose_impact",
    "should_skip_sensory_immersion",
    "simplify_text",
]
