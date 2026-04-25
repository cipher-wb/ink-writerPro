"""Dashboard aggregation surface — M5 治理指标 + overview JSON。

Public surface used by ink CLI and the Web Dashboard:

- :mod:`ink_writer.dashboard.aggregator` — pure metric helpers (recurrence
  rate, repair speed, editor score trend, checker accuracy, dry-run pass
  rate, switch recommendation).
- :mod:`ink_writer.dashboard.m5_overview` — bundled JSON payload served at
  ``/api/m5-overview``.

Spec §13 acceptance: all helpers degrade gracefully when source files are
missing (return ``0.0`` / empty list) so a fresh project never crashes the
dashboard.
"""
from ink_writer.dashboard.aggregator import (
    compute_checker_accuracy,
    compute_editor_score_trend,
    compute_m3_dry_run_pass_rate,
    compute_m4_dry_run_pass_rate,
    compute_recurrence_rate,
    compute_repair_speed,
    recommend_dry_run_switch,
)
from ink_writer.dashboard.m5_overview import get_m5_overview

__all__ = [
    "compute_checker_accuracy",
    "compute_editor_score_trend",
    "compute_m3_dry_run_pass_rate",
    "compute_m4_dry_run_pass_rate",
    "compute_recurrence_rate",
    "compute_repair_speed",
    "get_m5_overview",
    "recommend_dry_run_switch",
]
