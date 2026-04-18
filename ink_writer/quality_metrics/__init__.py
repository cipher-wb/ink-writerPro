"""Q1-Q8 quality metrics dashboard (US-018).

All metrics are derived from direct SQL queries against `.ink/index.db`
(and its `state_kv` table) — zero LLM calls.

Entry points:
    - :func:`collect_quality_metrics` — run all 8 collectors for a chapter range.
    - :class:`QualityReport`        — dataclass with 8 metric fields + ``to_dict()``.
"""

from ink_writer.quality_metrics.collectors import (
    QualityReport,
    collect_quality_metrics,
)

__all__ = ["QualityReport", "collect_quality_metrics"]
