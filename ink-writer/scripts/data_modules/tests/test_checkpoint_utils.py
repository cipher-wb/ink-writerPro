"""Tests for checkpoint_utils — ink-auto 检查点判断与报告解析。"""

import json

import pytest

from data_modules.checkpoint_utils import (
    CheckpointLevel,
    count_issues_by_severity,
    determine_checkpoint,
    disambiguation_urgency,
    get_disambiguation_backlog,
    report_has_issues,
    review_range,
)


# ───────── determine_checkpoint ─────────

class TestDetermineCheckpoint:
    def test_non_multiple_of_5_returns_no_action(self):
        for ch in (1, 3, 7, 12, 19, 23):
            level = determine_checkpoint(ch)
            assert not level.review
            assert level.audit is None
            assert level.macro is None
            assert not level.disambig

    def test_multiple_of_5_triggers_review(self):
        level = determine_checkpoint(5)
        assert level.review
        assert level.audit is None
        assert level.macro is None

    def test_multiple_of_10_triggers_quick_audit(self):
        level = determine_checkpoint(10)
        assert level.review
        assert level.audit == "quick"
        assert level.macro is None
        assert not level.disambig

    def test_multiple_of_20_triggers_full_checkpoint(self):
        level = determine_checkpoint(20)
        assert level.review
        assert level.audit == "standard"
        assert level.macro == "Tier2"
        assert level.disambig

    def test_chapter_40_is_20_multiple(self):
        level = determine_checkpoint(40)
        assert level.audit == "standard"
        assert level.macro == "Tier2"

    def test_chapter_15_is_5_only(self):
        level = determine_checkpoint(15)
        assert level.review
        assert level.audit is None

    def test_chapter_30_is_10_multiple(self):
        level = determine_checkpoint(30)
        assert level.review
        assert level.audit == "quick"
        assert level.macro is None

    def test_chapter_100_is_20_multiple(self):
        level = determine_checkpoint(100)
        assert level.audit == "standard"
        assert level.macro == "Tier2"
        assert level.disambig


# ───────── review_range ─────────

class TestReviewRange:
    def test_normal_range(self):
        assert review_range(10) == (6, 10)

    def test_early_chapter_clamps_start(self):
        assert review_range(3) == (1, 3)
        assert review_range(1) == (1, 1)

    def test_chapter_5(self):
        assert review_range(5) == (1, 5)

    def test_chapter_25(self):
        assert review_range(25) == (21, 25)


# ───────── report_has_issues ─────────

class TestReportHasIssues:
    def test_returns_false_for_missing_file(self, tmp_path):
        assert not report_has_issues(tmp_path / "nonexistent.md")

    def test_returns_false_for_clean_report(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# 审查报告\n\n所有指标正常，无问题。\n", encoding="utf-8")
        assert not report_has_issues(report)

    def test_detects_critical_english(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("## Issues\n- **Severity**: Critical\n", encoding="utf-8")
        assert report_has_issues(report)

    def test_detects_high_english(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("Found 1 high-severity issue\n", encoding="utf-8")
        assert report_has_issues(report)

    def test_detects_chinese_keywords(self, tmp_path):
        report = tmp_path / "report.md"
        for keyword in ["严重", "不一致", "漂移", "失衡", "逾期"]:
            report.write_text(f"发现{keyword}问题\n", encoding="utf-8")
            assert report_has_issues(report), f"未检测到关键词: {keyword}"

    def test_returns_false_for_empty_file(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("", encoding="utf-8")
        assert not report_has_issues(report)


# ───────── count_issues_by_severity ─────────

class TestCountIssues:
    def test_empty_file(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("", encoding="utf-8")
        counts = count_issues_by_severity(report)
        assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0}

    def test_mixed_severities(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text(
            "🔴 critical: 设定矛盾\n"
            "🟠 high: 连贯断裂\n"
            "🟠 high: 人设偏移\n"
            "🟡 medium: 节奏偏快\n"
            "🔵 low: 标点问题\n",
            encoding="utf-8",
        )
        counts = count_issues_by_severity(report)
        assert counts["critical"] == 1
        assert counts["high"] == 2
        assert counts["medium"] == 1
        assert counts["low"] == 1

    def test_missing_file(self, tmp_path):
        counts = count_issues_by_severity(tmp_path / "nope.md")
        assert all(v == 0 for v in counts.values())


# ───────── disambiguation ─────────

class TestDisambiguation:
    def test_get_backlog_normal(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"disambiguation_pending": [{"id": "a"}, {"id": "b"}]}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        assert get_disambiguation_backlog(tmp_path) == 2

    def test_get_backlog_missing_file(self, tmp_path):
        assert get_disambiguation_backlog(tmp_path) == 0

    def test_get_backlog_no_key(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")
        assert get_disambiguation_backlog(tmp_path) == 0

    def test_urgency_levels(self):
        assert disambiguation_urgency(0) == "normal"
        assert disambiguation_urgency(20) == "normal"
        assert disambiguation_urgency(21) == "warning"
        assert disambiguation_urgency(100) == "warning"
        assert disambiguation_urgency(101) == "critical"
