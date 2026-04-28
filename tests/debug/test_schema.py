"""Tests for ink_writer.debug.schema."""
from __future__ import annotations

import json

import pytest

from ink_writer.debug.schema import Incident, KIND_WHITELIST, validate_kind


def test_incident_required_fields():
    inc = Incident(
        ts="2026-04-28T14:23:51.123Z",
        run_id="auto-2026-04-28-batch12",
        source="layer_c_invariant",
        skill="ink-write",
        kind="writer.short_word_count",
        severity="warn",
        message="word count too low",
    )
    assert inc.ts == "2026-04-28T14:23:51.123Z"
    assert inc.severity == "warn"


def test_incident_to_jsonl_line_round_trip():
    inc = Incident(
        ts="2026-04-28T14:23:51.123Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="ink-write",
        kind="polish.diff_too_small",
        severity="warn",
        message="diff too small",
        evidence={"diff_chars": 32, "threshold": 50},
    )
    line = inc.to_jsonl_line()
    assert line.endswith("\n")
    decoded = json.loads(line)
    assert decoded["evidence"]["diff_chars"] == 32


def test_kind_whitelist_contains_reserved():
    for k in [
        "writer.short_word_count",
        "polish.diff_too_small",
        "review.missing_dimensions",
        "context.missing_required_skill_file",
        "auto.skill_step_skipped",
        "hook.pre_tool_use",
        "hook.post_tool_use",
        "hook.subagent_stop",
        "hook.stop",
        "hook.session_end",
        "meta.invariant_crashed",
        "meta.unknown_kind",
        "meta.collector_error",
    ]:
        assert k in KIND_WHITELIST


def test_validate_kind_accepts_checker_pattern():
    # checker.<name>.<problem> dynamic pattern
    assert validate_kind("checker.consistency.character_drift") is True
    assert validate_kind("checker.continuity.timeline_break") is True


def test_validate_kind_rejects_unknown():
    assert validate_kind("totally.made.up") is False


def test_validate_kind_rejects_non_ascii_or_uppercase():
    # Unicode in segment
    assert validate_kind("checker.x.中文") is False
    # Uppercase
    assert validate_kind("checker.UPPER.case") is False
    # Hyphen
    assert validate_kind("checker.foo-bar.baz") is False
    # Two-part (too short)
    assert validate_kind("checker.foo") is False
    # Empty
    assert validate_kind("") is False
    # Underscore-only segment
    assert validate_kind("checker._.x") is False
    # Leading digit (not a valid identifier)
    assert validate_kind("checker.123.foo") is False


def test_validate_kind_accepts_all_whitelist():
    for k in KIND_WHITELIST:
        assert validate_kind(k) is True, f"validate_kind({k!r}) should be True"


def test_severity_validation():
    with pytest.raises(ValueError, match="severity"):
        Incident(
            ts="2026-04-28T14:23:51Z",
            run_id="r1",
            source="layer_c_invariant",
            skill="x",
            kind="writer.short_word_count",
            severity="critical",  # invalid
            message="x",
        )


def test_to_dict_omits_empty_containers():
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="writer.short_word_count",
        severity="info",
        message="x",
        evidence={},  # empty dict should be omitted
    )
    d = inc.to_dict()
    assert "evidence" not in d


def test_incident_is_frozen():
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="writer.short_word_count",
        severity="info",
        message="x",
    )
    with pytest.raises(Exception):  # FrozenInstanceError or similar
        inc.severity = "warn"
