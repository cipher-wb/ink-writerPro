"""Prose-level tooling for the directness (US-003..US-010) pipeline."""

from ink_writer.prose.blacklist_loader import (
    Blacklist,
    BlacklistEntry,
    clear_cache,
    load_blacklist,
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
    "SENSORY_IMMERSION_CHECKER_NAME",
    "SimplificationReport",
    "clear_cache",
    "load_blacklist",
    "should_activate_simplification",
    "should_skip_sensory_immersion",
    "simplify_text",
]
