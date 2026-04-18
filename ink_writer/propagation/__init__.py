"""FIX-17 propagation debt: track rule violations requiring back-propagation fixes."""

from ink_writer.propagation.models import (
    PropagationDebtFile,
    PropagationDebtItem,
)
from ink_writer.propagation.debt_store import DebtStore
from ink_writer.propagation.drift_detector import detect_drifts
from ink_writer.propagation.macro_integration import (
    DEFAULT_INTERVAL,
    INTERVAL_ENV,
    get_interval,
    run_propagation,
    should_run,
)
from ink_writer.propagation.plan_integration import (
    ACTIVE_STATUSES,
    filter_debts_for_range,
    load_active_debts,
    mark_debts_resolved,
    render_debts_for_plan,
)

__all__ = [
    "PropagationDebtFile",
    "PropagationDebtItem",
    "DebtStore",
    "detect_drifts",
    "DEFAULT_INTERVAL",
    "INTERVAL_ENV",
    "get_interval",
    "run_propagation",
    "should_run",
    "ACTIVE_STATUSES",
    "load_active_debts",
    "filter_debts_for_range",
    "mark_debts_resolved",
    "render_debts_for_plan",
]
