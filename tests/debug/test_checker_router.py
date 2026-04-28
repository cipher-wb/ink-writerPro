"""Tests for checker_router Layer B."""
from __future__ import annotations

from ink_writer.debug.checker_router import route, SUPPORTED_CHECKERS


def test_consistency_red_violation_to_error_incident():
    report = {"violations": [
        {"severity": "red", "kind": "character_drift", "message": "name changed"},
    ]}
    incidents = route("consistency", report, run_id="r1", chapter=1, skill="ink-write")
    assert len(incidents) == 1
    assert incidents[0].source == "layer_b_checker"
    assert incidents[0].severity == "error"
    assert incidents[0].kind == "checker.consistency.character_drift"


def test_yellow_violation_to_warn():
    report = {"violations": [
        {"severity": "yellow", "kind": "tone_inconsistency", "message": "tone shift"},
    ]}
    incidents = route("ooc", report, run_id="r1", chapter=1, skill="ink-write")
    assert incidents[0].severity == "warn"
    assert incidents[0].kind == "checker.ooc.tone_inconsistency"


def test_green_or_no_violations_returns_empty():
    report = {"violations": [{"severity": "green", "kind": "ok", "message": "fine"}]}
    incidents = route("consistency", report, run_id="r1", chapter=1, skill="ink-write")
    assert incidents == []


def test_unsupported_checker_returns_empty():
    incidents = route("unknown_checker", {"violations": []}, run_id="r1", chapter=1, skill="ink-write")
    assert incidents == []


def test_supported_checkers_list():
    assert "consistency" in SUPPORTED_CHECKERS
    assert "continuity" in SUPPORTED_CHECKERS
    assert "live-review" in SUPPORTED_CHECKERS
    assert "ooc" in SUPPORTED_CHECKERS
    assert "reader-simulator" in SUPPORTED_CHECKERS
