"""US-022: Macro reflection agent.

Periodically scans recent chapter summaries + character progression ledgers
and distils 3-5 "emergent phenomena" bullets to ``.ink/reflections.json``.
Consumed by context-agent as an L2 memory layer.
"""
from ink_writer.reflection.reflection_agent import (  # noqa: F401
    ReflectionResult,
    load_reflections,
    run_reflection,
)
