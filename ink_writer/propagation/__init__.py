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
]
