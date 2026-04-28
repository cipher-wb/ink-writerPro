"""Tests for review_dimensions invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.review_dimensions import check


def test_too_few_dimensions_returns_incident():
    report = {"dimensions": {"d1": 0.8, "d2": 0.7}}
    inc = check(report=report, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is not None
    assert inc.kind == "review.missing_dimensions"
    assert inc.evidence["found"] == 2
    assert inc.evidence["expected"] == 7


def test_enough_dimensions_returns_none():
    report = {"dimensions": {f"d{i}": 0.7 for i in range(7)}}
    inc = check(report=report, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is None


def test_missing_dimensions_key_returns_incident():
    inc = check(report={}, skill="ink-review", run_id="r1", chapter=1, min_dimensions=7)
    assert inc is not None
    assert inc.evidence["found"] == 0
