"""Layer 4 regression tracker — detects resolved cases that regressed.

Public surface used by the M5 dashboard / CLI:

- :func:`scan_evidence_chains` — scan every chapter / planning evidence chain in
  ``base_dir`` and emit one :class:`RecurrenceRecord` per (book, case_id) where
  a *resolved* case re-appeared in ``cases_violated`` / ``cases_hit``.
- :func:`apply_recurrence` — persist a single record into the case library
  (severity bump + ``status=regressed`` + history append).

Spec §4 Q3: only same-book recurrences count by default; cross-book matches are
out of scope until the M5 P3 follow-up loop wires them in.
"""
from ink_writer.regression_tracker.models import RecurrenceRecord
from ink_writer.regression_tracker.tracker import (
    apply_recurrence,
    scan_evidence_chains,
)

__all__ = [
    "RecurrenceRecord",
    "apply_recurrence",
    "scan_evidence_chains",
]
