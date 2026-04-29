"""Tests for foreshadow fix prompt builder."""

from __future__ import annotations

import pytest

from ink_writer.foreshadow.fix_prompt_builder import (
    VIOLATION_FIX_TEMPLATES,
    build_fix_prompt,
    build_overdue_violation_list,
)
from ink_writer.foreshadow.tracker import (
    ForeshadowRecord,
    ForeshadowScanResult,
    OverdueInfo,
    SilentInfo,
)


def _make_record(**kwargs) -> ForeshadowRecord:
    defaults = {
        "thread_id": "fs_001",
        "title": "测试伏笔",
        "content": "内容",
        "priority": 50,
        "status": "active",
        "planted_chapter": 10,
        "last_touched_chapter": 20,
        "target_payoff_chapter": 30,
        "resolved_chapter": None,
    }
    defaults.update(kwargs)
    return ForeshadowRecord(**defaults)


class TestViolationTemplates:
    def test_all_templates_exist(self):
        expected = [
            "FORESHADOW_OVERDUE_CRITICAL",
            "FORESHADOW_OVERDUE_HIGH",
            "FORESHADOW_OVERDUE_MEDIUM",
            "FORESHADOW_SILENT",
            "FORESHADOW_DENSITY_HIGH",
        ]
        for key in expected:
            assert key in VIOLATION_FIX_TEMPLATES

    def test_templates_have_placeholders(self):
        assert "{title}" in VIOLATION_FIX_TEMPLATES["FORESHADOW_OVERDUE_CRITICAL"]
        assert "{overdue}" in VIOLATION_FIX_TEMPLATES["FORESHADOW_OVERDUE_CRITICAL"]
        assert "{silent}" in VIOLATION_FIX_TEMPLATES["FORESHADOW_SILENT"]


class TestBuildFixPrompt:
    def test_empty_scan_returns_empty(self):
        scan = ForeshadowScanResult(current_chapter=100, total_active=0)
        assert build_fix_prompt(scan) == ""

    def test_overdue_generates_prompt(self):
        rec = _make_record(thread_id="fs_1", title="三年之约", target_payoff_chapter=40)
        overdue = OverdueInfo(record=rec, overdue_chapters=15, severity="critical", grace_used=5)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=5,
            overdue=[overdue],
        )
        prompt = build_fix_prompt(scan)
        assert "伏笔生命周期修复指令" in prompt
        assert "三年之约" in prompt
        assert "15" in prompt

    def test_silent_generates_prompt(self):
        rec = _make_record(thread_id="fs_2", title="青莲火种", last_touched_chapter=30)
        silent = SilentInfo(record=rec, silent_chapters=70)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=5,
            silent=[silent],
        )
        prompt = build_fix_prompt(scan)
        assert "青莲火种" in prompt
        assert "70" in prompt

    def test_density_warning_generates_prompt(self):
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=20,
            density_warning=True,
        )
        prompt = build_fix_prompt(scan, warn_limit=15)
        assert "20" in prompt
        assert "15" in prompt

    def test_combined_prompt(self):
        rec1 = _make_record(thread_id="fs_1", title="伏笔A", target_payoff_chapter=40)
        rec2 = _make_record(thread_id="fs_2", title="伏笔B", last_touched_chapter=20)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=5,
            overdue=[OverdueInfo(record=rec1, overdue_chapters=10, severity="high", grace_used=10)],
            silent=[SilentInfo(record=rec2, silent_chapters=80)],
        )
        prompt = build_fix_prompt(scan)
        assert "伏笔A" in prompt
        assert "伏笔B" in prompt
        assert "修复时保持剧情自然流畅" in prompt


class TestBuildOverdueViolationList:
    def test_empty_scan(self):
        scan = ForeshadowScanResult(current_chapter=100, total_active=0)
        violations = build_overdue_violation_list(scan)
        assert violations == []

    def test_overdue_violations(self):
        rec = _make_record(thread_id="fs_1", title="核心伏笔", target_payoff_chapter=40)
        overdue = OverdueInfo(record=rec, overdue_chapters=10, severity="critical", grace_used=5)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=1,
            overdue=[overdue],
        )
        violations = build_overdue_violation_list(scan)
        assert len(violations) == 1
        assert violations[0]["id"] == "FORESHADOW_OVERDUE_CRITICAL"
        assert violations[0]["must_fix"] is True
        assert violations[0]["thread_id"] == "fs_1"

    def test_silent_violations(self):
        rec = _make_record(thread_id="fs_2", title="沉默伏笔", last_touched_chapter=10)
        silent = SilentInfo(record=rec, silent_chapters=90)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=1,
            silent=[silent],
        )
        violations = build_overdue_violation_list(scan)
        assert len(violations) == 1
        assert violations[0]["id"] == "FORESHADOW_SILENT"
        assert violations[0]["must_fix"] is False

    def test_medium_overdue_not_must_fix(self):
        rec = _make_record(thread_id="fs_1", priority=30, target_payoff_chapter=40)
        overdue = OverdueInfo(record=rec, overdue_chapters=10, severity="medium", grace_used=20)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=1,
            overdue=[overdue],
        )
        violations = build_overdue_violation_list(scan)
        assert violations[0]["must_fix"] is False
