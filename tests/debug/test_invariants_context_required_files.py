"""Tests for context_required_files invariant."""
from __future__ import annotations

from ink_writer.debug.invariants.context_required_files import check


def test_missing_file_returns_warn_incident():
    inc = check(
        required=["a.md", "b.md", "c.md"],
        actually_read=["a.md", "b.md"],
        run_id="r1",
        chapter=1,
    )
    assert inc is not None
    assert inc.kind == "context.missing_required_skill_file"
    assert inc.severity == "warn"
    assert inc.evidence["missing"] == ["c.md"]


def test_all_read_returns_none():
    inc = check(
        required=["a.md"],
        actually_read=["a.md"],
        run_id="r1",
        chapter=1,
    )
    assert inc is None


def test_empty_required_returns_none_fail_soft():
    """If skill declares no required list, fail soft."""
    inc = check(
        required=[],
        actually_read=[],
        run_id="r1",
        chapter=1,
    )
    assert inc is None
