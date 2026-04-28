"""Tests for auto_step_skipped invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.auto_step_skipped import check


def test_missing_step_returns_incident():
    inc = check(
        actual_steps=["context", "draft", "review"],
        expected_steps=["context", "draft", "review", "polish", "extract", "audit"],
        run_id="r1",
        chapter=42,
    )
    assert inc is not None
    assert inc.kind == "auto.skill_step_skipped"
    assert set(inc.evidence["missing"]) == {"polish", "extract", "audit"}


def test_all_steps_present_returns_none():
    inc = check(
        actual_steps=["context", "draft", "review", "polish", "extract", "audit"],
        expected_steps=["context", "draft", "review", "polish", "extract", "audit"],
        run_id="r1",
        chapter=42,
    )
    assert inc is None
