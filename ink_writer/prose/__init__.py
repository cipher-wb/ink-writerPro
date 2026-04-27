"""Prose-level tooling for the directness (US-003..US-010) pipeline."""

from ink_writer.prose.blacklist_loader import (
    Blacklist,
    BlacklistEntry,
    clear_cache,
    load_blacklist,
)
from ink_writer.prose.colloquial_checker import (
    DIMENSION_KEYS as COLLOQUIAL_DIMENSION_KEYS,
)
from ink_writer.prose.colloquial_checker import (
    ColloquialReport,
    run_colloquial_check,
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
    ReplacementResult,
    SimplificationReport,
    apply_replacement_map,
    should_activate_simplification,
    simplify_text,
)

__all__ = [
    "Blacklist",
    "BlacklistEntry",
    "COLLOQUIAL_DIMENSION_KEYS",
    "ColloquialReport",
    "FLOW_NATURALNESS_CHECKER_NAME",
    "FLOW_NATURALNESS_RELAXED_RULES",
    "PROSE_IMPACT_CHECKER_NAME",
    "PROSE_IMPACT_RELAXED_RULES",
    "ReplacementResult",
    "SENSORY_IMMERSION_CHECKER_NAME",
    "SimplificationReport",
    "apply_replacement_map",
    "clear_cache",
    "is_relaxed_issue",
    "load_blacklist",
    "run_colloquial_check",
    "should_activate_simplification",
    "should_relax_flow_naturalness",
    "should_relax_prose_impact",
    "should_skip_sensory_immersion",
    "simplify_text",
]
