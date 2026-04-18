"""US-026 integration: chapter 1-3 arbitration collapses conflicting fix_prompts.

Reference: ink-writer/references/golden-three-arbitration.md

Covers:
- §3.1 same-direction conflict → merged into single fix (highest priority wins)
- §3.2 reverse conflict       → low priority dropped with reason log
- §3.3 duplicate conflict     → all sources merged under one fix, no duplicates
- Chapter >= 4                → arbitration is skipped (returns None)
"""

from __future__ import annotations

import pytest

from ink_writer.editor_wisdom.arbitration import Issue, arbitrate

pytestmark = pytest.mark.integration


def _issue(source: str, priority: str, fix: str, symptom: str, direction: str = "forward") -> Issue:
    return Issue(
        source=source,
        priority=priority,
        fix_prompt=fix,
        symptom_key=symptom,
        direction=direction,
    )


def test_chapter1_triple_conflict_merges_to_single_fix() -> None:
    """§3.3: golden-three + highpoint + editor_wisdom all fire on same symptom → 1 merged fix."""
    issues = [
        _issue("golden-three-checker#H-12", "P0", "开篇三段内必须抛爽点", "ch1_opening_hook"),
        _issue("highpoint-checker-x4#H-03", "P1", "第 1 章需一个明确高光时刻", "ch1_opening_hook"),
        _issue("editor_wisdom#EW-0087", "P2", "前 500 字挂爽点", "ch1_opening_hook"),
    ]
    result = arbitrate(chapter_id=1, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 1, (
        f"expected single merged fix, got {result['merged_fixes']}"
    )
    merged = result["merged_fixes"][0]
    assert merged["priority"] == "P0"
    # highest-priority (P0) fix_prompt wins verbatim
    assert merged["fix_prompt"] == "开篇三段内必须抛爽点"
    # all three sources traceable
    assert set(merged["sources"]) == {
        "golden-three-checker#H-12",
        "highpoint-checker-x4#H-03",
        "editor_wisdom#EW-0087",
    }
    # lower-priority items collapse into context_addendum
    assert merged["context_addendum"] is not None
    assert "EW-0087" in merged["context_addendum"]
    assert result["dropped"] == []


def test_chapter2_reverse_conflict_drops_lower_priority() -> None:
    """§3.2: golden-three says 'use golden finger now', editor_wisdom says 'delay 3 chapters' → drop EW."""
    issues = [
        _issue(
            "golden-three-checker#H-07",
            "P0",
            "主角必须在第 1 章即展示金手指",
            "golden_finger_timing",
            direction="show_now",
        ),
        _issue(
            "editor_wisdom#EW-0091",
            "P3",
            "金手指延后 3 章揭示",
            "golden_finger_timing",
            direction="delay",
        ),
    ]
    result = arbitrate(chapter_id=2, issues=issues)
    assert result is not None
    # only P0 survives
    assert len(result["merged_fixes"]) == 1
    fix = result["merged_fixes"][0]
    assert fix["priority"] == "P0"
    assert fix["sources"] == ["golden-three-checker#H-07"]
    # EW dropped with reason referencing the winning priority
    assert len(result["dropped"]) == 1
    dropped = result["dropped"][0]
    assert dropped["source"] == "editor_wisdom#EW-0091"
    assert "P0" in dropped["reason"]


def test_chapter3_same_direction_merges_context_addendum() -> None:
    """§3.1: same symptom same direction but different wording → keep P0 text, addendum low-priority."""
    issues = [
        _issue("golden-three-checker#H-20", "P0", "第一章钩子不足，补足悬念", "ch3_hook"),
        _issue("editor_wisdom#EW-0120", "P3", "建议加一个对话钩", "ch3_hook"),
    ]
    result = arbitrate(chapter_id=3, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 1
    fix = result["merged_fixes"][0]
    assert fix["fix_prompt"] == "第一章钩子不足，补足悬念"
    assert fix["context_addendum"] is not None
    assert "EW-0120" in fix["context_addendum"]
    assert fix["context_addendum"].endswith("建议加一个对话钩")


def test_chapter4_arbitration_not_applied() -> None:
    """Chapters >= 4 bypass arbitration; callers use generic checker-merge-matrix path."""
    issues = [
        _issue("golden-three-checker#H-99", "P0", "x", "whatever"),
        _issue("editor_wisdom#EW-0001", "P3", "y", "whatever"),
    ]
    assert arbitrate(chapter_id=4, issues=issues) is None
    assert arbitrate(chapter_id=100, issues=issues) is None


def test_no_conflicts_produces_parallel_fixes() -> None:
    """Independent symptoms → one merged fix each, nothing dropped."""
    issues = [
        _issue("golden-three-checker#H-01", "P0", "fix A", "symptom_a"),
        _issue("highpoint-checker-x4#H-10", "P1", "fix B", "symptom_b"),
        _issue("editor_wisdom#EW-0500", "P2", "fix C", "symptom_c"),
    ]
    result = arbitrate(chapter_id=1, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 3
    priorities = [m["priority"] for m in result["merged_fixes"]]
    # sorted by priority ascending (P0 first)
    assert priorities == ["P0", "P1", "P2"]
    assert result["dropped"] == []


def test_info_level_p4_never_produces_fix() -> None:
    """P4 (info) is context-only and must not appear in merged_fixes or dropped."""
    issues = [
        _issue("editor_wisdom#EW-INFO-1", "P4", "知道就好", "info_only"),
    ]
    result = arbitrate(chapter_id=1, issues=issues)
    assert result is not None
    assert result["merged_fixes"] == []
    assert result["dropped"] == []


def test_polish_agent_contract_fields_present() -> None:
    """polish-agent must find these exact fields per spec: issue_id, priority, fix_prompt, sources."""
    issues = [
        _issue("golden-three-checker#H-50", "P0", "fix", "x"),
    ]
    result = arbitrate(chapter_id=1, issues=issues)
    assert result is not None
    assert result["chapter_id"] == 1
    assert "merged_fixes" in result
    assert "dropped" in result
    fix = result["merged_fixes"][0]
    for key in ("issue_id", "priority", "fix_prompt", "sources", "context_addendum"):
        assert key in fix, f"merged_fix missing {key!r}: {fix}"
    assert fix["issue_id"].startswith("ARB-")
