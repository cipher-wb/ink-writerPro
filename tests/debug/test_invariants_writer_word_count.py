"""Tests for writer_word_count invariant."""
from __future__ import annotations

import pytest

from ink_writer.debug.invariants.writer_word_count import check


def test_short_text_returns_incident():
    inc = check(text="x" * 1000, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is not None
    assert inc.kind == "writer.short_word_count"
    assert inc.severity == "warn"
    assert inc.evidence == {"length": 1000, "min": 2200}


def test_sufficient_text_returns_none():
    inc = check(text="x" * 2500, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is None


def test_exact_min_returns_none():
    inc = check(text="x" * 2200, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc is None
