"""Tests for plotline fix prompt builder."""

from __future__ import annotations

import pytest

from ink_writer.plotline.tracker import InactiveInfo, PlotlineRecord, PlotlineScanResult
from ink_writer.plotline.fix_prompt_builder import (
    build_fix_prompt,
    build_inactive_violation_list,
    VIOLATION_FIX_TEMPLATES,
)


def _make_record(
    thread_id: str = "pl_001",
    title: str = "测试线程",
    line_type: str = "sub",
    last_touched: int = 80,
) -> PlotlineRecord:
    return PlotlineRecord(
        thread_id=thread_id,
        title=title,
        content=f"内容: {title}",
        line_type=line_type,
        status="active",
        planted_chapter=1,
        last_touched_chapter=last_touched,
        resolved_chapter=None,
    )


class TestViolationFixTemplates:
    def test_all_templates_present(self):
        expected = {
            "PLOTLINE_INACTIVE_CRITICAL",
            "PLOTLINE_INACTIVE_HIGH",
            "PLOTLINE_INACTIVE_MEDIUM",
            "PLOTLINE_DENSITY_HIGH",
        }
        assert set(VIOLATION_FIX_TEMPLATES.keys()) == expected

    def test_templates_contain_placeholders(self):
        assert "{title}" in VIOLATION_FIX_TEMPLATES["PLOTLINE_INACTIVE_CRITICAL"]
        assert "{gap}" in VIOLATION_FIX_TEMPLATES["PLOTLINE_INACTIVE_CRITICAL"]


class TestBuildFixPrompt:
    def test_empty_scan(self):
        scan = PlotlineScanResult(current_chapter=10, total_active=3)
        assert build_fix_prompt(scan) == ""

    def test_with_critical_inactive(self):
        rec = _make_record(line_type="main", title="核心剧情")
        ia = InactiveInfo(record=rec, gap_chapters=10, max_gap=3, severity="critical")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=5, inactive=[ia],
        )
        result = build_fix_prompt(scan)
        assert "明暗线推进修复指令" in result
        assert "核心剧情" in result
        assert "PLOTLINE_INACTIVE_CRITICAL" in result

    def test_with_high_inactive(self):
        rec = _make_record(line_type="sub", title="感情线")
        ia = InactiveInfo(record=rec, gap_chapters=15, max_gap=8, severity="high")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=5, inactive=[ia],
        )
        result = build_fix_prompt(scan)
        assert "感情线" in result
        assert "PLOTLINE_INACTIVE_HIGH" in result

    def test_density_warning(self):
        scan = PlotlineScanResult(
            current_chapter=100, total_active=15, density_warning=True,
        )
        result = build_fix_prompt(scan, warn_limit=10)
        assert "PLOTLINE_DENSITY_HIGH" in result
        assert "15" in result

    def test_footer_present(self):
        rec = _make_record()
        ia = InactiveInfo(record=rec, gap_chapters=15, max_gap=8, severity="high")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=5, inactive=[ia],
        )
        result = build_fix_prompt(scan)
        assert "修复时保持剧情自然流畅" in result


class TestBuildInactiveViolationList:
    def test_empty(self):
        scan = PlotlineScanResult(current_chapter=10, total_active=0)
        assert build_inactive_violation_list(scan) == []

    def test_single_violation(self):
        rec = _make_record(thread_id="pl_romance", line_type="sub", title="感情线")
        ia = InactiveInfo(record=rec, gap_chapters=15, max_gap=8, severity="high")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=3, inactive=[ia],
        )
        violations = build_inactive_violation_list(scan)
        assert len(violations) == 1
        v = violations[0]
        assert v["id"] == "PLOTLINE_INACTIVE_HIGH"
        assert v["severity"] == "high"
        assert v["must_fix"] is True
        assert v["thread_id"] == "pl_romance"
        assert v["line_type"] == "sub"
        assert "支线" in v["description"]

    def test_medium_not_must_fix(self):
        rec = _make_record(line_type="dark")
        ia = InactiveInfo(record=rec, gap_chapters=20, max_gap=15, severity="medium")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=3, inactive=[ia],
        )
        violations = build_inactive_violation_list(scan)
        assert violations[0]["must_fix"] is False

    def test_multiple_violations_sorted(self):
        recs = [
            (_make_record(thread_id="pl_dark", line_type="dark"), "medium"),
            (_make_record(thread_id="pl_main", line_type="main"), "critical"),
        ]
        inactives = [
            InactiveInfo(record=r, gap_chapters=20, max_gap=3, severity=s)
            for r, s in recs
        ]
        scan = PlotlineScanResult(
            current_chapter=100, total_active=5, inactive=inactives,
        )
        violations = build_inactive_violation_list(scan)
        assert len(violations) == 2
