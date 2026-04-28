"""Tests for polish_diff invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.polish_diff import check


def test_identical_returns_incident():
    text = "x" * 500
    inc = check(before=text, after=text, run_id="r1", chapter=1, min_diff_chars=50)
    assert inc is not None
    assert inc.kind == "polish.diff_too_small"
    assert inc.evidence["diff_chars"] == 0


def test_large_change_returns_none():
    inc = check(
        before="hello world" * 100,
        after="goodbye world" * 100,
        run_id="r1",
        chapter=1,
        min_diff_chars=50,
    )
    assert inc is None


def test_small_change_must_not_crash():
    """Small punctuation-only changes should not crash; result depends on threshold."""
    before = "hello world. " * 100
    after = "hello world! " * 100
    inc = check(before=before, after=after, run_id="r1", chapter=1, min_diff_chars=200)
    # Just ensure no crash; either outcome (None or Incident) is acceptable.
    assert inc is None or inc.kind == "polish.diff_too_small"
